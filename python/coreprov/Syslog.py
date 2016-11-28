import os, re
from .RemoteControl import RemoteControl

class Syslog(RemoteControl):
    syslog_docker_image = 'zultron/syslog-server'
    syslog_data_dir = '/media/state/syslog-data'
    syslog_log_dir = '%s/logs' % syslog_data_dir

    def pull_syslog_docker_image(self, host):
        ip = self.to_ip(host)
        print "Pulling docker image on host %s" % host
        self.remote_run('docker pull %s' % self.syslog_docker_image, ip)

    def syslog_file_path(self, fname):
        return os.path.join(self.syslog_data_dir, fname)

    def install_syslog_config(self, host):
        ip = self.to_ip(host)
        print "Installing rsyslog configuration on %s" % host

        self.remote_sudo('install -d -o core %s' % self.syslog_data_dir, ip)
        self.remote_sudo('install -d -o syslog %s' % self.syslog_log_dir, ip)

        self.put_file(
            ip, self.render_jinja2(host, 'rsyslog.conf'),
                self.syslog_file_path('rsyslog.conf'))

    def install_syslog_server(self):
        ip = self.to_ip(self.master)
        print 'Starting rsyslog services (on %s)' % self.master
        self.put_file(
            ip, self.render_file(host, 'syslog.service'),
            self.freeipa_file_path('ipa@.service'))
        self.remote_run(
            'fleetctl submit %s' % self.syslog_file_path('syslog.service'), ip)
        self.remote_run(
            'fleetctl start syslog.service', ip)
