# behavior-template

A single-file-to-rule-them-all setup for AI agent behavioral rules across
multiple IDEs. Write your rules once, edit in one place, and they automatically
propagate to Claude Code, Zed, and Cursor IDE.

## The problem

Each AI coding tool stores global user rules in a different location:

| Tool | Global rules location | Format |
|------|----------------------|--------|
| Claude Code | `~/.claude/CLAUDE.md` | Markdown file |
| Zed | `assistant_instructions` in `~/.config/zed/settings.json` | JSON string value |
| Cursor IDE | Internal settings database | Paste via Settings UI |

If you use more than one tool, you end up with duplicate rules that drift apart
over time. There's no shared standard for global (user-wide) rules.

## The solution

```
~/.config/ai-rules/global-behavior.md    ← you edit this one file
        │
        ├─→ ~/.claude/CLAUDE.md              (symlink, instant)
        ├─→ ~/.config/zed/settings.json      (assistant_instructions, auto-updated)
        └─→ clipboard                        (paste into Cursor Settings > Rules)
```

A systemd path unit watches the canonical file via inotify. Any write triggers
a sync script that pushes the content to each IDE target. Zero CPU when idle,
survives reboots, starts on login.

## What's in this directory

```
behavior-template/
├── README.md                          # this file
├── install.sh                         # one-command setup
├── global-behavior.md                 # the behavioral rules template
├── sync-rules.sh                      # propagation script
├── systemd/
│   ├── ai-rules-sync.path            # file watcher unit
│   └── ai-rules-sync.service         # sync trigger unit
└── CUSTOMIZING.md                     # how to modify rules and add IDEs
```

## Requirements

- **Linux** with systemd user services (Ubuntu 22.04+, Fedora, Arch, etc.)
- **Python 3** (stdlib only — used for Zed's JSONC settings update)
- **One of**: `xclip`, `xsel`, or `wl-copy` (for Cursor clipboard copy;
  optional — falls back to printing the content if none found)
- At least one of: Claude Code, Zed, Cursor IDE

macOS users: systemd doesn't exist on macOS. You'd need to replace the systemd
units with a `launchd` plist or an `fswatch` loop. The `sync-rules.sh` script
itself works on macOS — only the auto-trigger mechanism differs.

## Quick start

```bash
cd behavior-template/
chmod +x install.sh
./install.sh
```

The installer will:

1. Copy `global-behavior.md` and `sync-rules.sh` to `~/.config/ai-rules/`
2. Install the systemd path and service units to `~/.config/systemd/user/`
3. Create the `~/.claude/CLAUDE.md` symlink (Claude Code)
4. Inject `assistant_instructions` into Zed's settings (if Zed is installed)
5. Copy rules to clipboard for Cursor IDE (manual paste required)
6. Enable and start the file watcher

After install, the **one manual step** is pasting into Cursor:

1. Open Cursor Settings (`Ctrl+Shift+J` on Linux)
2. Click **Rules** in the sidebar
3. Paste (the installer already copied the content to your clipboard)

## Day-to-day usage

**Edit your rules:**

```bash
$EDITOR ~/.config/ai-rules/global-behavior.md
```

Save, and the systemd watcher automatically syncs to Claude Code and Zed.
For Cursor, re-run `~/.config/ai-rules/sync-rules.sh` which copies to
clipboard, then paste.

**Check watcher status:**

```bash
systemctl --user status ai-rules-sync.path
```

**View sync history:**

```bash
journalctl --user -u ai-rules-sync.service --since "1 hour ago"
```

**Manual sync (bypass the watcher):**

```bash
~/.config/ai-rules/sync-rules.sh
```

## Uninstall

```bash
systemctl --user disable --now ai-rules-sync.path
rm ~/.config/systemd/user/ai-rules-sync.{path,service}
rm -rf ~/.config/ai-rules/
rm ~/.claude/CLAUDE.md  # only if it's a symlink to the canonical file
systemctl --user daemon-reload
```

For Zed, the `assistant_instructions` key will remain in settings.json.
Remove it manually if desired. For Cursor, clear the User Rules in
Settings > Rules.

## Scope: global vs repo

This tool handles **global** behavioral rules — the agent's personality,
working style, and meta-habits that apply to every project.

**Project-specific** rules (framework conventions, directory layout, testing
patterns, MCP server config) belong in a repo-level `AGENTS.md` file committed
with the project. Both layers stack: the agent reads global rules first, then
repo rules on top.

## How each IDE picks up rules

| IDE | Global mechanism | Repo mechanism |
|-----|-----------------|----------------|
| Claude Code | `~/.claude/CLAUDE.md` (always loaded) | `./CLAUDE.md` or `./AGENTS.md` in project root |
| Zed | `assistant_instructions` in settings | `./AGENTS.md` in project root |
| Cursor IDE | User Rules in Settings > Rules | `.cursor/rules/*.mdc` or `./AGENTS.md` in project root |
