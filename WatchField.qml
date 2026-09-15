import QtQuick
import QtQuick.Controls.Basic as Basic
import qs.Commons

Basic.TextField {
    id: control
    implicitHeight: 32
    font.pixelSize: 13
    color: Color.foreground
    placeholderTextColor: Qt.alpha(Color.foreground, 0.5)
    selectionColor: Qt.alpha(Color.foreground, 0.3)
    selectedTextColor: Color.foreground
    background: Rectangle {
        radius: 4
        color: Qt.alpha(Color.foreground, 0.035)
        border.color: Qt.alpha(Color.foreground, control.activeFocus ? 0.6 : 0.2)
    }
}
