import os, re
from .RemoteControl import RemoteControl

# https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/6/html/Identity_Management_Guide/install-command.html

class FreeIPA(RemoteControl):
    freeipa_docker_image = 'adelton/freeipa-server:centos-7'
    freeipa_docker_client_image = 'zultron/docker-freeipa:centos-7-client'
    freeipa_data_dir = '/media/state/ipa-data'

    def pull_freeipa_docker_image(self, host):
        ip = self.to_ip(host)
        print "Pulling docker image on host %s" % host
        self.remote_run('docker pull %s' % self.freeipa_docker_image, ip)

    @property
    def freeipa_master(self):
        masters = [h for h in self.hosts \
                   if self.hosts[h]['ipa_role'] == 'server']
        if len(masters) != 1:
            raise RuntimeError(
                "Exactly one host must have 'ipa_role: replica' in config")
        return masters[0]

    @property
    def freeipa_replicas(self):
        return [h for h in self.hosts \
                if self.hosts[h]['ipa_role'] == 'replica']

    def is_master(self, host):
        return host == self.freeipa_master

    def freeipa_file_path(self, fname):
        return os.path.join(self.freeipa_data_dir, fname)

    def install_freeipa_config(self, host):
        ip = self.to_ip(host)

        if self.is_master(host):
            fname = 'ipa-server-install-options'
        else:
            fname = 'ipa-replica-install-options'

        print "Installing %s on %s" % (fname, host)

        self.remote_sudo('install -d -o core %s' % self.freeipa_data_dir, ip)
        self.put_file(
            ip, self.render_jinja2(host, fname), self.freeipa_file_path(fname))

    def init_ipa_service(self, host):
        ip = self.to_ip(host)

        print 'Running FreeIPA install on %s' % host
        self.remote_run(
            "docker run -d"
            "    --hostname %(hostname)s"
            "    --name ipa"
            "    --volume /media/state/ipa-data:/data"
            "    --volume /sys/fs/cgroup:/sys/fs/cgroup:ro"
            "    --net cnet --ip %(ipa_ip)s"
            "    -e IPA_SERVER_IP=%(ip_address)s"
            "    adelton/freeipa-server:centos-7" %
            self.substitutions(host),
            ip)
        self.remote_run_and_grep(
            "docker attach ipa",
            ip, timeout=20*60,
            success_re=r'FreeIPA server configured\.',
            fail_re=r'Failed with result')
        self.install_rndc_config(host)
        self.harden_named(host)
        self.harden_ldap(host)
        self.kinit_admin(host)
        self.named_disable_zone_transfers(host)

        # Simple functionality test
        # kinit admin
        # ipa user-find admin


    def install_rndc_config(self, host):
        ip = self.to_ip(host)
        print 'Installing rndc config and key on %s' % host

        self.remote_run('docker exec -i ipa rndc-confgen -a', ip)
        self.remote_run('docker exec -i ipa restorecon /etc/rndc.key', ip)

    # Hardening IPA:
    # https://www.redhat.com/archives/freeipa-users/2014-April/msg00246.html
    def harden_named(self, host):
        ip = self.to_ip(host)
        print "Restricting DNS recursion and zone transfers on %s" % host
        acl="127.0.0.1; 10.0.0.0/8;"
        self.remote_docker_exec(
            ip, 'ipa',
            "sed -i /data/etc/named.conf"
            " -e '/allow-recursion/ s,any;,%s,'"
            " -e '/allow-recursion/ a\        allow-transfer { none; };'" %
            acl, quiet=False)

        self.remote_docker_exec(
            ip, 'ipa',
            "systemctl restart named-pkcs11.service",
            quiet=False)

    def harden_ldap(self, host):
        ip = self.to_ip(host)
        print "Restricting LDAP anonymous binds on %s" % host
        input = (
            "dn: cn=config\n"
            "changetype: modify\n"
            "replace: nsslapd-allow-anonymous-access\n"
            "nsslapd-allow-anonymous-access: rootdse\n"
            "\n")
        self.remote_run(
            'echo "%s" | docker exec -i ipa '
            'ldapmodify -c -x -D "cn=Directory Manager" -w %s' %
            (input, self.ds_password), ip, stdin_in=input, get_pty=True)

    def named_disable_zone_transfers(self, host, domain=None):
        ip = self.to_ip(host)
        if domain is None:  domain = self.domain_name
        print "Disabling DNS zone transfers on %s" % host
        self.remote_docker_exec(
            ip, 'ipa',
            "ipa dnszone-mod %s --allow-transfer='none;'" % domain,
            quiet=False)

    def ipa_set_default_login_shell(self, host):
        ip = self.to_ip(host)
        print "Setting default shell to /bin/bash"
        self.remote_docker_exec(
            ip, 'ipa', "ipa config-mod --defaultshell /bin/bash",
            quiet=False)

    def install_ipa_service(self, host):
        ip = self.to_ip(host)

        if host == self.freeipa_master:
            print "Installing fleet ipa.service unit file"
            self.put_file(
                ip, self.render_jinja2(host, 'ipa.service'),
                self.freeipa_file_path('ipa.service'))
            self.remote_run(
                'fleetctl submit %s' % \
                self.freeipa_file_path('ipa.service'), ip)
            self.remote_run('fleetctl load ipa.service', ip)

        else:
            server_ip = self.to_ip(self.freeipa_master)
            fname = 'replica-info-%s.gpg' % host
            src = '%s/var/lib/ipa/%s' % (self.freeipa_data_dir, fname)
            dst = '%s/%s' % (self.freeipa_data_dir, fname)

            print 'Preparing FreeIPA replica info for %s' % host
            self.remote_run(
                'docker exec -i ipa ipa-replica-prepare %s'
                ' --ip-address %s --no-reverse' % (host, ip), server_ip,
                stdin_in='%s\n' % self.ds_password, read_stdout=False)
            self.remote_sudo('mv %s %s' % (src, dst), server_ip)
            self.remote_sudo('chown core %s' % dst, server_ip)
            replica_info = self.get_file(server_ip, dst)
            self.put_file(ip, replica_info, dst)

        print 'Running FreeIPA install on %s' % host
        self.remote_run('systemctl start ipa.service', ip)
        self.remote_run_and_grep(
            'journalctl -fu ipa.service -n 0',
            ip, timeout=20*60,
            success_re=r'FreeIPA server configured\.',
            fail_re=r'Failed with result')
        self.install_rndc_config(host)

        # Simple functionality test
        # kinit admin
        # ipa user-find admin

    def kinit_admin(self, host):
        ip = self.to_ip(host)
        print "Initializing kerberos ticket for admin on %s" % host
        self.remote_docker_exec(
            ip, 'ipa',
            'bash -c \"echo %s | kinit admin\" >/dev/null' %
            self.admin_password, quiet=False)

    def install_resolv_conf(self, host):
        ip = self.to_ip(host)
        print "Installing /etc/resolv.conf on %s" % host
        # resolv_conf = ''.join(
        #     [ 'nameserver %s\n' % self.hconfig(h, 'ip_address')
        #       for h in self.hosts ])
        resolv_conf = 'nameserver %s\n' % self.hconfig(host, 'ipa_ip')
        self.put_file(ip, resolv_conf, '/tmp/resolv.conf')
        self.remote_sudo('mv /tmp/resolv.conf /etc/resolv.conf', ip)

    def install_ipa_client(self, host):
        ip = self.to_ip(host)

        print "Installing IPA client on host %s" % host
        self.remote_run(
            "docker pull %s" % self.freeipa_docker_client_image, ip)
        install_opts = "-N --force-join --force --server=%s" \
            " --fixed-primary --domain=zultron.com" % host
        self.remote_run_and_grep(
            "docker run -it --privileged --rm"
            "    --name ipa_client"
            "    -e IPA_PORT_53_UDP_ADDR=%(ip_address)s"
            "    -e PASSWORD=%(admin_password)s"
            "    -e IPA_PORT_80_TCP_ADDR=%(ip_address)s"
            "    -e IPA_CLIENT_INSTALL_OPTS=\"%(install_opts)s\""
            "    -h ipaclient-%(hostname)s"
            "    --net %(network_name)s --ip %(ipa_client_ip)s"
            "    %(image)s" %
            self.substitutions(host, extra_substitutions=dict(
                image = self.freeipa_docker_client_image,
                install_opts = install_opts)),
            ip, success_re=r'FreeIPA-enrolled', fail_re=r'docker: Error',
            get_pty=True)
