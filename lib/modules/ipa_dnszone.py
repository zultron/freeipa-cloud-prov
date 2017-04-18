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
    choices: ["present", "absent", "disabled"]
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

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.pycompat24 import get_exception
from ansible.module_utils.ipa import IPAClient


class DNSZoneIPAClient(IPAClient):
    def __init__(self, module, host, port, protocol):
        super(DNSZoneIPAClient, self).__init__(module, host, port, protocol)

    def dnszone_find(self, name):
        return self._post_json(method='dnszone_find', name=None,
                               item={'all': True, 'idnsname': name})

    def dnszone_add(self, name, item):
        return self._post_json(method='dnszone_add', name=name, item=item)

    def dnszone_mod(self, name, item):
        return self._post_json(method='dnszone_mod', name=name, item=item)

    def dnszone_del(self, name):
        return self._post_json(method='dnszone_del', name=name)

    def dnszone_disable(self, name):
        return self._post_json(method='dnszone_disable', name=name)

    def dnszone_enable(self, name):
        return self._post_json(method='dnszone_enable', name=name)
    # Also:
    # - dnszone-show
    # - dnszone-add-permission
    # - dnszone-remove-permission


def get_dnszone_dict(idnszoneactive=None, idnssoamname=None,
                     idnssoarname=None, idnssoaserial=None, idnssoarefresh=None,
                     idnssoaretry=None, idnssoaexpire=None, idnssoaminimum=None,
                     idnsallowquery=None, idnsallowtransfer=None,
                     idnsallowdynupdate=None, idnsupdatepolicy=None,
                     nsrecord=None):
    dnszone = {}
    if idnszoneactive is not None:
        dnszone['idnszoneactive'] = idnszoneactive
    if idnssoamname is not None:
        dnszone['idnssoamname'] = idnssoamname
    if idnssoarname is not None:
        dnszone['idnssoarname'] = idnssoarname
    if idnssoaserial is not None:
        dnszone['idnssoaserial'] = idnssoaserial
    if idnssoarefresh is not None:
        dnszone['idnssoarefresh'] = idnssoarefresh
    if idnssoaretry is not None:
        dnszone['idnssoaretry'] = idnssoaretry
    if idnssoaexpire is not None:
        dnszone['idnssoaexpire'] = idnssoaexpire
    if idnssoaminimum is not None:
        dnszone['idnssoaminimum'] = idnssoaminimum
    if idnsallowquery is not None:
        dnszone['idnsallowquery'] = idnsallowquery
    if idnsallowtransfer is not None:
        dnszone['idnsallowtransfer'] = idnsallowtransfer
    if idnsallowdynupdate is not None:
        dnszone['idnsallowdynupdate'] = idnsallowdynupdate
    if idnsupdatepolicy is not None:
        dnszone['idnsupdatepolicy'] = idnsupdatepolicy
    if nsrecord is not None:
        dnszone['nsrecord'] = nsrecord

    return dnszone


def get_dnszone_diff(client, ipa_dnszone, module_dnszone):
    return client.get_diff(ipa_data=ipa_dnszone, module_data=module_dnszone)


def ensure(module, client):
    state = module.params['state']
    name = module.params['idnsname']

    module_dnszone = get_dnszone_dict(
        idnszoneactive=module.params.get('idnszoneactive'),
        idnssoamname=module.params.get('idnssoamname'),
        idnssoarname=module.params.get('idnssoarname'),
        idnssoaserial=module.params.get('idnssoaserial'),
        idnssoarefresh=module.params.get('idnssoarefresh'),
        idnssoaretry=module.params.get('idnssoaretry'),
        idnssoaexpire=module.params.get('idnssoaexpire'),
        idnssoaminimum=module.params.get('idnssoaminimum'),
        idnsallowquery=module.params.get('idnsallowquery'),
        idnsallowtransfer=module.params.get('idnsallowtransfer'),
        idnsallowdynupdate=module.params.get('idnsallowdynupdate'),
        idnsupdatepolicy=module.params.get('idnsupdatepolicy'),
        nsrecord=module.params.get('nsrecord'),
    )

    ipa_dnszone = client.dnszone_find(name=name)

    changed = False
    if state in ['present', 'disabled']:
        if not ipa_dnszone:
            changed = True
            if not module.check_mode:
                ipa_dnszone = client.dnszone_add(name=name, item=module_dnszone)
        else:
            diff = get_dnszone_diff(client, ipa_dnszone, module_dnszone)
            if len(diff) > 0:
                changed = True
                if not module.check_mode:
                    ipa_dnszone = client.dnszone_mod(name=name, item=module_dnszone)
    else:
        if ipa_dnszone:
            changed = True
            if not module.check_mode:
                client.dnszone_del(name)

    return changed, ipa_dnszone


def main():
    module = AnsibleModule(
        argument_spec=dict(
            idnsname=dict(type='str', required=True, aliases=['name']),
            idnszoneactive=dict(type='bool', required=False),
            idnssoamname=dict(type='str', required=False),
            idnssoarname=dict(type='str', required=False),
            idnssoaserial=dict(type='str', required=False),
            idnssoarefresh=dict(type='str', required=False),
            idnssoaretry=dict(type='str', required=False),
            idnssoaexpire=dict(type='str', required=False),
            idnssoaminimum=dict(type='str', required=False),
            idnsallowquery=dict(type='str', required=False),
            idnsallowtransfer=dict(type='str', required=False),
            idnsallowdynupdate=dict(type='bool', required=False),
            idnsupdatepolicy=dict(type='str', required=False),
            nsrecord=dict(type='str', required=False),
            state=dict(type='str', required=False, default='present',
                       choices=['present', 'absent', 'disabled']),
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

    client = DNSZoneIPAClient(module=module,
                              host=module.params['ipa_host'],
                              port=module.params['ipa_port'],
                              protocol=module.params['ipa_prot'])

    try:
        client.login(username=module.params['ipa_user'],
                     password=module.params['ipa_pass'])
        changed, dnszone = ensure(module, client)
        module.exit_json(changed=changed, dnszone=dnszone)
    except Exception:
        e = get_exception()
        module.fail_json(msg=str(e))


if __name__ == '__main__':
    main()
