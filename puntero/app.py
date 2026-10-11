# SPDX-License-Identifier: GPL-3.0-or-later
"""Interfaz de Puntero (GTK4 + libadwaita)."""

import json
import os
import shutil
import subprocess
import sys

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from evdev import ecodes  # noqa: E402

from puntero.i18n import KEY_NAMES, LANGUAGES, _, code_label, key_label, key_name, language_choice, localize, set_language_choice, system_language, text_label  # noqa: E402

APP_ID = "ve.puntero.Puntero"
ROOT = Path(__file__).resolve().parent
ART = ROOT / "art"
USER_IMAGES = Path(GLib.get_user_config_dir()) / "puntero" / "images"
SOCKET_PATH = os.path.join(GLib.get_user_runtime_dir(), "puntero.sock")

CSS = """
.hero {
  border-radius: 24px;
  padding: 28px;
  background: linear-gradient(135deg, alpha(@accent_bg_color, 0.20), alpha(@accent_bg_color, 0.03));
}
.device-art {
  background: radial-gradient(circle closest-side, alpha(white, 0.16), transparent);
}
.hero-name { font-size: 26pt; font-weight: 800; }
.battery-big { font-size: 20pt; font-weight: 700; font-feature-settings: "tnum"; }
.dim-row { opacity: 0.5; }
.capture-area { min-height: 120px; padding: 18px; }
.capture-area.capturing { box-shadow: inset 0 0 0 2px @accent_color; }
.text-area, .text-area text { background: transparent; }
.keycap {
  padding: 2px 8px;
  min-width: 12px;
  border-radius: 6px;
  font-weight: 600;
  background: alpha(currentColor, 0.08);
  box-shadow: 0 0 0 1px alpha(currentColor, 0.15);
}
.keycap-big {
  font-size: 16pt;
  min-width: 30px;
  padding: 8px 16px;
  border-radius: 10px;
}
"""

BATTERY_APPROX = {
    "empty": ("Vacía", 5),
    "critical": ("Crítica", 10),
    "low": ("Baja", 25),
    "good": ("Buena", 60),
    "full": ("Llena", 100),
}
KIND_TEXT = {
    "mouse": "Ratón",
    "keyboard": "Teclado",
    "trackball": "Trackball",
    "touchpad": "Panel táctil",
    "headset": "Auriculares",
    "numpad": "Teclado numérico",
}
CHARGING_TEXT = {
    "recharging": "Cargando",
    "almost_full": "Casi llena",
    "full": "Cargada",
    "slow_recharge": "Carga lenta",
}

def battery_summary(b):
    """Devuelve (fracción 0..1 o None, texto corto)."""
    if not b:
        return None, _("Batería desconocida")
    if b.get("level") is not None:
        frac, text = b["level"] / 100, f"{b['level']} %"
    elif b.get("approx") in BATTERY_APPROX:
        label, pct = BATTERY_APPROX[b["approx"]]
        frac, text = pct / 100, _(label)
    else:
        return None, _("Batería desconocida")
    if b.get("charging"):
        text += " · " + _(CHARGING_TEXT.get(b.get("status"), "Cargando"))
    return frac, text


def display_name(dev):
    """Nombre corto: «LIFT» en vez de «LIFT VERTICAL ERGONOMIC MOUSE»."""
    code = dev.get("codename")
    return code if code and len(code) < len(dev["name"]) else dev["name"]


def device_art(dev):
    """Imagen del dispositivo: primero la del usuario, después la ilustración propia."""
    for stem in filter(None, (dev.get("codename"), dev.get("name"))):
        for ext in ("png", "svg", "webp", "jpg"):
            path = USER_IMAGES / f"{stem}.{ext}"
            if path.exists():
                return path
    name = f"{dev.get('name', '')} {dev.get('codename', '')}".lower()
    if any(w in name for w in ("lift", "vertical", "mx vertical")):
        return ART / "mouse-vertical.svg"
    return ART / "mouse-generic.svg"


# ---------------------------------------------------------------- motor


class Backend:
    """Se conecta al servicio de Puntero (lo arranca si hace falta) y traduce sus líneas JSON."""

    def __init__(self, on_message, on_exit):
        self.on_message, self.on_exit = on_message, on_exit
        self.conn = None

    def start(self):
        self.attempts = 0
        self._connect()

    def _connect(self):
        client = Gio.SocketClient()
        client.connect_async(Gio.UnixSocketAddress.new(SOCKET_PATH), None, self._on_connected)
        return GLib.SOURCE_REMOVE

    def _on_connected(self, client, result):
        try:
            self.conn = client.connect_finish(result)
        except GLib.Error:
            self.attempts += 1
            if self.attempts == 1:
                self._launch()
            if self.attempts > 40:
                self.on_exit()
            else:
                GLib.timeout_add(250, self._connect)
            return
        self.out = self.conn.get_output_stream()
        self.inp = Gio.DataInputStream.new(self.conn.get_input_stream())
        self._read_next()

    def _launch(self):
        """Arranca el servicio de systemd; si no está instalado, el motor directamente."""
        launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
        launcher.set_cwd(str(ROOT.parent))
        cmd = f"systemctl --user start puntero.service 2>/dev/null || exec '{sys.executable}' -m puntero.backend"
        try:
            launcher.spawnv(["sh", "-c", cmd])
        except GLib.Error:
            pass

    def _read_next(self):
        self.inp.read_line_async(GLib.PRIORITY_DEFAULT, None, self._on_line)

    def _on_line(self, stream, result):
        try:
            line, _length = stream.read_line_finish_utf8(result)
        except GLib.Error:
            line = None
        if line is None:  # el servicio se reinició o se detuvo: volver a conectar
            self.conn = None
            self.start()
            return
        try:
            msg = json.loads(line)
        except ValueError:
            msg = None
        if msg:
            self.on_message(msg)
        self._read_next()

    def send(self, **cmd):
        if self.conn is None:
            return
        try:
            self.out.write_all((json.dumps(cmd) + "\n").encode(), None)
        except GLib.Error:
            pass

    def stop(self):
        if self.conn is not None:
            self.conn.close(None)
            self.conn = None


# ---------------------------------------------------------------- filas de ajustes


class SettingRow:
    """Envuelve el widget de un ajuste; `update` refresca sin disparar escrituras."""

    def __init__(self, page, setting):
        self.page, self.name, self.label = page, setting["name"], setting["label"]
        self.syncing = False
        self.widget = self.build(setting)
        if setting.get("description"):
            self.widget.set_tooltip_text(setting["description"])

    def send(self, value, key=None):
        self.page.send_setting(self.name, value, key)

    def update(self, setting):
        self.syncing = True
        try:
            self.set_value(setting)
        finally:
            self.syncing = False


class ToggleRow(SettingRow):
    def build(self, s):
        row = Adw.SwitchRow(title=s["label"])
        row.connect("notify::active", lambda r, _p: self.syncing or self.send(r.get_active()))
        return row

    def set_value(self, s):
        if s["value"] is not None:
            self.widget.set_active(s["value"])


class ChoiceRow(SettingRow):
    def build(self, s):
        self.ids = [c["id"] for c in s["choices"]]
        row = Adw.ComboRow(title=s["label"], model=Gtk.StringList.new([c["label"] for c in s["choices"]]))
        row.connect("notify::selected", self._changed)
        return row

    def _changed(self, row, _p):
        i = row.get_selected()
        if not self.syncing and 0 <= i < len(self.ids):
            self.send(self.ids[i])

    def set_value(self, s):
        if s["value"] in self.ids:
            self.widget.set_selected(self.ids.index(s["value"]))


class HostRow(ChoiceRow):
    """Easy-Switch: pide confirmación, porque el ratón se va a otro equipo."""

    def build(self, s):
        row = super().build(s)
        self.current = s["value"]
        self.choice_labels = [c["label"] for c in s["choices"]]
        return row

    def _changed(self, row, _p):
        i = row.get_selected()
        if self.syncing or not (0 <= i < len(self.ids)) or self.ids[i] == self.current:
            return
        dialog = Adw.AlertDialog(
            heading=_("¿Pasar el ratón a «{host}»?").format(host=self.choice_labels[i].split(" · ")[-1]),
            body=_("Dejará de funcionar en este equipo. Para volver, pulsa el botón Easy-Switch "
                   "de la parte de abajo del ratón hasta elegir este canal."),
        )
        dialog.add_response("cancel", _("Cancelar"))
        dialog.add_response("switch", _("Cambiar"))
        dialog.set_response_appearance("switch", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_response, i)
        dialog.present(row.get_root())

    def _on_response(self, _dialog, response, i):
        if response == "switch":
            self.send(self.ids[i])
        else:
            self.syncing = True
            self.widget.set_selected(self.ids.index(self.current))
            self.syncing = False

    def set_value(self, s):
        self.current = s["value"]
        super().set_value(s)


class SliderRow(SettingRow):
    """Deslizador para rangos y para listas numéricas largas (p. ej. DPI)."""

    def build(self, s):
        self.pending = None
        if s["kind"] == "choice":
            self.ids = [c["id"] for c in s["choices"]]
            self.labels = [c["label"] for c in s["choices"]]
            lo, hi = 0, len(self.ids) - 1
        else:
            self.ids = None
            lo, hi = s["min"], s["max"]
        row = Adw.ActionRow(title=s["label"])
        self.value_label = Gtk.Label(width_chars=6, xalign=1)
        self.value_label.add_css_class("numeric")
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
        self.scale.set_draw_value(False)
        self.scale.set_size_request(280, -1)
        self.scale.set_valign(Gtk.Align.CENTER)
        self.scale.connect("value-changed", self._changed)
        row.add_suffix(self.scale)
        row.add_suffix(self.value_label)
        return row

    def _text(self, v):
        return self.labels[v] if self.ids else str(v)

    def _changed(self, scale):
        v = round(scale.get_value())
        self.value_label.set_label(self._text(v))
        if self.syncing:
            return
        if self.pending:
            GLib.source_remove(self.pending)
        self.pending = GLib.timeout_add(350, self._flush)

    def _flush(self):
        self.pending = None
        v = round(self.scale.get_value())
        self.send(self.ids[v] if self.ids else v)
        return GLib.SOURCE_REMOVE

    def set_value(self, s):
        if self.pending or s["value"] is None:
            return  # el usuario está moviendo el deslizador
        if self.ids:
            if s["value"] not in self.ids:
                return
            v = self.ids.index(s["value"])
        else:
            v = s["value"]
        self.scale.set_value(v)
        self.value_label.set_label(self._text(v))


class MapChoiceRow(SettingRow):
    """Un desplegable por tecla o botón (p. ej. reasignar botones)."""

    def build(self, s):
        row = Adw.ExpanderRow(title=s["label"])
        self.subrows = {}
        for key in s["keys"]:
            k = str(key["id"])
            if "choices" in key:
                ids = [c["id"] for c in key["choices"]]
                sub = Adw.ComboRow(title=key["label"], model=Gtk.StringList.new([c["label"] for c in key["choices"]]))
                sub.connect("notify::selected", self._combo_changed, k, ids)
            else:
                ids = None
                sub = Adw.SpinRow.new_with_range(key["min"], key["max"], 1)
                sub.set_title(key["label"])
                sub.connect("notify::value", self._spin_changed, k)
            self.subrows[k] = (sub, ids)
            row.add_row(sub)
        return row

    def _combo_changed(self, sub, _p, k, ids):
        i = sub.get_selected()
        if not self.syncing and 0 <= i < len(ids):
            self.send(ids[i], key=int(k))

    def _spin_changed(self, sub, _p, k):
        if not self.syncing:
            self.send(int(sub.get_value()), key=int(k))

    def set_value(self, s):
        for k, v in (s["value"] or {}).items():
            if k not in self.subrows:
                continue
            sub, ids = self.subrows[k]
            if ids is None:
                sub.set_value(v)
            elif v in ids:
                sub.set_selected(ids.index(v))


class MultipleToggleRow(SettingRow):
    def build(self, s):
        row = Adw.ExpanderRow(title=s["label"])
        self.subrows = {}
        for key in s["keys"]:
            k = str(key["id"])
            sub = Adw.SwitchRow(title=key["label"])
            if key.get("description"):
                sub.set_tooltip_text(key["description"])
            sub.connect("notify::active", lambda r, _p, k=k: self.syncing or self.send(r.get_active(), key=int(k)))
            self.subrows[k] = sub
            row.add_row(sub)
        return row

    def set_value(self, s):
        for k, v in (s["value"] or {}).items():
            if k in self.subrows:
                self.subrows[k].set_active(v)


class InfoRow(SettingRow):
    def build(self, s):
        row = Adw.ActionRow(title=s["label"])
        row.add_css_class("property")
        return row

    def set_value(self, s):
        self.widget.set_subtitle(s.get("text") or "—")


def make_row(page, s):
    kind = s["kind"]
    if kind == "toggle":
        return ToggleRow(page, s)
    if kind == "range":
        return SliderRow(page, s)
    if s["name"] == "change-host":
        return HostRow(page, s)
    if kind == "choice":
        numeric = all(c["label"].isdigit() for c in s["choices"])
        return SliderRow(page, s) if numeric and len(s["choices"]) > 6 else ChoiceRow(page, s)
    if kind == "map_choice":
        return MapChoiceRow(page, s)
    if kind == "multiple_toggle":
        return MultipleToggleRow(page, s)
    return InfoRow(page, s)


# ---------------------------------------------------------------- botones


# Modificadores de GDK -> códigos evdev de la tecla izquierda correspondiente
MODIFIER_CODES = (
    (Gdk.ModifierType.CONTROL_MASK, 29, "Ctrl"),
    (Gdk.ModifierType.SHIFT_MASK, 42, "Shift"),
    (Gdk.ModifierType.ALT_MASK, 56, "Alt"),
    (Gdk.ModifierType.SUPER_MASK, 125, "Super"),
)
MODIFIER_KEYVAL_CODES = {
    Gdk.KEY_Control_L: 29, Gdk.KEY_Control_R: 29, Gdk.KEY_Shift_L: 42, Gdk.KEY_Shift_R: 42,
    Gdk.KEY_Alt_L: 56, Gdk.KEY_Alt_R: 56, Gdk.KEY_Meta_L: 56, Gdk.KEY_Meta_R: 56,
    Gdk.KEY_Super_L: 125, Gdk.KEY_Super_R: 125, Gdk.KEY_ISO_Level3_Shift: 100,
}

SHORTCUT_PRESETS = (
    ("Copiar", ["KEY_LEFTCTRL", "KEY_C"]),
    ("Pegar", ["KEY_LEFTCTRL", "KEY_V"]),
    ("Cortar", ["KEY_LEFTCTRL", "KEY_X"]),
    ("Deshacer", ["KEY_LEFTCTRL", "KEY_Z"]),
    ("Rehacer", ["KEY_LEFTCTRL", "KEY_LEFTSHIFT", "KEY_Z"]),
    ("Cambiar de ventana", ["KEY_LEFTALT", "KEY_TAB"]),
    ("Nueva pestaña", ["KEY_LEFTCTRL", "KEY_T"]),
    ("Cerrar pestaña", ["KEY_LEFTCTRL", "KEY_W"]),
    ("Reabrir pestaña cerrada", ["KEY_LEFTCTRL", "KEY_LEFTSHIFT", "KEY_T"]),
    ("Play / Pausa", ["KEY_PLAYPAUSE"]),
    ("Subir volumen", ["KEY_VOLUMEUP"]),
    ("Bajar volumen", ["KEY_VOLUMEDOWN"]),
    ("Enter", ["KEY_ENTER"]),
    ("Escape", ["KEY_ESC"]),
)

# (título, comando, programa que tiene que existir para ofrecerlo)
COMMAND_CANDIDATES = (
    ("Captura de pantalla", "omarchy capture screenshot", "omarchy"),
    ("Abrir terminal", "omarchy launch terminal", "omarchy"),
    ("Abrir navegador", "omarchy launch browser", "omarchy"),
    ("Menú de Omarchy", "omarchy-menu toggle root", "omarchy-menu"),
    ("Abrir la carpeta personal", "xdg-open ~", "xdg-open"),
    ("Silenciar el sonido", "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle", "wpctl"),
    ("Silenciar el micrófono", "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle", "wpctl"),
    ("Bloquear la pantalla", "loginctl lock-session", "loginctl"),
)


def command_presets():
    """Solo los comandos que existen en este sistema (p. ej. los de Omarchy si está instalado)."""
    return [(_(title), cmd) for title, cmd, needs in COMMAND_CANDIDATES if shutil.which(needs)]


def keyval_label(keyval):
    name = Gdk.keyval_name(Gdk.keyval_to_lower(keyval)) or "?"
    if name in KEY_NAMES:
        return key_label(name)
    if len(name) == 1:
        return name.upper()
    return Gtk.accelerator_get_label(Gdk.keyval_to_lower(keyval), 0) or name


def keycaps(names, big=False):
    """Fila de teclas dibujadas como teclas: [Ctrl] + [C]."""
    box = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
    for i, name in enumerate(names):
        if i:
            plus = Gtk.Label(label="+")
            plus.add_css_class("dim-label")
            box.append(plus)
        cap = Gtk.Label(label=name)
        cap.add_css_class("keycap")
        if big:
            cap.add_css_class("keycap-big")
        box.append(cap)
    return box


def button_summary(b):
    action = b.get("action")
    if action and action["type"] == "keys":
        return _("Atajo: {label}").format(label=action["label"])
    if action and action["type"] == "command":
        return _("Comando: {label}").format(label=action["label"])
    if action and action["type"] == "text":
        return _("Escribe: «{label}»").format(label=action["label"])
    if action and action["type"] == "dpi_cycle":
        return _("Ciclo de DPI: {label}").format(label=action["label"])
    if b.get("remap") is not None and b["remap"] != b["cid"]:
        label = next((c["label"] for c in b["remap_choices"] if c["id"] == b["remap"]), str(b["remap"]))
        return _("Funciona como: {label}").format(label=label)
    return _("Función original")


class ButtonRow:
    def __init__(self, page, button):
        self.page, self.button = page, button
        self.widget = Adw.ActionRow(title=button["label"], activatable=True)
        self.caps = Gtk.Box(valign=Gtk.Align.CENTER)
        self.widget.add_suffix(self.caps)
        self.widget.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        self.widget.connect("activated", lambda _r: ButtonDialog(self.page, self.button).present(self.widget.get_root()))

    def update(self, button):
        self.button = button
        action = button.get("action")
        child = self.caps.get_first_child()
        if child:
            self.caps.remove(child)
        if action and action["type"] == "keys":
            names = action.get("names") or [code_label(c) for c in action["codes"]]
            self.caps.append(keycaps(names))
            self.widget.set_subtitle(_("Atajo de teclado"))
        else:
            self.widget.set_subtitle(button_summary(button))


class ButtonDialog(Adw.Dialog):
    """Elige qué hace un botón: su función, otro botón, un atajo de teclado, un texto o un comando."""

    def __init__(self, page, button):
        super().__init__(title=button["label"], content_width=580, content_height=640)
        self.page, self.button = page, button
        self.mods = set()  # códigos evdev de los modificadores elegidos
        self.key = None  # (código evdev, nombre visible) de la tecla principal
        self.capturing = False
        action = button.get("action")

        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        cancel = Gtk.Button(label=_("Cancelar"))
        cancel.connect("clicked", lambda _b: self.close())
        self.save_button = Gtk.Button(label=_("Guardar"))
        self.save_button.add_css_class("suggested-action")
        self.save_button.connect("clicked", self._save)
        header.pack_start(cancel)
        header.pack_end(self.save_button)

        # pestañas: una por tipo de acción
        self.tabs = Adw.ToggleGroup(halign=Gtk.Align.CENTER, margin_top=6, margin_bottom=12)
        self.tabs.add_css_class("round")
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vhomogeneous=False)
        self._add_tab("default", _("Original"), self._page_default())
        if button["remap_choices"]:
            self._add_tab("remap", _("Otro botón"), self._page_remap())
        if button["can_divert"]:
            self._add_tab("keys", _("Teclado"), self._page_keys())
            self._add_tab("text", _("Texto"), self._page_text())
            self._add_tab("command", _("Comando"), self._page_command())
            self.dpi_choices = self._dpi_choices()
            if self.dpi_choices:
                self._add_tab("dpi", "DPI", self._page_dpi())
        self.tabs.connect("notify::active-name", self._on_tab)

        if action and action["type"] == "keys":
            self._set_shortcut(action["codes"], action.get("names"))
            self.tabs.set_active_name("keys")
        elif action and action["type"] == "text":
            self.text_buffer.set_text(action["text"])
            self.tabs.set_active_name("text")
        elif action and action["type"] == "command":
            self.command_row.set_text(action["command"])
            self.tabs.set_active_name("command")
        elif action and action["type"] == "dpi_cycle" and getattr(self, "dpi_choices", None):
            self.tabs.set_active_name("dpi")
        elif button.get("remap") not in (None, button["cid"]) and button["remap_choices"]:
            self.tabs.set_active_name("remap")
        else:
            self.tabs.set_active_name("default")
        self._on_tab()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_start=16, margin_end=16, margin_bottom=24)
        box.append(self.tabs)
        box.append(self.stack)
        view = Adw.ToolbarView(content=Gtk.ScrolledWindow(child=box, hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True))
        view.add_top_bar(header)
        self.set_child(view)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key_pressed)
        keys.connect("key-released", self._on_key_released)
        self.add_controller(keys)

    def _add_tab(self, name, label, widget):
        self.tabs.add(Adw.Toggle(name=name, label=label))
        self.stack.add_named(widget, name)

    def _on_tab(self, *_):
        name = self.tabs.get_active_name() or "default"
        self.stack.set_visible_child_name(name)
        if name != "keys":
            self._stop_capture()
        self._refresh()

    def _refresh(self):
        name = self.tabs.get_active_name() or "default"
        ready = {
            "keys": self.key is not None,
            "text": hasattr(self, "text_buffer") and bool(self._text()),
            "command": hasattr(self, "command_row") and bool(self.command_row.get_text().strip()),
            "dpi": len(self._dpi_values()) >= 2 if hasattr(self, "dpi_rows") else False,
        }.get(name, True)
        self.save_button.set_sensitive(ready and not self.capturing)

    # -- páginas

    def _page_default(self):
        original = next((c["label"] for c in self.button["remap_choices"] if c["id"] == self.button["cid"]), None)
        text = _("El botón hace su función de fábrica: <b>{original}</b>.").format(
            original=GLib.markup_escape_text(original)) if original else _("El botón hace su función de fábrica.")
        label = Gtk.Label(label=text, use_markup=True, wrap=True, margin_top=24, justify=Gtk.Justification.CENTER)
        label.add_css_class("dim-label")
        return label

    def _page_remap(self):
        group = Adw.PreferencesGroup(title=_("Que funcione como…"))
        self.remap_checks = {}
        first = None
        for c in self.button["remap_choices"]:
            if c["id"] == self.button["cid"]:
                continue
            row = Adw.ActionRow(title=c["label"], activatable=True)
            check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            if first:
                check.set_group(first)
            first = first or check
            row.add_prefix(check)
            row.set_activatable_widget(check)
            self.remap_checks[c["id"]] = check
            group.add(row)
        current = self.button.get("remap")
        (self.remap_checks.get(current) or first).set_active(True)
        return group

    def _page_keys(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        # zona de grabación: se hace clic y se pulsa la combinación
        self.capture_button = Gtk.Button()
        self.capture_button.add_css_class("capture-area")
        self.capture_button.add_css_class("card")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, valign=Gtk.Align.CENTER)
        self.keycaps_box = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        self.capture_hint = Gtk.Label()
        self.capture_hint.add_css_class("dim-label")
        inner.append(self.keycaps_box)
        inner.append(self.capture_hint)
        self.capture_button.set_child(inner)
        self.capture_button.connect("clicked", lambda _b: self._start_capture())
        page.append(self.capture_button)

        # modificadores que se pueden activar a mano (útil para Super, que Hyprland suele quedarse)
        mods = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        self.mod_toggles = {}
        for _mask, code, name in MODIFIER_CODES:
            t = Gtk.ToggleButton(label=name)
            t.add_css_class("pill")
            t.connect("toggled", self._on_mod_toggled, code)
            self.mod_toggles[code] = t
            mods.append(t)
        page.append(mods)

        group = Adw.PreferencesGroup(title=_("Atajos frecuentes"))
        for title, names in SHORTCUT_PRESETS:
            row = Adw.ActionRow(title=_(title), activatable=True)
            row.add_suffix(keycaps([key_label(n) for n in names]))
            row.connect("activated", lambda _r, names=names: self._set_shortcut([ecodes.ecodes[n] for n in names]))
            group.add(row)
        page.append(group)
        self._show_shortcut()
        return page

    def _page_text(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        group = Adw.PreferencesGroup(
            title=_("Texto que se escribe"),
            description=_("Al pulsar el botón se escribe este texto donde esté el cursor: un saludo, "
                          "una firma, tu correo… Puede tener varias líneas."))
        self.text_buffer = Gtk.TextBuffer()
        self.text_buffer.connect("changed", lambda *_: self._refresh())
        view = Gtk.TextView(buffer=self.text_buffer, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                            top_margin=12, bottom_margin=12, left_margin=12, right_margin=12)
        view.add_css_class("text-area")
        frame = Gtk.ScrolledWindow(child=view, min_content_height=140, hscrollbar_policy=Gtk.PolicyType.NEVER)
        frame.add_css_class("card")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        group.add(frame)
        page.append(group)
        if not shutil.which("wtype") and not shutil.which("xdotool"):
            hint = Gtk.Label(wrap=True, xalign=0,
                             label=_("Para escribir acentos, ñ y símbolos instala wtype (Wayland) o xdotool (X11). "
                                     "Sin ellos solo se escriben letras sin acento, números y espacios."))
            hint.add_css_class("dim-label")
            hint.add_css_class("caption")
            page.append(hint)
        return page

    def _text(self):
        start, end = self.text_buffer.get_bounds()
        return self.text_buffer.get_text(start, end, False).rstrip("\n")

    def _page_command(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        entry_group = Adw.PreferencesGroup(description=_("Se ejecuta al pulsar el botón, como en una terminal."))
        self.command_row = Adw.EntryRow(title=_("Comando"))
        self.command_row.connect("changed", lambda *_: self._refresh())
        entry_group.add(self.command_row)
        page.append(entry_group)
        group = Adw.PreferencesGroup(title=_("Comandos frecuentes"))
        presets = command_presets()
        group.set_visible(bool(presets))
        for title, command in presets:
            row = Adw.ActionRow(title=title, subtitle=command, activatable=True)
            row.add_css_class("property")
            row.connect("activated", lambda _r, c=command: self.command_row.set_text(c))
            group.add(row)
        page.append(group)
        return page

    # -- ciclo de DPI

    def _dpi_choices(self):
        dpi = next((s for s in self.page.dev["settings"] if s["name"] == "dpi" and s.get("choices")), None)
        return [c["id"] for c in dpi["choices"]] if dpi else []

    def _nearest_dpi(self, value):
        return min(self.dpi_choices, key=lambda c: abs(c - value))

    def _page_dpi(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.dpi_group = Adw.PreferencesGroup(
            title=_("Puntos de DPI"),
            description=_("Cada pulsación del botón pasa al siguiente punto. Después del último vuelve al primero."),
        )
        add = Gtk.Button(icon_name="list-add-symbolic", valign=Gtk.Align.CENTER, tooltip_text=_("Añadir un punto"))
        add.add_css_class("flat")
        add.connect("clicked", lambda _b: self._add_dpi_row(self._suggest_dpi()))
        self.dpi_group.set_header_suffix(add)
        self.dpi_add = add
        self.dpi_rows = []
        action = self.button.get("action")
        if action and action["type"] == "dpi_cycle":
            values = action["values"]
        else:
            values = sorted({self._nearest_dpi(v) for v in (800, 1600, 3200)})
        for v in values:
            self._add_dpi_row(v)
        page.append(self.dpi_group)
        note = Gtk.Label(
            label=_("Al cambiar verás el DPI en pantalla. Puedes tener entre 2 y 5 puntos."),
            wrap=True, xalign=0,
        )
        note.add_css_class("dim-label")
        note.add_css_class("caption")
        page.append(note)
        return page

    def _suggest_dpi(self):
        used = set(self._dpi_values())
        top = max(used) if used else self.dpi_choices[0]
        return next((c for c in self.dpi_choices if c > top and c not in used),
                    next((c for c in self.dpi_choices if c not in used), self.dpi_choices[-1]))

    def _add_dpi_row(self, value):
        if len(self.dpi_rows) >= 5:
            return
        lo, hi = self.dpi_choices[0], self.dpi_choices[-1]
        step = self.dpi_choices[1] - lo if len(self.dpi_choices) > 1 else 1
        row = Adw.SpinRow.new_with_range(lo, hi, step)
        row.set_value(self._nearest_dpi(value))
        row.connect("notify::value", lambda *_: self._refresh_dpi())
        remove = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, tooltip_text=_("Quitar este punto"))
        remove.add_css_class("flat")
        remove.connect("clicked", lambda _b: self._remove_dpi_row(row))
        row.add_suffix(remove)
        row.remove_button = remove
        self.dpi_group.add(row)
        self.dpi_rows.append(row)
        self._refresh_dpi()

    def _remove_dpi_row(self, row):
        if len(self.dpi_rows) <= 2:
            return
        self.dpi_rows.remove(row)
        self.dpi_group.remove(row)
        self._refresh_dpi()

    def _refresh_dpi(self):
        for i, row in enumerate(self.dpi_rows, 1):
            row.set_title(_("Punto {n}").format(n=i))
            row.remove_button.set_sensitive(len(self.dpi_rows) > 2)
        self.dpi_add.set_sensitive(len(self.dpi_rows) < 5)
        self._refresh()

    def _dpi_values(self):
        """Valores válidos, sin repetir y de menor a mayor."""
        return sorted({self._nearest_dpi(int(r.get_value())) for r in getattr(self, "dpi_rows", [])})

    # -- atajo de teclado

    def _set_shortcut(self, codes, names=None):
        names = names or [code_label(c) for c in codes]
        mod_codes = {code for _m, code, _n in MODIFIER_CODES}
        self.mods = {c for c in codes if c in mod_codes}
        rest = [(c, n) for c, n in zip(codes, names) if c not in mod_codes]
        self.key = rest[-1] if rest else None
        self._show_shortcut()

    def _shortcut(self):
        """(códigos, nombres) en orden Ctrl, Shift, Alt, Super, tecla."""
        if self.key is None:
            return None
        pairs = [(code, name) for _m, code, name in MODIFIER_CODES if code in self.mods] + [self.key]
        return [c for c, _n in pairs], [n for _c, n in pairs]

    def _show_shortcut(self, live_mods=None):
        if not hasattr(self, "keycaps_box"):
            return
        child = self.keycaps_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.keycaps_box.remove(child)
            child = nxt
        if self.capturing:
            names = [name for _m, code, name in MODIFIER_CODES if code in (live_mods or set())]
            self.capture_hint.set_label(_("Pulsa la combinación… (Esc para cancelar)"))
            self.keycaps_box.append(keycaps(names + ["…"], big=True))
        elif self.key is not None:
            self.capture_hint.set_label(_("Haz clic para grabar otra"))
            self.keycaps_box.append(keycaps(self._shortcut()[1], big=True))
        else:
            self.capture_hint.set_label(_("Haz clic aquí y pulsa la tecla o combinación"))
            icon = Gtk.Image(icon_name="input-keyboard-symbolic", pixel_size=32)
            self.keycaps_box.append(icon)
        shown = (live_mods or set()) if self.capturing else self.mods
        for code, toggle in self.mod_toggles.items():
            toggle.handler_block_by_func(self._on_mod_toggled)
            toggle.set_active(code in shown)
            toggle.handler_unblock_by_func(self._on_mod_toggled)
        self._refresh()

    def _on_mod_toggled(self, toggle, code):
        if toggle.get_active():
            self.mods.add(code)
        else:
            self.mods.discard(code)
        self._show_shortcut()

    def _start_capture(self):
        self.capturing = True
        self.capture_button.add_css_class("capturing")
        self._show_shortcut(set())
        self.grab_focus()

    def _stop_capture(self):
        if not self.capturing:
            return
        self.capturing = False
        self.capture_button.remove_css_class("capturing")
        self._show_shortcut()

    def _live_mods(self, state, keyval=None, pressed=True):
        mods = {code for mask, code, _n in MODIFIER_CODES if state & mask}
        extra = MODIFIER_KEYVAL_CODES.get(keyval)
        if extra:
            (mods.add if pressed else mods.discard)(extra)
        return mods

    def _on_key_pressed(self, _ctrl, keyval, keycode, state):
        if not self.capturing:
            return False
        if keyval == Gdk.KEY_Escape and not (state & Gtk.accelerator_get_default_mod_mask()):
            self._stop_capture()
            return True
        if keyval in MODIFIER_KEYVAL_CODES:
            self._show_shortcut(self._live_mods(state, keyval))
            return True
        self.mods = self._live_mods(state)
        self.key = (keycode - 8, keyval_label(keyval))  # código XKB -> código evdev
        self._stop_capture()
        return True

    def _on_key_released(self, _ctrl, keyval, _keycode, state):
        if self.capturing and keyval in MODIFIER_KEYVAL_CODES:
            self._show_shortcut(self._live_mods(state, keyval, pressed=False))

    # -- guardar

    def _save(self, _button):
        b, choice = self.button, self.tabs.get_active_name()
        send = self.page.window.backend.send
        did, cid = self.page.dev_id, b["cid"]
        action = None
        if choice == "keys":
            codes, names = self._shortcut()
            action = {"type": "keys", "codes": codes, "names": names, "label": "+".join(names)}
        elif choice == "text":
            text = self._text()
            action = {"type": "text", "text": text, "label": text_label(text)}
        elif choice == "command":
            command = self.command_row.get_text().strip()
            action = {"type": "command", "command": command, "label": command}
        elif choice == "dpi":
            values = self._dpi_values()
            action = {"type": "dpi_cycle", "values": values, "label": " · ".join(map(str, values)) + " DPI"}

        if action or b.get("action"):
            send(cmd="set_button", device=did, cid=cid, action=action)
        if b["remap_choices"]:
            target = cid
            if choice == "remap":
                target = next(k for k, check in self.remap_checks.items() if check.get_active())
            if target != b.get("remap"):
                send(cmd="set", device=did, setting="reprogrammable-keys", key=cid, value=target)
        self.close()


# ---------------------------------------------------------------- página de dispositivo


class DevicePage(Gtk.ScrolledWindow):
    def __init__(self, window, dev):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.window, self.dev_id = window, dev["id"]
        self.signature = None
        self.rows = {}

        clamp = Adw.Clamp(maximum_size=760, margin_top=24, margin_bottom=32, margin_start=16, margin_end=16)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        clamp.set_child(self.box)
        self.set_child(clamp)

        hero = Gtk.Box(spacing=24)
        hero.add_css_class("hero")
        # Gtk.Image escala la imagen dentro de un cuadrado de pixel_size, sea cual sea su tamaño real
        self.picture = Gtk.Image(pixel_size=240)
        self.picture.add_css_class("device-art")
        self.art_path = None
        hero.append(self.picture)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER, hexpand=True)
        self.name_label = Gtk.Label(xalign=0, wrap=True)
        self.name_label.add_css_class("hero-name")
        self.sub_label = Gtk.Label(xalign=0)
        self.sub_label.add_css_class("dim-label")
        self.battery_label = Gtk.Label(xalign=0, margin_top=12)
        self.battery_label.add_css_class("battery-big")
        self.battery_bar = Gtk.LevelBar(min_value=0, max_value=1)
        self.battery_bar.set_size_request(220, -1)
        self.battery_bar.set_halign(Gtk.Align.START)
        for w in (self.name_label, self.sub_label, self.battery_label, self.battery_bar):
            info.append(w)
        hero.append(info)
        self.box.append(hero)

        self.groups, self.button_rows = [], {}
        self.update(dev)

    def send_setting(self, name, value, key=None):
        self.window.backend.send(cmd="set", device=self.dev_id, setting=name, value=value, key=key)

    def update(self, dev):
        self.dev = dev
        art = device_art(dev)
        if art != self.art_path:
            self.art_path = art
            self.picture.set_from_paintable(Gdk.Texture.new_from_filename(str(art)))
        self.name_label.set_label(display_name(dev))
        kind = dev.get("kind", "").lower()
        parts = [_(KIND_TEXT[kind]) if kind in KIND_TEXT else kind.capitalize()]
        if dev.get("codename") and dev["codename"] != dev["name"]:
            parts = [dev["name"].title()]
        if dev.get("bluetooth"):
            parts.append("Bluetooth")
        parts = [p for p in parts if p]
        parts.append(_("Conectado") if dev["online"] else _("Desconectado"))
        self.sub_label.set_label(" · ".join(parts))
        frac, text = battery_summary(dev.get("battery"))
        self.battery_label.set_label(text if dev["online"] else _("Sin conexión"))
        self.battery_bar.set_visible(frac is not None and dev["online"])
        if frac is not None:
            self.battery_bar.set_value(frac)

        signature = (
            tuple((s["name"], s["kind"]) for s in dev["settings"]),
            tuple(b["cid"] for b in dev.get("buttons", [])),
        )
        if signature != self.signature:
            self._rebuild(dev["settings"], dev.get("buttons", []))
            self.signature = signature
        for s in dev["settings"]:
            self.rows[s["name"]].update(s)
        for b in dev.get("buttons", []):
            self.button_rows[b["cid"]].update(b)
        for group in self.groups:
            group.set_sensitive(dev["online"])

    def _rebuild(self, settings, buttons):
        for group in self.groups:
            self.box.remove(group)
        self.groups, self.rows, self.button_rows = [], {}, {}
        if buttons:
            group = Adw.PreferencesGroup(
                title=_("Botones"),
                description=_("Asigna a cada botón otra función del ratón, un atajo de teclado, un texto o un comando."),
            )
            for b in buttons:
                row = ButtonRow(self, b)
                self.button_rows[b["cid"]] = row
                group.add(row.widget)
            self.box.append(group)
            self.groups.append(group)
        sections = (
            ("Ajustes", lambda s: s["kind"] in ("toggle", "choice", "range") and s["name"] != "change-host"),
            ("Otros botones y teclas", lambda s: s["kind"] in ("map_choice", "multiple_toggle")),
            ("Easy-Switch", lambda s: s["name"] == "change-host"),
            ("Información", lambda s: s["kind"] == "other"),
        )
        for title, wanted in sections:
            items = [s for s in settings if wanted(s)]
            if not items:
                continue
            group = Adw.PreferencesGroup(title=_(title))
            for s in items:
                row = make_row(self, s)
                self.rows[s["name"]] = row
                group.add(row.widget)
            self.box.append(group)
            self.groups.append(group)
        if not settings and not buttons:
            group = Adw.PreferencesGroup()
            group.add(Adw.ActionRow(title=_("Este dispositivo no expone ajustes")))
            self.box.append(group)
            self.groups.append(group)


# ---------------------------------------------------------------- ventana


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Puntero", default_width=1000, default_height=720)
        self.devices, self.pages, self.sidebar_rows = {}, {}, {}
        self.permission_error = False

        self.toasts = Adw.ToastOverlay()
        self.split = Adw.NavigationSplitView()
        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 640sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)

        # barra lateral
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.listbox.add_css_class("navigation-sidebar")
        self.listbox.connect("row-selected", self._on_row_selected)
        side_header = Adw.HeaderBar()
        side_header.pack_end(self._main_menu())
        side_view = Adw.ToolbarView()
        side_view.add_top_bar(side_header)
        side_view.set_content(Gtk.ScrolledWindow(child=self.listbox, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.split.set_sidebar(Adw.NavigationPage(title="Puntero", child=side_view))

        # contenido
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.banner = Adw.Banner(title=_("Sin permiso para acceder a un dispositivo Logitech"))
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self.banner)
        content.append(self.stack)
        self.stack.set_vexpand(True)
        self.content_view = Adw.ToolbarView()
        self.content_view.add_top_bar(Adw.HeaderBar())
        self.content_view.set_content(content)
        self.content_page = Adw.NavigationPage(title=_("Dispositivo"), child=self.content_view)
        self.split.set_content(self.content_page)

        self.searching = Adw.StatusPage(
            icon_name="input-mouse-symbolic",
            title=_("Buscando dispositivos"),
            description=_("Enciende tu ratón o teclado Logitech."),
        )
        spinner = Adw.Spinner()
        spinner.set_size_request(32, 32)
        self.searching.set_child(spinner)
        self.stack.add_named(self.searching, "searching")

        self.no_perm = Adw.StatusPage(
            icon_name="dialog-password-symbolic",
            title=_("Falta permiso"),
            description=(
                _("El sistema no deja leer el dispositivo. Instala Solaar (trae las reglas udev) y ejecuta:") + "\n\n"
                "<tt>sudo udevadm control --reload &amp;&amp; sudo udevadm trigger</tt>\n\n"
                + _("Después apaga y enciende el ratón.")
            ),
        )
        self.stack.add_named(self.no_perm, "permissions")

        self.dead = Adw.StatusPage(icon_name="dialog-error-symbolic", title=_("El motor se detuvo"))
        retry = Gtk.Button(label=_("Reiniciar"), halign=Gtk.Align.CENTER)
        retry.add_css_class("pill")
        retry.add_css_class("suggested-action")
        retry.connect("clicked", lambda _b: self.start_backend())
        self.dead.set_child(retry)
        self.stack.add_named(self.dead, "dead")

        self.backend = Backend(self.on_message, self.on_backend_exit)
        self.start_backend()
        self.connect("close-request", lambda _w: self.backend.stop() or False)

    def _main_menu(self):
        languages = Gio.Menu()
        system = {"es": "Español", "en": "English"}[system_language()]
        for choice, label in (("auto", _("Automático: {language}").format(language=system)), ("es", "Español"), ("en", "English")):
            languages.append(label, f"app.language::{choice}")
        menu = Gio.Menu()
        menu.append_section(_("Idioma"), languages)
        return Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text=_("Menú principal"))

    # -- motor

    def start_backend(self):
        self.stack.set_visible_child_name("searching")
        try:
            self.backend.start()
        except GLib.Error as e:
            self.dead.set_description(_("No se pudo iniciar: {error}").format(error=e.message))
            self.stack.set_visible_child_name("dead")

    def on_backend_exit(self):
        """El servicio no responde después de varios intentos de conexión."""
        self.dead.set_description(
            _("El proceso que habla con los dispositivos terminó. "
              "Comprueba que Solaar está instalado (<tt>sudo pacman -S solaar</tt>).")
        )
        self.stack.set_visible_child_name("dead")

    def on_message(self, msg):
        t = msg.get("type")
        if t == "device":
            self.on_device(msg["device"])
        elif t == "removed":
            self.on_removed(msg["id"])
        elif t == "error":
            if msg.get("reason") == "PERMISSIONS":
                self.permission_error = True
                self.banner.set_revealed(bool(self.devices))
                if not self.devices:
                    self.stack.set_visible_child_name("permissions")
        elif t == "result" and not msg.get("ok"):
            page = self.pages.get(msg.get("device"))
            name = msg.get("setting") or ""
            if page and name.startswith("button:"):
                row = page.button_rows.get(int(name.split(":")[1]))
                label = row.button["label"] if row else name
            else:
                row = page.rows.get(name) if page else None
                label = row.label if row else name
            self.toasts.add_toast(Adw.Toast(title=_("No se pudo cambiar «{label}»: {error}").format(
                label=label, error=_(msg.get("message") or ""))))

    # -- dispositivos

    def on_device(self, dev):
        localize(dev)
        did = dev["id"]
        self.devices[did] = dev
        if did in self.pages:
            self.pages[did].update(dev)
        else:
            page = DevicePage(self, dev)
            self.pages[did] = page
            self.stack.add_named(page, did)
            row = self._sidebar_row(dev)
            self.sidebar_rows[did] = row
            self.listbox.append(row)
            if self.listbox.get_selected_row() is None:
                self.listbox.select_row(row)
        self._refresh_sidebar_row(dev)
        if self.permission_error:
            self.banner.set_revealed(True)

    def on_removed(self, did):
        self.devices.pop(did, None)
        page = self.pages.pop(did, None)
        if page:
            self.stack.remove(page)
        row = self.sidebar_rows.pop(did, None)
        if row:
            self.listbox.remove(row)
        if not self.devices:
            self.stack.set_visible_child_name("permissions" if self.permission_error else "searching")

    def _sidebar_row(self, dev):
        row = Adw.ActionRow(title=display_name(dev))
        row.add_prefix(Gtk.Image(icon_name="input-mouse-symbolic"))
        row.dev_id = dev["id"]
        return row

    def _refresh_sidebar_row(self, dev):
        row = self.sidebar_rows[dev["id"]]
        row.set_title(display_name(dev))
        _frac, text = battery_summary(dev.get("battery"))
        row.set_subtitle(text if dev["online"] else _("Desconectado"))
        if dev["online"]:
            row.remove_css_class("dim-row")
        else:
            row.add_css_class("dim-row")

    def _on_row_selected(self, _box, row):
        did = getattr(row, "dev_id", None)
        if did in self.pages:
            self.stack.set_visible_child(self.pages[did])
            self.content_page.set_title(display_name(self.devices[did]))
            self.split.set_show_content(True)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self):
        Adw.Application.do_startup(self)
        action = Gio.SimpleAction.new_stateful("language", GLib.VariantType.new("s"), GLib.Variant("s", language_choice()))
        action.connect("change-state", self._on_language)
        self.add_action(action)
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self):
        win = self.get_active_window() or Window(self)
        win.present()

    def _on_language(self, action, value):
        choice = value.get_string()
        if choice not in LANGUAGES or choice == action.get_state().get_string():
            return
        action.set_state(value)
        set_language_choice(choice)
        # el servicio y el plugin de la barra toman los textos nuevos al reiniciarse
        # el motor; la ventana se vuelve a abrir para construirse en el idioma nuevo
        subprocess.run(["systemctl", "--user", "try-restart", "puntero.service"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        win = self.get_active_window()
        if win:
            win.backend.stop()
        os.execv(sys.executable, [sys.executable, "-m", "puntero", *sys.argv[1:]])


def main():
    return App().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
