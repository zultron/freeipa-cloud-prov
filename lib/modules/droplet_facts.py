#!/usr/bin/python

import yaml

from pprint import pformat
import sys

from ansible.module_utils.basic import AnsibleModule

def main():

    module = AnsibleModule(
        argument_spec = dict(
            droplets = dict(required=True),
        ),
    )

    # Structured data comes in as yaml string...?
    droplets = yaml.load(module.params['droplets'])['results']

    with open('/data/foo.txt', 'w') as f:
        f.write("droplets:\n%s\n" % pformat(droplets))

    facts = {}
    for d in droplets:
        with open('/data/foo.txt', 'a') as f:
            f.write("whole shebang:  %s\n" % d)
            host = d['droplet']['name']
            f.write("host: %s\n" % host)
            droplet = d['droplet']
            f.write("droplet: %s\n" % droplet)
        facts[d['droplet']['name']] = d['droplet'].copy()

    module.exit_json(
        changed = False,
        ansible_facts = dict(droplets=facts),
        droplets = facts,
    )
    # module.fail_json()

if __name__ == '__main__':
    main()
