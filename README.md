# FreeIPA in Docker on CoreOS on DigitalOcean

FreeIPA integrates LDAP, Kerberos, DNS and SSL CA services and exposes
graphical and text user interfaces for centralized management.  These
services can form a base around which to build highly scalable,
distributed, heterogeneous system infrastructures.  More and more,
large portions of system infrastructure reside on cloud computing
platforms.

FreeIPA can be a challenge to set up and run in any environment.  The
python scripts in this repository automate the process of provisioning
and configuring a CoreOS cluster on DigitalOcean, and bringing up a
FreeIPA server and replicas in Docker containers.

This is experimental work, and there are known, unresolved security
issues in the result.  **Readers should be aware of risks using this
work.**


## Usage

The `provision` script handles building a Docker container with the
needed tools, and running the Python utilities within it.

	./provision build  # build the Docker container
	./provision -h     # run the utility

To provision a new cluster, copy `config.yaml.example` to
`config.yaml` and edit it.  Then, on a good day, the following command
will provision and configure the CoreOS cluster and install and
configure FreeIPA:

    ./provision --provision-all


## Bootstrapping

### Plan and theory

- The initial IPA server node will be bootstrapped from start to finish
  before bootstrapping replicas
- The `cloud-config` file represents final configuration (except for
  `initial-cluster` static configuration params)
  - DO runs `cloud-config` at each boot, so direct changes not allowed
  - CoreOS update untested, so any changes will be in the persistent
    data volume so that the OS stays stateless and can be wiped
- `etcd2` configuration
  - Manual provisioning
	- Use DNS names:  IPA won't issue certs with IP addresses in
      `subjectAltName`
	- Initial URL resolution via `/etc/hosts`
	  - Initial IP addresses can't be known in advance; use systemd service to
		copy files from `/media/state` at boot
  - SSL on external interfaces
	- Initial bootstrap host needs temporary drop-in during bootstrap
	  to disable SSL until FreeIPA is running and integrated
	- Certs are generated with certmonger within an IPA client
      container, simplifying generation and automating updates, and
      good for all SSL services
	- Replicas are completely configured with SSL certs before running
      `etcdctl member add`
  - Iptables restricts `etcd2` communication to nodes only
- FreeIPA installation
  - Initial server bootstrap and replica bootstrap + replication
  - DNS zones set up for each location and container records added for
    record-keeping purposes
  - Host principals only set up for host (to generate certs with
    correct CN) and IPA client (to manage cert generation)
  - Hardened according to recommendations on FreeIPA wiki
	- No public DNS recursion
	- No DNS AXFR
	- No LDAP anonymous bind
	- Only HTTPS, no HTTP
  - IPA client container used to run IPA commands, generate certs, and
    run certmonger to monitor SSL cert expiration
- Other configuration
  - Systemd service copies files like `/etc/hosts` from data volume to
    system at boot time
  - Iptables and other config stored in data volume
- Bring up syslog container
- Bring up HAProxy container
  - HAProxy sidekick service installs/uninstalls IPTables rules to
    redirect port 80/443 traffic
- Repeat process for replicas

### Flow
For each FreeIPA server (first) and replicas (later):
- Set up server data in config.yaml
- `./provision --provision-all` does all the following in one command:
- CoreOS cluster provisioning
  - Provision droplet and volume
	- `./provision --create-volumes --provision`
  - Initialize data and swap volume, and install `system.env`
    configuration file
	- `./provision --init-volumes`
  - Install /etc/hosts, etc.
	- `./provision --install-update-config`
  - Install docker network
	- `./provision --init-docker-network`
  - On other hosts: install iptables, known-hosts;
	- `./provision --init-iptables --install-known-hosts --install-update-config`
  - Install config needed to bootstrap initial member or add later
    members
	- `./provision --early-bootstrap`
- FreeIPA provisioning
  - Install FreeIPA server/replica
	- `./provision --pull-ipa-image --install-ipa-config --init-ipa`
  - Install FreeIPA client
	- `./provision --install-ipa-client`
  - Configure IPA security and DNS; issue etcd2 certs for cluster;
	remove temp. bootstrap config
	- `./provision --configure-ipa`
- Other services
  - Set up syslog service
	- `./provision --install-syslog`
  - Set up haproxy service
	- `./provision --install-haproxy`


## Documentation used to develop this system

- [DigitalOcean][digitalocean]:
  - [DigitalOcean API][do-api]
  - [Python DigitalOcean API][py-do]

[digitalocean]: https://cloud.digitalocean.com/
[do-api]: https://developers.digitalocean.com/documentation/v2/
[py-do]: https://github.com/koalalorenzo/python-digitalocean

- [Paramiko][paramiko] Python SSH client

[paramiko]: http://docs.paramiko.org/en/2.0/index.html

- [`jinja2` documentation][jinja2-docs]

[jinja2-docs]: http://jinja.pocoo.org/docs/dev/

- [CoreOS][coreos]:
  - Basic configuration:
	- [Running CoreOS on DigitalOcean tutorial][coreos-do]
	- [CoreOS `cloud-config`][cloud-config] and
	  [validator][coreos-cloud-config-validate]
	- [`etcd2` options][etcd2-options]
	- [CoreOS clustering][coreos-clustering]:  "static" section
	- [CoreOS cluster reconfiguration][coreos-cluster-reconfig]
  - SSL on CoreOS:
	- [SSL Certificate Authority][coreos-ca]
    - [`etcd2` SSL][coreos-etcd-ssl]
    - [CoreOS client ssl][coreos-clients-ssl]
	- [CoreOS SSL and iptables on DigitalOcean][do-coreos-ssl]
      (somewhat outdated)
	- [`cfssl` CA utility][cfssl]
  - Launching containers in CoreOS:
	- [Launching containers with fleet][fleet]
	- [Unit files][unit-files]
  - IPA integration
	- [CoreOS SSSD integration][coreos-sssd]
  

[coreos]: https://coreos.com/
[coreos-do]: https://www.digitalocean.com/community/tutorials/how-to-set-up-a-coreos-cluster-on-digitalocean
[cloud-config]: https://coreos.com/os/docs/latest/cloud-config.html
[coreos-cloud-config-validate]: https://coreos.com/validate/
[etcd2-options]: https://coreos.com/etcd/docs/latest/configuration.html
[coreos-clustering]: https://coreos.com/etcd/docs/latest/clustering.html
[coreos-cluster-reconfig]: https://coreos.com/etcd/docs/latest/etcd-live-cluster-reconfiguration.html
[coreos-ca]: https://coreos.com/os/docs/latest/generate-self-signed-certificates.html
[coreos-etcd-ssl]: https://coreos.com/etcd/docs/latest/etcd-live-http-to-https-migration.html
[coreos-clients-ssl]: https://coreos.com/etcd/docs/latest/tls-etcd-clients.html
[do-coreos-ssl]: https://www.digitalocean.com/community/tutorials/how-to-secure-your-coreos-cluster-with-tls-ssl-and-firewall-rules
[cfssl]: https://github.com/cloudflare/cfssl
[fleet]: https://coreos.com/fleet/docs/latest/launching-containers-fleet.html
[unit-files]: https://coreos.com/fleet/docs/latest/unit-files-and-scheduling.html
[coreos-sssd]: https://coreos.com/os/docs/latest/sssd.html

- [StrongSwan][strongswan]:
  - [StrongSwan in Docker][docker-strongswan]
  - Configuration:
	- [`ipsec.conf`][ss-ipsec-conf]
	- [StrongSwan host-to-host config example][ss-host2host]

[strongswan]: https://strongswan.org/
[docker-strongswan]: https://github.com/philpl/docker-strongswan
[ss-ipsec-conf]: https://wiki.strongswan.org/projects/strongswan/wiki/IpsecConf
[ss-host2host]: https://wiki.strongswan.org/projects/strongswan/wiki/SaneExamples#Host-To-Host-transport-mode

- [FreeIPA][freeipa]:
  - [FreeIPA in Docker][freeipa-docker]
  - [FreeIPA client in Docker][freeipa-docker-client]
  - Man-pages:
	- [ipa-server-install][ipa-server-install-man]
	- [ipa-replica-prepare][ipa-replica-prepare-man]
	- [ipa-replica-install][ipa-replica-install-man]
	- [ipa-client-install][ipa-client-install-man]
	- [getcert-request][getcert-request-man]

  - Docs:
    - [RHEL7 IdM Guide][idm-guide]
	- RHEL7 system auth guide [certmonger][certmonger]
    - [RHEL6 replication docs][rhel6-ipa-rep-docs]
	- [NSS `certutil`][nss-certutil]
	- [FreeIPA behind SSL proxy][freeipa-ssl-proxy]

[freeipa]: http://www.freeipa.org/page/Main_Page
[freeipa-docker]: https://github.com/adelton/docker-freeipa
[freeipa-docker-client]: https://github.com/zultron/docker-freeipa/tree/centos-7-client
[ipa-server-install-man]: https://linux.die.net/man/1/ipa-server-install
[ipa-replica-prepare-man]: https://linux.die.net/man/1/ipa-replica-prepare
[ipa-replica-install-man]: https://linux.die.net/man/1/ipa-replica-install
[ipa-client-install-man]: https://linux.die.net/man/1/ipa-client-install
[getcert-request-man]: https://linux.die.net/man/1/getcert-request

[idm-guide]: https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/7/html/Linux_Domain_Identity_Authentication_and_Policy_Guide/index.html
[certmonger]: https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/7/html/System-Level_Authentication_Guide/certmongerX.html
[rhel6-ipa-rep-docs]: https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/6/html/Identity_Management_Guide/ipa-replica-manage.html
[nss-certutil]: https://developer.mozilla.org/en-US/docs/Mozilla/Projects/NSS/tools/NSS_Tools_certutil
[freeipa-ssl-proxy]: https://www.adelton.com/freeipa/freeipa-behind-ssl-proxy

- [HAProxy][haproxy]:
  - [Official HAProxy Docker Hub images][haproxy-docker-hub]
  - [Official HAProxy Dockerfiles][haproxy-docker-github]
  - [HAProxy documentation][haproxy-docs]

[haproxy]: http://www.haproxy.org/
[haproxy-docker-hub]: https://hub.docker.com/_/haproxy/
[haproxy-docker-github]: https://github.com/docker-library/haproxy/tree/master/1.6
[haproxy-docs]: http://cbonte.github.io/haproxy-dconv/

## Misc maintenance commands

Run `etcdctl` with SSL:

    cd /media/state/etcd
    etcdctl --endpoint=https://127.0.0.1:2380 \
        --ca-file=ca.pem --cert-file=client.pem --key-file=client-key.pem \
        cluster-health

Run shell in running container:

    ssh -t core@$HOST0 docker exec -it ipa bash

Other `fleetctl` commands:

	ssh core@$HOST0 fleetctl stop ipa.service  # stop the service
	ssh core@$HOST0 fleetctl list-unit-files   # show file exists
	ssh core@$HOST0 fleetctl cat ipa.service   # show file contents
	ssh core@$HOST0 fleetctl list-units        # show service status
	ssh core@$HOST0 fleetctl journal ipa.service
	ssh core@$HOST0 fleetctl unload ipa.service
	ssh core@$HOST0 fleetctl destroy ipa.service

FreeIPA information commands

        # List all servers and replicas
        ipa-replica-manage list
        # List agreements for a server
        ipa-replica-manage list h00.zultron.com

Querying LDAP needs SASL auth mech explicitly defined

        docker exec -it ipa ldapsearch -H ldaps://h20.zultron.com -Y GSSAPI

Run shell in `ipaclient` container, ready to run emacs

        docker exec -it --detach-keys ctrl-^ ipaclient env TERM=screen bash

## IPA configuration TODO

These should be added to automation

- Connect replica servers to eliminate h00 as SPOF

        ipa-replica-manage connect h10.zultron.com h20.zultron.com


## DNS

	[root@h00 /]# ipa help dns

	[root@h00 /]# ipa dnszone-show zultron.com --all

	[root@h00 /]# ipa dnszone-find zultron.com --forward-only --all

	[root@h00 /]# ipa dnsrecord-show zultron.com @ --all

	[root@h00 /]# ipa dnszone-add nyc1.zultron.com --forward-policy=none \
	  --admin-email=hostmaster@zultron.com --name-from-ip=10.26.0.0/24

Add DNS zone:

    [root@h00 /]# ipa dnszone-add nyc1.zultron.com \
        --forward-policy=none --admin-email=hostmaster@zultron.com
    [root@h00 /]# ipa dnszone-show nyc1.zultron.com --all
    [root@h00 /]# ipa dnszone-add sfo2.zultron.com \
        --forward-policy=none --admin-email=hostmaster@zultron.com
    [root@h00 /]# ipa dnszone-add fra1.zultron.com \
        --forward-policy=none --admin-email=hostmaster@zultron.com

## TODO

### Ansible

This system ended up reimplimenting what Ansible already does.  D'oh!
- [Manage CoreOS with Ansible][CoreOS-ansible]
- [Bootstrap CoreOS with Ansible][CoreOS-ansible-bootstrap]
- [Manage Docker with Ansible][Docker-ansible]
- [DigitalOcean API with Ansible][DO-ansible]

[CoreOS-ansible]: https://coreos.com/blog/managing-coreos-with-ansible/
[CoreOS-ansible-bootstrap]: https://github.com/defunctzombie/ansible-coreos-bootstrap
[Docker-ansible]: http://docs.ansible.com/ansible/guide_docker.html
[DO-ansible]: https://www.digitalocean.com/community/tutorials/how-to-use-the-digitalocean-api-v2-with-ansible-2-0-on-ubuntu-16-04

### Public SSL Certs

- [Let's Encrypt][letsencrypt]

[letsencrypt]: https://letsencrypt.org/

