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
    def __init__(self, curr, change, method_map, method_trans):
        self.method_map = method_map
        self.method_trans = method_trans

        # Clean up current and change object params
        self.curr = self.clean(curr, translate=True)
        self.change = self.clean(change)

    def clean(self, dirty, translate=False):
        c = {}
        for key, val in dirty.items():
            if translate:
                key = self.method_trans.get(key, None)
            if key not in self.method_map:
                continue # common arg
            if translate:
                if self.method_map[key]['value_filter'] is not None:
                    val = self.method_map[key]['value_filter'](val)
            if val is None:
                continue
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
    # Diff class:  may be overridden
    diff_class = IPAObjectDiff

    # Parameters for finding existing objects:  must be overridden
    #
    # - search keys for existing objects
    # find_keys = ['subject', 'cacn']
    find_keys = []
    # - additional args to add to search
    # extra_find_args = dict(exactly=True)
    extra_find_args = dict()
    # - for list results, a function to select relevant results
    # find_filter = lambda x: [...]
    find_filter = None

    # Parameters for adding and modifying objects:  must be overridden
    # 
    # - name param (positional) for add/mod operations
    add_or_mod_key = None

    # Parameters for removing objects:  must be overridden
    # 
    # - name param (positional) for rem operations
    rem_name = None
    # - other keyword params for rem operations
    rem_keys = []

    # Map method names in base object:  may be overridden
    methods = dict(
        add = None,
        rem = None,
        mod = None,
        find = None,
        show = None,
        enable = None,
        disable = None,
        )

    # Keyword args:  must be overridden
    # kw_args = dict(
    #     description = dict(
    #         type='str', required=False),
    # )
    kw_args = dict()


    def __init__(self):
        # Process module parameters
        self.init_standard_params()
        self.init_kw_args()

        # Init module object
        self.init_module()

    def init_standard_params(self):
        self.argument_spec = dict(
            state=dict(
                type='str', required=False, default='present',
                choices=(['present', 'absent']
                         + (['exact'] if 'mod' in self.methods else [])
                         + (['enabled', 'disabled'] if 'enable' in self.methods
                            else []))),
            ipa_prot=dict(
                type='str', required=False, default='https',
                choices=['http', 'https']),
            ipa_host=dict(
                type='str', required=False,
                default='ipa.example.com'),
            ipa_port=dict(
                type='int', required=False, default=443),
            ipa_user=dict(
                type='str', required=False, default='admin'),
            ipa_pass=dict(
                type='str', required=True, no_log=True),
            validate_certs=dict(
                type='bool', required=False, default=True),
        )

    def init_kw_args(self):
        self.method_map = {}
        self.method_trans = {}
        for name, spec in self.kw_args.items():
            self.method_map[name] = dict(
                add = spec.pop('add', self.methods['add']),
                rem = spec.pop('rem', self.methods['rem']),
                mod = spec.pop('mod', self.methods.get('mod',None)),
                type = spec['type'],
                when = spec.pop('when', ['add', 'rem', 'mod']),
                value_filter = spec.pop('value_filter', None),
            )
            self.argument_spec[name] = spec
            self.method_trans[spec.pop('from_result_attr', name)] = name
                

    def param(self, name, default=None):
        return self.module.params.get(name, default)

    def param_slice_old(self, params):
        res = {}
        for p in params:
            res[p] = self.param(p)
        return res

    def param_slice(self, action_type, skip_name):
        res = {}
        for key, val in self.method_map.items():
            if key != skip_name and action_type in val['when']:
                res[key] = self.param(key)
        return res

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
        self.changed = False
        self.new_obj = {}

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
        self.debug['data_%s' % method] = data
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
                if isinstance(result, list):
                    if item_filter is not None:
                        result = [ i for i in result if item_filter(i) ]
                    self.debug['result_%s' % method] = result
                    return (result[-1] if len(result) > 0 else {})
            self.debug['result_%s' % method] = result
            return result
        return None

    def find(self):
        item = dict(all=True)
        item.update(self.extra_find_args)
        for k in self.find_keys:
            if self.param(k) is not None:
                item[k] = self.param(k)
        self.current_obj = self._post_json(
            method=self.methods['find'], name=None, item=item,
            item_filter=self.find_filter)
        if self.current_obj:
            self.new_obj = self.current_obj

    def add_or_mod(self, action_type, actions):
        if action_type not in self.methods:
            self._fail('Cannot modify existing object')

        self.changed = True
        if self.module.check_mode: return
        
        self.new_obj = self._post_json(
            method=self.methods[action_type],
            name=(actions.pop(self.add_or_mod_key)
                  if self.add_or_mod_key else None),
            item=actions)
        
    def enable(self):
        if self.current_obj['ipaenabledflag']: return

        self.changed = True
        if self.module.check_mode: return

        self.new_obj = self._post_json(
            method=self.methods['enable'],
            name=self.param(self.add_or_mod_key))

    def disable(self):
        if not self.current_obj['ipaenabledflag']: return

        self.changed = True
        if self.module.check_mode: return

        self.new_obj = self._post_json(
            method=self.methods['disable'],
            name=self.param(self.add_or_mod_key))

    def rem(self):
        self.changed = True
        if self.module.check_mode: return

        if self.rem_name is not None:
            # When removing, sometimes the object key is only in the
            # find() results
            name=self.param(self.rem_name) or self.current_obj[self.rem_name]
        else:
            name=None
        self.new_obj = self._post_json(
            method=self.methods['rem'],
            name=name,
            # item=self.param_slice(self.rem_keys))
            item=self.param_slice('rem', self.rem_name))

    def list_mod(self, name, method, action):
        self.changed = True
        if self.module.check_mode: return

        self.new_obj = self._post_json(
            method=method, name=name, item=action)


    def ensure(self):
        self.debug = dict(
            argument_spec = self.argument_spec,
            module_params = self.module.params,
            # method_map = self.method_map,
        )

        # Find any existing objects
        self.find()

        # Create difference object
        self.diff = self.diff_class(
            self.current_obj, self.module.params, self.method_map,
            self.method_trans,
        )
        self.debug['diff_curr'] = self.diff.curr
        self.debug['diff_change'] = self.diff.change

        # Figure out which of add/mod/rem
        if self.state in ('present', 'exact', 'enabled', 'disabled'):
            # Adding items to new object or existing object?
            action_type_scalar = 'mod' if self.current_obj else 'add'

        else: # state == 'absent'
            if self.current_obj:
                if self.diff.has_list_keys():
                    # Existing object and absent list keys requested
                    action_type_scalar = 'mod'
                else:
                    # Existing object and no absent list key
                    # requested: remove whole object
                    self.rem()
                    return self.changed, self.new_obj
            else:
                # Object is already absent; do nothing
                return self.changed, self.new_obj

        # Compute list of items to modify/add/delete
        actions_scalar, actions_add, actions_rem = self.diff.state(
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

        # Scalars first; they may bring base object into existence
        if actions_scalar:
            self.add_or_mod(
                action_type_scalar, actions_scalar)

        # Enabled/disabled
        if self.state == 'enabled':
            self.enable()
        if self.state == 'disabled':
            self.disable()

        # List parameter add/remove actions grouped by method;
        # additions come first, since removals may inadvertently
        # delete object
        for method_type, actions in (('add', actions_add),
                                     ('rem', actions_rem)):
            action_map = {}
            for key, val in actions.items():
                action_map.setdefault(
                    self.method_map[key][method_type], {})[key] = val
            for method, action in action_map.items():
                self.list_mod(
                    name=self.param(self.add_or_mod_key),
                    method=method, action=action)

        return self.changed, self.new_obj

