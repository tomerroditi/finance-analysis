"""Print a free TCP port on 127.0.0.1.

Tries a small list of preferred ports first; falls back to an OS-assigned
ephemeral port if all are busy. Used by run.sh / run.bat to avoid binding a
hardcoded port that may already be taken (e.g. by another local dev server).
"""

import socket
import sys

PREFERRED = (8765, 8766, 8767, 17654, 39817)


def find_port() -> int:
    for port in PREFERRED:
        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            sock.close()

    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


if __name__ == "__main__":
    sys.stdout.write(str(find_port()))
