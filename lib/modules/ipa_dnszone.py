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
module: ipa_dnszone
author: John Morris (@zultron)
short_description: Manage FreeIPA DNS zones
description:
- Add, modify and delete DNS zones within IPA server
options:
  idnsname:
    description: DNS zone name
    required: true
    aliases: ['name']
  idnssoarname:
    description: Authoritative nameserver domain name
    required: false
  idnssoamname:
    description: Administrator e-mail address
    required: false
  idnssoaserial:
    description: SOA record serial number
    required: false
  idnssoarefresh:
    description: SOA record refresh time
    required: false
  idnssoaretry:
    description: SOA record retry time
    required: false
  idnssoaexpire:
    description: SOA record expire time
    required: false
  idnssoaminimum:
    description: How long should negative responses be cached
    required: false
  idnsupdatepolicy:
    description: BIND update policy
    required: false
  idnsallowdynupdate:
    description: Allow dynamic updates.
    required: false
  idnsallowquery:
    description: Semicolon separated list of IP addresses or networks
                 which are allowed to issue queries
    required: false
  idnsallowtransfer:
    description: Semicolon separated list of IP addresses or networks
                 which are allowed to transfer the zone
    required: false
  state:
    description: State to ensure
    required: false
    default: present
    choices: ["present", "absent", "enabled", "disabled"]
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
# Ensure example.com is present
- ipa_dnszone:
    idnsname: example.com.
    state: present
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret

# Ensure zapme.example.com is absent
- ipa_dnszone:
    idnsname: zapme.example.com.
    state: absent
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret
'''

RETURN = '''
dnszone:
  description: DNS zone as returned by IPA API
  returned: always
  type: dict
'''

from ansible.module_utils.pycompat24 import get_exception
from ansible.module_utils.ipa import EnablableIPAClient


class DNSZoneIPAClient(EnablableIPAClient):
    name = 'dnszone'

    param_keys = set(['idnsname'])
    enablekey = 'idnszoneactive'

    kw_args = dict(
        # common params
        idnsname = dict(
            type='str', required=True, aliases=['name']),
        idnssoarname = dict(
            type='str', required=False),
        idnssoamname = dict(
            type='str', required=False),
        idnszoneactive = dict(
            type='bool', required=False),
        idnssoaserial = dict(
            type='str', required=False),
        idnssoarefresh = dict(
            type='str', required=False),
        idnssoaretry = dict(
            type='str', required=False),
        idnssoaexpire = dict(
            type='str', required=False),
        idnssoaminimum = dict(
            type='str', required=False),
        idnsallowquery = dict(
            type='str', required=False),
        idnsallowtransfer = dict(
            type='str', required=False),
        idnsallowdynupdate = dict(
            type='bool', required=False),
        idnsupdatepolicy = dict(
            type='str', required=False),
        nsrecord = dict(
            type='list', required=False),
    )

    # Also:
    # - dnszone-add-permission
    # - dnszone-remove-permission


def main():
    DNSZoneIPAClient().main()

if __name__ == '__main__':
    main()
