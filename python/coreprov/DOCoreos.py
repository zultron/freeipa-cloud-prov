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
# import logging
# logging.captureWarnings(RemoteControl)

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

    @property
    def ssh_keys(self):
        if not hasattr(self, '_ssh_keys'):
            keylist = self.manager.get_all_sshkeys()
            self._ssh_keys = [k for k in self.manager.get_all_sshkeys() \
                              if k.name in self.keys]
        return self._ssh_keys

    def cloud_config(self, host):
        # YAML-format `ssh_authorized_keys` cloud-config key
        keys = yaml.dump(
            dict(ssh_authorized_keys=[
                str(k.public_key) for k in self.ssh_keys ]),
            default_flow_style=False)
        # cloud-config etcd2 `initial-cluster` values
        initial_cluster = ','.join(
            ['%s=http://127.0.0.1:2380' % host] +
            ['%s=https://%s:2380' % (h, h) for h in self.hosts])
        initial_cluster_state = (
            "new" if self.hosts[host].get('bootstrap_order', 1) == 0 \
            else "existing")
        return self.render_jinja2(
            host, 'cloud-config.yaml',
            ssh_authorized_keys = keys,
            serv_cert_file_path = self.serv_cert_file_path,
            serv_key_file_path = self.serv_key_file_path,
            clnt_cert_file_path = self.clnt_cert_file_path,
            clnt_key_file_path = self.clnt_key_file_path,
            ca_cert_file_path = self.ca_cert_file_path,
            initial_cluster = initial_cluster,
            initial_cluster_state = initial_cluster_state,
            initial_cluster_token = self.realm,
            )

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

    def get_ip_addr(self, host):
        d = self.get_droplet(host, raise_error=False)
        if d is None:  return None
        a = self.hosts[host].get('ip_address', d.ip_address)
        self.pickle_config()
        return a

    @property
    def initial_host(self):
        return [ h for h in self.hosts \
                 if self.hosts[h].get('bootstrap_order',1) == 0 ][0]

    def substitutions(self, host, **kwargs):
        # Add extra metadata
        fleet_metadata = "region=%s" % self.hosts[host]['region']
        fleet_metadata += ',ipa=true'
        fleet_metadata += ',host_id=%s' % self.hosts[host]['host_id']

        replica_names = [n for n in self.hosts \
                         if n != self.initial_host ]
        replica_ips = [self.get_ip_addr(n) for n in self.hosts \
                         if n != self.initial_host ]

        subs = super(DOCoreos, self).substitutions(
            host,
            fleet_metadata=fleet_metadata,
            replica_names=replica_names,
            replica_ips=replica_ips,
            **kwargs)
        return subs

    def dropin_path(self, service, fname=""):
        return "/etc/systemd/system/%s.service.d/%s" % (service, fname)
    
    etcd2_bootstrap_conf_fname = "40-etcd2-bootstrap.conf"
    def install_bootstrap_etcd_dropin(self, host):
        print "Installing temporary bootstrap etcd dropin on %s" % host
        self.remote_sudo(
            "install -d -o core %s" % self.dropin_path('etcd2'), host)
        self.put_file(
            host, self.render_jinja2(host, self.etcd2_bootstrap_conf_fname),
            self.dropin_path('etcd2', self.etcd2_bootstrap_conf_fname))
        self.remote_sudo("systemctl daemon-reload", host)
        self.remote_sudo("systemctl restart etcd2", host)

    def remove_bootstrap_etcd_dropin(self, host):
        print "Removing temporary bootstrap etcd dropin on %s" % host
        self.remote_sudo(
            "rm -f %s" % self.dropin_path(
                'etcd2', self.etcd2_bootstrap_conf_fname), host)
        self.remote_sudo("systemctl daemon-reload", host)
        self.remote_sudo("systemctl restart etcd2", host)
    
    fleet_bootstrap_conf_fname = "40-fleet-bootstrap.conf"
    def install_bootstrap_fleet_dropin(self, host):
        print "Installing temporary bootstrap fleet dropin on %s" % host
        self.remote_sudo(
            "install -d -o core %s" % self.dropin_path('fleet'), host)
        self.put_file(
            host, self.render_jinja2(host, self.fleet_bootstrap_conf_fname),
            self.dropin_path('fleet', self.fleet_bootstrap_conf_fname))
        self.remote_sudo("systemctl daemon-reload", host)
        self.remote_sudo("systemctl restart fleet", host)

    def remove_bootstrap_fleet_dropin(self, host):
        print "Removing temporary bootstrap fleet dropin on %s" % host
        self.remote_sudo(
            "rm -f %s" % self.dropin_path(
                'fleet', self.fleet_bootstrap_conf_fname), host)
        self.remote_sudo("systemctl daemon-reload", host)
        self.remote_sudo("systemctl restart fleet", host)

    def install_temp_bootstrap_config(self, host):
        if self.hosts[host].get('bootstrap_order', None) != 0:
            print "Not installing bootstrap config on %s:  " \
                "cluster exists" % host
            return
        self.install_bootstrap_etcd_dropin(host)
        self.install_bootstrap_fleet_dropin(host)
        self.bootstrapping = True
        self.pickle_config()

    def remove_temp_bootstrap_config(self, host):
        self.remove_bootstrap_etcd_dropin(host)
        self.remove_bootstrap_fleet_dropin(host)
        self.bootstrapping = False
        self.pickle_config()

    def install_update_config(self, host):
        print "Installing configuration updates on %s" % host
        self.remote_sudo("install -d -o core /media/state/configs", host)
        self.render_and_put(
            host, 'update-config', '/media/state/configs/update-config',
            mode=0755)
        self.render_and_put(
            host, 'resolv.conf', '/media/state/configs/resolv.conf')
        self.render_and_put(
            host, 'hosts', '/media/state/configs/hosts')
        self.remote_sudo("systemctl restart update-config", host)

    def check_fleet_status(self, host):
        out = self.remote_run_output('fleetctl list-machines', host)
        if len(out) == 0:
            raise RuntimeError("Fleet status not OK")
        else:
            print "Fleet status OK"

    def check_etcd_status(self, host):
        # etcdctl and SSL are ugly
        # https://www.digitalocean.com/community/tutorials/how-to-secure-your-coreos-cluster-with-tls-ssl-and-firewall-rules
        ssl_opts="" if getattr(self, 'bootstrapping', False) else \
            "--cert-file=%s --key-file=%s --ca-file=%s" % (
                self.clnt_cert_file_path, self.clnt_key_file_path,
                self.ca_cert_file_path)
        out = self.remote_run(
            'etcdctl %s cluster-health' % ssl_opts, host)

    def init_data_volume(self, host):
        print "Initializing data volume for %s" % host
        vols = self.get_data_volumes(host)
        # Sanity checks
        if not vols or vols[0].name != self.volume_name(host):
            raise RuntimeError("Cannot init swap on host with no data volume")
        # Init volume label
        self.remote_sudo('parted /dev/sda mklabel msdos', host)
        # Create and format swap partition, and start service
        swap_end = self.hosts[host]['swap_size'] * 1024 * 1024 * 2
        self.remote_sudo('parted -a min /dev/sda ' \
                         'mkpart primary linux-swap 1s %ds' % swap_end,
                         host)
        self.remote_sudo('mkswap /dev/sda1', host)
        self.remote_sudo('systemctl start dev-sda1.swap', host)
        # Create and format data partition, and start service
        data_end = self.hosts[host]['volume_size'] * 1024 * 1024 * 2 - 1
        self.remote_sudo('parted -a min /dev/sda ' \
                         'mkpart primary ext4 %ds %ds' % (swap_end+1, data_end),
                         host)
        self.remote_sudo('mkfs.ext4 /dev/sda2', host)
        self.remote_sudo('systemctl start media-state.mount', host)
        self.remote_sudo('install -d -o core %s' % self.state_dir, host)
        self.install_system_env(host)

    def data_volume_status(self, host):
        vols = self.get_data_volumes(host)
        out = self.remote_run_output("swapon -s | awk '/^.dev/ {print $3}'", host)
        if len(out) == 1:
            print("Swap OK; size = %s" % out[0].rstrip())
        else:
            print("No swap found")
        out = self.remote_run_output('mount | grep %s' % self.state_dir, host)
        if len(out) == 1:
            print("Data OK")
        else:
            print("Data partition not mounted")


    def install_system_env(self, host):
        print "Installing system environment file on %s" % host
        self.render_and_put(host, 'system.env',
                            os.path.join(self.state_dir, 'system.env'))
