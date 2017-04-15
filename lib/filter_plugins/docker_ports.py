__metaclass__ = type

class FilterModule(object):
    ''' Query filter '''

    def docker_port_list(self, data):
        """Given a list ['53', '53/udp'], return a list suitable for
        arguments to `docker run --publish=[]`, ['53:53', '53:53/udp']

        """
        res = []
        for d in data:
            port, proto = (d.split('/') + [None])[0:2]
            res.append(
                ('{0}:{0}/{1}' if proto else '{0}:{0}').format(port, proto))
        return res

    def docker_port_args(self, data):
        """Given a list ['53', '53/udp'], return a string of docker run
        arguments, `--publish=53:53 --publish=53:53/udp`

        """
        port_list = self.docker_ports_list(data)
        if not port_list: return ''

        return '--publish={}'.format( ' --publish='.join(port_list))

    def filters(self):
        return {
            'docker_port_list': self.docker_port_list,
            'docker_port_args': self.docker_port_args,
        }
