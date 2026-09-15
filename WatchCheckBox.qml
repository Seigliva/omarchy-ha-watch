import QtQuick
import QtQuick.Controls
import qs.Commons

CheckBox {
    id: control
    spacing: 7
    padding: 2
    implicitHeight: 26
    implicitWidth: indicator.width + (text ? spacing + contentItem.implicitWidth : 0) + 4
    opacity: enabled ? 1 : 0.4
    indicator: Rectangle {
        x: control.leftPadding
        y: (control.height - height) / 2
        width: 16
        height: 16
        radius: 3
        color: Qt.alpha(Color.foreground, control.checked ? 0.18 : 0.03)
        border.color: Qt.alpha(Color.foreground, control.activeFocus ? 0.9 : 0.4)
        Text {
            anchors.centerIn: parent
            text: control.checked ? "✓" : ""
            color: Color.foreground
            font.pixelSize: 12
        }
    }
    contentItem: Text {
        text: control.text
        color: Color.foreground
        font.pixelSize: 13
        leftPadding: control.indicator.width + control.spacing
        verticalAlignment: Text.AlignVCenter
    }
}
