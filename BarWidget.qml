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
        onPressed: Quickshell.execDetached(["omarchy-shell", "ha-watch", "settings"])
    }
}
