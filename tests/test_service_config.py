"""Run the real QML service with a fake shell and transport, without HA."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("qs"), "Quickshell required for QML integration")
class ServiceConfig(unittest.TestCase):
    def check_api(self, scoped):
        with tempfile.TemporaryDirectory(prefix="ha-watch-qml-") as folder:
            root = Path(folder)
            shutil.copy(ROOT / "Service.qml", root)
            (root / "Preview.qml").write_text('import QtQuick\nItem { property var service; function dismiss() {} function handle(p) {} }\n')
            (root / "run-bridge.sh").write_text('''#!/bin/bash
printf '%s\\n' '{"type":"ready"}'
while IFS= read -r line; do
  printf '%s\\n' '{"type":"status","state":"connected","message":"configured"}'
done
''')
            prop = "barConfig" if scoped else "shellConfig"
            first = '{layout: {right: [harness.entry]}}' if scoped else '{bar: {layout: {right: [harness.entry]}}}'
            second = '{layout: {left: [harness.updated]}}' if scoped else '{bar: {layout: {left: [harness.updated]}}}'
            (root / "shell.qml").write_text('''import QtQuick
import Quickshell
ShellRoot {
    id: harness
    property var entry: ({id: "seigliva.ha-watch", url: "http://example.invalid", clientId: "saved-client", rules: [{sensor: "binary_sensor.door"}]})
    property var updated: Object.assign({}, entry, {duration: 42})
    QtObject { id: api; property var PROP: (FIRST) }
    Service { id: service; shell: api }
    property int phase: 0
    Timer {
        interval: 100; running: true; repeat: true
        onTriggered: {
            if (service.state !== "connected") return
            if (service.config.clientId !== "saved-client" || service.config.rules.length !== 1) {
                console.log("FAIL: saved config missing"); Qt.quit(); return
            }
            if (phase === 0) { phase = 1; api.PROP = SECOND; return }
            if (service.config.duration !== 42) { console.log("FAIL: update missing"); Qt.quit(); return }
            console.log("PASS: restored and updated"); Qt.quit()
        }
    }
    Timer { interval: 5000; running: true; onTriggered: { console.log("FAIL: startup timeout", service.ready, service.state, JSON.stringify(service.config), service.errorMessage, JSON.stringify(api.PROP), service.shell); Qt.quit() } }
}
'''.replace("PROP", prop).replace("FIRST", first).replace("SECOND", second))
            run = subprocess.run(["qs", "-p", str(root / "shell.qml"), "--no-color"],
                                 env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                                 capture_output=True, text=True, timeout=12)
            output = run.stdout + run.stderr
            self.assertIn("PASS: restored and updated", output)
            self.assertNotIn("FAIL:", output)

    def test_scoped_api_restores_connection_and_rules(self):
        self.check_api(True)

    def test_legacy_api_restores_connection_and_rules(self):
        self.check_api(False)
