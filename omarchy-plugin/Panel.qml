// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Icono del ratón en la barra con su batería y un panel con ajustes rápidos.
// Los datos vienen del servicio de Puntero (puntero.service) por su socket Unix:
// una línea JSON por mensaje, el mismo protocolo que usa la ventana.
Panel {
  id: root
  moduleName: "puntero.mouse"
  ipcTarget: "puntero.mouse"

  property var devices: ({})
  property string currentId: ""
  property int pendingHost: -1
  property real dpiLive: -1      // posición mientras se arrastra
  property int dpiPending: -1    // DPI enviado y aún sin confirmar por el ratón

  readonly property var device: currentId !== "" && devices[currentId] ? devices[currentId] : null
  readonly property bool online: !!(device && device.online)
  readonly property int batteryLevel: device && device.battery && device.battery.level !== null && device.battery.level !== undefined ? device.battery.level : -1
  readonly property bool charging: !!(device && device.battery && device.battery.charging)
  readonly property bool batteryLow: batteryLevel >= 0 && batteryLevel <= 15 && !charging
  readonly property var dpiSetting: findSetting("dpi")
  readonly property var hostSetting: findSetting("change-host")
  readonly property var buttons: device && device.buttons ? device.buttons : []
  readonly property bool showPercentage: setting("showPercentage", true) === true

  readonly property color fg: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(fg, 1.55)
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property string imagesDir: Quickshell.env("HOME") + "/.config/puntero/images"

  readonly property string mouseGlyph: "󰍽"

  function findSetting(name) {
    if (!device || !device.settings) return null
    for (var i = 0; i < device.settings.length; i++)
      if (device.settings[i].name === name) return device.settings[i]
    return null
  }

  function shortName(d) {
    if (!d) return ""
    return d.codename && d.codename.length < d.name.length ? d.codename : d.name
  }

  function statusText() {
    if (!device) return ""
    var parts = []
    if (device.bluetooth) parts.push("Bluetooth")
    parts.push(online ? (charging ? "Cargando" : "Conectado") : "Desconectado")
    return parts.join(" · ")
  }

  function dpiIndex() {
    if (!dpiSetting || !dpiSetting.choices) return 0
    for (var i = 0; i < dpiSetting.choices.length; i++)
      if (dpiSetting.choices[i].id === dpiSetting.value) return i
    return 0
  }

  function choiceIndex(id) {
    if (!dpiSetting || !dpiSetting.choices) return -1
    for (var i = 0; i < dpiSetting.choices.length; i++)
      if (dpiSetting.choices[i].id === id) return i
    return -1
  }

  // Lo que se muestra: el valor pedido hasta que el ratón lo confirme, si no el real.
  function dpiShownIndex() {
    var pending = choiceIndex(dpiPending)
    return pending >= 0 ? pending : dpiIndex()
  }

  function requestDpi(index) {
    if (!dpiSetting || !dpiSetting.choices) return
    var i = Math.max(0, Math.min(dpiSetting.choices.length - 1, Math.round(index)))
    dpiPending = dpiSetting.choices[i].id
    dpiSend.restart()
  }

  function dpiLabel(index) {
    if (!dpiSetting || !dpiSetting.choices || dpiSetting.choices.length === 0) return "—"
    var i = Math.max(0, Math.min(dpiSetting.choices.length - 1, Math.round(index)))
    return dpiSetting.choices[i].label
  }

  function buttonSummary(b) {
    var a = b.action
    if (a && a.type === "keys") return (a.names || [a.label]).join(" + ")
    if (a && a.type === "command") return a.label
    if (a && a.type === "text") return "“" + a.label + "”"
    if (a && a.type === "dpi_cycle") return a.values.join(" · ") + " DPI"
    if (b.remap !== null && b.remap !== undefined && b.remap !== b.cid) {
      for (var i = 0; i < b.remap_choices.length; i++)
        if (b.remap_choices[i].id === b.remap) return b.remap_choices[i].label
    }
    return "Original"
  }

  function hostName(choice) {
    var parts = String(choice.label).split(" · ")
    return parts.length > 1 ? parts.slice(1).join(" · ") : choice.label
  }

  // instalado con ./install.sh queda en ~/.local/bin; desde el paquete, en /usr/bin
  function openApp() {
    Quickshell.execDetached(["sh", "-c", "PATH=\"$HOME/.local/bin:$PATH\" exec puntero"])
  }

  function send(obj) {
    if (!sock.connected) return
    sock.write(JSON.stringify(obj) + "\n")
    sock.flush()
  }

  function pickCurrent() {
    var ids = Object.keys(devices)
    if (currentId !== "" && devices[currentId] && devices[currentId].online) return
    for (var i = 0; i < ids.length; i++) if (devices[ids[i]].online) { currentId = ids[i]; return }
    currentId = ids.length > 0 ? ids[0] : ""
  }

  function handle(line) {
    var msg
    try { msg = JSON.parse(line) } catch (e) { return }
    var next = Object.assign({}, devices)
    if (msg.type === "device") next[msg.device.id] = msg.device
    else if (msg.type === "removed") delete next[msg.id]
    else return
    devices = next
    pickCurrent()
    if (dpiPending >= 0 && dpiSetting && dpiSetting.value === dpiPending) dpiPending = -1
  }

  function setHost(choice) {
    if (!hostSetting || choice.id === hostSetting.value) return
    if (pendingHost !== choice.id) {  // primer clic: pedir confirmación
      pendingHost = choice.id
      confirmReset.restart()
      return
    }
    pendingHost = -1
    send({ cmd: "set", device: currentId, setting: "change-host", value: choice.id })
  }

  Socket {
    id: sock
    path: Quickshell.env("XDG_RUNTIME_DIR") + "/puntero.sock"
    connected: true
    parser: SplitParser { onRead: function(line) { root.handle(line) } }
    onConnectionStateChanged: if (!connected) { root.devices = ({}); root.currentId = "" }
  }

  // Reintenta mientras el servicio no esté disponible (arranque, reinicio).
  Timer {
    interval: 5000
    running: !sock.connected
    repeat: true
    onTriggered: sock.connected = true
  }

  Timer { id: confirmReset; interval: 4000; onTriggered: root.pendingHost = -1 }

  // Agrupa los pasos de la rueda del ratón sobre el deslizador en un solo envío.
  Timer {
    id: dpiSend
    interval: 200
    onTriggered: {
      if (root.dpiPending < 0 || (root.dpiSetting && root.dpiSetting.value === root.dpiPending)) {
        root.dpiPending = -1
        return
      }
      root.send({ cmd: "set", device: root.currentId, setting: "dpi", value: root.dpiPending })
      dpiTimeout.restart()
    }
  }

  // Si el ratón no confirma, se vuelve a mostrar el valor real.
  Timer { id: dpiTimeout; interval: 5000; onTriggered: root.dpiPending = -1 }

  // Con el panel abierto se relee el ratón, por si se cambió el DPI con su botón.
  Timer {
    interval: 4000
    running: root.opened && root.online
    repeat: true
    onTriggered: if (root.dpiPending < 0) root.send({ cmd: "refresh" })
  }

  onOpenedChanged: {
    pendingHost = -1
    dpiLive = -1
    dpiPending = -1
    if (opened) send({ cmd: "refresh" })
  }

  visible: device !== null
  implicitWidth: visible ? button.implicitWidth : 0
  implicitHeight: visible ? button.implicitHeight : 0

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    opacity: root.online ? 1 : 0.5
    text: root.showPercentage && root.batteryLevel >= 0 && !vertical
      ? root.mouseGlyph + " " + root.batteryLevel + "%"
      : root.mouseGlyph
    slotSize: Style.bar.iconSlot * (root.showPercentage && root.batteryLevel >= 0 && !vertical ? 2.4 : 1)
    tooltipText: root.device ? root.shortName(root.device) + (root.batteryLevel >= 0 ? " · " + root.batteryLevel + "%" : "") : ""
    onPressed: function(b) {
      if (b === Qt.RightButton) root.openApp()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened && root.device !== null
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Style.space(14)

        // ---------- Cabecera: imagen · nombre/estado · batería ----------
        Item {
          width: parent.width
          implicitHeight: Math.max(Style.space(72), heroLabels.implicitHeight)

          Item {
            id: heroArt
            width: Style.space(64)
            height: Style.space(72)
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter

            Image {
              id: heroImage
              anchors.fill: parent
              fillMode: Image.PreserveAspectFit
              smooth: true
              mipmap: true
              source: root.device && root.device.codename ? "file://" + root.imagesDir + "/" + root.device.codename + ".png" : ""
              visible: status === Image.Ready
            }

            Text {
              anchors.centerIn: parent
              visible: heroImage.status !== Image.Ready
              text: root.mouseGlyph
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.display
            }
          }

          Column {
            id: heroLabels
            anchors.left: heroArt.right
            anchors.leftMargin: Style.space(14)
            anchors.right: heroPercent.left
            anchors.rightMargin: Style.space(10)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Text {
              text: root.shortName(root.device)
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
              elide: Text.ElideRight
              width: parent.width
            }

            Text {
              text: root.statusText().toUpperCase()
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.2
              elide: Text.ElideRight
              width: parent.width
            }
          }

          Text {
            id: heroPercent
            text: root.batteryLevel >= 0 ? root.batteryLevel + "%" : "—"
            color: root.batteryLow ? root.urgent : root.fg
            font.family: root.fontFamily
            font.pixelSize: Style.font.displayLarge
            font.bold: true
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
          }
        }

        // ---------- Barra de batería ----------
        Item {
          width: parent.width
          implicitHeight: Style.space(8)
          visible: root.batteryLevel >= 0

          Rectangle {
            id: track
            anchors.fill: parent
            radius: height / 2
            color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.12)
          }

          Rectangle {
            anchors.left: track.left
            anchors.verticalCenter: track.verticalCenter
            height: track.height
            radius: track.radius
            color: root.batteryLow ? root.urgent : root.fg
            width: Math.max(track.height, track.width * root.batteryLevel / 100)
            Behavior on width { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
          }
        }

        // ---------- Sensibilidad ----------
        PanelSeparator { foreground: root.fg; visible: root.dpiSetting !== null && root.online }

        Column {
          width: parent.width
          spacing: Style.space(8)
          visible: root.dpiSetting !== null && root.online

          Item {
            width: parent.width
            implicitHeight: dpiHeader.implicitHeight

            PanelSectionHeader {
              id: dpiHeader
              text: "SENSIBILIDAD"
              foreground: root.fg
              fontFamily: root.fontFamily
            }

            Text {
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              text: root.dpiLabel(root.dpiLive >= 0 ? root.dpiLive : root.dpiShownIndex()) + " DPI"
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              font.bold: true
            }
          }

          PanelSlider {
            bar: root.bar
            width: parent.width
            minimum: 0
            maximum: root.dpiSetting && root.dpiSetting.choices ? root.dpiSetting.choices.length - 1 : 1
            step: 1
            integer: true
            tickCount: 0
            value: root.dpiShownIndex()
            onMoved: function(v) { root.dpiLive = v }
            onReleased: function(v) {
              root.dpiLive = -1
              root.requestDpi(v)
            }
          }
        }

        // ---------- Botones ----------
        PanelSeparator { foreground: root.fg; visible: root.buttons.length > 0 }

        Column {
          width: parent.width
          spacing: Style.space(6)
          visible: root.buttons.length > 0

          PanelSectionHeader {
            text: "BOTONES"
            foreground: root.fg
            fontFamily: root.fontFamily
          }

          Repeater {
            model: root.buttons
            Item {
              required property var modelData
              width: parent.width
              implicitHeight: buttonName.implicitHeight

              Text {
                id: buttonName
                text: modelData.label
                color: root.fg
                opacity: 0.7
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Text {
                anchors.right: parent.right
                anchors.left: buttonName.right
                anchors.leftMargin: Style.space(12)
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideLeft
                text: root.buttonSummary(modelData)
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                font.bold: modelData.action !== null && modelData.action !== undefined
              }
            }
          }
        }

        // ---------- Easy-Switch ----------
        PanelSeparator { foreground: root.fg; visible: root.hostSetting !== null && root.online }

        Column {
          width: parent.width
          spacing: Style.space(10)
          visible: root.hostSetting !== null && root.online

          PanelSectionHeader {
            text: "EQUIPO CONECTADO"
            foreground: root.fg
            fontFamily: root.fontFamily
          }

          Column {
            id: hostColumn
            width: parent.width
            spacing: Style.space(6)

            Repeater {
              model: root.hostSetting && root.hostSetting.choices ? root.hostSetting.choices : []

              Rectangle {
                id: hostItem
                required property var modelData
                required property int index
                readonly property bool current: root.hostSetting && root.hostSetting.value === modelData.id
                readonly property bool pending: root.pendingHost === modelData.id

                width: hostColumn.width
                implicitHeight: hostText.implicitHeight + Style.space(16)
                radius: Style.cornerRadius
                color: hostMouse.containsMouse && !current ? Style.hoverFillFor(root.fg, Color.accent)
                  : current ? Style.selectedFillFor(root.fg, Color.accent)
                  : "transparent"
                border.width: 1
                border.color: pending ? root.urgent : Qt.rgba(root.fg.r, root.fg.g, root.fg.b, current ? 0.45 : 0.18)

                Text {
                  id: hostNumber
                  anchors.left: parent.left
                  anchors.leftMargin: Style.space(12)
                  anchors.verticalCenter: parent.verticalCenter
                  width: Style.space(18)
                  text: hostItem.index + 1
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  font.bold: true
                }

                Column {
                  id: hostText
                  anchors.left: hostNumber.right
                  anchors.leftMargin: Style.space(10)
                  anchors.right: hostCheck.left
                  anchors.rightMargin: Style.space(8)
                  anchors.verticalCenter: parent.verticalCenter
                  spacing: Style.space(1)

                  Text {
                    width: parent.width
                    text: root.hostName(hostItem.modelData)
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    color: root.fg
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    font.bold: hostItem.current
                  }

                  Text {
                    width: parent.width
                    visible: hostItem.current || hostItem.pending
                    text: hostItem.pending ? "Pulsa otra vez para pasar el ratón aquí" : "Este equipo"
                    wrapMode: Text.Wrap
                    color: hostItem.pending ? root.urgent : root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                }

                Text {
                  id: hostCheck
                  anchors.right: parent.right
                  anchors.rightMargin: Style.space(12)
                  anchors.verticalCenter: parent.verticalCenter
                  text: hostItem.current ? "󰄬" : ""
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.icon
                }

                MouseArea {
                  id: hostMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: hostItem.current ? Qt.ArrowCursor : Qt.PointingHandCursor
                  onClicked: root.setHost(hostItem.modelData)
                }
              }
            }
          }
        }

        // ---------- Abrir la app ----------
        PanelSeparator { foreground: root.fg }

        Button {
          width: parent.width
          text: "Abrir Puntero"
          iconText: "󰒓"
          fontSize: Style.font.bodySmall
          foreground: root.fg
          fontFamily: root.fontFamily
          bordered: true
          onClicked: {
            root.openApp()
            root.close()
          }
        }
      }
    }
  }
}
