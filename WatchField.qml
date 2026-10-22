import QtQuick
import QtQuick.Controls.Basic as Basic
import qs.Commons as Commons

Basic.TextField {
    id: control
    implicitHeight: 32
    font.pixelSize: 13
    color: Commons.Color.foreground
    placeholderTextColor: Qt.alpha(Commons.Color.foreground, 0.5)
    selectionColor: Qt.alpha(Commons.Color.foreground, 0.3)
    selectedTextColor: Commons.Color.foreground
    background: Rectangle {
        radius: 4
        color: Qt.alpha(Commons.Color.foreground, 0.035)
        border.color: Qt.alpha(Commons.Color.foreground, control.activeFocus ? 0.6 : 0.2)
    }
}
