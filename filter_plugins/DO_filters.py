__metaclass__ = type

class FilterModule(object):
    ''' Query filter '''

    def mapformat(self, data, fmt, sep=''):
        items = [fmt.format(d) for d in data]
        return sep.join(items)

    def systemd_escape(self, data):
        """Convert a path into a string suitable for a systemd unit name,
        similar to the `systemd-escape(1)` command

        See https://www.freedesktop.org/software/systemd/man/systemd.unit.html
        """
        res = ''
        for i,c in enumerate(data):
            if i==0 and c=='/':
                # Throw away initial slashes
                continue
            elif (c=='.' and res==''):
                # Escape initial '.' C-style
                res += '\\x2e'
            elif (c>='a' and c<='z') or (c>='A' and c<='Z') \
                 or (c>='0' and c<='9') or (c=='_'):
                # Pass alphanumerics and underscore unchanged
                res += c
            elif c=='/':
                # Convert to dash
                res += '-'
            else:
                # Escape everything else C-style
                res += '\\' + hex(ord(c))[1:]
        return res

    def filters(self):
        return {
            'mapformat': self.mapformat,
            'systemd_escape': self.systemd_escape,
        }
