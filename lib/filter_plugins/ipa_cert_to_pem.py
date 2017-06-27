__metaclass__ = type

class FilterModule(object):
    ''' Query filter '''

    def ipa_cert_to_pem(self, data):
        """Given a base64-encoded cert string from IPA, create a
        .pem-formatted cert"""
        cert = '-----BEGIN CERTIFICATE-----\n'
        while len(data) >= 64:
            cert += ('%s\n' % data[:64])
            data = data[64:]
        cert += ('%s\n-----END CERTIFICATE-----\n' % data)
        return cert

    def filters(self):
        return {
            'ipa_cert_to_pem': self.ipa_cert_to_pem,
        }
