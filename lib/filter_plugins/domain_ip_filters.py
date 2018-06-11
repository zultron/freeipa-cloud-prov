__metaclass__ = type

class FilterModule(object):
    ''' Query filter '''

    def shortname(self, data):
        """Given a fqdn, return the host name portion without the domain name
        """
        return data.split('.')[0]

    def last_octet(self, data):
        """Return the last octet of a set of dotted octets"""
        return data.split('.')[-1]

    def filters(self):
        return {
            'shortname': self.shortname,
            'last_octet': self.last_octet,
        }
