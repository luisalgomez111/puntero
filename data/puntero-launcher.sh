#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Lanzador de Puntero instalado desde un paquete (AUR). El programa vive en /usr/lib/puntero.
#
#   puntero            abre la app
#   puntero --setup    arranca el servicio y, en Omarchy, pone el plugin en la barra
#   puntero --reset    devuelve los botones a su función original y quita el plugin
#                      (conviene antes de desinstalar el paquete)
LIB=/usr/lib/puntero
export PYTHONPATH="$LIB${PYTHONPATH:+:$PYTHONPATH}"

case "${1:-}" in
--setup)
  systemctl --user daemon-reload
  systemctl --user enable --now puntero.service
  exec "$LIB/omarchy-plugin.sh" install /usr/share/puntero/omarchy-plugin
  ;;
--reset)
  /usr/bin/python3 -m puntero.release
  systemctl --user stop puntero.service 2>/dev/null
  exec "$LIB/omarchy-plugin.sh" remove
  ;;
esac
exec /usr/bin/python3 -m puntero "$@"
