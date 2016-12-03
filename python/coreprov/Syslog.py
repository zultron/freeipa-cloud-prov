import os, re
from .RemoteControl import RemoteControl

class Syslog(RemoteControl):
    syslog_docker_image = 'zultron/freeipa-cloud-prov:syslog'
    syslog_data_dir = '/media/state/syslog-data'
    syslog_log_dir = '%s/logs' % syslog_data_dir

    def pull_syslog_docker_image(self, host):
        print "Pulling docker image on host %s" % host
        self.remote_run('docker pull %s' % self.syslog_docker_image, host)

    def syslog_file_path(self, fname):
        return os.path.join(self.syslog_data_dir, fname)

    def install_syslog_config(self, host):
        print "Installing rsyslog configuration on %s" % host

        self.remote_sudo('install -d -o core %s' % self.syslog_data_dir, host)
        self.remote_sudo('install -d -o syslog %s' % self.syslog_log_dir, host)

        self.put_file(
            host, self.render_jinja2(host, 'rsyslog.conf'),
                self.syslog_file_path('rsyslog.conf'))

    def start_syslog_server(self):
        print 'Starting syslog services (on %s)' % self.initial_host
        self.put_file(
            self.initial_host,
            self.render_jinja2(self.initial_host, 'syslog.service'),
            self.syslog_file_path('syslog.service'))
        self.remote_run(
            'fleetctl submit %s' % self.syslog_file_path('syslog.service'),
            self.initial_host)
        self.remote_run(
            'fleetctl start syslog.service', self.initial_host)
