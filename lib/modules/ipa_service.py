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

from ansible.module_utils.pycompat24 import get_exception
from ansible.module_utils.ipa import IPAClient
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

    param_keys = set(('krbcanonicalname',))

    kw_args = dict(
        krbcanonicalname = dict(
            type='str', required=True, aliases=['name'],
            when=['find'], when_name=['add', 'mod', 'rem']),
        usercertificate = dict(
            type='str', required=False),
        krbprincipalauthind = dict(
            type='str', required=False),

        # The next three booleans are bits broken out of the
        # krbticketflags param; see filter_value() and request_cleanup()
        ipakrbrequirespreauth = dict(
            type='bool', required=False),
        ipakrbokasdelegate = dict(
            type='bool', required=False),
        ipakrboktoauthasdelegate = dict(
            type='bool', required=False),

        # service-add-principal CANONICAL-PRINCIPAL PRINCIPAL...
        krbprincipalname = dict(
            type='list', required=False),

        # The host and create/retrieve_keytab_* params require the DIT
        # base DN (e.g. 'dc=example,dc=com') to reconstruct
        # user/group/host/hostgroup DNs from uid/cn/fqdn/cn ; see
        # filter_value() and request_cleanup(); e.g.:
        #
        # write_keytab_users: admin ->
        # ipaAllowedToPerform;write_keys:
        #     uid=admin,cn=users,cn=accounts,dc=example,dc=com
        #
        # read_keytab_hosts: host1.example.com ->
        # ipaAllowedToPerform;read_keys:
        #     fqdn=host1.example.com,cn=computers,cn=accounts,dc=example,dc=com
        directory_base_dn = dict(
            type='str', required=False, when=[]),

        # managedby attribute value
        host = dict(type='list', required=False),

        # service-allow-create-keytab users/groups/hosts/hostgroups
        # ipaAllowedToPerform;write_keys:
        write_keytab_users = dict(
            type='list', required=False),
        write_keytab_groups = dict(
            type='list', required=False),
        write_keytab_hosts = dict(
            type='list', required=False),
        write_keytab_hostgroups = dict(
            type='list', required=False),

        # service-allow-read-keytab  users/groups/hosts/hostgroups
        # ipaAllowedToPerform;read_keys:  as above
        read_keytab_users = dict(
            type='list', required=False),
        read_keytab_groups = dict(
            type='list', required=False),
        read_keytab_hosts = dict(
            type='list', required=False),
        read_keytab_hostgroups = dict(
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
        # Duplicate original list
        new_val = list(response.pop('krbprincipalname'))
        # Remove principal canonical name
        new_val.remove(
            self.module.params.get('krbcanonicalname'))
        # Add back
        if new_val:
            response['krbprincipalname'] = new_val

        return response

    def munge_response_ipaallowedtoperform(self, response):
        # Filter account DNs of the right type and return the uid/cn/fqdn
        #
        # uid=admin,cn=users,cn=accounts,dc=example,dc=com
        # cn=editors,cn=groups,cn=accounts,dc=example,dc=com
        # fqdn=host1.example.com,cn=computers,cn=accounts,dc=example,dc=com
        # cn=ipaservers,cn=hostgroups,cn=accounts,dc=example,dc=com

        for key in response:
            if not key.startswith('ipaallowedtoperform;'): continue

            val = response.pop(key)
            op = re.match(r'ipaallowedtoperform;(.*)_keys', key).group(1)
            for v in val:
                m = re.match(
                    r'^(?:fqdn|cn|uid)=([^,]*),cn=([^,]*),cn=accounts,', v)
                if m is not None:
                    name, acct_type = m.groups()
                    if acct_type == 'computers':  acct_type = 'hosts'
                    response.setdefault(
                        '%s_keytab_%s' % (op, acct_type), []).append(name)
        return response

    def munge_response_managedby(self, response):
        # managedby attribute value:
        # fqdn=host1.example.com,cn=computers,cn=accounts,dc=example,dc=com
        if 'managedby' not in response:  return response

        for v in response.pop('managedby'):
            m = re.match( r'fqdn=([^,]*),cn=computers,cn=accounts', v)
            if m is not None:
                response.setdefault('host',[]).append(m.group(1))
        return response

    # def munge_response_krbticketflags(self, response):
    #     # These are broken out of the krbticketflags param of the reply
    #     if key == 'krbticketflags':
    #         for new_key, bit in (('ipakrbrequirespreauth', 128),
    #                              ('ipakrbokasdelegate', 1048576),
    #                              ('ipakrboktoauthasdelegate', 2097152)):
    #             new_v = bool( val[0] & bit )
    #             if new_v is False and \
    #                self.module.params['state'] in ('absent', 'exact'):
    #                 # ipakrb* : False doesn't make sense in 'absent'
    #                 # and superfluous in 'exact'
    #                 continue
    #             item[new_key] = [new_v]
    #         return True

    def munge_response(self, response):
        item = super(ServiceIPAClient, self).munge_response(response)

        item = self.munge_response_usercertificate(item)
        item = self.munge_response_krbprincipalname(item)
        item = self.munge_response_ipaallowedtoperform(item)
        item = self.munge_response_managedby(item)
        # item = self.munge_response_krbticketflags(item)
        return item


    def request_cleanup(self, request):

        # Allow krbticketflags and ipaAllowedToPerform;read/write_keys
        # request parameters to be composed from multiple other params
        # that are simpler to deal with in a task spec

        # krbticketflags:
        # Don't add this to the request unless there was a change
        have_krbticketflags = False
        ktf_old = krbticketflags = self.found_obj.get('krbticketflags',[0])[0]
        for req_op, is_del in ((request['item']['setattr'], False),
                               (request['item']['delattr'], True)):
            for key, mult in (('ipakrbrequirespreauth', 128),
                              ('ipakrbokasdelegate', 1048576),
                              ('ipakrboktoauthasdelegate', 2097152)):
                if key in req_op:
                    val = req_op.pop(key)[0]
                    if not val: complement = not is_del
                    else: complement = is_del
                    if is_del and val is False:
                        # Deleting 'ipakrb*: False' doesn't make
                        # sense, since the bit is still there
                        if self.module.params['state'] == 'absent' and not val:
                            # state = absent:  call this an error
                            self._fail(key, 'False value when state=absent')
                        else:
                            pass # otherwise just ignore
                    elif complement:
                        krbticketflags &= ~(mult)
                    else:
                        krbticketflags |= (mult)
                    have_krbticketflags = True
        if have_krbticketflags and krbticketflags != ktf_old:
            request['item']['setattr']['krbticketflags'] = [krbticketflags]
            request['item']['delattr'].pop('krbticketflags',None)

        # ipaAllowedToPerform;(read|write)_keys:
        directory_base_dn = self.module.params.get('directory_base_dn',None)
        dn_pat = '%s=%s,cn=%s,cn=accounts,%s'
        type_map = dict(users='uid', groups='cn', hosts='fqdn', hostgroups='cn')
        for thing in ('users', 'groups', 'hosts', 'hostgroups'):
            for perm in ('read', 'write'):
                key = '%s_keytab_%s' % (perm, thing)
                thing_trans = 'computers' if thing == 'hosts' else thing
                for req_op in (request['item']['addattr'],
                               request['item']['delattr']):
                    if key not in req_op: continue
                    # directory_base_dn must be defined
                    if directory_base_dn is None:
                        self._fail(key, 'directory_base_dn param undefined')
                    # Patch values into ipaallowedtoperform;read/write_keys
                    dest_key = 'ipaallowedtoperform;%s_keys'%perm
                    for val in req_op.pop(key):
                        req_op.setdefault(dest_key,[]).append(
                            dn_pat % (type_map[thing], val, thing_trans,
                                      directory_base_dn))

        # host -> managedby:
        for act_key, acts in request['item'].items():
            for host in acts.pop('host',[]):
                if 'directory_base_dn' not in self.module.params:
                    self._fail('host', 'Must specify directory_base_dn with host')
                    break
                acts.setdefault('managedby',[]).append(
                    'fqdn=%s,cn=computers,cn=accounts,%s' %
                    (host, self.module.params['directory_base_dn']))

def main():
    client = ServiceIPAClient().main()


if __name__ == '__main__':
    main()
