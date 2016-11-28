import os, re
from .RemoteControl import RemoteControl

# https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/6/html/Identity_Management_Guide/install-command.html

class FreeIPA(RemoteControl):
    freeipa_docker_image = 'adelton/freeipa-server:centos-7'
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
        print "Setting up FreeIPA %s %s" % \
            ('server' if self.is_master(host) else 'replica', host)

        self.remote_sudo('install -d -o core %s' % self.freeipa_data_dir, ip)

        if self.is_master(host):

            print "Installing ipa-server-install-options"
            self.put_file(
                ip, self.render_file(host, 'ipa-server-install-options'),
                self.freeipa_file_path('ipa-server-install-options'))

            print "Installing fleet ipa.service unit file"
            self.put_file(
                ip, self.render_jinja2(host, 'ipa.service'),
                self.freeipa_file_path('ipa.service'))
            self.remote_run(
                'fleetctl submit %s' % \
                self.freeipa_file_path('ipa.service'), ip)
            self.remote_run('fleetctl load ipa.service', ip)

        else:

            self.put_file(
                ip, self.render_file(host, 'ipa-replica-install-options'),
                os.path.join(self.freeipa_data_dir,
                             'ipa-replica-install-options'))

    def install_rndc_config(self, host):
        ip = self.to_ip(self.freeipa_master)
        print 'Installing rndc config and key on %s' % host

        self.remote_run('docker exec -i ipa rndc-confgen -a', ip)
        self.remote_run('docker exec -i ipa restorecon /etc/rndc.key', ip)

    def install_ipa(self, host):
        ip = self.to_ip(host)

        if host != self.freeipa_master:
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
