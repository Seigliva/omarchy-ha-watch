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
    // Device names are untrusted text. Basic's default IconLabel delegate
    // uses AutoText, which can fetch images embedded in a name.
    delegate: Basic.ItemDelegate {
        id: option
        required property var model
        required property int index
        width: ListView.view.width
        text: control.textAt(index)
        font.pixelSize: control.font.pixelSize
        font.weight: control.currentIndex === index ? Font.DemiBold : Font.Normal
        highlighted: control.highlightedIndex === index
        hoverEnabled: control.hoverEnabled
        contentItem: Text {
            text: option.text
            textFormat: Text.PlainText
            font: option.font
            color: option.highlighted ? control.palette.highlightedText : control.palette.text
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }
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
