#!/usr/bin/env python3
"""Refresh artifact hashes for the existing exact pins; never update versions.

Download each non-yanked PyPI wheel, verify its published SHA-256, and record
its independently calculated hash. Source archives are deliberately excluded.
Run manually and review the diff before committing; never run during setup.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def checked_hash(artifact):
    digest = hashlib.sha256()
    with urlopen(artifact["url"], timeout=60) as response:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != artifact["digests"]["sha256"]:
        raise ValueError(f"PyPI hash mismatch: {artifact['filename']}")
    return artifact["filename"], actual


def main():
    lock = ROOT / "requirements.lock"
    pins = re.findall(r"^([a-zA-Z0-9_.-]+)==([^\s\\]+)", lock.read_text(), re.MULTILINE)
    if not pins:
        raise ValueError("No exact dependency pins found")
    lines = ["# Exact pins and verified wheel SHA-256 hashes from https://pypi.org.",
             "# Regenerate explicitly: python3 scripts/lock-dependencies.py",
             "# Installation accepts wheels only; source builds are not permitted.",
             "--only-binary=:all:", "--require-hashes", ""]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, version in pins:
            with urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as response:
                release = json.load(response)
            wheels = [a for a in release["urls"] if a["packagetype"] == "bdist_wheel" and not a["yanked"]]
            if not wheels:
                raise ValueError(f"No non-yanked wheels: {name}=={version}")
            verified = sorted(pool.map(checked_hash, wheels))
            lines.append(f"{name}=={version} \\")
            for i, (filename, digest) in enumerate(verified):
                lines.append(f"    --hash=sha256:{digest}" + (" \\" if i < len(verified) - 1 else ""))
            lines.append("")
            print(f"Verified {name}=={version}: {len(verified)} wheels", flush=True)
    lock.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
