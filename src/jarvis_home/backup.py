"""Private, consistent backup including the key; never overwrites a target."""
import argparse
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
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination")
    args = parser.parse_args()
    backup(os.environ.get("JWS_DATA_DIR", ".runtime"), args.destination)
    print("backup_verified")


if __name__ == "__main__":
    main()
