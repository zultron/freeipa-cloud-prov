ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: ipa_caacl
author: John Morris (@zultron)
short_description: Manage FreeIPA CA ACLs
description:
- Add, delete and modify CA ACLs within IPA server
options:
  cn:
    description: CA ACL name
    required: true
    aliases: ['name']
  description:
    description: Description
    required: false
  user:
    description: List of user members
    required: false
  group:
    description: List of group members
    required: false
  host:
    description: List of target hosts
    required: false
  hostgroup:
    description: List of target hostgroups
    required: false
  service:
    description: List of services
    required: false
  certprofile:
    description: List of certificate profiles
    required: false
  ca:
    description: List of certificate authorities
    required: false
  state:
    description: State to ensure
    required: false
    default: present
    choices: ["present", "absent", "exact", "enabled", "disabled"]
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
# Create LDAP caacl
- ipa_caacl:
    krbprincipalname: ldap/host1.example.com@EXAMPLE.COM
    state: present
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret

# Remove LDAP caacl
- ipa_caacl:
    krbprincipalname: ldap/host1.example.com@EXAMPLE.COM
    state: absent
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret

# Allow host2 to manage host1 LDAP caacl
- ipa_caacl:
    krbprincipalname: ldap/host1.example.com@EXAMPLE.COM
    state: present
    managed_by: [ host2.example.com ]
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret
'''

RETURN = '''
caacl:
  description: caacl as returned by IPA API
  returned: always
  type: dict
'''

from ansible.module_utils.pycompat24 import get_exception
from ansible.module_utils.ipa import EnablableIPAClient

class CAACLIPAClient(EnablableIPAClient):
    name = 'caacl'

    param_keys = set(('cn',))
    enablekey = 'ipaenabledflag'

    # Only description may be modified from the base caacl_mod method
    base_keys = set(['description'])

    # Adding and removing other items from list parameters can't be
    # done in the base caacl_mod method's addattr/delattr arguments,
    # as it can in e.g. dnsrecord objects.
    change_functions = tuple(
        list(EnablableIPAClient.change_functions) +
        ['add_remove_list_items'] )

    kw_args = dict(
        # request key param
        cn =             dict(type='str',  required=True, aliases=['name']),
        # add/mod method param
        description =    dict(type='str',  required=False),
        # enable/disable method param
        ipaenabledflag = dict(type='bool', required=False),
        # add/rem list params
        user =           dict(type='list', required=False),
        group =          dict(type='list', required=False),
        host =           dict(type='list', required=False),
        hostgroup =      dict(type='list', required=False),
        service =        dict(type='list', required=False),
        certprofile =    dict(type='list', required=False),
        ca =             dict(type='list', required=False),
    )

    def munge_response_keys(self, item):
        # Response keys for list items look like 'memberuser_user' and
        # 'memberuser_group'; translate to simply 'user' and 'group'
        for key in item.keys():
            if key.startswith('memberuser_') or \
               key.startswith('memberhost_') or \
               key.startswith('memberservice_') or \
               key.startswith('ipamembercertprofile_') or \
               key.startswith('ipamemberca_'):
                new_key = key.split('_')[1]
                item[new_key] = item.pop(key)
        return item

    def munge_response(self, item):
        item = self.munge_response_keys(item.copy())
        item = super(CAACLIPAClient, self).munge_response(item)
        return item

    def add_remove_list_items(self):
        # caacl user/host/service/etc. list attributes can't be
        # manipulated with addattr/delattr, and need separate requests
        # with separate methods for each

        # Values in 'addattr' will go to caacl_add_*, and 'delattr' to
        # caacl_remove_*
        for from_list, method_op in (('list_add','add'),
                                     ('list_del','remove')):
            # Methods e.g. caacl_add_host have parameters e.g. user
            # and group
            for method_item, attrs in (
                    ('user',('user','group')),
                    ('host',('host','hostgroup')),
                    ('profile',('certprofile',)),
                    ('ca',('ca',)),
                    ('service',('service',))):
                # Construct request item
                item = {}
                for attr in attrs:
                    val = self.diffs[from_list].get(attr,None)
                    if val is not None:
                        item[attr] = sorted(val)

                # If no changes needed, do nothing
                if not item:  continue

                # Mark object changed
                self.changed = True

                # If in check mode, do nothing
                if self.module.check_mode:  continue

                # Construct request
                item['all'] = True
                request = dict(
                    method = 'caacl_%s_%s' % (method_op, method_item),
                    name = self.mod_request_params(),
                    item = item)

                self.requests.append(dict(
                    name = '%s_%s' % (method_op, method_item),
                    request = request ))
        

def main():
    CAACLIPAClient().main()

if __name__ == '__main__':
    main()
