# from .RemoteControl import RemoteControl
from CA import CA

class ProvisionIPSec(CA):
    ipsec_docker_image = 'philplckthun/strongswan'

    def pull_ipsec_docker_image(self, host):
        ip = self.to_ip(host)
        print "Pulling IPSec docker image %s on %s" % (
            self.ipsec_docker_image, host)
        self.remote_run('docker pull %s' % self.ipsec_docker_image, ip)

    def install_ipsec_certs(self, host):
        ip = self.to_ip(host)
        print "Installing IPSec certs on %s" % host
        if not self.hosts[host].has_key('cert'):
            self.gen_host_cert(host, ip)

        self.remote_sudo(
            'mkdir -p /media/state/ipsec/private '
            '/media/state/ipsec/certs '
            '/media/state/ipsec/cacerts', ip)
        self.remote_sudo('chown -R core /media/state/ipsec', ip)
        self.put_file(ip, self.hosts[host]['cert']['cert'],
                      '/media/state/ipsec/certs/cert.pem')
        self.put_file(ip, self.hosts[host]['cert']['key'],
                      '/media/state/ipsec/private/key.pem')
        self.put_file(ip, self.ca_cert,
                      '/media/state/ipsec/cacerts/ca-cert.pem')

    def gen_ipsec_config(self, host):
        res = self.render_file(host, 'ipsec.conf')
        for rh in self.hosts:
            if rh == host:  continue
            res += self.render_file(
                host, 'ipsec-conn.conf', extra_substitutions=dict(
                    conn_name='%s_to_%s' % (
                        self.short_hostname(host), self.short_hostname(rh)),
                    right_ip_address=self.to_ip(rh),
                    right_hostname=rh,
                ))
        return res

    def print_ipsec_config(self, host):
        print "ipsec.secrets:"
        print self.render_file(host, 'ipsec.secrets')
        print
        print "ipsec.conf:"
        print self.gen_ipsec_config(host)

    def install_ipsec_config(self, host):
        ip = self.to_ip(host)
        print "Installing IPSec configuration files on host %s" % host
        self.put_file(ip, self.render_file(host, 'ipsec.secrets'),
                      '/media/state/ipsec/ipsec.secrets')
        self.put_file(ip, self.gen_ipsec_config(host),
                      '/media/state/ipsec/ipsec.conf')
        self.put_file(ip, self.render_file(host, 'strongswan.conf'),
                      '/media/state/ipsec/strongswan.conf')

    def load_ipsec_unit(self, host=None):
        if host is None: host = self.hosts.keys()[0]
        ip = self.to_ip(host)
        print "Loading ipsec.service unit"
        self.put_file(ip, self.render_file(host, 'ipsec.service'),
                      '/media/state/ipsec/ipsec.service')
        self.remote_run('fleetctl submit /media/state/ipsec/ipsec.service', ip)
        self.remote_run('fleetctl load ipsec.service', ip)

    def start_ipsec(self, host=None):
        if host is None: host = self.hosts.keys()[0]
        ip = self.to_ip(host)
        print "Starting ipsec.service unit"
        self.remote_run('fleetctl start ipsec.service', ip)

    def install_ipsec(self, host):
        self.pull_ipsec_docker_image(host)
        self.install_ipsec_certs(host)
        self.install_ipsec_config(host)
        self.load_ipsec_unit(host)
        self.start_ipsec(host)
