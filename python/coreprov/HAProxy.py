import os
from .FreeIPA import FreeIPA

class HAProxy(FreeIPA):
    haproxy_docker_image = 'haproxy'
    haproxy_data_dir = '/media/state/haproxy-data'

    def pull_haproxy_docker_image(self, host):
        print "Pulling docker image on host %s" % host
        self.remote_run('docker pull %s' % self.haproxy_docker_image, host)

    def haproxy_file_path(self, fname):
        return os.path.join(self.haproxy_data_dir, fname)

    def install_haproxy_certs(self, host):
        print "Installing HAProxy certs on %s" % host

        self.create_svc_principal(host, 'HAPROXY')
        self.issue_cert_pem(
            host, "HAPROXY",
            self.haproxy_file_path('cert.pem'),
            self.haproxy_file_path('key.pem'),
            ca_cert_fname=self.haproxy_file_path('ca.pem'),
            exec_host=host)

    def install_haproxy_config(self, host):
        print "Installing HAProxy config file on %s" % host

        self.remote_sudo('install -d -o core %s' % self.haproxy_data_dir, host)
        self.put_file(
            host, self.render_jinja2(host, 'haproxy.cfg'),
                self.haproxy_file_path('haproxy.cfg'))

    def start_haproxy_server(self, host=None):
        if host is None:  host=self.initial_host

        if host == self.initial_host:
            print 'Installing HAProxy (and sidekick) service'
            self.put_file(
                host, self.render_jinja2(
                    self.initial_host, 'haproxy.service'),
                self.haproxy_file_path('haproxy.service'))
            self.put_file(
                host, self.render_jinja2(
                    self.initial_host, 'haproxy-iptables.service'),
                self.haproxy_file_path('haproxy-iptables.service'))
            self.remote_run(
                'fleetctl submit %s' %
                self.haproxy_file_path('haproxy.service'), host)
            self.remote_run(
                'fleetctl submit %s' %
                self.haproxy_file_path('haproxy-iptables.service'), host)
            self.remote_run('fleetctl load haproxy.service', host)
            self.remote_run('fleetctl load haproxy-iptables.service', host)

        print 'Starting HAProxy service on %s' % host
        self.remote_run(
            'fleetctl start haproxy.service', host)
