#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v git >/dev/null 2>&1; then
  echo "❌ git not found"
  exit 1
fi

cd "$ROOT"

if [ ! -d ".githooks" ]; then
  echo "❌ .githooks directory not found at repo root"
  exit 1
fi

git config core.hooksPath .githooks
echo "✅ Installed git hooks (core.hooksPath=.githooks)"
echo "To uninstall: git config --unset core.hooksPath"

