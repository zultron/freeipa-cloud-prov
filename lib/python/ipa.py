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

import re

from ansible.module_utils._text import to_bytes, to_text
from ansible.module_utils.pycompat24 import get_exception
from ansible.module_utils.six import PY3
from ansible.module_utils.six.moves.urllib.parse import quote
from ansible.module_utils.urls import fetch_url
from ansible.module_utils.basic import AnsibleModule


class IPAClient(object):

    # Object name: must be overridden
    name = 'unnamed'

    # Parameters for finding existing objects:  must be overridden
    #
    # - for list results, a function to select relevant results
    # find_filter = lambda x: [...]
    find_filter = None

    # Map method names in base object:  may be overridden
    # - Pattern will be filled with class `name` attribute
    methods = dict(
        add = '{}_add',
        rem = '{}_del',
        mod = '{}_mod',
        find = '{}_find',
        )

    # Choices for `state` param
    state_choices = ('present', 'absent', 'exact')

    # List of functions to run to generate change requests
    change_functions = ('rem', 'add_or_mod')

    # Parameters used as request keys:  must be overridden
    param_keys = set([])

    # Parameters of interest in base object add/mod requests; default
    # is to generate from kw_args, stripping out param_keys;
    # subclasses may explicitly define
    #base_keys = set([])

    # Keyword args:  must be overridden
    # kw_args = dict(
    #     description = dict(
    #         type='str', required=False),
    # )
    kw_args = dict()


    #######################################################
    # init

    def __init__(self):
        # Process module parameters
        self.init_methods()
        self.init_standard_params()
        self.init_kw_args()

        # Init some attributes
        self.requests = []

        # Init module object
        self.init_module()

    def init_methods(self):
        self._methods = dict(map(
            lambda x: (x[0],x[1].format(self.name)),
            self.__class__.methods.items()))

    def init_standard_params(self):
        self.argument_spec = dict(
            state=dict(
                type='str', required=False, default='present',
                choices=self.state_choices),
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
        self.param_data = {}
        for name, spec_orig in self.kw_args.items():
            spec = spec_orig.copy()
            self.param_data[name] = dict(
                type = spec['type'],
                when = spec.pop('when', ['add','mod']),
                value_filter_func = spec.pop('value_filter_func', None),
                value_filter_re = (re.compile(spec.pop('value_filter_re')) \
                                   if 'value_filter_re' in spec else None),
            )
            self.argument_spec[name] = spec
        if not hasattr(self, 'base_keys'):
            self.base_keys = set([
                k for k in self.param_data
                if k not in self.param_keys])
                
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
        self.changed = False


    #######################################################
    # post API request

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
        url = '%s/session/json' % self.get_base_url()
        data = {'method': method, 'params': [name, item]}
        from pprint import pprint; print "data:"; pprint(data)
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
        from pprint import pprint; print "resp:"; pprint(resp); print "err:"; pprint(err)
        if err is not None:
            self._fail('response %s' % method, err)

        if 'result' in resp:
            result = resp.get('result')
            if 'result' in result:
                result = result.get('result')
            if isinstance(result, list) and method == self._methods['find']:
                if self.find_filter is not None:
                    result = [ i for i in result if self.find_filter(i) ]
                return (result[-1] if len(result) > 0 else {})
            return result
        return None

    #######################################################
    # multi-method

    #########
    # accessors

    @property
    def response_cleaned(self):
        return self.requests[0].get('response_cleaned',None)

    #########
    # munging responses

    def munge_pop_request_keys(self, item):
        # Remove params that are request keys
        for k in item.keys():
            if k in self.param_keys:  item.pop(k)
        return item

    def clean(self, dirty):
        item = {}
        for key, val in dirty.items():
            # Ignore params that are not object attributes ('dn', 'ipa_host')
            if key not in self.param_data:  continue
            if self.param_data[key]['type'] == 'list':
                # Ensure list attributes are actually in lists (list
                # module params may be specified as strings)
                if not isinstance(val, list):
                    val = [val]
                # Ignore empty values
                if val==[] or val[0] is None:  continue
            if self.param_data[key]['type'] != 'list':
                # Ensure non-list attributes are not in lists (API
                # replies wrap scalars in lists)
                if isinstance(val, list):
                    val = val[0]
                # Ignore empty values
                if val is None: continue
            # Convert 'TRUE' and 'FALSE' strings to booleans
            if self.param_data[key]['type'] == 'bool' \
               and isinstance(val, basestring):
                if val.lower() == 'true': val = True
                elif val.lower() == 'false': val = False
            # Convert strings to integers
            if self.param_data[key]['type'] == 'int' \
               and isinstance(val, basestring):
                val = int(val)
            # Add key:val to item
            item[key] = val
        return item

    def filter_params_on_when(self, item, when):
        item = item.copy()
        for key in item.keys():
            if when not in self.param_data.get(key,{}).get('when',[]):
                item.pop(key)
        return item

    #######################################################
    # diffs

    def get_slice(self, params):
        res = {'list':{}, 'scalar':{}}
        for key in params:
            if self.param_data.get(key,{}).get('type',None) == 'list':
                res['list'][key] = params[key]
            else:
                res['scalar'][key] = params[key]
        return res

    def op(self, a, b, op):
        keys = set(self.param_data.keys())
        res = {}
        for key in set(a) | set(b):
            # if key not in self.param_data: continue
            # FIXME can we treat scalars this way?
            # if self.param_data[key]['type'] != 'list': continue
            # FIXME
            # if 'add' not in self.param_data[key]['when']: continue
            # => res_val = a[key] <op> b[key]
            res_val = list(getattr(set(a.get(key, [])), op)(set(b.get(key, []))))
            if res_val: res.setdefault(key,[]).extend(res_val)
        return res

    def compute_changes(self, change_params, curr_params):

        change_slice = self.get_slice(change_params)
        curr_slice = self.get_slice(curr_params)

        changes = dict(scalars = {}, list_add = {}, list_del = {})
        if self.state != 'absent':
            changes['list_add'].update(
                self.op(change_slice['list'], curr_slice['list'], 'difference'))
        if self.state == 'exact':
            changes['list_del'].update(
                self.op(curr_slice['list'], change_slice['list'], 'difference'))
        if self.state == 'absent':
            changes['list_del'].update(
                self.op(change_slice['list'], curr_slice['list'], 'intersection'))

        # Compute changes for scalar parameters
        scalar_keys = set()
        if self.state != 'absent':
            # New scalar keys
            scalar_keys |= (set(change_slice['scalar'].keys()) -
                            set(curr_slice['scalar'].keys()))
            # Changed scalar keys
            scalar_keys |= set(
                [ k for k in (set(change_slice['scalar'].keys()) &
                              set(curr_slice['scalar'].keys()))
                  if change_params[k] != curr_params[k]])
            if self.state == 'exact':
                # Deleted scalar keys
                scalar_keys |= (set(curr_slice['scalar'].keys()) -
                                set(change_slice['scalar'].keys()))
            for k in scalar_keys:
                changes['scalars'][k] = change_params.get(k,None)
        if self.state == 'absent':
            for k in change_slice['scalar']:
                if change_slice['scalar'][k] == \
                   curr_slice['scalar'].get(k,None):
                    changes['scalars'][k] = None

        return changes

    #######################################################
    # find

    #########
    # module params

    def munge_module_params(self):
        item = self.clean(self.module.params)
        item = self.munge_pop_request_keys(item)
        return item

    #########
    # request

    def find_request_params(self):
        return []

    def find_request_item(self):
        item = {'all': True}
        for k in self.param_keys:
            if k in self.module.params:
                item[k] = self.module.params[k]
        return item

    #########
    # response

    def munge_response(self, response):
        item = self.clean(response)
        item = self.munge_pop_request_keys(item)
        return item

    #########
    # find

    def find(self):
        # Store data about the find request and diff computation
        entry = {'name' : 'find'}
        self.requests.append(entry)

        # Clean module params
        self.canon_params = self.munge_module_params()

        # Build and post request
        request = entry['request'] = dict(
            method = self._methods['find'],
            name = self.find_request_params(),
            item = self.find_request_item(),
        )
        response = entry['response'] = self._post_json(**request)

        # Clean results
        entry['response_cleaned'] = (self.munge_response(response.copy()))

        # Make object diff
        self.diffs = self.compute_changes(
            self.canon_params, self.response_cleaned)

    #######################################################
    # add/modify base params

    def mod_request_params(self, extra_vals=None):
        name = []
        for k in self.module.params:
            if k not in self.param_data: continue
            if k in self.param_keys:
                name.append( self.module.params[k] )
        if extra_vals is not None:
            name.extend(extra_vals)
        return name

    def mod_rewrite_list_changes(self, request):
        item = request['item']

        for key, val in item.items():
            if key in ('addattr','delattr'):
                for k, vs in item.pop(key).items():
                    # Turn key:[val1,val2,...] dicts into
                    # ["key=val1","key=val2",...] lists
                    for v in vs:
                        item.setdefault(key, []).append("%s=%s" % (k, v))
                    # Sort list for tests
                    item[key].sort()
                continue
        # Add all=True to get back object with all attributes in reply
        item['all'] = True

    @property
    def is_absent(self):
        return not bool(self.response_cleaned)

    def add_or_mod(self):
        # Compute list of items to modify/add/delete
        item = {}
        for k, v in self.diffs['list_add'].items():
            if k in self.base_keys:
                item.setdefault('addattr',{})[k] = v
        for k, v in self.diffs['list_del'].items():
            if k in self.base_keys:
                item.setdefault('delattr',{})[k] = v
        for k, v in self.diffs['scalars'].items():
            if k in self.base_keys:
                item[k] = v


        # Do nothing if no changes in item
        if not item:  return

        # Construct request and queue it up
        item['all'] = True
        request = dict(
            method = (self._methods['add'] if self.is_absent \
                      else self._methods['mod']),
            name = self.mod_request_params(),
            item = item)
        self.mod_rewrite_list_changes(request)

        self.requests.append(dict( name = 'add_or_mod', request = request ))

    #######################################################
    # remove object
        
    def rem_request_cleanup(self, request):
        # Classes may override to munge request
        pass

    def rem_request_params(self):
        return self.mod_request_params()

    def rem_request_item(self):
        return {}

    def is_rem_param_request(self):
        # Module params contain object params; 'absent' means
        # absent attributes, not absent object
        return bool(self.canon_params)

    def rem(self):
        if self.state != 'absent':
            # Not removing object; signal to continue
            return False

        if self.is_rem_param_request():
            # state='absent' means remove params, not remove object
            return False

        if self.is_absent:
            # Object is already absent; signal done
            return True

        if self.module.check_mode:
            # In check mode, do nothing; signal done
            return True

        # Generate remove request
        request = dict(
            method = self._methods['rem'],
            name = self.rem_request_params(),
            item = self.rem_request_item())

        # Run any subclass request cleanups
        self.rem_request_cleanup(request)

        # Queue request and signal done
        self.requests.append(dict( name = 'rem', request = request ))
        return True

    #######################################################
    # main functions

    def queue_requests(self):
        for func_name in self.change_functions:
            func = getattr(self, func_name)
            # Let function queue up any request; if it returns True,
            # then stop and don't enqueue any more requests
            if func():  break

    def process_queue(self):
        # Process queue, except for initial find() request
        for entry in self.requests[1:]:
            request = entry['request']
            if self.module.check_mode:
                entry['response'] = {}
            else:
                entry['response'] = self._post_json(**request)
            self.changed = True

    def ensure(self):

        # Find existing objects and compute diff
        self.find()

        # Queue up requests
        self.queue_requests()

        # Effect changes
        self.process_queue()

        # Return results
        return self.changed, self.requests[-1]['response']

    def main(self):

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

class EnablableIPAClient(IPAClient):
    methods = dict(
        add = '{}_add',
        rem = '{}_del',
        mod = '{}_mod',
        find = '{}_find',
        enabled = '{}_enable',
        disabled = '{}_disable',
        )

    state_choices = ('present', 'absent', 'exact', 'enabled', 'disabled')

    change_functions = ('rem', 'add_or_mod', 'enable_or_disable')

    # Subclasses must override
    enablekey = None

    # Subclasses:  Set to True if object enabled when enablekey False
    enablekey_sense_inverted = False

    #######################################################
    # enable/disable methods

    def init_kw_args(self):
        super(EnablableIPAClient, self).init_kw_args()

        # For subclasses where self.base_keys is not supplied,
        # remove enablekey from generated set of parameters
        if not hasattr(self.__class__, 'base_keys'):
            self.base_keys.discard(self.enablekey)

    def munge_module_params(self):
        item = super(EnablableIPAClient, self).munge_module_params()
        if self.state == 'enabled':
            item[self.enablekey] = True
        elif self.state == 'disabled':
            item[self.enablekey] = False
        else:
            return item
        if self.enablekey_sense_inverted:
            item[self.enablekey] = not item[self.enablekey]
        return item

    def enable_or_disable(self):

        # Do nothing if enablekey is not in diffs
        if self.enablekey not in self.diffs['scalars']:
            return

        # Do nothing if object is being created (enabled by default)
        # or not in enable/disable state
        if self.is_absent or self.state not in ('enabled','disabled'):
            return

        # Do nothing in check mode
        if self.module.check_mode:
            return

        # Effect requested state
        enable = self.diffs['scalars'][self.enablekey]
        if self.enablekey_sense_inverted:
            enable = not enable
        request = dict(
            method = (self._methods['enabled'] if enable \
                      else self._methods['disabled']),
            name = self.mod_request_params(),
            item = {})

        self.requests.append(dict(name = 'enable_or_disable',
                                  request = request ))

