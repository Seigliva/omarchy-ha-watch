#!/usr/bin/env bash
set -euo pipefail
plugin_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
runtime_dir="${XDG_DATA_HOME:-$HOME/.local/share}/seigliva.ha-watch/venv"
if [[ ! -x "$runtime_dir/bin/python" ]] || ! "$runtime_dir/bin/python" -c "import aiohttp" >/dev/null 2>&1; then
    echo '{"type":"status","state":"setup_required","message":"Open Home Assistant Watch and choose Finish installation."}'
    exit 78
fi
exec "$runtime_dir/bin/python" -u "$plugin_root/bridge.py"
