from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def _workspace_identifier(ws_id: str, path: Path) -> dict:
    path_str = str(path)
    return {
        "id": ws_id,
        "uri": {
            "$mid": 1,
            "fsPath": path_str,
            "external": f"file://{path_str}",
            "path": path_str,
            "scheme": "file",
        },
    }


def _read_db_json(db_path: Path, table: str, key: str) -> dict:
    with sqlite3.connect(db_path) as con:
        row = con.execute(f"SELECT value FROM {table} WHERE key=?", (key,)).fetchone()
    assert row is not None
    return json.loads(row[0])


def test_dry_run_reports_matches_without_writing(
    isolated_cursor_env, migrate_module, capsys
):
    env = isolated_cursor_env()

    result = migrate_module.main(
        ["--dry-run", str(env.src_workspace), str(env.dst_workspace)]
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "found 2 chat(s) to migrate" in output
    assert "[dry-run] no changes written." in output
    assert "transcripts that would be copied" in output
    assert "would copy" in output

    headers = _read_db_json(env.db_path, "ItemTable", "composer.composerHeaders")
    assert headers["allComposers"][0]["workspaceIdentifier"]["id"] == "src-id"
    assert headers["allComposers"][1]["workspaceIdentifier"]["id"] == "other-id"
    assert headers["allComposers"][2]["workspaceIdentifier"]["id"] == "stale-id"
    assert not list(env.db_path.parent.glob("state.vscdb.bak-*"))
    assert not (env.dst_transcripts_dir / "chat-one").exists()


def test_main_updates_matching_chat_records_and_copies_transcripts(
    isolated_cursor_env, migrate_module, capsys
):
    env = isolated_cursor_env()

    result = migrate_module.main([str(env.src_workspace), str(env.dst_workspace)])

    assert result == 0
    output = capsys.readouterr().out
    assert "updated headers entries: 2, composerData entries: 2" in output
    assert "copied" in output
    assert list(env.db_path.parent.glob("state.vscdb.bak-*"))

    headers = _read_db_json(env.db_path, "ItemTable", "composer.composerHeaders")
    by_id = {entry["composerId"]: entry for entry in headers["allComposers"]}
    assert by_id["chat-one"]["workspaceIdentifier"] == _workspace_identifier(
        "dst-id", env.dst_workspace
    )
    assert by_id["chat-path-match"]["workspaceIdentifier"] == _workspace_identifier(
        "dst-id", env.dst_workspace
    )
    assert by_id["chat-other"]["workspaceIdentifier"]["id"] == "other-id"

    chat_one = _read_db_json(env.db_path, "cursorDiskKV", "composerData:chat-one")
    chat_path_match = _read_db_json(
        env.db_path, "cursorDiskKV", "composerData:chat-path-match"
    )
    chat_other = _read_db_json(env.db_path, "cursorDiskKV", "composerData:chat-other")
    assert chat_one["workspaceIdentifier"] == _workspace_identifier(
        "dst-id", env.dst_workspace
    )
    assert chat_path_match["workspaceIdentifier"] == _workspace_identifier(
        "dst-id", env.dst_workspace
    )
    assert chat_other["workspaceIdentifier"]["id"] == "other-id"

    copied_transcript = (
        env.dst_transcripts_dir / "chat-one" / "chat-one.jsonl"
    ).read_text()
    assert copied_transcript == '{"message": "hello"}\n'


def test_no_transcripts_skips_copying(isolated_cursor_env, migrate_module, capsys):
    env = isolated_cursor_env()

    result = migrate_module.main(
        ["--no-transcripts", str(env.src_workspace), str(env.dst_workspace)]
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "copying transcripts" not in output
    assert not env.dst_transcripts_dir.exists()


def test_real_run_aborts_when_cursor_lock_files_exist(
    isolated_cursor_env, migrate_module, capsys
):
    env = isolated_cursor_env()
    env.db_path.with_suffix(env.db_path.suffix + "-wal").write_text("")

    result = migrate_module.main([str(env.src_workspace), str(env.dst_workspace)])

    assert result == 1
    captured = capsys.readouterr()
    assert "Cursor appears to be running" in captured.err

    headers = _read_db_json(env.db_path, "ItemTable", "composer.composerHeaders")
    assert headers["allComposers"][0]["workspaceIdentifier"]["id"] == "src-id"


def test_missing_destination_workspace_entry_returns_error(
    isolated_cursor_env, migrate_module, capsys
):
    env = isolated_cursor_env(include_dst_workspace=False)

    result = migrate_module.main(
        ["--dry-run", str(env.src_workspace), str(env.dst_workspace)]
    )

    assert result == 1
    assert "no workspaceStorage entry for dest path" in capsys.readouterr().err


def test_missing_headers_returns_error(isolated_cursor_env, migrate_module, capsys):
    env = isolated_cursor_env(include_headers=False)

    result = migrate_module.main(
        ["--dry-run", str(env.src_workspace), str(env.dst_workspace)]
    )

    assert result == 1
    assert "composer.composerHeaders not found" in capsys.readouterr().err
