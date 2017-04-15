__metaclass__ = type

class FilterModule(object):
    ''' Query filter '''

    def shortname(self, data):
        """Given a fqdn, return the host name portion without the domain name
        """
        return data.split('.')[0]

    def reverse_ip(self, data, pad=False):
        """Return the reverse of a set of dotted octets"""
        octets = data.split('.')
        if pad: octets = (octets + ['0'] * 4)[0:4]

        return '.'.join(reversed(octets))

    def last_octet(self, data):
        """Return the last octet of a set of dotted octets"""
        return data.split('.')[-1]

    def reverse_zone(self, data):
        """Return the reverse zone of a set of dotted octets"""
        return "{}.in-addr.arpa.".format(self.reverse_ip(data))

    def filters(self):
        return {
            'shortname': self.shortname,
            'reverse_ip': self.reverse_ip,
            'reverse_zone': self.reverse_zone,
            'last_octet': self.last_octet,
        }
