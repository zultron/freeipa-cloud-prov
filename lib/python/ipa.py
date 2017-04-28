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
    def __init__(self, curr, change, method_map, method_trans, action_type):
        self.method_map = method_map
        self.method_trans = method_trans
        self.action_type = action_type

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
            if self.action_type in self.method_map[key]['when_name']:
                continue # used as `name` attr; don't compare
            if translate:
                if self.method_map[key]['value_filter'] is not None:
                    val = self.method_map[key]['value_filter'](val)
            if self.method_map[key]['type'] != 'list' and isinstance(val, list):
                # In some find results, string values are still in lists
                val = val[0] if val else None
            if val is None:
                continue
            elif self.method_map[key]['type'] == 'list':
                # Allow single list args to be provided as strings
                c[key] = [val,] if isinstance(val, basestring) else val
            else:
                c[key] = val
        return c

    def mods(self):
        keys = set(self.method_map.keys())
        res = {}
        for key in self.change:
            # Ignore junk keys
            if key not in keys:  continue
            # List attributes are handled in exact/present/absent methods
            if self.method_map[key]['type'] == 'list': continue
            # Observe attribute restrictions for add/mod/rem action types
            if self.action_type not in self.method_map[key]['when']: continue
            # Only add keys that don't match requested state
            if self.change[key] != self.curr.get(key, None):
                res[key] = self.change[key]
        return res

    def op(self, a, b, op):
        keys = set(self.method_map.keys())
        res = {}
        for key in set(a) | set(b):
            if key not in keys: continue
            if self.method_map[key]['type'] != 'list': continue
            if self.action_type not in self.method_map[key]['when']: continue
            # => res_val = a[key] <op> b[key]
            res_val = list(getattr(set(a.get(key, [])), op)(b.get(key, [])))
            if res_val: res[key] = res_val
        return res

    def exact(self):
        return (
            self.mods(),                                     # scalar params
            self.op(self.change, self.curr, 'difference'),   # records to add
            self.op(self.curr, self.change, 'difference'),   # records to del
        )

    def present(self):
        return (
            self.mods(),                                     # scalar params
            self.op(self.change, self.curr, 'difference'),   # records to add
            {},                                              # records to del
        )

    def absent(self):
        return (
            {},                                              # scalar params
            {},                                              # records to add
            self.op(self.change, self.curr, 'intersection'), # records to del
        )

    def enabled(self):
        return self.present()

    def disabled(self):
        return self.present()

    def state(self, state):
        return getattr(self, state)()

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

    # Object name: must be overridden
    name = 'unnamed'

    # Diff class:  may be overridden
    diff_class = IPAObjectDiff

    # Parameters for finding existing objects:  must be overridden
    #
    # - additional args to add to search
    # extra_find_args = dict(exactly=True)
    extra_find_args = dict()
    # - for list results, a function to select relevant results
    # find_filter = lambda x: [...]
    find_filter = None

    # Map method names in base object:  may be overridden
    # - Pattern will be filled with class `name` attribute
    methods = dict(
        add = '%s_add',
        rem = '%s_del',
        mod = '%s_mod',
        find = '%s_find',
        show = '%s_show',
        enable = '%s_enable',
        disable = '%s_disable',
        )

    # Keyword args:  must be overridden
    # kw_args = dict(
    #     description = dict(
    #         type='str', required=False),
    # )
    kw_args = dict()


    def __init__(self):
        # Process module parameters
        self.init_methods()
        self.init_standard_params()
        self.init_kw_args()

        # Init module object
        self.init_module()

    def init_methods(self):
        self._methods = dict(map(
            lambda x: (x[0],x[1]%self.name),
            self.__class__.methods.items()))

    def init_standard_params(self):
        self.argument_spec = dict(
            state=dict(
                type='str', required=False, default='present',
                choices=(['present', 'absent']
                         + (['exact'] if 'mod' in self._methods else [])
                         + (['enabled', 'disabled'] if 'enable' in self._methods
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
        self.name_map = {}
        self.enablekey = None
        for name, spec in self.kw_args.items():
            spec = spec.copy()
            # if isinstance(spec, basestring):  continue
            self.method_map[name] = dict(
                type = spec['type'],
                when = (spec.pop('when', ['add', 'mod']) \
                        if 'add' not in spec else []),
                when_name = spec.pop('when_name', []),
                value_filter = spec.pop('value_filter', None),
                # For list args
                add = spec.pop('add', self._methods['add']),
                rem = spec.pop('rem', self._methods['rem']),
                mod = spec.pop('mod', self._methods.get('mod',None)),
            )
            for k in self.method_map[name]['when_name']:
                self.name_map[k] = name
            if spec.pop('enablekey',False):
                self.enablekey = name
            self.argument_spec[name] = spec
            self.method_trans[spec.pop('from_result_attr', name)] = name
                

    def param(self, name, default=None):
        return self.module.params.get(name, default)

    def param_slice_old(self, params):
        res = {}
        for p in params:
            res[p] = self.param(p)
        return res

    def param_slice(self):
        res = {}
        name = None
        for key, val in self.method_map.items():
            # Special handling for request 'name' positional parameter
            if key == self.name_map.get(self.action_type, None):
                name = self.param(key)
                continue
            # Skip keys not applicable to current action type
            if self.action_type not in val['when']:  continue
            # Skip keys with no values
            if self.param(key) is None:  continue
            # Add key:val to slice
            res[key] = self.param(key)
        return res, name

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
        self.module.fail_json(msg='%s: %s' % (msg, err_string))

    def _post_json(self, method, name, item=None, item_filter=None):
        if item is None:
            item = {}
        url = '%s/session/json' % self.get_base_url()
        data = {'method': method, 'params': [[name], item]}
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
                    return (result[-1] if len(result) > 0 else {})
            return result
        return None

    def name_attr(self):
        return ([ k for k,v in self.kw_args.items() \
                  if self.action_type in v.get('when_name',[])] + [None])[0]

    def name_value(self):
        return self.param(self.name_attr())

    def find(self):
        assert self.action_type == 'find'
        item = dict(all=True)
        params, name = self.param_slice()
        item.update(params)
        item.update(self.extra_find_args)
        self.current_obj = self._post_json(
            method=self._methods['find'], name=name,
            item=item,
            item_filter=self.find_filter)
        if self.current_obj:
            self.new_obj = self.current_obj

    def add_or_mod(self, actions):
        assert self.action_type in ('add', 'mod')
        if self.action_type not in self._methods:
            self._fail('Cannot %s object' % self.action_type)

        self.changed = True
        if self.module.check_mode: return
        
        params, name = self.param_slice()

        self.new_obj = self._post_json(
            method=self._methods[self.action_type],
            name=name,
            # FIXME this should be params?
            item=actions)
        
    @property
    def is_enabled(self):
        enabled = self.current_obj[self.enablekey]
        if isinstance(enabled, list):
            enabled = enabled[0] if enabled else False
        if isinstance(enabled, basestring):
            enabled = (enabled.lower() == 'true')
        return enabled

    @property
    def request_name_value(self):
        return self.param(self.name_map[self.action_type])

    def enable(self):
        if self.is_enabled: return

        self.changed = True
        if self.module.check_mode: return

        self.new_obj = self._post_json(
            method=self._methods['enable'],
            name=self.request_name_value)

    def disable(self):
        if not self.is_enabled: return

        self.changed = True
        if self.module.check_mode: return

        self.new_obj = self._post_json(
            method=self._methods['disable'],
            name=self.request_name_value)

    @property
    def action_type(self):
        if not hasattr(self, 'current_obj'):
            # Haven't searched yet
            return 'find'

        if self.state == 'absent':
            # Remove either list values or the whole object
            return 'rem'

        # In 'present', 'exact', 'disable', 'enable' states...
        if self.current_obj:
            # ...modify existing object...
            return 'mod'
        else:
            # ...or add absent object
            return 'add'

    def rem(self):
        self.changed = True
        if self.module.check_mode: return

        params, name = self.param_slice()
        self.new_obj = self._post_json(
            method=self._methods['rem'],
            name=name,
            item=params)

    def list_mod(self, name, method, action):
        self.changed = True
        if self.module.check_mode: return

        self.new_obj = self._post_json(
            method=method, name=name, item=action)


    def ensure(self):

        # Find any existing objects
        self.find()

        self.diff = self.diff_class(
            self.current_obj, self.module.params, self.method_map,
            self.method_trans, self.action_type,
        )

        if self.state == 'absent':
            if not self.current_obj:
                # Object is already absent; do nothing
                return self.changed, self.new_obj

            # Existing object:
            if not self.diff.has_list_keys():
                # No list keys in request:  remove whole object
                self.rem()
                return self.changed, self.new_obj
            # Otherwise, 'absent' means to remove items from list keys

        # Compute list of items to modify/add/delete
        actions_scalar, actions_add, actions_rem = self.diff.state(
            self.state)

        # Scalars first; they may bring base object into existence
        if actions_scalar:
            self.add_or_mod(actions_scalar)

        # Enable/disable
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
                    name=self.request_name_value,
                    method=method, action=action)

        return self.changed, self.new_obj

    def main(self):

        # self.login()
        # changed, obj = self.ensure()
        # result = {
        #     'changed': changed,
        #     self.name: obj,
        # }
        # self.module.exit_json(**result)
        try:
            self.login()
            changed, obj = self.ensure()
            result = {
                'changed': changed,
                self.name: obj,
            }
            self.module.exit_json(**result)
        except Exception:
            e = get_exception()
            self.module.fail_json(msg=str(e))

