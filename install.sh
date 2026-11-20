#!/usr/bin/env bash
# skill-radar installer: copies the hook scripts into ~/.claude/skill-radar
# and wires a UserPromptSubmit hook into ~/.claude/settings.json (merged,
# never overwritten; your existing settings are preserved). Safe to re-run.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="$HOME/.claude/skill-radar"

echo "skill-radar: installing from $SRC_DIR to $DEST_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "skill-radar: python3 is required and was not found on PATH." >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
cp "$SRC_DIR/hint.py" "$SRC_DIR/discover.py" "$SRC_DIR/index.json" "$DEST_DIR/"
chmod +x "$DEST_DIR/hint.py" "$DEST_DIR/discover.py"

python3 - "$DEST_DIR" <<'PYEOF'
import json
import os
import sys

dest_dir = sys.argv[1]
settings_path = os.path.expanduser("~/.claude/settings.json")
command = f'python3 "{dest_dir}/hint.py"'

settings = {}
if os.path.exists(settings_path):
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

hooks = settings.setdefault("hooks", {})
ups = hooks.setdefault("UserPromptSubmit", [])

already_installed = any(
    h.get("command", "").find("skill-radar/hint.py") != -1
    for group in ups
    for h in group.get("hooks", [])
)

if already_installed:
    # keep the existing entry's command in sync with the (possibly moved) dest_dir
    for group in ups:
        for h in group.get("hooks", []):
            if "skill-radar/hint.py" in h.get("command", ""):
                h["command"] = command
    print("skill-radar: hook entry already present, refreshed its path.")
else:
    ups.append({"hooks": [{"type": "command", "command": command, "timeout": 5}]})
    print("skill-radar: hook entry added to ~/.claude/settings.json.")

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)
    f.write("\n")
PYEOF

echo "skill-radar: running first scan..."
python3 "$DEST_DIR/discover.py"
echo "skill-radar: installed. Start a new Claude Code session for the hook to take effect."
