__metaclass__ = type

class FilterModule(object):
    ''' Query filter '''

    def mapformat(self, data, fmt, sep=''):
        items = [fmt.format(d) for d in data]
        return sep.join(items)

    def filters(self):
        return {
            'mapformat': self.mapformat
        }
