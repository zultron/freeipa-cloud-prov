from .DOCoreos import DOCoreos
#from .IPSec import ProvisionIPSec
from .DockerNetwork import DockerNetwork
from .Syslog import Syslog
from .HAProxy import HAProxy

import argparse

__all__ = ['CLIArgParser', 'CoreProvCLI']

########################################################################
# CLI Processing

class CoreProvCLI(DOCoreos, DockerNetwork, HAProxy, Syslog):
    '''
    CoreProvCLI().run()
    '''

    def __init__(self, *args, **kwargs):
        # Read command-line args
        self._args = CLIArgParser().parse_args()

        # Init from configfile
        kwargs.setdefault('configfile', self._args.configfile)
        super(CoreProvCLI, self).__init__(*args, **kwargs)

    def run(self):

        # Canonicalize host list
        hosts = [ self.canon_hostname(h) for h in self._args.hosts ] \
                if self._args.hosts else self.hosts.keys()

        if self._args.destroy_all:
            for host in hosts:
                self.destroy_droplet(host)
            for host in hosts:
                self.destroy_host_volumes(host)
            self.destroy_pickle()

        if self._args.provision_all:
            # IPA server first, replicas second
            for host in [self.freeipa_master] + self.freeipa_replicas:
                if host not in hosts:  continue

                # DigitalOcean provisioning
                self.create_data_volumes(host)
                self.create_droplet(host, wait=True)
                # Post-provisioning configuration
                self.init_data_volume(host)
                self.install_update_config(host)
                self.init_docker_network(host)
                # Bootstrap etcd2 cluster
                self.install_temp_bootstrap_config(host)
                #self.join_etcd2_cluster(host)
                # Set up network security
                self.init_iptables(host)
                self.install_known_hosts(host)
                # Provision FreeIPA service and client
                self.pull_freeipa_docker_image(host)
                self.install_freeipa_config(host)
                self.install_ipa_service(host)
                self.install_ipa_client(host)
                # Configure FreeIPA and remove bootstrap config
                self.configure_ipa_server(host)
                # Install syslog
                self.pull_syslog_docker_image(host)
                self.install_syslog_config(host)
                self.start_syslog_server()
                # Install HAProxy
                self.pull_haproxy_docker_image(host)
                self.install_haproxy_config(host)
                self.install_haproxy_certs(host)
                self.start_haproxy_server(host)


        if self._args.run:
            for host in hosts:
                self.remote_run(self._args.run, self.get_ip_addr(host))

        if self._args.docker_exec:
            for host in hosts:
                self.remote_docker_exec(host, self._args.container,
                                        self._args.docker_exec)

        if self._args.dump_config:
            self.dump_config()

        if self._args.render_jinja2:
            for host in hosts:
                self.render_jinja2_to_stdout(host, self._args.render_jinja2)

        for host in hosts:

            ##########################
            # - (De-)Provision coreos hosts
            if self._args.destroy:
                self.destroy_droplet(host)

            if self._args.show_ip_addresses:
                print "%s %s" % (self.get_ip_addr(host), host)

            if self._args.show_cloud_config:
                print self.cloud_config(host)


            ############################
            # - (De-)Provision coreos volumes and hosts
            if self._args.destroy_volumes:
                for v in self.get_data_volumes(host):
                    self.destroy_data_volume(v)

            if self._args.create_volumes:
                self.create_data_volumes(host)

            if self._args.show_volumes:
                for v in self.get_data_volumes(host):
                    print "host %s:  name %s; size %sGB; region %s; attached [%s]" % \
                        (host, v.name, v.size_gigabytes, v.region['slug'],
                         ', '.join([d.name for d in v.droplets]))

            if self._args.detach_volumes:
                self.detach_data_volumes(host)

            if self._args.provision:
                self.create_droplet(host)

            if self._args.attach_volumes:
                self.attach_data_volumes(host)

            ##########################
            # - Coreos post-provisioning configuration
            if self._args.init_volumes:
                self.init_data_volume(host)

            if self._args.install_system_env:
                self.install_system_env(host)

            if self._args.install_temp_bootstrap_config:
                self.install_temp_bootstrap_config(host)

            if self._args.install_update_config:
                self.install_update_config(host)

            if self._args.init_docker_network:
                self.init_docker_network(host)

            if self._args.init_iptables:
                self.init_iptables(host)

            if self._args.install_known_hosts:
                self.install_known_hosts(host)

            if self._args.show_iptables_config:
                print self.render_iptables_config(host)

            if self._args.show_ssh_host_keys:
                print self.get_ssh_host_keys(host)[0]

            if self._args.data_volume_status:
                self.data_volume_status(host)

            if self._args.fleet_status:
                self.check_fleet_status(host)


        #################
        # - Droplet provisioning
        if self._args.show_ssh_keys:
            for key in self.keys:
                print "%s:\n    %s" % (key.name, key.public_key)

        if self._args.show_discovery_url:
            print self.get_discovery_url()

        if self._args.reboot:
            for host in hosts:
                self.reboot(host)

        if self._args.etcd_status:
            self.check_etcd_status(host)

        #############
        # - Certificate authority commands
        if self._args.show_ca_cert:
            print self.get_ca_cert()

        if self._args.show_ca_config:
            self.print_ca_config()

        if self._args.show_ca_csr:
            self.print_ca_csr()


        for host in hosts:
            if self._args.gen_host_certs:
                cert = self.gen_host_cert(host)

            if self._args.show_host_certs:
                print self.gen_host_cert(host)['cert']

            if self._args.show_host_keys:
                print self.gen_host_cert(host)['key']

            if self._args.install_host_certs:
                self.install_host_certs(host)


        # ##############################
        # # - IPSec commands

        # IPSec in transport mode not trivially adapted to Docker
        # networking
        #

        # for host in hosts:
        #     if self._args.pull_ipsec_image or self._args.install_ipsec:
        #         self.pull_ipsec_docker_image(host)

        #     if self._args.install_ipsec_certs or self._args.install_ipsec:
        #         self.install_ipsec_certs(host)

        #     if self._args.install_ipsec_config or self._args.install_ipsec:
        #         self.install_ipsec_config(host)

        # if self._args.load_ipsec_unit or self._args.install_ipsec:
        #     self.load_ipsec_unit(host)

        # if self._args.start_ipsec or self._args.install_ipsec:
        #     self.start_ipsec(host)

        # for host in hosts:
        #     if self._args.show_ipsec_config:
        #         self.print_ipsec_config(host)



        ########################
        # - Provision IPA hosts

        for host in [self.freeipa_master] + self.freeipa_replicas:
            # IPA server first, replicas second
            if host not in hosts:  continue

            if self._args.pull_ipa_image or self._args.install_ipa:
                self.pull_freeipa_docker_image(host)

            if self._args.install_ipa_config or self._args.install_ipa:
                self.install_freeipa_config(host)

        if self._args.init_ipa or self._args.install_ipa:
            self.install_ipa_service(host)

        if self._args.install_ipa_client or self._args.install_ipa:
            self.install_ipa_client(host)

        if self._args.configure_ipa or self._args.install_ipa:
            for host in hosts:
                self.configure_ipa_server(host)

        if self._args.ipa_client_exec:
            self.ipa_client_exec(self._args.ipa_client_exec)

        if self._args.show_ipa_hosts:
            print "Server:  %s" % self.freeipa_master
            print "Replicas:  %s" % ', '.join(self.freeipa_replicas)

        ########################
        # - Provision Syslog containers

        for host in hosts:
            if self._args.pull_syslog_image or self._args.install_syslog:
                self.pull_syslog_docker_image(host)

            if self._args.install_syslog_config or self._args.install_syslog:
                self.install_syslog_config(host)

        if self._args.start_syslog or self._args.install_syslog:
            self.start_syslog_server()

        ########################
        # - Provision HAProxy containers

        for host in hosts:
            if self._args.pull_haproxy_image or self._args.install_haproxy:
                self.pull_haproxy_docker_image(host)

            if self._args.install_haproxy_config or self._args.install_haproxy:
                self.install_haproxy_config(host)

            if self._args.install_haproxy_certs or self._args.install_haproxy:
                self.install_haproxy_certs(host)

            if self._args.start_haproxy or self._args.install_haproxy:
                self.start_haproxy_server(host)

        # # Testing
        for host in hosts:
            self.ipa_fix_https_redirect(host)
        #     self.install_ca_cert(host, self.ca_cert_file_path)
        #     self.issue_cert_pem(
        #         host, self.serv_cert_file_path, self.serv_key_file_path,
        #         host, "ETCD")
        #     self.issue_cert_pem(
        #         host, self.clnt_cert_file_path, self.clnt_key_file_path,
        #         host, "ETCD")

########################################################################
# CLI argument parsing

class CLIArgParser(argparse.ArgumentParser):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            'description', 'Provision FreeIPA on CoreOS on DigitalOcean')
        super(CLIArgParser, self).__init__(*args, **kwargs)


    def parse_args(self, *args, **kwargs):

        self.add_argument(
            '--configfile', action='store',
            metavar="FILE",
            default="config.yaml",
            help='YAML-format configuration file ("config.yaml")')

        self.add_argument(
            '--dump-config', action='store_true',
            help='Print configuration')

        self.add_argument(
            '--provision-all', action='store_true',
            help='Provision all hosts with single command')

        self.add_argument(
            '--destroy-all', action='store_true',
            help='Destroy all hosts and volumes with single command  '
            '***DESTRUCTIVE***')

        self.add_argument(
            '--run', action='store', metavar='COMMAND',
            help='Run command on remote hosts')

        self.add_argument(
            '--container', action='store', metavar='CONTAINER_NAME',
            help='Specify container to use for --docker-exec command')

        self.add_argument(
            '--docker-exec', action='store', metavar='COMMAND',
            help='Run command in remote container specified by --container')

        self.add_argument(
            '--reboot', action='store_true',
            help='Reboot host')

        self.add_argument(
            'hosts', metavar='HOST', nargs='*',
            help='Hostnames to act on (all)')

        self.add_argument(
            '--render-jinja2', metavar='FILENAME',
            help='render a jinja2 file from the "coreprov/templates" directory')

        # - Provision coreos hosts
        droplet_group = self.add_argument_group(
            "Droplet (host) provisioning")
        droplet_group.add_argument(
            '--provision', action='store_true',
            help='Provision droplets')
        droplet_group.add_argument(
            '--destroy', action='store_true',
            help='Destroy droplets  ***DESTRUCTIVE***')
        droplet_group.add_argument(
            '--show-ip-addresses', action='store_true',
            help='Print droplet IP addresses')
        droplet_group.add_argument(
            '--show-cloud-config', action='store_true',
            help='Print droplet cloud config')
        droplet_group.add_argument(
            '--show-discovery-url', action='store_true',
            help='Print etcd discovery URL')
        droplet_group.add_argument(
            '--show-ssh-keys', action='store_true',
            help='Print SSH keys')

        # - Provision coreos volumes
        volume_group = self.add_argument_group(
            "Droplet data volume provisioning")
        volume_group.add_argument(
            '--create-volumes', action='store_true',
            help='Create droplet data volumes')
        volume_group.add_argument(
            '--destroy-volumes', action='store_true',
            help='Destroy droplet data volumes ***DESTRUCTIVE***')
        volume_group.add_argument(
            '--attach-volumes', action='store_true',
            help='Attach droplet data volumes')
        volume_group.add_argument(
            '--detach-volumes', action='store_true',
            help='Detach droplet data volumes')
        volume_group.add_argument(
            '--show-volumes', action='store_true',
            help='Print droplet data volumes')


        # - Coreos post-provisioning configuration
        post_group = self.add_argument_group(
            "Post-provisioning host configuration")
        post_group.add_argument(
            '--init-volumes', action='store_true',
            help='Initialize volumes with swap and data partitions')
        post_group.add_argument(
            '--install-system-env', action='store_true',
            help='Install system environment file')
        post_group.add_argument(
            '--install-temp-bootstrap-config', action='store_true',
            help='Install temporary configuration needed during bootstrap')
        post_group.add_argument(
            '--install-update-config', action='store_true',
            help='Install configuration updates on host')
        post_group.add_argument(
            '--init-docker-network', action='store_true',
            help='Initialize Docker container network')
        post_group.add_argument(
            '--init-iptables', action='store_true',
            help='Initialize iptables rules')
        post_group.add_argument(
            '--install-known-hosts', action='store_true',
            help='Install ~core/.fleetctl/known_hosts')
        post_group.add_argument(
            '--data-volume-status', action='store_true',
            help='Show data volume swap and storage status')
        post_group.add_argument(
            '--show-iptables-config', action='store_true',
            help='Print iptables-restore file')
        post_group.add_argument(
            '--show-ssh-host-keys', action='store_true',
            help='Print SSH known host keys')
        post_group.add_argument(
            '--etcd-status', action='store_true',
            help='Show fleet status')
        post_group.add_argument(
            '--fleet-status', action='store_true',
            help='Show fleet status')

        # - Certificate authority commands
        ca_group = self.add_argument_group(
            "Bootstrap certificate authority")
        ca_group.add_argument(
            '--show-ca-cert', action='store_true',
            help='Print CA certificate')
        ca_group.add_argument(
            '--show-ca-config', action='store_true',
            help='Print CA configuration')
        ca_group.add_argument(
            '--show-ca-csr', action='store_true',
            help='Print CA CSR')
        ca_group.add_argument(
            '--gen-host-certs', action='store_true',
            help='Generate host certificates')
        ca_group.add_argument(
            '--show-host-certs', action='store_true',
            help='Print host certificates')
        ca_group.add_argument(
            '--show-host-keys', action='store_true',
            help='Print host keys ***INSECURE***')
        ca_group.add_argument(
            '--install-host-certs', action='store_true',
            help='Install host certificates (generate if needed)')

        # # - IPSec commands
        # ipsec_group = self.add_argument_group(
        #     "IPSec configuration")
        # ipsec_group.add_argument(
        #     '--install-ipsec', action='store_true',
        #     help='Install and start IPSec in one command')
        # ipsec_group.add_argument(
        #     '--pull-ipsec-image', action='store_true',
        #     help='Pull IPSec Docker image')
        # ipsec_group.add_argument(
        #     '--install-ipsec-certs', action='store_true',
        #     help='Install IPSec certificates (same as host certs)')
        # ipsec_group.add_argument(
        #     '--install-ipsec-config', action='store_true',
        #     help='Install IPSec configuration files')
        # ipsec_group.add_argument(
        #     '--load-ipsec-unit', action='store_true',
        #     help='Load IPSec fleetctl unit file')
        # ipsec_group.add_argument(
        #     '--start-ipsec', action='store_true',
        #     help='Start IPSec fleetctl unit')
        # ipsec_group.add_argument(
        #     '--show-ipsec-config', action='store_true',
        #     help='Print IPSec configuration files')

        # - FreeIPA commands
        freeipa_group = self.add_argument_group(
            "FreeIPA configuration")
        freeipa_group.add_argument(
            '--install-ipa', action='store_true',
            help='Install FreeIPA servers and/or replicas in one command')
        freeipa_group.add_argument(
            '--pull-ipa-image', action='store_true',
            help='Pull FreeIPA Docker image')
        freeipa_group.add_argument(
            '--install-ipa-config', action='store_true',
            help='Install FreeIPA configuration files')
        freeipa_group.add_argument(
            '--init-ipa', action='store_true',
            help='Run "ipa-{server,replica}-install" on FreeIPA server/replica')
        freeipa_group.add_argument(
            '--install-ipa-client', action='store_true',
            help='Install IPA client container on FreeIPA server/replica')
        freeipa_group.add_argument(
            '--configure-ipa', action='store_true',
            help='Set up DNS, LDAP and SSL')
        freeipa_group.add_argument(
            '--ipa-client-exec', action='store', metavar='COMMAND',
            help='Run command in IPA client container')
        freeipa_group.add_argument(
            '--show-ipa-hosts', action='store_true',
            help='Print FreeIPA server and replicas')

        # - Syslog commands
        syslog_group = self.add_argument_group(
            "syslog configuration")
        syslog_group.add_argument(
            '--install-syslog', action='store_true',
            help='Install syslog servers in one command')
        syslog_group.add_argument(
            '--pull-syslog-image', action='store_true',
            help='Pull syslog Docker image')
        syslog_group.add_argument(
            '--install-syslog-config', action='store_true',
            help='Install syslog configuration files')
        syslog_group.add_argument(
            '--start-syslog', action='store_true',
            help='Start syslog containers')

        # - HAProxy commands
        haproxy_group = self.add_argument_group(
            "HAProxy configuration")
        haproxy_group.add_argument(
            '--install-haproxy', action='store_true',
            help='Install HAProxy servers in one command')
        haproxy_group.add_argument(
            '--pull-haproxy-image', action='store_true',
            help='Pull HAProxy Docker image')
        haproxy_group.add_argument(
            '--install-haproxy-config', action='store_true',
            help='Install HAProxy configuration files')
        haproxy_group.add_argument(
            '--install-haproxy-certs', action='store_true',
            help='Install HAProxy SSL certificates')
        haproxy_group.add_argument(
            '--start-haproxy', action='store_true',
            help='Start HAProxy containers')

        return super(CLIArgParser, self).parse_args(*args, **kwargs)

