# Customizing the behavior template

## Editing the rules

The template ships with a starter set of behavioral rules. They're opinions,
not gospel. Edit `~/.config/ai-rules/global-behavior.md` to match how you
want your agent to behave.

Common additions people make:

- **Response language or tone** — "Be terse. Skip pleasantries."
- **Commit message style** — "Use conventional commits. Always include a body."
- **Framework preferences** — these may fit better in repo-level `AGENTS.md`
- **Personal shortcuts** — "When I say 'ship it', run tests then commit."

## Adding a new IDE

1. Open `~/.config/ai-rules/sync-rules.sh`
2. Add a new section following the existing pattern (Claude Code, Zed, Cursor
   are already there as examples)
3. The section should:
   - Check if the IDE's config file/directory exists
   - Skip with a `warn` if not found
   - Apply the rules content to wherever the IDE reads them from
4. No changes needed to the systemd units or the canonical file

Example skeleton for a new IDE:

```bash
# --- NewIDE: description of how it stores rules ---
echo "=== NewIDE ==="
NEWIDE_CONFIG="$HOME/.config/newide/settings.json"
if [[ -f "$NEWIDE_CONFIG" ]]; then
    # ... apply rules ...
    ok "NewIDE updated"
else
    warn "NewIDE config not found at $NEWIDE_CONFIG — skipping"
fi
echo ""
```

## Removing an IDE

Either delete the IDE's section from `sync-rules.sh`, or just leave it. The
script checks for config file existence before acting and skips missing IDEs
with a warning. No errors, no side effects.

## Changing the canonical file location

If you want the rules file somewhere other than `~/.config/ai-rules/`:

1. Move the file
2. Update `CANONICAL=` in `sync-rules.sh`
3. Update `PathModified=` in `~/.config/systemd/user/ai-rules-sync.path`
4. Update the Claude Code symlink:
   ```bash
   ln -sf /new/path/global-behavior.md ~/.claude/CLAUDE.md
   ```
5. Reload systemd:
   ```bash
   systemctl --user daemon-reload
   systemctl --user restart ai-rules-sync.path
   ```

## macOS adaptation

The sync script works on macOS as-is. Only the auto-trigger needs replacing.

**Option A: launchd plist** (recommended)

Create `~/Library/LaunchAgents/com.ai-rules.sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ai-rules.sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOU/.config/ai-rules/sync-rules.sh</string>
  </array>
  <key>WatchPaths</key>
  <array>
    <string>/Users/YOU/.config/ai-rules/global-behavior.md</string>
  </array>
</dict>
</plist>
```

Then: `launchctl load ~/Library/LaunchAgents/com.ai-rules.sync.plist`

**Option B: fswatch loop**

```bash
brew install fswatch
fswatch -o ~/.config/ai-rules/global-behavior.md | xargs -n1 ~/.config/ai-rules/sync-rules.sh
```

Run this in a tmux session or wrap it in a launchd plist for persistence.

On macOS, Claude Code paths are the same (`~/.claude/CLAUDE.md`). Zed settings
live at `~/Library/Application Support/Zed/settings.json` — update
`ZED_SETTINGS` in the sync script. Cursor settings are at
`~/Library/Application Support/Cursor/User/settings.json`.
