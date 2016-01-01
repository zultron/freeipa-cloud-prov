# Set up SSL for CoreOS compenents:  etcd, fleet, locksmith
#
# https://coreos.com/os/docs/latest/generate-self-signed-certificates.html
# https://coreos.com/etcd/docs/latest/etcd-live-http-to-https-migration.html
# https://coreos.com/etcd/docs/latest/tls-etcd-clients.html#configure-locksmith-to-use-secure-etcd-connection

import json, tempfile, os, sys, subprocess, pprint, shutil
from Config import Config

class CA(Config):
    etcd_config_path = '/media/state/etcd'
    serv_cert_file_path = '%s/etcd.pem' % etcd_config_path
    serv_key_file_path = '%s/etcd-key.pem' % etcd_config_path
    clnt_cert_file_path = '%s/client.pem' % etcd_config_path
    clnt_key_file_path = '%s/client-key.pem' % etcd_config_path
    ca_cert_file_path = '%s/ca.pem' % etcd_config_path

    @property
    def ca_config(self):
        if hasattr(self, '_ca_config'): return json.dumps(self._ca_config)
        self._ca_config = {
            'signing' : {
                'default' : {
                    'expiry' : '175200h',
                },
                'profiles' : {
                    'client-server' : {
                        'expiry' : '43800h',
                        'usages' : [
                            'signing',
                            'key encipherment',
                            'server auth',
                            'client auth',
                        ],
                    },
                },
            },
        }
        return json.dumps(self._ca_config, indent=4)

    def print_ca_config(self):
        pprint.pprint(json.loads(self.ca_config))

    @property
    def ca_csr(self):
        if hasattr(self, '_ca_csr'): return json.dumps(self._ca_csr)
        self._ca_csr = {
            'CN': '%s cloud bootstrap CA' % self.domain_name,
            'key': {
                'algo': 'rsa',
                'size': 4096,
            },
            'names': [
                {
                    'O': self.domain_name,
                    'OU': 'Cloud bootstrap CA'
                },
            ],
        }
        return json.dumps(self._ca_csr, indent=4)

    def print_ca_csr(self):
        pprint.pprint(json.loads(self.ca_csr))

    def mktmpdir(self):
        self._tmpdir = tempfile.mkdtemp(prefix='coreprov')

    def rmtmpdir(self):
        shutil.rmtree(self._tmpdir)

    def write_ca_config(self):
        self._ca_config_file = os.path.join(self._tmpdir, 'ca-config.json')
        with open(self._ca_config_file, 'w') as f:
            f.write(self.ca_config)
        return self._ca_config_file

    def write_ca_csr(self):
        fname = os.path.join(self._tmpdir, 'ca-csr.json')
        with open(fname, 'w') as f:
            f.write(self.ca_csr)
        return fname

    def write_ca_cert(self):
        self._ca_cert_file = os.path.join(self._tmpdir, 'ca.pem')
        with open(self._ca_cert_file, 'w') as f:
            f.write(self.ca_cert)
        return self._ca_cert_file

    def write_ca_key(self):
        self._ca_key_file = os.path.join(self._tmpdir, 'ca-key.pem')
        with open(self._ca_key_file, 'w') as f:
            f.write(self.ca_key)
        return self._ca_key_file

    def list_ca_dir(self):
        print "Contents of CA directory %s:" % self._tmpdir
        subprocess.call(['ls', '-la', self._tmpdir])

    def load_json_cert(self, data):
        rawcert = json.loads(data)
        cert = dict(
            cert = str(rawcert['cert']),
            csr = str(rawcert['csr']),
            key = str(rawcert['key']))
        return cert

    def ca_init(self):
        self._curdir = os.getcwd()
        self.mktmpdir()
        self.write_ca_config()
        os.chdir(self._tmpdir)
        if not hasattr(self, 'ca_cert'):
            ca_csr = self.write_ca_csr()
            sys.stderr.write("Initializing new CA\n")
            p = subprocess.Popen(
                ["cfssl", "gencert", "-initca", ca_csr],
                stdout=subprocess.PIPE)
            (out, err) = p.communicate()
            ca_cert = self.load_json_cert(out)
            self.ca_cert = ca_cert['cert']
            self.ca_key = ca_cert['key']
            self.pickle_config()
        self.write_ca_cert()
        self.write_ca_key()

    def get_ca_cert(self):
        if not hasattr(self, 'ca_cert'):
            try:
                self.ca_init()
            finally:
                self.ca_teardown()
        return self.ca_cert

    def get_ca_key(self):
        if not hasattr(self, 'ca_key'):
            try:
                self.ca_init()
            finally:
                self.ca_teardown()
        return self.ca_key

    def ca_teardown(self):
        os.chdir(self._curdir)
        self.rmtmpdir()

    def write_csr(self, hostname, *hosts):
        hosts = list(hosts)
        hosts.insert(0, '127.0.0.1')
        hosts.insert(0, hostname)
        csr = {
            'CN': hostname,
            'hosts': hosts,
            'key': {
                'algo': 'rsa',
                'size': 2048,
            },
            'names': [
                {
                    'O': self.domain_name,
                    'OU': 'Cloud bootstrap certs',
                },
            ],
        }
        csr_file = os.path.join(self._tmpdir, '%s-csr.pem' % hostname)
        with open(csr_file, 'w') as f:
            f.write(json.dumps(csr, indent=4))
        return csr_file

    def gen_host_cert(self, hostname, *hosts):
        if self.hosts[hostname].has_key('cert'):
            return self.hosts[hostname]['cert']
        try:
            self.ca_init()
            sys.stderr.write("Initializing new cert for host %s\n" % hostname)
            csr_file = self.write_csr(hostname, *hosts)
            # self.list_ca_dir()
            # subprocess.call(['cat', csr_file])
            p = subprocess.Popen(
                ['cfssl', 'gencert',
                 '-ca', self._ca_cert_file,
                 '-ca-key', self._ca_key_file,
                 '-config', self._ca_config_file,
                 '-profile=client-server',
                 csr_file],
                stdout=subprocess.PIPE)
            (out, err) = p.communicate()
            self.hosts[hostname]['cert'] = self.load_json_cert(out)
            self.pickle_config()
        finally:
            self.ca_teardown()
        return self.hosts[hostname]['cert']

    def install_host_certs(self, hostname):
        ip = self.to_ip(hostname)
        if not self.hosts[hostname].has_key('cert'):
            self.gen_host_cert(hostname, ip)
        print "Installing SSL certificates on %s" % hostname
        self.remote_sudo("install -d -o core %s" % self.etcd_config_path, ip)
        self.put_file(ip, self.hosts[hostname]['cert']['cert'],
                      self.serv_cert_file_path, mode=0644)
        self.put_file(ip, self.hosts[hostname]['cert']['cert'],
                      self.clnt_cert_file_path, mode=0644)
        self.put_file(ip, self.hosts[hostname]['cert']['key'],
                      self.serv_key_file_path)
        self.put_file(ip, self.hosts[hostname]['cert']['key'],
                      self.clnt_key_file_path)
        self.put_file(ip, self.ca_cert, self.ca_cert_file_path, mode=0644)
        self.remote_sudo("chown -R etcd:etcd %s" % self.etcd_config_path, ip)

