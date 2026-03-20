#!/bin/bash
set -e

# PostToolUse commit confirmation for Bash tool calls.
# Supports both raw command strings and JSON-encoded CLAUDE_TOOL_INPUT payloads.

if [ -z "$CLAUDE_TOOL_INPUT" ]; then
  exit 0
fi

extract_command() {
  python3 - "$CLAUDE_TOOL_INPUT" <<'PY'
import json
import sys

raw = sys.argv[1].strip()
if not raw:
    print("")
    raise SystemExit(0)

keys = ("command", "cmd", "shell_command", "bash_command", "input", "text")

def pick(obj):
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in obj.values():
            found = pick(value)
            if found:
                return found
        return ""
    if isinstance(obj, list):
        for item in obj:
            found = pick(item)
            if found:
                return found
        return ""
    return ""

try:
    payload = json.loads(raw)
except Exception:
    print(raw)
    raise SystemExit(0)
if isinstance(payload, str):
    print(payload.strip() or raw)
    raise SystemExit(0)

command = pick(payload) or raw
print(command)
PY
}

COMMAND="$(extract_command || true)"
if [ -z "$COMMAND" ]; then
  exit 0
fi

if printf '%s' "$COMMAND" | grep -Eq '^[[:space:]]*git[[:space:]]+commit([[:space:]]|$)'; then
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "✅ Committed:"
    git log -1 --oneline 2>/dev/null || true
  fi
fi

exit 0
