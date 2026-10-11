#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Desinstala Puntero del usuario actual. Antes devuelve los botones a su función
# original, para que no queden "desviados" sin nadie que los atienda. Las acciones
# guardadas se conservan: al reinstalar, el servicio las vuelve a aplicar.
#
#   ./uninstall.sh          conserva tu configuración (~/.config/puntero)
#   ./uninstall.sh --purge  también borra la configuración y las imágenes
set -euo pipefail

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
PLUGIN_ID="puntero.mouse"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

# --- devolver los botones a su función original ------------------------------
if [[ -f "$CONFIG/puntero/buttons.json" && -S "${XDG_RUNTIME_DIR:-/run/user/$UID}/puntero.sock" ]]; then
  say "Devolviendo los botones a su función original"
  python3 - <<'EOF' || true
import os, socket
path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}", "puntero.sock")
s = socket.socket(socket.AF_UNIX)
s.connect(path)
s.settimeout(30)
s.sendall(b'{"cmd": "release_buttons"}\n')
# esperar la confirmación: el servicio responde cuando ya escribió en el ratón
for line in s.makefile():
    if '"released"' in line:
        break
EOF
fi

# --- servicio ---------------------------------------------------------------
say "Deteniendo el servicio"
systemctl --user disable --now puntero.service >/dev/null 2>&1 || true
rm -f "$CONFIG/systemd/user/puntero.service"
systemctl --user daemon-reload

# --- plugin de la barra -----------------------------------------------------
if [[ -e "$CONFIG/omarchy/plugins/$PLUGIN_ID" || -L "$CONFIG/omarchy/plugins/$PLUGIN_ID" ]]; then
  say "Quitando el plugin de la barra"
  if [[ -f "$CONFIG/omarchy/shell.json" ]]; then
    cp "$CONFIG/omarchy/shell.json" "$CONFIG/omarchy/shell.json.bak.$(date +%s)"
    python3 - "$CONFIG/omarchy/shell.json" "$PLUGIN_ID" <<'EOF'
import json, sys
path, plugin = sys.argv[1], sys.argv[2]
data = json.load(open(path))
layout = data.get("bar", {}).get("layout", {})
for section, items in layout.items():
    layout[section] = [i for i in items if not (isinstance(i, dict) and i.get("id") == plugin)]
json.dump(data, open(path, "w"), indent=2, ensure_ascii=False)
EOF
  fi
  rm -f "$CONFIG/omarchy/plugins/$PLUGIN_ID"
  omarchy restart shell >/dev/null 2>&1 || true
fi

# --- programa ---------------------------------------------------------------
say "Borrando el programa y el lanzador"
rm -f "$HOME/.local/bin/puntero" "$DATA/applications/puntero.desktop"
rm -rf "$DATA/puntero"
update-desktop-database "$DATA/applications" 2>/dev/null || true
rm -f "${XDG_RUNTIME_DIR:-/run/user/$UID}/puntero.sock"

if [[ "${1:-}" == "--purge" ]]; then
  say "Borrando la configuración (~/.config/puntero)"
  rm -rf "$CONFIG/puntero"
fi

say "Puntero desinstalado. Solaar sigue instalado; quítalo con: sudo pacman -Rns solaar"
