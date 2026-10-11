#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Pone o quita el plugin de Puntero en la barra de Omarchy del usuario actual.
# Lo usan install.sh, uninstall.sh y `puntero --setup` (paquete de AUR).
#
#   omarchy-plugin.sh install <carpeta del plugin>
#   omarchy-plugin.sh remove
set -euo pipefail

CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
PLUGIN_ID="puntero.mouse"
LINK="$CONFIG/omarchy/plugins/$PLUGIN_ID"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }

case "${1:-}" in
install)
  if ! command -v omarchy >/dev/null || [[ ! -d "$CONFIG/omarchy" ]]; then
    say "Omarchy no detectado: se omite el plugin de la barra"
    exit 0
  fi
  say "Instalando el plugin de la barra de Omarchy"
  mkdir -p "$CONFIG/omarchy/plugins"
  ln -sfn "$2" "$LINK"
  omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
  sleep 1
  if ! grep -q "\"$PLUGIN_ID\"" "$CONFIG/omarchy/shell.json" 2>/dev/null; then
    omarchy bar put "$PLUGIN_ID" --after omarchy.bluetooth >/dev/null 2>&1 \
      || omarchy bar put "$PLUGIN_ID" >/dev/null 2>&1 \
      || warn "No se pudo añadir a la barra; hazlo con: omarchy bar put $PLUGIN_ID"
  fi
  # la recarga en caliente no reemplaza un widget ya montado
  omarchy restart shell >/dev/null 2>&1 || true
  ;;
remove)
  [[ -e "$LINK" || -L "$LINK" ]] || exit 0
  say "Quitando el plugin de la barra"
  if [[ -f "$CONFIG/omarchy/shell.json" ]]; then
    cp "$CONFIG/omarchy/shell.json" "$CONFIG/omarchy/shell.json.bak.$(date +%s)"
    python3 - "$CONFIG/omarchy/shell.json" "$PLUGIN_ID" <<'PY'
import json, sys
path, plugin = sys.argv[1], sys.argv[2]
data = json.load(open(path))
layout = data.get("bar", {}).get("layout", {})
for section, items in layout.items():
    layout[section] = [i for i in items if not (isinstance(i, dict) and i.get("id") == plugin)]
json.dump(data, open(path, "w"), indent=2, ensure_ascii=False)
PY
  fi
  rm -f "$LINK"
  omarchy restart shell >/dev/null 2>&1 || true
  ;;
*)
  echo "uso: $0 install <carpeta del plugin> | remove" >&2
  exit 2
  ;;
esac
