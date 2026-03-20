#!/usr/bin/env python3
"""
Workflow hooks runner to reduce latency.

Used by .claude/settings.json hooks:
- PreToolUse (Bash): token optimization telemetry + compact command suggestions
- PostToolUse (Write|Edit): format only edited files when possible
No external dependencies.
"""

from __future__ import annotations

try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass  # imported as module; caller manages sys.path

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from workflow_utils import load_workflow, repo_root


def _iter_possible_paths(obj: Any) -> Iterable[str]:
    """
    Heuristically extract file paths from CLAUDE_TOOL_INPUT. Claude Code tool input is typically JSON-ish.
    We try a few known key names and also fall back to scanning for strings that look like paths.
    """
    if obj is None:
        return
    if isinstance(obj, dict):
        for k in ["target_file", "path", "file", "filename"]:
            v = obj.get(k)
            if isinstance(v, str):
                yield v
        # Recurse into dict values
        for v in obj.values():
            yield from _iter_possible_paths(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _iter_possible_paths(it)
    elif isinstance(obj, str):
        # Sometimes the whole input is a string path
        yield obj


PATH_LIKE_RE = re.compile(r"""(?x)
(
  (?:\./|/)?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+
)
""")


_TEST_CMD_RE = re.compile(
    r"(^|[\s;&|])(pytest|python3 -m pytest|cargo test|go test|npm test|pnpm test|yarn test|mvn test|\./gradlew test)([\s;&|]|$)"
)
_GIT_STATUS_COMPACT_RE = re.compile(r"git status\s+.*(--short|--porcelain)")
_GIT_DIFF_COMPACT_RE = re.compile(r"git diff\s+.*(--name-only|--stat)")
_LIST_COMPACT_RE = re.compile(r"(rg --files|find\s+\.\s+-type\s+f)")
_INLINE_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"-----BEGIN\s+[\w\s]+PRIVATE\s+KEY-----"),
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),
]
_FLAG_SECRET_RE = re.compile(
    r"(?i)(--?(?:password|pass|token|secret|apikey|api-key)\s+)(\S+)"
)
_KV_SECRET_RE = re.compile(
    r"(?i)((?:password|pass|token|secret|apikey|api[-_]?key)=)([^\s]+)"
)
_COMMAND_KEYS = ("command", "cmd", "shell_command", "bash_command", "input", "text")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _hook_optimization_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "enabled": True,
        "mode": "suggest",  # suggest|enforce|off
        "showSuggestions": True,
        "logFile": ".cnogo/command-usage.jsonl",
    }
    perf = cfg.get("performance")
    if not isinstance(perf, dict):
        return defaults
    raw = perf.get("hookOptimization")
    if not isinstance(raw, dict):
        return defaults

    out = dict(defaults)
    enabled = raw.get("enabled")
    if isinstance(enabled, bool):
        out["enabled"] = enabled
    mode = raw.get("mode")
    if mode in {"suggest", "enforce", "off"}:
        out["mode"] = mode
    show = raw.get("showSuggestions")
    if isinstance(show, bool):
        out["showSuggestions"] = show
    log_file = raw.get("logFile")
    if isinstance(log_file, str) and log_file.strip():
        out["logFile"] = log_file.strip()
    return out


def _command_log_path(root: Path, cfg: dict[str, Any]) -> Path:
    raw = str(cfg.get("logFile") or ".cnogo/command-usage.jsonl")
    p = Path(raw)
    return p if p.is_absolute() else (root / p)


def _normalize_cmd(raw: str) -> str:
    return " ".join(raw.strip().split())


def _extract_bash_command(raw_input: str) -> str:
    raw = raw_input.strip()
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except Exception:
        return raw
    if isinstance(payload, str):
        return payload.strip() or raw

    def pick(obj: Any) -> str:
        if isinstance(obj, dict):
            for key in _COMMAND_KEYS:
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

    extracted = pick(payload)
    return extracted if extracted else raw


def _redact_for_log(command: str) -> str:
    out = command
    for pattern in _INLINE_SECRET_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    out = _FLAG_SECRET_RE.sub(r"\1[REDACTED]", out)
    out = _KV_SECRET_RE.sub(r"\1[REDACTED]", out)
    return out


def _classify_command(command: str) -> dict[str, Any]:
    normalized = _normalize_cmd(command)
    lower = normalized.lower()

    # Already using compact cnogo-first paths.
    if lower.startswith("python3 .cnogo/scripts/workflow_checks.py review") or lower.startswith(
        "python3 .cnogo/scripts/workflow_checks.py verify-ci"
    ):
        return {
            "status": "optimized",
            "category": "workflow-checks",
            "suggestion": "",
            "estimatedSavingsPct": 0,
            "estimatedRawTokens": 0,
            "estimatedSaveableTokens": 0,
        }

    if lower.startswith("python3 .cnogo/scripts/workflow_memory.py prime") or lower.startswith(
        "python3 .cnogo/scripts/workflow_memory.py checkpoint"
    ):
        return {
            "status": "optimized",
            "category": "memory-context",
            "suggestion": "",
            "estimatedSavingsPct": 0,
            "estimatedRawTokens": 0,
            "estimatedSaveableTokens": 0,
        }

    if lower.startswith("git status") and _GIT_STATUS_COMPACT_RE.search(lower):
        return {
            "status": "optimized",
            "category": "git-status",
            "suggestion": "",
            "estimatedSavingsPct": 0,
            "estimatedRawTokens": 0,
            "estimatedSaveableTokens": 0,
        }

    if lower.startswith("git diff") and _GIT_DIFF_COMPACT_RE.search(lower):
        return {
            "status": "optimized",
            "category": "git-diff",
            "suggestion": "",
            "estimatedSavingsPct": 0,
            "estimatedRawTokens": 0,
            "estimatedSaveableTokens": 0,
        }

    if lower.startswith("ls") and _LIST_COMPACT_RE.search(lower):
        return {
            "status": "optimized",
            "category": "listing",
            "suggestion": "",
            "estimatedSavingsPct": 0,
            "estimatedRawTokens": 0,
            "estimatedSaveableTokens": 0,
        }

    # Missed compact path opportunities.
    if _TEST_CMD_RE.search(lower):
        pct = 82
        raw_tokens = 900
        saveable = int(raw_tokens * pct / 100)
        return {
            "status": "missed",
            "category": "tests",
            "suggestion": "python3 .cnogo/scripts/workflow_checks.py verify-ci <feature>",
            "estimatedSavingsPct": pct,
            "estimatedRawTokens": raw_tokens,
            "estimatedSaveableTokens": saveable,
        }

    if lower.startswith("git status") and not _GIT_STATUS_COMPACT_RE.search(lower):
        pct = 70
        raw_tokens = 120
        saveable = int(raw_tokens * pct / 100)
        return {
            "status": "missed",
            "category": "git-status",
            "suggestion": "git status --porcelain",
            "estimatedSavingsPct": pct,
            "estimatedRawTokens": raw_tokens,
            "estimatedSaveableTokens": saveable,
        }

    if lower.startswith("git diff") and not _GIT_DIFF_COMPACT_RE.search(lower):
        pct = 68
        raw_tokens = 360
        saveable = int(raw_tokens * pct / 100)
        return {
            "status": "missed",
            "category": "git-diff",
            "suggestion": "git diff --name-only",
            "estimatedSavingsPct": pct,
            "estimatedRawTokens": raw_tokens,
            "estimatedSaveableTokens": saveable,
        }

    if lower.startswith("ls") and not _LIST_COMPACT_RE.search(lower):
        pct = 62
        raw_tokens = 180
        saveable = int(raw_tokens * pct / 100)
        return {
            "status": "missed",
            "category": "listing",
            "suggestion": "rg --files | head -n 200",
            "estimatedSavingsPct": pct,
            "estimatedRawTokens": raw_tokens,
            "estimatedSaveableTokens": saveable,
        }

    return {
        "status": "neutral",
        "category": "other",
        "suggestion": "",
        "estimatedSavingsPct": 0,
        "estimatedRawTokens": 0,
        "estimatedSaveableTokens": 0,
    }


_MAX_LOG_BYTES = 512 * 1024  # 512KB max before rotation


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Rotate if log file exceeds limit to prevent unbounded growth.
    try:
        if path.exists() and path.stat().st_size > _MAX_LOG_BYTES:
            rotated = path.with_suffix(".jsonl.old")
            path.rename(rotated)
    except OSError:
        pass
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def pre_bash() -> int:
    raw_input = os.environ.get("CLAUDE_TOOL_INPUT", "").strip()
    if not raw_input:
        return 0

    # Fast exit: skip heavy processing for very large inputs (>64KB).
    # Prevents hangs when context compaction produces large tool payloads.
    if len(raw_input) > 65536:
        return 0

    try:
        command = _extract_bash_command(raw_input)
        if not command:
            return 0
        root = repo_root()
        wf = load_workflow(root)
        cfg = _hook_optimization_cfg(wf)
        if not cfg.get("enabled", True) or cfg.get("mode") == "off":
            return 0

        classification = _classify_command(command)
        safe_cmd = _redact_for_log(_normalize_cmd(command))
        payload = {
            "timestamp": _now_iso(),
            "command": safe_cmd,
            **classification,
            "source": "pre_bash_hook",
        }
        _append_jsonl(_command_log_path(root, cfg), payload)

        if classification.get("status") == "missed":
            suggestion = str(classification.get("suggestion") or "").strip()
            if cfg.get("showSuggestions", True) and suggestion:
                print(
                    f"Token hint: prefer `{suggestion}` (est. -{classification.get('estimatedSavingsPct', 0)}%).",
                    file=sys.stderr,
                )
            if cfg.get("mode") == "enforce":
                print(
                    "Blocked by token-optimization policy. Use the suggested compact command.",
                    file=sys.stderr,
                )
                return 2
        return 0
    except Exception as exc:
        # Never block work on hook telemetry/suggestion failure.
        print(f"[cnogo] Hook error (non-blocking): {exc}", file=sys.stderr)
        return 0


def extract_edited_files(raw_input: str, root: Path) -> list[Path]:
    candidates: set[Path] = set()
    raw_input = raw_input.strip()
    if not raw_input:
        return []

    # Attempt JSON parse first
    parsed: Any = None
    try:
        parsed = json.loads(raw_input)
    except Exception:
        parsed = None

    if parsed is not None:
        for s in _iter_possible_paths(parsed):
            s = s.strip()
            if not s:
                continue
            p = Path(s)
            if not p.is_absolute():
                p = (root / p).resolve()
            candidates.add(p)

    # Fallback: regex scan for path-like strings
    for m in PATH_LIKE_RE.finditer(raw_input):
        s = m.group(1)
        if not s:
            continue
        p = Path(s)
        if not p.is_absolute():
            p = (root / p).resolve()
        candidates.add(p)

    # Filter to files within repo
    filtered: list[Path] = []
    root_res = root.resolve()
    for p in candidates:
        try:
            pr = p.resolve()
            if root_res in pr.parents or pr == root_res:
                if pr.is_file():
                    filtered.append(pr)
        except Exception:
            continue
    return sorted(set(filtered))


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(cmd: list[str], *, cwd: Path) -> int:
    try:
        subprocess.check_call(cmd, cwd=cwd)
        return 0
    except subprocess.CalledProcessError as e:
        return int(e.returncode or 1)
    except Exception:
        return 1


def post_edit() -> int:
    raw = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if not raw.strip():
        return 0

    root = repo_root()
    cfg = load_workflow()
    perf = cfg.get("performance") if isinstance(cfg.get("performance"), dict) else {}
    enabled = perf.get("postEditFormat", "auto")
    scope = perf.get("postEditFormatScope", "changed")

    if enabled in {"off", False, "false"}:
        return 0
    edited = extract_edited_files(raw, root)

    # If we couldn't identify files, fall back (auto) to repo-wide formatter command.
    if not edited or scope == "repo":
        return run_repo_formatters(root)

    return run_changed_formatters(root, edited)


def run_repo_formatters(root: Path) -> int:
    # Mirror the old behavior, but keep it best-effort and fast.
    # Prefer a project-provided formatter if it exists.
    if (root / "pom.xml").exists():
        return run(["mvn", "spotless:apply", "-q"], cwd=root)
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        return run(["./gradlew", "spotlessApply", "-q"], cwd=root)
    if (root / "package.json").exists():
        # Only run npm format when the script exists; otherwise best-effort no-op.
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
            if isinstance(scripts, dict):
                fmt = scripts.get("format")
                if isinstance(fmt, str) and fmt.strip():
                    return run(["npm", "run", "format", "--silent"], cwd=root)
        except Exception:
            pass
        return 0
    if (root / "pyproject.toml").exists():
        rc1 = run(["python3", "-m", "black", ".", "-q"], cwd=root) if which("black") else 0
        rc2 = run(["python3", "-m", "isort", ".", "-q"], cwd=root) if which("isort") else 0
        return 0 if (rc1 == 0 and rc2 == 0) else 1
    if (root / "setup.py").exists():
        return run(["python3", "-m", "black", ".", "-q"], cwd=root) if which("black") else 0
    if (root / "go.mod").exists():
        # repo-wide gofmt is expensive; avoid by preferring changed-file mode.
        return 0
    if (root / "Cargo.toml").exists():
        return run(["cargo", "fmt"], cwd=root)
    return 0


def run_changed_formatters(root: Path, files: list[Path]) -> int:
    # Group by extension
    py = [f for f in files if f.suffix == ".py"]
    go = [f for f in files if f.suffix == ".go"]
    js = [f for f in files if f.suffix in {".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".yml", ".yaml"}]
    rs = [f for f in files if f.suffix == ".rs"]

    ok = True

    if py:
        if which("black"):
            ok = ok and (run(["python3", "-m", "black", "-q", *map(str, py)], cwd=root) == 0)
        if which("isort"):
            ok = ok and (run(["python3", "-m", "isort", "-q", *map(str, py)], cwd=root) == 0)

    if go:
        if which("gofmt"):
            ok = ok and (run(["gofmt", "-w", *map(str, go)], cwd=root) == 0)
        if which("goimports"):
            ok = ok and (run(["goimports", "-w", *map(str, go)], cwd=root) == 0)

    if rs:
        # cargo fmt isn't file-scoped; keep best-effort.
        if (root / "Cargo.toml").exists():
            ok = ok and (run(["cargo", "fmt"], cwd=root) == 0)

    if js and (root / "package.json").exists():
        # Prefer prettier on specific files when available; fallback to npm run format.
        prettier = root / "node_modules" / ".bin" / "prettier"
        if prettier.exists():
            ok = ok and (run([str(prettier), "--write", *map(str, js)], cwd=root) == 0)
        else:
            # If the repo defines a fast "format" script, this may still be expensive.
            ok = ok and (run(["npm", "run", "format", "--silent"], cwd=root) == 0)

    return 0 if ok else 1


def _is_git_commit_command(command: str) -> bool:
    """Return True if command is a git commit invocation."""
    return bool(re.match(r"^\s*git\s+commit(\s|$)", command))


def post_commit_graph(repo_root_override: Path | None = None) -> int:
    """PostCommit hook: run incremental graph reindex after git commit.

    When called as a hook, reads CLAUDE_TOOL_INPUT to detect git commit.
    When called directly with repo_root_override, skips command detection.

    Delegates to .cnogo/.venv/bin/python3 if available and we're not
    already running inside the venv. Uses subprocess.run() (not os.execv)
    so the hook process returns cleanly.
    """
    if repo_root_override is None:
        raw_input = os.environ.get("CLAUDE_TOOL_INPUT", "").strip()
        if not raw_input:
            return 0
        command = _extract_bash_command(raw_input)
        if not command or not _is_git_commit_command(command):
            return 0

    try:
        root = repo_root_override or repo_root()

        # Delegate to venv python if available and we're not already in it
        venv_python = root / ".cnogo" / ".venv" / "bin" / "python3"
        venv_dir = (root / ".cnogo" / ".venv").resolve()
        if venv_python.exists() and Path(sys.prefix).resolve() != venv_dir:
            result = subprocess.run(
                [str(venv_python), __file__, "post_commit_graph"],
                cwd=str(root),
            )
            return result.returncode
        if not venv_python.exists():
            print(
                "[cnogo] Graph venv not found, using current interpreter.\n"
                "  For best results, create a dedicated venv:\n"
                "    python3 -m venv .cnogo/.venv && "
                ".cnogo/.venv/bin/pip install kuzu tree-sitter tree-sitter-languages",
                file=sys.stderr,
            )

        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from scripts.context import ContextGraph

        graph = ContextGraph(repo_path=root)
        try:
            graph.index()
            count = graph._storage.node_count()
            print(f"Graph reindexed: {count} nodes", file=sys.stderr)
        finally:
            graph.close()
        return 0
    except ImportError:
        print(
            "[cnogo] Graph reindex skipped: missing dependencies.\n"
            "  Install graph requirements:\n"
            "    .cnogo/.venv/bin/pip install -r .cnogo/requirements-graph.txt",
            file=sys.stderr,
        )
        return 0
    except Exception as exc:
        print(
            f"[cnogo] Graph reindex warning: {type(exc).__name__}: {exc}\n"
            "  Check graph DB at .cnogo/graph.db or re-run: "
            "python3 .cnogo/scripts/workflow_hooks.py post_commit_graph",
            file=sys.stderr,
        )
        return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: workflow_hooks.py <pre_bash|post_edit|post_commit_graph>", file=sys.stderr)
        return 2
    cmd = sys.argv[1]
    if cmd == "pre_bash":
        return pre_bash()
    if cmd == "post_edit":
        return post_edit()
    if cmd == "post_commit_graph":
        return post_commit_graph()
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
