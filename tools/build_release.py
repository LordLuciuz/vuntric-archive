"""Create a strictly scoped, hashed VuntricArchive_Update_<version>.zip."""
from __future__ import annotations
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ["app.py", "storage.py", "archive_updater.py", "requirements.txt"]


def build(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Version must look like 0.1.3")
    files = CORE + [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "modules").glob("*.py"))] if (ROOT / "modules").exists() else CORE[:]
    for f in files:
        if not (ROOT / f).is_file():
            raise ValueError(f"Missing required source: {f}")
        if f.endswith(".py"):
            compile((ROOT / f).read_text(encoding="utf-8"), f, "exec")
    manifest = {
        "format": "vuntric-app-update",
        "schema_version": 1,
        "version": version,
        "description": f"Vûntric Linguistic Archive release {version}",
        "files": [
            {"path": f, "sha256": hashlib.sha256((ROOT / f).read_bytes()).hexdigest()}
            for f in files
        ],
    }
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"VuntricArchive_Update_{version}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("archive-update.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for f in files:
            z.write(ROOT / f, arcname=f)
    print(out)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/build_release.py 0.1.3")
    build(sys.argv[1])
