__metaclass__ = type

class FilterModule(object):
    ''' Query filter '''

    def mapformat(self, data, fmt, sep=''):
        items = [fmt.format(d) for d in data]
        return sep.join(items)

    def hostname(self, fqdn):
        return fqdn.split('.')[0]

    def domainname(self, fqdn):
        return '.'.join(fqdn.split('.')[1:])

    def filters(self):
        return {
            'mapformat': self.mapformat,
            'hostname': self.hostname,
            'domainname': self.domainname,
        }
