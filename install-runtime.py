#!/usr/bin/env python3
"""User-triggered setup, with bounded lifetime and credential-free UI messages."""
import contextlib
import os
import signal
import json
from pathlib import Path
import shutil
import subprocess
import sys


def report(message):
    print(json.dumps({'message': message}), flush=True)


def main():
    missing = [name for name in ('python3', 'secret-tool', 'xdg-open', 'omarchy-shell', 'ffmpeg', 'ffprobe')
               if not shutil.which(name)]
    if missing:
        report('Missing system tools: ' + ', '.join(missing) + '. Install the system requirements listed in the README, then try again.')
        return 1
    report('Preparing the runtime and downloading verified packages…')
    # Do not forward pip output: custom index URLs can contain credentials.
    def interrupted(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    process = subprocess.Popen(['bash', str(Path(__file__).with_name('setup.sh')), '--dependencies-only'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        code = process.wait(timeout=180)
    except subprocess.TimeoutExpired:
        report('Installation timed out. Check your connection and try again. You can also use the manual command below.')
        return 1
    finally:
        # Stop pip/venv children too if the shell closes or the deadline expires.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    if code:
        report('Installation failed. Check your connection and system requirements, then try again. The manual command below shows detailed errors.')
        return 1
    report('Installation complete. Starting Home Assistant Watch…')
    return 0


if __name__ == '__main__':
    sys.exit(main())
