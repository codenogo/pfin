#!/usr/bin/env python3
"""
PreCompact hook — write a compaction checkpoint before context is compacted.

Reads PreCompact hook input from stdin as JSON:
  {hook_event_name, trigger, custom_instructions}

Writes .cnogo/compaction-checkpoint.json with current session + team state.
Appends one telemetry line to .cnogo/command-usage.jsonl.

Must complete in < 3 seconds. Always exits 0.
"""

from __future__ import annotations

try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass  # imported as module; caller manages sys.path

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


_SESSION_FILE = ".cnogo/worktree-session.json"
_CHECKPOINT_FILE = ".cnogo/compaction-checkpoint.json"
_USAGE_FILE = ".cnogo/command-usage.jsonl"
_TEAMS_DIR = Path.home() / ".claude" / "teams"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_session(repo_root: Path) -> dict | None:
    """Read .cnogo/worktree-session.json and extract relevant fields."""
    try:
        session_path = repo_root / _SESSION_FILE
        if not session_path.exists():
            return None
        data = json.loads(session_path.read_text(encoding="utf-8"))
        worktrees = []
        for wt in data.get("worktrees", []):
            worktrees.append(
                {
                    "taskIndex": wt.get("taskIndex"),
                    "name": wt.get("name", ""),
                    "status": wt.get("status", ""),
                    "memoryId": wt.get("memoryId", ""),
                }
            )
        return {
            "feature": data.get("feature", ""),
            "planNumber": data.get("planNumber", ""),
            "phase": data.get("phase", ""),
            "worktrees": worktrees,
        }
    except Exception as exc:
        print(f"[hook-pre-compact] could not read session: {exc}", file=sys.stderr)
        return None


def _read_team() -> dict | None:
    """Read ~/.claude/teams/ and extract first active team config."""
    try:
        if not _TEAMS_DIR.exists():
            return None
        for team_dir in sorted(_TEAMS_DIR.iterdir()):
            if not team_dir.is_dir():
                continue
            config_path = team_dir / "config.json"
            if not config_path.exists():
                continue
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                members_raw = data.get("members", [])
                members = [m["name"] for m in members_raw if m.get("name")]
                return {
                    "name": data.get("name", team_dir.name),
                    "members": members,
                }
            except Exception as exc:
                print(
                    f"[hook-pre-compact] could not read team config {config_path}: {exc}",
                    file=sys.stderr,
                )
                continue
        return None
    except Exception as exc:
        print(f"[hook-pre-compact] could not read teams dir: {exc}", file=sys.stderr)
        return None


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically via tempfile + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp-checkpoint-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _append_telemetry(path: Path, record: dict) -> None:
    """Append one JSON line to the telemetry file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload: dict = {}
        try:
            payload = json.loads(raw)
        except Exception:
            print(
                "[hook-pre-compact] could not parse stdin as JSON", file=sys.stderr
            )

        trigger: str = payload.get("trigger", "auto") or "auto"
        print(f"[hook-pre-compact] trigger={trigger}", file=sys.stderr)

        # Repo root is three levels up: .cnogo/hooks/file.py → repo root
        repo_root = Path(__file__).parent.parent.parent.resolve()

        session = _read_session(repo_root)
        team = _read_team()

        timestamp = _now_iso()

        checkpoint = {
            "schemaVersion": 1,
            "trigger": trigger,
            "timestamp": timestamp,
            "session": session,
            "team": team,
        }

        checkpoint_path = repo_root / _CHECKPOINT_FILE
        _atomic_write(checkpoint_path, checkpoint)
        print(
            f"[hook-pre-compact] wrote checkpoint to {checkpoint_path}", file=sys.stderr
        )

        worktree_count = len(session.get("worktrees", [])) if session else 0
        telemetry = {
            "type": "compaction",
            "trigger": trigger,
            "timestamp": timestamp,
            "hasSession": session is not None,
            "worktreeCount": worktree_count,
        }
        usage_path = repo_root / _USAGE_FILE
        _append_telemetry(usage_path, telemetry)
        print(
            f"[hook-pre-compact] appended telemetry to {usage_path}", file=sys.stderr
        )

    except Exception as exc:
        print(f"[hook-pre-compact] unexpected error: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
