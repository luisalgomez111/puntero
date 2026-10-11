#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Instala Puntero para el usuario actual: la app, el servicio en segundo plano y,
# si el sistema usa Omarchy, el plugin de la barra.
#
#   ./install.sh         copia el programa a ~/.local/share/puntero
#   ./install.sh --dev   usa este directorio tal cual (los cambios se ven sin reinstalar)
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN="$HOME/.local/bin"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }

# --- dependencias -----------------------------------------------------------
# El Python del sistema va primero: es donde los paquetes de la distribución instalan
# Solaar y GTK. Un python3 de un gestor de versiones (mise, pyenv…) no los suele tener.
PYTHON=""
for candidate in /usr/bin/python3 "$(command -v python3 || true)"; do
  [[ -x "$candidate" ]] || continue
  [[ -z "$PYTHON" ]] && PYTHON="$candidate"
  if "$candidate" -c 'import gi, evdev, logitech_receiver' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [[ -z "$PYTHON" ]]; then
  warn "No se encontró python3. Instálalo y vuelve a ejecutar este script."
  exit 1
fi

# Nombres de los paquetes en cada gestor: solaar, evdev, gobject, gtk4, libadwaita
if command -v pacman >/dev/null; then
  pm="sudo pacman -S --needed"; pkgs=(solaar python-evdev python-gobject gtk4 libadwaita)
elif command -v apt-get >/dev/null; then
  pm="sudo apt install"; pkgs=(solaar python3-evdev python3-gi gir1.2-gtk-4.0 gir1.2-adw-1)
elif command -v dnf >/dev/null; then
  pm="sudo dnf install"; pkgs=(solaar python3-evdev python3-gobject gtk4 libadwaita)
elif command -v zypper >/dev/null; then
  pm="sudo zypper install"; pkgs=(solaar python3-evdev python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1)
else
  pm=""; pkgs=(solaar python-evdev python-gobject gtk4 libadwaita)
fi

missing=()
"$PYTHON" -c 'import logitech_receiver, solaar' 2>/dev/null || missing+=("${pkgs[0]}")
"$PYTHON" -c 'import evdev' 2>/dev/null || missing+=("${pkgs[1]}")
"$PYTHON" -c 'import gi' 2>/dev/null || missing+=("${pkgs[2]}")
"$PYTHON" -c 'import gi; gi.require_version("Gtk", "4.0")' 2>/dev/null || missing+=("${pkgs[3]}")
"$PYTHON" -c 'import gi; gi.require_version("Adw", "1")' 2>/dev/null || missing+=("${pkgs[4]}")
if ((${#missing[@]})); then
  warn "Faltan dependencias. Instálalas y vuelve a ejecutar este script:"
  if [[ -n "$pm" ]]; then
    echo "    $pm ${missing[*]}"
  else
    echo "    (con el gestor de paquetes de tu distribución) ${missing[*]}"
  fi
  echo "    sudo udevadm control --reload && sudo udevadm trigger"
  exit 1
fi

# --- versiones ---------------------------------------------------------------
adw_minor="$("$PYTHON" -c 'import gi; gi.require_version("Adw", "1"); from gi.repository import Adw; print(Adw.get_minor_version())')"
if ((adw_minor < 7)); then
  warn "Puntero necesita libadwaita 1.7 o superior (tienes la 1.$adw_minor)."
  echo "    Tu distribución es demasiado antigua; prueba con una versión más reciente."
  exit 1
fi
solaar_version="$("$PYTHON" -c 'import pkgutil; print(pkgutil.get_data("solaar", "version").decode().strip())' 2>/dev/null || echo "?")"
if ! "$PYTHON" -c 'import sys; v = tuple(int(x) for x in sys.argv[1].split(".")[:3]); sys.exit(v < (1, 1, 20))' "$solaar_version" 2>/dev/null; then
  warn "Puntero se probó con Solaar 1.1.20 y tienes la $solaar_version; algunas funciones podrían fallar."
fi

# --- programa ---------------------------------------------------------------
if [[ "${1:-}" == "--dev" ]]; then
  APPDIR="$SRC"
  say "Modo desarrollo: se usará $APPDIR"
else
  APPDIR="$DATA/puntero"
  say "Copiando el programa a $APPDIR"
  mkdir -p "$APPDIR"
  rm -rf "$APPDIR/puntero" "$APPDIR/omarchy-plugin"
  cp -r "$SRC/puntero" "$SRC/omarchy-plugin" "$APPDIR/"
  find "$APPDIR" -name __pycache__ -type d -prune -exec rm -rf {} +
fi

say "Creando el lanzador y el acceso del menú"
mkdir -p "$BIN" "$DATA/applications"
cat >"$BIN/puntero" <<EOF
#!/bin/sh
cd "$APPDIR" && exec "$PYTHON" -m puntero "\$@"
EOF
chmod +x "$BIN/puntero"
cat >"$DATA/applications/puntero.desktop" <<EOF
[Desktop Entry]
Version=1.0
Name=Puntero
Comment=Configure your Logitech mice and keyboards
Comment[es]=Controla tus ratones y teclados Logitech
Exec=$BIN/puntero
Icon=input-mouse
Terminal=false
Type=Application
Categories=Settings;HardwareSettings;
StartupWMClass=ve.puntero.Puntero
EOF
update-desktop-database "$DATA/applications" 2>/dev/null || true

# --- servicio ---------------------------------------------------------------
say "Instalando y arrancando el servicio puntero.service"
mkdir -p "$CONFIG/systemd/user"
sed -e "s|@APPDIR@|$APPDIR|" -e "s|@PYTHON@|$PYTHON|" "$SRC/data/puntero.service" >"$CONFIG/systemd/user/puntero.service"
systemctl --user daemon-reload
systemctl --user enable puntero.service >/dev/null 2>&1
systemctl --user restart puntero.service

# --- plugin de la barra de Omarchy ------------------------------------------
"$SRC/data/omarchy-plugin.sh" install "$APPDIR/omarchy-plugin"

say "Listo. Abre Puntero desde el menú de apps o con: puntero"
