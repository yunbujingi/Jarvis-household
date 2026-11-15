"""Private, consistent backup including the key; never overwrites a target."""
import argparse
import hashlib
import json
from importlib.metadata import version
import os
from pathlib import Path
import sqlite3

from .store import Store


def backup(source, destination):
    source, destination = Path(source), Path(destination)
    if not (source / "home.sqlite3").is_file() or not (source / "key").is_file():
        raise ValueError("source_not_initialized")
    store = Store(source)
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    key = destination / "key"
    fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(store.key)
        f.flush()
        os.fsync(f.fileno())
    target = destination / "home.sqlite3"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    with store.connect() as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    restored = Store(destination)
    with restored.connect() as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("backup_integrity_failed")
        for table, prefix in (("records", "record:"), ("operations", "operation:"), ("meta", "meta:")):
            for rid, payload in db.execute(f"SELECT id,payload FROM {table}"):
                restored.unpack(prefix + rid, payload)
    manifest = {"format": 1, "database_version": 1, "package_version": version("jarvis-home"),
                "sha256": {name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
                           for name in ("key", "home.sqlite3")}}
    with (destination / "backup.json").open("x") as f:
        json.dump(manifest, f, indent=2)
    (destination / "backup.json").chmod(0o600)
    return destination


def restore(source, destination):
    """Validate a backup and restore into a new directory, never over live data."""
    source = Path(source)
    manifest_path = source / "backup.json"
    if manifest_path.is_symlink():
        raise ValueError("unsafe_backup_manifest")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != 1 or manifest.get("database_version") != 1:
        raise ValueError("unsupported_backup_format")
    for name in ("key", "home.sqlite3"):
        path = source / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"].get(name):
            raise ValueError("backup_checksum_mismatch")
    return backup(source, destination)


def restore_main():
    parser = argparse.ArgumentParser(description="Restore verified backup into a NEW private directory")
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    restore(args.source, args.destination)
    print("restore_verified")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination")
    args = parser.parse_args()
    backup(os.environ.get("JWS_DATA_DIR", ".runtime"), args.destination)
    print("backup_verified")


if __name__ == "__main__":
    main()
