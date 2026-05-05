from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "migrate-cursor-chat.py"


@pytest.fixture
def migrate_module():
    spec = importlib.util.spec_from_file_location("migrate_cursor_chat", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def workspace_paths(tmp_path):
    root = tmp_path / "workspaces"
    src = root / "source"
    dst = root / "dest"
    other = root / "other"
    for path in (src, dst, other):
        path.mkdir(parents=True)
    return {"root": root, "src": src, "dst": dst, "other": other}


@pytest.fixture
def cursor_env(tmp_path, migrate_module, monkeypatch):
    user_dir = tmp_path / "home/.config/Cursor/User"
    workspace_storage = user_dir / "workspaceStorage"
    global_storage = user_dir / "globalStorage"
    projects_dir = tmp_path / "home/.cursor/projects"

    workspace_storage.mkdir(parents=True)
    global_storage.mkdir(parents=True)
    projects_dir.mkdir(parents=True)

    db_path = global_storage / "state.vscdb"
    create_cursor_db(db_path)

    monkeypatch.setattr(migrate_module, "CURSOR_USER_DIR", user_dir)
    monkeypatch.setattr(migrate_module, "WORKSPACE_STORAGE_DIR", workspace_storage)
    monkeypatch.setattr(migrate_module, "GLOBAL_DB", db_path)
    monkeypatch.setattr(migrate_module, "PROJECTS_DIR", projects_dir)

    env = CursorTestEnv(
        module=migrate_module,
        user_dir=user_dir,
        workspace_storage=workspace_storage,
        db_path=db_path,
        projects_dir=projects_dir,
    )
    return env


@pytest.fixture
def isolated_cursor_env(cursor_env, workspace_paths):
    def build(
        *,
        include_dst_workspace: bool = True,
        include_headers: bool = True,
    ):
        src = workspace_paths["src"]
        dst = workspace_paths["dst"]
        other = workspace_paths["other"]

        cursor_env.add_workspace("src-id", src)
        if include_dst_workspace:
            cursor_env.add_workspace("dst-id", dst)
        cursor_env.add_workspace("other-id", other)

        if include_headers:
            cursor_env.seed_headers(
                {
                    "allComposers": [
                        composer_entry("chat-one", "src-id", src, "Chat by id"),
                        composer_entry("chat-other", "other-id", other, "Other chat"),
                        composer_entry(
                            "chat-path-match",
                            "stale-id",
                            src,
                            "Chat by path",
                        ),
                    ]
                }
            )

        cursor_env.seed_composer_data(
            "chat-one",
            {
                "composerId": "chat-one",
                "workspaceIdentifier": workspace_identifier("src-id", src),
            },
        )
        cursor_env.seed_composer_data(
            "chat-path-match",
            {
                "composerId": "chat-path-match",
                "workspaceIdentifier": workspace_identifier("stale-id", src),
            },
        )
        cursor_env.seed_composer_data(
            "chat-other",
            {
                "composerId": "chat-other",
                "workspaceIdentifier": workspace_identifier("other-id", other),
            },
        )
        cursor_env.add_transcript(src, "chat-one", '{"message": "hello"}\n')

        return SimpleNamespace(
            src_workspace=src,
            dst_workspace=dst,
            other_workspace=other,
            db_path=cursor_env.db_path,
            dst_transcripts_dir=(
                cursor_env.projects_dir
                / cursor_env.module.encode_project_dir(dst)
                / "agent-transcripts"
            ),
        )

    return build


class CursorTestEnv:
    def __init__(
        self,
        module,
        user_dir: Path,
        workspace_storage: Path,
        db_path: Path,
        projects_dir: Path,
    ) -> None:
        self.module = module
        self.user_dir = user_dir
        self.workspace_storage = workspace_storage
        self.db_path = db_path
        self.projects_dir = projects_dir

    def add_workspace(self, workspace_id: str, folder_path: Path) -> None:
        workspace_dir = self.workspace_storage / workspace_id
        workspace_dir.mkdir(parents=True)
        (workspace_dir / "workspace.json").write_text(
            json.dumps({"folder": f"file://{folder_path}"}),
            encoding="utf-8",
        )

    def seed_headers(self, headers: dict) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT OR REPLACE INTO ItemTable(key, value) VALUES (?, ?)",
                ("composer.composerHeaders", json.dumps(headers)),
            )

    def seed_composer_data(self, composer_id: str, data: dict) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT OR REPLACE INTO cursorDiskKV(key, value) VALUES (?, ?)",
                (f"composerData:{composer_id}", json.dumps(data)),
            )

    def read_headers(self) -> dict:
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT value FROM ItemTable WHERE key='composer.composerHeaders'"
            ).fetchone()
        assert row is not None
        return json.loads(row[0])

    def read_composer_data(self, composer_id: str) -> dict:
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT value FROM cursorDiskKV WHERE key=?",
                (f"composerData:{composer_id}",),
            ).fetchone()
        assert row is not None
        return json.loads(row[0])

    def add_transcript(self, workspace_path: Path, composer_id: str, text: str) -> Path:
        transcript_dir = (
            self.projects_dir
            / self.module.encode_project_dir(workspace_path)
            / "agent-transcripts"
            / composer_id
        )
        transcript_dir.mkdir(parents=True)
        transcript_file = transcript_dir / f"{composer_id}.jsonl"
        transcript_file.write_text(text, encoding="utf-8")
        return transcript_file

    def transcript_file(self, workspace_path: Path, composer_id: str) -> Path:
        return (
            self.projects_dir
            / self.module.encode_project_dir(workspace_path)
            / "agent-transcripts"
            / composer_id
            / f"{composer_id}.jsonl"
        )


def create_cursor_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute("CREATE TABLE ItemTable(key TEXT PRIMARY KEY, value TEXT)")
        con.execute("CREATE TABLE cursorDiskKV(key TEXT PRIMARY KEY, value TEXT)")


def composer_entry(
    composer_id: str,
    workspace_id: str,
    workspace_path: Path,
    name: str = "Test chat",
) -> dict:
    return {
        "composerId": composer_id,
        "name": name,
        "workspaceIdentifier": workspace_identifier(workspace_id, workspace_path),
    }


def workspace_identifier(workspace_id: str, workspace_path: Path) -> dict:
    path = str(workspace_path)
    return {
        "id": workspace_id,
        "uri": {
            "$mid": 1,
            "fsPath": path,
            "external": f"file://{path}",
            "path": path,
            "scheme": "file",
        },
    }
