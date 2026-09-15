import QtQuick
import Quickshell
import qs.Ui as Ui
import qs.Commons
import QtQuick.Effects

Ui.BarWidget {
    id: root
    moduleName: "seigliva.ha-watch"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    property bool opened: false
    property bool popoutSwitchClosing: false
    readonly property var service: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
    function open() { if (service) opened = true }
    function close() { opened = false }
    function toggle() { opened ? close() : open() }
    function closeForPopoutSwitch() {
        popoutSwitchClosing = true
        close()
        Qt.callLater(function() { root.popoutSwitchClosing = false })
    }
    Loader {
        active: root.service !== null
        sourceComponent: Component {
            Settings {
                service: root.service
                anchorItem: button
                bar: root.bar
                owner: root
                open: root.opened
            }
        }
    }
    Ui.BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        iconComponent: Component {
            Item {
                Image { id: icon; anchors.fill: parent; source: Qt.resolvedUrl("assets/house-eye.svg"); visible: false; sourceSize: Qt.size(64, 64) }
                MultiEffect { anchors.fill: parent; source: icon; colorization: 1; colorizationColor: Color.foreground }
            }
        }
        tooltipText: "Home Assistant Watch"
        onPressed: root.toggle()
    }
}
