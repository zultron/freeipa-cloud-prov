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

            print "Installing fleet ipa-server.service unit file"
            self.put_file(
                ip, self.render_file(host, 'ipa.service',
                                     extra_substitutions=dict(
                                         ipa_server_ip='')),
                self.freeipa_file_path('ipa-server.service'))
            self.remote_run('fleetctl submit %s' % \
                            self.freeipa_file_path('ipa-server.service'), ip)
            self.remote_run('fleetctl load ipa-server.service', ip)

            print "Installing fleet ipa-replica@.service unit file"
            self.put_file(
                ip, self.render_file(
                    host, 'ipa.service',
                    extra_substitutions=dict(
                        ipa_role='replica',
                        ipa_server_ip=self.to_ip(self.freeipa_master))),
                self.freeipa_file_path('ipa-replica@.service'))
            self.remote_run('fleetctl submit %s' % \
                            self.freeipa_file_path('ipa-replica@.service'), ip)
            for instance_num in range(len(self.freeipa_replicas)):
                self.remote_run('fleetctl load ipa-replica@%s.service' % \
                                instance_num, ip)
        else:

            self.put_file(
                ip, self.render_file(host, 'ipa-replica-install-options'),
                os.path.join(self.freeipa_data_dir,
                             'ipa-replica-install-options'))

    def start_freeipa_install(self, host):
        ip = self.to_ip(host)

    def install_rndc_config(self, host):
        ip = self.to_ip(self.freeipa_master)
        print 'Installing rndc config and key on %s' % host

        self.remote_run('docker exec -i ipa rndc-confgen -a', ip)
        self.remote_run('docker exec -i ipa restorecon /etc/rndc.key', ip)

    def install_freeipa_server(self):
        ip = self.to_ip(self.freeipa_master)
        print 'Running FreeIPA server install on %s' % self.freeipa_master
        self.remote_run('fleetctl start ipa-server.service', ip)
        self.remote_run_and_grep(
            'fleetctl journal -lines 0 -f ipa-server.service',
            ip, timeout=20*60,
            success_re=r'FreeIPA server configured\.',
            fail_re=r'Failed with result')
        self.install_rndc_config(self.freeipa_master)

        # Simple functionality test
        # kinit admin
        # ipa user-find admin

    def freeipa_fleet_replica_id(self, host):
        if self.hosts[host].has_key('fleet_replica_id'):
            return self.hosts[host]['fleet_replica_id']

        ip = self.to_ip(self.freeipa_master)
        filt = re.compile(r'ipa-replica@([0-9]+).service.*/([0-9.]+)\s')
        replica_ip = self.to_ip(host)
        print 'Running FreeIPA replica install on %s' % host
        o = self.remote_run_output('fleetctl list-units -l -no-legend', ip)
        res = None
        for line in o:
            m = filt.match(line)
            if m is not None and replica_ip == m.group(2):
                self.hosts[host]['fleet_replica_id'] = res = m.group(1)
        return res

    def install_ipa_replica(self, replica):
        ip = self.to_ip(self.freeipa_master)
        replica_ip = self.to_ip(replica)
        replica_id = self.freeipa_fleet_replica_id(replica)
        fname = 'replica-info-%s.gpg' % replica
        src = '%s/var/lib/ipa/%s' % (self.freeipa_data_dir, fname)
        dst = '%s/%s' % (self.freeipa_data_dir, fname)

        print 'Preparing FreeIPA replica info for %s' % replica
        self.remote_run(
            'docker exec -i ipa ipa-replica-prepare %s'
            ' --ip-address %s --no-reverse' % (replica, replica_ip), ip,
            stdin_in='%s\n' % self.ds_password, read_stdout=False)
        self.remote_sudo('mv %s %s' % (src, dst), ip)
        self.remote_sudo('chown core %s' % dst, ip)
        replica_info = self.get_file(ip, dst)
        self.put_file(replica_ip, replica_info, dst)

        print 'Running FreeIPA replica install on %s' % replica
        self.remote_run('fleetctl start ipa-replica@%s.service' % replica_id,
                        replica_ip)
        self.remote_run_and_grep(
            'fleetctl journal -lines 0 -f ipa-replica@%s.service' % replica_id,
            replica_ip, timeout=20*60,
            success_re=r'FreeIPA server configured\.',
            fail_re=r'Failed with result')
        self.install_rndc_config(replica)
