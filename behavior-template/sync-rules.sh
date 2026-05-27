#!/usr/bin/env bash
# sync-rules.sh — propagate ~/.config/ai-rules/global-behavior.md to each IDE.
#
# Triggered automatically by the systemd path unit ai-rules-sync.path
# whenever the canonical file is modified. Can also be run manually.
#
# Sync targets (each section is independent — one failing won't block others):
#   Claude Code : symlinks ~/.claude/CLAUDE.md → canonical file
#   Zed         : writes assistant_instructions into ~/.config/zed/settings.json
#   Cursor IDE  : copies to clipboard for manual paste (Settings > Rules)
#
# Adding a new IDE:
#   Add a new section below following the same pattern. The script skips
#   targets whose config files don't exist, so removing an IDE is safe.
#
# Removing an IDE:
#   Delete the IDE's section, or just leave it — missing config files are
#   handled gracefully with a [warn] and the script continues.
#
# Dependencies:
#   - python3 (for Zed JSONC parsing; Zed section skipped if missing)
#   - xclip, xsel, or wl-copy (for Cursor clipboard; falls back to stdout)
set -uo pipefail

CANONICAL="$HOME/.config/ai-rules/global-behavior.md"
CLAUDE_TARGET="$HOME/.claude/CLAUDE.md"
ZED_SETTINGS="$HOME/.config/zed/settings.json"
CURSOR_SETTINGS="$HOME/.config/Cursor/User/settings.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[ok]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
fail() { echo -e "${RED}[fail]${NC} $1"; }

if [[ ! -f "$CANONICAL" ]]; then
    fail "Canonical file not found: $CANONICAL"
    exit 1
fi

echo "Syncing global AI rules from: $CANONICAL"
echo ""

# --- Claude Code: symlink ---
echo "=== Claude Code ==="
if [[ -L "$CLAUDE_TARGET" ]]; then
    target=$(readlink -f "$CLAUDE_TARGET")
    canonical_real=$(readlink -f "$CANONICAL")
    if [[ "$target" == "$canonical_real" ]]; then
        ok "Symlink correct: $CLAUDE_TARGET -> $CANONICAL"
    else
        warn "Symlink exists but points to: $target"
        warn "Relinking to canonical..."
        ln -sf "$CANONICAL" "$CLAUDE_TARGET"
        ok "Symlink updated"
    fi
elif [[ -f "$CLAUDE_TARGET" ]]; then
    warn "$CLAUDE_TARGET exists as a regular file, backing up and replacing with symlink"
    cp "$CLAUDE_TARGET" "${CLAUDE_TARGET}.bak.$(date +%Y%m%d-%H%M%S)"
    ln -sf "$CANONICAL" "$CLAUDE_TARGET"
    ok "Backed up original and created symlink"
else
    mkdir -p "$(dirname "$CLAUDE_TARGET")"
    ln -sf "$CANONICAL" "$CLAUDE_TARGET"
    ok "Created symlink: $CLAUDE_TARGET -> $CANONICAL"
fi
echo ""

# --- Zed: inject assistant_instructions into settings.json ---
# Uses targeted text surgery to insert/replace the key without
# round-tripping through a JSON parser, so JSONC comments survive.
echo "=== Zed ==="
if [[ -f "$ZED_SETTINGS" ]]; then
    if python3 -c "import json" 2>/dev/null; then
        python3 << 'PYEOF'
import json, os, re, shutil, sys
from datetime import datetime

settings_path = os.path.expanduser("~/.config/zed/settings.json")
canonical_path = os.path.expanduser("~/.config/ai-rules/global-behavior.md")

with open(canonical_path, "r") as f:
    rules_content = f.read()

with open(settings_path, "r") as f:
    raw = f.read()

encoded_value = json.dumps(rules_content)
new_entry = f'  "assistant_instructions": {encoded_value}'

# Check if assistant_instructions already exists in the raw JSONC.
# Match the key and its value (a JSON string: "..." with escaped content).
pattern = re.compile(
    r'^(\s*)"assistant_instructions"\s*:\s*"(?:[^"\\]|\\.)*"',
    re.MULTILINE | re.DOTALL,
)

match = pattern.search(raw)

if match:
    updated = raw[:match.start()] + new_entry + raw[match.end():]
    action = "Updated"
else:
    # Insert before the final closing brace. Find the last `}` that
    # closes the top-level object.
    last_brace = raw.rfind("}")
    if last_brace == -1:
        print("Cannot find closing } in Zed settings", file=sys.stderr)
        sys.exit(1)

    # Walk backwards to find the last non-whitespace char before `}`
    # to decide whether we need a comma.
    before = raw[:last_brace].rstrip()
    needs_comma = before and before[-1] not in (",", "{")
    comma = "," if needs_comma else ""

    updated = before + comma + "\n" + new_entry + ",\n" + raw[last_brace:]
    action = "Added"

# Back up, then write
backup = settings_path + f".bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
shutil.copy2(settings_path, backup)

with open(settings_path, "w") as f:
    f.write(updated)

print(f"{action} assistant_instructions in Zed settings")
print(f"Backup saved: {backup}")
PYEOF
        if [[ $? -eq 0 ]]; then
            ok "Zed settings updated with assistant_instructions"
        else
            fail "Failed to update Zed settings"
        fi
    else
        fail "Python3 required for Zed settings update (JSONC parsing)"
    fi
else
    warn "Zed settings not found at $ZED_SETTINGS — skipping"
fi
echo ""

# --- Cursor IDE: no file-based global rules mechanism ---
echo "=== Cursor IDE ==="
echo "Cursor stores User Rules in its internal settings (not a plain file)."
echo "The sync script cannot update them programmatically."
echo ""
echo "To set your global rules in Cursor:"
echo "  1. Open Cursor Settings (Ctrl+Shift+J or Cmd+,)"
echo "  2. Click 'Rules' in the sidebar"
echo "  3. Paste the content below into 'User Rules'"
echo ""

if command -v xclip &>/dev/null; then
    cat "$CANONICAL" | xclip -selection clipboard
    ok "Rules content copied to clipboard — paste into Cursor Settings > Rules"
elif command -v xsel &>/dev/null; then
    cat "$CANONICAL" | xsel --clipboard
    ok "Rules content copied to clipboard — paste into Cursor Settings > Rules"
elif command -v wl-copy &>/dev/null; then
    cat "$CANONICAL" | wl-copy
    ok "Rules content copied to clipboard — paste into Cursor Settings > Rules"
else
    warn "No clipboard tool found (xclip/xsel/wl-copy). Printing content instead:"
    echo ""
    echo "--- BEGIN RULES (copy this) ---"
    cat "$CANONICAL"
    echo "--- END RULES ---"
fi
echo ""

# --- Summary ---
echo "=== Summary ==="
echo "Canonical source: $CANONICAL"
echo ""
echo "  Claude Code:  symlink at $CLAUDE_TARGET"
echo "  Zed:          assistant_instructions in $ZED_SETTINGS"
echo "  Cursor IDE:   paste into Settings > Rules (manual)"
echo ""
echo "Edit $CANONICAL and re-run this script to propagate changes."
