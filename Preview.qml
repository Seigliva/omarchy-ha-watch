import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import qs.Commons

PanelWindow {
    id: popup
    required property var service
    property int serial: 0
    property string heading: ""
    property string camera: ""
    property string imageUrl: ""
    property int frameId: 0
    property string detail: ""
    property string activityText: ""
    property bool pinned: false
    property bool expanded: false
    property bool live: false
    property bool liveUnavailable: false
    visible: false
    color: "transparent"
    implicitWidth: expanded ? 700 : 360
    implicitHeight: camera ? (expanded ? 500 : 300) : previewContent.implicitHeight + 24
    anchors.top: service.config.position.startsWith("top")
    anchors.bottom: service.config.position.startsWith("bottom")
    anchors.right: service.config.position.endsWith("right")
    anchors.left: service.config.position.endsWith("left")
    margins { top: 48; bottom: 20; left: 20; right: 20 }
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "ha-watch-preview"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    function dismiss() {
        visible = false
        imageUrl = ""
        still.source = ""
        live = false
        closeTimer.stop()
        service.send({type: "dismiss", serial: popup.serial})
    }
    function handle(p) {
        if (p.type === "preview") {
            // A pinned preview remains under the user's control.
            if (visible && pinned) return
            serial = p.serial
            heading = p.title
            camera = p.camera
            imageUrl = ""; still.source = ""; live = false
            activityText = p.message || "Activity detected"
            liveUnavailable = false
            detail = camera ? "Connecting to camera…" : ""
            pinned = false; expanded = false
            var name = service.config.monitor || (Hyprland.focusedMonitor ? Hyprland.focusedMonitor.name : "")
            var target = Quickshell.screens.find(s => s.name === name)
            screen = target || Quickshell.screens[0]
            visible = true
            closeTimer.interval = Math.max(5, Math.min(120, p.duration || 20)) * 1000
            closeTimer.restart()
        } else if (p.serial === serial && visible) {
            if (p.type === "image" && p.url.startsWith("file://")) {
                frameId = p.frame
                live = !!p.live
                detail = live ? "Live · muted" : (liveUnavailable ? "Snapshot · live stream unavailable" : "Snapshot · connecting to live…")
                imageUrl = p.url
                still.source = imageUrl
            }
            else if (p.type === "video_unavailable") { live = false; liveUnavailable = true; detail = "Snapshot · live stream unavailable" }
            else if (p.type === "media_error") { live = false; detail = p.message }
        }
    }
    Timer { id: closeTimer; onTriggered: if (!popup.pinned) popup.dismiss() }
    Rectangle {
        anchors.fill: parent
        radius: Style.cornerRadius
        color: Color.popups.background
        border.color: Color.popups.border
        border.width: 1
        ColumnLayout {
            id: previewContent
            anchors.fill: parent; anchors.margins: 12; spacing: 6
            RowLayout {
                Layout.fillWidth: true
                Label { text: popup.heading; textFormat: Text.PlainText; color: Color.foreground; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                WatchButton { text: popup.pinned ? "Unpin" : "Pin"; onClicked: { popup.pinned = !popup.pinned; service.send({type: "pin", serial: popup.serial, pinned: popup.pinned}); if (!popup.pinned) closeTimer.restart() } }
                WatchButton { text: "×"; onClicked: popup.dismiss() }
            }
            Label {
                id: activityLabel
                text: popup.activityText; textFormat: Text.PlainText
                color: Color.foreground; wrapMode: Text.Wrap
                Layout.fillWidth: true
                maximumLineCount: 6; elide: Text.ElideRight
            }
            Item {
                visible: popup.camera !== ""
                Layout.fillWidth: true; Layout.fillHeight: true
                Image {
                    id: still
                    anchors.fill: parent
                    fillMode: Image.PreserveAspectFit
                    sourceSize: Qt.size(640, 360)
                    cache: false
                    asynchronous: true
                    retainWhileLoading: true
                    onStatusChanged: if (status === Image.Ready || status === Image.Error)
                        service.send({type: "frame_ready", serial: popup.serial, frame: popup.frameId})
                }
                Label {
                    anchors.centerIn: parent
                    visible: still.status !== Image.Ready
                    text: still.status === Image.Error ? "Camera image unavailable" : "Loading camera…"
                    color: Color.foreground
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Label { text: popup.detail; color: Color.foreground; opacity: 0.7; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                WatchButton { visible: popup.camera !== ""; text: popup.expanded ? "Smaller" : "Expand"; onClicked: popup.expanded = !popup.expanded }
                WatchButton {
                    text: "Open HA"
                    onClicked: Qt.openUrlExternally(service.config.url + "/lovelace/0" + (popup.camera ? "?more-info-entity-id=" + encodeURIComponent(popup.camera) : ""))
                }
            }
        }
    }
}
