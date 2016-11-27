import yaml, pprint, os, sys


class Config(object):
    pickle_fname = 'state.yaml'
    state_dir = '/media/state'

    def __init__(self, configfile='config.yaml'):
        self.configfile = os.path.abspath(configfile)
        self.config_dir = os.path.dirname(self.configfile)
        self.template_dir = os.path.join(self.config_dir, 'templates')
        self.update_config(self.configfile)
        if os.path.exists(self.pickle_file_path):
            self.update_config(self.pickle_file_path)

    @property
    def sanitized_config(self):
        config = self.__dict__.copy()
        for key in self.__dict__:
            if key.startswith('_'):
                del(config[key])
        return config

    def dump_config(self):
        pprint.pprint(self.sanitized_config)

    def short_hostname(self, hostname):
        return hostname.split('.')[0]

    def canon_hostname(self, name):
        for h in self.hosts:
            if name == h:  return h
            if name == self.short_hostname(h):  return h

    def update_config(self, fname):
        self.__dict__.update(yaml.load(file(fname, 'r')))

    def config_file_path(self, fname):
        return os.path.join(self.config_dir, fname)

    def template_file_path(self, fname):
        return os.path.join(self.template_dir, fname)

    @property
    def pickle_file_path(self):
        return self.config_file_path(self.pickle_fname)

    def pickle_config(self):
        with open(self.pickle_file_path, 'w') as f:
            f.write(yaml.dump(self.sanitized_config, default_flow_style=False))

    @classmethod
    def state_subdir(cls, subdir_name):
        return os.path.join(cls.state_dir, subdir_name)

    def hconfig(self, host, key=None, val=None):
        if key is None:
            return self.hosts[host]
        elif val is None:
            return self.hosts[host][key]
        else:
            self.hosts[host][key] = val

    def to_ip(self, host, bomb=True):
        ip = self.hosts[host].get('ip_address', None)
        if bomb and ip is None:
            raise RuntimeError("No cached IP address for host %s" % host)
        return ip

    def other_hosts(self, host):
        return [ h for h in self.hosts if h != host ]

    def other_ips(self, host, bomb=True):
        return [ self.to_ip(h, bomb=bomb) for h in self.other_hosts(host)
                 if self.to_ip(h, bomb=bomb) is not None ]

    def substitutions(self, host, extra_substitutions={}):
        subs = self.__dict__.copy()
        subs.update(self.hosts[host])
        subs.update(extra_substitutions)
        subs['hostname'] = host
        subs['num_hosts'] = len(self.hosts)
        subs['other_ips'] = ','.join(self.other_ips(host, bomb=False))
        # print "substitutions for %s:" % host
        # pprint(subs)
        return subs

    def render_file(self, host, fname, extra_substitutions={}):
        subs = self.substitutions(host, extra_substitutions)
        in_path = self.template_file_path(fname)
        res = ''
        with open(in_path, 'r') as inf:
            for line in inf:
                res += line.format(**subs)
        return res

    def render_file_to_stdout(self, *args, **kwargs):
        # sys.stdout.write(self.render_file(*args, **kwargs))
        print(self.render_file(*args, **kwargs))

    def destroy_pickle(self):
        if not os.path.exists(self.pickle_file_path):
            print "No state file %s to remove" % self.pickle_file_path
        else:
            print "Removing state file %s" % self.pickle_file_path
            os.remove(self.pickle_file_path)
