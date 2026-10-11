# SPDX-License-Identifier: GPL-3.0-or-later
"""Acciones personalizadas para los botones del ratón.

El ratón solo sabe cambiar un botón por otro botón del ratón. Para que un botón
lance un atajo de teclado o un comando, se "desvía" (divert-keys = Diverted):
el ratón deja de enviar el clic y en su lugar avisa por HID++ con la lista de
botones desviados que están pulsados. Aquí se traduce ese aviso en teclas
simuladas con uinput, o en un comando.

Acciones guardadas en ~/.config/puntero/buttons.json:
    {"<id dispositivo>": {"<cid>": {"type": "keys", "codes": [29, 46], "label": "Ctrl+C"}}}
    {"type": "command", "command": "omarchy-capture-screenshot", "label": "..."}
    {"type": "dpi_cycle", "values": [800, 1600, 3200], "label": "800 · 1600 · 3200 DPI"}
"""

import json
import logging
import os
import struct
import subprocess
import threading

from pathlib import Path

from logitech_receiver.hidpp20_constants import SupportedFeature

logger = logging.getLogger("puntero.buttons")

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "puntero" / "buttons.json"
DIVERT_SETTING = "divert-keys"
DIVERT_REGULAR, DIVERT_DIVERTED = 0, 1


class Keyboard:
    """Teclado virtual de uinput, creado la primera vez que hace falta."""

    def __init__(self):
        self._dev = None
        self._lock = threading.Lock()

    def _device(self):
        if self._dev is None:
            import evdev

            keys = [c for c in evdev.ecodes.keys if isinstance(c, int) and 0 < c < 0x2FF]
            self._dev = evdev.UInput({evdev.ecodes.EV_KEY: keys}, name="puntero-keyboard")
        return self._dev

    def press(self, codes, down):
        import evdev

        with self._lock:
            try:
                dev = self._device()
                for code in codes if down else reversed(codes):
                    dev.write(evdev.ecodes.EV_KEY, code, 1 if down else 0)
                dev.syn()
            except Exception:
                logger.exception("no se pudo simular %s", codes)


class ButtonMapper:
    def __init__(self):
        self.keyboard = Keyboard()
        self.actions = self._load()
        self._pressed = {}  # id dispositivo -> set de CIDs pulsados
        self.on_dpi_cycle = None  # lo asigna el motor: fn(dispositivo, lista de DPI)

    def _load(self):
        try:
            return json.loads(CONFIG.read_text())
        except FileNotFoundError:
            return {}
        except Exception:
            logger.exception("leyendo %s", CONFIG)
            return {}

    def _save(self):
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.actions, indent=2, ensure_ascii=False))
        tmp.replace(CONFIG)

    def actions_for(self, did):
        return {int(cid): a for cid, a in self.actions.get(did, {}).items()}

    def _divert(self, dev, cid, diverted):
        divert = next((s for s in dev.settings if s.name == DIVERT_SETTING), None)
        if divert is None:
            raise RuntimeError("este dispositivo no permite desviar botones")
        state = DIVERT_DIVERTED if diverted else DIVERT_REGULAR
        space = next(sp for k, sp in divert.choices.items() if int(k) == cid)
        value = next(c for c in space if int(c) == state)
        if divert.write_key_value(cid, value) is None:
            raise RuntimeError("el ratón no aceptó el cambio")

    def set_action(self, dev, did, cid, action):
        """Guarda la acción (None = predeterminada) y desvía o restaura el botón."""
        self._divert(dev, cid, bool(action))
        per_dev = self.actions.setdefault(did, {})
        if action:
            per_dev[str(cid)] = action
        else:
            per_dev.pop(str(cid), None)
            if not per_dev:
                self.actions.pop(did, None)
        self._save()

    def ensure(self, dev, did):
        """Vuelve a desviar los botones con acción guardada (p. ej. tras reinstalar)."""
        for cid in self.actions_for(did):
            try:
                self._divert(dev, cid, True)
            except Exception:
                logger.exception("no se pudo desviar el botón %s de %s", cid, dev)

    def release(self, dev, did):
        """Devuelve los botones a su función original sin olvidar las acciones guardadas."""
        for cid in self.actions_for(did):
            try:
                self._divert(dev, cid, False)
            except Exception:
                logger.exception("no se pudo restaurar el botón %s de %s", cid, dev)

    def attach(self, dev, did):
        dev.add_notification_handler("puntero-buttons", lambda d, n: self._on_notification(did, d, n))

    def _on_notification(self, did, dev, n):
        if n.sub_id >= 0x40 or n.address != 0x00 or not dev.features:
            return None
        try:
            if dev.features.get_feature(n.sub_id) != SupportedFeature.REPROG_CONTROLS_V4:
                return None
        except IndexError:
            return None
        now = {c for c in struct.unpack("!HHHH", n.data[:8]) if c}
        before = self._pressed.get(did, set())
        self._pressed[did] = now
        actions = self.actions_for(did)
        for cid in now - before:
            self._run(dev, actions.get(cid), down=True)
        for cid in before - now:
            self._run(dev, actions.get(cid), down=False)
        return True if (now | before) & actions.keys() else None

    def _run(self, dev, action, down):
        if not action:
            return
        if action["type"] == "keys":
            # el atajo se mantiene mientras el botón esté pulsado (sirve para Ctrl, Alt+Tab…)
            self.keyboard.press(action["codes"], down)
        elif action["type"] == "dpi_cycle" and down and self.on_dpi_cycle:
            self.on_dpi_cycle(dev, action["values"])
        elif action["type"] == "command" and down:
            subprocess.Popen(["sh", "-c", action["command"]], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
