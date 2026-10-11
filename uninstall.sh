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

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

# --- devolver los botones a su función original ------------------------------
if [[ -f "$CONFIG/puntero/buttons.json" && -S "${XDG_RUNTIME_DIR:-/run/user/$UID}/puntero.sock" ]]; then
  say "Devolviendo los botones a su función original"
  (cd "$(dirname "${BASH_SOURCE[0]}")" && python3 -m puntero.release) || true
fi

# --- servicio ---------------------------------------------------------------
say "Deteniendo el servicio"
systemctl --user disable --now puntero.service >/dev/null 2>&1 || true
rm -f "$CONFIG/systemd/user/puntero.service"
systemctl --user daemon-reload

# --- plugin de la barra -----------------------------------------------------
"$(dirname "${BASH_SOURCE[0]}")/data/omarchy-plugin.sh" remove

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
