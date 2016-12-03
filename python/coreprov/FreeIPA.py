import os, ipcalc
from .RemoteControl import RemoteControl

# https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/6/html/Identity_Management_Guide/install-command.html

class FreeIPA(RemoteControl):
    freeipa_docker_image = 'adelton/freeipa-server:centos-7'
    freeipa_docker_client_image = 'zultron/freeipa-cloud-prov:ipaclient'
    freeipa_data_dir = os.path.join(RemoteControl.state_dir, 'ipa-data')
    cert_db_dir = os.path.join(freeipa_data_dir, 'root')

    def pull_freeipa_docker_image(self, host):
        print "Pulling docker image on host %s" % host
        self.remote_run('docker pull %s' % self.freeipa_docker_image, host)

    @property
    def freeipa_master(self):
        masters = [h for h in self.hosts if h == self.initial_host]
        if len(masters) != 1:
            raise RuntimeError(
                "Exactly one host must have 'bootstrap_order: 0' in config")
        return masters[0]

    @property
    def freeipa_replicas(self):
        return [h for h in self.hosts if h != self.initial_host]

    def is_master(self, host):
        return host == self.freeipa_master

    def freeipa_file_path(self, fname=""):
        return os.path.join(self.freeipa_data_dir, fname)

    def install_freeipa_config(self, host):
        if self.is_master(host):
            fname = 'ipa-server-install-options'
        else:
            fname = 'ipa-replica-install-options'

        print "Installing %s on %s" % (fname, host)

        self.remote_sudo('install -d -o core %s' % self.freeipa_data_dir, host)
        self.put_file(
            host, self.render_jinja2(host, fname), self.freeipa_file_path(fname))


    def install_ipa_service(self, host):
        name = 'ipa@%s.service'% self.hconfig(host, 'host_id')
        if host == self.initial_host:
            print "Installing fleet ipa@.service unit file"
            self.put_file(
                host, self.render_jinja2(host, 'ipa@.service'),
                self.freeipa_file_path('ipa@.service'))
            self.remote_run(
                'fleetctl submit %s' % \
                self.freeipa_file_path('ipa@.service'), host)

        else:
            replica_ip = self.to_ip(host)
            server_ip = self.to_ip(self.initial_host)
            fname = 'replica-info-%s.gpg' % host
            src = '%s/var/lib/ipa/%s' % (self.freeipa_data_dir, fname)
            dst = '%s/%s' % (self.freeipa_data_dir, fname)

            print 'Preparing FreeIPA replica info for %s' % host
            self.remote_run(
                'docker exec -i ipa ipa-replica-prepare %s'
                ' --ip-address %s --no-reverse' % (host, replica_ip),
                self.initial_host,
                stdin_in='%s\n' % self.ds_password, read_stdout=False)
            self.remote_sudo('mv %s %s' % (src, dst), self.initial_host)
            self.remote_sudo('chown core %s' % dst, self.initial_host)
            replica_info = self.get_file(self.initial_host, dst)
            self.put_file(host, replica_info, dst)

        print 'Running FreeIPA install on %s' % host
        self.remote_run('fleetctl load %s'% name, host)
        self.remote_sudo('systemctl start --no-block %s' % name, host)
        self.remote_run_and_grep(
            'journalctl -fu %s -n 0' % name,
            host, timeout=20*60,
            success_re=r'FreeIPA server configured\.',
            fail_re=r'(Failed with result|FreeIPA server configuration failed)')

        # Simple functionality test
        # kinit admin
        # ipa user-find admin


    def install_ipaclient(self, host):
        name = 'ipaclient@%s.service'% self.hconfig(host, 'host_id')
        if host == self.freeipa_master:
            print "Installing fleet ipaclient@.service unit file"
            self.remote_sudo(
                "install -d -o core %s" % self.freeipa_file_path(), host)
            self.put_file(
                host, self.render_jinja2(
                    host, 'ipaclient@.service',
                    DOCKER_IMAGE=self.freeipa_docker_client_image),
                self.freeipa_file_path('ipaclient@.service'))
            self.remote_run(
                'fleetctl submit %s' % \
                self.freeipa_file_path('ipaclient@.service'), host)
            self.remote_run('fleetctl load %s' % name, host)

        print 'Running FreeIPA client install on %s' % host
        self.remote_run('fleetctl start %s' % name, host)
        self.remote_run_and_grep(
            'journalctl -fu %s -n 0' % name,
            host, timeout=20*60,
            success_re=r'FreeIPA-enrolled',
            fail_re=r'(docker: Error|Failed with result)')

    def ipa_client_exec(self, command, host=None, **kwargs):
        if host is None:  host = self.freeipa_master
        return self.remote_docker_exec(
            host, 'ipaclient', command, **kwargs)

    def kinit_admin(self, host=None):
        if host is None:  host = self.freeipa_master
        print "Initializing kerberos ticket for admin on %s" % host
        self.ipa_client_exec(
            'bash -c \"echo %s | kinit admin\" >/dev/null' %
            self.admin_password, quiet=False)
        self.ipa_client_exec(
            'klist', quiet=False)

    def install_rndc_config(self, host):
        print 'Installing rndc config and key on %s' % host

        self.remote_run('docker exec -i ipa rndc-confgen -a', host)
        self.remote_run('docker exec -i ipa restorecon /etc/rndc.key', host)

    # Hardening IPA:
    # https://www.redhat.com/archives/freeipa-users/2014-April/msg00246.html
    def harden_named(self, host):
        print "Restricting DNS recursion and zone transfers on %s" % host
        acl="127.0.0.1; 10.0.0.0/8;"
        self.remote_docker_exec(
            host, 'ipa',
            "sed -i /data/etc/named.conf"
            " -e '/allow-recursion.*any/ s,any;,%s,'"
            " -e '/allow-recursion.*any/ a\        allow-transfer { none; };'" %
            acl, quiet=False)

        self.remote_docker_exec(
            host, 'ipa',
            "systemctl restart named-pkcs11.service",
            quiet=False)

    def harden_ldap(self, host):
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
            (input, self.ds_password), host, stdin_in=input, get_pty=True)

    def ipa_fix_https_redirect(self, host):
        print "Disabling IPA web UI redirect to https on %s" % host
        self.remote_docker_exec(
            host, 'ipa',
            "sed -i /data/etc/httpd/conf.d/ipa-rewrite.conf"
            " -e '/RewriteCond.*SERVER_PORT/,+3 s/^/#/'", quiet=False)
        self.remote_docker_exec(
            host, 'ipa',
            "systemctl restart httpd.service", quiet=False)

    def named_disable_zone_transfers(self, host=None, domain=None):
        if domain is None:  domain = self.domain_name
        print "Disabling DNS zone transfers in IPA"
        self.ipa_client_exec(
            "ipa dnszone-mod %s --allow-transfer='none;'" % domain)

    def ipa_set_default_login_shell(self, host):
        print "Setting default shell to /bin/bash"
        self.ipa_client_exec(
            "ipa config-mod --defaultshell /bin/bash")

    def ptr_record(self, ip):
        (a,b,c,d) = ip.split('.')
        return (d, "%s.%s.%s.in-addr.arpa" % (c,b,a))

    def zone_and_host(self, name):
        return list(reversed(name.split('.',1)))

    def dns_local_zone_add(self, name):
        print "Adding DNS local zone for %s" % (name)
        self.ipa_client_exec(
            "ipa dnszone-add %s --forward-policy=none" % name)

    def dns_a_record_del(self, name, ip=None):
        zone, host = self.zone_and_host(name)
        if ip is None:
            print "Removing DNS A records for %s" % (name)
            self.ipa_client_exec(
                "ipa dnsrecord-del %s %s --del-all" % (zone, host))
        else:
            print "Removing DNS A record for %s -> %s" % (name, ip)
            self.ipa_client_exec(
                "ipa dnsrecord-del %s %s --a-rec=%s" % (zone, host, ip))

    def dns_ptr_record_del(self, ip, name=None):
        last_octet, zone = self.ptr_record(ip)
        if name is None:
            print "Removing DNS ptr records for %s" % (ip)
            self.ipa_client_exec(
                "ipa dnsrecord-del %s %s --del-all" %
                (zone, last_octet))
        else:
            print "Removing DNS ptr record for %s -> %s" % (ip, name)
            self.ipa_client_exec(
                "ipa dnsrecord-del %s %s --ptr-rec=%s." %
                (zone, last_octet, name))

    def dns_local_host_add(self, name, ip, reverse=True):
        print "Adding DNS records for %s (%s)" % (name, ip)
        (zone, short) = self.zone_and_host(name)
        reverse_arg = "--a-create-reverse" if reverse else ""
        self.ipa_client_exec(
            "ipa dnsrecord-add %s %s --a-ip-address=%s %s" %
            (zone, short, ip, reverse_arg))

    def local_zone(self, host, name=None):
        if host is None: host = self.freeipa_master
        if name is not None:
            return '%s.%s' % (name, self.local_zone(host))
        else:
            return '%s.%s' % (self.hconfig(host, 'region'), self.domain_name)

    def ipa_init_dns(self, host):
        self.dns_local_zone_add(self.local_zone(host))
        if host == self.initial_host:
            # IPA server:  Clear auto-added IPA local reverse IP entry
            self.dns_ptr_record_del(self.hconfig(host, 'ipa_ip'), host)
        else:
            # IPA replicas:  Add reverse zone
            rev_local_zone = self.ptr_record(self.hconfig(host, 'ipa_ip'))[1]
            self.dns_local_zone_add(rev_local_zone)
        # Fix auto-added `ipa-ca` entry
        self.dns_a_record_del('ipa-ca.%s' % self.domain_name,
                              self.hconfig(host, 'ipa_ip'))
        self.dns_local_host_add('ipa-ca.%s' % self.domain_name,
                                self.hconfig(host, 'ip_address'),
                                reverse=False)
        # Add host internal record host.domain -> x.x.x.1
        self.dns_local_host_add(
            self.local_zone(host, self.zone_and_host(host)[1]),
            ipcalc.Network(self.hconfig(host,'network')['subnet'])[1])
        # Add basic containers
        for name in ('ipa', 'syslog', 'haproxy', 'ipaclient'):
            self.dns_local_host_add(
                self.local_zone(host, name),
                self.hconfig(host, '%s_ip' % name))

    def create_svc_principal(self, princ_host, svc,
                             exec_host=None, mgr_host=None):
        print "Creating service principal %s/%s" % (svc, princ_host)
        self.kinit_admin(exec_host)
        # Create service principal
        self.ipa_client_exec(
            "ipa service-add %s/%s" % (svc, princ_host), exec_host)
        # Delegate service admin to host
        if mgr_host is None: mgr_host = princ_host
        self.ipa_client_exec(
            "ipa service-add-host --hosts=%s %s/%s" % (
                self.local_zone(mgr_host, 'ipaclient'), svc, princ_host),
            exec_host)

    def issue_cert_pem(self, cn, svc, cert_fname, key_fname,
                       ca_cert_fname=None, exec_host=None, altname_ips=[]):
        if exec_host is None: exec_host = cn
        print "Creating pem cert on host %s for %s/%s" % (exec_host, svc, cn)
        dirs = dict([(os.path.dirname(f), 1) for f in (cert_fname, key_fname)])
        for d in dirs:
            self.remote_sudo("mkdir -p %s" % d, exec_host)
        # Request cert from certmonger
        cl = ("ipa-getcert request -w -f '%s' -k '%s' -K %s/%s -N '%s'"
              " -g 2048" + ''.join([" -A %s" for i in altname_ips]))
        vals = [cert_fname, key_fname, svc, cn, cn] + altname_ips
        if ca_cert_fname is not None:
            cl += " -F '%s'"
            vals.append(ca_cert_fname)
        self.ipa_client_exec(cl % tuple(vals), host=exec_host)
        # Check cert request
        self.ipa_client_exec(
            "ipa-getcert list -f '%s'" % cert_fname, host=exec_host)
        # Check cert status
        # self.ipa_client_exec(
        #     "openssl x509 -in '%s' -noout -text" % cert_fname, host=exec_host)

    def issue_cert_nss(self, host, cert_db, cn, svc):
        subject = "CN=%s,OU=%s,O=%s" % (cn, svc, self.realm)
        passf = os.path.join(cert_db, 'pass.txt')
        # noisef = os.path.join(cert_db, 'noise.bin')
        csrf = os.path.join(cert_db, 'csr.pem')
        print "Creating cert on host %s for '%s'" % (host, subject)
        # Create service principal
        self.ipa_client_exec(
            "ipa service-add %s/%s" % (svc, host))
        # Init DB
        self.ipa_client_exec(
            "rm -rf '%s'" % cert_db, host=host)
        self.ipa_client_exec(
            "install -d -o core -m 0700 '%s'" % cert_db, host=host)
        self.put_file(host, "%s\n" % self.admin_password, passf, mode=0700)
        # self.ipa_client_exec(
        #     "openssl rand -out '%s' 2048" % noisef, host=host)
        self.ipa_client_exec(
            "certutil -N -d '%s' -f '%s'" %
            (cert_db, passf), host=host)
        # Import CA cert
        self.ipa_client_exec(
            "bash -c \"certutil -A -d '%s' -f '%s' -n '%s IPA CA' -t CT,, -a "
            "< /etc/ipa/ca.crt\"" % (cert_db, passf, self.realm), host=host)
        # Create CSR
        self.ipa_client_exec(
            "ipa-getcert request -d '%s' -f '%s' -n cert -K %s/%s -N '%s' -g 2048" %
            (cert_db, passf, svc, host, subject), host=host)
        # Check cert
        self.ipa_client_exec(
            "ipa-getcert list -d '%s' -n cert" % cert_db, host=host)
        self.ipa_client_exec(
            "certutil -V -u V -d '%s' -n cert" % cert_db, host=host)
        
    def install_etcd_certs(self, host):
        print "Installing CoreOS etcd2 certs on host %s" % host
        self.issue_cert_pem(
            host, "ETCD",
            self.serv_cert_file_path,
            self.serv_key_file_path,
             ca_cert_fname=self.ca_cert_file_path)
        self.remote_sudo("chown etcd %s %s" %
                         (self.serv_cert_file_path, self.serv_key_file_path),
                         host)
        self.issue_cert_pem(
            host, "ETCD",
            self.clnt_cert_file_path,
            self.clnt_key_file_path)
        self.remote_sudo("chmod a+r %s %s %s" %
                         (self.clnt_cert_file_path, self.clnt_key_file_path,
                          self.ca_cert_file_path), host)

    def ipa_host_add(self, host, ip_addr=None, no_reverse=False, ipa_host=None):
        ip_args="" if ip_addr is None \
            else "--force --ip-address=%s" % ip_addr
        if no_reverse:  ip_args+=" --no-reverse"
        self.ipa_client_exec(
            "ipa host-add %s %s" % (ip_args, host), host=ipa_host)

    def early_bootstrap(self, host):
        if self.is_bootstrapped(host):
            print "Host %s already bootstrapped" % host
            return
        self.kinit_admin()
        if host == self.initial_host:
            # Initial cluster bootstrap
            self.install_bootstrap_etcd_dropin(host)
            self.install_bootstrap_fleet_dropin(host)
        else:
            # Add new member to cluster
            # - Generate SSL certs on existing member and copy to new member
            self.create_svc_principal(host, 'ETCD', self.initial_host,
                                      self.initial_host)
            cert_path = "%s/%s_etcd.pem" % (self.etcd_config_path, host)
            key_path = "%s/%s_etcd-key.pem" % (self.etcd_config_path, host)
            self.issue_cert_pem(
                host, 'ETCD',
                cert_path, key_path, exec_host=self.freeipa_master)
            self.remote_sudo(
                "chown core %s/%s_etcd*.pem" % (self.etcd_config_path, host),
                self.freeipa_master)
            cert = self.get_file(self.freeipa_master, cert_path)
            key = self.get_file(self.freeipa_master, key_path)
            ca = self.get_file(self.freeipa_master, self.ca_cert_file_path)
            self.remote_sudo(
                "install -d -o core %s" % self.etcd_config_path, host)
            self.put_file(host, cert, self.serv_cert_file_path)
            self.put_file(host, key, self.serv_key_file_path)
            self.put_file(host, ca, self.ca_cert_file_path)
            self.put_file(host, cert, self.clnt_cert_file_path)
            self.put_file(host, key, self.clnt_key_file_path)
            # - Be sure iptables & /etc/hosts etc. are all current on master
            self.init_iptables(self.initial_host)
            self.install_update_config(self.initial_host)
            # - Add member to cluster
            self.etcdctl_run("member add %s https://%s:2380" % (host, host))
        self.is_bootstrapped(host, False)
        self.pickle_config()

    def configure_ipa_server(self, host):
        print "Configuring IPA service on %s" % host
        # named config
        self.install_rndc_config(host)
        self.harden_named(host)
        # ldap config
        self.harden_ldap(host)
        # apache config
        self.ipa_fix_https_redirect(host)
        # IPA config
        self.kinit_admin(host)
        if host == self.freeipa_master:
            self.named_disable_zone_transfers(host)
            self.ipa_set_default_login_shell(host)
        # DNS
        self.ipa_init_dns(host)
        # etcd certs
        if host == self.freeipa_master:
            self.create_svc_principal(host, 'ETCD')
        self.install_etcd_certs(host)
        self.remove_temp_bootstrap_config(host)
        self.install_update_config(host)
