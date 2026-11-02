#!/usr/bin/env python3
import os
import pty
import select
import sys

def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    cmd = sys.argv[1:]
    master, slave = pty.openpty()

    pid = os.fork()
    if pid == 0:
        # Child
        os.close(master)
        os.setsid()
        # Set controlling terminal
        import fcntl, termios
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        os.dup2(slave, 0)
        os.dup2(slave, 1)
        os.dup2(slave, 2)
        if slave > 2:
            os.close(slave)
        os.execvp(cmd[0], cmd)
    else:
        # Parent
        os.close(slave)
        while True:
            r, _, _ = select.select([0, master], [], [], 0.05)
            if 0 in r:
                data = os.read(0, 1024)
                if not data:
                    break
                os.write(master, data)
            if master in r:
                try:
                    data = os.read(master, 1024)
                    if not data:
                        break
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                except OSError:
                    break
            # Check child status
            res = os.waitpid(pid, os.WNOHANG)
            if res[0] == pid:
                break

        # Flush any remaining master output
        try:
            while True:
                r, _, _ = select.select([master], [], [], 0.05)
                if master in r:
                    data = os.read(master, 1024)
                    if not data:
                        break
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                else:
                    break
        except OSError:
            pass

        try:
            _, status = os.waitpid(pid, 0)
            sig = status & 0x7F
            sys.exit(128 + sig if sig else (status >> 8) & 0xFF)
        except OSError:
            sys.exit(0)

if __name__ == "__main__":
    main()
