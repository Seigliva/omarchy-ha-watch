import QtQuick
import QtQuick.Controls
import qs.Commons as Commons

Button {
    id: control
    implicitHeight: 30
    implicitWidth: Math.max(30, contentItem.implicitWidth + 18)
    padding: 6
    opacity: enabled ? 1 : 0.4
    contentItem: Text {
        text: control.text
        color: Commons.Color.foreground
        font.pixelSize: 12
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 4
        color: Qt.alpha(Commons.Color.foreground, control.down ? 0.16 : control.hovered ? 0.09 : 0.035)
        border.color: Qt.alpha(Commons.Color.foreground, control.activeFocus ? 0.6 : 0.14)
    }
}
