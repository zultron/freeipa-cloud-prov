import paramiko, sys, re, time
from .Config import Config

# https://urllib3.readthedocs.io/en/latest/advanced-usage.html#ssl-warnings
# import urllib3
# urllib3.disable_warnings()
# import logging
# logging.captureWarnings(paramiko)

class RemoteControl(Config):
    # Cache of host connections
    conns = {}
    default_user = 'core'

    def conn(self, hostname, username=default_user):
        if not hasattr(self, '_conns'): self._conns = {}
        if self._conns.get(hostname, {}).get(username, None) is not None:
            return self._conns[hostname][username]

        print "- Creating new SSH connection for %s@%s" % (username, hostname)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(
            paramiko.AutoAddPolicy())
        ssh.connect(hostname, username=username)
        self._conns.setdefault(hostname, {})[username] = ssh

        # Cache host key
        if not hasattr(self, 'host_keys'):  self.host_keys = {}
        if not self.host_keys.has_key(hostname):
            self.host_keys[hostname] = str("%s %s" % (
                ssh.get_transport().get_remote_server_key().get_name(),
                ssh.get_transport().get_remote_server_key().get_base64()))
            self.pickle_config()

        return self._conns[hostname][username]

    def remote_run(self, command, hostname, username=default_user,
                   stdin_in=None, get_pty=False,
                   read_stdout=True, quiet=False, read_stderr=True):
        conn = self.conn(hostname, username)

        if not quiet:
            print "- Running on %s: '%s'" % (hostname, command)
        # stdin, stdout, stderr = conn.exec_command(command)
        # stdin.close()
        chan = conn.get_transport().open_session()
        paramiko.agent.AgentRequestHandler(chan)
        if get_pty: chan.get_pty()
        chan.exec_command(command)
        stdin = chan.makefile('wb')
        if stdin_in is not None:
            stdin.write(stdin_in)
            stdin.flush()
        stdin.close()
        bufsize = -1
        stdout = chan.makefile('r', bufsize)
        stderr = chan.makefile_stderr('r', bufsize)
        res = []
        if read_stdout:
            for line in stdout:
                sys.stdout.write(('   out: %s' % line).encode("utf-8"))
        else:
            res.append(stdout)
        if read_stderr:
            for line in stderr:
                sys.stdout.write(("   err: %s" % line).encode("utf-8"))
        else:
            res.append(stderr)
        if len(res) == 1:
            return res[0]
        elif len(res) == 2:
            return res

    def remote_run_and_grep(self, command, hostname,
                            success_re=None, fail_re=None,
                            stdin_in=None, get_pty=False,
                            print_stdout=True, print_stderr=True,
                            username=default_user, timeout=None, quiet=False):
        # http://docs.paramiko.org/en/2.0/api/channel.html
        conn = self.conn(hostname, username)
        if success_re is not None:
            r_s = re.compile(success_re)
        if fail_re is not None:
            r_f = re.compile(fail_re)
        start_time = time.time()

        if not quiet:
            print "- Running on %s: '%s'" % (hostname, command)
        chan = conn.get_transport().open_session()
        paramiko.agent.AgentRequestHandler(chan)
        if get_pty: chan.get_pty()
        chan.exec_command(command)
        stdin = chan.makefile('wb')
        if stdin_in is not None:
            stdin.write(stdin_in)
            stdin.flush()
        stdin.close()
        bufsize = -1
        stdout_buf = bytearray()
        stderr_buf = bytearray()

        while True:
            if chan.exit_status_ready():
                print "Process exited status %s" % chan.recv_exit_status()
                break
            if not chan.recv_ready() and not chan.recv_stderr_ready():
                time.sleep(0.1)
                continue
            if chan.recv_ready():
                stdout_buf.extend(chan.recv(1))
                n = stdout_buf.find(b'\n')
                if n >= 0:
                    output = stdout_buf[:(n+1)].decode('utf-8')
                    if print_stdout:
                        sys.stdout.write('   out:  %s' % output)
                    if success_re is not None and r_s.search(output):
                        print "SUCCESS"
                        break
                    if fail_re is not None and r_f.search(output):
                        raise RuntimeError("Found output indicating failure")
                    stdout_buf = stdout_buf[(n+1):]
            if chan.recv_stderr_ready():
                stderr_buf.extend(chan.recv_stderr(1))
                n = stderr_buf.find(b'\n')
                if n >= 0:
                    output = stderr_buf[:(n+1)].decode('utf-8')
                    if print_stderr:
                        sys.stdout.write('   err: %s' % output)
                    if success_re is not None and r_s.search(output):
                        print "SUCCESS"
                        break
                    if fail_re is not None and r_f.search(output):
                        raise RuntimeError("Found output indicating failure")
                    stderr_buf = stderr_buf[(n+1):]
            if timeout and time.time() > start_time + timeout:
                print "TIMEOUT"
                break
        chan.close()

    def remote_sudo(self, command, hostname, **kwargs):
        return self.remote_run('sudo ' + command, hostname, **kwargs)

    def remote_run_output(self, command, hostname, username=default_user,
                          quiet=True):
        stdout = self.remote_run(command, hostname, username,
                                 read_stdout=False, quiet=quiet)
        return stdout.readlines()

    def remote_docker_exec(self, hostname, container, command, get_pty=True,
                           **kwargs):
        if get_pty:
            cmd_fmt = 'docker exec -it %s %s'
        else:
            cmd_fmt = 'docker exec -i %s %s'
        return self.remote_run(cmd_fmt % (container, command),
                               hostname, get_pty=get_pty, **kwargs)

    def close(self, hostname, username=default_user):
        self.conn(hostname, username).close()

    def put_file(self, hostname, contents, remote_fname,
                 mode=0644, owner=None, username=default_user):
        print "- Installing file %s:%s" % (hostname, remote_fname)
        ssh = self.conn(hostname, username)
        sftp = ssh.open_sftp()
        with sftp.file(remote_fname, mode='w', bufsize=1000) as f:
            f.write(contents)
        sftp.chmod(remote_fname, mode)
        if owner is not None:
            # Use sudo to change owner
            self.remote_sudo('chown %s %s' % (owner, remote_fname), hostname)

    def get_file(self, hostname, remote_fname, username=default_user):
        print "- Retrieving file %s:%s" % (hostname, remote_fname)
        ssh = self.conn(hostname, username)
        sftp = ssh.open_sftp()
        with sftp.file(remote_fname, mode='r', bufsize=1000) as f:
            res = f.read()
        return res

    def get_ssh_host_keys(self, *hosts):
        if not hosts:  hosts = self.hosts.keys()
        res = []
        for h in hosts:
            if h in self.hosts:  h = self.to_ip(h)
            if getattr(self, 'host_keys', {}).get(h, None) is None:  continue
            res.append('%s %s' % (h, self.host_keys[h]))
        return res

    def install_known_hosts(self, hostname):
        ip = self.to_ip(hostname)
        print "Installing %s:/home/core/.fleetctl/known_hosts" % hostname
        self.remote_run("install -d -m 700 /home/core/.fleetctl", ip)
        self.put_file(ip, "%s\n" % "\n".join(self.get_ssh_host_keys()),
                      '/home/core/.fleetctl/known_hosts')

    def update_etc_hosts(self, hostname):
        ip = self.to_ip(hostname)
        print "Updating %s:/etc/hosts" % hostname
        hosts_entries = ''
        for h in self.hosts:
            self.remote_run('echo "%s %s" | sudo tee -a /etc/hosts' % \
                            (self.get_ip_addr(h), h),
                            ip, stdin_in=hosts_entries, read_stdout=False)

    def reboot(self, hostname, username=default_user):
        self.remote_sudo('reboot', hostname, username)
