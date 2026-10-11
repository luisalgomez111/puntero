# SPDX-License-Identifier: GPL-3.0-or-later
"""Textos en español para los ajustes y botones que describe Solaar.

Lo aplica el motor a cada dispositivo antes de enviarlo, así todos los clientes
(la ventana y el plugin de la barra) reciben los mismos textos. Es idempotente.
"""

from evdev import ecodes

# Ajustes que solo tienen sentido con el motor de reglas de Solaar: un botón "desviado"
# deja de funcionar si nadie procesa sus avisos, así que no se muestran.
HIDDEN_SETTINGS = {"divert-keys", "lowres-scroll-mode", "hires-scroll-mode", "divert-crown", "divert-gkeys"}

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
    for b in dev.get("buttons", []):
        b["label"] = TEXT.get(b["label"], b["label"])
        for c in b["remap_choices"]:
            c["label"] = TEXT.get(c["label"], c["label"])
    for s in dev["settings"]:
        label, desc = SETTING_TEXT.get(s["name"], (None, None))
        s["label"] = label or s["label"]
        s["description"] = desc if desc is not None else s["description"]
        for c in s.get("choices", []):
            c["label"] = TEXT.get(c["label"], c["label"])
        for k in s.get("keys", []):
            k["label"] = TEXT.get(k["label"], k["label"])
            for c in k.get("choices", []):
                c["label"] = TEXT.get(c["label"], c["label"])
        if s["name"] == "change-host":
            for c in s["choices"]:
                num, _, host = c["label"].partition(":")
                c["label"] = f"{num} · {host}" if host else c["label"]
    for b in dev.get("buttons", []):
        action = b.get("action")
        if action and action["type"] == "keys" and not action.get("names"):
            action["names"] = [code_label(c) for c in action["codes"]]
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


def key_label(name):
    """Nombre visible de una tecla a partir de su nombre evdev (KEY_C -> C)."""
    if name in KEY_NAMES:
        return KEY_NAMES[name]
    return name.removeprefix("KEY_").capitalize() if len(name) > 5 else name.removeprefix("KEY_")


def code_label(code):
    """Nombre visible de un código evdev (28 -> Enter)."""
    name = ecodes.KEY.get(code, str(code))
    if isinstance(name, (list, tuple)):  # alias: preferir el que tiene nombre propio
        name = next((n for n in name if n in KEY_NAMES), name[-1])
    return key_label(name)
