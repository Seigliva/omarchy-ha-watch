#!/usr/bin/env bash
set -euo pipefail
plugin_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
plugin_target="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/seigliva.ha-watch"
runtime_dir="${XDG_DATA_HOME:-$HOME/.local/share}/seigliva.ha-watch/venv"
setup_mode="${1:-}"
[[ -z "$setup_mode" || "$setup_mode" == "--dependencies-only" ]] || { echo 'Usage: bash setup.sh [--dependencies-only]' >&2; exit 1; }

for dependency in python3 secret-tool xdg-open omarchy-shell; do
    command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency" >&2; exit 1; }
done
if [[ "$setup_mode" != "--dependencies-only" && ( -e "$plugin_target" || -L "$plugin_target" ) ]]; then
    [[ "$(readlink -f -- "$plugin_target")" == "$plugin_root" ]] || {
        echo "A different seigliva.ha-watch installation already exists at $plugin_target" >&2
        exit 1
    }
fi
python3 -m venv "$runtime_dir"
"$runtime_dir/bin/python" -m pip install --require-hashes --only-binary=:all: -r "$plugin_root/requirements.lock"
[[ "$setup_mode" != "--dependencies-only" ]] || exit 0
python3 "$plugin_root/migrate.py"
mkdir -p -- "$(dirname -- "$plugin_target")"
if [[ ! -e "$plugin_target" ]]; then
    ln -s -- "$plugin_root" "$plugin_target"
fi
omarchy-shell shell rescanPlugins
omarchy-shell shell reloadConfig
omarchy-shell shell enablePlugin seigliva.ha-watch '{}'
echo 'Home Assistant Watch is ready. Click the house button in the bar to sign in.'
