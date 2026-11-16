"""The Pi's own IPv4 address, shown on the LCD so it can be entered in Artisan."""

import socket
import subprocess


def local_ip() -> str | None:
    """Address of the interface that carries outgoing traffic, None without a network."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # UDP connect only selects a route; no packet is sent.
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
            if not ip.startswith('127.') and ip != '0.0.0.0':
                return ip
    except OSError:
        pass
    # No default route (e.g. a LAN without gateway): take the first configured address.
    try:
        out = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for addr in out.split():
        if '.' in addr and not addr.startswith('127.'):
            return addr
    return None
