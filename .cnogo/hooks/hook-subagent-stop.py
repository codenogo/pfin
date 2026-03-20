#!/usr/bin/env python3
"""
SubagentStop hook — observer-only footer validation (Contract 06).

Reads SubagentStop hook input from stdin as JSON, validates TASK_EVIDENCE
and TASK_DONE footer structure, and emits warnings only.

Must complete in < 3 seconds total. Always exits 0.
"""

from __future__ import annotations

try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass  # imported as module; caller manages sys.path

import json
import re
import sys

_TASK_DONE_RE = re.compile(r"TASK_DONE:\s*\[([^\]]+)\]")
_TASK_EVIDENCE_RE = re.compile(r"^TASK_EVIDENCE:\s*(\{.*\})\s*$")
_SCOUT_REPORT_RE = re.compile(r"^SCOUT_REPORT:\s*(\{.*\})\s*$")


def _extract_task_evidence(last_msg: str) -> dict | None:
    """Extract TASK_EVIDENCE JSON payload from the last assistant message."""
    for raw_line in reversed(last_msg.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        match = _TASK_EVIDENCE_RE.match(line)
        if not match:
            continue
        try:
            parsed = json.loads(match.group(1))
        except Exception:
            print("[hook-subagent-stop] malformed TASK_EVIDENCE JSON", file=sys.stderr)
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _extract_scout_report(last_msg: str) -> tuple[dict | None, bool]:
    """Extract SCOUT_REPORT JSON payload from the last assistant message."""
    for raw_line in reversed(last_msg.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        match = _SCOUT_REPORT_RE.match(line)
        if not match:
            continue
        try:
            parsed = json.loads(match.group(1))
        except Exception:
            print("[hook-subagent-stop] malformed SCOUT_REPORT JSON", file=sys.stderr)
            return None, True
        return parsed if isinstance(parsed, dict) else None, True
    return None, False


def _validate_scout_report(report: dict | None) -> bool:
    """Validate minimal SCOUT_REPORT structure."""
    if report is None:
        print("[hook-subagent-stop] missing or malformed SCOUT_REPORT payload", file=sys.stderr)
        return False

    required_strings = ("kind", "question", "confidence", "summary", "implication")
    valid = True
    for key in required_strings:
        value = report.get(key)
        if not isinstance(value, str) or not value.strip():
            print(f"[hook-subagent-stop] SCOUT_REPORT missing non-empty '{key}'", file=sys.stderr)
            valid = False

    sources = report.get("sources")
    if not isinstance(sources, list) or not sources or not all(isinstance(item, str) and item.strip() for item in sources):
        print("[hook-subagent-stop] SCOUT_REPORT sources should be a non-empty list of strings", file=sys.stderr)
        valid = False

    if valid:
        kind = report["kind"].strip()
        confidence = report["confidence"].strip()
        print(f"[hook-subagent-stop] observed scout report: {kind} ({confidence})", file=sys.stderr)
    return valid


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload: dict = {}
        try:
            payload = json.loads(raw)
        except Exception:
            print(
                "[hook-subagent-stop] could not parse stdin as JSON", file=sys.stderr
            )

        last_msg: str = payload.get("last_assistant_message", "") or ""
        task_evidence = _extract_task_evidence(last_msg)

        # Allow read-only scouts to report with SCOUT_REPORT instead of TASK_DONE.
        match = _TASK_DONE_RE.search(last_msg)
        if not match:
            scout_report, has_scout_report = _extract_scout_report(last_msg)
            if has_scout_report:
                _validate_scout_report(scout_report)
                return 0
            print("[hook-subagent-stop] no TASK_DONE footer found", file=sys.stderr)
            return 0

        # Parse comma-separated IDs
        ids_str = match.group(1)
        reported: set[str] = set()
        has_duplicate = False
        for raw_id in ids_str.split(","):
            memory_id = raw_id.strip()
            if not memory_id:
                continue
            if memory_id in reported:
                has_duplicate = True
                continue
            reported.add(memory_id)

        if has_duplicate:
            print("[hook-subagent-stop] duplicate TASK_DONE ids detected", file=sys.stderr)

        if task_evidence is None:
            print("[hook-subagent-stop] missing or malformed TASK_EVIDENCE payload", file=sys.stderr)
        else:
            verification = task_evidence.get("verification")
            if not isinstance(verification, dict):
                print("[hook-subagent-stop] TASK_EVIDENCE missing verification object", file=sys.stderr)
            commands = verification.get("commands") if isinstance(verification, dict) else None
            timestamp = verification.get("timestamp") if isinstance(verification, dict) else None
            if not isinstance(commands, list) or not commands:
                print("[hook-subagent-stop] TASK_EVIDENCE verification.commands should be non-empty list", file=sys.stderr)
            if not isinstance(timestamp, str) or not timestamp.strip():
                print("[hook-subagent-stop] TASK_EVIDENCE verification.timestamp should be non-empty string", file=sys.stderr)

        if reported:
            print(f"[hook-subagent-stop] observed TASK_DONE for: {', '.join(sorted(reported))}", file=sys.stderr)

    except Exception as exc:
        print(f"[hook-subagent-stop] unexpected error: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
