ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: ipa_service
author: John Morris (@zultron)
short_description: Manage FreeIPA services
description:
- Add, delete and modify services within IPA server
options:
  krbprincipalname:
    description: Kerberos principal name
    required: true
    aliases: ['name']
  managed_by:
    description:
      - List of hosts that can manage this service
      - When this option is given, the C(state) option applies to this
        list of hosts.
    required: false
  state:
    description:
      - State to ensure
      - If the C(managed_by) option is not supplied, C(state=absent) ensures
        the service itself is absent, and otherwise it ensures the listed
        hosts are absent from C(managed_by).
      - C(state=present) applies to both the service itself and C(managed_by)
        hosts.
    required: false
    default: present
    choices: ["present", "absent"]
  ipa_port:
    description: Port of IPA server
    required: false
    default: 443
  ipa_host:
    description: IP or hostname of IPA server
    required: false
    default: "ipa.example.com"
  ipa_user:
    description: Administrative account used on IPA server
    required: false
    default: "admin"
  ipa_pass:
    description: Password of administrative user
    required: true
  ipa_prot:
    description: Protocol used by IPA server
    required: false
    default: "https"
    choices: ["http", "https"]
  validate_certs:
    description:
    - This only applies if C(ipa_prot) is I(https).
    - If set to C(no), the SSL certificates will not be validated.
    - This should only set to C(no) used on personally controlled
      sites using self-signed certificates.
    required: false
    default: true
version_added: "2.3"
'''

EXAMPLES = '''
# Create LDAP service
- ipa_service:
    krbprincipalname: ldap/host1.example.com@EXAMPLE.COM
    state: present
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret

# Remove LDAP service
- ipa_service:
    krbprincipalname: ldap/host1.example.com@EXAMPLE.COM
    state: absent
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret

# Allow host2 to manage host1 LDAP service
- ipa_service:
    krbprincipalname: ldap/host1.example.com@EXAMPLE.COM
    state: present
    managed_by: [ host2.example.com ]
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret
'''

RETURN = '''
service:
  description: service as returned by IPA API
  returned: always
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.pycompat24 import get_exception
from ansible.module_utils.ipa import IPAClient


class ServiceIPAClient(IPAClient):
    def __init__(self, module, host, port, protocol):
        super(ServiceIPAClient, self).__init__(module, host, port, protocol)

    def service_find(self, name):
        return self._post_json(method='service_find', name=None,
                               item={'all': True, 'krbprincipalname': name})

    def service_show(self, name):
        return self._post_json(method='service_show', name=name)

    def service_add(self, name, item):
        return self._post_json(method='service_add', name=name, item=item)

    def service_mod(self, name, item):
        return self._post_json(method='service_mod', name=name, item=item)

    def service_del(self, name):
        return self._post_json(method='service_del', name=name)

    def service_add_host(self, name, item):
        return self._post_json(method='service_add_host', name=name, item=item)

    def service_remove_host(self, name, item):
        return self._post_json(method='service_remove_host', name=name, item=item)

    # Also:
    # - service-add-cert
    # - service-remove-cert
    # - service-add-principal
    # - service-remove-principal
    # - service-allow-create-keytab
    # - service-disallow-create-keytab
    # - service-allow-retrieve-keytab
    # - service-disallow-retrieve-keytab
    # - service-remove-permission


def get_service_dict(host=None):
    service = dict(
        host = host if host is not None else [],
    )
    return service


def get_service_diff(client, ipa_service, module_service):
    return client.get_diff(ipa_data=ipa_service, module_data=module_service)


def ensure(module, client):
    state = module.params['state']
    name = module.params['krbprincipalname']

    module_service = get_service_dict(
        host=module.params.get('host'),
    )

    ipa_service = client.service_find(name=name)

    changed = False
    if state == 'present':
        if not ipa_service:
            changed = True
            if not module.check_mode:
                ipa_service = client.service_add(name=name, item={})

        if module_service['host'] is not None:
            # Get object with managedby_host attr
            ipa_service = client.service_show(name)
            add_hosts = list(set(module_service['host']) -
                             set(ipa_service['managedby_host']))
            if add_hosts:
                changed = True
                if not module.check_mode:
                    client.service_add_host(name, dict(host=add_hosts))
                    
    else:
        if ipa_service:
            if module_service['host']:
                # Get object with managedby_host attr
                ipa_service = client.service_show(name)
                del_hosts = list(set(module_service['host']) &
                                 set(ipa_service['managedby_host']))
                if del_hosts:
                    changed = True
                    if not module.check_mode:
                        client.service_remove_host(name, dict(host=del_hosts))
            else:
                changed = True
                if not module.check_mode:
                    client.service_del(name)

    return changed, ipa_service


def main():
    module = AnsibleModule(
        argument_spec=dict(
            krbprincipalname=dict(type='str', required=True, aliases=['name']),
            host=dict(type='list', required=False),
            state=dict(type='str', required=False, default='present',
                       choices=['present', 'absent']),
            ipa_prot=dict(type='str', required=False, default='https',
                          choices=['http', 'https']),
            ipa_host=dict(type='str', required=False,
                          default='ipa.example.com'),
            ipa_port=dict(type='int', required=False, default=443),
            ipa_user=dict(type='str', required=False, default='admin'),
            ipa_pass=dict(type='str', required=True, no_log=True),
            validate_certs=dict(type='bool', required=False, default=True),
        ),
        supports_check_mode=True,
    )

    client = ServiceIPAClient(module=module,
                              host=module.params['ipa_host'],
                              port=module.params['ipa_port'],
                              protocol=module.params['ipa_prot'])

    try:
        client.login(username=module.params['ipa_user'],
                     password=module.params['ipa_pass'])
        changed, service = ensure(module, client)
        module.exit_json(changed=changed, service=service)
    except Exception:
        e = get_exception()
        module.fail_json(msg=str(e))


if __name__ == '__main__':
    main()
