#!/bin/bash
set -e

# PostToolUse hook: reindex context graph after git commit.
# Delegates to workflow_hooks.py post_commit_graph for the actual work.

if [ -z "$CLAUDE_TOOL_INPUT" ]; then
  exit 0
fi

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

if [ -f "$ROOT/.cnogo/scripts/workflow_hooks.py" ]; then
  python3 "$ROOT/.cnogo/scripts/workflow_hooks.py" post_commit_graph
else
  exit 0
fi
