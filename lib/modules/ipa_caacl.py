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
# from ansible.module_utils.ipa import IPAClient
from ipa import IPAClient

class CAACLClient(IPAClient):

    name = 'caacl'

    # Parameters for adding and modifying objects
    add_or_mod_name = 'cn'
    # Parameters for removing objects
    rem_name = 'cn'


    kw_args = dict(
        # common params
        cn = dict(
            type='str', required=True, aliases=['name'],
            when_name=['add', 'mod', 'rem']),
        # add/mod params
        description = dict(
            type='str', required=False, when=['add', 'mod'],
            value_filter=lambda x: x[0] if x else None),
        # add/rem list params
        user = dict(
            type='list', required=False,
            ipa_name='memberuser_user',
            add='caacl_add_user', rem='caacl_remove_user'),
        group = dict(
            type='list', required=False,
            ipa_name='memberuser_group',
            add='caacl_add_user', rem='caacl_remove_user'),
        host = dict(
            type='list', required=False,
            ipa_name='memberhost_host',
            add='caacl_add_host', rem='caacl_remove_host'),
        hostgroup = dict(
            type='list', required=False,
            ipa_name='memberhost_hostgroup',
            add='caacl_add_host', rem='caacl_remove_host'),
        service = dict(
            type='list', required=False,
            ipa_name='memberservice_service',
            add='caacl_add_service', rem='caacl_remove_service'),
        certprofile = dict(
            type='list', required=False,
            ipa_name='ipamembercertprofile_certprofile',
            add='caacl_add_profile', rem='caacl_remove_profile'),
        ca = dict(
            type='list', required=False,
            ipa_name='ipamemberca_ca',
            add='caacl_add_ca', rem='caacl_remove_ca'),
    )


def main():
    client = CAACLClient()
    client.debug['init_kw_args'] = CAACLClient.kw_args.copy()

    client.login()
    changed, obj = client.ensure()
    result = {
        'changed': changed,
        client.name: obj,
        # 'debug': client.debug,
    }
    client.module.exit_json(**result)
    # try:
    #     client.login()
    #     changed, obj = client.ensure()
    #     result = {
    #         'changed': changed,
    #         client.name: obj,
    #         'debug': client.debug,
    #     }
    #     client.module.exit_json(**result)
    # except Exception:
    #     e = get_exception()
    #     client.module.fail_json(msg=str(e), debug=client.debug)

if __name__ == '__main__':
    main()
