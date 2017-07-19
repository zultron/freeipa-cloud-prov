# FreeIPA in Kubernetes on CoreOS on DigitalOcean with Ansible

This project uses Ansible to automate bootstrapping a Kubernetes
cluster around FreeIPA infrastructure, with cluster nodes running
CoreOS Container Linux on DigitalOcean droplets.  It also installs a
number of basic containerized services, including email and web.

FreeIPA provides core services essential to clusters, such as DNS,
user/host authentication/authorization, and SSL certificate
authorities.  A Kubernetes cluster built on this infrastructure
orchestrates various containerized services, including FreeIPA itself,
simplifying service management across the cluster.  Kubernetes runs in
CoreOS Container Linux, a minimal OS that might be seen as a cluster
node appliance requiring minimal maintenance.  And the OS runs on
DigitalOcean droplets for inexpensive, automated provisioning on the
cloud.  Provisioning and configuration management is automated at all
levels with Ansible, and a full cluster may be bootstrapped and
running within an hour by issuing a few simple commands.

This project means to automate setup of a basic Internet site with
self-hosted email, web and phone system.  Service is redundant where
possible to increase reliability.  The components are chosen to scale
up, but the down-scaled, three-node bootstrap configuration is
complete, and meant to be ready for production.

Although the goal is production readiness, this is unfinished and
experimental work.  It is not represented to be fit for any purpose.
**Readers are strongly advised to contemplate the risks before using
this work in any critical scenario.**

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

        # Set up password vault once; will prompt for FreeIPA admin
        # and directory passwords
        ansible-playbook playbooks/init-site.yaml

- Install hosts (master first, then others):

        # Provision master droplet on DigitalOcean and configure storage
        ansible-playbook playbooks/provision.yaml -l host1

        # Install FreeIPA server+client containers
        ansible-playbook playbooks/freeipa-install.yaml -l host1

        # Install and configure etcd3 and Kubernetes on master
        ansible-playbook playbooks/coreos-cluster.yaml -l host1

        # Install other cluster nodes
        ansible-playbook playbooks/provision.yaml -l host2,host3
        ansible-playbook playbooks/freeipa-install.yaml -l host2,host3
        ansible-playbook playbooks/coreos-kubernetes.yaml -l host2,host3

        # Install services on all hosts:  email, PBX, web, etc.
        ansible-playbook playbooks/services-install.yaml

## Other commands

- Misc commands:

        # Re-collect facts about host
        ansible host1 -m setup \
            -e ansible_python_interpreter=/home/core/bin/python \
            -e ansible_ssh_user=core

        # Destroy host1
        ansible-playbook playbooks/destroy.yaml -e confirm=yes -l host1

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
    etcdctl --endpoint=https://127.0.0.1:2380 \
        --ca-file=ca.pem --cert-file=client.pem --key-file=client-key.pem \
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

## Documentation used to develop this system

### [Ansible][ansible]

Ansible automates the bootstrapping before anything else.

At this time, Ansible has an enormous number of modules that handle
90% of our needs.  The missing 10% primarily handle FreeIPA object
classes that the roles in this repo use extensively, such as the
SSL-related objects CA, CA ACL, certificate and service, and also DNS
zones and records.  There is also a parted module copied from upstream
with bugfixes.

It also turned out to simplify playbooks to write a number of filter
plugins, some for specific purposes and some general.

- [Glossary][ansible-glossary] of Play, Role, Block, Task directives
- [Local actions][ansible-local] on stackoverflow, incl. nice syntax
- and CoreOS Container Linux:
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

### [FreeIPA][freeipa]:

Next step is to install and configure FreeIPA in a Docker container.

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

### [CoreOS][coreos]

CoreOS Container Linux must be configured for clustering with etcd3
and Kubernetes.  This depends on FreeIPA being bootstrapped.

The initial node will be bootstrapped with a static cluster
configuration and no TLS.  TLS will be introduced after FreeIPA is
running and DNS and the CA are available.

The etcd cluster will be bootstrapped from DNS with the
`--discovery-srv` flag.

All communication will be over TLS with certs generated from FreeIPA
(in a dedicated sub-CA) and monitored with certmonger.

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

- Launching containers in CoreOS:
  - See Kubernetes below
  - Fleet is deprecated

- IPA integration
  - [CoreOS SSSD integration][coreos-sssd]
  

[coreos]: https://coreos.com/

[coreos-provisioning]: https://coreos.com/os/docs/latest/provisioning.html
[coreos-do]: https://coreos.com/os/docs/latest/booting-on-digitalocean.html
[coreos-ignition-config-validate]: https://coreos.com/validate/
[etcd3-options]: https://coreos.com/etcd/docs/latest/op-guide/configuration.html
[coreos-cluster-reconfig]: https://coreos.com/etcd/docs/latest/etcd-live-cluster-reconfiguration.html

[coreos-tls-existing]: https://coreos.com/etcd/docs/latest/etcd-live-http-to-https-migration.html
[coreos-clients-ssl]: https://coreos.com/etcd/docs/latest/tls-etcd-clients.html
[do-coreos-ssl]: https://www.digitalocean.com/community/tutorials/how-to-secure-your-coreos-cluster-with-tls-ssl-and-firewall-rules

[coreos-sssd]: https://coreos.com/os/docs/latest/sssd.html

### Flannel

Kubernetes depends on Flannel networking.

- [CoreOS Flannel docs][coreos-flannel]

[coreos-flannel]: https://coreos.com/flannel/docs/latest/flannel-config.html

### Kubernetes

Install Kubernetes after the Container Linux cluster is configured.

- [CoreOS Kubernetes docs][coreos-kubernetes]
- [Ansible examples][kub-ansible] incl. etcd2, docker in kubernetes

- Kubernetes is replacing fleet
- Other projects to set up Kubernetes on CoreOS with Ansible
  - [GH thesamet/ansible-kubernetes-coreos][kubernetes-coreos-ansible-1]
  - [GH sebiwi/kubernetes-coreos][kubernetes-coreos-ansible-2]; adds Vagrant
  - [GH deimosfr/ansible-coreos-kubernetes][kubernetes-coreos-ansible-3];
    for "production usage"
- [Kubernetes CoreOS docs][kubernetes-coreos]
  - Question:  Article calls for creating certs with IP addr altname
    attributes; how to do with FreeIPA?
    - [FreeIPA won't issue IP SANs][freeipa-no-ip-sans]
    - Kubernetes-users list [query][kubernetes-no-ip-sans-email]
- [Kubernetes module][ansible-kubernetes-module] in Ansible


[coreos-kubernetes]:  https://coreos.com/kubernetes/docs/latest/
[kub-ansible]: https://github.com/kubernetes/contrib/tree/master/ansible/roles
[kubernetes-coreos-ansible-1]:  https://github.com/thesamet/ansible-kubernetes-coreos
[kubernetes-coreos-ansible-2]:  https://github.com/sebiwi/kubernetes-coreos
[kubernetes-coreos-ansible-3]:  https://github.com/deimosfr/ansible-coreos-kubernetes
[kubernetes-coreos]:  https://kubernetes.io/docs/getting-started-guides/coreos/
[freeipa-no-ip-sans]:  https://www.redhat.com/archives/freeipa-users/2016-October/msg00053.html
[kubernetes-no-ip-sans-email]:  https://groups.google.com/forum/#!topic/kubernetes-users/azpLUFHu_2I
[ansible-kubernetes-module]:  http://docs.ansible.com/ansible/kubernetes_module.html

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



## TODO

### Adjust etcd endpoints after cluster complete

- Initial members may have incomplete endpoint list

### Is certmonger actually running in ipaclient?

- Should a new ipaclient Docker image be written from scratch?
  - The fake systemd stuff is pretty irritating; why not a real
    systemd like the `ipa` container seems to have?

### IPA configuration

These should be added to automation

- Connect replica servers to eliminate host1 as SPOF

        ipa-replica-manage connect host2.example.com host3.example.com

- Create ipa sidekick `/etc/resolv.conf` service to install
  FreeIPA/Google DNS servers at start/stop


### Public SSL Certs

- [Let's Encrypt][letsencrypt]

[letsencrypt]: https://letsencrypt.org/

