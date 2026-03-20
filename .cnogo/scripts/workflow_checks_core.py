#!/usr/bin/env python3
"""
Package-aware check runner for this workflow pack.

Reads docs/planning/WORKFLOW.json packages[].commands and runs checks per package:
- verify-ci: writes VERIFICATION-CI.md/json under a feature folder
- review: writes REVIEW.md/json under feature folder if inferable from memory, else under work/review/
- ship-ready: validates staged-review completeness + freshness for /ship
- entropy: scans for invariant drift and can write background cleanup tasks
- discover: analyzes hook telemetry for missed token-savings opportunities

No external dependencies.
"""

from __future__ import annotations

try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass  # imported as module; caller manages sys.path

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from workflow_utils import load_json, load_workflow as _load_workflow_util, repo_root, write_json
except ModuleNotFoundError:
    from .workflow_utils import load_json, load_workflow as _load_workflow_util, repo_root, write_json  # type: ignore

DEFAULT_COMMAND_TIMEOUT_SEC = 300
DEFAULT_OUTPUT_COMPACT_MAX_LINES = 120
DEFAULT_OUTPUT_COMPACT_FAIL_TAIL_LINES = 80
DEFAULT_OUTPUT_COMPACT_PASS_LINES = 30
DEFAULT_TEE_MIN_CHARS = 500
DEFAULT_TEE_MAX_FILES = 20
DEFAULT_TEE_MAX_FILE_SIZE = 1_048_576
DEFAULT_COMMAND_USAGE_SINCE_DAYS = 30

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_TEST_SUMMARY_RE = re.compile(
    r"(?i)(test result:|collected\s+\d+|ran\s+\d+\s+tests?|pass(?:ed|ing)|fail(?:ed|ures?)|error(?:s)?|xfailed|xpassed|skipped|duration|time:)"
)
_FAILURE_LINE_RE = re.compile(r"(?i)(fail(?:ed|ure)?|error|exception|traceback|panic|assert|E\s+)")
_LINT_RULE_RE = re.compile(r"(?i)\b([A-Z]{1,4}\d{2,4}|[a-z][a-z0-9_-]{2,})\b")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_shell(cmd: str, cwd: Path, *, timeout_sec: int = DEFAULT_COMMAND_TIMEOUT_SEC) -> tuple[int, str]:
    # WORKFLOW.json is a trusted file (equivalent to Makefile) — shell=True is intentional.
    try:
        out = subprocess.check_output(
            cmd,
            cwd=cwd,
            shell=True,
            stderr=subprocess.STDOUT,
            timeout=timeout_sec,
        ).decode(errors="replace")
        return 0, out
    except subprocess.CalledProcessError as e:
        out = (e.output or b"").decode(errors="replace")
        return int(e.returncode or 1), out
    except subprocess.TimeoutExpired as e:
        out = (e.output or b"").decode(errors="replace")
        return 124, f"Command timed out after {timeout_sec}s.\n{out}".strip()
    except FileNotFoundError as e:
        return 127, str(e)
    except Exception as e:
        return 1, str(e)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _normalize_cmd_text(cmd: str) -> str:
    return " ".join(cmd.strip().split())


def _sanitize_slug(text: str, *, max_len: int = 40) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "output"
    return slug[:max_len]


def _relative_display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)


def _append_compact_line(
    ordered: list[str],
    counts: dict[str, int],
    line: str,
    *,
    dedupe: bool,
) -> None:
    text = line.strip()
    if not text:
        return
    if not dedupe:
        ordered.append(text)
        return
    if text in counts:
        counts[text] += 1
        return
    counts[text] = 1
    ordered.append(text)


def _materialize_compact_lines(ordered: list[str], counts: dict[str, int], *, dedupe: bool) -> list[str]:
    if not dedupe:
        return ordered
    out: list[str] = []
    for line in ordered:
        n = counts.get(line, 1)
        if n > 1:
            out.append(f"{line} (x{n})")
        else:
            out.append(line)
    return out


def _clip_lines(lines: list[str], max_lines: int) -> list[str]:
    if len(lines) <= max_lines:
        return lines
    hidden = len(lines) - max_lines
    return lines[:max_lines] + [f"... +{hidden} more lines"]


def _compact_test_output(
    lines: list[str],
    *,
    max_lines: int,
    fail_tail_lines: int,
    pass_lines: int,
    dedupe: bool,
    rc: int,
) -> tuple[str, str]:
    summary: list[str] = []
    failures: list[str] = []
    keep_context = False
    blank_run = 0

    for raw in lines:
        line = raw.rstrip()
        if _TEST_SUMMARY_RE.search(line):
            summary.append(line.strip())

        if _FAILURE_LINE_RE.search(line):
            failures.append(line.strip())
            keep_context = True
            blank_run = 0
            continue

        if keep_context:
            if not line.strip():
                blank_run += 1
                if blank_run >= 2:
                    keep_context = False
                continue
            if (
                line.startswith((" ", "\t"))
                or line.lstrip().startswith(("at ", "File \"", "...", "Caused by:"))
            ):
                failures.append(line.strip())
                blank_run = 0
                continue
            keep_context = False

    ordered: list[str] = []
    counts: dict[str, int] = {}
    if rc != 0 and failures:
        _append_compact_line(ordered, counts, "FAILURES:", dedupe=False)
        for line in failures:
            _append_compact_line(ordered, counts, line, dedupe=dedupe)
    if summary:
        _append_compact_line(ordered, counts, "SUMMARY:", dedupe=False)
        limit = pass_lines if rc == 0 else max(8, pass_lines // 2)
        for line in summary[:limit]:
            _append_compact_line(ordered, counts, line, dedupe=dedupe)

    if not ordered:
        _append_compact_line(ordered, counts, "OUTPUT (tail):", dedupe=False)
        for line in lines[-fail_tail_lines:]:
            _append_compact_line(ordered, counts, line.strip(), dedupe=dedupe)

    compact_lines = _materialize_compact_lines(ordered, counts, dedupe=dedupe)
    compact_lines = _clip_lines(compact_lines, max_lines)
    return "\n".join(compact_lines).strip(), "failure-focus"


def _compact_lint_output(
    lines: list[str],
    *,
    max_lines: int,
    fail_tail_lines: int,
    pass_lines: int,
    dedupe: bool,
    rc: int,
) -> tuple[str, str]:
    summary: list[str] = []
    findings: list[str] = []
    grouped_rules: dict[str, int] = {}

    for raw in lines:
        line = raw.rstrip()
        low = line.lower()
        if any(tok in low for tok in ("error", "warning", "failed", "issues", "found", "passed", "success")):
            summary.append(line.strip())
        if _FAILURE_LINE_RE.search(line) or ":" in line:
            findings.append(line.strip())
            m = _LINT_RULE_RE.search(line)
            if m:
                rule = m.group(1).lower()
                if rule not in {"error", "warning", "failed"}:
                    grouped_rules[rule] = grouped_rules.get(rule, 0) + 1

    ordered: list[str] = []
    counts: dict[str, int] = {}
    if grouped_rules:
        _append_compact_line(ordered, counts, "GROUPED FINDINGS:", dedupe=False)
        for rule, cnt in sorted(grouped_rules.items(), key=lambda it: (-it[1], it[0]))[:10]:
            _append_compact_line(ordered, counts, f"{rule}: {cnt}", dedupe=False)
    if findings:
        _append_compact_line(ordered, counts, "FINDINGS:", dedupe=False)
        finding_cap = max(10, max_lines // 2)
        for line in findings[:finding_cap]:
            _append_compact_line(ordered, counts, line, dedupe=dedupe)
    if summary:
        _append_compact_line(ordered, counts, "SUMMARY:", dedupe=False)
        limit = pass_lines if rc == 0 else max(8, pass_lines // 2)
        for line in summary[:limit]:
            _append_compact_line(ordered, counts, line, dedupe=dedupe)
    if not ordered:
        _append_compact_line(ordered, counts, "OUTPUT (tail):", dedupe=False)
        for line in lines[-fail_tail_lines:]:
            _append_compact_line(ordered, counts, line.strip(), dedupe=dedupe)

    compact_lines = _materialize_compact_lines(ordered, counts, dedupe=dedupe)
    compact_lines = _clip_lines(compact_lines, max_lines)
    return "\n".join(compact_lines).strip(), "grouped-errors"


def compact_check_output(
    check_name: str,
    cmd: str,
    output: str,
    *,
    rc: int,
    max_lines: int,
    fail_tail_lines: int,
    pass_lines: int,
    dedupe: bool,
    enabled: bool,
) -> tuple[str, str]:
    text = _strip_ansi(output or "").replace("\r\n", "\n")
    lines = [line for line in text.splitlines() if line.strip()]

    if not enabled:
        tail = lines[-max_lines:] if lines else []
        return "\n".join(tail).strip(), "raw-tail"
    if not lines:
        return "", "empty"

    if check_name == "test":
        return _compact_test_output(
            lines,
            max_lines=max_lines,
            fail_tail_lines=fail_tail_lines,
            pass_lines=pass_lines,
            dedupe=dedupe,
            rc=rc,
        )
    if check_name in {"lint", "typecheck"}:
        return _compact_lint_output(
            lines,
            max_lines=max_lines,
            fail_tail_lines=fail_tail_lines,
            pass_lines=pass_lines,
            dedupe=dedupe,
            rc=rc,
        )

    clipped = _clip_lines(lines, max_lines)
    return "\n".join(clipped).strip(), "tail"


def _write_recovery_output(
    root: Path,
    raw_output: str,
    *,
    command_slug: str,
    rc: int,
    cfg: dict[str, Any],
) -> str | None:
    if not cfg.get("enabled", True):
        return None
    mode = str(cfg.get("mode", "failures"))
    if mode == "never":
        return None
    if mode == "failures" and rc == 0:
        return None
    if len(raw_output) < int(cfg.get("minChars", DEFAULT_TEE_MIN_CHARS)):
        return None

    dir_raw = cfg.get("directory", ".cnogo/tee")
    base = Path(str(dir_raw))
    tee_dir = base if base.is_absolute() else (root / base)
    tee_dir.mkdir(parents=True, exist_ok=True)

    max_file_size = int(cfg.get("maxFileSize", DEFAULT_TEE_MAX_FILE_SIZE))
    max_files = int(cfg.get("maxFiles", DEFAULT_TEE_MAX_FILES))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    filename = f"{stamp}_{os.getpid()}_{_sanitize_slug(command_slug)}.log"
    path = tee_dir / filename

    content = raw_output
    if len(content) > max_file_size:
        content = (
            content[:max_file_size]
            + f"\n\n--- truncated at {max_file_size} chars ---"
        )
    path.write_text(content, encoding="utf-8", errors="replace")

    entries = sorted(
        [p for p in tee_dir.glob("*.log") if p.is_file()],
        key=lambda p: p.name,
    )
    if len(entries) > max_files:
        for old in entries[: len(entries) - max_files]:
            try:
                old.unlink()
            except Exception:
                pass

    return _relative_display_path(path, root)


def summarize_token_telemetry(per_pkg: list[dict[str, Any]]) -> dict[str, Any]:
    total_checks = 0
    skipped_checks = 0
    input_tokens = 0
    output_tokens = 0
    saved_tokens = 0

    for pkg in per_pkg:
        for check in pkg.get("checks", []):
            if check.get("result") == "skipped":
                skipped_checks += 1
                continue
            total_checks += 1
            tt = check.get("tokenTelemetry")
            if not isinstance(tt, dict):
                continue
            input_tokens += int(tt.get("inputTokens", 0))
            output_tokens += int(tt.get("outputTokens", 0))
            saved_tokens += int(tt.get("savedTokens", 0))

    savings_pct = round((saved_tokens * 100.0 / input_tokens), 1) if input_tokens else 0.0
    return {
        "checksRun": total_checks,
        "checksSkipped": skipped_checks,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "savedTokens": saved_tokens,
        "savingsPct": savings_pct,
    }


def _parse_iso_timestamp(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _discover_command_usage(
    root: Path,
    *,
    log_file: str,
    since_days: int,
    limit: int,
) -> dict[str, Any]:
    p = Path(log_file)
    log_path = p if p.is_absolute() else (root / p)
    if not log_path.exists():
        return {
            "logPath": _relative_display_path(log_path, root),
            "commandsScanned": 0,
            "optimized": 0,
            "missed": [],
            "unhandled": [],
            "parseErrors": 0,
            "sinceDays": since_days,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, since_days))
    total = 0
    optimized = 0
    parse_errors = 0
    missed_map: dict[str, dict[str, Any]] = {}
    unhandled: dict[str, int] = {}

    for raw_line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except Exception:
            parse_errors += 1
            continue
        if not isinstance(row, dict):
            parse_errors += 1
            continue

        ts = _parse_iso_timestamp(str(row.get("timestamp") or ""))
        if ts is not None and ts < cutoff:
            continue

        total += 1
        status = str(row.get("status") or "neutral")
        cmd = _normalize_cmd_text(str(row.get("command") or ""))
        if status == "optimized":
            optimized += 1
            continue
        if status == "missed":
            suggestion = str(row.get("suggestion") or "").strip() or "[no suggestion]"
            key = f"{row.get('category', 'other')}::{suggestion}"
            bucket = missed_map.setdefault(
                key,
                {
                    "category": str(row.get("category") or "other"),
                    "suggestion": suggestion,
                    "count": 0,
                    "estimatedSaveableTokens": 0,
                },
            )
            bucket["count"] += 1
            bucket["estimatedSaveableTokens"] += int(row.get("estimatedSaveableTokens") or 0)
            continue

        base = cmd.split(" ", 1)[0] if cmd else "[empty]"
        unhandled[base] = unhandled.get(base, 0) + 1

    missed_all = sorted(
        missed_map.values(),
        key=lambda it: (-int(it["estimatedSaveableTokens"]), -int(it["count"]), str(it["suggestion"])),
    )
    missed = missed_all[:limit]
    unhandled_rows = sorted(
        [{"command": k, "count": v} for k, v in unhandled.items()],
        key=lambda it: (-int(it["count"]), str(it["command"])),
    )[:limit]
    total_saveable = sum(int(it.get("estimatedSaveableTokens", 0)) for it in missed_all)

    return {
        "logPath": _relative_display_path(log_path, root),
        "commandsScanned": total,
        "optimized": optimized,
        "optimizedPct": round((optimized * 100.0 / total), 1) if total else 0.0,
        "missed": missed,
        "unhandled": unhandled_rows,
        "estimatedSaveableTokens": total_saveable,
        "parseErrors": parse_errors,
        "sinceDays": since_days,
    }


def _print_discover_text(report: dict[str, Any]) -> None:
    print("CNOGO Discover -- Savings Opportunities")
    print("====================================================")
    print(
        f"Scanned: {report.get('commandsScanned', 0)} commands "
        f"(last {report.get('sinceDays', DEFAULT_COMMAND_USAGE_SINCE_DAYS)} days)"
    )
    print(
        f"Already optimized: {report.get('optimized', 0)} "
        f"({report.get('optimizedPct', 0.0)}%)"
    )
    print(f"Command log: {report.get('logPath', '[unknown]')}")
    print("")

    missed = report.get("missed") if isinstance(report.get("missed"), list) else []
    if missed:
        print("MISSED SAVINGS")
        print("----------------------------------------------------")
        for row in missed:
            suggestion = str(row.get("suggestion") or "")
            print(
                f"- {row.get('category', 'other')}: {row.get('count', 0)}x -> "
                f"`{suggestion}` (~{row.get('estimatedSaveableTokens', 0)} tokens)"
            )
        print("----------------------------------------------------")
        print(f"Estimated saveable tokens: ~{report.get('estimatedSaveableTokens', 0)}")
        print("")

    unhandled = report.get("unhandled") if isinstance(report.get("unhandled"), list) else []
    if unhandled:
        print("TOP UNHANDLED COMMANDS")
        print("----------------------------------------------------")
        for row in unhandled:
            print(f"- {row.get('command', '[unknown]')}: {row.get('count', 0)}")
        print("")

    if int(report.get("parseErrors", 0)) > 0:
        print(f"Parse errors: {report.get('parseErrors', 0)}")


def git_branch(root: Path) -> str:
    rc, out = run_shell("git branch --show-current", cwd=root)
    return out.strip() if rc == 0 else ""


def infer_feature_from_state(root: Path) -> str | None:
    """Infer the active feature slug from memory engine, with branch fallback."""
    # Try memory engine first
    try:
        import sys
        sys.path.insert(0, str(root))
        from scripts.memory import is_initialized, list_issues
        if is_initialized(root):
            # Look for in-progress epics first, then open epics
            for status in ("in_progress", "open"):
                epics = list_issues(
                    issue_type="epic", status=status, root=root
                )
                for epic in epics:
                    if epic.feature_slug:
                        return epic.feature_slug
    except Exception:
        pass
    # Fallback: parse branch name (e.g. feature/foo-bar -> foo-bar)
    branch = git_branch(root)
    if branch and "/" in branch:
        slug = branch.split("/", 1)[1]
        if slug and slug not in {"main", "master", "develop"}:
            return slug
    return None


@dataclass
class CheckResult:
    name: str
    result: str  # pass|fail|skipped|warn
    details: str = ""
    cmd: str | None = None


@dataclass
class InvariantFinding:
    rule: str
    severity: str  # warn|fail
    file: str
    line: int
    message: str


REVIEW_SCHEMA_VERSION = 4


def load_workflow(root: Path | None = None) -> dict[str, Any]:
    return _load_workflow_util(root)


def packages_from_workflow(wf: dict[str, Any]) -> list[dict[str, Any]]:
    pkgs = wf.get("packages")
    if not isinstance(pkgs, list):
        return []
    out: list[dict[str, Any]] = []
    for p in pkgs:
        if isinstance(p, dict) and isinstance(p.get("path"), str):
            out.append(p)
    return out


_CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs", ".kt"}
_SCAN_IGNORE_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
    "__pycache__",
}


def _invariants_cfg(wf: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "enabled": True,
        "scanScope": "changed",
        "maxFileLines": 800,
        "maxFileLinesExceptions": [],
        "maxLineLength": 140,
        "todoRequiresTicket": True,
        "pythonBareExcept": "warn",
        "forbiddenImportPatterns": [
            {
                "pattern": r"^\s*from\s+\S+\s+import\s+\*",
                "mode": "regex",
                "severity": "warn",
                "message": "Avoid wildcard imports.",
            }
        ],
    }
    raw = wf.get("invariants")
    if not isinstance(raw, dict):
        return defaults
    cfg = dict(defaults)
    if isinstance(raw.get("enabled"), bool):
        cfg["enabled"] = raw["enabled"]
    if raw.get("scanScope") in {"changed", "repo"}:
        cfg["scanScope"] = raw["scanScope"]
    for key in ("maxFileLines", "maxLineLength"):
        v = raw.get(key)
        if isinstance(v, int) and not isinstance(v, bool) and v > 0:
            cfg[key] = v
    exceptions = raw.get("maxFileLinesExceptions")
    if isinstance(exceptions, list):
        normalized_exceptions: list[str] = []
        for item in exceptions:
            if isinstance(item, str) and item.strip():
                normalized_exceptions.append(item.strip())
        cfg["maxFileLinesExceptions"] = normalized_exceptions
    if isinstance(raw.get("todoRequiresTicket"), bool):
        cfg["todoRequiresTicket"] = raw["todoRequiresTicket"]
    if raw.get("pythonBareExcept") in {"off", "warn", "fail"}:
        cfg["pythonBareExcept"] = raw["pythonBareExcept"]
    fip = raw.get("forbiddenImportPatterns")
    if isinstance(fip, list):
        normalized: list[dict[str, str]] = []
        for it in fip:
            if not isinstance(it, dict):
                continue
            pattern = it.get("pattern")
            if not isinstance(pattern, str) or not pattern.strip():
                continue
            mode = it.get("mode", "substring")
            if mode not in {"substring", "regex"}:
                mode = "substring"
            sev = it.get("severity", "warn")
            if sev not in {"warn", "fail"}:
                sev = "warn"
            msg = it.get("message")
            normalized.append(
                {
                    "pattern": pattern,
                    "mode": mode,
                    "severity": sev,
                    "message": msg if isinstance(msg, str) and msg.strip() else "Forbidden import pattern matched.",
                }
            )
        cfg["forbiddenImportPatterns"] = normalized
    return cfg


def _entropy_cfg(wf: dict[str, Any]) -> dict[str, Any]:
    defaults = {"enabled": True, "mode": "background", "maxFilesPerTask": 3, "maxTasksPerRun": 3}
    raw = wf.get("entropy")
    if not isinstance(raw, dict):
        return defaults
    cfg = dict(defaults)
    if isinstance(raw.get("enabled"), bool):
        cfg["enabled"] = raw["enabled"]
    if raw.get("mode") in {"background", "manual"}:
        cfg["mode"] = raw["mode"]
    for key in ("maxFilesPerTask", "maxTasksPerRun"):
        val = raw.get(key)
        if isinstance(val, int) and not isinstance(val, bool) and val > 0:
            cfg[key] = val
    return cfg


def _checks_runtime_cfg(wf: dict[str, Any]) -> dict[str, Any]:
    """Runtime config for check scope, changed-file fallback, and command timeout."""
    defaults: dict[str, Any] = {
        "checkScope": "auto",  # auto -> changed locally, all in CI (with feature-scoped CI narrowing when available)
        "changedFilesFallback": "none",  # none|head
        "commandTimeoutSec": DEFAULT_COMMAND_TIMEOUT_SEC,
        "outputCompaction": {
            "enabled": True,
            "maxLines": DEFAULT_OUTPUT_COMPACT_MAX_LINES,
            "failTailLines": DEFAULT_OUTPUT_COMPACT_FAIL_TAIL_LINES,
            "passLines": DEFAULT_OUTPUT_COMPACT_PASS_LINES,
            "dedupe": True,
        },
        "outputRecovery": {
            "enabled": True,
            "mode": "failures",  # failures|always|never
            "minChars": DEFAULT_TEE_MIN_CHARS,
            "maxFiles": DEFAULT_TEE_MAX_FILES,
            "maxFileSize": DEFAULT_TEE_MAX_FILE_SIZE,
            "directory": ".cnogo/tee",
        },
        "tokenTelemetry": {"enabled": True},
        "hookOptimization": {
            "enabled": True,
            "mode": "suggest",
            "showSuggestions": True,
            "logFile": ".cnogo/command-usage.jsonl",
        },
    }
    perf = wf.get("performance")
    if not isinstance(perf, dict):
        return defaults

    cfg = dict(defaults)
    scope = perf.get("checkScope")
    if scope in {"auto", "changed", "all"}:
        cfg["checkScope"] = scope
    fallback = perf.get("changedFilesFallback")
    if fallback in {"none", "head"}:
        cfg["changedFilesFallback"] = fallback
    timeout = perf.get("commandTimeoutSec")
    if isinstance(timeout, int) and not isinstance(timeout, bool) and timeout > 0:
        cfg["commandTimeoutSec"] = timeout

    compact_raw = perf.get("outputCompaction")
    if isinstance(compact_raw, dict):
        compact = dict(defaults["outputCompaction"])
        enabled = compact_raw.get("enabled")
        if isinstance(enabled, bool):
            compact["enabled"] = enabled
        for key in ("maxLines", "failTailLines", "passLines"):
            val = compact_raw.get(key)
            if isinstance(val, int) and not isinstance(val, bool) and val > 0:
                compact[key] = val
        dedupe = compact_raw.get("dedupe")
        if isinstance(dedupe, bool):
            compact["dedupe"] = dedupe
        cfg["outputCompaction"] = compact

    recovery_raw = perf.get("outputRecovery")
    if isinstance(recovery_raw, dict):
        recovery = dict(defaults["outputRecovery"])
        enabled = recovery_raw.get("enabled")
        if isinstance(enabled, bool):
            recovery["enabled"] = enabled
        mode = recovery_raw.get("mode")
        if mode in {"failures", "always", "never"}:
            recovery["mode"] = mode
        for key in ("minChars", "maxFiles", "maxFileSize"):
            val = recovery_raw.get(key)
            if isinstance(val, int) and not isinstance(val, bool) and val > 0:
                recovery[key] = val
        directory = recovery_raw.get("directory")
        if isinstance(directory, str) and directory.strip():
            recovery["directory"] = directory.strip()
        cfg["outputRecovery"] = recovery

    telemetry_raw = perf.get("tokenTelemetry")
    if isinstance(telemetry_raw, dict):
        telemetry = dict(defaults["tokenTelemetry"])
        enabled = telemetry_raw.get("enabled")
        if isinstance(enabled, bool):
            telemetry["enabled"] = enabled
        cfg["tokenTelemetry"] = telemetry

    hook_raw = perf.get("hookOptimization")
    if isinstance(hook_raw, dict):
        hook_cfg = dict(defaults["hookOptimization"])
        enabled = hook_raw.get("enabled")
        if isinstance(enabled, bool):
            hook_cfg["enabled"] = enabled
        mode = hook_raw.get("mode")
        if mode in {"suggest", "enforce", "off"}:
            hook_cfg["mode"] = mode
        show = hook_raw.get("showSuggestions")
        if isinstance(show, bool):
            hook_cfg["showSuggestions"] = show
        log_file = hook_raw.get("logFile")
        if isinstance(log_file, str) and log_file.strip():
            hook_cfg["logFile"] = log_file.strip()
        cfg["hookOptimization"] = hook_cfg

    return cfg



def _git_name_only(root: Path, cmd: str) -> list[str]:
    rc, out = run_shell(cmd, cwd=root, timeout_sec=30)
    if rc != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _changed_relpaths(root: Path, *, fallback: str = "none") -> set[str]:
    """Return changed/untracked relative file paths, with optional HEAD fallback."""
    names: set[str] = set()
    names.update(_git_name_only(root, "git diff --name-only --diff-filter=ACMR"))
    names.update(_git_name_only(root, "git diff --cached --name-only --diff-filter=ACMR"))
    names.update(_git_name_only(root, "git ls-files --others --exclude-standard"))
    if not names and fallback == "head":
        names.update(_git_name_only(root, "git show --name-only --pretty='' HEAD"))
    return names


def _git_ref_exists(root: Path, ref: str) -> bool:
    rc, _ = run_shell(f"git rev-parse --verify --quiet {ref}", cwd=root, timeout_sec=30)
    return rc == 0


def _changed_relpaths_against_base(root: Path) -> set[str]:
    """
    Return changed files in HEAD compared to a likely default branch.
    Used for feature-scoped CI runs where working tree is clean.
    """
    base_ref = ""
    for candidate in ("origin/main", "origin/master", "main", "master"):
        if _git_ref_exists(root, candidate):
            base_ref = candidate
            break
    if not base_ref:
        return set()

    rc, out = run_shell(f"git merge-base HEAD {base_ref}", cwd=root, timeout_sec=30)
    if rc != 0:
        return set()
    merge_base = out.strip().splitlines()[-1] if out.strip() else ""
    if not merge_base:
        return set()

    return set(
        _git_name_only(
            root,
            f"git diff --name-only --diff-filter=ACMR {merge_base}...HEAD",
        )
    )


def _changed_files(root: Path, *, fallback: str = "none") -> list[Path]:
    """Return changed/untracked files, with configurable fallback when tree is clean."""
    names = _changed_relpaths(root, fallback=fallback)
    files: list[Path] = []
    for name in sorted(names):
        p = (root / name).resolve()
        if p.exists() and p.is_file():
            files.append(p)
    return files


def _repo_files(root: Path) -> list[Path]:
    """Return all repo files while pruning ignored directories early."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SCAN_IGNORE_PARTS]
        dpath = Path(dirpath)
        for name in filenames:
            p = dpath / name
            if p.is_file():
                files.append(p)
    return files


def _target_files_for_invariants(
    root: Path,
    cfg: dict[str, Any],
    *,
    changed_files_fallback: str = "none",
) -> list[Path]:
    scope = cfg.get("scanScope", "changed")
    candidates = (
        _repo_files(root)
        if scope == "repo"
        else _changed_files(root, fallback=changed_files_fallback)
    )
    out: list[Path] = []
    for p in candidates:
        if p.suffix.lower() not in _CODE_EXTS:
            continue
        if any(part in _SCAN_IGNORE_PARTS for part in p.parts):
            continue
        out.append(p)
    return out


def _command_prefers_repo_root(pkg_path: str, cmd: str) -> bool:
    """Heuristic: command references package path explicitly, so run from repo root."""
    normalized = pkg_path.strip().strip("./")
    if not normalized:
        return False
    marker = normalized + "/"
    return marker in cmd


def _is_spotless_not_configured(cmd: str, output: str) -> bool:
    lower_cmd = cmd.lower()
    if "spotless" not in lower_cmd:
        return False
    lower_out = output.lower()
    patterns = (
        "no plugin found for prefix 'spotless'",
        'task "spotlesscheck" not found',
        "task 'spotlesscheck' not found",
        'task "spotlessapply" not found',
        "task 'spotlessapply' not found",
        "could not find method spotless",
        "plugin with id 'com.diffplug.spotless' not found",
    )
    return any(p in lower_out for p in patterns)


def _path_matches_patterns(relpath: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if not pattern:
            continue
        if relpath == pattern:
            return True
        if fnmatch.fnmatch(relpath, pattern):
            return True
    return False


def run_invariant_checks(
    root: Path,
    wf: dict[str, Any],
    *,
    changed_files_fallback: str = "none",
) -> list[InvariantFinding]:
    cfg = _invariants_cfg(wf)
    if not cfg.get("enabled", True):
        return []

    findings: list[InvariantFinding] = []
    files = _target_files_for_invariants(
        root,
        cfg,
        changed_files_fallback=changed_files_fallback,
    )
    ticket_re = re.compile(r"(?:[A-Z][A-Z0-9]+-\d+|#[0-9]+)")
    todo_re = re.compile(r"\b(?:TODO|FIXME|XXX)\b")
    bare_except_re = re.compile(r"^\s*except\s*:\s*(#.*)?$")
    forbidden = cfg.get("forbiddenImportPatterns", [])
    max_file_lines = int(cfg.get("maxFileLines", 800))
    max_file_lines_exceptions = cfg.get("maxFileLinesExceptions", [])
    if not isinstance(max_file_lines_exceptions, list):
        max_file_lines_exceptions = []
    max_line_len = int(cfg.get("maxLineLength", 140))
    python_bare_except = cfg.get("pythonBareExcept", "warn")
    todo_requires_ticket = bool(cfg.get("todoRequiresTicket", True))

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        lines = text.splitlines()
        rel = str(path.relative_to(root))

        exempt_from_file_size = _path_matches_patterns(rel, max_file_lines_exceptions)
        if len(lines) > max_file_lines and not exempt_from_file_size:
            findings.append(
                InvariantFinding(
                    rule="max-file-lines",
                    severity="warn",
                    file=rel,
                    line=1,
                    message=f"File has {len(lines)} lines (max {max_file_lines}).",
                )
            )

        for i, line in enumerate(lines, start=1):
            if len(line) > max_line_len and not line.strip().startswith("http"):
                findings.append(
                    InvariantFinding(
                        rule="max-line-length",
                        severity="warn",
                        file=rel,
                        line=i,
                        message=f"Line length {len(line)} exceeds {max_line_len}.",
                    )
                )

            if todo_requires_ticket and todo_re.search(line):
                stripped = line.lstrip()
                is_comment = stripped.startswith(("#", "//", "/*", "*", "--"))
                if is_comment and not ticket_re.search(line):
                    findings.append(
                        InvariantFinding(
                            rule="todo-requires-ticket",
                            severity="warn",
                            file=rel,
                            line=i,
                            message="TODO/FIXME/XXX without ticket reference (e.g., ABC-123 or #123).",
                        )
                    )

            if path.suffix.lower() == ".py" and python_bare_except != "off" and bare_except_re.match(line):
                findings.append(
                    InvariantFinding(
                        rule="python-bare-except",
                        severity="fail" if python_bare_except == "fail" else "warn",
                        file=rel,
                        line=i,
                        message="Bare except detected; catch a specific exception type.",
                    )
                )

            if line.lstrip().startswith(("import ", "from ")):
                for pat in forbidden:
                    if not isinstance(pat, dict):
                        continue
                    pattern = pat.get("pattern", "")
                    mode = pat.get("mode", "substring")
                    if not isinstance(pattern, str) or not pattern:
                        continue
                    matched = False
                    if mode == "regex":
                        try:
                            matched = re.search(pattern, line) is not None
                        except re.error:
                            matched = False
                    else:
                        matched = pattern in line
                    if matched:
                        findings.append(
                            InvariantFinding(
                                rule="forbidden-import-pattern",
                                severity="fail" if pat.get("severity") == "fail" else "warn",
                                file=rel,
                                line=i,
                                message=str(pat.get("message") or "Forbidden import pattern matched."),
                            )
                        )

        if len(findings) > 500:
            break

    return findings


def summarize_invariants(findings: list[InvariantFinding]) -> dict[str, int]:
    summary = {"total": len(findings), "warn": 0, "fail": 0}
    for f in findings:
        if f.severity == "fail":
            summary["fail"] += 1
        else:
            summary["warn"] += 1
    return summary


def _package_has_changes(pkg_path: str, changed_relpaths: set[str]) -> bool:
    normalized = pkg_path.strip()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.strip("/")
    if normalized in {"", "."}:
        return bool(changed_relpaths)
    prefix = normalized + "/"
    return any(p == normalized or p.startswith(prefix) for p in changed_relpaths)


def run_package_checks(
    root: Path,
    pkgs: list[dict[str, Any]],
    *,
    changed_relpaths: set[str] | None = None,
    timeout_sec: int = DEFAULT_COMMAND_TIMEOUT_SEC,
    output_compaction: dict[str, Any] | None = None,
    output_recovery: dict[str, Any] | None = None,
    token_telemetry_enabled: bool = True,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    compact_cfg = output_compaction or {
        "enabled": True,
        "maxLines": DEFAULT_OUTPUT_COMPACT_MAX_LINES,
        "failTailLines": DEFAULT_OUTPUT_COMPACT_FAIL_TAIL_LINES,
        "passLines": DEFAULT_OUTPUT_COMPACT_PASS_LINES,
        "dedupe": True,
    }
    recovery_cfg = output_recovery or {
        "enabled": True,
        "mode": "failures",
        "minChars": DEFAULT_TEE_MIN_CHARS,
        "maxFiles": DEFAULT_TEE_MAX_FILES,
        "maxFileSize": DEFAULT_TEE_MAX_FILE_SIZE,
        "directory": ".cnogo/tee",
    }

    for p in pkgs:
        path = str(p.get("path") or ".")
        kind = str(p.get("kind") or "other")
        name = str(p.get("name") or Path(path).name or path)
        cmds = p.get("commands") if isinstance(p.get("commands"), dict) else {}

        pkg_dir = (root / path).resolve()
        pkg_res: dict[str, Any] = {"name": name, "path": path, "kind": kind, "checks": []}
        pkg_changed = (
            True
            if changed_relpaths is None
            else _package_has_changes(path, changed_relpaths)
        )

        for check_name in ["lint", "typecheck", "test"]:
            cmd = cmds.get(check_name)
            if not isinstance(cmd, str) or not cmd.strip():
                pkg_res["checks"].append({"name": check_name, "result": "skipped", "cmd": None})
                continue
            if not pkg_changed:
                pkg_res["checks"].append(
                    {
                        "name": check_name,
                        "result": "skipped",
                        "cmd": cmd,
                        "reason": "no changed files for package",
                    }
                )
                continue
            check_cwd = root if _command_prefers_repo_root(path, cmd) else pkg_dir
            rc, out = run_shell(cmd, cwd=check_cwd, timeout_sec=timeout_sec)
            compact_out, reducer = compact_check_output(
                check_name,
                cmd,
                out,
                rc=rc,
                max_lines=int(compact_cfg.get("maxLines", DEFAULT_OUTPUT_COMPACT_MAX_LINES)),
                fail_tail_lines=int(compact_cfg.get("failTailLines", DEFAULT_OUTPUT_COMPACT_FAIL_TAIL_LINES)),
                pass_lines=int(compact_cfg.get("passLines", DEFAULT_OUTPUT_COMPACT_PASS_LINES)),
                dedupe=bool(compact_cfg.get("dedupe", True)),
                enabled=bool(compact_cfg.get("enabled", True)),
            )
            recovery_path = _write_recovery_output(
                root,
                out,
                command_slug=f"{name}_{check_name}",
                rc=rc,
                cfg=recovery_cfg,
            )
            input_tokens = _estimate_tokens(out)
            output_tokens = _estimate_tokens(compact_out)
            saved_tokens = max(0, input_tokens - output_tokens)
            savings_pct = round((saved_tokens * 100.0 / input_tokens), 1) if input_tokens else 0.0
            if not token_telemetry_enabled:
                input_tokens = 0
                output_tokens = 0
                saved_tokens = 0
                savings_pct = 0.0

            result = "pass" if rc == 0 else "fail"
            reason = ""
            if rc != 0 and _is_spotless_not_configured(cmd, out):
                result = "skipped"
                reason = "spotless plugin not configured"

            pkg_res["checks"].append(
                {
                    "name": check_name,
                    "result": result,
                    "cmd": cmd,
                    "cwd": _relative_display_path(check_cwd, root) if check_cwd != root else ".",
                    "reason": reason or None,
                    "exitCode": rc,
                    "output": compact_out,
                    "outputReducer": reducer,
                    "fullOutputPath": recovery_path,
                    "tokenTelemetry": {
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                        "savedTokens": saved_tokens,
                        "savingsPct": savings_pct,
                    },
                }
            )

        results.append(pkg_res)
    return results


def summarize_checksets(per_pkg: list[dict[str, Any]]) -> dict[str, str]:
    """
    Aggregate overall lint/tests/types results.
    """
    summary = {"lint": "skipped", "typecheck": "skipped", "tests": "skipped"}
    mapping = {"lint": "lint", "typecheck": "typecheck", "test": "tests"}

    for pkg in per_pkg:
        for c in pkg.get("checks", []):
            nm = c.get("name")
            res = c.get("result")
            if nm not in mapping:
                continue
            key = mapping[nm]
            if res == "fail":
                summary[key] = "fail"
            elif res == "pass" and summary[key] != "fail":
                summary[key] = "pass"
            elif summary[key] == "skipped" and res == "skipped":
                summary[key] = "skipped"
    return summary


def write_verify_ci(
    root: Path,
    feature: str,
    per_pkg: list[dict[str, Any]],
    invariant_findings: list[InvariantFinding],
) -> int:
    base = root / "docs" / "planning" / "work" / "features" / feature
    ts = now_iso()
    agg = summarize_checksets(per_pkg)
    inv = summarize_invariants(invariant_findings)
    tokens = summarize_token_telemetry(per_pkg)

    contract = {
        "schemaVersion": 1,
        "feature": feature,
        "timestamp": ts,
        "checks": [
            {"name": "lint", "result": agg["lint"]},
            {"name": "types", "result": agg["typecheck"]},
            {"name": "tests", "result": agg["tests"]},
        ],
        "packages": per_pkg,
        "invariants": {
            "summary": inv,
            "findings": [
                {
                    "rule": f.rule,
                    "severity": f.severity,
                    "file": f.file,
                    "line": f.line,
                    "message": f.message,
                }
                for f in invariant_findings[:200]
            ],
        },
        "tokenTelemetry": tokens,
        "notes": [],
    }
    write_json(base / "VERIFICATION-CI.json", contract)

    md_lines = [
        f"# Verification (CI): {feature}",
        "",
        f"**Timestamp:** {ts}",
        "",
        "## Summary",
        "",
        f"- Lint: **{agg['lint']}**",
        f"- Types: **{agg['typecheck']}**",
        f"- Tests: **{agg['tests']}**",
        f"- Invariants: **{inv['fail']} fail / {inv['warn']} warn**",
        (
            f"- Token savings: **{tokens['savedTokens']} tokens** "
            f"({tokens['savingsPct']}%, {tokens['checksRun']} checks)"
        ),
        "",
        "## Per-Package Results",
        "",
    ]
    for pkg in per_pkg:
        md_lines.append(f"### {pkg['name']} (`{pkg['path']}`)")
        for c in pkg.get("checks", []):
            suffix = ""
            if c.get("cmd"):
                cwd = c.get("cwd")
                cwd_part = f", cwd `{cwd}`" if isinstance(cwd, str) and cwd else ""
                suffix = f" (`{c.get('cmd')}`{cwd_part})"
            md_lines.append(f"- {c.get('name')}: **{c.get('result')}**{suffix}")
            tt = c.get("tokenTelemetry")
            if isinstance(tt, dict) and c.get("result") != "skipped":
                md_lines.append(
                    f"  - tokenTelemetry: in={tt.get('inputTokens', 0)} out={tt.get('outputTokens', 0)} "
                    f"saved={tt.get('savedTokens', 0)} ({tt.get('savingsPct', 0.0)}%)"
                )
            full = c.get("fullOutputPath")
            if isinstance(full, str) and full:
                md_lines.append(f"  - full output: `{full}`")
        md_lines.append("")

    if invariant_findings:
        md_lines.append("## Invariant Findings")
        md_lines.append("")
        for f in invariant_findings[:50]:
            md_lines.append(f"- [{f.severity}] `{f.file}:{f.line}` {f.message} ({f.rule})")
        if len(invariant_findings) > 50:
            md_lines.append(f"- ... {len(invariant_findings) - 50} more")
        md_lines.append("")
    write_text(base / "VERIFICATION-CI.md", "\n".join(md_lines).strip() + "\n")

    # exit code: fail if any fail
    has_pkg_fail = any(c["result"] == "fail" for pkg in per_pkg for c in pkg.get("checks", []))
    return 1 if has_pkg_fail or inv["fail"] > 0 else 0


def _graph_impact_section(root: Path, changed_relpaths: set[str]) -> dict[str, Any]:
    """Compute blast-radius impact analysis via context graph.

    Returns a dict suitable for inclusion in REVIEW.json under 'impactAnalysis'.
    Gracefully degrades: returns {enabled: false, error: ...} on any failure.
    """
    try:
        import sys
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from scripts.context import ContextGraph

        graph = ContextGraph(repo_path=root)
        try:
            result = graph.review_impact(sorted(changed_relpaths))
            return {"enabled": True, **result}
        finally:
            graph.close()
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}


def write_review(
    root: Path,
    feature: str | None,
    per_pkg: list[dict[str, Any]],
    invariant_findings: list[InvariantFinding],
) -> int:
    ts = now_iso()
    branch = git_branch(root)
    agg = summarize_checksets(per_pkg)
    inv = summarize_invariants(invariant_findings)
    tokens = summarize_token_telemetry(per_pkg)

    verdict = "pass"
    if "fail" in agg.values() or inv["fail"] > 0:
        verdict = "fail"
    elif any(v == "skipped" for v in agg.values()) or inv["warn"] > 0:
        verdict = "warn"

    blockers = [
        {
            "file": f.file,
            "line": f.line,
            "issue": f.message,
            "severity": "high",
            "rule": f.rule,
        }
        for f in invariant_findings
        if f.severity == "fail"
    ]
    warnings = [
        {
            "file": f.file,
            "line": f.line,
            "issue": f.message,
            "severity": "medium",
            "rule": f.rule,
        }
        for f in invariant_findings
        if f.severity != "fail"
    ]

    contract = {
        "schemaVersion": REVIEW_SCHEMA_VERSION,
        "timestamp": ts,
        "feature": feature,
        "branch": branch,
        "automated": [
            {"name": "lint", "result": agg["lint"]},
            {"name": "types", "result": agg["typecheck"]},
            {"name": "tests", "result": agg["tests"]},
        ],
        "packages": per_pkg,
        "invariants": {
            "summary": inv,
            "findings": [
                {
                    "rule": f.rule,
                    "severity": f.severity,
                    "file": f.file,
                    "line": f.line,
                    "message": f.message,
                }
                for f in invariant_findings[:200]
            ],
        },
        "tokenTelemetry": tokens,
        "impactAnalysis": _graph_impact_section(root, _changed_relpaths(root)),
        "securityFindings": [],
        "performanceFindings": [],
        "patternCompliance": [],
        "stageReviews": [
            {
                "stage": "spec-compliance",
                "status": "pending",
                "findings": [],
                "evidence": [],
                "notes": "",
            },
            {
                "stage": "code-quality",
                "status": "pending",
                "findings": [],
                "evidence": [],
                "notes": "",
            },
        ],
        "principleNotes": [],
        "verdict": verdict,
        "blockers": blockers[:100],
        "warnings": warnings[:200],
    }

    if feature:
        out_base = root / "docs" / "planning" / "work" / "features" / feature
        write_json(out_base / "REVIEW.json", contract)
        md_path = out_base / "REVIEW.md"
    else:
        out_base = root / "docs" / "planning" / "work" / "review"
        write_json(out_base / f"{ts}-REVIEW.json", contract)
        md_path = out_base / f"{ts}-REVIEW.md"

    md_lines = [
        "# Review Report",
        "",
        f"**Timestamp:** {ts}",
        f"**Branch:** {branch or '[unknown]'}",
        f"**Feature:** {feature or '[none]'}",
        "",
        "## Automated Checks (Package-Aware)",
        "",
        f"- Lint: **{agg['lint']}**",
        f"- Types: **{agg['typecheck']}**",
        f"- Tests: **{agg['tests']}**",
        f"- Invariants: **{inv['fail']} fail / {inv['warn']} warn**",
        (
            f"- Token savings: **{tokens['savedTokens']} tokens** "
            f"({tokens['savingsPct']}%, {tokens['checksRun']} checks)"
        ),
        "",
        "## Per-Package Results",
        "",
    ]
    for pkg in per_pkg:
        md_lines.append(f"### {pkg['name']} (`{pkg['path']}`)")
        for c in pkg.get("checks", []):
            suffix = ""
            if c.get("cmd"):
                cwd = c.get("cwd")
                cwd_part = f", cwd `{cwd}`" if isinstance(cwd, str) and cwd else ""
                suffix = f" (`{c.get('cmd')}`{cwd_part})"
            md_lines.append(f"- {c.get('name')}: **{c.get('result')}**{suffix}")
            tt = c.get("tokenTelemetry")
            if isinstance(tt, dict) and c.get("result") != "skipped":
                md_lines.append(
                    f"  - tokenTelemetry: in={tt.get('inputTokens', 0)} out={tt.get('outputTokens', 0)} "
                    f"saved={tt.get('savedTokens', 0)} ({tt.get('savingsPct', 0.0)}%)"
                )
            full = c.get("fullOutputPath")
            if isinstance(full, str) and full:
                md_lines.append(f"  - full output: `{full}`")
        md_lines.append("")

    if invariant_findings:
        md_lines.append("## Invariant Findings")
        md_lines.append("")
        for f in invariant_findings[:100]:
            md_lines.append(f"- [{f.severity}] `{f.file}:{f.line}` {f.message} ({f.rule})")
        if len(invariant_findings) > 100:
            md_lines.append(f"- ... {len(invariant_findings) - 100} more")
        md_lines.append("")
    md_lines.append(f"## Verdict\n\n**{verdict.upper()}**\n")

    md_lines.append("## Manual Review")
    md_lines.append("")
    md_lines.append("> Review criteria: see `.claude/skills/code-review.md`")
    md_lines.append(">")
    md_lines.append("> Fill stage reviews in order: `stageReviews[0]=spec-compliance`, then `stageReviews[1]=code-quality`.")
    md_lines.append(">")
    md_lines.append("> Fill `securityFindings[]`, `performanceFindings[]`, `patternCompliance[]` in REVIEW.json.")
    md_lines.append("")

    write_text(md_path, "\n".join(md_lines).strip() + "\n")

    return 1 if verdict == "fail" else 0


def _parse_iso_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    val = raw.strip()
    if val.endswith("Z"):
        val = val[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(val)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _latest_summary_timestamp(feature_dir: Path) -> datetime | None:
    latest: datetime | None = None
    for summary_json in sorted(feature_dir.glob("*-SUMMARY.json")):
        ts: datetime | None = None
        try:
            payload = load_json(summary_json)
            if isinstance(payload, dict):
                ts = _parse_iso_ts(payload.get("timestamp"))
        except Exception:
            ts = None
        if ts is None:
            try:
                ts = datetime.fromtimestamp(summary_json.stat().st_mtime, tz=timezone.utc)
            except OSError:
                ts = None
        if ts is not None and (latest is None or ts > latest):
            latest = ts
    return latest


def _enforcement_level(wf: dict[str, Any], key: str, default: str = "error") -> str:
    enforcement = wf.get("enforcement")
    if not isinstance(enforcement, dict):
        return default
    level = enforcement.get(key, default)
    if level not in {"off", "warn", "error"}:
        return default
    return level


def _cmd_ship_ready(root: Path, feature: str, *, json_output: bool = False) -> int:
    feature_dir = root / "docs" / "planning" / "work" / "features" / feature
    wf = load_workflow(root)
    two_stage_level = _enforcement_level(wf, "twoStageReview", default="error")
    verify_level = _enforcement_level(wf, "verificationBeforeCompletion", default="error")
    checks: list[dict[str, str]] = []

    def add_check(name: str, ok: bool, details: str, level: str = "error") -> None:
        if ok:
            checks.append({"name": name, "status": "pass", "details": "ok"})
            return
        if level == "off":
            checks.append({"name": name, "status": "pass", "details": f"{details} (policy off)"})
            return
        status = "fail" if level == "error" else "warn"
        checks.append({"name": name, "status": status, "details": details})

    add_check(
        "feature_dir_exists",
        feature_dir.is_dir(),
        f"Feature directory not found: {feature_dir}",
        "error",
    )
    if not feature_dir.is_dir():
        if json_output:
            print(json.dumps({"feature": feature, "checks": checks}, indent=2))
        else:
            print(f"ship-ready: feature directory not found for `{feature}`")
        return 1

    # Phase check (advisory — warn only, never blocks)
    try:
        phase_result = subprocess.run(
            ["python3", ".cnogo/scripts/workflow_memory.py", "phase-get", feature],
            capture_output=True, text=True, timeout=10, cwd=str(root),
        )
        phase_line = phase_result.stdout.strip()
        current_phase = phase_line.split(":")[-1].strip() if ":" in phase_line else ""
        phase_ok = current_phase in ("review", "ship")
        add_check(
            "phase_check",
            phase_ok,
            f"Feature phase is '{current_phase}'; expected 'review' or 'ship'.",
            "warn",
        )
    except Exception:
        # Memory not initialized or subprocess failed — skip silently
        checks.append({"name": "phase_check", "status": "pass", "details": "skipped (memory unavailable)"})

    review_json = feature_dir / "REVIEW.json"
    add_check("review_contract_exists", review_json.exists(), "Missing REVIEW.json contract.", "error")
    if not review_json.exists():
        if json_output:
            print(json.dumps({"feature": feature, "checks": checks}, indent=2))
        else:
            print(f"ship-ready: missing REVIEW.json for `{feature}`")
        return 1

    review_data: dict[str, Any] = {}
    try:
        parsed = load_json(review_json)
        if isinstance(parsed, dict):
            review_data = parsed
        else:
            raise ValueError("REVIEW.json is not a JSON object.")
    except Exception as exc:
        checks.append({"name": "review_contract_parse", "status": "fail", "details": str(exc)})
        if json_output:
            print(json.dumps({"feature": feature, "checks": checks}, indent=2))
        else:
            print(f"ship-ready: invalid REVIEW.json: {exc}")
        return 1

    schema_version = review_data.get("schemaVersion")
    add_check(
        "review_schema_v4",
        isinstance(schema_version, int) and not isinstance(schema_version, bool) and schema_version >= 4,
        "REVIEW.json schemaVersion must be >=4 for staged review enforcement.",
        two_stage_level,
    )

    stage_reviews = review_data.get("stageReviews")
    expected_stages = ["spec-compliance", "code-quality"]
    stages_ok = isinstance(stage_reviews, list) and len(stage_reviews) >= 2
    add_check(
        "stage_reviews_present",
        stages_ok,
        "REVIEW.json must include stageReviews[spec-compliance, code-quality].",
        two_stage_level,
    )

    if stages_ok and isinstance(stage_reviews, list):
        order_ok = True
        completion_ok = True
        evidence_ok = True
        no_failed_stage = True
        for idx, expected in enumerate(expected_stages):
            item = stage_reviews[idx]
            if not isinstance(item, dict):
                order_ok = False
                completion_ok = False
                evidence_ok = False
                no_failed_stage = False
                continue
            if item.get("stage") != expected:
                order_ok = False
            status = item.get("status")
            if status not in {"pass", "warn", "fail"}:
                completion_ok = False
                no_failed_stage = False
            elif status == "fail":
                no_failed_stage = False
            evidence = item.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                evidence_ok = False
        add_check(
            "stage_review_order",
            order_ok,
            "stageReviews must be ordered as spec-compliance then code-quality.",
            two_stage_level,
        )
        add_check(
            "stage_review_complete",
            completion_ok,
            "Both stage reviews must be completed with status pass|warn|fail before ship.",
            two_stage_level,
        )
        add_check(
            "stage_review_no_fail",
            no_failed_stage,
            "Stage review status cannot be fail before ship; resolve blockers or downgrade to warn with rationale.",
            two_stage_level,
        )
        add_check(
            "stage_review_evidence",
            evidence_ok,
            "Each completed stage review must include non-empty evidence entries.",
            verify_level,
        )

    review_ts = _parse_iso_ts(review_data.get("timestamp"))
    latest_summary_ts = _latest_summary_timestamp(feature_dir)
    freshness_ok = (
        review_ts is not None
        and latest_summary_ts is not None
        and review_ts >= latest_summary_ts
    )
    add_check(
        "fresh_review_after_latest_summary",
        freshness_ok,
        "REVIEW.json timestamp must be at/after latest SUMMARY.json timestamp.",
        verify_level,
    )

    has_fail = any(c["status"] == "fail" for c in checks)
    if json_output:
        print(json.dumps({"feature": feature, "checks": checks}, indent=2))
    else:
        icons = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
        print(f"ship-ready checks for `{feature}`")
        for check in checks:
            icon = icons.get(check["status"], "?")
            print(f"  {icon} {check['name']}: {check['details']}")
    return 1 if has_fail else 0


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "cleanup"


def _entropy_candidates(
    findings: list[InvariantFinding],
    *,
    max_files_per_task: int,
    max_tasks: int,
) -> list[dict[str, Any]]:
    by_file: dict[str, list[InvariantFinding]] = {}
    for f in findings:
        by_file.setdefault(f.file, []).append(f)

    def score(item: tuple[str, list[InvariantFinding]]) -> tuple[int, int, str]:
        file, fs = item
        fail_count = sum(1 for f in fs if f.severity == "fail")
        return (-fail_count, -len(fs), file)

    ordered_files = [f for f, _ in sorted(by_file.items(), key=score)]
    chunks: list[list[str]] = []
    current: list[str] = []
    for fp in ordered_files:
        current.append(fp)
        if len(current) >= max_files_per_task:
            chunks.append(current)
            current = []
        if len(chunks) >= max_tasks:
            break
    if current and len(chunks) < max_tasks:
        chunks.append(current)

    tasks: list[dict[str, Any]] = []
    for idx, files in enumerate(chunks, start=1):
        task_findings = [f for f in findings if f.file in files]
        rules = sorted({f.rule for f in task_findings})
        tasks.append(
            {
                "name": f"Entropy cleanup #{idx}",
                "files": files,
                "rules": rules,
                "findingCount": len(task_findings),
                "action": (
                    "Apply tiny non-behavioral refactors for listed files only. "
                    "Keep each PR scoped and verify checks pass."
                ),
            }
        )
    return tasks


def write_entropy_task(
    root: Path,
    findings: list[InvariantFinding],
    *,
    max_files_per_task: int,
    max_tasks: int,
) -> Path:
    task_dir = root / "docs" / "planning" / "work" / "background"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    task_path = task_dir / f"{task_id}-entropy-cleanup-TASK.md"
    candidates = _entropy_candidates(
        findings,
        max_files_per_task=max_files_per_task,
        max_tasks=max_tasks,
    )

    lines = [
        f"# Background Task: {task_id}",
        "",
        "## Request",
        "Continuous entropy cleanup: open tiny refactor PR(s) for invariant drift/slop patterns.",
        "",
        "## Status",
        "🕒 Queued",
        "",
        "## Started",
        now_iso(),
        "",
        "## Constraints",
        f"- Max files per cleanup task: {max_files_per_task}",
        f"- Max tasks this run: {max_tasks}",
        "- Non-behavioral refactors only",
        "- Keep commits/PRs small and focused",
        "",
        "## Candidate Tasks",
        "",
    ]
    if not candidates:
        lines.extend(["- No candidates found.", ""])
    else:
        for t in candidates:
            lines.append(f"### {t['name']}")
            lines.append(f"- Files: {', '.join(f'`{f}`' for f in t['files'])}")
            lines.append(f"- Rules: {', '.join(f'`{r}`' for r in t['rules']) if t['rules'] else '[none]'}")
            lines.append(f"- Findings: {t['findingCount']}")
            lines.append(f"- Action: {t['action']}")
            lines.append("")

    lines.extend(
        [
            "## Log",
            "- Generated by `python3 .cnogo/scripts/workflow_checks.py entropy --write-task`",
            "",
        ]
    )
    write_text(task_path, "\n".join(lines))
    return task_path


def _autobootstrap_packages_if_empty(
    root: Path,
    wf: dict[str, Any],
    *,
    cmd: str,
    timeout_sec: int,
) -> dict[str, Any]:
    """Auto-populate WORKFLOW packages[] for review/verify-ci when empty."""
    if cmd not in {"review", "verify-ci"}:
        return wf
    if packages_from_workflow(wf):
        return wf
    detect_script = root / ".cnogo" / "scripts" / "workflow_detect.py"
    if not detect_script.exists():
        return wf

    print("⚠️  No packages configured; attempting auto-detect via workflow_detect.py ...")
    detect_timeout = max(20, min(timeout_sec, 120))
    rc, out = run_shell(
        "python3 .cnogo/scripts/workflow_detect.py --write-workflow",
        cwd=root,
        timeout_sec=detect_timeout,
    )
    if rc != 0:
        tail = "\n".join(line for line in out.splitlines()[-3:] if line.strip())
        print("⚠️  Auto-detect failed; continuing with existing WORKFLOW.json.")
        if tail:
            print(tail)
        return wf

    refreshed = load_workflow(root)
    refreshed_pkgs = packages_from_workflow(refreshed)
    if refreshed_pkgs:
        print(f"✅ Detected {len(refreshed_pkgs)} package(s) and updated WORKFLOW.json.")
        return refreshed
    print("⚠️  Auto-detect ran, but packages[] is still empty.")
    return refreshed


def _cmd_doctor(root: Path, wf: dict, json_output: bool = False) -> int:
    """Run 6 diagnostic checks and report pass/warn/fail."""
    import sqlite3
    checks = []

    # Check 1: Workflow validation
    try:
        result = subprocess.run(
            [sys.executable, ".cnogo/scripts/workflow_validate.py", "--json"],
            capture_output=True, text=True, timeout=30, cwd=str(root)
        )
        if result.returncode == 0:
            checks.append({"name": "workflow_validation", "status": "pass", "details": "WORKFLOW.json and contracts valid"})
        else:
            details = result.stdout.strip()[:200] or result.stderr.strip()[:200] or "Validation failed"
            checks.append({"name": "workflow_validation", "status": "fail", "details": details})
    except Exception as exc:
        checks.append({"name": "workflow_validation", "status": "fail", "details": str(exc)[:200]})

    # Check 2: Memory DB integrity
    db_path = root / ".cnogo" / "memory.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            if result and result[0] == "ok":
                checks.append({"name": "memory_db_integrity", "status": "pass", "details": "PRAGMA integrity_check: ok"})
            else:
                checks.append({"name": "memory_db_integrity", "status": "fail", "details": f"integrity_check: {result[0] if result else 'no result'}"})
        except Exception as exc:
            checks.append({"name": "memory_db_integrity", "status": "fail", "details": str(exc)[:200]})
    else:
        checks.append({"name": "memory_db_integrity", "status": "warn", "details": "memory.db not found (not initialized)"})

    # Check 3: Orphaned worktrees
    try:
        wt_result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=10, cwd=str(root)
        )
        session_file = root / ".cnogo" / "worktree-session.json"
        tracked_paths = set()
        if session_file.exists():
            import json as _json
            with open(session_file) as f:
                session_data = _json.load(f)
            for wt in session_data.get("worktrees", []):
                tracked_paths.add(wt.get("path", ""))

        # Parse porcelain output
        worktree_paths = []
        for line in wt_result.stdout.splitlines():
            if line.startswith("worktree "):
                wp = line[len("worktree "):]
                # Skip the main worktree
                if wp != str(root):
                    worktree_paths.append(wp)

        orphaned = [p for p in worktree_paths if p not in tracked_paths]
        if orphaned:
            checks.append({"name": "orphaned_worktrees", "status": "warn", "details": f"{len(orphaned)} orphaned worktree(s): {', '.join(orphaned[:3])}"})
        else:
            checks.append({"name": "orphaned_worktrees", "status": "pass", "details": f"No orphaned worktrees ({len(worktree_paths)} tracked)"})
    except Exception as exc:
        checks.append({"name": "orphaned_worktrees", "status": "warn", "details": str(exc)[:200]})

    # Check 4: Stale issues
    try:
        import sys as _sys
        _repo = str(root)
        if _repo not in _sys.path:
            _sys.path.insert(0, _repo)
        from scripts.memory.watchdog import check_stale_issues
        stale = check_stale_issues(root)
        if stale:
            titles = [s.get("title", s.get("id", "?"))[:40] for s in stale[:3]]
            checks.append({"name": "stale_issues", "status": "warn", "details": f"{len(stale)} stale issue(s): {', '.join(titles)}"})
        else:
            checks.append({"name": "stale_issues", "status": "pass", "details": "No stale issues found"})
    except Exception as exc:
        checks.append({"name": "stale_issues", "status": "warn", "details": f"Could not check: {exc}"})

    # Check 5: Hook config sanity
    settings_path = root / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            import json as _json
            with open(settings_path) as f:
                settings = _json.load(f)
            hooks = settings.get("hooks", {})
            missing_scripts = []
            for hook_name, hook_entries in hooks.items():
                if isinstance(hook_entries, list):
                    for entry in hook_entries:
                        cmd = entry.get("command", "") if isinstance(entry, dict) else ""
                        # Extract script path from command (first arg after bash/python3)
                        parts = cmd.split()
                        for part in parts:
                            if part.endswith((".sh", ".py")) and not part.startswith("-"):
                                script_path = root / part
                                if not script_path.exists():
                                    missing_scripts.append(part)
            if missing_scripts:
                checks.append({"name": "hook_config", "status": "warn", "details": f"Missing hook scripts: {', '.join(missing_scripts[:3])}"})
            else:
                checks.append({"name": "hook_config", "status": "pass", "details": "All hook script paths valid"})
        except Exception as exc:
            checks.append({"name": "hook_config", "status": "fail", "details": str(exc)[:200]})
    else:
        checks.append({"name": "hook_config", "status": "warn", "details": ".claude/settings.json not found"})

    # Check 6: Git state
    git_issues = []
    try:
        rc_status, out_status = run_shell("git status --porcelain", cwd=root, timeout_sec=10)
        if rc_status == 0 and out_status.strip():
            git_issues.append("dirty working tree (uncommitted changes)")
    except Exception as exc:
        git_issues.append(f"could not check working tree: {exc}")

    try:
        rc_head, out_head = run_shell("git symbolic-ref HEAD", cwd=root, timeout_sec=10)
        if rc_head != 0:
            git_issues.append("detached HEAD")
    except Exception as exc:
        git_issues.append(f"could not check HEAD: {exc}")

    try:
        rc_merged, out_merged = run_shell("git branch --merged main", cwd=root, timeout_sec=10)
        if rc_merged == 0:
            stale_branches = [
                b.strip().lstrip("* ")
                for b in out_merged.splitlines()
                if b.strip() and b.strip().lstrip("* ") not in {"main", "master", ""}
            ]
            if len(stale_branches) > 3:
                git_issues.append(f"{len(stale_branches)} stale merged branches (exclude main)")
    except Exception as exc:
        git_issues.append(f"could not check merged branches: {exc}")

    if git_issues:
        checks.append({"name": "git_state", "status": "warn", "details": "; ".join(git_issues)})
    else:
        checks.append({"name": "git_state", "status": "pass", "details": "clean working tree, no detached HEAD, merged branches ok"})

    # Output
    has_fail = any(c["status"] == "fail" for c in checks)

    if json_output:
        print(json.dumps({"checks": checks}, indent=2))
    else:
        status_icons = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
        print("cnogo doctor — diagnostic checks\n")
        for c in checks:
            icon = status_icons.get(c["status"], "?")
            print(f"  {icon} {c['name']}: {c['details']}")
        print()
        if has_fail:
            print("Some checks failed. Run with --json for machine-readable output.")
        else:
            print("All checks passed.")

    return 1 if has_fail else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run package-aware workflow checks.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("verify-ci", help="Run CI verification checks and write VERIFICATION-CI artifacts.")
    v.add_argument("feature", help="Feature slug (docs/planning/work/features/<feature>/)")

    r = sub.add_parser("review", help="Run review checks and write REVIEW artifacts.")
    r.add_argument("--feature", help="Feature slug (overrides memory inference).")

    sr = sub.add_parser(
        "ship-ready",
        help="Validate staged review completion and evidence freshness before /ship.",
    )
    sr.add_argument("--feature", required=True, help="Feature slug (docs/planning/work/features/<feature>/)")
    sr.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON.")

    e = sub.add_parser(
        "entropy",
        help="Run invariant scan and optionally write a background entropy-cleanup task.",
    )
    e.add_argument("--write-task", action="store_true", help="Write docs/planning/work/background/*-entropy-cleanup-TASK.md")
    e.add_argument("--max-files", type=int, help="Override max files per entropy cleanup task.")
    e.add_argument("--max-tasks", type=int, help="Override max cleanup tasks generated per run.")

    d = sub.add_parser(
        "discover",
        help="Analyze command usage telemetry for missed token-savings opportunities.",
    )
    d.add_argument("--since-days", type=int, default=DEFAULT_COMMAND_USAGE_SINCE_DAYS, help="Telemetry lookback window in days.")
    d.add_argument("--limit", type=int, default=10, help="Max rows per section.")
    d.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")

    doc = sub.add_parser("doctor", help="Run diagnostic health checks on the workflow environment.")
    doc.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON.")

    args = parser.parse_args()
    root = repo_root()
    wf = load_workflow(root)
    wf = _autobootstrap_packages_if_empty(
        root,
        wf,
        cmd=args.cmd,
        timeout_sec=DEFAULT_COMMAND_TIMEOUT_SEC,
    )
    checks_cfg = _checks_runtime_cfg(wf)
    check_scope_cfg = str(checks_cfg.get("checkScope", "auto"))
    ci_env = os.getenv("CI", "").strip().lower()
    in_ci = ci_env not in {"", "0", "false", "no"}
    if check_scope_cfg == "all":
        effective_check_scope = "all"
    elif check_scope_cfg == "changed":
        effective_check_scope = "changed"
    else:
        effective_check_scope = "all" if in_ci else "changed"

    changed_files_fallback = str(checks_cfg.get("changedFilesFallback", "none"))
    command_timeout_sec = int(checks_cfg.get("commandTimeoutSec", DEFAULT_COMMAND_TIMEOUT_SEC))
    output_compaction = checks_cfg.get("outputCompaction") if isinstance(checks_cfg.get("outputCompaction"), dict) else {}
    output_recovery = checks_cfg.get("outputRecovery") if isinstance(checks_cfg.get("outputRecovery"), dict) else {}
    token_telemetry_cfg = checks_cfg.get("tokenTelemetry") if isinstance(checks_cfg.get("tokenTelemetry"), dict) else {}
    token_telemetry_enabled = bool(token_telemetry_cfg.get("enabled", True))
    hook_opt_cfg = checks_cfg.get("hookOptimization") if isinstance(checks_cfg.get("hookOptimization"), dict) else {}
    feature_for_scope: str | None = None
    if args.cmd == "verify-ci":
        feature_for_scope = args.feature
    elif args.cmd == "review":
        feature_for_scope = args.feature or infer_feature_from_state(root)

    if args.cmd == "discover":
        report = _discover_command_usage(
            root,
            log_file=str(hook_opt_cfg.get("logFile", ".cnogo/command-usage.jsonl")),
            since_days=max(0, int(args.since_days)),
            limit=max(1, int(args.limit)),
        )
        if args.format == "json":
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            _print_discover_text(report)
        return 0

    if args.cmd == "doctor":
        return _cmd_doctor(root, wf, json_output=getattr(args, 'json_output', False))

    if args.cmd == "ship-ready":
        return _cmd_ship_ready(
            root,
            args.feature,
            json_output=getattr(args, "json_output", False),
        )

    invariant_findings = run_invariant_checks(
        root,
        wf,
        changed_files_fallback=changed_files_fallback,
    )

    if args.cmd == "entropy":
        ecfg = _entropy_cfg(wf)
        if not ecfg.get("enabled", True):
            print("Entropy cleanup is disabled in WORKFLOW.json (entropy.enabled=false).")
            return 0
        max_files = args.max_files if isinstance(args.max_files, int) and args.max_files > 0 else int(ecfg.get("maxFilesPerTask", 3))
        max_tasks = args.max_tasks if isinstance(args.max_tasks, int) and args.max_tasks > 0 else int(ecfg.get("maxTasksPerRun", 3))
        summary = summarize_invariants(invariant_findings)
        print(
            json.dumps(
                {
                    "invariants": summary,
                    "candidates": _entropy_candidates(
                        invariant_findings,
                        max_files_per_task=max_files,
                        max_tasks=max_tasks,
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
        if args.write_task:
            task_path = write_entropy_task(
                root,
                invariant_findings,
                max_files_per_task=max_files,
                max_tasks=max_tasks,
            )
            print(f"Wrote entropy background task: {task_path}")
        return 1 if summary["fail"] > 0 else 0

    pkgs = packages_from_workflow(wf)
    if not pkgs:
        print("⚠️ No packages configured in docs/planning/WORKFLOW.json (packages[]).")
        print("Proceeding with empty package set; checks will be recorded as skipped.")
        print("Optional setup: python3 .cnogo/scripts/workflow_detect.py --write-workflow")
        per_pkg: list[dict[str, Any]] = []
    else:
        changed_relpaths: set[str] | None = None
        if effective_check_scope == "changed":
            changed_relpaths = _changed_relpaths(root, fallback=changed_files_fallback)
        elif in_ci and (feature_for_scope or args.cmd == "review"):
            scoped = _changed_relpaths_against_base(root)
            if not scoped and changed_files_fallback != "none":
                scoped = _changed_relpaths(root, fallback=changed_files_fallback)
            if scoped:
                changed_relpaths = scoped
                scope_label = feature_for_scope or "review"
                print(
                    "CI feature-scoped package checks: "
                    f"{len(scoped)} changed file(s) against base for `{scope_label}`."
                )
            else:
                print("CI feature-scoped package checks unavailable; running all packages.")

        if effective_check_scope == "changed" and not changed_relpaths:
            print("No local changes detected; package checks skipped (checkScope=changed).")
        per_pkg = run_package_checks(
            root,
            pkgs,
            changed_relpaths=changed_relpaths,
            timeout_sec=command_timeout_sec,
            output_compaction=output_compaction,
            output_recovery=output_recovery,
            token_telemetry_enabled=token_telemetry_enabled,
        )

    if args.cmd == "verify-ci":
        return write_verify_ci(root, args.feature, per_pkg, invariant_findings)

    if args.cmd == "review":
        return write_review(root, feature_for_scope, per_pkg, invariant_findings)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
