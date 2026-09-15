import QtQuick
import Quickshell
import Quickshell.Io
import "./"

Item {
    id: root
    property var shell: null
    property var config: ({rules: [], duration: 20, position: "top-right", monitor: ""})
    property var entities: []
    state: "starting"
    property string message: "Starting Home Assistant Watch…"
    property string errorMessage: ""
    property bool ready: false
    property bool paused: false
    property bool settingsOpen: false
    property string directory: Qt.resolvedUrl(".").toString().replace("file://", "")

    function loadConfig() {
        if (!shell) return
        var c = shell.shellConfig || {}
        var entries = (c.plugins || []).slice()
        var layout = c.bar ? c.bar.layout || {} : {}
        for (var section of ["left", "center", "right"])
            entries = entries.concat(layout[section] || [])
        for (var entry of entries) {
            if (entry.id === "seigliva.ha-watch") {
                config = Object.assign({rules: [], duration: 20, position: "top-right", monitor: ""}, entry)
                if (ready) send({type: "configure", config: config})
                return
            }
        }
    }
    function save(values) {
        config = Object.assign({}, config, values)
        if (shell) shell.updateEntryInline("seigliva.ha-watch", config)
        send({type: "configure", config: config})
    }
    function send(value) {
        if (ready && bridge.running) bridge.write(JSON.stringify(value) + "\n")
    }
    function togglePause() {
        paused = !paused
        send({type: "pause", paused: paused})
        if (paused) pauseTimer.restart()
        else pauseTimer.stop()
    }
    function handle(line) {
        try {
            var p = JSON.parse(line)
            if (p.type === "ready") { ready = true; loadConfig(); if (paused) send({type: "pause", paused: true}) }
            else if (p.type === "status") { state = p.state; message = p.message }
            else if (p.type === "entities") entities = p.entities
            else if (p.type === "error") errorMessage = p.message
            else if (p.type === "open_url") Quickshell.execDetached(["xdg-open", p.url])
            else if (p.type === "save_connection") {
                errorMessage = ""
                var connection = {url: p.url, clientId: p.clientId}
                if (p.resetRules) connection.rules = []
                save(connection)
            } else if (p.type === "clear") { entities = []; preview.dismiss() }
            else preview.handle(p)
        } catch (e) { errorMessage = "Could not read a response from the connection service." }
    }
    onShellChanged: loadConfig()
    Connections {
        target: root.shell
        function onShellConfigChanged() { root.loadConfig() }
    }
    Process {
        id: bridge
        command: ["bash", root.directory + "run-bridge.sh"]
        stdinEnabled: true
        running: true
        stdout: SplitParser { onRead: line => root.handle(line) }
        // Do not forward transport/library output, which can contain camera URLs.
        onExited: function(exitCode) {
            root.ready = false
            if (exitCode === 78) {
                root.state = "setup_required"
                root.message = "Run bash setup.sh in the plugin folder to finish installation."
                return
            }
            root.state = "offline"
            root.message = "Connection service stopped. Check the plugin dependencies."
            preview.dismiss()
            restartTimer.restart()
        }
    }
    Timer { id: restartTimer; interval: 10000; onTriggered: bridge.running = true }
    Timer {
        id: pauseTimer
        interval: 3600000
        onTriggered: { root.paused = false; root.send({type: "pause", paused: false}) }
    }
    IpcHandler {
        target: "ha-watch"
        function settings(): string { root.settingsOpen = true; return "ok" }
        function status(): string { return JSON.stringify({version: "0.3.0", pluginId: "seigliva.ha-watch", state: root.state, message: root.message, rules: root.config.rules.length, paused: root.paused}) }
        function demo(): string {
            preview.handle({type: "preview", serial: -1, title: "Preview test · Entrance", camera: "", duration: 20})
            return "ok"
        }
    }
    Settings { service: root; visible: root.settingsOpen; onVisibleChanged: if (!visible) root.settingsOpen = false }
    Preview { id: preview; service: root }
}
