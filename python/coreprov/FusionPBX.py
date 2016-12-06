import os
from .FreeIPA import FreeIPA

class FusionPBX(FreeIPA):
    fusionpbx_docker_image = 'zultron/fusionpbx-docker'
    fusionpbx_data_dir = '/media/state/fusionpbx-data'

    def pull_fusionpbx_docker_image(self, host):
        print "Pulling FusionPBX docker image on host %s" % host
        self.remote_run('docker pull %s' % self.fusionpbx_docker_image, host)

    def fusionpbx_file_path(self, fname=None):
        if fname is None: return self.fusionpbx_data_dir
        return os.path.join(self.fusionpbx_data_dir, fname)

    def install_fusionpbx_certs(self, host):
        print "Installing FusionPBX certs on %s" % host

        self.create_svc_principal(host, 'PBX')
        self.issue_cert_pem(
            host, "PBX",
            self.fusionpbx_file_path('cert.pem'),
            self.fusionpbx_file_path('key.pem'),
            ca_cert_fname=self.fusionpbx_file_path('ca.pem'),
            exec_host=host)

    def start_fusionpbx_server(self, host):
        if not self.hconfig(host).has_key('pbx_ip'):
            print "PBX not configured for host %s" % host
            return

        print 'Installing FusionPBX service on host %s' % host
        hid = self.hconfig(host, 'host_id')
        self.remote_sudo(
            'install -d -o core %s' % self.fusionpbx_file_path(), host)
        self.render_and_put(
            host, 'pbx@.service', self.fusionpbx_file_path('pbx@.service'))
        self.remote_run(
            'fleetctl submit %s' %
            self.fusionpbx_file_path('pbx@.service'), host)
        self.remote_run('fleetctl load pbx@%s.service' % hid, host)

        print 'Starting Fusionpbx service on %s' % host
        self.remote_run('fleetctl start pbx@%s.service' % hid, host)

        print 'Be sure iptables, system.env and HAProxy configuration are'
        print 'up to date, and configure FusionPBX with password %s' % \
            self.hconfig(host, 'pbx_db_pass')
        print 'at https://%s/pbx' % host

    def install_fusionpbx_config(self, host):
        print "Installing FusionPBX config on %s" % host

        self.remote_sudo(
            'install -d -o core %s' % self.fusionpbx_file_path(), host)
        self.render_and_put(
            host, 'pbx-start-helper.sh',
            self.fusionpbx_file_path('pbx-start-helper.sh'),
            raw=True)
