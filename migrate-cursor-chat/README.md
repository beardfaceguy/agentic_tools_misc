# migrate-cursor-chat

Move Cursor chat history from one workspace folder to another after you've
moved the folder on disk.

## The problem

Cursor binds each chat (composer) to a specific workspace path. The binding
lives in Cursor's global SQLite database at `globalStorage/state.vscdb` under
the platform-specific user data directory, embedded inside each chat's record.
If you move the workspace folder (e.g. `~/work/foo` → `~/work/team/foo`),
Cursor opens the new path as a brand-new workspace and your previous chats
vanish from the sidebar — they're not deleted, just orphaned to the old path.

This script rewrites those embedded workspace identifiers so the chats
re-appear in the new workspace's history.

## What it does

For every chat associated with the source workspace, the script:

1. Updates the `workspaceIdentifier` field in `composer.composerHeaders`
   (the master sidebar list) inside `state.vscdb`.
2. Updates the `workspaceIdentifier` field in `composerData:<chat-id>`
   (the per-chat record) inside the same DB.
3. Copies the per-chat transcript folder from
   `~/.cursor/projects/<src-encoded>/agent-transcripts/<chat-id>/` to
   `~/.cursor/projects/<dst-encoded>/agent-transcripts/<chat-id>/` so past
   chats remain citeable by uuid in new sessions. (Skip with
   `--no-transcripts`.)

Before any write it makes a timestamped backup of `state.vscdb` at
`state.vscdb.bak-<unix-ts>`.

## Requirements

- Python 3.9+ (uses only the standard library).
- Linux or macOS. The script automatically uses Cursor's platform-specific
  data root:
  - Linux: `~/.config/Cursor/User/`
  - macOS: `~/Library/Application Support/Cursor/User/`
  Per-workspace agent data is read from `~/.cursor/projects/` on both.
  Windows is not currently supported.
- Both the **source** and the **destination** workspace must have been
  opened in Cursor at least once (so each appears under Cursor's
  `workspaceStorage/<id>/workspace.json`).
- **Cursor must be fully quit** before running. The script aborts if it
  detects a `state.vscdb-wal` or `state.vscdb-shm` lock file.

## Testing

Install the development test dependency and run pytest from this directory:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```

The tests build an isolated Cursor data layout under pytest's temporary
directory, including workspaceStorage entries, a synthetic `state.vscdb`, and
agent transcript folders. They never read or write your real Cursor data.

## Usage

```bash
python3 migrate-cursor-chat.py [--dry-run] [--no-transcripts] \
    <source-workspace-path> <dest-workspace-path>
```

### Recommended workflow

1. Move the workspace folder on disk:

   ```bash
   mv ~/work/foo ~/work/team/foo
   ```

2. Open the new path in Cursor once (just so Cursor registers it under
   `workspaceStorage/`), then quit Cursor completely.

3. Dry-run first to see what would be migrated:

   ```bash
   python3 migrate-cursor-chat.py --dry-run \
       ~/work/foo ~/work/team/foo
   ```

   Output looks like:

   ```text
   source: /home/you/work/foo  (id=57802428a31abf2687e60a1f8911fc93)
   dest:   /home/you/work/team/foo  (id=91298217030efd0a8e4378a8c77a3433)

   found 3 chat(s) to migrate:
     - f3352f24-…  (Jira ticket FOO-123)
     - 9c8a01b2-…  (Refactor auth service)
     - d888d778-…  ((no name))

   [dry-run] no changes written.
   ```

4. Apply for real:

   ```bash
   python3 migrate-cursor-chat.py \
       ~/work/foo ~/work/team/foo
   ```

5. Reopen Cursor at the new path. The chats now appear in the sidebar.

### Options

| Flag | Effect |
|------|--------|
| `--dry-run` | Print what would change without touching the DB. Safe to run while Cursor is open. |
| `--no-transcripts` | Skip copying the per-chat folders under `~/.cursor/projects/.../agent-transcripts/`. Use if you only care about the sidebar entry and don't need past chats to remain citeable from new agent sessions. |

## How chat-to-workspace binding works in Cursor

Useful if you want to verify the script's behaviour or extend it.

### Workspace storage

Each workspace Cursor has ever opened gets a folder under
Cursor's platform-specific `workspaceStorage/<id>/`. The folder name is
an opaque hash; the actual path is recorded in `workspace.json`:

```json
{ "folder": "file:///home/you/work/foo" }
```

To find a workspace's id: scan those `workspace.json` files and match by
folder URI. That's exactly what the script does.

### Project-data layout

Cursor also keeps per-workspace agent data at
`~/.cursor/projects/<encoded-path>/`, where `<encoded-path>` is the
absolute workspace path with the leading `/` removed and remaining `/`
characters replaced by `-`:

```text
/home/you/work/foo  →  home-you-work-foo
```

This folder holds `agent-transcripts/<chat-id>/<chat-id>.jsonl` (the
machine-readable transcript that new agent sessions can cite), `mcps/`,
`terminals/`, and `canvases/`. Note: this folder is **not** the source of
truth for the sidebar — moving these files alone won't restore chat
history.

### The actual binding

The chat→workspace association is stored in the global database
`globalStorage/state.vscdb` under Cursor's platform-specific user data
directory in two places:

- `ItemTable['composer.composerHeaders']` — JSON value containing
  `allComposers: [...]`. Each composer has a `workspaceIdentifier` field
  with `id` and `uri` keys. This is what populates the chat sidebar.
- `cursorDiskKV['composerData:<chat-id>']` — JSON value with the full chat
  record, including its own `workspaceIdentifier`.

Both must be updated to fully migrate a chat.

## Recovery

If something goes wrong, restore the backup the script created:

```bash
# Linux
cp ~/.config/Cursor/User/globalStorage/state.vscdb.bak-<ts> \
   ~/.config/Cursor/User/globalStorage/state.vscdb

# macOS
cp ~/Library/Application\ Support/Cursor/User/globalStorage/state.vscdb.bak-<ts> \
   ~/Library/Application\ Support/Cursor/User/globalStorage/state.vscdb
```

(With Cursor quit.)

## Caveats

- This file layout is **not officially documented**. It was reverse-
  engineered from a current Cursor install and may change in future
  versions. Always run `--dry-run` first and keep the backup until you've
  confirmed the chats appear correctly.
- Only chats associated with the source workspace are touched. Chats
  belonging to other workspaces are left alone.
- The script matches chats by both workspace `id` and `fsPath` (in case
  one drifted from the other), so it works even when the source
  workspaceStorage entry has already been recreated.
