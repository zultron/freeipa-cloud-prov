s__metaclass__ = type

class FilterModule(object):
    ''' Query filter '''

    def freeipa_dns_server_ips(self, hostvars):
        """Given hostvars, extract DNS server IPs"""
        # This was implemented as a variable 'freeipa_dns_servers' in
        # group_vars/freeipa_all.yaml after Ansible upgrade error saying
        # hostvars undefined; see that file for old implementation
        if len(hostvars.keys()) == 0: return []
        random_host = hostvars.keys()[0]
        dns_server_list = hostvars[random_host].get('groups',{})\
                                               .get('freeipa_servers',None)
        if not isinstance(dns_server_list, list): return
        dns_server_ips = [ hostvars[s]['ipa_ip_addr']
                           for s in dns_server_list
                           if 'ipa_ip_addr' in hostvars[s] ]
        return dns_server_ips


    def filters(self):
        return {
            'freeipa_dns_server_ips': self.freeipa_dns_server_ips,
        }
