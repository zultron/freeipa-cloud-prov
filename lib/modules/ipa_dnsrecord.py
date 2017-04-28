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
module: ipa_dnsrecord
author: John Morris (@zultron)
short_description: Manage FreeIPA DNS records
description:
- Add, modify and delete DNS records within IPA server
options:
  name:
    description: DNS record name
    required: true
  zone:
    description: DNS zone name
    required: true
  arecord:
    description: A Record
    required: false
  ptrrecord:
    description: PTR Record
    required: false
  srvrecord:
    description: SRV Record
    required: false
  state:
    description: State to ensure
    required: false
    default: present
    choices: ["present", "absent", "exact"]
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
# Ensure host1.example.com A record is present
- ipa_dnsrecord:
    name: host1
    zone: example.com.
    arecord: 192.168.1.25
    state: present
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret

# Ensure 192.168.1.25 PTR record is absent
- ipa_dnsrecord:
    name: 25
    zone: 1.168.192.in-addr.arpa.
    state: absent
    ipa_host: ipa.example.com
    ipa_user: admin
    ipa_pass: topsecret
'''

RETURN = '''
dnsrecord:
  description: DNS record as returned by IPA API
  returned: always
  type: dict
'''

from ansible.module_utils.pycompat24 import get_exception
from ansible.module_utils.ipa import IPAClient

class DNSRecordIPAClient(IPAClient):
    name = 'dnsrecord'

    methods = dict(
        add = '%s_add',
        rem = '%s_del',
        mod = '%s_mod',
        find = '%s_find',
        show = '%s_show',
        )

    kw_args = dict(
        zone=dict(
            type='str', required=True, aliases=['name'],
            when_name=['add', 'mod','rem','find']),
        idnsname = dict(
            type='str', required=True, when=['find'], req_key='__dns_name__',
            when_name=['add','mod','rem'],),
        arecord = dict(
            type='list', required=False),
        aaaarecord = dict(
            type='list', required=False),
        a6record = dict(
            type='list', required=False),
        afsdbrecord = dict(
            type='list', required=False),
        cnamerecord = dict(
            type='list', required=False),
        certrecord = dict(
            type='list', required=False),
        dlvrecord = dict(
            type='list', required=False),
        dnamerecord = dict(
            type='list', required=False),
        dsrecord = dict(
            type='list', required=False),
        ksrecord = dict(
            type='list', required=False),
        locrecord = dict(
            type='list', required=False),
        mxrecord = dict(
            type='list', required=False),
        naptrrecord = dict(
            type='list', required=False),
        nsrecord = dict(
            type='list', required=False),
        ptrrecord = dict(
            type='list', required=False),
        srvrecord = dict(
            type='list', required=False),
        sshfprecord = dict(
            type='list', required=False),
        tlsarecord = dict(
            type='list', required=False),
        txtrecord = dict(
            type='list', required=False),
    )

def main():
    DNSRecordIPAClient().main()

if __name__ == '__main__':
    main()
