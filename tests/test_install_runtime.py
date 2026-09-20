import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install_runtime', ROOT / 'install-runtime.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallRuntime(unittest.TestCase):
    def run_installer(self, code):
        with tempfile.TemporaryDirectory(prefix='watch setup ') as folder:
            path = Path(folder)
            shutil.copy2(ROOT / 'install-runtime.py', path / 'install-runtime.py')
            (path / 'setup.sh').write_text('echo secret-index-url\n[ "$1" = --dependencies-only ] || exit 99\nexit ' + str(code))
            tools = path / 'bin'
            tools.mkdir()
            for name in ['python3', 'secret-tool', 'xdg-open', 'omarchy-shell', 'ffmpeg', 'ffprobe']:
                file = tools / name
                file.write_text('#!/bin/sh\nexit 0\n')
                file.chmod(0o700)
            return subprocess.run([sys.executable, str(path / 'install-runtime.py')],
                env={**os.environ, 'PATH': str(tools) + os.pathsep + os.environ['PATH']},
                capture_output=True, text=True, timeout=10)

    def test_success_reports_progress_without_raw_logs(self):
        result = self.run_installer(0)
        self.assertEqual(result.returncode, 0)
        messages = [json.loads(line)['message'] for line in result.stdout.splitlines()]
        self.assertEqual(len(messages), 2)
        self.assertIn('complete', messages[-1])
        self.assertNotIn('secret-index-url', result.stdout + result.stderr)

    def test_failure_has_retry_guidance_without_raw_logs(self):
        result = self.run_installer(7)
        self.assertEqual(result.returncode, 1)
        self.assertIn('try again', result.stdout)
        self.assertNotIn('secret-index-url', result.stdout + result.stderr)

    def test_missing_tools_do_not_start_installation(self):
        with patch.object(installer.shutil, 'which', return_value=None), patch.object(installer.subprocess, 'Popen') as start, patch.object(installer, 'report') as report:
            self.assertEqual(installer.main(), 1)
            start.assert_not_called()
            self.assertIn('Missing system tools', report.call_args.args[0])

    def test_timeout_kills_and_reaps_process_group(self):
        process = MagicMock(pid=12345)
        process.wait.side_effect = [subprocess.TimeoutExpired('setup', 180), 0]
        with patch.object(installer.shutil, 'which', return_value='/bin/tool'), patch.object(installer.subprocess, 'Popen', return_value=process) as start, patch.object(installer.os, 'killpg') as kill, patch.object(installer.signal, 'signal'), patch.object(installer, 'report') as report:
            self.assertEqual(installer.main(), 1)
            self.assertTrue(start.call_args.kwargs['start_new_session'])
            kill.assert_called_once_with(12345, installer.signal.SIGKILL)
            self.assertEqual(process.wait.call_count, 2)
            self.assertIn('timed out', report.call_args.args[0])
