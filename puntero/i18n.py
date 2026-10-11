# SPDX-License-Identifier: GPL-3.0-or-later
"""Idiomas de Puntero (español e inglés) y textos de los ajustes y botones de Solaar.

Los textos del programa se escriben en español y `_()` los pasa al inglés con el
catálogo de puntero/lang_en.py. El idioma se elige en la app y se guarda en
~/.config/puntero/settings.json; con "auto" se usa el del sistema (español si el
idioma del sistema es español, inglés en cualquier otro caso).

`localize` lo aplica el motor a cada dispositivo antes de enviarlo, así todos los
clientes (la ventana y el plugin de la barra) reciben los mismos textos. Solaar
siempre entrega sus etiquetas en inglés; en español se traducen con TEXT y, si no
están ahí, con la traducción del propio Solaar.
"""

import gettext
import json
import os

from pathlib import Path

from evdev import ecodes

from puntero.lang_en import EN

LANGUAGES = ("auto", "es", "en")
SETTINGS = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "puntero" / "settings.json"
_cache = {"mtime": None, "choice": "auto"}


def language_choice():
    """Lo elegido en la app: "auto", "es" o "en"."""
    try:
        mtime = SETTINGS.stat().st_mtime
    except OSError:
        mtime = None
    if mtime != _cache["mtime"]:
        _cache["mtime"] = mtime
        try:
            choice = json.loads(SETTINGS.read_text()).get("language", "auto")
        except Exception:
            choice = "auto"
        _cache["choice"] = choice if choice in LANGUAGES else "auto"
    return _cache["choice"]


def _detect_system_language():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return "es" if value.split(":")[0].lower().startswith("es") else "en"
    return "en"


# se mira al importar: el motor cambia LANGUAGE después para que Solaar hable en inglés
_SYSTEM_LANGUAGE = _detect_system_language()


def system_language():
    return _SYSTEM_LANGUAGE


def language():
    """Idioma en uso: "es" o "en"."""
    choice = language_choice()
    return system_language() if choice == "auto" else choice


def set_language_choice(choice):
    try:
        data = json.loads(SETTINGS.read_text())
    except Exception:
        data = {}
    data["language"] = choice
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(SETTINGS)


def _(text):
    """Traduce un texto del programa (escrito en español) al idioma en uso."""
    return EN.get(text, text) if language() == "en" else text


_solaar_es = None


def _solaar_spanish(text):
    """Traducción al español que trae Solaar (para etiquetas que Puntero no conoce)."""
    global _solaar_es
    if _solaar_es is None:
        try:
            from solaar.i18n import _find_locale_path

            _solaar_es = gettext.translation("solaar", _find_locale_path("solaar"), languages=["es"])
        except Exception:
            _solaar_es = gettext.NullTranslations()
    return _solaar_es.gettext(text)


def _label(text):
    if language() == "en":
        return text
    return TEXT.get(text) or _solaar_spanish(text)

# Ajustes que solo tienen sentido con el motor de reglas de Solaar: un botón "desviado"
# deja de funcionar si nadie procesa sus avisos, así que no se muestran.
HIDDEN_SETTINGS = {"divert-keys", "lowres-scroll-mode", "hires-scroll-mode", "divert-crown", "divert-gkeys"}

# Nombre y descripción en español (se pasan por _() para el inglés)
SETTING_TEXT = {
    "dpi": ("Sensibilidad (DPI)", "Velocidad del puntero. Más DPI, más rápido se mueve."),
    "reprogrammable-keys": ("Acción de cada botón", "Elige qué hace cada botón. Cambiar el clic izquierdo puede dejarte sin ratón."),
    "change-host": ("Equipo conectado", "Easy-Switch: pasa el ratón a otro equipo emparejado."),
    "scroll-direction": ("Desplazamiento natural", "Invierte el sentido de la rueda."),
    "hires-scroll": ("Desplazamiento de alta resolución", "Rueda más suave y precisa."),
    "smart-shift": ("SmartShift", "Velocidad a partir de la cual la rueda pasa a giro libre."),
    "thumb-scroll-mode": ("Rueda del pulgar en alta resolución", ""),
    "thumb-scroll-invert": ("Invertir rueda del pulgar", ""),
    "pointer_speed": ("Velocidad del puntero", ""),
    "backlight": ("Retroiluminación", ""),
    "fn-swap": ("Intercambiar teclas Fn", "Las teclas F1–F12 funcionan sin pulsar Fn."),
}

TEXT = {
    "Left Button": "Botón izquierdo",
    "Right Button": "Botón derecho",
    "Middle Button": "Botón central",
    "Back Button": "Botón atrás",
    "Forward Button": "Botón adelante",
    "DPI Switch": "Botón de DPI",
    "Left Click": "Clic izquierdo",
    "Right Click": "Clic derecho",
    "Mouse Middle Button": "Clic central",
    "Mouse Back Button": "Atrás",
    "Mouse Forward Button": "Adelante",
    "Dpi Switch": "Cambiar DPI",
}


def localize(dev):
    """Traduce etiquetas y quita los ajustes ocultos (modifica `dev`)."""
    hidden = HIDDEN_SETTINGS | ({"reprogrammable-keys"} if dev.get("buttons") else set())
    dev["settings"] = [s for s in dev["settings"] if s["name"] not in hidden]
    if dev.get("localized"):
        return dev
    dev["localized"] = True
    for b in dev.get("buttons", []):
        b["label"] = _label(b["label"])
        for c in b["remap_choices"]:
            c["label"] = _label(c["label"])
    for s in dev["settings"]:
        label, desc = SETTING_TEXT.get(s["name"], (None, None))
        s["label"] = _(label) if label else _label(s["label"])
        if desc is None:  # Puntero no la conoce: la de Solaar
            s["description"] = _label(s["description"]) if s["description"] else ""
        else:
            s["description"] = _(desc) if desc else ""
        for c in s.get("choices", []):
            c["label"] = _label(c["label"])
        for k in s.get("keys", []):
            k["label"] = _label(k["label"])
            for c in k.get("choices", []):
                c["label"] = _label(c["label"])
        if s["name"] == "change-host":
            for c in s["choices"]:
                num, _sep, host = c["label"].partition(":")
                c["label"] = f"{num} · {host}" if host else c["label"]
    for b in dev.get("buttons", []):
        action = b.get("action")
        if action and action["type"] == "keys":
            # los nombres se guardan en el idioma de cuando se grabó el atajo
            names = action.get("names") or [code_label(c) for c in action["codes"]]
            action["names"] = [key_name(n) for n in names]
            action["label"] = "+".join(action["names"])
    return dev


# Nombres visibles de teclas, por nombre evdev (KEY_…) o por nombre de GDK
KEY_NAMES = {
    "KEY_LEFTCTRL": "Ctrl", "KEY_RIGHTCTRL": "Ctrl", "KEY_LEFTSHIFT": "Shift", "KEY_RIGHTSHIFT": "Shift",
    "KEY_LEFTALT": "Alt", "KEY_RIGHTALT": "AltGr", "KEY_LEFTMETA": "Super", "KEY_RIGHTMETA": "Super",
    "KEY_ENTER": "Enter", "Return": "Enter", "KEY_ESC": "Esc", "Escape": "Esc", "KEY_TAB": "Tab", "Tab": "Tab",
    "KEY_SPACE": "Espacio", "space": "Espacio", "KEY_BACKSPACE": "Retroceso", "BackSpace": "Retroceso",
    "KEY_DELETE": "Supr", "Delete": "Supr", "KEY_HOME": "Inicio", "Home": "Inicio", "KEY_END": "Fin", "End": "Fin",
    "KEY_PAGEUP": "RePág", "Page_Up": "RePág", "KEY_PAGEDOWN": "AvPág", "Page_Down": "AvPág",
    "KEY_LEFT": "←", "Left": "←", "KEY_RIGHT": "→", "Right": "→", "KEY_UP": "↑", "Up": "↑", "KEY_DOWN": "↓", "Down": "↓",
    "KEY_SYSRQ": "ImprPant", "Print": "ImprPant", "KEY_VOLUMEUP": "Vol +", "KEY_VOLUMEDOWN": "Vol −",
    "KEY_MUTE": "Silencio", "KEY_PLAYPAUSE": "Play/Pausa", "KEY_NEXTSONG": "Siguiente", "KEY_PREVIOUSSONG": "Anterior",
    "KEY_BACK": "Atrás", "KEY_FORWARD": "Adelante",
}


_SPANISH_KEYS = set(KEY_NAMES.values())
_ENGLISH_TO_SPANISH = {EN[n]: n for n in _SPANISH_KEYS if n in EN}


def key_name(name):
    """Pasa un nombre de tecla ya guardado (p. ej. «Espacio» o «Space») al idioma en uso."""
    spanish = _ENGLISH_TO_SPANISH.get(name, name) if name not in _SPANISH_KEYS else name
    return _(spanish) if spanish in _SPANISH_KEYS else name


def key_label(name):
    """Nombre visible de una tecla a partir de su nombre evdev (KEY_C -> C)."""
    if name in KEY_NAMES:
        return _(KEY_NAMES[name])
    return name.removeprefix("KEY_").capitalize() if len(name) > 5 else name.removeprefix("KEY_")


def code_label(code):
    """Nombre visible de un código evdev (28 -> Enter)."""
    name = ecodes.KEY.get(code, str(code))
    if isinstance(name, (list, tuple)):  # alias: preferir el que tiene nombre propio
        name = next((n for n in name if n in KEY_NAMES), name[-1])
    return key_label(name)


def text_label(text, limit=32):
    """Resumen de una línea para mostrar un texto guardado en un botón."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
