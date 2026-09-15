import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
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
    property string videoUrl: ""
    property string detail: ""
    property string activityText: ""
    property bool pinned: false
    property bool expanded: false
    property bool live: false
    visible: false
    color: "transparent"
    implicitWidth: expanded ? 700 : 390
    implicitHeight: camera ? (expanded ? 500 : 326) : 124 + activityLabel.implicitHeight
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
        player.stop()
        videoUrl = ""
        imageUrl = ""
        still.source = ""
        live = false
        closeTimer.stop()
        service.send({type: "dismiss"})
    }
    function handle(p) {
        if (p.type === "preview") {
            // A pinned preview remains under the user's control.
            if (visible && pinned) return
            player.stop()
            serial = p.serial
            heading = p.title
            camera = p.camera
            imageUrl = ""; videoUrl = ""; still.source = ""; live = false
            activityText = p.message || "Activity detected"
            detail = camera ? "Connecting to camera…" : ""
            pinned = false; expanded = false
            var name = service.config.monitor || (Hyprland.focusedMonitor ? Hyprland.focusedMonitor.name : "")
            var target = Quickshell.screens.find(s => s.name === name)
            screen = target || Quickshell.screens[0]
            visible = true
            closeTimer.interval = Math.max(5, Math.min(120, p.duration || 20)) * 1000
            closeTimer.restart()
        } else if (p.serial === serial && visible) {
            if (p.type === "image") { imageUrl = p.url; still.source = imageUrl }
            else if (p.type === "video") { videoUrl = p.url; player.play() }
            else if (p.type === "video_unavailable") detail = "Snapshot · live stream unavailable"
        }
    }
    Timer { id: closeTimer; onTriggered: if (!popup.pinned) popup.dismiss() }
    Timer {
        interval: 5000; repeat: true; running: popup.visible && popup.imageUrl !== "" && !popup.live
        onTriggered: {
            // Signed HA URLs include the query parameters in their signature.
            // Reload the uncached image without modifying the signed URL.
            still.source = ""
            Qt.callLater(function() { if (popup.visible && !popup.live) still.source = popup.imageUrl })
        }
    }
    MediaPlayer {
        id: player
        source: popup.videoUrl
        videoOutput: video
        audioOutput: AudioOutput { muted: true }
        onErrorOccurred: { popup.live = false; popup.detail = "Snapshot · video could not start" }
    }
    Connections {
        target: video.videoSink
        function onVideoFrameChanged() { popup.live = true; popup.detail = "Live · muted" }
    }
    Rectangle {
        anchors.fill: parent
        radius: 14
        color: Color.background
        border.color: Color.foreground
        border.width: 1
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 12; spacing: 6
            RowLayout {
                Layout.fillWidth: true
                Label { text: popup.heading; textFormat: Text.PlainText; color: Color.foreground; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                ToolButton { text: popup.pinned ? "Unpin" : "Pin"; onClicked: { popup.pinned = !popup.pinned; if (!popup.pinned) closeTimer.restart() } }
                ToolButton { text: "×"; onClicked: popup.dismiss() }
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
                Image { id: still; anchors.fill: parent; fillMode: Image.PreserveAspectFit; cache: false; asynchronous: true; visible: !popup.live }
                VideoOutput { id: video; anchors.fill: parent; visible: popup.live; fillMode: VideoOutput.PreserveAspectFit }
                Label {
                    anchors.centerIn: parent
                    visible: !popup.live && still.status !== Image.Ready
                    text: still.status === Image.Error ? "Camera image unavailable" : "Loading camera…"
                    color: Color.foreground
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Label { text: popup.detail; color: Color.foreground; opacity: 0.7; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                ToolButton { visible: popup.camera !== ""; text: popup.expanded ? "Smaller" : "Expand"; onClicked: popup.expanded = !popup.expanded }
                ToolButton {
                    text: "Open HA"
                    onClicked: Qt.openUrlExternally(service.config.url + "/lovelace/0" + (popup.camera ? "?more-info-entity-id=" + encodeURIComponent(popup.camera) : ""))
                }
            }
        }
    }
}
