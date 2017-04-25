# -*- coding: utf-8 -*-
# This code is part of Ansible, but is an independent component.
# This particular file snippet, and this file snippet only, is BSD licensed.
# Modules you write using this snippet, which is embedded dynamically by Ansible
# still belong to the author of the module, and may assign their own license
# to the complete work.
#
# Copyright (c) 2016 Thomas Krahn (@Nosmoht)
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright notice,
#      this list of conditions and the following disclaimer in the documentation
#      and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

try:
    import json
except ImportError:
    import simplejson as json

from ansible.module_utils._text import to_bytes, to_text
from ansible.module_utils.pycompat24 import get_exception
from ansible.module_utils.six import PY3
from ansible.module_utils.six.moves.urllib.parse import quote
from ansible.module_utils.urls import fetch_url
from ansible.module_utils.basic import AnsibleModule


class IPAObjectDiff(object):
    """Compute ansible present, exact, absent state changes for items that
    are dicts of lists
    """
    def __init__(self, curr, change, method_map, method_trans, method_filt):
        self.method_map = method_map
        self.method_trans = method_trans
        self.method_filt = method_filt

        # Clean up current and change object params
        self.curr = self.clean(curr, translate=True)
        self.change = self.clean(change)

    def clean(self, dirty, translate=False):
        c = {}
        for key, val in dirty.items():
            if translate:
                key = self.method_trans.get(key, None)
                val = self.method_filt.get(key, lambda x: x)(val)
            if val is None:
                continue
            elif key not in self.method_map:
                continue # common arg
            elif self.method_map[key]['type'] == 'list':
                # Allow single list args to be provided as strings
                c[key] = [val,] if isinstance(val, basestring) else val
            else:
                c[key] = val
        return c

    def op(self, a, b, op, action_type):
        keys = set(self.method_map.keys())
        res = {}
        for key in set(a) | set(b):
            if key not in keys: continue
            if self.method_map[key]['type'] != 'list': continue
            if action_type not in self.method_map[key]['when']: continue
            # => res_val = a[key] <op> b[key]
            res_val = list(getattr(set(a.get(key, [])), op)(b.get(key, [])))
            if res_val: res[key] = res_val
        return res

    def difference(self, a, b, action_type):
        return self.op(a, b, 'difference', action_type)

    def intersection(self, a, b, action_type):
        return self.op(a, b, 'intersection', action_type)

    def mods(self, action_type):
        keys = set(self.method_map.keys())
        res = {}
        for key in self.change:
            # Ignore junk keys
            if key not in keys:  continue
            # List attributes are handled in exact/present/absent methods
            if self.method_map[key]['type'] == 'list': continue
            # Observe attribute restrictions for add/mod/rem action types
            if action_type not in self.method_map[key]['when']: continue
            # Only add keys that don't match requested state
            if self.change[key] != self.curr.get(key, None): # FIXME are these ever lists?
                res[key] = self.change[key]
        return res

    def exact(self, action_type):
        return (
            self.mods(action_type),                 # scalar params
            self.difference(self.change, self.curr,
                            action_type),           # records to add
            self.difference(self.curr, self.change,
                            action_type),           # records to del
        )

    def present(self, action_type):
        return (
            self.mods(action_type),                 # scalar params
            self.difference(self.change, self.curr,
                            action_type),           # records to add
            {},                                     # records to del
        )

    def absent(self, action_type):
        return (
            {},                                     # scalar params
            {},                                     # records to add
            self.intersection(self.change, self.curr,
                              action_type),         # records to del
        )

    def enabled(self, action_type):
        return self.present(action_type)

    def disabled(self, action_type):
        return self.present(action_type)

    def state(self, state, action_type):
        return getattr(self, state)(action_type)

    def list_keys(self):
        return [ k for k in self.change.keys()
                 if self.method_map[k]['type'] == 'list'
                 and self.change[k] is not None ]

    def has_list_keys(self):
        # Presence of lists in change set affects processing
        return len(self.list_keys()) > 0

    def scalar_keys(self):
        return [ k for k in self.change.keys()
                 if self.method_map[k]['type'] != 'list' ]

    def has_scalar_keys(self):
        # Presence of scalars in change set affects processing
        return len(self.scalar_keys() > 0)

class IPAClient(object):
    # Allow diff class to be overridden
    diff_class = IPAObjectDiff

    # Override:  Map method names in base object
    methods = dict(
        add = None,
        rem = None,
        mod = None,
        find = None,
        show = None,
        enable = None,
        disable = None,
        )

    # Override:  Positional args
    pos_args = [
        dict(name = 'arg1',
             spec = dict(type='str', required=True, aliases=['name'])),
    ]
    
    # Override: Keyword args
    kw_args = dict(
        description = dict(
            type='str', required=False),
    )

    extra_find_args = dict()
    find_filter = None

    def __init__(self):
        # Process module parameters
        self.init_standard_params()
        self.init_pos_args()
        self.init_kw_args()

        # Init module object
        self.init_module()

    def init_standard_params(self):
        self.argument_spec = dict(
            state=dict(type='str', required=False, default='present',
                       choices=['present', 'absent', 'exact'] +
                       (['enabled', 'disabled'] if 'enable' in self.methods
                        else [])),
            ipa_prot=dict(type='str', required=False, default='https',
                          choices=['http', 'https']),
            ipa_host=dict(type='str', required=False,
                          default='ipa.example.com'),
            ipa_port=dict(type='int', required=False, default=443),
            ipa_user=dict(type='str', required=False, default='admin'),
            ipa_pass=dict(type='str', required=True, no_log=True),
            validate_certs=dict(type='bool', required=False, default=True),
        )

    def init_pos_args(self):
        self.scalar_method_map = {}
        for a in self.pos_args:
            name = a['name']
            self.argument_spec[name] = a['spec']
            self.scalar_method_map[name] = dict(
                add = self.methods['add'],
                rem = self.methods['rem'],
                mod = self.methods.get('mod',None),
                when = a.pop('when', ['add', 'rem', 'mod']),
            )

    def init_kw_args(self):
        self.method_map = {}
        self.method_trans = {}
        self.method_filt = {}
        for name, spec in self.kw_args.items():
            self.argument_spec[name] = spec
            self.method_map[name] = dict(
                add = spec.pop('add', self.methods['add']),
                rem = spec.pop('rem', self.methods['rem']),
                mod = spec.pop('mod', self.methods.get('mod',None)),
                type = spec['type'],
                when = spec.pop('when', ['add', 'rem', 'mod']),
            )
            self.method_trans[spec.pop('ipa_name', name)] = name
            self.method_filt[name] = spec.pop('filt', lambda x: x)
                

    def param(self, name, default=None):
        return self.module.params.get(name, default)

    def init_module(self):
        self.module = AnsibleModule(
            argument_spec=self.argument_spec,
            supports_check_mode=True,
        )

        self.host = self.param('ipa_host')
        self.port = self.param('ipa_port')
        self.protocol = self.param('ipa_prot')
        self.username = self.param('ipa_user')
        self.password = self.param('ipa_pass')
        self.headers = None
        self.state = self.param('state')

    def get_base_url(self):
        return '%s://%s/ipa' % (self.protocol, self.host)

    def get_json_url(self):
        return '%s/session/json' % self.get_base_url()

    def login(self):
        url = '%s/session/login_password' % self.get_base_url()
        data = 'user=%s&password=%s' % \
               (quote(self.username, safe=''), quote(self.password, safe=''))
        headers = {'referer': self.get_base_url(),
                   'Content-Type': 'application/x-www-form-urlencoded',
                   'Accept': 'text/plain'}
        try:
            resp, info = fetch_url(
                module=self.module, url=url,
                data=to_bytes(data), headers=headers)
            status_code = info['status']
            if status_code not in [200, 201, 204]:
                self._fail('login', info['msg'])

            self.headers = {'referer': self.get_base_url(),
                            'Content-Type': 'application/json',
                            'Accept': 'application/json',
                            'Cookie': resp.info().get('Set-Cookie')}
        except Exception:
            e = get_exception()
            self._fail('login', str(e))

    def _fail(self, msg, e):
        if 'message' in e:
            err_string = e.get('message')
        else:
            err_string = e
        # self.module.fail_json(msg='%s: %s' % (msg, err_string))
        # FIXME
        self.module.fail_json(msg='%s: %s' % (msg, err_string),
                              debug=getattr(self,'debug',None))

    def _post_json(self, method, name, item=None, item_filter=None):
        if item is None:
            item = {}
        url = '%s/session/json' % self.get_base_url()
        data = {'method': method, 'params': [[name], item]}
        self.debug['data'] = data
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
        resp = json.loads(to_text(resp.read(), encoding=charset),
                          encoding=charset)
        err = resp.get('error')
        if err is not None:
            self._fail('response %s' % method, err)

        if 'result' in resp:
            result = resp.get('result')
            if 'result' in result:
                result = result.get('result')
                if isinstance(result, list) and item_filter is not None:
                    result = [ i for i in result if item_filter(i) ]
                if isinstance(result, list):
                    if len(result) > 0:
                        return result[0]
                    else:
                        return {}
            return result
        return None

    def find(self):
        item = dict(all=True)
        item.update(self.extra_find_args)
        for k in self.find_keys:
            if self.param(k) is not None:
                item[k] = self.param(k)
        self.debug['find_data'] = dict(
            method=self.methods['find'], name=None, item=item)
        return self._post_json(
            method=self.methods['find'], name=None, item=item,
            item_filter=self.find_filter)

    def add_or_mod(self, action_type, actions):
        return self._post_json(
            method=self.methods[action_type],
            name=self.param(self.add_or_mod_key),
            item=actions)
        
    def rem(self):
        return self._post_json(
            method=self.methods['rem'], name=self.param(self.rem_key))


    def ensure(self):
        self.debug = dict(
            argument_spec = self.argument_spec,
            module_params = self.module.params,
            method_map = self.method_map,
        )

        self.ipa_obj = self.find()
        self.debug['ipa_obj'] = self.ipa_obj

        d = self.diff_class(
            self.ipa_obj, self.module.params, self.method_map,
            self.method_trans, self.method_filt,
        )
        self.debug['diff_curr'] = d.curr
        self.debug['diff_change'] = d.change

        action_enable = False
        action_disable = False

        # Compute changes
        if self.state in ('present', 'exact', 'enabled', 'disabled'):

            # Adding items to new object or existing object?
            action_type_scalar = 'mod' if self.ipa_obj else 'add'

        else: # state == 'absent'
            if self.ipa_obj:
                if not d.has_list_keys():
                    # No list items supplied
                    if not self.module.check_mode:
                        # Remove existing object
                        return True, self.rem()
                    else:
                        # Or do nothing in check mode
                        return True, self.ipa_obj
                else:
                    # Existing object
                    action_type_scalar = 'mod'
            else:
                # Do nothing with non-existent object
                return False, self.ipa_obj

        # Compute list of items to modify/add/delete
        actions_scalar, actions_add, actions_rem = d.state(
            self.state, action_type_scalar)

        self.debug['actions_scalar'] = actions_scalar
        self.debug['actions_add'] = actions_add
        self.debug['actions_rem'] = actions_rem
        self.debug['action_type_scalar'] = action_type_scalar

        # Compile list of changes; each change is a tuple:
        # (method_name,
        #  { attr1 : [ val1, val2 ],
        #    attr2 : [ val3 ],
        #  })
        changes = []
        changed = False

        # Scalars first; they may bring base object into existence
        if actions_scalar:
            changed = True
            if not self.module.check_mode:
                self.ipa_obj = self.add_or_mod(
                    action_type_scalar, actions_scalar)
                self.debug['add_or_mod'] = self.ipa_obj

        # Enabled/disabled
        if self.state == 'enabled' and not self.ipa_obj['ipaenabledflag']:
            self.ipa_obj = changes.append(dict(
                method=self.methods['enable'],
                name=self.param(self.add_or_mod_key)))
            self.debug['enabled'] = self.ipa_obj
        if self.state == 'disabled' and self.ipa_obj['ipaenabledflag']:
            self.ipa_obj = changes.append(dict(
                method=self.methods['disable'],
                name=self.param(self.add_or_mod_key)))
            self.debug['enabled'] = self.ipa_obj

        # Add list add/remove actions grouped by method; additions come
        # first, since removals may inadvertently delete object
        for method_type, actions in (('add', actions_add),
                                     ('rem', actions_rem)):
            action_map = {}
            for key, val in actions.items():
                action_map.setdefault(
                    self.method_map[key][method_type], {})[key] = val
            for method, action in action_map.items():
                changes.append(dict(
                    method=method,
                    name=self.param(self.add_or_mod_key),
                    item=action))

        self.debug['changes'] = changes

        # Effect changes
        res = {}
        if not self.module.check_mode:
            for c in changes:
                self.ipa_obj = self._post_json(**c)
                res[c['method']] = self.ipa_obj
        changed |= (len(changes) > 0) and (not self.module.check_mode)

        return changed, res[-1] if res else None

