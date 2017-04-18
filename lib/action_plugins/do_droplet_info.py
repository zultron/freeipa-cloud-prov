#!/usr/bin/env python

# Task spec:
#
# - do_droplet_info:
#     # Optional: look up single host
#     name: host1.example.com
#     # Optional: look up hosts in list
#     names:
#       - host1.example.com
#       - host2.example.com
#
# With name arg, returns droplet info (plus 'changed' attribute):
#
# { changed: False,
#   name: 'host1.example.com',
#   id: 1234567,
#   ip_address:  '192.168.42.12',
#   [...]
# }
#
# With names arg, returns dict of name:info:
#
# { changed: False,
#   d: {
#     host1.example.com: {
#       name: 'host1.example.com',
#       id: 1234567,
#       ip_address:  '192.168.42.12',
#       [...]
#     },
#     host2.example.com: {
#       [...]
#     }
#   }
# }

__metaclass__ = type

from ansible.plugins.action import ActionBase
import os, sys

try:
    from dopy.manager import DoManager
except ImportError as e:
    sys.exit("failed=True msg='`dopy` library required for this script'")

class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=dict()):

        result = super(ActionModule, self).run(tmp, task_vars)

        args = self._task.args

        # Get DO API token and manager object
        api_token = args.get(
            'api_token', os.environ.get('DO_API_KEY', None))
        if api_token is None:
            return dict(failed=True,
                        msg=("No 'api_token' option or 'DO_API_KEY' "
                             "environment variable set"))
        manager = DoManager(None, api_token, api_version=2)

        # Read arguments
        if 'name' in args:
            name = args['name']
            names = [ name, ]
        elif 'names' in args:
            names = args['names']
            if not isinstance(names, list):
                return dict(failed=True,
                            msg=("Argument 'names' must be a list"))
        else:
            return dict(failed=True,
                        msg=("Required argument 'name' or 'names' not found"))

        # Get droplet info
        droplets = [ d for d in manager.all_active_droplets()
                     if d['name'] in names ]

        # If a single 'name', return the droplet info dict
        if 'name' in args:
            if len(droplets) != 1:
                return dict(failed=True,
                            msg=("No droplet named '{}' found".format(name)))
            droplet = droplets[0]
            droplet['changed'] = False
            return droplet

        # Otherwise, return a dict of name:info
        return dict(
            changed=False,
            d=dict( [(d['name'], d) for d in droplets] ),
        )
