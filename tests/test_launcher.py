import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Launcher(unittest.TestCase):
    def test_first_install_explains_missing_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            run = subprocess.run(["bash", str(ROOT / "run-bridge.sh")], env={**os.environ, "XDG_DATA_HOME": folder}, capture_output=True, text=True)
            self.assertEqual(run.returncode, 78)
            self.assertEqual(json.loads(run.stdout)["state"], "setup_required")

    def test_runtime_is_loaded_from_data_directory(self):
        with tempfile.TemporaryDirectory(prefix="ha watch ") as folder:
            python = Path(folder) / "seigliva.ha-watch/venv/bin/python"
            python.parent.mkdir(parents=True)
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            python.chmod(0o700)
            run = subprocess.run(["bash", str(ROOT / "run-bridge.sh")], env={**os.environ, "XDG_DATA_HOME": folder}, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0)
            self.assertEqual(run.stdout.splitlines(), ["-u", str(ROOT / "bridge.py")])
