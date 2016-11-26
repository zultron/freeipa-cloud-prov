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


## Documentation used to develop this system

- [DigitalOcean][digitalocean]:
  - [DigitalOcean API][do-api]
  - [Python DigitalOcean API][py-do]

[digitalocean]: https://cloud.digitalocean.com/
[do-api]: https://developers.digitalocean.com/documentation/v2/
[py-do]: https://github.com/koalalorenzo/python-digitalocean

- [Paramiko][paramiko] Python SSH client

[paramiko]: http://docs.paramiko.org/en/2.0/index.html

- [CoreOS][coreos]:
  - Basic configuration:
	- [Running CoreOS on DigitalOcean tutorial][coreos-do]
	- [CoreOS `cloud-config`][cloud-config] and
	  [validator][coreos-cloud-config-validate]
	- [`etcd2` options][etcd2-options]
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

[coreos]: https://coreos.com/
[coreos-do]: https://www.digitalocean.com/community/tutorials/how-to-set-up-a-coreos-cluster-on-digitalocean
[cloud-config]: https://coreos.com/os/docs/latest/cloud-config.html
[coreos-cloud-config-validate]: https://coreos.com/validate/
[etcd2-options]: https://github.com/coreos/etcd/blob/master/Documentation/v2/configuration.md
[coreos-ca]: https://coreos.com/os/docs/latest/generate-self-signed-certificates.html
[coreos-etcd-ssl]: https://coreos.com/etcd/docs/latest/etcd-live-http-to-https-migration.html
[coreos-clients-ssl]: https://coreos.com/etcd/docs/latest/tls-etcd-clients.html
[do-coreos-ssl]: https://www.digitalocean.com/community/tutorials/how-to-secure-your-coreos-cluster-with-tls-ssl-and-firewall-rules
[cfssl]: https://github.com/cloudflare/cfssl
[fleet]: https://coreos.com/fleet/docs/latest/launching-containers-fleet.html
[unit-files]: https://coreos.com/fleet/docs/latest/unit-files-and-scheduling.html

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
  - Man-pages:
	- [ipa-server-install][ipa-server-install-man]
	- [ipa-replica-prepare][ipa-replica-prepare-man]
	- [ipa-replica-install][ipa-replica-install-man]
	- [ipa-client-install][ipa-client-install-man]
  - Docs:
    - [RHEL7 IdM Guide][idm-guide]
	- RHEL7 system auth guide [certmonger][certmonger]
    - [RHEL6 replication docs][rhel6-ipa-rep-docs]

[freeipa]: http://www.freeipa.org/page/Main_Page
[freeipa-docker]: https://github.com/adelton/docker-freeipa
[ipa-server-install-man]: https://linux.die.net/man/1/ipa-server-install
[ipa-replica-prepare-man]: https://linux.die.net/man/1/ipa-replica-prepare
[ipa-replica-install-man]: https://linux.die.net/man/1/ipa-replica-install
[ipa-client-install-man]: https://linux.die.net/man/1/ipa-client-install
[idm-guide]: https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/7/html/Linux_Domain_Identity_Authentication_and_Policy_Guide/index.html
[certmonger]: https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/7/html/System-Level_Authentication_Guide/certmongerX.html
[rhel6-ipa-rep-docs]: https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/6/html/Identity_Management_Guide/ipa-replica-manage.html


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

## IPA configuration TODO

These should be added to automation

- Connect replica servers to eliminate h00 as SPOF

        ipa-replica-manage connect h10.zultron.com h20.zultron.com

- Set default login shell

        ipa config-mod --defaultshell /bin/bash

- [FreeIPA hardening][freeipa-hardening]
  - Either block Internet access, or
  - Disable zone transfers

          ipa dnszone-mod --allow-transfer="none;"

  - Disable recursion in `/data/etc/named.conf`

          allow-recursion {"none";};
          recursion no;

  - Disable unauthed LDAP access

          ldapmodify -c -x -H ldap://h00.zultron.com \
              -D "cn=Directory Manager" -W << EOF
          dn: cn=config
          changetype: modify
          replace: nsslapd-allow-anonymous-access
          nsslapd-allow-anonymous-access: rootdse

          EOF

[freeipa-hardening]: https://www.redhat.com/archives/freeipa-users/2014-April/msg00246.html
