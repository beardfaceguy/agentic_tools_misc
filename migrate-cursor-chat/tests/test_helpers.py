from pathlib import Path
from urllib.parse import quote


def test_default_cursor_user_dir_uses_linux_config_path(migrate_module):
    home = Path("/home/alice")

    assert migrate_module.default_cursor_user_dir(home, "linux") == (
        home / ".config/Cursor/User"
    )


def test_default_cursor_user_dir_uses_macos_application_support_path(migrate_module):
    home = Path("/Users/alice")

    assert migrate_module.default_cursor_user_dir(home, "darwin") == (
        home / "Library/Application Support/Cursor/User"
    )


def test_default_projects_dir_is_shared_across_supported_platforms(migrate_module):
    home = Path("/Users/alice")

    assert migrate_module.default_projects_dir(home) == home / ".cursor/projects"


def test_encode_project_dir_strips_leading_slash_and_replaces_separators(migrate_module):
    assert migrate_module.encode_project_dir(Path("/home/alice/work/foo")) == "home-alice-work-foo"


def test_make_workspace_identifier_uses_destination_path(migrate_module):
    identifier = migrate_module.make_workspace_identifier("workspace-123", Path("/tmp/new/path"))

    assert identifier == {
        "id": "workspace-123",
        "uri": {
            "$mid": 1,
            "fsPath": "/tmp/new/path",
            "external": "file:///tmp/new/path",
            "path": "/tmp/new/path",
            "scheme": "file",
        },
    }


def test_find_matching_chats_matches_by_workspace_id_or_path(migrate_module, workspace_paths):
    headers = {
        "allComposers": [
            {
                "composerId": "by-id",
                "workspaceIdentifier": {
                    "id": "source-id",
                    "uri": {"fsPath": "/other/path", "path": "/other/path"},
                },
            },
            {
                "composerId": "by-fs-path",
                "workspaceIdentifier": {
                    "id": "stale-id",
                    "uri": {"fsPath": str(workspace_paths["src"])},
                },
            },
            {
                "composerId": "by-uri-path",
                "workspaceIdentifier": {
                    "id": "another-stale-id",
                    "uri": {"path": str(workspace_paths["src"])},
                },
            },
            {
                "composerId": "other-workspace",
                "workspaceIdentifier": {
                    "id": "dest-id",
                    "uri": {"fsPath": str(workspace_paths["dst"])},
                },
            },
        ]
    }

    matches = migrate_module.find_matching_chats(headers, "source-id", workspace_paths["src"])

    assert [entry["composerId"] for entry in matches] == [
        "by-id",
        "by-fs-path",
        "by-uri-path",
    ]


def test_find_workspace_id_reads_workspace_storage(migrate_module, cursor_env, workspace_paths):
    cursor_env.add_workspace("source-id", workspace_paths["src"])
    cursor_env.add_workspace("dest-id", workspace_paths["dst"])

    assert migrate_module.find_workspace_id(workspace_paths["src"]) == "source-id"
    assert migrate_module.find_workspace_id(workspace_paths["dst"]) == "dest-id"
    assert migrate_module.find_workspace_id(workspace_paths["root"] / "missing") is None


def test_find_workspace_id_decodes_file_uri_paths(
    migrate_module, cursor_env, workspace_paths
):
    spaced_path = workspace_paths["root"] / "source with spaces"
    spaced_path.mkdir()
    workspace_dir = cursor_env.workspace_storage / "spaces-id"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "workspace.json").write_text(
        f'{{"folder": "file://{quote(str(spaced_path))}"}}',
        encoding="utf-8",
    )

    assert migrate_module.find_workspace_id(spaced_path) == "spaces-id"

