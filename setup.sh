#!/usr/bin/env bash
set -euo pipefail
plugin_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
plugin_target="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/ha.watch"

for dependency in python3 secret-tool xdg-open omarchy-shell; do
    command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency" >&2; exit 1; }
done
if [[ -e "$plugin_target" || -L "$plugin_target" ]]; then
    [[ "$(readlink -f -- "$plugin_target")" == "$plugin_root" ]] || {
        echo "A different ha.watch installation already exists at $plugin_target" >&2
        exit 1
    }
fi
python3 -m venv "$plugin_root/.venv"
"$plugin_root/.venv/bin/pip" install -r "$plugin_root/requirements.lock"
mkdir -p -- "$(dirname -- "$plugin_target")"
if [[ ! -e "$plugin_target" ]]; then
    ln -s -- "$plugin_root" "$plugin_target"
fi
omarchy-shell shell rescanPlugins
omarchy-shell shell enablePlugin ha.watch '{}'
echo 'Home Assistant Watch is ready. Click the house button in the bar to sign in.'
