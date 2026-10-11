# SPDX-License-Identifier: GPL-3.0-or-later
"""Pide al servicio que devuelva los botones a su función original (antes de desinstalar).

Las acciones guardadas se conservan: al volver a instalar, el servicio las aplica otra vez.
"""

import os
import socket
import sys


def main():
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}", "puntero.sock")
    try:
        s = socket.socket(socket.AF_UNIX)
        s.connect(path)
    except OSError:
        return 0  # el servicio no está en marcha: no hay botones desviados que atender
    s.settimeout(30)
    s.sendall(b'{"cmd": "release_buttons"}\n')
    # esperar la confirmación: el servicio responde cuando ya escribió en el ratón
    for line in s.makefile():
        if '"released"' in line:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
