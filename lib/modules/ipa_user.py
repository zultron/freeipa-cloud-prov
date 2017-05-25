#!/usr/bin/python
# -*- coding: utf-8 -*-
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: ipa_user
author: Thomas Krahn (@Nosmoht)
short_description: Manage FreeIPA users
description:
- Add, modify and delete user within IPA server
options:
  displayname:
    description: Display name
    required: false
  givenname:
    description: First name
    required: false
  loginshell:
    description: Login shell
    required: false
  mail:
    description:
    - List of mail addresses assigned to the user.
    - If an empty list is passed all assigned email addresses will be deleted.
    - If None is passed email addresses will not be checked or changed.
    required: false
  password:
    description:
    - Password
    required: false
  sn:
    description: Surname
    required: false
  sshpubkey:
    description:
    - List of public SSH key.
    - If an empty list is passed all assigned public keys will be deleted.
    - If None is passed SSH public keys will not be checked or changed.
    required: false
  state:
    description: State to ensure
    required: false
    default: "present"
    choices: ["present", "absent", "enabled", "disabled"]
  telephonenumber:
    description:
    - List of telephone numbers assigned to the user.
    - If an empty list is passed all assigned telephone numbers will be deleted.
    - If None is passed telephone numbers will not be checked or changed.
    required: false
  title:
    description: Title
    required: false
  uid:
    description: uid of the user
    required: true
    aliases: ["name"]
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
    - This should only set to C(no) used on personally controlled sites using self-signed certificates.
    required: false
    default: true
version_added: "2.3"
'''

EXAMPLES = '''
# Ensure pinky is present
- ipa_user:
    name: pinky
    state: present
    givenname: Pinky
    sn: Acme
    mail:
    - pinky@acme.com
    telephonenumber:
    - '+555123456'
    sshpubkeyfp:
    - ssh-rsa ....
    - ssh-dsa ....
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret

# Ensure brain is absent
- ipa_user:
    name: brain
    state: absent
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret
'''

RETURN = '''
user:
  description: User as returned by IPA API
  returned: always
  type: dict
'''

import re

from ansible.module_utils.ipa import EnablableIPAClient

class UserIPAClient(EnablableIPAClient):
    name = 'user'

    change_functions = tuple(
        list(EnablableIPAClient.change_functions) +
        ['handle_cert', 'handle_principal'] )

    param_keys = set(['uid'])
    base_keys = set([
        'givenname', 'sn', 'cn', 'displayname', 'initials', 'homedirectory',
        'gecos', 'loginshell', 'mail', 'password', 'gidnumber',
        'street', 'l', 'st', 'postalcode',
        'telephonenumber', 'mobile', 'pager', 'fax',
        'orgunit', 'title', 'manager', 'carlicense', 'ipasshpubkey',
        'user_auth_type', 'category', 'radius', 'radius_username',
        'departmentnumber', 'employeenumber', 'employeetype',
        'preferredlanguage',
        ])
    enablekey = 'nsaccountlock'
    enablekey_sense_inverted = True

    kw_args = dict(
        uid=dict(
            type='str', required=True),
        # Base add/mod keys
        givenname=dict(
            type='str', required=False, aliases=['first']),
        sn=dict(
            type='str', required=False, aliases=['last']),
        cn=dict(
            type='str', required=False),
        displayname=dict(
            type='str', required=False),
        initials=dict(
            type='str', required=False),
        homedirectory=dict(
            type='str', required=False, aliases=['homedir']),
        gecos=dict(
            type='str', required=False),
        loginshell=dict(
            type='str', required=False, aliases=['shell']),
        mail=dict(
            type='list', required=False, aliases=['email']),
        password=dict(
            type='str', required=False, no_log=True),
        gidnumber=dict(
            type='int', required=False),
        street=dict(
            type='str', required=False),
        l=dict(
            type='str', required=False, aliases=['city']),
        st=dict(
            type='str', required=False),
        postalcode=dict(
            type='str', required=False),
        telephonenumber=dict(
            type='list', required=False, aliases=['phone']),
        mobile=dict(
            type='list', required=False),
        pager=dict(
            type='list', required=False),
        fax=dict(
            type='list', required=False),
        orgunit=dict(
            type='str', required=False),
        title=dict(
            type='str', required=False),
        manager=dict(
            type='str', required=False),
        carlicense=dict(
            type='str', required=False),
        ipasshpubkey=dict(
            type='str', required=False, aliases=['sshpubkey']),
        user_auth_type=dict(
            type='str', required=False, choices=['password', 'radius', 'otp']),
        category=dict(
            type='str', required=False, aliases=['class']),
        radius=dict(
            type='str', required=False),
        radius_username=dict(
            type='str', required=False),
        departmentnumber=dict(
            type='str', required=False),
        employeenumber=dict(
            type='str', required=False),
        employeetype=dict(
            type='str', required=False),
        preferredlanguage=dict(
            type='str', required=False),

        # enable/disable
        nsaccountlock=dict(
            type='bool', default=False),

        # add/remove_cert
        usercertificate=dict(
            type='list', required=False, aliases=['certificate']),

        # add/remove_principal
        krbprincipalname = dict(
            type='list', required=False, aliases=['principal']),
    )

    def munge_response_usercertificate(self, response):
        # Replace dict value with string:
        # from:  'usercertificate': {'__base64__': 'MIIC[...]QLnA='}
        #   to:  'usercertificate': 'MIIC[...]QLnA='
        if 'usercertificate' not in response:  return response

        vs = response.pop('usercertificate')
        certs = response['usercertificate'] = []
        for v in vs:
            if isinstance(v,dict) and '__base64__' in v:
                certs.append(v['__base64__'])
            else:
                certs.append(v)
        return response

    krbprincipal_re = re.compile(r'([^@]*)(@[^@]*)?$')

    def munge_response_krbprincipalname(self, response):
        # krbprincipalname list:  This list of principal aliases may
        # include the principal canonical name.  Aliases specified in
        # this list should avoid touching that value.

        if 'krbprincipalname' not in response:  return response

        # Remove krbcanonicalname from list
        krbcanonicalname = response.get('krbcanonicalname',None)
        if krbcanonicalname is not None and \
           krbcanonicalname in response['krbprincipalname']:
            response['krbprincipalname'].remove(krbcanonicalname)

        # Turn principal foo@EXAMPLE.COM into foo
        for i, princ in enumerate(response['krbprincipalname']):
            m = self.krbprincipal_re.match(princ)
            if m is not None:
                response['krbprincipalname'][i] = m.group(1)

        return response

    def munge_response(self, response):
        response = self.munge_response_usercertificate(response)
        response = self.munge_response_krbprincipalname(response)
        return super(UserIPAClient, self).munge_response(response)

    def handle_cert(self):
        # Use user_add/remove_cert methods for certs
        for from_list, method in (
                ('list_add', 'user_add_cert'),
                ('list_del', 'user_remove_cert')):
            certs = self.diffs[from_list].get('usercertificate',None)

            # If no changes needed, do nothing
            if certs is None:  continue

            # Mark object changed
            self.changed = True

            # If in check mode, do nothing
            if self.module.check_mode:  continue

            # Construct request
            request = dict(
                method = method,
                name = self.mod_request_params(),
                item = dict(
                    all = True,
                    usercertificate = [ {'__base64__': c} for c in certs ]))

            self.requests.append(dict(
                name = method,
                request = request ))

    def handle_principal(self):
        # Use user_add/remove_principal methods for principals
        for from_list, method in (
                ('list_add', 'user_add_principal'),
                ('list_del', 'user_remove_principal')):
            princs = self.diffs[from_list].get('krbprincipalname',None)

            # If no changes needed, do nothing
            if princs is None:  continue

            # Mark object changed
            self.changed = True

            # If in check mode, do nothing
            if self.module.check_mode:  continue

            # Construct request
            request = dict(
                method = method,
                name = self.mod_request_params(extra_vals = [princs]),
                item = dict( all = True ))

            self.requests.append(dict(
                name = method,
                request = request ))

