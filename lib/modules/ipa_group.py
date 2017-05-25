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
module: ipa_group
author: Thomas Krahn (@Nosmoht)
short_description: Manage FreeIPA group
description:
- Add, modify and delete group within IPA server
options:
  cn:
    description:
    - Canonical name.
    - Can not be changed as it is the unique identifier.
    required: true
    aliases: ['name']
  external:
    description:
    - Allow adding external non-IPA members from trusted domains.
    required: false
  gidnumber:
    description:
    - GID (use this option to set it manually).
    required: false
  group:
    description:
    - List of group names assigned to this group.
    - If an empty list is passed all groups will be removed from this group.
    - If option is omitted assigned groups will not be checked or changed.
    - Groups that are already assigned but not passed will be removed.
  nonposix:
    description:
    - Create as a non-POSIX group.
    required: false
  user:
    description:
    - List of user names assigned to this group.
    - If an empty list is passed all users will be removed from this group.
    - If option is omitted assigned users will not be checked or changed.
    - Users that are already assigned but not passed will be removed.
  state:
    description:
    - State to ensure
    required: false
    default: "present"
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
    - This should only set to C(no) used on personally controlled sites using self-signed certificates.
    required: false
    default: true
version_added: "2.3"
'''

EXAMPLES = '''
# Ensure group is present
- ipa_group:
    name: oinstall
    gidnumber: 54321
    state: present
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret

# Ensure that groups sysops and appops are assigned to ops but no other group
- ipa_group:
    name: ops
    group:
    - sysops
    - appops
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret

# Ensure that users linus and larry are assign to the group, but no other user
- ipa_group:
    name: sysops
    user:
    - linus
    - larry
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret

# Ensure group is absent
- ipa_group:
    name: sysops
    state: absent
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret
'''

RETURN = '''
group:
  description: Group as returned by IPA API
  returned: always
  type: dict
'''

from ansible.module_utils.ipa import IPAClient


class GroupIPAClient(IPAClient):
    name = 'group'

    param_keys = set(['cn'])
    base_keys = set([
        'description', 'gidnumber', 'nonposix', 'external',
    ])
    change_functions = tuple(
        list(IPAClient.change_functions) +
        ['handle_members'] )

    kw_args = dict(
        cn=dict(
            type='str', required=True, aliases=['name']),
        description=dict(
            type='str', required=False),
        gidnumber=dict(
            type='int', required=False, aliases=['gid']),
        nonposix=dict(
            type='bool', required=False),
        external=dict(
            type='bool', required=False),
        member_group=dict(
            type='list', required=False, aliases=['group']),
        member_user=dict(
            type='list', required=False, aliases=['user']),
    )

    def handle_members(self):
        # Use group_add/remove_member method for user/group members

        for from_list, method in (
                ('list_add', 'group_add_member'),
                ('list_del', 'group_remove_member')):
            users = self.diffs[from_list].get('member_user',None)
            groups = self.diffs[from_list].get('member_group',None)

            # If no changes needed, do nothing
            if users is None and groups is None:  continue

            # Mark object changed
            self.changed = True

            # If in check mode, do nothing
            if self.module.check_mode:  continue

            # Construct request
            item = dict( all = True )
            if users is not None:
                item['user'] = users
            if groups is not None:
                item['group'] = groups

            request = dict(
                method = method,
                name = self.mod_request_params(),
                item = item)

            self.requests.append(dict(
                name = method,
                request = request ))



def main():
    client = GroupIPAClient().main()


if __name__ == '__main__':
    main()
