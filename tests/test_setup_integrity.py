"""Exercise the real setup script offline with a harmless local wheel."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class SetupIntegrity(unittest.TestCase):
    def run_setup(self, *, tamper=False, include_hash=True):
        with tempfile.TemporaryDirectory(prefix="ha-watch-integrity-") as folder:
            root = Path(folder)
            shutil.copy2(ROOT / "setup.sh", root / "setup.sh")
            wheels = root / "wheels"
            wheels.mkdir()
            wheel = wheels / "watch_fixture-1.0-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("watch_fixture/__init__.py", "")
                archive.writestr("watch_fixture-1.0.dist-info/METADATA", "Metadata-Version: 2.1\nName: watch-fixture\nVersion: 1.0\n")
                archive.writestr("watch_fixture-1.0.dist-info/WHEEL", "Wheel-Version: 1.0\nGenerator: integrity-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
                archive.writestr("watch_fixture-1.0.dist-info/RECORD", "")
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            requirement = "watch-fixture==1.0"
            if include_hash:
                requirement += f" --hash=sha256:{digest}"
            (root / "requirements.lock").write_text(requirement + "\n")
            if tamper:
                with wheel.open("ab") as output:
                    output.write(b"unexpected bytes")
            commands = root / "bin"
            commands.mkdir()
            (commands / "python3").symlink_to(sys.executable)
            for name in ["secret-tool", "xdg-open", "omarchy-shell"]:
                command = commands / name
                command.write_text("#!/bin/sh\nexit 0\n")
                command.chmod(0o700)
            env = {k: v for k, v in os.environ.items() if not k.startswith("PIP_")}
            env.update(PATH=str(commands) + os.pathsep + env["PATH"],
                       XDG_DATA_HOME=str(root / "data"), XDG_CONFIG_HOME=str(root / "config"),
                       PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX="1", PIP_FIND_LINKS=str(wheels),
                       PIP_NO_CACHE_DIR="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
            run = subprocess.run(["bash", str(root / "setup.sh"), "--dependencies-only"],
                                 env=env, capture_output=True, text=True, timeout=60)
            return run.returncode, run.stdout + run.stderr

    def test_verified_wheel_installs(self):
        code, output = self.run_setup()
        self.assertEqual(code, 0, output)
        self.assertIn("Successfully installed", output)

    def test_tampered_wheel_is_rejected(self):
        code, output = self.run_setup(tamper=True)
        self.assertNotEqual(code, 0, output)
        self.assertIn("DO NOT MATCH THE HASHES", output)

    def test_missing_hash_is_rejected(self):
        code, output = self.run_setup(include_hash=False)
        self.assertNotEqual(code, 0, output)
        self.assertIn("Hashes are required", output)
