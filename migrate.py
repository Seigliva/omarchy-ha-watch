#!/usr/bin/env python3
"""Migrate the initial plugin ID, retaining settings and making a private backup."""
import argparse
import copy
import json
import os
from pathlib import Path
import tempfile

OLD_ID = "ha.watch"
PLUGIN_ID = "seigliva.ha-watch"


def entries(config):
    for entry in config.get("plugins", []):
        yield entry
    for section in config.get("bar", {}).get("layout", {}).values():
        yield from section


def migrate(config):
    result = copy.deepcopy(config)
    old = [e for e in entries(result) if e.get("id") == OLD_ID]
    new = [e for e in entries(result) if e.get("id") == PLUGIN_ID]
    if old and new:
        raise ValueError("Both plugin IDs have settings. Merge them before running setup; no settings were changed.")
    for entry in old:
        entry["id"] = PLUGIN_ID
    disabled = result.get("disabledPlugins", [])
    result["disabledPlugins"] = list(dict.fromkeys(PLUGIN_ID if i == OLD_ID else i for i in disabled))
    if "disabledPlugins" not in config:
        result.pop("disabledPlugins")
    return result


def migrate_file(path):
    if not path.exists():
        return None
    original = path.read_bytes()
    updated = migrate(json.loads(original))
    if updated == json.loads(original):
        return None
    fd, backup = tempfile.mkstemp(prefix="shell-before-ha-watch-", suffix=".json", dir=path.parent)
    with os.fdopen(fd, "wb") as out:
        out.write(original)
    fd, pending = tempfile.mkstemp(prefix=".ha-watch-migration-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(updated, out, indent=2, ensure_ascii=False)
            out.write("\n")
        if path.read_bytes() != original:
            raise RuntimeError("Shell settings changed during migration. Run setup again.")
        os.replace(pending, path)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)
    return backup


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omarchy/shell.json")
    args = parser.parse_args()
    backup = migrate_file(args.config)
    if backup:
        print(f"Migrated settings to {PLUGIN_ID}. Backup: {backup}")
