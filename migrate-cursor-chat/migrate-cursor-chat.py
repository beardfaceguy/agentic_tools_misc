#!/usr/bin/env python3
"""
Re-associate Cursor chats (composers) with a different workspace path.

Use case: you moved a workspace folder on disk (e.g. ~/work/AE-2387 ->
~/work/alix/AE-2387) and your old chat history no longer appears in the
sidebar. This script finds every chat tied to the source workspace path
and rewrites its embedded `workspaceIdentifier` so Cursor shows it under
the destination workspace.

Both the source and the destination workspace must have been opened in
Cursor at least once (so each has an entry in
~/.config/Cursor/User/workspaceStorage/<id>/workspace.json).

PREREQUISITE: Cursor must be fully quit before running, otherwise SQLite
is locked and Cursor will overwrite the changes on shutdown.

Usage:
    python3 migrate-cursor-chat.py [--dry-run] [--no-transcripts] \\
        <source-workspace-path> <dest-workspace-path>

Example:
    python3 migrate-cursor-chat.py \\
        ~/work/AE-2387 ~/work/alix/AE-2387
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Iterable

CURSOR_USER_DIR = Path.home() / ".config/Cursor/User"
WORKSPACE_STORAGE_DIR = CURSOR_USER_DIR / "workspaceStorage"
GLOBAL_DB = CURSOR_USER_DIR / "globalStorage" / "state.vscdb"
PROJECTS_DIR = Path.home() / ".cursor/projects"


def encode_project_dir(abs_path: Path) -> str:
    """Encode an absolute filesystem path the way ~/.cursor/projects/ does:
    drop the leading slash, replace remaining slashes with dashes."""
    s = str(abs_path)
    if s.startswith("/"):
        s = s[1:]
    return s.replace("/", "-")


def find_workspace_id(folder_path: Path) -> str | None:
    """Scan workspaceStorage for the dir whose workspace.json points at
    `folder_path`. Returns the storage dir name (the workspace id), or None.
    """
    target = folder_path.resolve()
    if not WORKSPACE_STORAGE_DIR.is_dir():
        return None
    for entry in WORKSPACE_STORAGE_DIR.iterdir():
        wsfile = entry / "workspace.json"
        if not wsfile.is_file():
            continue
        try:
            data = json.loads(wsfile.read_text())
        except Exception:
            continue
        folder = data.get("folder")
        if not folder or not folder.startswith("file://"):
            continue
        if Path(folder[len("file://") :]).resolve() == target:
            return entry.name
    return None


def is_cursor_running(db: Path) -> bool:
    return (
        db.with_suffix(db.suffix + "-wal").exists()
        or db.with_suffix(db.suffix + "-shm").exists()
    )


def make_workspace_identifier(ws_id: str, folder_path: Path) -> dict:
    s = str(folder_path)
    return {
        "id": ws_id,
        "uri": {
            "$mid": 1,
            "fsPath": s,
            "external": f"file://{s}",
            "path": s,
            "scheme": "file",
        },
    }


def find_matching_chats(headers: dict, src_id: str, src_path: Path) -> list[dict]:
    """Return composer entries that belong to the source workspace, matching
    on either workspace id or fsPath (in case the id has changed but the path
    survived in the embedded identifier, or vice versa)."""
    src_str = str(src_path)
    out = []
    for entry in headers.get("allComposers", []):
        ws = entry.get("workspaceIdentifier") or {}
        if ws.get("id") == src_id:
            out.append(entry)
            continue
        uri = ws.get("uri") or {}
        if uri.get("fsPath") == src_str or uri.get("path") == src_str:
            out.append(entry)
    return out


def migrate_transcripts(
    src_path: Path, dst_path: Path, chat_ids: Iterable[str], dry_run: bool
) -> int:
    """Copy per-chat transcript folders from the source project dir to the
    destination project dir. Returns the number of chats copied."""
    src_dir = PROJECTS_DIR / encode_project_dir(src_path) / "agent-transcripts"
    dst_dir = PROJECTS_DIR / encode_project_dir(dst_path) / "agent-transcripts"
    if not src_dir.is_dir():
        print(f"  no source transcripts dir ({src_dir}); skipping")
        return 0
    copied = 0
    for cid in chat_ids:
        src_chat = src_dir / cid
        if not src_chat.is_dir():
            continue
        dst_chat = dst_dir / cid
        if dst_chat.exists():
            print(f"  transcript already present, skipping: {dst_chat}")
            continue
        if dry_run:
            print(f"  would copy {src_chat} -> {dst_chat}")
        else:
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src_chat, dst_chat)
            print(f"  copied {src_chat} -> {dst_chat}")
        copied += 1
    return copied


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Re-associate Cursor chats from one workspace path to another.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("source", type=Path, help="Source workspace folder path")
    p.add_argument("dest", type=Path, help="Destination workspace folder path")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing.",
    )
    p.add_argument(
        "--no-transcripts",
        action="store_true",
        help="Skip copying ~/.cursor/projects/<src>/agent-transcripts/<id>/ "
        "into the destination project folder.",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    src_path = args.source.expanduser().resolve()
    dst_path = args.dest.expanduser().resolve()

    if not GLOBAL_DB.exists():
        print(f"ERROR: not found: {GLOBAL_DB}", file=sys.stderr)
        return 1
    if is_cursor_running(GLOBAL_DB) and not args.dry_run:
        print(
            "ERROR: Cursor appears to be running (state.vscdb-wal or -shm exists).\n"
            "Quit Cursor completely, then re-run this script.",
            file=sys.stderr,
        )
        return 1

    src_id = find_workspace_id(src_path)
    dst_id = find_workspace_id(dst_path)
    if not src_id:
        print(
            f"ERROR: no workspaceStorage entry for source path: {src_path}\n"
            f"Cursor records workspaces only after they've been opened.",
            file=sys.stderr,
        )
        return 1
    if not dst_id:
        print(
            f"ERROR: no workspaceStorage entry for dest path: {dst_path}\n"
            f"Open the destination folder in Cursor once so it gets registered.",
            file=sys.stderr,
        )
        return 1

    print(f"source: {src_path}  (id={src_id})")
    print(f"dest:   {dst_path}  (id={dst_id})")

    con = sqlite3.connect(GLOBAL_DB)
    cur = con.cursor()

    headers_row = cur.execute(
        "SELECT value FROM ItemTable WHERE key='composer.composerHeaders'"
    ).fetchone()
    if not headers_row:
        print("ERROR: composer.composerHeaders not found", file=sys.stderr)
        return 1
    headers = json.loads(headers_row[0])

    matches = find_matching_chats(headers, src_id, src_path)
    if not matches:
        print("no chats to migrate.")
        return 0

    print(f"\nfound {len(matches)} chat(s) to migrate:")
    for m in matches:
        print(
            f"  - {m.get('composerId')}  "
            f"({m.get('name') or m.get('subtitle') or '(no name)'})"
        )

    new_ws = make_workspace_identifier(dst_id, dst_path)
    chat_ids = [m["composerId"] for m in matches if m.get("composerId")]

    if args.dry_run:
        print("\n[dry-run] no changes written.")
        if not args.no_transcripts:
            print("\ntranscripts that would be copied:")
            migrate_transcripts(src_path, dst_path, chat_ids, dry_run=True)
        return 0

    backup = GLOBAL_DB.with_suffix(f".vscdb.bak-{int(time.time())}")
    shutil.copy2(GLOBAL_DB, backup)
    print(f"\nbackup: {backup}")

    for entry in matches:
        entry["workspaceIdentifier"] = new_ws
    cur.execute(
        "UPDATE ItemTable SET value=? WHERE key='composer.composerHeaders'",
        (json.dumps(headers),),
    )

    data_updated = 0
    for cid in chat_ids:
        key = f"composerData:{cid}"
        row = cur.execute(
            "SELECT value FROM cursorDiskKV WHERE key=?", (key,)
        ).fetchone()
        if not row:
            print(f"WARN: {key} not found", file=sys.stderr)
            continue
        data = json.loads(row[0])
        data["workspaceIdentifier"] = new_ws
        cur.execute(
            "UPDATE cursorDiskKV SET value=? WHERE key=?",
            (json.dumps(data), key),
        )
        data_updated += 1

    con.commit()
    con.close()

    print(
        f"updated headers entries: {len(matches)}, "
        f"composerData entries: {data_updated}"
    )

    if not args.no_transcripts:
        print("\ncopying transcripts:")
        migrate_transcripts(src_path, dst_path, chat_ids, dry_run=False)

    print("\nDone. Reopen Cursor at the destination workspace.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
