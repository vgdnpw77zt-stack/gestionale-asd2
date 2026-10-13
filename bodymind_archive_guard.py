"""BodyMind archival safety toolkit. Never auto-runs on the production site.

Audit is read-only; export captures a consistent SQLite snapshot plus persistent
document roots. Verify checks hashes and SQLite. Restore works only on an EMPTY
OFFLINE target: it never replaces the running database or deletes user files.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

DB = "tenants/default/asd.db"
ROOTS = ("tenants", "onboarding_docs", "signatures", "user_static",
         "incoming", "uploads", "documents", "documenti", "attachments",
         "verbali", "media", "top2_app/user_static", "top2_app/static")
FORMAT = "bodymind-volume-archive-v1"


def _sha(file):
    h = hashlib.sha256()
    with open(file, "rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def _path(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or "\\" in name or ".." in p.parts or "." in p.parts:
        raise ValueError("Unsafe file path in archive")
    return name


def _sqlite(path):
    c = sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro",
                        uri=True, timeout=40)
    try:
        c.execute("PRAGMA query_only=ON")
        if str(c.execute("PRAGMA integrity_check").fetchone()[0]).lower() != "ok":
            raise ValueError("SQLite integrity failure")
        if c.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("SQLite foreign keys broken")
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        totals = {}
        for t in ("tesserati", "pagamenti", "ricevute", "documenti",
                  "inbound_documents", "verbali"):
            if t in tables:
                totals[t] = c.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
        return totals
    finally:
        c.close()


def _files(root):
    """Never follow symlinks outside the volume or copy live WAL/SHM files."""
    seen = set()
    for prefix in ROOTS:
        base = root / prefix
        if not base.exists():
            continue
        if base.is_symlink():
            raise ValueError("Symlinked root blocked")
        for path, dirs, names in os.walk(base, followlinks=False):
            if any((Path(path) / d).is_symlink() for d in dirs):
                raise ValueError("Symlinked directory blocked")
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in sorted(names):
                file = Path(path) / name
                if file.is_symlink():
                    raise ValueError("Symlinked user file blocked")
                if not file.is_file() or name.endswith(("-wal", "-shm")):
                    continue
                rel = _path(file.relative_to(root).as_posix())
                if rel == DB or rel in seen:
                    continue
                seen.add(rel)
                yield rel, file


def _missing_docs(root):
    """Report IDs, never private filenames or personal information."""
    c = sqlite3.connect("file:" + str((root / DB).resolve()) + "?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone():
            return {"visible": [], "archived": [], "checked": 0}
        cols = {x[1] for x in c.execute("PRAGMA table_info(documenti)")}
        field = next((x for x in ("filename", "file_path", "percorso_file", "path", "allegato_path")
                      if x in cols), None)
        if field is None:
            return {"visible": [], "archived": [], "checked": 0, "warning": "Path field unknown"}
        fields = "id," + field + (",visibile" if "visibile" in cols else "")
        rows = c.execute("SELECT " + fields + " FROM documenti").fetchall()
        bases = (root / "tenants/default/media", root / "top2_app/user_static",
                 root / "top2_app/static", root / "top2_app",
                 root / "tenants/default", root)
        bad_visible, bad_archived = [], []
        for r in rows:
            raw = str(r[field] or "").strip()
            if not raw or raw.startswith(("https://", "http://")):
                continue
            p = Path(raw)
            alternatives = [p] if p.is_absolute() else [b / p for b in bases]
            found = False
            for candidate in alternatives:
                try:
                    absolute = candidate.resolve(strict=True)
                    if absolute.is_file() and root.resolve() in absolute.parents:
                        found = True
                        break
                except (OSError, RuntimeError):
                    pass
            if not found:
                archive = ("visibile" in cols and r["visibile"] == 0)
                (bad_archived if archive else bad_visible).append(int(r["id"]))
        return {"visible": bad_visible, "archived": bad_archived, "checked": len(rows)}
    finally:
        c.close()


def audit(root):
    root = Path(root).resolve()
    if not (root / DB).is_file():
        raise FileNotFoundError("Persistent database missing; no new database will be created")
    totals = _sqlite(root / DB)
    docs = _missing_docs(root)
    files = list(_files(root))
    return {"integrity": "ok", "foreign_keys": 0, "tables": totals,
            "document_references_missing": docs, "files": len(files),
            "bytes": sum(p.stat().st_size for _, p in files),
            "roots": [x for x in ROOTS if (root / x).exists()]}


def create(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination == root or root in destination.parents:
        raise ValueError("Destination MUST be outside the production volume")
    status = audit(root)
    if status["document_references_missing"]["visible"]:
        raise ValueError("Missing visible document references: cannot certify backup")
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = list(_files(root))
    required = status["bytes"] + (root / DB).stat().st_size + 128 * 1024 * 1024
    if shutil.disk_usage(destination.parent).free < required:
        raise OSError("Insufficient external space for reliable backup")
    with tempfile.TemporaryDirectory(prefix="bodymind_sqlite_") as td:
        snapshot = Path(td) / "asd.db"
        a = sqlite3.connect("file:" + str((root / DB).resolve()) + "?mode=ro", uri=True)
        b = sqlite3.connect(snapshot)
        try:
            a.backup(b)
        finally:
            b.close()
            a.close()
        snapshot_counts = _sqlite(snapshot)
        manifest = {"format": FORMAT,
                    "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "database_counts": snapshot_counts, "audit": status, "files": []}
        part = Path(str(destination) + ".partial")
        if part.exists() or destination.exists():
            raise FileExistsError("Never overwrite an existing backup")
        try:
            with zipfile.ZipFile(part, mode="w", allowZip64=True) as zipout:
                for name, file in [("database/asd.db", snapshot)] + [
                        ("data/" + rel, file) for rel, file in files]:
                    before = file.stat()
                    with zipout.open(name, mode="w", force_zip64=True) as out, file.open("rb") as inp:
                        digest = hashlib.sha256()
                        for partdata in iter(lambda: inp.read(1024 * 1024), b""):
                            out.write(partdata)
                            digest.update(partdata)
                    after = file.stat()
                    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                        raise RuntimeError("File changed during backup; abort rather than ship stale copy")
                    manifest["files"].append(
                        {"name": name, "sha256": digest.hexdigest(), "size": before.st_size})
                zipout.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
            verify(part)
            os.replace(part, destination)
        except Exception:
            part.unlink(missing_ok=True)
            raise
    return {"verified": True, "file_count": len(manifest["files"]),
            "database": snapshot_counts, "archive": str(destination)}


def verify(path):
    with zipfile.ZipFile(path, "r") as package:
        names = package.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("Missing manifest or duplicated archive members")
        for item in package.infolist():
            _path(item.filename)
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Symlink archive member prohibited")
        m = json.loads(package.read("manifest.json"))
        if m.get("format") != FORMAT:
            raise ValueError("Unknown backup format")
        members = {x["name"] for x in m["files"]}
        if set(names) != members | {"manifest.json"} or "database/asd.db" not in members:
            raise ValueError("Incomplete manifest")
        for entry in m["files"]:
            _path(entry["name"])
            h = hashlib.sha256()
            size = 0
            with package.open(entry["name"]) as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(block)
                    size += len(block)
            if h.hexdigest() != entry["sha256"] or size != entry["size"]:
                raise ValueError("Checksum mismatch; backup damaged")
        with tempfile.TemporaryDirectory(prefix="bodymind_verify_") as td:
            tmpdb = Path(td) / "db.sqlite"
            with package.open("database/asd.db") as inp, tmpdb.open("wb") as out:
                shutil.copyfileobj(inp, out)
            verified_totals = _sqlite(tmpdb)
        if verified_totals != m["database_counts"]:
            raise ValueError("SQLite data totals differ from manifest")
        return {"verified": True, "file_count": len(members),
                "database": verified_totals, "audit": m["audit"]}


def restore_into_empty(archive, target):
    """Recovery to a NEW offline volume only. NEVER clobber production."""
    target = Path(target).resolve()
    if target.exists() and any(target.iterdir()):
        raise FileExistsError("Restore destination must be EMPTY")
    report = verify(archive)
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if name == "manifest.json":
                continue
            rel = DB if name == "database/asd.db" else name[5:]
            if name != "database/asd.db" and not name.startswith("data/"):
                raise ValueError("Invalid restoration path")
            rel = _path(rel)
            out = (target / rel).resolve()
            if target not in out.parents:
                raise ValueError("Restore path escape blocked")
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(name) as src, out.open("xb") as dst:
                shutil.copyfileobj(src, dst)
    _sqlite(target / DB)
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    commands = cli.add_subparsers(dest="command", required=True)
    for name in ("audit", "create"):
        p = commands.add_parser(name)
        p.add_argument("--root", type=Path, default=Path("/data"))
        if name == "create":
            p.add_argument("--output", type=Path, required=True,
                           help="Backup outside /data, e.g. mounted external storage")
    p = commands.add_parser("verify")
    p.add_argument("archive", type=Path)
    p = commands.add_parser("restore-empty")
    p.add_argument("archive", type=Path)
    p.add_argument("--target", type=Path, required=True)
    p.add_argument("--confirm", required=True)
    args = cli.parse_args()
    if args.command == "audit":
        result = audit(args.root)
    elif args.command == "create":
        result = create(args.root, args.output)
    elif args.command == "verify":
        result = verify(args.archive)
    else:
        if args.confirm != "RIPRISTINO OFFLINE SU VOLUME VUOTO":
            raise ValueError("Confirm explicit offline restoration")
        result = restore_into_empty(args.archive, args.target)
    print(json.dumps(result, ensure_ascii=False, indent=2))
