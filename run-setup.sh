#!/usr/bin/env bash
set -euo pipefail
plugin_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null; then
    echo '{"message":"Python is missing. Install the python package, then try again."}'
    exit 1
fi
exec python3 "$plugin_root/install-runtime.py"
