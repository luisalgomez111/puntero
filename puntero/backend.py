# SPDX-License-Identifier: GPL-3.0-or-later
"""Motor de Puntero (servicio en segundo plano).

Corre aparte de la interfaz porque Solaar carga GTK3/Gdk3, que no puede convivir
con GTK4 en el mismo proceso, y porque los botones con atajos de teclado tienen
que funcionar aunque la ventana esté cerrada. Escucha en un socket Unix y habla
con cada cliente con una línea JSON por mensaje.

Eventos:  {"type": "device", "device": {...}}
          {"type": "removed", "id": "..."}
          {"type": "error", "reason": "...", "path": "..."}
          {"type": "result", "ok": bool, "device": "...", "setting": "...", "message": "..."}
Órdenes:  {"cmd": "set", "device": id, "setting": name, "value": v, "key": k}
          {"cmd": "set_button", "device": id, "cid": n, "action": {...} | null}
          {"cmd": "refresh"}
          {"cmd": "release_buttons"}   (al desinstalar: botones a su función original; responde {"type": "released"})
"""

import json
import logging
import os
import signal
import socket
import socketserver
import subprocess
import sys
import threading

from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib  # noqa: E402

from logitech_receiver.settings import Kind  # noqa: E402
from logitech_receiver.settings_validator import Range  # noqa: E402
from solaar import configuration  # noqa: E402
from solaar import listener  # noqa: E402

from puntero.buttons import DIVERT_SETTING, ButtonMapper  # noqa: E402
from puntero.i18n import localize  # noqa: E402

logger = logging.getLogger("puntero.backend")

SOCKET_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}", "puntero.sock")
REMAP_SETTING = "reprogrammable-keys"

KIND_NAMES = {
    Kind.TOGGLE: "toggle",
    Kind.CHOICE: "choice",
    Kind.RANGE: "range",
    Kind.MAP_CHOICE: "map_choice",
    Kind.MULTIPLE_TOGGLE: "multiple_toggle",
}

# Toda la E/S con los dispositivos pasa por un único hilo para no pisar peticiones.
_io = ThreadPoolExecutor(max_workers=1)
_clients = set()
_clients_lock = threading.Lock()
_devices = {}  # id -> Device
_ensured = set()  # dispositivos con los botones ya desviados en esta conexión
_buttons = ButtonMapper()
_buttons.on_dpi_cycle = lambda dev, values: _io.submit(_cycle_dpi, dev, values)
_loop = None


def emit(msg, only=None):
    data = (json.dumps(msg, ensure_ascii=False, default=str) + "\n").encode()
    with _clients_lock:
        targets = [only] if only else list(_clients)
    for wfile in targets:
        try:
            wfile.write(data)
            wfile.flush()
        except OSError:
            with _clients_lock:
                _clients.discard(wfile)


def device_id(dev):
    for attr in ("unitId", "serial"):
        try:
            value = getattr(dev, attr)
        except Exception:
            value = None
        if value and value not in ("00000000", "?"):
            return str(value)
    return f"{dev.path}:{dev.number}"


def _battery(dev):
    info = getattr(dev, "battery_info", None)
    if info is None and dev.online:
        try:
            info = dev.battery()
        except Exception:
            logger.exception("leyendo batería de %s", dev)
    if info is None or info.level is None:
        return None
    level = info.level
    return {
        "level": level if isinstance(level, int) and not hasattr(level, "name") else None,
        "approx": level.name.lower() if hasattr(level, "name") else None,
        "status": info.status.name.lower() if info.status is not None else None,
        "charging": bool(info.charging()),
        "voltage": info.voltage,
    }


def _choices(space):
    return [{"id": int(c), "label": str(c)} for c in space]


def _describe(dev, s, fresh=False):
    kind = KIND_NAMES.get(s.kind, "other")
    d = {
        "name": s.name,
        "label": str(s.label),
        "description": str(s.description or ""),
        "kind": kind,
        "value": None,
    }
    try:
        value = s.read(cached=not fresh)
    except Exception:
        logger.exception("leyendo %s de %s", s.name, dev)
        value = None
    if fresh and value is not None and s.persist and dev.persister is not None and dev.persister.get(s.name) != value:
        # El valor cambió en el propio ratón (p. ej. con su botón de DPI): se guarda para que
        # Solaar no le vuelva a aplicar el valor viejo la próxima vez que se conecte.
        dev.persister[s.name] = value

    if kind == "toggle":
        d["value"] = None if value is None else bool(value)
    elif kind == "range":
        d["min"], d["max"] = s.range
        d["value"] = value
    elif kind == "choice":
        d["choices"] = _choices(s.choices)
        d["value"] = None if value is None else int(value)
    elif kind == "map_choice":
        keys = []
        for k, space in s.choices.items():
            entry = {"id": int(k), "label": str(k)}
            if isinstance(space, Range):
                entry["min"], entry["max"] = space.min, space.max
            else:
                entry["choices"] = _choices(space)
            keys.append(entry)
        d["keys"] = keys
        d["value"] = {str(int(k)): int(v) for k, v in (value or {}).items() if v is not None}
    elif kind == "multiple_toggle":
        labels = getattr(s, "_labels", {})
        keys = []
        for k in s._validator.get_options():
            l1, l2 = labels.get(k, (None, None))
            keys.append({"id": int(k), "label": str(l1 or k), "description": str(l2 or "")})
        d["keys"] = keys
        d["value"] = {str(int(k)): bool(v) for k, v in (value or {}).items()}
    else:
        d["text"] = s.val_to_string(value) if value is not None else None
    return d


def _buttons_info(did, settings):
    """Botones configurables: los que se pueden reasignar o desviar."""
    remap = next((s for s in settings if s["name"] == REMAP_SETTING), None)
    divert = next((s for s in settings if s["name"] == DIVERT_SETTING), None)
    if not remap and not divert:
        return []
    actions = _buttons.actions_for(did)
    divertable = {k["id"] for k in divert["keys"]} if divert else set()
    source = remap or divert
    buttons = []
    for key in source["keys"]:
        cid = key["id"]
        buttons.append({
            "cid": cid,
            "label": key["label"],
            "remap_choices": key.get("choices", []) if remap else [],
            "remap": (remap["value"] or {}).get(str(cid)) if remap else None,
            "can_divert": cid in divertable,
            "action": actions.get(cid),
        })
    return buttons


def snapshot(dev, fresh=False):
    """Estado del dispositivo. `fresh` lee los ajustes del ratón en vez de usar la caché."""
    did = device_id(dev)
    info = {
        "id": did,
        "name": dev.name or dev.codename or "Dispositivo",
        "codename": dev.codename,
        "kind": str(dev.kind) if dev.kind is not None else "",
        "online": bool(dev.online),
        "bluetooth": bool(getattr(dev, "bluetooth", False)),
        "battery": None,
        "settings": [],
        "buttons": [],
    }
    if not dev.online:
        return info
    info["battery"] = _battery(dev)
    try:
        for s in dev.settings:
            if not s.display:
                continue
            if dev.persister and dev.persister.get_sensitivity(s.name) == "ignore":
                continue
            info["settings"].append(_describe(dev, s, fresh))
    except Exception:
        logger.exception("leyendo ajustes de %s", dev)
    info["buttons"] = _buttons_info(did, info["settings"])
    return localize(info)


def _publish(dev, only=None, fresh=False):
    try:
        emit({"type": "device", "device": snapshot(dev, fresh)}, only)
    except Exception:
        logger.exception("publicando %s", dev)


def status_changed(device, alert=None, reason=None, refresh=False):
    if device is None:
        return
    if not device:  # dispositivo "fantasma": se despareó o desapareció
        for did, dev in list(_devices.items()):
            if dev.receiver is device.receiver and dev.number == device.number:
                _devices.pop(did, None)
                emit({"type": "removed", "id": did})
        return
    if not getattr(device, "isDevice", False):
        return  # los receptores no se muestran; sus dispositivos llegan por separado
    did = device_id(device)
    if did not in _devices:
        _buttons.attach(device, did)
    _devices[did] = device
    if device.online and did not in _ensured:
        _ensured.add(did)
        _io.submit(_buttons.ensure, device, did)
    elif not device.online:
        _ensured.discard(did)  # al reconectar se vuelven a comprobar
    _io.submit(_publish, device)


def setting_changed(device, setting_class, vals):
    if device is not None and getattr(device, "isDevice", False):
        _io.submit(_publish, device)


def error_callback(reason, path):
    emit({"type": "error", "reason": getattr(reason, "name", str(reason)), "path": str(path)})


def _find_setting(dev, name):
    return next((s for s in dev.settings if s.name == name), None)


def _show_osd(value, values):
    """Muestra el DPI en el indicador de Omarchy (o como notificación si no está)."""
    payload = json.dumps({
        "icon": "󰍽",
        "value": values.index(value) + 1,
        "max": len(values),
        "progressText": f"{value} DPI",
        "duration": 1500,
    })
    for cmd in (["omarchy-shell", "osd", "show", payload],
                ["notify-send", "-a", "Puntero", "-t", "1500", "Sensibilidad", f"{value} DPI"]):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            continue


def _cycle_dpi(dev, values):
    """Pasa al siguiente DPI de la lista (lo llama el botón con la acción dpi_cycle)."""
    s = _find_setting(dev, "dpi")
    values = [int(v) for v in values]
    if s is None or not values:
        return
    current = s.read(cached=False)
    current = int(current) if current is not None else values[0]
    if current in values:
        target = values[(values.index(current) + 1) % len(values)]
    else:
        target = next((v for v in values if v > current), values[0])
    choice = next((c for c in s.choices if int(c) == target), None)
    if choice is None or s.write(choice) is None:
        logger.warning("no se pudo poner %s DPI en %s", target, dev)
        return
    _show_osd(target, values)
    _publish(dev)


def _write_setting(s, value, key):
    kind = KIND_NAMES.get(s.kind)
    if kind == "toggle":
        return s.write(bool(value))
    if kind == "range":
        lo, hi = s.range
        return s.write(max(lo, min(hi, int(value))))
    if kind == "choice":
        return s.write(next(c for c in s.choices if int(c) == int(value)))
    if kind == "map_choice":
        k = int(key)
        space = next(sp for kk, sp in s.choices.items() if int(kk) == k)
        v = int(value) if isinstance(space, Range) else next(c for c in space if int(c) == int(value))
        return s.write_key_value(k, v)
    if kind == "multiple_toggle":
        return s.write_key_value(int(key), bool(value))
    raise RuntimeError("este ajuste no se puede cambiar desde Puntero")


def _apply(cmd):
    did = cmd.get("device")
    name = cmd.get("setting") or f"button:{cmd.get('cid')}"
    dev = _devices.get(did)
    result = {"type": "result", "ok": False, "device": did, "setting": name, "message": ""}
    try:
        if dev is None or not dev.online:
            raise RuntimeError("el dispositivo no está conectado")
        if cmd["cmd"] == "set_button":
            _buttons.set_action(dev, did, int(cmd["cid"]), cmd.get("action"))
            result["ok"] = True
        else:
            s = _find_setting(dev, name)
            if s is None:
                raise RuntimeError(f"ajuste desconocido: {name}")
            result["ok"] = _write_setting(s, cmd.get("value"), cmd.get("key")) is not None
            if not result["ok"]:
                result["message"] = "el dispositivo no respondió"
    except StopIteration:
        result["message"] = "valor fuera de las opciones del ajuste"
    except Exception as e:
        logger.exception("aplicando %s", cmd)
        result["message"] = str(e)
    emit(result)
    if dev is not None:
        _publish(dev)


class ClientHandler(socketserver.StreamRequestHandler):
    def handle(self):
        with _clients_lock:
            _clients.add(self.wfile)
        emit({"type": "ready"}, self.wfile)
        for dev in list(_devices.values()):
            _io.submit(_publish, dev, self.wfile, True)
        try:
            for line in self.rfile:
                try:
                    cmd = json.loads(line)
                except ValueError:
                    continue
                if cmd.get("cmd") in ("set", "set_button"):
                    _io.submit(_apply, cmd)
                elif cmd.get("cmd") == "release_buttons":
                    # se espera a que termine para que quien lo pidió (el desinstalador)
                    # no detenga el servicio con los botones aún desviados
                    jobs = [_io.submit(_buttons.release, dev, did) for did, dev in list(_devices.items()) if dev.online]
                    for job in jobs:
                        job.result(timeout=30)
                    emit({"type": "released"}, self.wfile)
                elif cmd.get("cmd") == "refresh":
                    for dev in list(_devices.values()):
                        if dev.online:
                            _io.submit(_publish, dev, None, True)
        finally:
            with _clients_lock:
                _clients.discard(self.wfile)


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def _claim_socket():
    """Sale si ya hay otro motor escuchando; si el socket quedó huérfano, lo borra."""
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.connect(SOCKET_PATH)
        sys.exit("puntero-backend: ya hay un motor en marcha")
    except (FileNotFoundError, ConnectionRefusedError):
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
    finally:
        probe.close()


def main():
    global _loop
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="puntero-backend: %(levelname)s %(message)s")
    _claim_socket()
    server = Server(SOCKET_PATH, ClientHandler)
    os.chmod(SOCKET_PATH, 0o600)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    _loop = GLib.MainLoop()
    listener.setup_scanner(status_changed, setting_changed, error_callback)
    try:
        from solaar import dbus

        dbus.watch_suspend_resume(lambda: listener.ping_all(True))
    except Exception:
        logger.info("sin aviso de suspensión por D-Bus")
    GLib.idle_add(listener.start_all)
    try:
        from gi.repository import GLibUnix

        add_signal = GLibUnix.signal_add
    except ImportError:
        add_signal = GLib.unix_signal_add
    for sig in (signal.SIGTERM, signal.SIGINT):
        add_signal(GLib.PRIORITY_DEFAULT, sig, _loop.quit)
    try:
        _loop.run()
    finally:
        server.shutdown()
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        listener.stop_all()
        configuration.save()
        _io.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
