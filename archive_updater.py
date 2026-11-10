"""Vûntric Archive application updater (standard-library only).

Applies explicitly chosen, hash-checked application update ZIPs. Never patches
user data. All updates can be reversed from update_backups/.
"""
from __future__ import annotations

import argparse
import re
import urllib.request
import urllib.error
from urllib.parse import urlparse, unquote
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

APP_ROOT = Path(__file__).resolve().parent
BACKUPS = APP_ROOT / "update_backups"
VERSION_FILE = APP_ROOT / "archive-version.json"
FORMAT = "vuntric-app-update"
MAX_TOTAL_SIZE = 25 * 1024 * 1024
MAX_SINGLE_SIZE = 10 * 1024 * 1024


class UpdateError(Exception):
    pass


def safe_relpath(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise UpdateError(f"Invalid update path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(p in (".", "..", "") for p in value.split("/")):
        raise UpdateError(f"Invalid update path: {value!r}")
    parts = pure.parts
    if len(parts) == 1:
        if value not in {"app.py", "storage.py", "archive_updater.py", "requirements.txt", "README.txt"}:
            raise UpdateError(f"Update cannot modify protected path: {value}")
    elif len(parts) == 2 and parts[0] == "modules" and parts[1].endswith(".py") and not parts[1].startswith("."):
        pass
    else:
        raise UpdateError(f"Update cannot modify protected path: {value}")
    return Path(*parts)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def ensure_archive():
    if not (APP_ROOT / "app.py").is_file() or not (APP_ROOT / "storage.py").is_file():
        raise UpdateError("Move this updater into your existing Archive folder next to app.py and storage.py.")


def app_running():
    try:
        with socket.create_connection(("127.0.0.1", 8502), timeout=0.45):
            return True
    except OSError:
        return False


def validate_package(zip_path):
    if not zip_path.is_file():
        raise UpdateError(f"Update ZIP not found: {zip_path}")
    if zip_path.stat().st_size > MAX_TOTAL_SIZE:
        raise UpdateError("Package too large for the basic updater (25 MB limit).")
    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
        if len(names) > 100 or len(set(names)) != len(names):
            raise UpdateError("Too many or duplicate ZIP members.")
        if "archive-update.json" not in names:
            raise UpdateError("Missing archive-update.json. This is not an application update package.\n"
                              "For language data use the Import / Export page inside the archive.")
        try:
            manifest = json.loads(z.read("archive-update.json").decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise UpdateError(f"Invalid update manifest: {exc}") from exc
        if manifest.get("format") != FORMAT or manifest.get("schema_version") != 1:
            raise UpdateError("Unsupported application update format/schema.")
        version = manifest.get("version")
        if not isinstance(version, str) or not 1 <= len(version) <= 60:
            raise UpdateError("Update manifest has no valid version.")
        files = manifest.get("files")
        if not isinstance(files, list) or not files or len(files) > 100:
            raise UpdateError("Update manifest has no valid files list.")
        expected_names = {"archive-update.json"}
        prepared = []
        uncompressed = 0
        for item in files:
            if not isinstance(item, dict):
                raise UpdateError("Invalid file entry in update manifest.")
            rel = safe_relpath(item.get("path"))
            rel_posix = rel.as_posix()
            if rel_posix in expected_names:
                raise UpdateError(f"Duplicate file in manifest: {rel_posix}")
            expected_names.add(rel_posix)
            digest = item.get("sha256")
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise UpdateError(f"Invalid SHA-256 checksum for {rel_posix}.")
            if rel_posix not in names:
                raise UpdateError(f"Missing file from update ZIP: {rel_posix}")
            info = z.getinfo(rel_posix)
            if info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise UpdateError(f"Invalid ZIP member type: {rel_posix}")
            uncompressed += info.file_size
            if info.file_size > MAX_SINGLE_SIZE or uncompressed > MAX_TOTAL_SIZE:
                raise UpdateError("ZIP contains too much uncompressed data.")
            content = z.read(rel_posix)
            if sha256(content) != digest:
                raise UpdateError(f"Checksum mismatch: {rel_posix}")
            if rel.suffix == ".py":
                try:
                    compile(content.decode("utf-8-sig"), rel_posix, "exec")
                except (SyntaxError, UnicodeError) as exc:
                    raise UpdateError(f"Invalid Python file {rel_posix}: {exc}") from exc
            prepared.append((rel, content))
        if set(names) != expected_names:
            raise UpdateError("Unexpected files inside ZIP: " + ", ".join(sorted(set(names) - expected_names)))
    return manifest, prepared


def write_atomic(destination, content):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".updating-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def make_backup(changes, old_version):
    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUPS / stamp
    n = 2
    while target.exists():
        target = BACKUPS / f"{stamp}-{n}"
        n += 1
    target.mkdir()
    previous_files = []
    for rel, _content in changes:
        existing = APP_ROOT / rel
        was_present = existing.exists()
        if was_present:
            stored = target / "original" / rel
            stored.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(existing, stored)
        previous_files.append({"path": rel.as_posix(), "existed": was_present})
    if VERSION_FILE.exists():
        shutil.copy2(VERSION_FILE, target / "original-version.json")
    record = {"format": "vuntric-app-backup", "files": previous_files,
              "previous_version_record_existed": VERSION_FILE.exists(),
              "previous_version": old_version}
    (target / "restore.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def restore_backup(backup):
    record_file = backup / "restore.json"
    if not record_file.exists():
        raise UpdateError("This backup has no restore metadata.")
    record = json.loads(record_file.read_text(encoding="utf-8"))
    if record.get("format") != "vuntric-app-backup":
        raise UpdateError("This is not an archive updater backup.")
    for item in record["files"]:
        rel = safe_relpath(item["path"])
        destination = APP_ROOT / rel
        if item["existed"]:
            original = backup / "original" / rel
            if not original.exists():
                raise UpdateError(f"Backup file is missing: {rel}")
            write_atomic(destination, original.read_bytes())
        elif destination.exists():
            destination.unlink()
    if record["previous_version_record_existed"]:
        write_atomic(VERSION_FILE, (backup / "original-version.json").read_bytes())
    elif VERSION_FILE.exists():
        VERSION_FILE.unlink()


def current_version():
    try:
        return json.loads(VERSION_FILE.read_text(encoding="utf-8")).get("version", "untracked")
    except (FileNotFoundError, ValueError, OSError):
        return "untracked"


def apply(zip_path):
    ensure_archive()
    if app_running():
        raise UpdateError("The archive appears to be running on port 8502.\n"
                          "Stop it with Ctrl+C in its Command Prompt, then retry.")
    manifest, files = validate_package(zip_path)
    version = manifest["version"]
    print("\nVÛNTRIC ARCHIVE — APPLICATION UPDATE")
    print(f"Current tracked version: {current_version()}")
    print(f"Package version: {version}")
    print("Changes:")
    to_change = []
    for rel, content in files:
        dest = APP_ROOT / rel
        changed = not dest.is_file() or sha256(dest.read_bytes()) != sha256(content)
        print(f"  {'UPDATE' if changed else 'ALREADY CURRENT'}  {rel.as_posix()}")
        if changed:
            to_change.append((rel, content))
    print("\nYour data/ folder and SQLite database are not part of app updates.")
    if not to_change:
        print("\nNo application files need replacing.")
        write_atomic(VERSION_FILE, json.dumps({"version": version, "updated_at": datetime.now().isoformat()}, indent=2).encode("utf-8"))
        return
    confirm = input("\nApply this update? Type YES to proceed: ").strip()
    if confirm != "YES":
        print("Update cancelled; nothing changed.")
        return
    backup = make_backup(to_change, current_version())
    try:
        for rel, content in to_change:
            write_atomic(APP_ROOT / rel, content)
        write_atomic(VERSION_FILE, json.dumps({"version":version, "updated_at":datetime.now().isoformat()}, indent=2).encode("utf-8"))
    except Exception:
        restore_backup(backup)
        print("An error occurred. Previous application files restored.")
        raise
    print(f"\nSUCCESS — updated to {version}.")
    print(f"Previous code saved in: {backup}")
    print("Start Archive.bat to use the updated application.")


def find_package():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(title="Select Vûntric Archive application update ZIP",
                                          initialdir=str(APP_ROOT),
                                          filetypes=[("ZIP update packages", "*.zip")])
        root.destroy()
        return Path(path) if path else None
    except Exception:
        entered = input("Enter the full path to an update ZIP: ").strip().strip('"')
        return Path(entered) if entered else None


# GitHub Releases integration. No GitHub account token is stored locally.
CONFIG_FILE = APP_ROOT / "update-config.json"
REPO_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}$")
SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def normalize_repo(raw):
    value = raw.strip().rstrip("/")
    if value.startswith("https://github.com/"):
        value = value[len("https://github.com/"):]
    if value.endswith(".git"):
        value = value[:-4]
    if not REPO_PATTERN.fullmatch(value):
        raise UpdateError("Enter a valid GitHub owner/repository, such as username/vuntric-archive.")
    return value


def configure_repo():
    print("\nGITHUB UPDATER SETUP (ONE TIME)")
    print("Only a PUBLIC GitHub repository is supported by this updater.")
    print("Publish application code there, never your data/, .venv/ or language exports.")
    raw = input("Enter GitHub repository URL or owner/repo (blank to cancel): ").strip()
    if not raw:
        print("Setup cancelled.")
        return None
    repo = normalize_repo(raw)
    write_atomic(CONFIG_FILE, json.dumps({"repository": repo}, indent=2).encode("utf-8"))
    print(f"Saved GitHub repository: {repo}")
    return repo


def configured_repo():
    try:
        content = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return normalize_repo(content["repository"])
    except FileNotFoundError:
        return None
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise UpdateError("The update-config.json file is malformed; run --setup to configure again.") from exc


def version_tuple(value):
    match = SEMVER.fullmatch(str(value))
    return tuple(int(group) for group in match.groups()) if match else None


def get_latest_release(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "VuntricArchiveUpdater/1.1",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise UpdateError(f"GitHub returned HTTP {response.status}.")
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise UpdateError("GitHub release metadata is unexpectedly large.")
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("No published release found. Ensure the repository is public and has a published GitHub Release.") from exc
        if exc.code == 403:
            raise UpdateError("GitHub API access was blocked or rate limited. Try again later.") from exc
        raise UpdateError(f"GitHub API failed with HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(f"Could not connect to GitHub: {exc.reason}") from exc


def select_release_asset(repo, release):
    tag = release.get("tag_name", "")
    version = version_tuple(tag)
    if version is None:
        raise UpdateError(f"Latest GitHub release uses an unsupported version tag: {tag!r}. Expected v0.1.3.")
    version_text = ".".join(str(x) for x in version)
    expected_name = f"VuntricArchive_Update_{version_text}.zip"
    matching = [asset for asset in release.get("assets", []) if asset.get("name") == expected_name]
    if len(matching) != 1:
        raise UpdateError(f"Release {tag} must include exactly one asset named {expected_name}.")
    asset = matching[0]
    digest = asset.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise UpdateError("Release asset does not provide a valid GitHub SHA-256 digest; refusing download.")
    url = asset.get("browser_download_url", "")
    parsed = urlparse(url)
    prefix = f"/{repo}/releases/download/"
    if (parsed.scheme != "https" or parsed.hostname != "github.com"
            or not parsed.path.startswith(prefix)
            or unquote(parsed.path.split("/")[-1]) != expected_name
            or parsed.username or parsed.password):
        raise UpdateError("Release asset has an unexpected download URL; refusing download.")
    size = asset.get("size", -1)
    if not isinstance(size, int) or size < 1 or size > MAX_TOTAL_SIZE:
        raise UpdateError("Release ZIP has an invalid size or exceeds 25 MB.")
    return version, asset, digest.split(":", 1)[1]


def download_release_asset(asset, expected_digest, destination):
    request = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "VuntricArchiveUpdater/1.1"})
    digest = hashlib.sha256()
    count = 0
    try:
        with urllib.request.urlopen(request, timeout=45) as response, destination.open("wb") as output:
            if response.status != 200:
                raise UpdateError(f"Release download returned HTTP {response.status}.")
            while True:
                block = response.read(128 * 1024)
                if not block:
                    break
                count += len(block)
                if count > MAX_TOTAL_SIZE:
                    raise UpdateError("Downloaded update exceeds 25 MB limit.")
                output.write(block)
                digest.update(block)
    except urllib.error.URLError as exc:
        raise UpdateError(f"Could not download GitHub release: {exc.reason}") from exc
    if count != asset["size"] or digest.hexdigest() != expected_digest:
        raise UpdateError("Downloaded file size/checksum mismatch. No files were changed.")


def update_from_github():
    ensure_archive()
    if app_running():
        raise UpdateError("Close the archive (Ctrl+C in its Command Prompt) before updating.")
    repo = configured_repo()
    if not repo:
        repo = configure_repo()
        if not repo:
            return
    print(f"\nChecking GitHub Releases: {repo}")
    release = get_latest_release(repo)
    latest, asset, expected_digest = select_release_asset(repo, release)
    installed = version_tuple(current_version())
    print(f"Installed application version: {current_version()}")
    print(f"Latest release: {release['tag_name']}")
    if installed is not None and latest <= installed:
        print("\nYou're up to date; no application files were changed.")
        return
    print("\nRelease notes:")
    print((release.get("body") or "No release notes provided.")[:1200])
    print("\nDownloading and verifying application update...")
    with tempfile.TemporaryDirectory(prefix="vuntric-update-") as temp_dir:
        temp = Path(temp_dir) / asset["name"]
        download_release_asset(asset, expected_digest, temp)
        manifest, _files = validate_package(temp)
        if version_tuple(manifest["version"]) != latest:
            raise UpdateError("Release tag and package manifest version disagree; refusing update.")
        apply(temp)


def main():
    parser = argparse.ArgumentParser(description="Update the local Vûntric Archive application.")
    parser.add_argument("package", nargs="?", help="Legacy manual update ZIP path")
    parser.add_argument("--restore", action="store_true", help="Restore most recent code backup")
    parser.add_argument("--setup", action="store_true", help="Set a GitHub repository for releases")
    parser.add_argument("--local", action="store_true", help="Choose a downloaded local update ZIP")
    args = parser.parse_args()
    try:
        ensure_archive()
        if args.setup:
            configure_repo()
        elif args.restore:
            if app_running():
                raise UpdateError("Stop the archive before restoring an app backup.")
            backups = sorted(p for p in BACKUPS.iterdir() if p.is_dir() and (p / "restore.json").exists()) if BACKUPS.exists() else []
            if not backups:
                raise UpdateError("No updater backups exist yet.")
            backup = backups[-1]
            print(f"Restore application code from: {backup.name}")
            print("Language records in data/ will not be touched.")
            if input("Type RESTORE to continue: ").strip() == "RESTORE":
                restore_backup(backup)
                print("Restored previous application files.")
            else:
                print("Cancelled.")
        elif args.package or args.local:
            pkg = Path(args.package).expanduser() if args.package else find_package()
            if pkg:
                apply(pkg.resolve())
            else:
                print("Cancelled; no update selected.")
        else:
            update_from_github()
    except (UpdateError, ValueError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"\nERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
