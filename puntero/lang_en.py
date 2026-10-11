# SPDX-License-Identifier: GPL-3.0-or-later
"""Traducción al inglés de los textos de Puntero (clave: el texto en español).

Para añadir o corregir una traducción basta con editar este diccionario; los textos
que falten se muestran en español. Los de {llaves} se rellenan con .format().
"""

EN = {
    # ajustes (i18n.SETTING_TEXT)
    "Sensibilidad (DPI)": "Sensitivity (DPI)",
    "Velocidad del puntero. Más DPI, más rápido se mueve.": "Pointer speed. More DPI moves the pointer faster.",
    "Acción de cada botón": "Button actions",
    "Elige qué hace cada botón. Cambiar el clic izquierdo puede dejarte sin ratón.":
        "Choose what each button does. Changing the left click can leave you without a mouse.",
    "Equipo conectado": "Connected computer",
    "Easy-Switch: pasa el ratón a otro equipo emparejado.": "Easy-Switch: move the mouse to another paired computer.",
    "Desplazamiento natural": "Natural scrolling",
    "Invierte el sentido de la rueda.": "Reverses the scroll wheel direction.",
    "Desplazamiento de alta resolución": "High-resolution scrolling",
    "Rueda más suave y precisa.": "Smoother, more precise scroll wheel.",
    "SmartShift": "SmartShift",
    "Velocidad a partir de la cual la rueda pasa a giro libre.": "Speed at which the wheel switches to free spin.",
    "Rueda del pulgar en alta resolución": "High-resolution thumb wheel",
    "Invertir rueda del pulgar": "Invert thumb wheel",
    "Velocidad del puntero": "Pointer speed",
    "Retroiluminación": "Backlight",
    "Intercambiar teclas Fn": "Swap Fn keys",
    "Las teclas F1–F12 funcionan sin pulsar Fn.": "F1–F12 work without holding Fn.",

    # nombres de teclas (i18n.KEY_NAMES)
    "Espacio": "Space",
    "Retroceso": "Backspace",
    "Supr": "Delete",
    "Inicio": "Home",
    "Fin": "End",
    "RePág": "PgUp",
    "AvPág": "PgDn",
    "ImprPant": "PrtSc",
    "Silencio": "Mute",
    "Play/Pausa": "Play/Pause",
    "Siguiente": "Next",
    "Anterior": "Previous",
    "Atrás": "Back",
    "Adelante": "Forward",

    # batería y tipo de dispositivo
    "Vacía": "Empty",
    "Crítica": "Critical",
    "Baja": "Low",
    "Buena": "Good",
    "Llena": "Full",
    "Cargando": "Charging",
    "Casi llena": "Almost full",
    "Cargada": "Charged",
    "Carga lenta": "Slow charging",
    "Batería desconocida": "Battery unknown",
    "Ratón": "Mouse",
    "Teclado": "Keyboard",
    "Trackball": "Trackball",
    "Panel táctil": "Touchpad",
    "Auriculares": "Headset",
    "Teclado numérico": "Numpad",
    "Conectado": "Connected",
    "Desconectado": "Disconnected",
    "Sin conexión": "Offline",

    # Easy-Switch
    "¿Pasar el ratón a «{host}»?": "Move the mouse to “{host}”?",
    "Dejará de funcionar en este equipo. Para volver, pulsa el botón Easy-Switch "
    "de la parte de abajo del ratón hasta elegir este canal.":
        "It will stop working on this computer. To come back, press the Easy-Switch button "
        "on the bottom of the mouse until this channel is selected.",
    "Cancelar": "Cancel",
    "Cambiar": "Switch",

    # atajos frecuentes
    "Copiar": "Copy",
    "Pegar": "Paste",
    "Cortar": "Cut",
    "Deshacer": "Undo",
    "Rehacer": "Redo",
    "Cambiar de ventana": "Switch window",
    "Nueva pestaña": "New tab",
    "Cerrar pestaña": "Close tab",
    "Reabrir pestaña cerrada": "Reopen closed tab",
    "Play / Pausa": "Play / Pause",
    "Subir volumen": "Volume up",
    "Bajar volumen": "Volume down",
    "Enter": "Enter",
    "Escape": "Escape",

    # comandos frecuentes
    "Captura de pantalla": "Screenshot",
    "Abrir terminal": "Open terminal",
    "Abrir navegador": "Open browser",
    "Menú de Omarchy": "Omarchy menu",
    "Abrir la carpeta personal": "Open home folder",
    "Silenciar el sonido": "Mute sound",
    "Silenciar el micrófono": "Mute microphone",
    "Bloquear la pantalla": "Lock screen",

    # botones
    "Atajo: {label}": "Shortcut: {label}",
    "Comando: {label}": "Command: {label}",
    "Escribe: «{label}»": "Types: “{label}”",
    "Ciclo de DPI: {label}": "DPI cycle: {label}",
    "Funciona como: {label}": "Works as: {label}",
    "Función original": "Default function",
    "Atajo de teclado": "Keyboard shortcut",
    "Guardar": "Save",
    "Original": "Default",
    "Otro botón": "Other button",
    "Texto": "Text",
    "Comando": "Command",
    "El botón hace su función de fábrica: <b>{original}</b>.": "The button does its factory function: <b>{original}</b>.",
    "El botón hace su función de fábrica.": "The button does its factory function.",
    "Que funcione como…": "Make it work as…",
    "Atajos frecuentes": "Common shortcuts",
    "Texto que se escribe": "Text to type",
    "Al pulsar el botón se escribe este texto donde esté el cursor: un saludo, "
    "una firma, tu correo… Puede tener varias líneas.":
        "Pressing the button types this text wherever the cursor is: a greeting, "
        "a signature, your email… It can have several lines.",
    "Para escribir acentos, ñ y símbolos instala wtype (Wayland) o xdotool (X11). "
    "Sin ellos solo se escriben letras sin acento, números y espacios.":
        "To type accents and symbols, install wtype (Wayland) or xdotool (X11). "
        "Without them only plain letters, numbers and spaces are typed.",
    "Se ejecuta al pulsar el botón, como en una terminal.": "Runs when the button is pressed, as in a terminal.",
    "Comandos frecuentes": "Common commands",
    "Puntos de DPI": "DPI steps",
    "Cada pulsación del botón pasa al siguiente punto. Después del último vuelve al primero.":
        "Each press moves to the next step. After the last one it goes back to the first.",
    "Añadir un punto": "Add a step",
    "Al cambiar verás el DPI en pantalla. Puedes tener entre 2 y 5 puntos.":
        "The DPI is shown on screen when it changes. You can have 2 to 5 steps.",
    "Quitar este punto": "Remove this step",
    "Punto {n}": "Step {n}",
    "Pulsa la combinación… (Esc para cancelar)": "Press the combination… (Esc to cancel)",
    "Haz clic para grabar otra": "Click to record another one",
    "Haz clic aquí y pulsa la tecla o combinación": "Click here and press the key or combination",

    # página del dispositivo
    "Botones": "Buttons",
    "Asigna a cada botón otra función del ratón, un atajo de teclado, un texto o un comando.":
        "Give each button another mouse function, a keyboard shortcut, a text or a command.",
    "Ajustes": "Settings",
    "Otros botones y teclas": "Other buttons and keys",
    "Easy-Switch": "Easy-Switch",
    "Información": "Information",
    "Este dispositivo no expone ajustes": "This device has no settings",

    # ventana
    "Sin permiso para acceder a un dispositivo Logitech": "No permission to access a Logitech device",
    "Dispositivo": "Device",
    "Buscando dispositivos": "Looking for devices",
    "Enciende tu ratón o teclado Logitech.": "Turn on your Logitech mouse or keyboard.",
    "Falta permiso": "Permission needed",
    "El sistema no deja leer el dispositivo. Instala Solaar (trae las reglas udev) y ejecuta:":
        "The system won't let Puntero read the device. Install Solaar (it ships the udev rules) and run:",
    "Después apaga y enciende el ratón.": "Then turn the mouse off and on again.",
    "El motor se detuvo": "The engine stopped",
    "Reiniciar": "Restart",
    "No se pudo iniciar: {error}": "Could not start: {error}",
    "El proceso que habla con los dispositivos terminó. "
    "Comprueba que Solaar está instalado (<tt>sudo pacman -S solaar</tt>).":
        "The process that talks to the devices has stopped. "
        "Check that Solaar is installed (<tt>sudo pacman -S solaar</tt>).",
    "No se pudo cambiar «{label}»: {error}": "Could not change “{label}”: {error}",
    "Automático (el del sistema)": "Automatic (system language)",
    "Idioma": "Language",
    "Menú principal": "Main menu",

    # mensajes del motor
    "Sensibilidad": "Sensitivity",
    "el dispositivo no está conectado": "the device is not connected",
    "el dispositivo no respondió": "the device did not respond",
    "valor fuera de las opciones del ajuste": "value outside the setting's options",
    "este ajuste no se puede cambiar desde Puntero": "this setting can't be changed from Puntero",
    "este dispositivo no permite desviar botones": "this device doesn't allow diverting buttons",
    "el ratón no aceptó el cambio": "the mouse did not accept the change",
}
