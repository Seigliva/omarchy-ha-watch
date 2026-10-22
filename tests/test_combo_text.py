"""Render real dropdowns and check that device names never fetch images."""
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = shutil.which('qmltestrunner') or shutil.which('qmltestrunner6') or '/usr/lib/qt6/bin/qmltestrunner'


@unittest.skipUnless(Path(RUNNER).is_file(), 'Qt Quick Test runner required')
class ComboText(unittest.TestCase):
    def test_plain_names_and_selection(self):
        requests = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_response(404)
                self.end_headers()
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                shutil.copy(ROOT / 'WatchComboBox.qml', root)
                commons = root / 'qs/Commons'
                commons.mkdir(parents=True)
                (commons / 'qmldir').write_text('module qs.Commons\nsingleton Color 1.0 Color.qml\n')
                (commons / 'Color.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject { property color foreground: "white"; property var popups: ({background: "#222222"}) }')
                name = '<img src="http://127.0.0.1:%d/device.png"> Entré & <b>kamera</b>' % server.server_port
                (root / 'tst_combo.qml').write_text('''import QtQuick
import QtTest
Item {
    width: 600; height: 500
    WatchComboBox { id: combo; width: 500; textRole: "name"; model: [{name: NAME, id: "camera.entry"}, {name: "Dør æøå & garage", id: "binary_sensor.door"}] }
    SignalSpy { id: activation; target: combo; signalName: "activated" }
    TestCase {
        name: "UntrustedNames"; when: windowShown
        function test_names_and_selection() {
            compare(combo.palette.text, "#ffffff")
            compare(combo.palette.base, "#222222")
            compare(combo.currentText, NAME)
            combo.popup.open()
            tryCompare(combo.popup, "visible", true)
            wait(350)
            var row = combo.popup.contentItem.itemAtIndex(0)
            verify(row !== null)
            compare(row.contentItem.text, NAME)
            compare(row.contentItem.textFormat, Text.PlainText)
            // Native keyboard selection must still emit activated and retain IDs.
            combo.forceActiveFocus()
            keyClick(Qt.Key_Down)
            keyClick(Qt.Key_Return)
            tryCompare(combo, "currentIndex", 1)
            compare(combo.model[combo.currentIndex].id, "binary_sensor.door")
            verify(activation.count > 0)
            compare(combo.displayText, "Dør æøå & garage")
            // The same control also serves plain string position/screen models.
            combo.textRole = ""
            combo.model = ["Automatic", NAME, "Top left"]
            combo.currentIndex = 1
            compare(combo.currentText, NAME)
            combo.popup.open()
            wait(350)
            row = combo.popup.contentItem.itemAtIndex(1)
            verify(row !== null)
            compare(row.contentItem.text, NAME)
            compare(row.contentItem.textFormat, Text.PlainText)
            mouseClick(row, 10, row.height / 2)
            tryCompare(combo.popup, "visible", false)
            compare(combo.currentIndex, 1)
            wait(350)
        }
    }
}
'''.replace('NAME', json.dumps(name)))
                run = subprocess.run([RUNNER, '-input', str(root), '-import', str(root)],
                    env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software'},
                    capture_output=True, text=True, timeout=20)
                self.assertEqual(requests, [], 'Rendering a device name requested an image')
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
