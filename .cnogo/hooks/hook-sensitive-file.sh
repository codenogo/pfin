#!/bin/bash

# Sensitive file reader blocker for PreToolUse (Read)
# Warns when attempting to read files that may contain secrets.
#
# Perf notes (fix/compaction-hook-hang):
# - Pure bash — no Python subprocess spawn (was causing session hangs during compaction)
# - Input size guard — skip parsing for large payloads (>64KB)
# - permissions.deny in settings.json already blocks the same patterns;
#   this hook is defense-in-depth only.

if [ -z "${CLAUDE_TOOL_INPUT:-}" ]; then
  exit 0
fi

# Fast exit: skip if input is too large (>64KB). Large payloads are
# unlikely to be simple file reads and parsing them blocks the session.
if [ "${#CLAUDE_TOOL_INPUT}" -gt 65536 ]; then
  exit 0
fi

# Extract file_path from JSON without spawning Python.
# CLAUDE_TOOL_INPUT for Read is typically: {"file_path":"/some/path",...}
# We use a simple regex extraction.
extract_path() {
  local input="$1"
  local path=""

  # Match "key": "value" for common path keys
  for key in file_path path target_file filename file; do
    path=$(printf '%s' "$input" | \
      sed -n 's/.*"'"$key"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    if [ -n "$path" ]; then
      printf '%s\n' "$path"
      return
    fi
  done
}

path="$(extract_path "$CLAUDE_TOOL_INPUT")"
if [ -z "$path" ]; then
  exit 0
fi

# Check against sensitive patterns (lowercase comparison)
lower="$(printf '%s' "$path" | tr '[:upper:]' '[:lower:]')"
if printf '%s' "$lower" | grep -qE '((^|/)\.env($|\.|/)|credentials|secrets\.ya?ml$|-prod\.(ya?ml|properties|json)$|\.pem$|\.key$|id_rsa$|id_ed25519$|\.aws/credentials$|\.kube/config$)'; then
  printf '⚠️ Attempting to read sensitive file: %s\n' "$path"
  exit 1
fi

exit 0
