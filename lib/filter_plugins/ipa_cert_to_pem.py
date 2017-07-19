__metaclass__ = type

import re

class FilterModule(object):
    ''' Query filter '''

    def ipa_cert_to_pem(self, data):
        """Given a base64-encoded cert string from IPA, create a
        .pem-formatted cert"""
        cert = '-----BEGIN CERTIFICATE-----\n'
        while len(data) >= 64:
            cert += ('%s\n' % data[:64])
            data = data[64:]
        cert += ('%s-----END CERTIFICATE-----\n' %
                 ('%s\n' % data if data else ''))
        return cert

    cn_re = re.compile(r'CN=([^,]*),')
    def cn_from_dn(self, data):
        """Given a DN, extract and return the CN"""
        m = self.cn_re.search(data)
        if m is None:  return None
        return m.group(1)

    def filters(self):
        return {
            'ipa_cert_to_pem': self.ipa_cert_to_pem,
            'cn_from_dn': self.cn_from_dn,
        }
