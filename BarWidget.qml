import QtQuick
import Quickshell
import qs.Ui as Ui

Ui.BarWidget {
    id: root
    moduleName: "ha.watch"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    Ui.BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: ""
        tooltipText: "Home Assistant Watch"
        onPressed: Quickshell.execDetached(["omarchy-shell", "ha-watch", "settings"])
    }
}
