#!/bin/bash
set -e

# Dangerous command blocker for PreToolUse (Bash)
# Blocks destructive patterns that could damage the system.
# Uses printf instead of echo to avoid shell injection via $CLAUDE_TOOL_INPUT.

if [ -z "$CLAUDE_TOOL_INPUT" ]; then
  exit 0
fi

# Fast exit: skip for very large inputs (>64KB) to prevent hangs.
if [ "${#CLAUDE_TOOL_INPUT}" -gt 65536 ]; then
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

# Match dangerous patterns — covers flag variants, absolute paths, and command wrappers
if printf '%s' "$COMMAND" | grep -qE '(rm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+-[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*\s+-[a-zA-Z]*r|-rf|-fr)\s+[/~]|/bin/rm\s|command\s+rm\s|sudo\s+rm\s|chmod\s+777|>\s*/dev/sd|mkfs\.|dd\s+if=)'; then
  echo '❌ Blocked: Dangerous command pattern detected'
  exit 1
fi

exit 0
