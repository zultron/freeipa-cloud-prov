#!/usr/bin/env python

# Task spec:
#
# - do_droplet_id: name=host1.example.com
#
# Should return:
#
# { changed: False,
#   name: 'host1.example.com',
#   id: 1234567,
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

        # Read options
        name = self._task.args.get('name', None)
        if name is None:
            return dict(failed=True,
                        msg="Required 'name' attribute not found")

        api_token = self._task.args.get(
            'api_token', os.environ.get('DO_API_KEY', None))
        if api_token is None:
            return dict(failed=True,
                        msg=("No 'api_token' option or 'DO_API_KEY' "
                             "environment variable set"))

        # Get droplet info
        manager = DoManager(None, api_token, api_version=2)
        droplets = [ d for d in manager.all_active_droplets()
                     if d['name'] == name ]
        if len(droplets) != 1:
            return dict(failed=True,
                        msg=("No droplet named '{}' found".format(name)))
        droplet_id = droplets[0]['id']

        # Return result
        return dict(
            changed = False,
            name = name,
            id = droplet_id,
        )
