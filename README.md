# FreeIPA in Kubernetes on CoreOS on DigitalOcean with Ansible

This project uses Ansible to automate bootstrapping a Kubernetes
cluster around FreeIPA infrastructure on DigitalOcean cloud instances
running CoreOS Container Linux.  Containerized services, including
email and web, may be run atop this platform.

FreeIPA provides core services essential to clusters, such as DNS,
user/host authentication/authorization, and SSL certificate
authorities.  A Kubernetes cluster built on this infrastructure
orchestrates various containerized services, simplifying service
management across the cluster.  These components run in CoreOS
Container Linux, a minimal OS that might be seen as a cluster node
appliance requiring minimal maintenance.  And the OS runs on
DigitalOcean droplets for inexpensive, automated provisioning on the
cloud.  Provisioning and configuration management is automated at all
levels with Ansible, and a full cluster may be bootstrapped and
running within an hour by issuing a few simple commands.

This project means to automate setup of a basic Internet site with
self-hosted email, web and phone system.  Service is redundant where
possible to increase reliability.  The components are chosen to scale
up, but the down-scaled, three-node bootstrap configuration is
complete, and meant to be ready for production.

Challenges:

- Bootstrapping CoreOS before FreeIPA DNS and CA are available
- Running etcd and Kubernetes on SSL certs without IP SANs, as all
  guides call for

## Current status

Although the goal is production readiness, this is unfinished and
experimental work.  It is not represented to be fit for any purpose.
**Readers are strongly advised to contemplate the risks before using
this work in any critical scenario.**

At present, the Ansible playbooks can complete the following tasks for
a 3-node cluster with no manual intervention.  The end result is a
running Kubernetes cluster, still with a few minor known issues.

FIXME refer to below instead of these bullets

- Provision DigitalOcean cloud servers
  - Configure CoreOS image with ignition
  - Add and configure block storage for filesystems and swap
  - Other basic OS configuration
- Deploy etcd and flanneld with temporary DNS and CA
  - Set up temporary `dnsmasq` container with etcd SRV records
  - Set up temporary `cfssl` CA with etcd TLS certificates
  - Start etcd cluster
  - Configure and run flanneld
  - Configure `etcdctl` client on nodes
- Install FreeIPA server, replicas and clients
  - Add and configure block storage for IPA data
  - Configure and run FreeIPA server install
  - Migrate to FreeIPA DNS
  - Configure and run FreeIPA replica and client installs
  - Harden publicly exposed services
  - Basic DNS and other configuration
- Configure Docker TLS for remote control
  - IPA:  Create CA and install monitored service certificates
  - Configure Docker TLS port with client cert authentication
  - Create client cert
  - Restart docker service with TLS configuration
- Migrate etcd to FreeIPA certs
  - IPA:  Create CA and install monitored service certificates
  - Set up cluster DNS SRV records
- Configure and start kubernetes
  - IPA:  Create CA and install monitored service certificates
  - Template kube-system pod manifests, kubelet service, kube
    configuration, etc. for API server and other nodes, with
    inter-node TLS and etcd TLS endpoints
  - Start kubelet service, wait for API availability, and check for
    pod creation
  - Install and configure `kubectl` client with TLS client certs
  - Install and configure the k8s dns and dashboard add-ons

## Installing the cluster

- Initial site setup (only run once):

        # Copy `hosts.yaml` template and edit
        cp hosts.yaml.example hosts.yaml
        # You will certainly want to edit:
        # - domain_name and kerberos_realm
        # - network_prefix:  each host, first 2 octets MUST BE unique
        # You might want to edit:
        # - host names:  host1 etc.
        # - additional hosts:  minimum 3 hosts
        # - defaults:  size_id (default 1gb), region_id (nyc1)
        $EDITOR hosts.yaml

        # Optionally build container if not pulling from docker hub
		./container -b

        # Start shell in container; the following `ansible-*` commands
        # should all be run in the container
        ./container

        # Set up password vault once; will prompt for DigitalOcean
        # token, FreeIPA admin and directory passwords
        ansible-playbook playbooks/init-site.yaml

- Install whole cluster in one command:

        ansible-playbook playbooks/site.yaml

- Delete a node or the whole cluster

        # Destroy host1
        ansible-playbook playbooks/destroy.yaml -e confirm=host -l host1

        # Destroy whole cluster
        ansible-playbook playbooks/destroy.yaml -e confirm=all

-----------

## FIXME restructure

To get IPA server on a calico network from the start will need a
restructure.

Done:
- If bootstrapping:
  - Gen and deploy certs with `cfssl`
  - Point dns at `dnsmasq` in container with `SRV` records
- If not bootstrapping:
  - Gen and deploy certs with IPA
- Bring up etcd cluster with calico
- Point dns at IPA servers
- Provision IPA

TODO:
- Add `SRV` records, etc.
- Re-gen certs with certmonger
  - Clean up bootstrapping
- Migrate onto new certs

-----------

## Commands for development

- Misc commands:

        # Re-collect facts about host
        ansible host1 -m setup \
            -e ansible_python_interpreter=/home/core/bin/python \
            -e ansible_ssh_user=core

        # List all variables for a host
        ansible host1 -m debug -a "var=hostvars[inventory_hostname]"
        # Also vars, environment, group_names, groups

- Ansible ipa_* tests:
  - Testing against live IPA server
  ```
      env \
        PYTHONPATH=$(pwd)/lib \
        IPA_HOST=host1.example.com \
        IPA_USER=admin \
        IPA_PASS=mysecretpw \
        IPA_DOMAIN=example.com \
        IPA_NSRECORD=host1.example.com. \
        nosetests -v test/units/modules/identity/ipa/
    ```

- Run nosetests in ansible repo
  - `PYTHONPATH=$(pwd)/lib nosetests -v test/units/modules/identity/ipa/`

Run `etcdctl` with SSL:

    cd /media/state/etcd
    etcdctl --endpoint=https://$(hostname):2380 \
        --ca-file=ca.pem --cert-file=cert.pem --key-file=key.pem \
        cluster-health

Run shell in running container:

    ssh -t core@$HOST0 docker exec -it ipa bash

FreeIPA information commands

        # List all servers and replicas
        ipa-replica-manage list
        # List agreements for a server
        ipa-replica-manage list host1.example.com

Querying LDAP needs SASL auth mech explicitly defined

        docker exec -it ipa ldapsearch -H ldaps://host1.example.com -Y GSSAPI

Run shell in `ipaclient` container, ready to run emacs

        docker exec -it --detach-keys ctrl-^ ipaclient env TERM=screen bash

Misc. kubernetes commands

    kubectl config *
    kubectl cluster-info
    kubectl get cs
    kubectl --namespace=kube-system get pods
    kubectl --namespace=kube-system describe pods kube-dns-v20-d7crm
    kubectl --namespace=kube-system logs kube-dns-v20-d7crm kubedns
    kubectl --namespace=kube-system replace --force -f var/k8s/dns-addon.yaml
    kubectl --namespace=kube-system delete pods kube-dns-v20-d7crm
    kubectl --namespace=kube-system port-forward kubernetes-dashboard-v1.6.0-xcgh7 9090
    kubectl --namespace=kube-system exec kube-dns-v20-jh9sb -c kubedns -- nslookup host1
    kubectl --namespace=kube-system describe pods kube-dns-v20-jh9sb

-----------

## Documentation used to develop this system

### [Ansible][ansible]

At the lowest level, Ansible automates bootstrapping.

Ansible's enormous number of modules handle 90% of our needs.  The
missing 10% primarily handle FreeIPA object classes that the roles in
this repo use extensively, such as the SSL-related objects CA, CA ACL,
certificate and service, and also DNS zones and records.  There is
also a parted module copied from upstream with bugfixes.

A number of filter plugins, some for specific purposes and some
general, simplify playbooks.  It has been found, however, that some of
them duplicate existing functionality in Ansible and should be
factored out.

Documentation used during development:

- [Glossary][ansible-glossary] of Play, Role, Block, Task directives
- [Local actions][ansible-local] on stackoverflow, incl. nice syntax
- And CoreOS Container Linux:
  - [Manage CoreOS with Ansible][CoreOS-ansible]
  - [Bootstrap CoreOS with Ansible][CoreOS-ansible-bootstrap]
- And Docker:
  - [Manage Docker with Ansible][Docker-ansible]
  - [Docker connection][ansible-docker-conn] (st. similar merged into Ansible)
- Plugin development:
  - [Local facts][ansible-local-facts]
    - `ansible.cfg`: `fact_path = /home/centos/ansible_facts.d`
    - [Providing cached facts from modules][ansible-module-facts]
- This online [YAML parser][yaml-parser] is very helpful

[ansible]: https://www.ansible.com/
[ansible-glossary]: https://docs.ansible.com/ansible/playbooks_keywords.html
[ansible-local]: http://stackoverflow.com/questions/18900236/run-command-on-the-ansible-host

[CoreOS-ansible]: https://coreos.com/blog/managing-coreos-with-ansible/
[CoreOS-ansible-bootstrap]: https://github.com/defunctzombie/ansible-coreos-bootstrap

[Docker-ansible]: http://docs.ansible.com/ansible/guide_docker.html
[ansible-docker-conn]: http://docs.ansible.com/ansible/intro_inventory.html#non-ssh-connection-types
[ansible-local-facts]: http://docs.ansible.com/ansible/playbooks_variables.html#local-facts-facts-d
[ansible-module-facts]:  http://docs.ansible.com/ansible/dev_guide/developing_modules_general.html#module-provided-facts
[yaml-parser]: http://yaml-online-parser.appspot.com/

### [DigitalOcean][digitalocean]

First step is to provision DigitalOcean droplets with CoreOS image.

- [DigitalOcean API][do-api]
- [Python DigitalOcean API][py-do]
- And Ansible:
  - [DigitalOcean API with Ansible][DO-ansible]
- And CoreOS:
  - [Running CoreOS on DigitalOcean tutorial][coreos-do]

[digitalocean]: https://cloud.digitalocean.com/
[do-api]: https://developers.digitalocean.com/documentation/v2/
[py-do]: https://github.com/koalalorenzo/python-digitalocean
[DO-ansible]: https://www.digitalocean.com/community/tutorials/how-to-use-the-digitalocean-api-v2-with-ansible-2-0-on-ubuntu-16-04
[coreos-do]: https://www.digitalocean.com/community/tutorials/how-to-set-up-a-coreos-cluster-on-digitalocean

### Clustering

In this configuration, etcd requires DNS SRV records for initial
cluster discovery and TLS certificates for communication.  Running
atop etcd, Calico and its libnetwork plugin manage the Docker networks
that containers attach to.

FreeIPA provides the DNS service and TLS certificate authority for
etcd, but requires Calico for a fixed IP routable across cluster
nodes, introducing a chicken-and-egg problem.  This is overcome by
bootstrapping etcd with a temporary `dnsmasq` DNS service configured
with cluster discovery SRV records, and a `cfssl` TLS CA to generate
temporary SSL certificates.  Once the etcd cluster is initialized, the
DNS service may be torn down (SRV records no longer needed for
discovery, and `/etc/hosts` taking the place of A records).  In later
stages, FreeIPA can be installed and permanent etcd certificates will
be generated with a dedicated sub-CA, and installed and monitored and
automatically renewed with certmonger.

With certificates installed, nodes join the etcd cluster [FIXME]

- Basic configuration:
  - [CoreOS Provisioning][coreos-provisioning]
  - [CoreOS on DigitalOcean][coreos-do]
  - [Ignition config validator][coreos-ignition-config-validate]
  - [`etcd3` options][etcd3-options]
  - [CoreOS cluster reconfiguration][coreos-cluster-reconfig]

- SSL on CoreOS:
  - [Enabling HTTPS in an existing etcd cluster][coreos-tls-existing]
  - [CoreOS client ssl][coreos-clients-ssl]
  - [CoreOS SSL and iptables on DigitalOcean][do-coreos-ssl] (somewhat
    outdated)

- Temporary SSL certs and DNS service
  - Generate [self-signed certificates][coreos-cfssl-certs] with
    `cfssl`
  - Provide DNS [SRV records with `dnsmasq`][dnsmasq-srv-rec]
  - [`dnsmasq` manual][dnsmasq-man]

- Flannel networking:
  - [CoreOS Flannel docs][coreos-flannel]

[coreos]: https://coreos.com/

[coreos-provisioning]: https://coreos.com/os/docs/latest/provisioning.html
[coreos-do]: https://coreos.com/os/docs/latest/booting-on-digitalocean.html
[coreos-ignition-config-validate]: https://coreos.com/validate/
[etcd3-options]: https://coreos.com/etcd/docs/latest/op-guide/configuration.html
[coreos-cluster-reconfig]: https://coreos.com/etcd/docs/latest/etcd-live-cluster-reconfiguration.html

[coreos-tls-existing]: https://coreos.com/etcd/docs/latest/etcd-live-http-to-https-migration.html
[coreos-clients-ssl]: https://coreos.com/etcd/docs/latest/tls-etcd-clients.html
[do-coreos-ssl]: https://www.digitalocean.com/community/tutorials/how-to-secure-your-coreos-cluster-with-tls-ssl-and-firewall-rules

[coreos-cfssl-certs]:  https://coreos.com/os/docs/latest/generate-self-signed-certificates.html
[dnsmasq-srv-rec]:  https://blog.delouw.ch/2014/03/26/providing-srv-and-txt-records-for-kerberos-and-ldap-with-dnsmasq/
[dnsmasq-man]:  http://www.thekelleys.org.uk/dnsmasq/docs/dnsmasq-man.html

[coreos-flannel]: https://coreos.com/flannel/docs/latest/flannel-config.html

### [FreeIPA][freeipa]:

With basic CoreOS clustering in place, first the FreeIPA server and
then the replicas and clients may be installed in Docker containers.

FreeIPA consists of many microservices tied together with a web UI and
a complex installer.  Installation is non-trivial, but there is an
official project to containerize FreeIPA server and replicas.

Not all cluster nodes need to run a FreeIPA server.  These nodes
instead run only the certmonger service, needed to manage local
service SSL certificates from the remote IPA server.  Because
of [lack of consensus][freeipa-container-155] in the FreeIPA community
about providing an official client container with certmonger service,
one is created from a [customized fork][freeipa-container-client] for
use in this project.

The FreeIPA DNS service is used internally by the cluster, and so the
internal service IP must be fixed and routable across the cluster.
Routing internal IPs across nodes is possible with flannel, but there
is no way to guarantee a fixed container IP on the main `docker0`
network.  Instead, a separate Docker 'ipa' network is managed by a
separate flanneld instance, configured with reservations to guarantee
the network address remains fixed on a node, and configured with
30-bit CIDRs to guarantee the container IP remains fixed within the
network.

Also internally, the CoreOS host will also be enrolled in the FreeIPA
domain with SSSD.

FreeIPA services will also be exposed on the Internet for remote
clients of the domain.  Services therefore must be hardened, for
example by disabling DNS recursion and disabling anonymous LDAP
queries.

The FreeIPA container does not run inside Kubernetes.  It is unknown
whether there are technical limitations with starting Kubernetes
during either initial bootstrapping or normal node rebooting while DNS
services are not yet available.  At the time of writing, the FreeIPA
container [cannot run in k8s][freeipa-container-154], because of
shared PID space changes in version 1.7 that prevent systemd from
starting.  (This may be fixed in version 1.8; fqdn-based TLS is broken
in version 1.6.)

- Docker:
  - [FreeIPA server/replica in Docker][freeipa-docker]
  - [Flannel fixed IP][flannel-fixed-ip]
  - [Flannel network reservations][flannel-reservation]
  - [Flanneld configuration options][flanneld-config]

- FreeIPA man-pages:
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

- [Configure SSSD on CoreOS][coreos-sssd]

[freeipa]: http://www.freeipa.org/page/Main_Page

[freeipa-container-155]: https://github.com/freeipa/freeipa-container/pull/155
[freeipa-container-client]: https://github.com/zultron/freeipa-container
[freeipa-container-154]: https://github.com/freeipa/freeipa-container/issues/154

[freeipa-docker]: https://github.com/freeipa/freeipa-container
[flannel-fixed-ip]: https://groups.google.com/forum/#!topic/coreos-user/lt7muDO820U
[flannel-reservation]: https://coreos.com/flannel/docs/latest/reservations.html#reservations
[flanneld-config]: https://coreos.com/flannel/docs/latest/configuration.html


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

[coreos-sssd]: https://coreos.com/os/docs/latest/sssd.html

### Kubernetes

Once CoreOS clustering and FreeIPA is running, Kubernetes may be
installed.

Installation follows the (abandoned?) CoreOS documentation, except
that TLS certificates go by FQDN in the subject CN because FreeIPA
cannot create TLS certificates with IP address SANs.  This seems to be
an unusual use case, but seems to work (see below).

FIXME  Ansible management of k8s resources

Previous versions of CoreOS used fleet for container orchestration,
but fleet is now deprecated in favor of Kubernetes.

- [Kubectl cheat sheet][kubectl-cheat]

- Kubernetes and CoreOS
  - [CoreOS Kubernetes docs][coreos-kubernetes]
  - [Kubernetes CoreOS docs][kubernetes-coreos]
  - Kubernetes is [replacing fleet][coreos-fleet-to-k8s] in CoreOS

- Kubernetes and Ansible
  - [Kubernetes module][ansible-kubernetes-module] in Ansible
  - [Ansible examples][kub-ansible] incl. etcd2, docker in kubernetes
  - Other projects to set up Kubernetes on CoreOS with Ansible
    - [GH thesamet/ansible-kubernetes-coreos][kubernetes-coreos-ansible-1]
    - [GH sebiwi/kubernetes-coreos][kubernetes-coreos-ansible-2]; adds Vagrant
    - [GH deimosfr/ansible-coreos-kubernetes][kubernetes-coreos-ansible-3];
      for "production usage"

- Kubernetes and FreeIPA
  - Kubernetes [TLS certs without IP SANs][k8s-no-ip-sans] may work
  - [FreeIPA won't issue IP SANs][freeipa-no-ip-sans]

[kubectl-cheat]: https://kubernetes.io/docs/user-guide/kubectl-cheatsheet/

[coreos-kubernetes]:  https://coreos.com/kubernetes/docs/latest/
[kubernetes-coreos]:  https://kubernetes.io/docs/getting-started-guides/coreos/
[coreos-fleet-to-k8s]:  https://coreos.com/blog/migrating-from-fleet-to-kubernetes.html

[ansible-kubernetes-module]:  http://docs.ansible.com/ansible/kubernetes_module.html
[kub-ansible]: https://github.com/kubernetes/contrib/tree/master/ansible/roles
[kubernetes-coreos-ansible-1]:  https://github.com/thesamet/ansible-kubernetes-coreos
[kubernetes-coreos-ansible-2]:  https://github.com/sebiwi/kubernetes-coreos
[kubernetes-coreos-ansible-3]:  https://github.com/deimosfr/ansible-coreos-kubernetes

[k8s-no-ip-sans]: https://groups.google.com/forum/#!searchin/kubernetes-users/morris%7Csort:relevance/kubernetes-users/azpLUFHu_2I/U56NVJyACAAJ
[freeipa-no-ip-sans]:  https://www.redhat.com/archives/freeipa-users/2016-October/msg00053.html

### [HAProxy][haproxy]

HAProxy for load balancing, but really for reverse-proxying multiple
web services on a single IP.

- [Official HAProxy Docker Hub images][haproxy-docker-hub]
- [Official HAProxy Dockerfiles][haproxy-docker-github]
- [HAProxy documentation][haproxy-docs]

[haproxy]: http://www.haproxy.org/
[haproxy-docker-hub]: https://hub.docker.com/_/haproxy/
[haproxy-docker-github]: https://github.com/docker-library/haproxy/tree/master/1.6
[haproxy-docs]: http://cbonte.github.io/haproxy-dconv/


### Postfix

Postfix, Dovecot

- 'container-images' [Postfix][ci-postfix] and [Dovecot][ci-dovecot]
  Docker containers (What is this project?)

[ci-postfix]: https://github.com/container-images/postfix
[ci-dovecot]: https://github.com/container-images/dovecot

-----------

## Other links

- [port.direct Harbor][pd-harbor] integrates K8s and FreeIPA (and others)
- A [paper][tremolo-k8s-idm] from Tremolo Security about a K8s and
  FreeIPA integration

[pd-harbor]: https://github.com/portdirect/harbor
[tremolo-k8s-idm]: https://www.tremolosecurity.com/kubernetes-idm-part-i/

## TODO

### IPTables and Docker, again

DNS recursion is disabled in named.conf and in the IPA config, I
thought, but now it's recursing publicly again.  This happened when
the manual iptables rules were removed; now external DNS queries
appear to be coming from the `br-ipa` router address, an internal 10.0.0.0/8
address.

Also, the `DOCKER-ISOLATION` chain, which blocks packets between
the `br-ipa` and `docker0` bridges, is going to cause problems for
containers on `docker0` attempting to access the local DNS server.
There appears to be no way of fixing this until docker v. 17.0, which
supports a `DOCKER-USER` iptables chain.  Right now, Docker inserts
the isolation chain at the top of the forward chain every time it
restarts, and maybe even more often.

The solution will inevitably be to restore manual iptables to the
`br-ipa` network.

...Or, use calico?

Create docker network using `docker network create --driver calico
--ipam-driver calico-ipam`, then specify container IP

https://docs.projectcalico.org/v2.5/getting-started/docker/tutorials/ipam

To do this, use the `dockerd --cluster-store` stuff.

https://docs.projectcalico.org/v2.5/getting-started/docker/installation/requirements

How to run the calico container:

https://docs.projectcalico.org/v2.5/getting-started/docker/installation/manual

- FIXME The current
  `playbooks/roles/calico-deploy/templates/calico-rkt.service.j2`
  needs to be fixed with the right resolv.conf or something.

Later, integrate with k8s:

https://docs.projectcalico.org/v2.5/getting-started/kubernetes/

### GH Issues

- Container IP address issues:
  - [nsupdate `incorrect section name` error][freeipa-container-92]
  - [`update_server_ip_address` rationale][freeipa-container-51]
  - [`ipa-server-install-options` issues][freeipa-container-121];
    includes mention of `incorrect section name` problem and
    `update_server_ip_address` function
    - Points to [BZ 1377973][bz-1377973], about `--ip-address=$IP`
      where `$IP` is not configured on any container interface;
      apparently fixed in v. 4.5
- Container [FreeIPA v. 4.5 support][freeipa-container-157]
- Script debugging options [PR #156][freeipa-container-156]
- PR for [client-mode][freeipa-container-155]

[freeipa-container-157]: https://github.com/freeipa/freeipa-container/issues/157
[freeipa-container-92]: https://github.com/freeipa/freeipa-container/issues/92
[freeipa-container-51]: https://github.com/freeipa/freeipa-container/issues/51
[freeipa-container-121]: https://github.com/freeipa/freeipa-container/issues/121
[bz-1377973]: https://bugzilla.redhat.com/show_bug.cgi?id=1377973
[freeipa-container-156]: https://github.com/freeipa/freeipa-container/pull/156
[freeipa-container-155]: https://github.com/freeipa/freeipa-container/pull/155

### Sub-CA and security

Verify that top-level client certs can't auth against services
configured with sub-CAs:  Docker, etcd, k8s

### IPA configuration

These should be added to automation

- Connect replica servers to eliminate host1 as SPOF

        ipa-replica-manage connect host2.example.com host3.example.com

- Create ipa sidekick `/etc/resolv.conf` service to install
  FreeIPA/Google DNS servers at start/stop

### Public SSL Certs

- [Let's Encrypt][letsencrypt]

[letsencrypt]: https://letsencrypt.org/

### Cheaper VPSs

DO isn't the cheapest anymore, and Dogtag struggles in a $10/month 1gb
droplet.

- [Scaleway][scaleway]:  For 30% less money, get 300% more CPU and RAM
  and 150% more disk, and 300% more disk for the same money.
  Apparently no Ansible modules, but there is an API and a
  (read-only?) Python module.

- [OVH VPS][ovh]:  For 30% less money, get 50% less CPU, 300% more
  RAM, 60% less disk, in NA

[scaleway]: https://www.scaleway.com/pricing/
[ovh]: https://www.ovh.com/us/vps/vps-ssd.xml

### Logging

Possibilities:

- Kubernetes [Logging Agent For Elasticsearch][k8s-fluentd-es] add-on
- Kubernetes [Logging Using Elasticsearch and Kibana][k8s-es-kibana]
  docs
  - Deis.com blog,
    [Kubernetes Logging With Elasticsearch and Kibana][k8s-logging-deis-blog]

[k8s-fluentd-es]: https://github.com/kubernetes/kubernetes/tree/master/cluster/addons/fluentd-elasticsearch
[k8s-es-kibana]: https://kubernetes.io/docs/tasks/debug-application-cluster/logging-elasticsearch-kibana/
[k8s-logging-deis-blog]: https://deis.com/blog/2016/kubernetes-logging-with-elasticsearch-and-kibana/

### Schedule pods on k8s apiserver

- Security recommendations say don't schedule pods on k8s master
- However, this is possible; see [master isolation docs][k8s-master-isolation]

[k8s-master-isolation]: https://kubernetes.io/docs/setup/independent/create-cluster-kubeadm/#master-isolation

### CoreOS SSSD

- Enrol CoreOS in IPA

### Adding later nodes

- This probably won't work at all right now.

### FIXME play_hosts

http://docs.ansible.com/ansible/latest/playbooks_loops.html#looping-over-the-inventory

### FIXME get docker IP easily

docker inspect --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ipa

### Docker cluster-store

See the `--cluster-store` argument for doing something in etcd

https://docs.docker.com/engine/reference/commandline/dockerd/
