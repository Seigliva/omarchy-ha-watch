import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import qs.Commons
import "RuleOptions.js" as RuleOptions

FloatingWindow {
    id: win
    required property var service
    title: "Home Assistant Watch"
    implicitWidth: 620
    implicitHeight: 690
    minimumSize: Qt.size(480, 500)
    color: Color.background
    property var cameras: service.entities.filter(e => e.id.startsWith("camera."))
    property var sensors: service.entities.filter(e => !e.id.startsWith("camera."))
    property int editIndex: -1
    property string selectedSensor: ""
    property string selectedCamera: ""
    property var selectedStates: ["on"]
    property var customMessages: ({})
    property var stateOptions: RuleOptions.options(service.entities.find(e => e.id === selectedSensor) || {id: selectedSensor})
    property var positions: ["top-right", "bottom-right", "top-left", "bottom-left"]
    property var screenNames: ["Automatic"].concat(Quickshell.screens.map(s => s.name))

    function selected(model, ident) { return model.findIndex(e => e.id === ident) }
    function editRule(index) {
        editIndex = index
        var r = service.config.rules[index]
        selectedSensor = r.sensor
        selectedCamera = r.camera || ""
        selectedStates = (r.states || RuleOptions.defaults(r.sensor)).slice()
        customMessages = Object.assign({}, r.messages || {})
    }
    function storeRule() {
        if (selected(sensors, selectedSensor) < 0 || (selectedCamera && selected(cameras, selectedCamera) < 0)) return
        var rules = service.config.rules.slice()
        if (!selectedStates.length) return
        var previous = editIndex >= 0 ? rules[editIndex] : {enabled: true}
        var rule = Object.assign({}, previous, {sensor: selectedSensor, camera: selectedCamera,
            states: selectedStates.slice(), messages: Object.assign({}, customMessages)})
        if (editIndex >= 0) rules[editIndex] = rule
        else rules.push(rule)
        service.save({rules: rules})
        resetEditor()
    }
    function resetEditor() {
        editIndex = -1; selectedSensor = ""; selectedCamera = ""
        selectedStates = ["on"]; customMessages = ({})
    }
    function ruleSummary(rule) {
        var source = service.entities.find(e => e.id === rule.sensor) || {id: rule.sensor}
        var chosen = rule.states || RuleOptions.defaults(rule.sensor)
        return RuleOptions.options(source).filter(o => chosen.indexOf(o.value) >= 0).map(o => o.label).join(" / ")
    }
    function label(ident) {
        var found = service.entities.find(e => e.id === ident)
        return found ? found.name : ident
    }
    ScrollView {
        anchors.fill: parent
        anchors.margins: 24
        contentWidth: availableWidth
        clip: true
        ColumnLayout {
            width: parent.width
            spacing: 14
            Label { text: "Home Assistant Watch"; font.pixelSize: 26; font.bold: true; color: Color.foreground }
            Label {
                text: "A little window into your home."
                color: Color.foreground; opacity: 0.65
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Color.foreground; opacity: 0.15 }
            Label {
                text: (service.state === "connected" ? "●  " : "○  ") + service.message
                color: service.state === "connected" ? "#87c99b" : Color.foreground
                wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Label {
                visible: service.errorMessage !== ""
                text: service.errorMessage; color: "#ef9999"
                wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                TextField {
                    id: address
                    Layout.fillWidth: true
                    placeholderText: "http://homeassistant.local:8123"
                    text: service.config.url || ""
                    enabled: service.state !== "connected"
                    onAccepted: login.clicked()
                    selectByMouse: true
                }
                Button {
                    id: login
                    text: "Sign in"
                    visible: service.state !== "connected"
                    enabled: service.ready
                    onClicked: {
                        service.errorMessage = ""
                        service.send({type: "login", url: address.text})
                    }
                }
                Button {
                    text: "Sign out"
                    visible: !!service.config.clientId
                    enabled: service.ready
                    onClicked: service.send({type: "logout"})
                }
            }
            Label {
                text: "Sign in securely in your browser. Your session is saved in your system keyring."
                color: Color.foreground; opacity: 0.65; font.pixelSize: 12
                wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Label { text: "Activity rules"; font.pixelSize: 18; font.bold: true; color: Color.foreground }
            Label {
                visible: service.config.rules.length === 0
                text: "Choose what should open a camera preview. No rules yet."
                color: Color.foreground; opacity: 0.65; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Repeater {
                model: service.config.rules
                delegate: Frame {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    ColumnLayout {
                        width: parent.width
                        Label { text: win.label(modelData.sensor); color: Color.foreground; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                        Label { text: modelData.camera ? "Show " + win.label(modelData.camera) : "Text notification"; color: Color.foreground; opacity: 0.7; elide: Text.ElideRight; Layout.fillWidth: true }
                        Label { text: "When: " + win.ruleSummary(modelData); color: Color.foreground; opacity: 0.7; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        RowLayout {
                            CheckBox {
                                text: "Enabled"; checked: modelData.enabled !== false
                                onToggled: {
                                    var rules = service.config.rules.slice()
                                    rules[index] = Object.assign({}, modelData, {enabled: checked})
                                    service.save({rules: rules})
                                }
                            }
                            Item { Layout.fillWidth: true }
                            Button { text: "Test"; enabled: service.state === "connected"; onClicked: service.send({type: "test", rule: modelData}) }
                            Button { text: "Edit"; onClicked: win.editRule(index) }
                            Button {
                                text: "Remove"
                                onClicked: { var rules = service.config.rules.slice(); rules.splice(index, 1); service.save({rules: rules}); win.resetEditor() }
                            }
                        }
                    }
                }
            }
            GridLayout {
                columns: 2; Layout.fillWidth: true
                enabled: service.state === "connected"
                Label { text: "Device"; color: Color.foreground }
                ComboBox {
                    id: sensor; Layout.fillWidth: true; model: win.sensors; textRole: "name"
                    currentIndex: win.selected(win.sensors, win.selectedSensor)
                    displayText: currentIndex < 0 ? "Choose a sensor or cover" : currentText
                    onActivated: {
                        win.selectedSensor = win.sensors[currentIndex].id
                        win.selectedStates = RuleOptions.defaults(win.selectedSensor)
                        win.customMessages = ({})
                    }
                }
                Label { text: "Notify when"; color: Color.foreground }
                ColumnLayout {
                    Layout.fillWidth: true
                    Repeater {
                        model: win.stateOptions
                        delegate: CheckBox {
                            required property var modelData
                            text: modelData.label
                            checked: win.selectedStates.indexOf(modelData.value) >= 0
                            onToggled: {
                                var states = win.selectedStates.filter(s => s !== modelData.value)
                                if (checked) states.push(modelData.value)
                                win.selectedStates = states
                            }
                        }
                    }
                    Label {
                        visible: win.selectedSensor.startsWith("cover.")
                        text: "Opening/Closing require your integration to report movement."
                        wrapMode: Text.WordWrap; Layout.fillWidth: true
                        color: Color.foreground; opacity: 0.65; font.pixelSize: 12
                    }
                }
                Label { text: "Show"; color: Color.foreground }
                ComboBox {
                    id: camera; Layout.fillWidth: true
                    model: [{name: "Text notification only", id: ""}].concat(win.cameras); textRole: "name"
                    currentIndex: win.selectedCamera ? win.selected(win.cameras, win.selectedCamera) + 1 : 0
                    onActivated: win.selectedCamera = currentIndex ? win.cameras[currentIndex - 1].id : ""
                }
                Label { text: "Custom text"; color: Color.foreground }
                ColumnLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "Optional. Leave blank to use the device state."
                        color: Color.foreground; opacity: 0.65; font.pixelSize: 12
                        wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                    Repeater {
                        model: win.stateOptions
                        delegate: TextField {
                            required property var modelData
                            Layout.fillWidth: true
                            visible: win.selectedStates.indexOf(modelData.value) >= 0
                            placeholderText: modelData.label + " — automatic"
                            text: win.customMessages[modelData.value] || ""
                            selectByMouse: true
                            maximumLength: 240
                            onTextEdited: {
                                var messages = Object.assign({}, win.customMessages)
                                messages[modelData.value] = text
                                win.customMessages = messages
                            }
                        }
                    }
                }
                Item { implicitWidth: 1; implicitHeight: 1 }
                RowLayout {
                    Button { text: win.editIndex >= 0 ? "Save changes" : "Add rule"; enabled: sensor.currentIndex >= 0 && win.selectedStates.length > 0; onClicked: win.storeRule() }
                    Button { visible: win.editIndex >= 0; text: "Cancel"; onClicked: win.resetEditor() }
                }
            }
            Label { text: "Camera window"; font.pixelSize: 18; font.bold: true; color: Color.foreground }
            GridLayout {
                columns: 2; Layout.fillWidth: true
                Label { text: "Position"; color: Color.foreground }
                ComboBox {
                    Layout.fillWidth: true
                    model: ["Top right", "Bottom right", "Top left", "Bottom left"]
                    currentIndex: Math.max(0, win.positions.indexOf(service.config.position))
                    onActivated: service.save({position: win.positions[currentIndex]})
                }
                Label { text: "Screen"; color: Color.foreground }
                ComboBox {
                    Layout.fillWidth: true; model: win.screenNames
                    currentIndex: Math.max(0, win.screenNames.indexOf(service.config.monitor || "Automatic"))
                    onActivated: service.save({monitor: currentIndex ? win.screenNames[currentIndex] : ""})
                }
                Label { text: "Seconds visible"; color: Color.foreground }
                SpinBox { from: 5; to: 120; value: service.config.duration; onValueModified: service.save({duration: value}) }
            }
            Label {
                text: "Video is muted. Repeated notifications for the same state are limited to one every 30 seconds. Opposite states can notify immediately."
                color: Color.foreground; opacity: 0.65; font.pixelSize: 12
                wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            RowLayout {
                Button { text: service.paused ? "Resume alerts" : "Pause for 1 hour"; onClicked: service.togglePause() }
                Item { Layout.fillWidth: true }
                Button { text: "Done"; onClicked: service.settingsOpen = false }
            }
        }
    }
}
