# Provision DigitalOcean hosts from config
#
# Requires digitalocean module from
# https://github.com/koalalorenzo/python-digitalocean
#
# API docs
# https://developers.digitalocean.com/documentation/v2/

import os, sys, re, time, urllib3, StringIO, yaml
from pprint import pprint
import digitalocean
from .RemoteControl import RemoteControl
from .CA import CA

# https://urllib3.readthedocs.io/en/latest/advanced-usage.html#ssl-warnings
# import urllib3
# urllib3.disable_warnings()
import logging
logging.captureWarnings(RemoteControl)

class DOCoreos(RemoteControl, CA):
    etcd_config_path = RemoteControl.state_subdir('etcd')
    serv_cert_file_path = '%s/etcd.pem' % etcd_config_path
    serv_key_file_path = '%s/etcd-key.pem' % etcd_config_path
    clnt_cert_file_path = '%s/client.pem' % etcd_config_path
    clnt_key_file_path = '%s/client-key.pem' % etcd_config_path
    ca_cert_file_path = '%s/ca.pem' % etcd_config_path

    @property
    def manager(self):
        if not hasattr(self, '_manager'):
            self._manager = digitalocean.Manager(token=self.token)
        return self._manager


    def get_discovery_url(self):
        if hasattr(self, 'discovery_url'):
            return self.discovery_url

        http = urllib3.PoolManager()
        r = http.request('GET',
                         'https://discovery.etcd.io/new?size=%s' % \
                         len(self.hosts))
        self.discovery_url = r.data
        self.pickle_config()
        return self.discovery_url

    @property
    def ssh_keys(self):
        if not hasattr(self, '_ssh_keys'):
            keylist = self.manager.get_all_sshkeys()
            self._ssh_keys = [k for k in self.manager.get_all_sshkeys() \
                              if k.name in self.keys]
        return self._ssh_keys

    def cloud_config(self, hostname):
        self.get_discovery_url()
        rawfile = self.render_file(hostname, 'cloud-config.yaml')
        conf = yaml.load(rawfile)
        conf['ssh_authorized_keys'] = [ str(k.public_key) \
                                        for k in self.ssh_keys ]
        # pprint(conf)
        return '#cloud-config\n' + yaml.dump(conf, default_flow_style=False)

    def get_droplet(self, name, raise_error=False):
        droplet = None
        for d in self.manager.get_all_droplets():
            if d.name in self.hosts:
                # Grab IP address while we have it
                self.hosts[d.name]['ip_address'] = str(d.ip_address)
            if d.name == name:
                droplet = d
        if droplet is None and raise_error:
            raise RuntimeError("No droplet named %s" % name)
        return droplet

    def volume_name(self, hostname):
        return self.short_hostname(hostname) + '-data'

    def get_data_volumes(self, hostname):
        name = self.volume_name(hostname)
        vols = [v for v in self.manager.get_all_volumes() if v.name == name]
        for v in vols:
            v.droplets = [self.get_droplet_by_id(id) \
                          for id in v.droplet_ids]
        return vols

    def create_data_volumes(self, hostname):
        if self.get_data_volumes(hostname):
            raise RuntimeError("Volumes already provisioned for host %s" % \
                               hostname)
        name = self.volume_name(hostname)
        size = self.hosts[hostname]['volume_size']
        region = self.hosts[hostname]['region']
        print "Creating %sGB data volume %s for host %s (region %s)" % \
            (size, name, hostname, region)
        v = digitalocean.Volume(
            token = self.token,
            size_gigabytes = size,
            name = name,
            region = region,
            )
        v.create()
        time.sleep(5)
        return v

    def to_droplet(self, hostname_or_droplet):
        if type(hostname_or_droplet) == str:
            return self.get_droplet(hostname_or_droplet)
        else:
            return hostname_or_droplet

    def attach_data_volumes(self, hostname_or_droplet):
        droplet = self.to_droplet(hostname_or_droplet)
        volumes = self.get_data_volumes(droplet.name)
        if not volumes:
            raise RuntimeError("No volumes exist for host %s" % droplet.name)
        for volume in volumes:
            print "Attaching volume %s to droplet %s (region %s)" % \
                (volume.name, droplet.name, volume.region['slug'])
            res = volume.attach(droplet_id = droplet.id,
                                region = volume.region['slug'])
        time.sleep(5) # FIXME ugh

    def detach_data_volumes(self, hostname):
        droplet = self.get_droplet(hostname, raise_error=True)
        for v in self.get_data_volumes(droplet.name):
            if droplet.id in v.droplet_ids:
                print "Detaching volume %s from droplet %s in region %s" % \
                    (v.name, droplet.name, v.region['slug'])
                v.detach(droplet_id=droplet.id, region=droplet.region['slug'])
        time.sleep(5) # FIXME ugh


    def get_droplet_by_id(self, id):
        return self.manager.get_droplet(id)

    def create_droplet(self, name, wait=False):
        # Check volumes exist
        volumes = self.get_data_volumes(name)
        if not volumes:
            raise RuntimeError("No volumes exist for host %s" % name)

        dconf = self.hosts[name]
        print "Creating droplet %s (region %s)" % (name, dconf['region'])
        droplet = digitalocean.Droplet(
            token = self.token,
            name = name,
            region = dconf['region'],
            size_slug = dconf['size'],
            image = dconf['image'],
            ssh_keys = self.ssh_keys,
            backups = False,
            ipv6 = False,
            private_networking = False,
            user_data = self.cloud_config(name),
        )
        droplet.create()
        done = False
        while not done:
            actions = droplet.get_actions()
            for action in actions:
                # can we use action.wait()?
                action.load()
                # Once it shows complete, droplet is up and running
                print "    ...%s" % action.status
                done = action.status == "completed"

        self.attach_data_volumes(droplet)
        print "Host %s ip address %s" % \
            (name, self.get_ip_addr(name)) # Side-effect:  cache IP
        # print "Waiting 60 seconds for host to start up"
        # time.sleep(60)

    def destroy_data_volume(self, volume):
        if volume.droplets:
            raise RuntimeError("Cannot destroy volume %s attached to %s" % \
                               (volume.name, ', '.join(
                                   [d.name for d in volume.droplets])))
        print "Destroying volume %s in region %s" % \
            (volume.name, volume.region['slug'])
        volume.destroy()

    def destroy_host_volumes(self, host):
        volumes = self.get_data_volumes(host)
        if not volumes:
            print "No volumes to destroy for host %s" % host
        for volume in volumes:
            self.destroy_data_volume(volume)

    def destroy_droplet(self, name):
        droplet = self.get_droplet(name, raise_error=False)
        if droplet is None:
            print "No droplet %s to destroy" % name
            return

        print "Destroying droplet %s" % droplet.name
        res = droplet.destroy()
        del self.hosts[name]['ip_address']
        self.pickle_config()

        actions = droplet.get_actions()
        for action in actions:
            action.load()
            # Once it shows complete, droplet is up and running
            print "    ...%s" % action.status

    def create_all_droplets(self):
        self.get_discovery_url()
        for host in self.hosts:
            self.create_droplet(host)

    def destroy_all_droplets(self):
        for host in self.hosts:
            try:
                self.destroy_droplet(host)
            except:
                print "Failed to destroy droplet %s" % host

    def get_ip_addr(self, host):
        d = self.get_droplet(host, raise_error=False)
        return None if d is None else \
            self.hosts[host].get('ip_address', d.ip_address)

    def substitutions(self, host, extra_substitutions={}):
        # Add extra metadata
        fleet_metadata = "region=%s" % self.hosts[host]['region']
        if self.hosts[host].get('ipa_role') == "server":
            fleet_metadata += ',ipa=true,ipa_role=server'
        if self.hosts[host].get('ipa_role') == "replica":
            fleet_metadata += ',ipa=true,ipa_role=replica'

        replica_names = [n for n in self.hosts \
                         if self.hosts[n]['ipa_role'] == 'replica' ]
        replica_ips = [self.get_ip_addr(n) for n in self.hosts \
                         if self.hosts[n]['ipa_role'] == 'replica' ]

        subs = super(DOCoreos, self).substitutions(
            host, extra_substitutions=dict(
                fleet_metadata=fleet_metadata,
                replica_names=replica_names,
                replica_ips=replica_ips,
            ))
        subs.update(extra_substitutions)
        return subs

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

    def render_host_config(self, host):
        fnames = ["init.sh"]
        if self.hosts[host].get('ipa_role') == "server":
            fnames += ["ipa-replica@.service",
                       "ipa-server-install-options",
                       "ipa-server.service"]
        if self.hosts[host].get('ipa_role') == "replica":
            fnames += ["ipa-replica-install-options"]
        for fname in fnames:
            self.render_file(host, fname)
                

    def check_fleet_status(self, host):
        ip = self.get_ip_addr(host)
        out = self.remote_run_output('fleetctl list-machines', ip)
        if len(out) == 0:
            raise RuntimeError("Fleet status not OK")
        else:
            print "Fleet status OK"

    def check_etcd_status(self, host):
        ip = self.get_ip_addr(host)
        # etcdctl and SSL are ugly
        # https://www.digitalocean.com/community/tutorials/how-to-secure-your-coreos-cluster-with-tls-ssl-and-firewall-rules
        out = self.remote_run(
            'etcdctl --endpoint="https://127.0.0.1:2379/" '
            '--cert-file=%s --key-file=%s --ca-file=%s cluster-health' %
            (self.clnt_cert_file_path, self.clnt_key_file_path,
             self.ca_cert_file_path), ip)

    def init_data_volume(self, host):
        print "Initializing data volume for %s" % host
        ip = self.get_ip_addr(host)
        vols = self.get_data_volumes(host)
        # Sanity checks
        if not vols or vols[0].name != self.volume_name(host):
            raise RuntimeError("Cannot init swap on host with no data volume")
        # Init volume label
        self.remote_sudo('parted /dev/sda mklabel msdos', ip)
        # Create and format swap partition, and start service
        swap_end = self.hosts[host]['swap_size'] * 1024 * 1024 * 2
        self.remote_sudo('parted -a min /dev/sda ' \
                         'mkpart primary linux-swap 1s %ds' % swap_end,
                         ip)
        self.remote_sudo('mkswap /dev/sda1', ip)
        self.remote_sudo('systemctl start dev-sda1.swap', ip)
        # Create and format data partition, and start service
        data_end = self.hosts[host]['volume_size'] * 1024 * 1024 * 2 - 1
        self.remote_sudo('parted -a min /dev/sda ' \
                         'mkpart primary ext4 %ds %ds' % (swap_end+1, data_end),
                         ip)
        self.remote_sudo('mkfs.ext4 /dev/sda2', ip)
        self.remote_sudo('systemctl start media-state.mount', ip)

    def data_volume_status(self, host):
        ip = self.get_ip_addr(host)
        vols = self.get_data_volumes(host)
        out = self.remote_run_output("swapon -s | awk '/^.dev/ {print $3}'", ip)
        if len(out) == 1:
            print("Swap OK; size = %s" % out[0].rstrip())
        else:
            print("No swap found")
        out = self.remote_run_output('mount | grep %s' % self.state_dir, ip)
        if len(out) == 1:
            print("Data OK")
        else:
            print("Data partition not mounted")

    def render_iptables_config(self, host):
        return self.render_file(host, 'iptables-rules-save')

    def init_iptables(self, host):
        ip = self.get_ip_addr(host)
        print "Copying firewall rules to %s:/var/lib/iptables/rules-save" % host
        self.put_file(
            ip, self.render_iptables_config(host), 'iptables-rules-save')
        self.remote_sudo(
            'mv iptables-rules-save /var/lib/iptables/rules-save', ip)
        self.remote_sudo(
            'systemctl restart iptables-restore.service', ip)
