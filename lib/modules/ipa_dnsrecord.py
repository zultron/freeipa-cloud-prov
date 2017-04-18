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

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.pycompat24 import get_exception
from ansible.module_utils.ipa import IPAClient
# Needed to support overridden _post_json
try:
    import json
except ImportError:
    import simplejson as json
from ansible.module_utils.six import PY3
from ansible.module_utils.urls import fetch_url
from ansible.module_utils._text import to_bytes, to_text


class Diff(object):
    """Compute ansible present, exact, absent state changes for items that
    are dicts of lists
    """
    record_keys = ['arecord', 'ptrrecord', 'srvrecord', 'txtrecord']

    def __init__(self, curr, change, record_keys, fill_empty_change=False):
        self.curr_orig = curr
        self.curr, nras = self.clean(curr, return_nras=True)
        for key, val in nras.items():
            setattr(self, key, val)

        self.change_orig = change
        self.change = self.clean(change)

        # Keys to operate on in result
        self.record_keys = record_keys

        # Special case: if change is empty, set it to curr
        if not self.change and fill_empty_change:
            self.change = self.curr

    def clean(self, dirty, return_nras=False):
        c = {}
        non_record_attrs = {}
        for key, val in dirty.items():
            if val is None:
                continue
            elif key in self.record_keys:
                c[key] = [val,] if isinstance(val, basestring) else val
            else:
                non_record_attrs[key] = val
        return (c, non_record_attrs) if return_nras else c

    def op(self, a, b, op):
        res = {}
        for key in set(a) | set(b):
            # => res_val = a[key] <op> b[key]
            res_val = list(getattr(set(a.get(key, [])), op)(b.get(key, [])))
            if res_val: res[key] = res_val
        return res

    def difference(self, a, b):
        return self.op(a, b, 'difference')

    def intersection(self, a, b):
        return self.op(a, b, 'intersection')

    def union(self, a, b):
        return self.op(a, b, 'union')

    def exact(self):
        return (
            self.difference(self.change, self.curr) or None, # records to add
            self.difference(self.curr, self.change) or None, # records to del
        )

    def present(self):
        return (
            self.difference(self.change, self.curr) or None, # records to add
            None,                                            # records to del
        )

    def absent(self):
        return (
            None,                                              # records to add
            self.intersection(self.change, self.curr) or None, # records to del
        )

class DNSRecordIPAClient(IPAClient):
    def _post_json(self, method, zone, name=None, item=None):
        if item is None:
            item = {}
        url = '%s/session/json' % self.get_base_url()
        if name is not None:
            params1 = [zone, dict(__dns_name__=name)]
        else:
            params1 = [zone]
        data = {'method': method,
                'params': [params1, item]}
        try:
            resp, info = fetch_url(
                module=self.module, url=url,
                data=to_bytes(json.dumps(data)), headers=self.headers)
            status_code = info['status']
            if status_code not in [200, 201, 204]:
                self._fail(method, info['msg'])
        except Exception:
            e = get_exception()
            self._fail('post %s' % method, str(e))

        if PY3:
            charset = resp.headers.get_content_charset('latin-1')
        else:
            response_charset = resp.headers.getparam('charset')
            if response_charset:
                charset = response_charset
            else:
                charset = 'latin-1'
        resp = json.loads(
            to_text(resp.read(), encoding=charset), encoding=charset)
        err = resp.get('error')
        if err is not None:
            self._fail('repsonse %s' % method, err)

        if 'result' in resp:
            result = resp.get('result')
            if 'result' in result:
                result = result.get('result')
                if isinstance(result, list):
                    if len(result) > 0:
                        return result[0]
                    else:
                        return {}
            return result
        return None

    def __init__(self, module, host, port, protocol):
        super(DNSRecordIPAClient, self).__init__(module, host, port, protocol)

    def dnsrecord_find(self, name, zone):
        if name == '@':
            return self._post_json(method='dnsrecord_find', zone=zone)
            # # Work around '@' record not found in:
            # # ipa -vv dnsrecord-find --all --raw example.com. --name='@'
            # foo = self._post_json(method='dnsrecord_find', zone=zone)
            # from pprint import pformat
            # with open('/tmp/foo.txt', 'a') as f:
            #     f.write('\nreply:\n')
            #     f.write(pformat(foo))
            #     f.write('\n---------------------------\n')

            # m = [ r for r in
            #       self._post_json(method='dnsrecord_find', zone=zone)
            #       if r['idnsname'] == '@']
            # return m[0] if m else {}
        else:
            return self._post_json(method='dnsrecord_find', zone=zone,
                                   item=dict(all=True,
                                             idnsname=dict(__dns_name__=name)))

    def dnsrecord_add(self, name, zone, item):
        return self._post_json(method='dnsrecord_add', zone=zone, name=name,
                               item=item)

    def dnsrecord_mod(self, name, zone, item):
        return self._post_json(method='dnsrecord_mod', zone=zone, name=name,
                               item=item)

    def dnsrecord_del(self, name, zone, item=None):
        if not item:
            item = dict(del_all=True)
        return self._post_json(method='dnsrecord_del', zone=zone, name=name,
                               item=item)

    def dnsrecord_show(self, name, zone):
        return self._post_json(method='dnsrecord_show', zone=zone, name=name)

rr_types = ['arecord', 'ptrrecord', 'srvrecord', 'txtrecord']

def ensure(module, client):
    state = module.params['state']
    name = module.params['name']
    zone = module.params['zone']

    ipa_dnsrecord = client.dnsrecord_find(zone=zone, name=name)

    d = Diff(ipa_dnsrecord, module.params, rr_types,
             fill_empty_change=(state=='absent'))

    to_add, to_del = getattr(d, state)()
    changed = to_add is not None or to_del is not None

    if to_add is not None and not module.check_mode:
        ipa_dnsrecord = client.dnsrecord_add(
            zone=zone, name=name, item=to_add)

    if to_del is not None and not module.check_mode:
        ipa_dnsrecord = client.dnsrecord_del(
            zone=zone, name=name, item=to_del)

    return changed, ipa_dnsrecord


def main():
    argument_spec = dict(
            name=dict(type='str', required=True),
            zone=dict(type='str', required=True),
            state=dict(type='str', required=False, default='present',
                       choices=['present', 'absent', 'exact']),
            ipa_prot=dict(type='str', required=False, default='https',
                          choices=['http', 'https']),
            ipa_host=dict(type='str', required=False,
                          default='ipa.example.com'),
            ipa_port=dict(type='int', required=False, default=443),
            ipa_user=dict(type='str', required=False, default='admin'),
            ipa_pass=dict(type='str', required=True, no_log=True),
            validate_certs=dict(type='bool', required=False, default=True),
        )
    for key in rr_types:
        argument_spec[key] = dict(type='list', required=False)

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    client = DNSRecordIPAClient(module=module,
                                host=module.params['ipa_host'],
                                port=module.params['ipa_port'],
                                protocol=module.params['ipa_prot'])

    try:
        client.login(username=module.params['ipa_user'],
                     password=module.params['ipa_pass'])
        changed, dnsrecord = ensure(module, client)
        module.exit_json(changed=changed, dnsrecord=dnsrecord)
    except Exception:
        e = get_exception()
        module.fail_json(msg=str(e))


if __name__ == '__main__':
    main()
