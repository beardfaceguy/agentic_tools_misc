#!/usr/bin/env bash
# install.sh — set up the global AI rules pipeline.
#
# Installs:
#   ~/.config/ai-rules/global-behavior.md   (canonical rules file)
#   ~/.config/ai-rules/sync-rules.sh        (propagation script)
#   ~/.config/systemd/user/ai-rules-sync.*  (file watcher units)
#   ~/.claude/CLAUDE.md                     (symlink for Claude Code)
#
# Safe to re-run. Existing global-behavior.md is never overwritten — you'll
# be prompted. Backups are created before any destructive writes.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RULES_DIR="$HOME/.config/ai-rules"
SYSTEMD_DIR="$HOME/.config/systemd/user"
CLAUDE_TARGET="$HOME/.claude/CLAUDE.md"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[ok]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
fail() { echo -e "${RED}[fail]${NC} $1"; }

echo "=== behavior-template installer ==="
echo ""

# --- Preflight checks ---
if [[ "$(uname)" != "Linux" ]]; then
    warn "This installer targets Linux with systemd."
    warn "See CUSTOMIZING.md for macOS adaptation."
    echo ""
fi

if ! command -v python3 &>/dev/null; then
    warn "python3 not found. Zed sync will be skipped at runtime."
fi

if ! command -v systemctl &>/dev/null; then
    fail "systemctl not found. The auto-sync watcher requires systemd."
    fail "You can still use sync-rules.sh manually."
    NO_SYSTEMD=1
else
    NO_SYSTEMD=0
fi
echo ""

# --- Copy rules and sync script ---
echo "=== Installing files ==="
mkdir -p "$RULES_DIR"

if [[ -f "$RULES_DIR/global-behavior.md" ]]; then
    warn "Existing global-behavior.md found at $RULES_DIR/"
    echo -n "  Overwrite with template? [y/N] "
    read -r reply
    if [[ "$reply" =~ ^[Yy]$ ]]; then
        cp "$RULES_DIR/global-behavior.md" \
           "$RULES_DIR/global-behavior.md.bak.$(date +%Y%m%d-%H%M%S)"
        cp "$SCRIPT_DIR/global-behavior.md" "$RULES_DIR/global-behavior.md"
        ok "Replaced (backup saved)"
    else
        ok "Kept existing rules file"
    fi
else
    cp "$SCRIPT_DIR/global-behavior.md" "$RULES_DIR/global-behavior.md"
    ok "Installed global-behavior.md"
fi

cp "$SCRIPT_DIR/sync-rules.sh" "$RULES_DIR/sync-rules.sh"
chmod +x "$RULES_DIR/sync-rules.sh"
ok "Installed sync-rules.sh"
echo ""

# --- Add pipeline comment to the installed rules file ---
# Only if the file doesn't already have the pipeline comment
if ! grep -q "CANONICAL SOURCE" "$RULES_DIR/global-behavior.md" 2>/dev/null; then
    COMMENT='<!--
CANONICAL SOURCE for global AI agent behavior rules.

This file is the single source of truth. Edit ONLY this file, then changes
propagate automatically to every IDE via a systemd file watcher.

Pipeline:
  1. You edit this file (any editor, any method).
  2. systemd path unit (ai-rules-sync.path) detects the write via inotify.
  3. It triggers ai-rules-sync.service, which runs sync-rules.sh.
  4. sync-rules.sh pushes the content to each IDE target:
       Claude Code : ~/.claude/CLAUDE.md (symlink — instant, no copy needed)
       Zed         : ~/.config/zed/settings.json (assistant_instructions, auto-updated)
       Cursor IDE  : copies to clipboard for manual paste into Settings > Rules

Related files:
  This file          : ~/.config/ai-rules/global-behavior.md
  Sync script        : ~/.config/ai-rules/sync-rules.sh
  systemd path unit  : ~/.config/systemd/user/ai-rules-sync.path
  systemd service    : ~/.config/systemd/user/ai-rules-sync.service

Manual sync:  ~/.config/ai-rules/sync-rules.sh
Watcher status: systemctl --user status ai-rules-sync.path
-->

'
    EXISTING=$(cat "$RULES_DIR/global-behavior.md")
    printf '%s%s' "$COMMENT" "$EXISTING" > "$RULES_DIR/global-behavior.md"
    ok "Added pipeline comment to rules file"
fi

# --- Install systemd units ---
echo "=== Installing systemd units ==="
if [[ "$NO_SYSTEMD" -eq 0 ]]; then
    mkdir -p "$SYSTEMD_DIR"
    cp "$SCRIPT_DIR/systemd/ai-rules-sync.path" "$SYSTEMD_DIR/"
    cp "$SCRIPT_DIR/systemd/ai-rules-sync.service" "$SYSTEMD_DIR/"
    ok "Installed ai-rules-sync.path and ai-rules-sync.service"

    systemctl --user daemon-reload
    systemctl --user enable --now ai-rules-sync.path
    ok "File watcher enabled and started"
else
    warn "Skipped systemd setup (systemctl not available)"
fi
echo ""

# --- Claude Code: symlink ---
echo "=== Claude Code ==="
if [[ -L "$CLAUDE_TARGET" ]]; then
    existing=$(readlink -f "$CLAUDE_TARGET")
    canonical=$(readlink -f "$RULES_DIR/global-behavior.md")
    if [[ "$existing" == "$canonical" ]]; then
        ok "Symlink already correct"
    else
        ln -sf "$RULES_DIR/global-behavior.md" "$CLAUDE_TARGET"
        ok "Symlink updated (was pointing to $existing)"
    fi
elif [[ -f "$CLAUDE_TARGET" ]]; then
    cp "$CLAUDE_TARGET" "${CLAUDE_TARGET}.bak.$(date +%Y%m%d-%H%M%S)"
    ln -sf "$RULES_DIR/global-behavior.md" "$CLAUDE_TARGET"
    ok "Backed up existing CLAUDE.md and created symlink"
else
    mkdir -p "$(dirname "$CLAUDE_TARGET")"
    ln -sf "$RULES_DIR/global-behavior.md" "$CLAUDE_TARGET"
    ok "Created symlink"
fi
echo ""

# --- Initial sync (Zed + Cursor clipboard) ---
echo "=== Running initial sync ==="
"$RULES_DIR/sync-rules.sh"
echo ""

# --- Done ---
echo "=== Installation complete ==="
echo ""
echo "Canonical file: $RULES_DIR/global-behavior.md"
echo ""
echo "What's automatic:"
echo "  - Claude Code picks up changes instantly (symlink)"
echo "  - Zed gets updated on every save (systemd watcher)"
echo ""
echo "One manual step for Cursor IDE:"
echo "  1. Open Cursor Settings (Ctrl+Shift+J)"
echo "  2. Click 'Rules' in the sidebar"
echo "  3. Paste (content was copied to your clipboard)"
echo ""
echo "To edit your rules later:"
echo "  \$EDITOR $RULES_DIR/global-behavior.md"
