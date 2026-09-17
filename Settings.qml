import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Ui as Ui
import "RuleOptions.js" as RuleOptions

Ui.KeyboardPanel {
    id: win
    required property var service
    property string page: "rules"
    property bool confirmRemove: false
    contentWidth: fittedContentWidth(420)
    contentHeight: fittedContentHeight(content.implicitHeight, 590)
    focusTarget: closeButton
    onPageChanged: {
        confirmRemove = false;
        scroller.contentItem.contentY = 0;
        Qt.callLater(function () {
            if (win.open)
                closeButton.forceActiveFocus();
        });
    }
    property var cameras: service.entities.filter(e => e.id.startsWith("camera."))
    property var sensors: service.entities.filter(e => !e.id.startsWith("camera."))
    property int editIndex: -1
    property string selectedSensor: ""
    property string selectedCamera: ""
    property var selectedStates: ["on"]
    property var customMessages: ({})
    property var stateOptions: RuleOptions.options(service.entities.find(e => e.id === selectedSensor) || {
        id: selectedSensor
    })
    property var positions: ["top-right", "bottom-right", "top-left", "bottom-left"]
    property var screenNames: ["Automatic"].concat(Quickshell.screens.map(s => s.name))

    function selected(model, ident) {
        return model.findIndex(e => e.id === ident);
    }
    function editRule(index) {
        editIndex = index;
        var r = service.config.rules[index];
        selectedSensor = r.sensor;
        selectedCamera = r.camera || "";
        selectedStates = (r.states || RuleOptions.defaults(r.sensor)).slice();
        customMessages = Object.assign({}, r.messages || {});
        page = "edit";
    }
    function storeRule() {
        if (selected(sensors, selectedSensor) < 0 || (selectedCamera && selected(cameras, selectedCamera) < 0))
            return;
        var rules = service.config.rules.slice();
        if (!selectedStates.length)
            return;
        var previous = editIndex >= 0 ? rules[editIndex] : {
            enabled: true
        };
        var rule = Object.assign({}, previous, {
            sensor: selectedSensor,
            camera: selectedCamera,
            states: selectedStates.slice(),
            messages: Object.assign({}, customMessages)
        });
        if (editIndex >= 0)
            rules[editIndex] = rule;
        else
            rules.push(rule);
        service.save({
            rules: rules
        });
        resetEditor();
        page = "rules";
    }
    function resetEditor() {
        editIndex = -1;
        selectedSensor = "";
        selectedCamera = "";
        selectedStates = ["on"];
        customMessages = ({});
    }
    function ruleSummary(rule) {
        var source = service.entities.find(e => e.id === rule.sensor) || {
            id: rule.sensor
        };
        var chosen = rule.states || RuleOptions.defaults(rule.sensor);
        return RuleOptions.options(source).filter(o => chosen.indexOf(o.value) >= 0).map(o => o.label).join(" / ");
    }
    function label(ident) {
        var found = service.entities.find(e => e.id === ident);
        return found ? found.name : ident;
    }

    FocusScope {
        id: focusScope
        anchors.fill: parent
        Keys.onEscapePressed: event => {
            win.close();
            event.accepted = true;
        }
        ScrollView {
            id: scroller
            anchors.fill: parent
            contentWidth: availableWidth
            clip: true
            ColumnLayout {
                id: content
                width: scroller.availableWidth
                spacing: 10
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Label {
                            text: "Home Assistant Watch"
                            color: Color.foreground
                            font.pixelSize: 18
                            font.bold: true
                            Layout.fillWidth: true
                        }
                        Label {
                            text: "A little window into your home."
                            color: Color.foreground
                            opacity: 0.55
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                    WatchButton {
                        id: closeButton
                        text: "×"
                        Accessible.name: "Close panel"
                        onClicked: win.close()
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: service.paused ? "◌  Alerts paused" : (service.state === "connected" ? "●  Connected" : "○  " + service.message)
                        color: Color.foreground
                        opacity: 0.7
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    WatchButton {
                        text: service.paused ? "Resume" : "Pause 1h"
                        onClicked: service.togglePause()
                    }
                }
                Label {
                    visible: service.errorMessage !== ""
                    text: service.errorMessage
                    textFormat: Text.PlainText
                    color: "#ef9999"
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 1
                    color: Color.foreground
                    opacity: 0.12
                }
                ColumnLayout {
                    visible: win.page === "rules"
                    Layout.fillWidth: true
                    spacing: 8
                    Label {
                        visible: service.config.rules.length === 0
                        text: service.state === "connected" ? "No rules yet. Add a sensor or cover to get started." : "Open Settings to connect your Home Assistant."
                        color: Color.foreground
                        opacity: 0.7
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Repeater {
                        model: service.config.rules
                        delegate: Frame {
                            padding: 10
                            background: Rectangle {
                                color: Qt.alpha(Color.foreground, 0.035)
                                radius: 6
                                border.color: Qt.alpha(Color.foreground, 0.12)
                            }
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            ColumnLayout {
                                width: parent.width
                                spacing: 4
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label {
                                        text: win.label(modelData.sensor)
                                        textFormat: Text.PlainText
                                        color: Color.foreground
                                        font.bold: true
                                        font.pixelSize: 14
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                    WatchCheckBox {
                                        Accessible.name: "Enable " + win.label(modelData.sensor)
                                        checked: modelData.enabled !== false
                                        onToggled: {
                                            var rules = service.config.rules.slice();
                                            rules[index] = Object.assign({}, modelData, {
                                                enabled: checked
                                            });
                                            service.save({
                                                rules: rules
                                            });
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Label {
                                            text: win.ruleSummary(modelData)
                                            color: Color.foreground
                                            opacity: 0.8
                                            font.pixelSize: 12
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                        Label {
                                            text: modelData.camera ? "Camera · " + win.label(modelData.camera) : "Text notification"
                                            textFormat: Text.PlainText
                                            color: Color.foreground
                                            opacity: 0.55
                                            font.pixelSize: 11
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                    }
                                    WatchButton {
                                        text: "Test"
                                        enabled: service.state === "connected"
                                        onClicked: service.send({
                                            type: "test",
                                            rule: modelData
                                        })
                                    }
                                    WatchButton {
                                        text: "Edit"
                                        onClicked: win.editRule(index)
                                    }
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        WatchButton {
                            text: "+ Add rule"
                            enabled: service.state === "connected"
                            onClicked: {
                                win.resetEditor();
                                win.page = "edit";
                            }
                        }
                        Item {
                            Layout.fillWidth: true
                        }
                        WatchButton {
                            text: "Settings"
                            onClicked: win.page = "settings"
                        }
                    }
                }
                ColumnLayout {
                    visible: win.page === "edit"
                    Layout.fillWidth: true
                    spacing: 10
                    Label {
                        id: editorHeading
                        text: win.editIndex >= 0 ? "Editing: " + win.label(win.selectedSensor) : "Add an activity rule"
                        textFormat: Text.PlainText
                        font.pixelSize: 16
                        font.bold: true
                        color: Color.foreground
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    GridLayout {
                        columns: 2
                        Layout.fillWidth: true
                        enabled: service.state === "connected"
                        Label {
                            text: "Device"
                            color: Color.foreground
                        }
                        WatchComboBox {
                            id: sensor
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            model: win.sensors
                            textRole: "name"
                            currentIndex: win.selected(win.sensors, win.selectedSensor)
                            displayText: currentIndex < 0 ? "Choose a sensor or cover" : currentText
                            onActivated: {
                                win.selectedSensor = win.sensors[currentIndex].id;
                                win.selectedStates = RuleOptions.defaults(win.selectedSensor);
                                win.customMessages = ({});
                            }
                        }
                        Label {
                            text: "Notify when"
                            color: Color.foreground
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Repeater {
                                model: win.stateOptions
                                delegate: WatchCheckBox {
                                    required property var modelData
                                    text: modelData.label
                                    checked: win.selectedStates.indexOf(modelData.value) >= 0
                                    onToggled: {
                                        var states = win.selectedStates.filter(s => s !== modelData.value);
                                        if (checked)
                                            states.push(modelData.value);
                                        win.selectedStates = states;
                                    }
                                }
                            }
                            Label {
                                visible: win.selectedSensor.startsWith("cover.")
                                text: "Opening/Closing require your integration to report movement."
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                                color: Color.foreground
                                opacity: 0.65
                                font.pixelSize: 12
                            }
                        }
                        Label {
                            text: "Show"
                            color: Color.foreground
                        }
                        WatchComboBox {
                            id: camera
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            model: [
                                {
                                    name: "Text notification only",
                                    id: ""
                                }
                            ].concat(win.cameras)
                            textRole: "name"
                            currentIndex: win.selectedCamera ? win.selected(win.cameras, win.selectedCamera) + 1 : 0
                            onActivated: win.selectedCamera = currentIndex ? win.cameras[currentIndex - 1].id : ""
                        }
                        Label {
                            text: "Custom text"
                            color: Color.foreground
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label {
                                text: "Optional. Leave blank to use the device state."
                                color: Color.foreground
                                opacity: 0.65
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Repeater {
                                model: win.stateOptions
                                delegate: WatchField {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    visible: win.selectedStates.indexOf(modelData.value) >= 0
                                    placeholderText: modelData.label + " — automatic"
                                    text: win.customMessages[modelData.value] || ""
                                    selectByMouse: true
                                    maximumLength: 240
                                    onTextEdited: {
                                        var messages = Object.assign({}, win.customMessages);
                                        messages[modelData.value] = text;
                                        win.customMessages = messages;
                                    }
                                }
                            }
                        }
                        Item {
                            implicitWidth: 1
                            implicitHeight: 1
                        }
                        RowLayout {
                            WatchButton {
                                text: win.editIndex >= 0 ? "Save changes" : "Add rule"
                                enabled: sensor.currentIndex >= 0 && win.selectedStates.length > 0
                                onClicked: win.storeRule()
                            }
                            WatchButton {
                                text: "Cancel"
                                onClicked: {
                                    win.resetEditor();
                                    win.page = "rules";
                                }
                            }
                        }
                    }

                    WatchButton {
                        visible: win.editIndex >= 0
                        text: win.confirmRemove ? "Confirm removal" : "Remove rule"
                        onClicked: {
                            if (!win.confirmRemove) {
                                win.confirmRemove = true;
                                return;
                            }
                            var rules = service.config.rules.slice();
                            rules.splice(win.editIndex, 1);
                            service.save({
                                rules: rules
                            });
                            win.resetEditor();
                            win.page = "rules";
                        }
                    }
                }
                ColumnLayout {
                    visible: win.page === "settings"
                    Layout.fillWidth: true
                    spacing: 10
                    WatchButton {
                        text: "‹ Back"
                        onClicked: win.page = "rules"
                    }
                    Label {
                        text: "Home Assistant"
                        color: Color.foreground
                        font.bold: true
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        WatchField {
                            id: address
                            Layout.fillWidth: true
                            placeholderText: "http://homeassistant.local:8123"
                            text: service.config.url || ""
                            enabled: service.state !== "connected"
                            onAccepted: login.clicked()
                            selectByMouse: true
                        }
                        WatchButton {
                            id: login
                            text: "Sign in"
                            visible: service.state !== "connected"
                            enabled: service.ready
                            onClicked: {
                                service.errorMessage = "";
                                service.send({
                                    type: "login",
                                    url: address.text
                                });
                            }
                        }
                        WatchButton {
                            text: "Sign out"
                            visible: !!service.config.clientId
                            enabled: service.ready
                            onClicked: service.send({
                                type: "logout"
                            })
                        }
                    }
                    Label {
                        text: "Sign in securely in your browser. Your session is saved in your system keyring."
                        color: Color.foreground
                        opacity: 0.65
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Label {
                        text: "Notifications"
                        font.pixelSize: 16
                        font.bold: true
                        color: Color.foreground
                    }
                    GridLayout {
                        columns: 2
                        Layout.fillWidth: true
                        Label {
                            text: "Position"
                            color: Color.foreground
                        }
                        WatchComboBox {
                            Layout.fillWidth: true
                            model: ["Top right", "Bottom right", "Top left", "Bottom left"]
                            currentIndex: Math.max(0, win.positions.indexOf(service.config.position))
                            onActivated: service.save({
                                position: win.positions[currentIndex]
                            })
                        }
                        Label {
                            text: "Screen"
                            color: Color.foreground
                        }
                        WatchComboBox {
                            Layout.fillWidth: true
                            model: win.screenNames
                            currentIndex: Math.max(0, win.screenNames.indexOf(service.config.monitor || "Automatic"))
                            onActivated: service.save({
                                monitor: currentIndex ? win.screenNames[currentIndex] : ""
                            })
                        }
                        Label {
                            text: "Seconds visible"
                            color: Color.foreground
                        }
                        SpinBox {
                            from: 5
                            to: 120
                            value: service.config.duration
                            onValueModified: service.save({
                                duration: value
                            })
                        }
                    }
                    Label {
                        text: "Video previews are muted, up to 10 fps. Pinned previews stop after 10 minutes. Repeated notifications for the same state are limited to one every 30 seconds. Opposite states can notify immediately."
                        color: Color.foreground
                        opacity: 0.65
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Label {
                        text: "By Seigliva · 0.5.0"
                        color: Color.foreground
                        opacity: 0.55
                        font.pixelSize: 11
                    }
                }
            }
        }
    }
}
