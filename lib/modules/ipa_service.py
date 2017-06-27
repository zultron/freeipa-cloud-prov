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

#from ansible.module_utils.ipa import IPAClient
from ipa import IPAClient
import re


class ServiceIPAClient(IPAClient):
    name = 'service'

    methods = dict(
        add = '{}_add',
        rem = '{}_del',
        mod = '{}_mod',
        find = '{}_find',
        show = '{}_show',
        )

    change_functions = tuple(
        list(IPAClient.change_functions) +
        ['handle_managedby_host', 'handle_allow_keytab'] )

    param_keys = set(('krbcanonicalname',))
    base_keys = set([
        'krbcanonicalname', 'usercertificate', 'krbprincipalauthind',
        'ipakrbrequirespreauth', 'ipakrbokasdelegate',
        'ipakrboktoauthasdelegate', 'krbprincipalname',
        'write_keytab_users', 'write_keytab_groups',
        'write_keytab_hosts', 'write_keytab_hostgroups',
        'read_keytab_users', 'read_keytab_groups',
        'read_keytab_hosts', 'read_keytab_hostgroups',
    ])

    kw_args = dict(
        krbcanonicalname = dict(
            type='str', required=True, aliases=['name']),
        usercertificate = dict(
            type='str', required=False, aliases=['certificate']),
        krbprincipalauthind = dict(
            type='str', required=False, aliases=['auth_ind']),

        ipakrbrequirespreauth = dict(
            type='bool', default=True, aliases=['requires_pre_auth']),
        ipakrbokasdelegate = dict(
            type='bool', default=False, aliases=['ok_as_delegate']),
        ipakrboktoauthasdelegate = dict(
            type='bool', default=False, aliases=['ok_to_auth_as_delegate']),

        # ipa service-add-principal CANONICAL-PRINCIPAL PRINCIPAL...
        krbprincipalname = dict(
            type='list', required=False),

        # ipa service-add-host/service-remove-host
        managedby_host = dict(type='list', required=False),

        # ipa service-(dis)allow-create-keytab users/groups/hosts/hostgroups
        ipaallowedtoperform_write_keys_user = dict(
            type='list', required=False),
        ipaallowedtoperform_write_keys_group = dict(
            type='list', required=False),
        ipaallowedtoperform_write_keys_host = dict(
            type='list', required=False),
        ipaallowedtoperform_write_keys_hostgroup = dict(
            type='list', required=False),

        # ipa service-(dis)allow-read-keytab  users/groups/hosts/hostgroups
        ipaallowedtoperform_read_keys_user = dict(
            type='list', required=False),
        ipaallowedtoperform_read_keys_group = dict(
            type='list', required=False),
        ipaallowedtoperform_read_keys_host = dict(
            type='list', required=False),
        ipaallowedtoperform_read_keys_hostgroup = dict(
            type='list', required=False),
    )

    def munge_response_usercertificate(self, response):
        # Replace dict value with string:
        # from:  'usercertificate': {'__base64__': 'MIIC[...]QLnA='}
        #   to:  'usercertificate': 'MIIC[...]QLnA='
        if 'usercertificate' not in response:  return response

        v = response.pop('usercertificate')
        if isinstance(v,dict) and '__base64__' in v:
            response['usercertificate'] = v['__base64__']
        else:
            response['usercertificate'] = v
        return response

    def munge_response_krbprincipalname(self, response):
        # krbprincipalname list:  This list of principal aliases
        # always includes the principal canonical name.  Aliases
        # specified in this list should avoid touching that value.

        if 'krbprincipalname' not in response:  return response
        # Pop response attribute, copy and remove principal canonical name
        new_val = list(response.pop('krbprincipalname'))
        new_val.remove(
            self.module.params.get('krbcanonicalname'))
        # If anything left, add back
        if new_val:
            response['krbprincipalname'] = new_val

        return response

    def munge_response(self, response):
        item = super(ServiceIPAClient, self).munge_response(response)

        item = self.munge_response_usercertificate(item)
        item = self.munge_response_krbprincipalname(item)
        return item

    def handle_managedby_host(self):
        # service_add_host/service_remove_host methods
        for from_list, method in (
                ('list_add', 'service_add_host'),
                ('list_del', 'service_remove_host')):
            hosts = self.diffs[from_list].get('managedby_host',None)

            # If no changes in check mode, do nothing
            if (not hosts) or self.module.check_mode:  continue

            # Construct and queue request
            self.requests.append(dict(
                name = method,
                request = dict(
                    method = method,
                    name = self.mod_request_params(),
                    item = dict( all = True,
                                 host = hosts ),
                )))

    def handle_allow_keytab(self):
        # service_add_host/service_remove_host methods
        for from_list, method, r_w in (
                ('list_add', 'service_allow_create_keytab', 'write'),
                ('list_del', 'service_disallow_create_keytab', 'write'),
                ('list_add', 'service_allow_retrieve_keytab', 'read'),
                ('list_del', 'service_disallow_retrieve_keytab', 'read')):
            item = dict()
            for objtype in ('user','group','host','hostgroup'):
                attr_name = 'ipaallowedtoperform_%s_keys_%s' % (r_w, objtype)
                attr_val = self.diffs[from_list].get(attr_name, None)

                # If no changes needed, do nothing
                if attr_val is None:  continue

                item[objtype] = attr_val

            # If no changes in check mode, do nothing
            if (not item) or self.module.check_mode:  continue

            # Construct and queue request
            item['all'] = True
            self.requests.append(dict(
                name = method,
                request = dict(
                    method = method,
                    name = self.mod_request_params(),
                    item = item,
                )))


def main():
    client = ServiceIPAClient().main()


if __name__ == '__main__':
    main()
