import QtQuick
import QtQuick.Controls.Basic as Basic
import qs.Commons

Basic.ComboBox {
    id: control
    implicitHeight: 32
    font.pixelSize: 13
    palette.buttonText: Color.foreground
    palette.text: Color.foreground
    palette.window: Color.popups.background
    palette.base: Color.popups.background
    palette.button: Color.popups.background
    palette.highlight: Qt.alpha(Color.foreground, 0.15)
    palette.highlightedText: Color.foreground
    indicator: Text {
        x: control.width - width - 10
        y: (control.height - height) / 2
        text: "⌄"
        color: Color.foreground
        font.pixelSize: 16
    }
    background: Rectangle {
        radius: 4
        color: Qt.alpha(Color.foreground, control.hovered ? 0.08 : 0.035)
        border.color: Qt.alpha(Color.foreground, control.activeFocus ? 0.6 : 0.2)
    }
}
