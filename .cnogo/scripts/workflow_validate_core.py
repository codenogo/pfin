#!/usr/bin/env python3
"""
Workflow Validator for Universal Development Workflow Pack

Validates that planning artifacts follow the workflow rules and that
machine-checkable contracts exist for key markdown files.

No external dependencies.
"""

from __future__ import annotations

try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass  # imported as module; caller manages sys.path

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from workflow_utils import load_json as _load_json
    from workflow_utils import iter_skill_paths as _iter_skill_paths
    from workflow_utils import parse_skill_frontmatter as _parse_skill_frontmatter
except ModuleNotFoundError:
    from .workflow_utils import load_json as _load_json  # type: ignore
    from .workflow_utils import iter_skill_paths as _iter_skill_paths  # type: ignore
    from .workflow_utils import parse_skill_frontmatter as _parse_skill_frontmatter  # type: ignore


def _is_positive_int(val: Any, *, allow_zero: bool = False) -> bool:
    """Check val is a real int (not bool) and positive (or >= 0 if allow_zero)."""
    return isinstance(val, int) and not isinstance(val, bool) and (val >= 0 if allow_zero else val > 0)


FEATURE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
QUICK_DIR_RE = re.compile(r"^[0-9]{3}-[a-z0-9]+(?:-[a-z0-9]+)*$")
PLAN_MD_RE = re.compile(r"^(?P<num>[0-9]{2})-PLAN\.md$")
SUMMARY_MD_RE = re.compile(r"^(?P<num>[0-9]{2})-SUMMARY\.md$")
DEFAULT_TOKEN_BUDGETS = {
    "enabled": True,
    "commandWordMax": 400,
    "commandsTotalWordMax": 8000,
    "contextWordMax": 1300,
    "planWordMax": 1200,
    "summaryWordMax": 900,
    "reviewWordMax": 1400,
    "researchWordMax": 2200,
    "shapeWordMax": 1600,
    "brainstormWordMax": 1400,
}
DEFAULT_BOOTSTRAP_CONTEXT = {
    "enabled": True,
    "rootClaudeWordMax": 500,
    "workflowClaudeWordMax": 450,
    "commandSetWordMax": 7000,
}
SHAPE_CANDIDATE_STATUSES = {"draft", "discuss-ready", "blocked", "parked"}


def _repo_root(start: Path) -> Path:
    """Resolve validation root from a user-supplied path.

    If ``start`` is inside a git repo, return that repo's toplevel.
    Otherwise, use ``start`` as-is.
    """
    candidate = start.resolve()
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=candidate,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return Path(out)
    except Exception:
        return candidate


def _is_git_repo(root: Path) -> bool:
    try:
        subprocess.check_output(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _staged_files(root: Path) -> list[Path]:
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"], cwd=root, stderr=subprocess.DEVNULL
    ).decode()
    files: list[Path] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        files.append(root / line)
    return files


@dataclass
class Finding:
    level: str  # "ERROR" | "WARN"
    message: str
    path: str | None = None

    def format(self) -> str:
        loc = f" ({self.path})" if self.path else ""
        return f"[{self.level}]{loc} {self.message}"


def _require(path: Path, findings: list[Finding], msg: str) -> None:
    if not path.exists():
        findings.append(Finding("ERROR", msg, str(path)))


def _validate_memory_runtime(root: Path, findings: list[Finding]) -> None:
    """Treat tracked memory sync data as sufficient for source validation."""
    memory_db = root / ".cnogo" / "memory.db"
    issues_jsonl = root / ".cnogo" / "issues.jsonl"
    if memory_db.exists() or issues_jsonl.exists():
        return
    findings.append(
        Finding(
            "WARN",
            (
                "Memory runtime is not initialized locally. "
                "Run: python3 .cnogo/scripts/workflow_memory.py init "
                "to enable memory commands."
            ),
            str(memory_db),
        )
    )


def _validate_feature_slug(name: str, findings: list[Finding], path: Path) -> None:
    if not FEATURE_SLUG_RE.match(name):
        findings.append(
            Finding(
                "ERROR",
                "Feature directory must be kebab-case slug (lowercase letters/numbers/hyphens). Example: 'websocket-notifications'.",
                str(path),
            )
        )


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _resolve_contract_ref(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _linked_artifact_time(root: Path, raw_path: str) -> datetime | None:
    resolved = _resolve_contract_ref(root, raw_path)
    if resolved.suffix == ".json":
        md_path = resolved.with_suffix(".md")
        return _artifact_time(md_path if md_path.exists() else resolved, resolved)
    if resolved.suffix == ".md":
        json_path = resolved.with_suffix(".json")
        return _artifact_time(resolved, json_path if json_path.exists() else None)
    return _artifact_time(resolved, None)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: Any) -> datetime | None:
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


def _artifact_time(markdown_path: Path, contract_path: Path | None = None) -> datetime | None:
    """Best-effort artifact timestamp from contract.timestamp, then file mtime."""
    if contract_path is not None and contract_path.exists():
        try:
            data = _load_json(contract_path)
            if isinstance(data, dict):
                dt = _parse_ts(data.get("timestamp"))
                if dt is not None:
                    return dt
        except Exception:
            pass
    if markdown_path.exists():
        try:
            return datetime.fromtimestamp(markdown_path.stat().st_mtime, tz=timezone.utc)
        except Exception:
            return None
    return None


def _age_days(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    delta = _utc_now() - dt
    return max(0, int(delta.total_seconds() // 86400))


def _freshness_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "enabled": True,
        "contextMaxAgeDays": 30,
        "planMaxAgeDaysWithoutSummary": 14,
        "summaryMaxAgeDaysWithoutReview": 7,
    }
    raw = cfg.get("freshness")
    if not isinstance(raw, dict):
        return defaults
    out = dict(defaults)
    enabled = raw.get("enabled")
    if isinstance(enabled, bool):
        out["enabled"] = enabled
    for key in (
        "contextMaxAgeDays",
        "planMaxAgeDaysWithoutSummary",
        "summaryMaxAgeDaysWithoutReview",
    ):
        val = raw.get(key)
        if _is_positive_int(val, allow_zero=True):
            out[key] = val
    return out


def _token_budgets_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    perf = cfg.get("performance")
    if not isinstance(perf, dict):
        return dict(DEFAULT_TOKEN_BUDGETS)
    raw = perf.get("tokenBudgets")
    if not isinstance(raw, dict):
        return dict(DEFAULT_TOKEN_BUDGETS)

    out = dict(DEFAULT_TOKEN_BUDGETS)
    enabled = raw.get("enabled")
    if isinstance(enabled, bool):
        out["enabled"] = enabled

    for key in (
        "commandWordMax",
        "commandsTotalWordMax",
        "contextWordMax",
        "planWordMax",
        "summaryWordMax",
        "reviewWordMax",
        "researchWordMax",
        "shapeWordMax",
        "brainstormWordMax",
    ):
        val = raw.get(key)
        if _is_positive_int(val):
            out[key] = val

    return out


def _bootstrap_context_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    perf = cfg.get("performance")
    if not isinstance(perf, dict):
        return dict(DEFAULT_BOOTSTRAP_CONTEXT)
    raw = perf.get("bootstrapContext")
    if not isinstance(raw, dict):
        return dict(DEFAULT_BOOTSTRAP_CONTEXT)

    out = dict(DEFAULT_BOOTSTRAP_CONTEXT)
    enabled = raw.get("enabled")
    if isinstance(enabled, bool):
        out["enabled"] = enabled
    for key in ("rootClaudeWordMax", "workflowClaudeWordMax", "commandSetWordMax"):
        val = raw.get(key)
        if _is_positive_int(val):
            out[key] = val
    return out


def _word_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").split())
    except Exception:
        return 0


MEMORY_ID_RE = re.compile(r"^cn-[a-z0-9]+(\.\d+)*$")
_RATIONALIZATION_PATTERNS = [
    re.compile(r"\btoo\s+small\b", re.IGNORECASE),
    re.compile(r"\btoo\s+simple\b", re.IGNORECASE),
    re.compile(r"\bskip(?:ping)?\s+tdd\b", re.IGNORECASE),
    re.compile(r"\bdo(?:n'?t| not)\s+need\s+tests?\b", re.IGNORECASE),
    re.compile(r"\balready\s+works\b", re.IGNORECASE),
    re.compile(r"\bprobably\s+fine\b", re.IGNORECASE),
    re.compile(r"\bseems?\s+fine\b", re.IGNORECASE),
    re.compile(r"\bno\s+time\b", re.IGNORECASE),
    re.compile(r"\blater\b", re.IGNORECASE),
    re.compile(r"\bmanual\s+only\b", re.IGNORECASE),
]


def _validate_memory_id(value: Any, field_name: str, findings: list[Finding], path: Path) -> None:
    """Validate optional memory ID fields (memoryEpicId, memoryId)."""
    if value is None:
        return  # Optional field, absence is fine
    if not isinstance(value, str) or not MEMORY_ID_RE.match(value):
        findings.append(Finding(
            "WARN",
            f"{field_name} has invalid format (expected cn-<base36>[.N]): {value!r}",
            str(path),
        ))


def _contains_rationalization(text: str) -> bool:
    return any(p.search(text) for p in _RATIONALIZATION_PATTERNS)


def _policy_level_to_finding(level: str) -> str:
    return "ERROR" if level == "error" else "WARN"


def _validate_plan_contract(
    contract: Any,
    findings: list[Finding],
    path: Path,
    *,
    tdd_mode_level: str = "error",
) -> None:
    if not isinstance(contract, dict):
        findings.append(Finding("ERROR", "Plan contract must be a JSON object.", str(path)))
        return

    if "schemaVersion" not in contract:
        findings.append(Finding("WARN", "Plan contract missing schemaVersion (recommended).", str(path)))
    schema_version_raw = contract.get("schemaVersion", 1)
    schema_version = schema_version_raw if _is_positive_int(schema_version_raw, allow_zero=True) else 1

    # Validate optional memory fields
    _validate_memory_id(contract.get("memoryEpicId"), "memoryEpicId", findings, path)

    # Validate optional parallelizable hint
    parallelizable = contract.get("parallelizable")
    if parallelizable is not None and not isinstance(parallelizable, bool):
        findings.append(Finding("WARN", "Plan contract: 'parallelizable' should be a boolean if present.", str(path)))

    tasks = contract.get("tasks")
    if not isinstance(tasks, list):
        findings.append(Finding("ERROR", "Plan contract must include 'tasks' array.", str(path)))
        return

    if len(tasks) == 0:
        findings.append(Finding("ERROR", "Plan must include at least 1 task.", str(path)))
    if len(tasks) > 3:
        findings.append(Finding("ERROR", "Plan has >3 tasks. Split into multiple plans to keep context fresh.", str(path)))

    for i, t in enumerate(tasks, start=1):
        if not isinstance(t, dict):
            findings.append(Finding("ERROR", f"Task {i} must be an object.", str(path)))
            continue
        name = t.get("name")
        if not isinstance(name, str) or not name.strip():
            findings.append(Finding("ERROR", f"Task {i} missing non-empty 'name'.", str(path)))
        files = t.get("files")
        if not isinstance(files, list) or not files:
            findings.append(Finding("ERROR", f"Task {i} must include non-empty 'files' array.", str(path)))
        else:
            for fp in files:
                if not isinstance(fp, str) or not fp.strip():
                    findings.append(Finding("ERROR", f"Task {i} has empty file path.", str(path)))
                    continue
                if "*" in fp or "…" in fp or fp.endswith("/"):
                    findings.append(Finding("WARN", f"Task {i} file path looks ambiguous: {fp!r}", str(path)))
        verify = t.get("verify")
        if not isinstance(verify, list) or not verify or not all(isinstance(x, str) and x.strip() for x in verify):
            findings.append(Finding("ERROR", f"Task {i} must include non-empty 'verify' array of commands.", str(path)))
        # Validate optional memory ID per task
        _validate_memory_id(t.get("memoryId"), f"Task {i} memoryId", findings, path)
        # Validate optional deletions field type
        deletions = t.get("deletions")
        if deletions is not None:
            if not isinstance(deletions, list) or not all(isinstance(d, str) for d in deletions):
                findings.append(Finding("WARN", f"Task {i} 'deletions' must be a list of strings.", str(path)))

        if schema_version >= 2 and tdd_mode_level != "off":
            policy_level = _policy_level_to_finding(tdd_mode_level)

            micro_steps = t.get("microSteps")
            if not isinstance(micro_steps, list) or not micro_steps:
                findings.append(
                    Finding(
                        policy_level,
                        f"Task {i} schemaVersion>=2 requires non-empty 'microSteps' array.",
                        str(path),
                    )
                )
            elif not all(isinstance(step, str) and step.strip() for step in micro_steps):
                findings.append(
                    Finding(
                        policy_level,
                        f"Task {i} microSteps entries must be non-empty strings.",
                        str(path),
                    )
                )

            tdd = t.get("tdd")
            if not isinstance(tdd, dict):
                findings.append(
                    Finding(
                        policy_level,
                        f"Task {i} schemaVersion>=2 requires 'tdd' object.",
                        str(path),
                    )
                )
            else:
                required = tdd.get("required")
                if not isinstance(required, bool):
                    findings.append(
                        Finding(
                            policy_level,
                            f"Task {i} tdd.required must be boolean.",
                            str(path),
                        )
                    )
                elif required:
                    failing_verify = tdd.get("failingVerify")
                    passing_verify = tdd.get("passingVerify")
                    if (
                        not isinstance(failing_verify, list)
                        or not failing_verify
                        or not all(isinstance(v, str) and v.strip() for v in failing_verify)
                    ):
                        findings.append(
                            Finding(
                                policy_level,
                                f"Task {i} tdd.required=true requires non-empty failingVerify[] commands.",
                                str(path),
                            )
                        )
                    if (
                        not isinstance(passing_verify, list)
                        or not passing_verify
                        or not all(isinstance(v, str) and v.strip() for v in passing_verify)
                    ):
                        findings.append(
                            Finding(
                                policy_level,
                                f"Task {i} tdd.required=true requires non-empty passingVerify[] commands.",
                                str(path),
                            )
                        )
                else:
                    reason = tdd.get("reason")
                    if not isinstance(reason, str) or not reason.strip():
                        findings.append(
                            Finding(
                                policy_level,
                                f"Task {i} tdd.required=false requires non-empty tdd.reason.",
                                str(path),
                            )
                        )
                    elif _contains_rationalization(reason):
                        findings.append(
                            Finding(
                                policy_level,
                                f"Task {i} tdd.reason appears rationalized; provide a concrete non-rationalized exemption reason.",
                                str(path),
                            )
                        )

    # Check if the last task has deletions with no subsequent task to receive auto-expanded caller cleanup scope
    if tasks:
        last_idx = len(tasks)
        last_task = tasks[-1]
        if isinstance(last_task, dict):
            last_deletions = last_task.get("deletions")
            if isinstance(last_deletions, list) and last_deletions:
                findings.append(
                    Finding(
                        "WARN",
                        f"Task {last_idx} has `deletions` but is the last task in the plan — no subsequent task to receive auto-expanded caller cleanup scope.",
                        str(path),
                    )
                )


def _validate_quick_contract(contract: Any, findings: list[Finding], path: Path) -> None:
    if not isinstance(contract, dict):
        findings.append(Finding("ERROR", "Quick contract must be a JSON object.", str(path)))
        return
    if "schemaVersion" not in contract:
        findings.append(Finding("WARN", "Quick contract missing schemaVersion (recommended).", str(path)))
    goal = contract.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        findings.append(Finding("ERROR", "Quick contract missing non-empty 'goal'.", str(path)))
    files = contract.get("files")
    if not isinstance(files, list) or not files:
        findings.append(Finding("ERROR", "Quick contract missing non-empty 'files' array.", str(path)))
    verify = contract.get("verify")
    if not isinstance(verify, list) or not verify:
        findings.append(Finding("ERROR", "Quick contract missing non-empty 'verify' array of commands.", str(path)))


def _validate_quick_summary(contract: dict, findings: list, path: "Path") -> None:
    """Validate SUMMARY.json content for quick tasks."""
    if "schemaVersion" not in contract:
        findings.append(Finding("WARN", "Quick summary missing 'schemaVersion'.", str(path)))
    outcome = contract.get("outcome")
    if not isinstance(outcome, str) or not outcome:
        findings.append(Finding("ERROR", "Quick summary missing non-empty 'outcome'.", str(path)))
    changes = contract.get("changes")
    if not isinstance(changes, list) or not changes:
        findings.append(Finding("ERROR", "Quick summary missing non-empty 'changes' list.", str(path)))
    verification = contract.get("verification")
    if not isinstance(verification, list) or not verification:
        findings.append(Finding("ERROR", "Quick summary missing non-empty 'verification' list.", str(path)))


def _iter_feature_dirs(root: Path) -> Iterable[Path]:
    base = root / "docs" / "planning" / "work" / "features"
    if not base.is_dir():
        return []
    return [p for p in base.iterdir() if p.is_dir()]


def _iter_quick_dirs(root: Path) -> Iterable[Path]:
    base = root / "docs" / "planning" / "work" / "quick"
    if not base.is_dir():
        return []
    return [p for p in base.iterdir() if p.is_dir()]


def _iter_research_dirs(root: Path) -> Iterable[Path]:
    base = root / "docs" / "planning" / "work" / "research"
    if not base.is_dir():
        return []
    return [p for p in base.iterdir() if p.is_dir()]


def _iter_ideas_dirs(root: Path) -> Iterable[Path]:
    base = root / "docs" / "planning" / "work" / "ideas"
    if not base.is_dir():
        return []
    return [p for p in base.iterdir() if p.is_dir()]


def _detect_repo_shape(root: Path, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Heuristic repo-shape detection to support single-repo, monorepo, and polyglot repos.
    This is used only for validation warnings unless configured stricter via WORKFLOW.json.

    Optimization: if WORKFLOW.json has non-empty packages[], use that instead of rglob.
    Falls back to rglob only when repoShape is "auto" AND packages is empty.
    """
    resolved_cfg = cfg if isinstance(cfg, dict) else _load_workflow_config(root)
    pkgs = resolved_cfg.get("packages")

    # Fast path: use configured packages[] if available
    if isinstance(pkgs, list) and pkgs:
        kind_counts: dict[str, int] = {}
        for p in pkgs:
            if isinstance(p, dict):
                kind = str(p.get("kind", "other"))
                kind_counts[kind] = kind_counts.get(kind, 0) + 1
        manifest_total = sum(kind_counts.values())
        languages = len(kind_counts.keys() - {"other"})
        return {
            "package_json": kind_counts.get("node", 0),
            "pom_xml": kind_counts.get("java", 0),
            "pyproject_toml": kind_counts.get("python", 0),
            "go_mod": kind_counts.get("go", 0),
            "cargo_toml": kind_counts.get("rust", 0),
            "monorepo": manifest_total > 1,
            "polyglot": languages > 1,
        }

    # Slow path: single-pass manifest walk when packages[] is empty or missing.
    counts = {
        "package_json": 0,
        "pom_xml": 0,
        "pyproject_toml": 0,
        "go_mod": 0,
        "cargo_toml": 0,
    }
    ignore_dirs = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        "target",
        "__pycache__",
    }
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        name_set = set(filenames)
        if "package.json" in name_set:
            counts["package_json"] += 1
        if "pom.xml" in name_set:
            counts["pom_xml"] += 1
        if "pyproject.toml" in name_set:
            counts["pyproject_toml"] += 1
        if "go.mod" in name_set:
            counts["go_mod"] += 1
        if "Cargo.toml" in name_set:
            counts["cargo_toml"] += 1

    manifest_total = sum(counts.values())
    languages = sum(1 for x in counts.values() if x > 0)

    return {
        "package_json": counts["package_json"],
        "pom_xml": counts["pom_xml"],
        "pyproject_toml": counts["pyproject_toml"],
        "go_mod": counts["go_mod"],
        "cargo_toml": counts["cargo_toml"],
        "monorepo": manifest_total > 1,
        "polyglot": languages > 1,
    }


def _load_workflow_config(root: Path) -> dict[str, Any]:
    cfg_path = root / "docs" / "planning" / "WORKFLOW.json"
    if not cfg_path.exists():
        return {}
    try:
        cfg = _load_json(cfg_path)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _validate_workflow_config(cfg: dict[str, Any], findings: list[Finding], root: Path) -> None:
    """
    Minimal validation of WORKFLOW.json without external dependencies.
    The JSON Schema is provided for editors; this is runtime sanity checking.
    """
    cfg_path = root / "docs" / "planning" / "WORKFLOW.json"

    version = cfg.get("version")
    if not isinstance(version, int) or version < 1:
        findings.append(Finding("WARN", "WORKFLOW.json: 'version' should be an integer >= 1.", str(cfg_path)))

    repo_shape = cfg.get("repoShape")
    if repo_shape not in {"auto", "single", "monorepo", "polyglot"}:
        findings.append(Finding("WARN", "WORKFLOW.json: 'repoShape' should be one of auto|single|monorepo|polyglot.", str(cfg_path)))

    perf = cfg.get("performance")
    if perf is not None and not isinstance(perf, dict):
        findings.append(Finding("WARN", "WORKFLOW.json: 'performance' should be an object.", str(cfg_path)))
    elif isinstance(perf, dict):
        pef = perf.get("postEditFormat", "auto")
        if pef not in {"auto", "off"}:
            findings.append(Finding("WARN", "WORKFLOW.json: performance.postEditFormat should be auto|off.", str(cfg_path)))
        scope = perf.get("postEditFormatScope", "changed")
        if scope not in {"changed", "repo"}:
            findings.append(Finding("WARN", "WORKFLOW.json: performance.postEditFormatScope should be changed|repo.", str(cfg_path)))
        check_scope = perf.get("checkScope", "auto")
        if check_scope not in {"auto", "changed", "all"}:
            findings.append(Finding("WARN", "WORKFLOW.json: performance.checkScope should be auto|changed|all.", str(cfg_path)))
        changed_fallback = perf.get("changedFilesFallback", "none")
        if changed_fallback not in {"none", "head"}:
            findings.append(Finding("WARN", "WORKFLOW.json: performance.changedFilesFallback should be none|head.", str(cfg_path)))
        timeout = perf.get("commandTimeoutSec")
        if timeout is not None and (
            not _is_positive_int(timeout)
        ):
            findings.append(Finding("WARN", "WORKFLOW.json: performance.commandTimeoutSec should be an integer > 0.", str(cfg_path)))
        budgets = perf.get("tokenBudgets")
        if budgets is not None and not isinstance(budgets, dict):
            findings.append(Finding("WARN", "WORKFLOW.json: performance.tokenBudgets should be an object.", str(cfg_path)))
        elif isinstance(budgets, dict):
            enabled = budgets.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                findings.append(Finding("WARN", "WORKFLOW.json: performance.tokenBudgets.enabled should be boolean.", str(cfg_path)))
            for key in (
                "commandWordMax",
                "commandsTotalWordMax",
                "contextWordMax",
                "planWordMax",
                "summaryWordMax",
                "reviewWordMax",
                "researchWordMax",
                "shapeWordMax",
                "brainstormWordMax",
            ):
                val = budgets.get(key)
                if val is not None and (
                    not _is_positive_int(val)
                ):
                    findings.append(
                        Finding(
                            "WARN",
                            f"WORKFLOW.json: performance.tokenBudgets.{key} should be an integer > 0.",
                            str(cfg_path),
                        )
                    )

        compaction = perf.get("outputCompaction")
        if compaction is not None and not isinstance(compaction, dict):
            findings.append(Finding("WARN", "WORKFLOW.json: performance.outputCompaction should be an object.", str(cfg_path)))
        elif isinstance(compaction, dict):
            enabled = compaction.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                findings.append(Finding("WARN", "WORKFLOW.json: performance.outputCompaction.enabled should be boolean.", str(cfg_path)))
            dedupe = compaction.get("dedupe")
            if dedupe is not None and not isinstance(dedupe, bool):
                findings.append(Finding("WARN", "WORKFLOW.json: performance.outputCompaction.dedupe should be boolean.", str(cfg_path)))
            for key in ("maxLines", "failTailLines", "passLines"):
                val = compaction.get(key)
                if val is not None and (
                    not _is_positive_int(val)
                ):
                    findings.append(
                        Finding(
                            "WARN",
                            f"WORKFLOW.json: performance.outputCompaction.{key} should be an integer > 0.",
                            str(cfg_path),
                        )
                    )

        recovery = perf.get("outputRecovery")
        if recovery is not None and not isinstance(recovery, dict):
            findings.append(Finding("WARN", "WORKFLOW.json: performance.outputRecovery should be an object.", str(cfg_path)))
        elif isinstance(recovery, dict):
            enabled = recovery.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                findings.append(Finding("WARN", "WORKFLOW.json: performance.outputRecovery.enabled should be boolean.", str(cfg_path)))
            mode = recovery.get("mode")
            if mode is not None and mode not in {"failures", "always", "never"}:
                findings.append(Finding("WARN", "WORKFLOW.json: performance.outputRecovery.mode should be failures|always|never.", str(cfg_path)))
            directory = recovery.get("directory")
            if directory is not None and (not isinstance(directory, str) or not directory.strip()):
                findings.append(Finding("WARN", "WORKFLOW.json: performance.outputRecovery.directory should be a non-empty string.", str(cfg_path)))
            for key in ("minChars", "maxFiles", "maxFileSize"):
                val = recovery.get(key)
                if val is not None and (
                    not _is_positive_int(val)
                ):
                    findings.append(
                        Finding(
                            "WARN",
                            f"WORKFLOW.json: performance.outputRecovery.{key} should be an integer > 0.",
                            str(cfg_path),
                        )
                    )

        telemetry = perf.get("tokenTelemetry")
        if telemetry is not None and not isinstance(telemetry, dict):
            findings.append(Finding("WARN", "WORKFLOW.json: performance.tokenTelemetry should be an object.", str(cfg_path)))
        elif isinstance(telemetry, dict):
            enabled = telemetry.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                findings.append(Finding("WARN", "WORKFLOW.json: performance.tokenTelemetry.enabled should be boolean.", str(cfg_path)))

        hook_opt = perf.get("hookOptimization")
        if hook_opt is not None and not isinstance(hook_opt, dict):
            findings.append(Finding("WARN", "WORKFLOW.json: performance.hookOptimization should be an object.", str(cfg_path)))
        elif isinstance(hook_opt, dict):
            enabled = hook_opt.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                findings.append(Finding("WARN", "WORKFLOW.json: performance.hookOptimization.enabled should be boolean.", str(cfg_path)))
            mode = hook_opt.get("mode")
            if mode is not None and mode not in {"suggest", "enforce", "off"}:
                findings.append(Finding("WARN", "WORKFLOW.json: performance.hookOptimization.mode should be suggest|enforce|off.", str(cfg_path)))
            show = hook_opt.get("showSuggestions")
            if show is not None and not isinstance(show, bool):
                findings.append(Finding("WARN", "WORKFLOW.json: performance.hookOptimization.showSuggestions should be boolean.", str(cfg_path)))
            log_file = hook_opt.get("logFile")
            if log_file is not None and (not isinstance(log_file, str) or not log_file.strip()):
                findings.append(Finding("WARN", "WORKFLOW.json: performance.hookOptimization.logFile should be a non-empty string.", str(cfg_path)))

        bootstrap = perf.get("bootstrapContext")
        if bootstrap is not None and not isinstance(bootstrap, dict):
            findings.append(Finding("WARN", "WORKFLOW.json: performance.bootstrapContext should be an object.", str(cfg_path)))
        elif isinstance(bootstrap, dict):
            enabled = bootstrap.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                findings.append(Finding("WARN", "WORKFLOW.json: performance.bootstrapContext.enabled should be boolean.", str(cfg_path)))
            for key in ("rootClaudeWordMax", "workflowClaudeWordMax", "commandSetWordMax"):
                val = bootstrap.get(key)
                if val is not None and (
                    not _is_positive_int(val)
                ):
                    findings.append(
                        Finding(
                            "WARN",
                            f"WORKFLOW.json: performance.bootstrapContext.{key} should be an integer > 0.",
                            str(cfg_path),
                        )
                    )

    enf = cfg.get("enforcement")
    if enf is not None and not isinstance(enf, dict):
        findings.append(Finding("WARN", "WORKFLOW.json: 'enforcement' should be an object.", str(cfg_path)))
    elif isinstance(enf, dict):
        mvs = enf.get("monorepoVerifyScope", "warn")
        if mvs not in {"warn", "error"}:
            findings.append(Finding("WARN", "WORKFLOW.json: enforcement.monorepoVerifyScope should be warn|error.", str(cfg_path)))
        op = enf.get("operatingPrinciples", "warn")
        if op not in {"off", "warn", "error"}:
            findings.append(Finding("WARN", "WORKFLOW.json: enforcement.operatingPrinciples should be off|warn|error.", str(cfg_path)))
        tdd_mode = enf.get("tddMode", "error")
        if tdd_mode not in {"off", "warn", "error"}:
            findings.append(Finding("WARN", "WORKFLOW.json: enforcement.tddMode should be off|warn|error.", str(cfg_path)))
        vbc = enf.get("verificationBeforeCompletion", "error")
        if vbc not in {"off", "warn", "error"}:
            findings.append(
                Finding(
                    "WARN",
                    "WORKFLOW.json: enforcement.verificationBeforeCompletion should be off|warn|error.",
                    str(cfg_path),
                )
            )
        tsr = enf.get("twoStageReview", "error")
        if tsr not in {"off", "warn", "error"}:
            findings.append(Finding("WARN", "WORKFLOW.json: enforcement.twoStageReview should be off|warn|error.", str(cfg_path)))
        ownership = enf.get("taskOwnership", "error")
        if ownership not in {"off", "warn", "error"}:
            findings.append(Finding("WARN", "WORKFLOW.json: enforcement.taskOwnership should be off|warn|error.", str(cfg_path)))

    pkgs = cfg.get("packages")
    if pkgs is not None and not isinstance(pkgs, list):
        findings.append(Finding("WARN", "WORKFLOW.json: 'packages' should be an array.", str(cfg_path)))
    elif isinstance(pkgs, list):
        for i, p in enumerate(pkgs, start=1):
            if not isinstance(p, dict):
                findings.append(Finding("WARN", f"WORKFLOW.json: packages[{i}] should be an object.", str(cfg_path)))
                continue
            path = p.get("path")
            if not isinstance(path, str) or not path.strip():
                findings.append(Finding("WARN", f"WORKFLOW.json: packages[{i}].path is required.", str(cfg_path)))
                continue
            # Soft check: warn if the configured package path doesn't exist (helps catch typos).
            if not (root / path).exists():
                findings.append(Finding("WARN", f"WORKFLOW.json: packages[{i}].path does not exist: {path}", str(cfg_path)))
            cmds = p.get("commands")
            if cmds is not None and not isinstance(cmds, dict):
                findings.append(Finding("WARN", f"WORKFLOW.json: packages[{i}].commands should be an object.", str(cfg_path)))
            elif isinstance(cmds, dict):
                for k in ["build", "test", "lint", "format", "typecheck", "run"]:
                    v = cmds.get(k)
                    if v is not None and (not isinstance(v, str) or not v.strip()):
                        findings.append(Finding("WARN", f"WORKFLOW.json: packages[{i}].commands.{k} should be a non-empty string.", str(cfg_path)))

    research = cfg.get("research")
    if research is not None and not isinstance(research, dict):
        findings.append(Finding("WARN", "WORKFLOW.json: 'research' should be an object.", str(cfg_path)))
    elif isinstance(research, dict):
        mode = research.get("mode", "auto")
        if mode not in {"off", "local", "mcp", "web", "auto"}:
            findings.append(Finding("WARN", "WORKFLOW.json: research.mode should be off|local|mcp|web|auto.", str(cfg_path)))
        ms = research.get("minSources", 0)
        if not isinstance(ms, int) or ms < 0:
            findings.append(Finding("WARN", "WORKFLOW.json: research.minSources should be an integer >= 0.", str(cfg_path)))

    agent_teams = cfg.get("agentTeams")
    if agent_teams is not None and not isinstance(agent_teams, dict):
        findings.append(Finding("WARN", "WORKFLOW.json: 'agentTeams' should be an object.", str(cfg_path)))
    elif isinstance(agent_teams, dict):
        stale = agent_teams.get("staleIndicatorMinutes")
        if stale is not None:
            if not _is_positive_int(stale):
                findings.append(Finding("WARN", "WORKFLOW.json: agentTeams.staleIndicatorMinutes should be an integer > 0.", str(cfg_path)))
        max_takeovers = agent_teams.get("maxTakeoversPerTask")
        if max_takeovers is not None:
            if not _is_positive_int(max_takeovers, allow_zero=True):
                findings.append(
                    Finding(
                        "WARN",
                        "WORKFLOW.json: agentTeams.maxTakeoversPerTask should be an integer >= 0.",
                        str(cfg_path),
                    )
                )
        wt_mode = agent_teams.get("worktreeMode")
        if wt_mode is not None:
            if isinstance(wt_mode, bool) or not isinstance(wt_mode, str) or wt_mode not in ("always", "off"):
                findings.append(Finding("WARN", "WORKFLOW.json: agentTeams.worktreeMode should be 'always' or 'off'.", str(cfg_path)))

    freshness = cfg.get("freshness")
    if freshness is not None and not isinstance(freshness, dict):
        findings.append(Finding("WARN", "WORKFLOW.json: 'freshness' should be an object.", str(cfg_path)))
    elif isinstance(freshness, dict):
        enabled = freshness.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            findings.append(Finding("WARN", "WORKFLOW.json: freshness.enabled should be boolean.", str(cfg_path)))
        for key in (
            "contextMaxAgeDays",
            "planMaxAgeDaysWithoutSummary",
            "summaryMaxAgeDaysWithoutReview",
        ):
            v = freshness.get(key)
            if v is not None:
                if not _is_positive_int(v, allow_zero=True):
                    findings.append(Finding("WARN", f"WORKFLOW.json: freshness.{key} should be an integer >= 0.", str(cfg_path)))

    invariants = cfg.get("invariants")
    if invariants is not None and not isinstance(invariants, dict):
        findings.append(Finding("WARN", "WORKFLOW.json: 'invariants' should be an object.", str(cfg_path)))
    elif isinstance(invariants, dict):
        enabled = invariants.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            findings.append(Finding("WARN", "WORKFLOW.json: invariants.enabled should be boolean.", str(cfg_path)))
        scope = invariants.get("scanScope")
        if scope is not None and scope not in {"changed", "repo"}:
            findings.append(Finding("WARN", "WORKFLOW.json: invariants.scanScope should be changed|repo.", str(cfg_path)))
        for key in ("maxFileLines", "maxLineLength"):
            v = invariants.get(key)
            if v is not None:
                if not _is_positive_int(v):
                    findings.append(Finding("WARN", f"WORKFLOW.json: invariants.{key} should be an integer > 0.", str(cfg_path)))
        exceptions = invariants.get("maxFileLinesExceptions")
        if exceptions is not None:
            if not isinstance(exceptions, list):
                findings.append(Finding("WARN", "WORKFLOW.json: invariants.maxFileLinesExceptions should be an array of path patterns.", str(cfg_path)))
            else:
                for i, item in enumerate(exceptions, start=1):
                    if not isinstance(item, str) or not item.strip():
                        findings.append(
                            Finding(
                                "WARN",
                                f"WORKFLOW.json: invariants.maxFileLinesExceptions[{i}] should be a non-empty string.",
                                str(cfg_path),
                            )
                        )
        fip = invariants.get("forbiddenImportPatterns")
        if fip is not None and not isinstance(fip, list):
            findings.append(Finding("WARN", "WORKFLOW.json: invariants.forbiddenImportPatterns should be an array.", str(cfg_path)))

    entropy = cfg.get("entropy")
    if entropy is not None and not isinstance(entropy, dict):
        findings.append(Finding("WARN", "WORKFLOW.json: 'entropy' should be an object.", str(cfg_path)))
    elif isinstance(entropy, dict):
        enabled = entropy.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            findings.append(Finding("WARN", "WORKFLOW.json: entropy.enabled should be boolean.", str(cfg_path)))
        mode = entropy.get("mode")
        if mode is not None and mode not in {"background", "manual"}:
            findings.append(Finding("WARN", "WORKFLOW.json: entropy.mode should be background|manual.", str(cfg_path)))
        for key in ("maxFilesPerTask", "maxTasksPerRun"):
            v = entropy.get(key)
            if v is not None:
                if not _is_positive_int(v):
                    findings.append(Finding("WARN", f"WORKFLOW.json: entropy.{key} should be an integer > 0.", str(cfg_path)))


def _packages_from_cfg(cfg: dict[str, Any]) -> list[dict[str, str]]:
    pkgs = cfg.get("packages")
    if not isinstance(pkgs, list):
        return []
    out: list[dict[str, str]] = []
    for p in pkgs:
        if not isinstance(p, dict):
            continue
        path = p.get("path")
        if isinstance(path, str) and path.strip():
            out.append({"path": path.strip(), "name": str(p.get("name") or "").strip()})
    # Sort longer paths first to match most specific package
    out.sort(key=lambda x: len(x["path"]), reverse=True)
    return out


def _infer_task_package(files: list[str], packages: list[dict[str, str]]) -> str | None:
    """
    If all files fall under a single configured package path, return that path.
    """
    if not files or not packages:
        return None
    matched: set[str] = set()
    for f in files:
        fp = f.lstrip("./")
        for p in packages:
            base = p["path"].rstrip("/").lstrip("./")
            if fp == base or fp.startswith(base + "/"):
                matched.add(p["path"])
                break
        else:
            matched.add("__outside__")
    # If everything matches the same package path, return it.
    if len(matched) == 1:
        only = next(iter(matched))
        if only != "__outside__":
            return only
    return None


def _get_monorepo_scope_level(cfg: dict[str, Any]) -> str:
    # warn|error, default warn
    enforcement = cfg.get("enforcement") if isinstance(cfg.get("enforcement"), dict) else {}
    level = enforcement.get("monorepoVerifyScope", "warn")
    if level not in {"warn", "error"}:
        return "warn"
    return level


def _get_operating_principles_level(cfg: dict[str, Any]) -> str:
    enforcement = cfg.get("enforcement") if isinstance(cfg.get("enforcement"), dict) else {}
    level = enforcement.get("operatingPrinciples", "warn")
    if level not in {"off", "warn", "error"}:
        return "warn"
    return level


def _get_tdd_mode_level(cfg: dict[str, Any]) -> str:
    enforcement = cfg.get("enforcement") if isinstance(cfg.get("enforcement"), dict) else {}
    level = enforcement.get("tddMode", "error")
    if level not in {"off", "warn", "error"}:
        return "error"
    return level


def _get_verification_before_completion_level(cfg: dict[str, Any]) -> str:
    enforcement = cfg.get("enforcement") if isinstance(cfg.get("enforcement"), dict) else {}
    level = enforcement.get("verificationBeforeCompletion", "error")
    if level not in {"off", "warn", "error"}:
        return "error"
    return level


def _get_two_stage_review_level(cfg: dict[str, Any]) -> str:
    enforcement = cfg.get("enforcement") if isinstance(cfg.get("enforcement"), dict) else {}
    level = enforcement.get("twoStageReview", "error")
    if level not in {"off", "warn", "error"}:
        return "error"
    return level


def _get_task_ownership_level(cfg: dict[str, Any]) -> str:
    enforcement = cfg.get("enforcement") if isinstance(cfg.get("enforcement"), dict) else {}
    level = enforcement.get("taskOwnership", "error")
    if level not in {"off", "warn", "error"}:
        return "error"
    return level



def _verify_cmd_scoped(cmd: str) -> bool:
    """
    Returns True if a verification command looks scoped to a package.
    Heuristic: uses `cd <dir> && ...` or common workspace flags.
    """
    c = cmd.strip()
    if not c:
        return True
    if re.search(r"(^|\s)cd\s+[^;&|]+\s*&&", c):
        return True
    # common monorepo/workspace patterns
    if "pnpm -C " in c or "pnpm --dir " in c:
        return True
    if "npm --prefix " in c:
        return True
    if "yarn workspace " in c or "pnpm -F " in c or "pnpm --filter " in c:
        return True
    if "mvn -f " in c or "mvn --file " in c:
        return True
    if "gradle -p " in c or "./gradlew -p " in c:
        return True
    if "go test " in c or "cargo test" in c:
        # Usually repo-root is acceptable for Go/Rust; treat as scoped enough.
        return True
    if "pytest" in c or "ruff" in c:
        # Often repo-root is acceptable; treat as scoped enough.
        return True
    return False


def _validate_features(
    root: Path,
    findings: list[Finding],
    touched,
    shape: dict[str, Any],
    monorepo_scope_level: str,
    operating_principles_level: str,
    tdd_mode_level: str,
    verification_before_completion_level: str,
    two_stage_review_level: str,
    packages_cfg: list[dict[str, str]],
    freshness_cfg: dict[str, Any],
    feature_filter: str | None = None,
) -> None:
    """Validate feature directories: context, plans, summaries, reviews."""
    if feature_filter:
        feature_dir = root / "docs" / "planning" / "work" / "features" / feature_filter
        if not feature_dir.is_dir():
            findings.append(
                Finding(
                    "ERROR",
                    f"--feature target not found: {feature_filter!r}",
                    str(feature_dir),
                )
            )
            return
        feature_dirs: list[Path] = [feature_dir]
    else:
        feature_dirs = list(_iter_feature_dirs(root))

    for feature_dir in feature_dirs:
        if not touched(feature_dir):
            continue
        _validate_feature_slug(feature_dir.name, findings, feature_dir)

        plan_nums: set[str] = set()
        summary_nums: set[str] = set()
        plan_files_by_num: dict[str, set[str]] = {}
        summary_change_files_by_num: dict[str, set[str]] = {}

        feature_md = feature_dir / "FEATURE.md"
        feature_json = feature_dir / "FEATURE.json"
        if feature_md.exists():
            _require(feature_json, findings, "Missing FEATURE.json contract for FEATURE.md")
        if feature_json.exists():
            try:
                feature_contract = _load_json(feature_json)
                _validate_feature_stub_contract(root, feature_dir, feature_contract, findings, feature_json)
            except Exception as e:
                findings.append(Finding("ERROR", f"Failed to parse FEATURE.json: {e}", str(feature_json)))

        context_md = feature_dir / "CONTEXT.md"
        context_json = feature_dir / "CONTEXT.json"
        if context_md.exists():
            _require(context_json, findings, "Missing CONTEXT.json contract for CONTEXT.md")
        if context_json.exists():
            try:
                c = _load_json(context_json)
                if not isinstance(c, dict):
                    findings.append(Finding("ERROR", "CONTEXT.json must be a JSON object.", str(context_json)))
                else:
                    if "schemaVersion" not in c:
                        findings.append(Finding("WARN", "CONTEXT.json missing schemaVersion (recommended).", str(context_json)))
                    c_feature = c.get("feature")
                    if isinstance(c_feature, str) and c_feature.strip() and c_feature != feature_dir.name:
                        findings.append(
                            Finding(
                                "WARN",
                                f"CONTEXT.json feature {c_feature!r} does not match directory slug {feature_dir.name!r}.",
                                str(context_json),
                            )
                        )
                    _validate_shape_feedback(c.get("shapeFeedback"), findings, context_json)
                    parent_shape = c.get("parentShape")
                    if parent_shape is not None:
                        _validate_contract_link(
                            root,
                            parent_shape,
                            findings,
                            context_json,
                            field_name="parentShape",
                            required_timestamp=True,
                        )
                        _warn_if_link_stale(
                            root,
                            parent_shape,
                            findings,
                            context_json,
                            field_name="parentShape",
                            target_label="SHAPE artifact",
                        )
                    feature_stub_link = c.get("featureStub")
                    if feature_stub_link is not None:
                        _validate_contract_link(
                            root,
                            feature_stub_link,
                            findings,
                            context_json,
                            field_name="featureStub",
                            required_timestamp=True,
                        )
                        _warn_if_link_stale(
                            root,
                            feature_stub_link,
                            findings,
                            context_json,
                            field_name="featureStub",
                            target_label="FEATURE artifact",
                        )
            except Exception as e:
                findings.append(Finding("ERROR", f"Failed to parse CONTEXT.json: {e}", str(context_json)))

        for p in feature_dir.iterdir():
            if not p.is_file():
                continue
            m = PLAN_MD_RE.match(p.name)
            if not m:
                continue
            num = m.group("num")
            plan_nums.add(num)
            plan_json = feature_dir / f"{num}-PLAN.json"
            _require(plan_json, findings, f"Missing plan contract {num}-PLAN.json for {p.name}")
            if plan_json.exists():
                try:
                    contract = _load_json(plan_json)
                    _validate_plan_contract(
                        contract,
                        findings,
                        plan_json,
                        tdd_mode_level=tdd_mode_level,
                    )

                    if isinstance(contract, dict):
                        c_feature = contract.get("feature")
                        if isinstance(c_feature, str) and c_feature.strip() and c_feature != feature_dir.name:
                            findings.append(
                                Finding(
                                    "WARN",
                                    f"{num}-PLAN.json feature {c_feature!r} does not match directory slug {feature_dir.name!r}.",
                                    str(plan_json),
                                )
                            )
                        tasks = contract.get("tasks")
                        if isinstance(tasks, list):
                            planned_files: set[str] = set()
                            for task in tasks:
                                if not isinstance(task, dict):
                                    continue
                                files = task.get("files")
                                if not isinstance(files, list):
                                    continue
                                for fp in files:
                                    if isinstance(fp, str) and fp.strip():
                                        planned_files.add(fp.strip())
                            plan_files_by_num[num] = planned_files

                    # Monorepo/polyglot ergonomics: warn/error when verify commands are not scoped.
                    if shape.get("monorepo") and isinstance(contract, dict):
                        tasks = contract.get("tasks")
                        if isinstance(tasks, list):
                            for idx, task in enumerate(tasks, start=1):
                                if not isinstance(task, dict):
                                    continue
                                cwd = task.get("cwd")
                                verify = task.get("verify")
                                files = task.get("files")
                                if isinstance(cwd, str) and cwd.strip():
                                    continue  # explicit cwd is considered scoped
                                inferred = None
                                if isinstance(files, list) and all(isinstance(x, str) for x in files):
                                    inferred = _infer_task_package([str(x) for x in files], packages_cfg)
                                if isinstance(verify, list) and any(isinstance(v, str) and v.strip() for v in verify):
                                    unscoped = [v for v in verify if isinstance(v, str) and v.strip() and not _verify_cmd_scoped(v)]
                                    if unscoped:
                                        msg = (
                                            f"Plan task {idx} has verify commands that may be unscoped for a monorepo/polyglot repo. "
                                            f"Add task.cwd or scope verify with `cd <pkg> && ...` / workspace flags."
                                        )
                                        if inferred:
                                            msg += f" Inferred package cwd from files: {inferred!r}."
                                        lvl = "ERROR" if monorepo_scope_level == "error" else "WARN"
                                        findings.append(Finding(lvl, msg, str(plan_json)))
                except Exception as e:
                    findings.append(Finding("ERROR", f"Failed to parse plan contract: {e}", str(plan_json)))

            summary_md = feature_dir / f"{num}-SUMMARY.md"
            summary_json = feature_dir / f"{num}-SUMMARY.json"
            if summary_md.exists():
                summary_nums.add(num)
                _require(summary_json, findings, f"Missing summary contract {num}-SUMMARY.json for {summary_md.name}")
                if summary_json.exists():
                    try:
                        s = _load_json(summary_json)
                        if not isinstance(s, dict):
                            findings.append(Finding("ERROR", "Summary contract must be a JSON object.", str(summary_json)))
                        else:
                            s_feature = s.get("feature")
                            if isinstance(s_feature, str) and s_feature.strip() and s_feature != feature_dir.name:
                                findings.append(
                                    Finding(
                                        "WARN",
                                        f"{num}-SUMMARY.json feature {s_feature!r} does not match directory slug {feature_dir.name!r}.",
                                        str(summary_json),
                                    )
                                )
                            plan_number = s.get("planNumber")
                            if plan_number is not None:
                                plan_number_str = str(plan_number).strip()
                                if plan_number_str and plan_number_str != num:
                                    findings.append(
                                        Finding(
                                            "WARN",
                                            f"{num}-SUMMARY.json planNumber {plan_number_str!r} does not match filename plan number {num!r}.",
                                            str(summary_json),
                                        )
                                    )
                            changes = s.get("changes")
                            changed_files: set[str] = set()
                            if isinstance(changes, list):
                                for ch in changes:
                                    if isinstance(ch, dict):
                                        fp = ch.get("file")
                                        if isinstance(fp, str) and fp.strip():
                                            changed_files.add(fp.strip())
                            summary_change_files_by_num[num] = changed_files
                            outcome = s.get("outcome")
                            if outcome not in {"complete", "partial", "failed"}:
                                findings.append(
                                    Finding("ERROR", "Summary contract must include outcome: complete|partial|failed", str(summary_json))
                                )
                    except Exception as e:
                        findings.append(Finding("ERROR", f"Failed to parse summary contract: {e}", str(summary_json)))

        for p in feature_dir.iterdir():
            if not p.is_file():
                continue
            m = SUMMARY_MD_RE.match(p.name)
            if m:
                summary_nums.add(m.group("num"))

        _validate_ci_verification(
            feature_dir,
            findings,
            operating_principles_level,
            verification_before_completion_level,
            two_stage_review_level,
        )
        _validate_feature_lifecycle_and_freshness(
            feature_dir=feature_dir,
            context_md=context_md,
            context_json=context_json,
            plan_nums=plan_nums,
            summary_nums=summary_nums,
            plan_files_by_num=plan_files_by_num,
            summary_change_files_by_num=summary_change_files_by_num,
            freshness=freshness_cfg,
            findings=findings,
        )


def _validate_ci_verification(
    feature_dir: Path,
    findings: list[Finding],
    operating_principles_level: str,
    verification_before_completion_level: str,
    two_stage_review_level: str,
) -> None:
    """Validate review, CI verification, and human verification artifacts within a feature."""
    # Review artifacts
    review_md = feature_dir / "REVIEW.md"
    review_json = feature_dir / "REVIEW.json"
    if review_md.exists():
        _require(review_json, findings, "Missing REVIEW.json contract for REVIEW.md")
        if review_json.exists():
            try:
                r = _load_json(review_json)
                if isinstance(r, dict):
                    if "schemaVersion" not in r:
                        findings.append(Finding("WARN", "REVIEW.json missing schemaVersion (recommended).", str(review_json)))
                    schema_version = r.get("schemaVersion")
                    # New schema (v3+): validate securityFindings, performanceFindings, patternCompliance
                    if (
                        isinstance(schema_version, int)
                        and not isinstance(schema_version, bool)
                        and schema_version >= 3
                    ):
                        for field in ("securityFindings", "performanceFindings", "patternCompliance"):
                            val = r.get(field)
                            if val is None:
                                lvl = "ERROR" if operating_principles_level == "error" else "WARN"
                                findings.append(
                                    Finding(lvl, f"REVIEW.json schemaVersion>=3 requires {field} array.", str(review_json))
                                )
                            elif not isinstance(val, list):
                                findings.append(
                                    Finding("WARN", f"REVIEW.json {field} should be an array.", str(review_json))
                                )
                    if two_stage_review_level != "off":
                        stage_lvl = _policy_level_to_finding(two_stage_review_level)
                        if not (
                            isinstance(schema_version, int)
                            and not isinstance(schema_version, bool)
                            and schema_version >= 4
                        ):
                            findings.append(
                                Finding(
                                    stage_lvl,
                                    "REVIEW.json must set schemaVersion>=4 when twoStageReview policy is enabled.",
                                    str(review_json),
                                )
                            )
                        else:
                            stage_reviews = r.get("stageReviews")
                            verify_lvl = _policy_level_to_finding(verification_before_completion_level)
                            expected_stages = ["spec-compliance", "code-quality"]
                            if not isinstance(stage_reviews, list) or len(stage_reviews) < 2:
                                findings.append(
                                    Finding(
                                        stage_lvl,
                                        "REVIEW.json schemaVersion>=4 requires stageReviews[spec-compliance, code-quality].",
                                        str(review_json),
                                    )
                                )
                            else:
                                for idx, expected in enumerate(expected_stages):
                                    if idx >= len(stage_reviews):
                                        findings.append(
                                            Finding(
                                                stage_lvl,
                                                f"REVIEW.json missing stageReviews[{idx}] for {expected}.",
                                                str(review_json),
                                            )
                                        )
                                        continue
                                    stage_review = stage_reviews[idx]
                                    if not isinstance(stage_review, dict):
                                        findings.append(
                                            Finding(
                                                stage_lvl,
                                                f"REVIEW.json stageReviews[{idx}] must be an object.",
                                                str(review_json),
                                            )
                                        )
                                        continue

                                    stage_name = stage_review.get("stage")
                                    if stage_name != expected:
                                        findings.append(
                                            Finding(
                                                stage_lvl,
                                                f"REVIEW.json stageReviews[{idx}].stage should be {expected!r}.",
                                                str(review_json),
                                            )
                                        )

                                    status = stage_review.get("status")
                                    if status not in {"pending", "pass", "warn", "fail"}:
                                        findings.append(
                                            Finding(
                                                stage_lvl,
                                                f"REVIEW.json stageReviews[{idx}].status must be pending|pass|warn|fail.",
                                                str(review_json),
                                            )
                                        )

                                    stage_findings = stage_review.get("findings")
                                    if not isinstance(stage_findings, list):
                                        findings.append(
                                            Finding(
                                                stage_lvl,
                                                f"REVIEW.json stageReviews[{idx}].findings should be an array.",
                                                str(review_json),
                                            )
                                        )

                                    evidence = stage_review.get("evidence")
                                    if verification_before_completion_level != "off":
                                        if not isinstance(evidence, list):
                                            findings.append(
                                                Finding(
                                                    verify_lvl,
                                                    f"REVIEW.json stageReviews[{idx}].evidence should be an array.",
                                                    str(review_json),
                                                )
                                            )
                                        elif status in {"pass", "warn", "fail"} and not evidence:
                                            findings.append(
                                                Finding(
                                                    verify_lvl,
                                                    f"REVIEW.json stageReviews[{idx}] completed status requires evidence entries.",
                                                    str(review_json),
                                                )
                                            )
                    # Old schema (v1-v2): accept silently for backward compat
            except Exception:
                pass

    # CI verification artifacts
    vci_md = feature_dir / "VERIFICATION-CI.md"
    vci_json = feature_dir / "VERIFICATION-CI.json"
    if vci_md.exists():
        _require(vci_json, findings, "Missing VERIFICATION-CI.json contract for VERIFICATION-CI.md")
        if vci_json.exists():
            try:
                vc = _load_json(vci_json)
                if isinstance(vc, dict) and "schemaVersion" not in vc:
                    findings.append(Finding("WARN", "VERIFICATION-CI.json missing schemaVersion (recommended).", str(vci_json)))
            except Exception:
                pass

    # Human verification artifacts
    v_md = feature_dir / "VERIFICATION.md"
    v_json = feature_dir / "VERIFICATION.json"
    if v_md.exists():
        _require(v_json, findings, "Missing VERIFICATION.json contract for VERIFICATION.md")
        if v_json.exists():
            try:
                vh = _load_json(v_json)
                if isinstance(vh, dict) and "schemaVersion" not in vh:
                    findings.append(Finding("WARN", "VERIFICATION.json missing schemaVersion (recommended).", str(v_json)))
            except Exception:
                pass


def _validate_feature_lifecycle_and_freshness(
    *,
    feature_dir: Path,
    context_md: Path,
    context_json: Path,
    plan_nums: set[str],
    summary_nums: set[str],
    plan_files_by_num: dict[str, set[str]],
    summary_change_files_by_num: dict[str, set[str]],
    freshness: dict[str, Any],
    findings: list[Finding],
) -> None:
    """Cross-link and freshness checks across CONTEXT/PLAN/SUMMARY/REVIEW."""
    review_md = feature_dir / "REVIEW.md"

    if review_md.exists() and not summary_nums:
        findings.append(
            Finding(
                "WARN",
                "REVIEW.md exists without any SUMMARY artifacts (missing summary->review link).",
                str(review_md),
            )
        )

    if plan_nums and not context_md.exists():
        findings.append(
            Finding(
                "WARN",
                "Feature has PLAN artifacts but no CONTEXT.md (missing context->plan link).",
                str(feature_dir),
            )
        )

    for num in sorted(summary_nums):
        if num not in plan_nums:
            findings.append(
                Finding(
                    "ERROR",
                    f"Found {num}-SUMMARY.md without matching {num}-PLAN.md.",
                    str(feature_dir / f"{num}-SUMMARY.md"),
                )
            )

    for num in sorted(plan_nums):
        if num not in summary_nums:
            continue
        planned = plan_files_by_num.get(num, set())
        changed = summary_change_files_by_num.get(num, set())
        if not planned or not changed:
            continue
        outside = sorted(changed - planned)
        if outside:
            sample = ", ".join(outside[:5])
            findings.append(
                Finding(
                    "WARN",
                    f"{num}-SUMMARY.json records files outside {num}-PLAN.json task files: {sample}",
                    str(feature_dir / f"{num}-SUMMARY.json"),
                )
            )

    if summary_nums and not review_md.exists():
        newest_summary_dt: datetime | None = None
        for num in summary_nums:
            dt = _artifact_time(
                feature_dir / f"{num}-SUMMARY.md",
                feature_dir / f"{num}-SUMMARY.json",
            )
            if dt is not None and (newest_summary_dt is None or dt > newest_summary_dt):
                newest_summary_dt = dt
        if newest_summary_dt is not None:
            age = _age_days(newest_summary_dt)
            threshold = int(freshness.get("summaryMaxAgeDaysWithoutReview", 7))
            if age is not None and age > threshold:
                findings.append(
                    Finding(
                        "WARN",
                        f"Feature has SUMMARY artifacts but no REVIEW.md and latest summary is {age} days old (> {threshold}).",
                        str(feature_dir),
                    )
                )

    if not freshness.get("enabled", True):
        return

    if context_md.exists() and not plan_nums:
        age = _age_days(_artifact_time(context_md, context_json))
        threshold = int(freshness.get("contextMaxAgeDays", 30))
        if age is not None and age > threshold:
            findings.append(
                Finding(
                    "WARN",
                    f"CONTEXT exists without any PLAN and is {age} days old (> {threshold}).",
                    str(context_md),
                )
            )

    for num in sorted(plan_nums):
        if num in summary_nums:
            continue
        age = _age_days(
            _artifact_time(
                feature_dir / f"{num}-PLAN.md",
                feature_dir / f"{num}-PLAN.json",
            )
        )
        threshold = int(freshness.get("planMaxAgeDaysWithoutSummary", 14))
        if age is not None and age > threshold:
            findings.append(
                Finding(
                    "WARN",
                    f"{num}-PLAN has no SUMMARY and is {age} days old (> {threshold}).",
                    str(feature_dir / f"{num}-PLAN.md"),
                )
            )


def _validate_quick_tasks(root: Path, findings: list[Finding], touched) -> None:
    """Validate quick task directories."""
    for quick_dir in _iter_quick_dirs(root):
        if not touched(quick_dir):
            continue
        if not QUICK_DIR_RE.match(quick_dir.name):
            findings.append(
                Finding(
                    "ERROR",
                    "Quick task directory must be NNN-slug (e.g. 001-fix-typo).",
                    str(quick_dir),
                )
            )
        plan_md = quick_dir / "PLAN.md"
        plan_json = quick_dir / "PLAN.json"
        if plan_md.exists():
            _require(plan_json, findings, "Missing PLAN.json contract for quick PLAN.md")
            if plan_json.exists():
                try:
                    qc = _load_json(plan_json)
                    _validate_quick_contract(qc, findings, plan_json)
                except Exception as e:
                    findings.append(Finding("ERROR", f"Failed to parse quick plan contract: {e}", str(plan_json)))
        summary_md = quick_dir / "SUMMARY.md"
        summary_json = quick_dir / "SUMMARY.json"
        if summary_md.exists():
            _require(summary_json, findings, "Missing SUMMARY.json contract for quick SUMMARY.md")
        if summary_json.exists():
            try:
                sc = _load_json(summary_json)
                _validate_quick_summary(sc, findings, summary_json)
            except Exception as e:
                findings.append(Finding("ERROR", f"Failed to parse quick summary contract: {e}", str(summary_json)))


def _validate_research(root: Path, findings: list[Finding], touched) -> None:
    """Validate research artifact directories."""
    for rdir in _iter_research_dirs(root):
        if not touched(rdir):
            continue
        rmd = rdir / "RESEARCH.md"
        rjson = rdir / "RESEARCH.json"
        if rmd.exists():
            _require(rjson, findings, "Missing RESEARCH.json contract for RESEARCH.md")
            if rjson.exists():
                try:
                    r = _load_json(rjson)
                    if not isinstance(r, dict):
                        findings.append(Finding("ERROR", "RESEARCH.json must be a JSON object.", str(rjson)))
                    else:
                        if "schemaVersion" not in r:
                            findings.append(Finding("WARN", "RESEARCH.json missing schemaVersion (recommended).", str(rjson)))
                        sources = r.get("sources")
                        if sources is not None and not isinstance(sources, list):
                            findings.append(Finding("WARN", "RESEARCH.json: sources should be an array.", str(rjson)))
                except Exception as e:
                    findings.append(Finding("ERROR", f"Failed to parse RESEARCH.json: {e}", str(rjson)))


def _validate_shape_artifacts(root: Path, findings: list[Finding], touched) -> None:
    """Validate initiative-level shape artifacts, including legacy brainstorms."""
    for idir in _iter_ideas_dirs(root):
        if not touched(idir):
            continue

        shape_md = idir / "SHAPE.md"
        shape_json = idir / "SHAPE.json"
        if shape_md.exists():
            _require(shape_json, findings, "Missing SHAPE.json contract for SHAPE.md")
        if shape_json.exists():
            try:
                shape_contract = _load_json(shape_json)
                _validate_shape_contract(root, idir, shape_contract, findings, shape_json)
            except Exception as e:
                findings.append(Finding("ERROR", f"Failed to parse SHAPE.json: {e}", str(shape_json)))

        bmd = idir / "BRAINSTORM.md"
        bjson = idir / "BRAINSTORM.json"
        if bmd.exists():
            _require(bjson, findings, "Missing BRAINSTORM.json contract for BRAINSTORM.md")
        if bjson.exists():
            try:
                legacy_contract = _load_json(bjson)
                _validate_legacy_brainstorm_contract(legacy_contract, findings, bjson)
            except Exception as e:
                findings.append(Finding("ERROR", f"Failed to parse BRAINSTORM.json: {e}", str(bjson)))


def _validate_shape_contract(
    root: Path,
    idea_dir: Path,
    contract: Any,
    findings: list[Finding],
    path: Path,
) -> None:
    if not isinstance(contract, dict):
        findings.append(Finding("ERROR", "SHAPE.json must be a JSON object.", str(path)))
        return

    if "schemaVersion" not in contract:
        findings.append(Finding("WARN", "SHAPE.json missing schemaVersion (recommended).", str(path)))

    slug = contract.get("slug")
    if _is_nonempty_str(slug):
        slug = slug.strip()
        if slug != idea_dir.name:
            findings.append(
                Finding(
                    "WARN",
                    f"SHAPE.json slug {slug!r} does not match directory slug {idea_dir.name!r}.",
                    str(path),
                )
            )
        if not FEATURE_SLUG_RE.match(slug):
            findings.append(Finding("WARN", "SHAPE.json slug should be kebab-case.", str(path)))
    else:
        findings.append(Finding("WARN", "SHAPE.json should include non-empty slug.", str(path)))

    for field in ("initiative", "problem"):
        if not _is_nonempty_str(contract.get(field)):
            findings.append(Finding("WARN", f"SHAPE.json should include non-empty {field}.", str(path)))

    for field in ("constraints", "globalDecisions", "researchRefs", "openQuestions"):
        val = contract.get(field)
        if val is not None and not isinstance(val, list):
            findings.append(Finding("WARN", f"SHAPE.json: {field} should be an array.", str(path)))
    _validate_decision_log(contract.get("decisionLog"), findings, path)
    _validate_shape_threads(contract.get("shapeThreads"), findings, path)
    _validate_next_shape_moves(contract.get("nextShapeMoves"), findings, path)

    candidate_features = contract.get("candidateFeatures")
    if candidate_features is not None and not isinstance(candidate_features, list):
        findings.append(Finding("WARN", "SHAPE.json: candidateFeatures should be an array.", str(path)))
        candidate_features = []

    seen_feature_slugs: set[str] = set()
    if isinstance(candidate_features, list):
        for idx, candidate in enumerate(candidate_features, start=1):
            label = f"candidateFeatures[{idx}]"
            if not isinstance(candidate, dict):
                findings.append(Finding("ERROR", f"SHAPE.json: {label} should be an object.", str(path)))
                continue

            candidate_slug = candidate.get("slug")
            if not _is_nonempty_str(candidate_slug):
                findings.append(Finding("ERROR", f"SHAPE.json: {label}.slug should be a non-empty string.", str(path)))
                continue
            candidate_slug = candidate_slug.strip()
            if not FEATURE_SLUG_RE.match(candidate_slug):
                findings.append(Finding("ERROR", f"SHAPE.json: {label}.slug should be kebab-case.", str(path)))
            if candidate_slug in seen_feature_slugs:
                findings.append(Finding("ERROR", f"SHAPE.json: duplicate candidate feature slug {candidate_slug!r}.", str(path)))
            seen_feature_slugs.add(candidate_slug)

            for field in ("displayName", "userOutcome", "scopeSummary", "readinessReason", "handoffSummary"):
                if not _is_nonempty_str(candidate.get(field)):
                    findings.append(Finding("WARN", f"SHAPE.json: {label}.{field} should be a non-empty string.", str(path)))
            for field in ("dependencies", "risks"):
                if not isinstance(candidate.get(field), list):
                    findings.append(Finding("WARN", f"SHAPE.json: {label}.{field} should be an array.", str(path)))

            status = candidate.get("status")
            if status not in SHAPE_CANDIDATE_STATUSES:
                findings.append(
                    Finding(
                        "ERROR",
                        f"SHAPE.json: {label}.status should be one of {sorted(SHAPE_CANDIDATE_STATUSES)}.",
                        str(path),
                    )
                )
            elif status == "discuss-ready":
                stub_md = root / "docs" / "planning" / "work" / "features" / candidate_slug / "FEATURE.md"
                stub_json = root / "docs" / "planning" / "work" / "features" / candidate_slug / "FEATURE.json"
                if not stub_md.exists():
                    findings.append(
                        Finding(
                            "ERROR",
                            (
                                f"SHAPE.json candidate {candidate_slug!r} is discuss-ready but missing feature stub "
                                f"{stub_md.relative_to(root)}."
                            ),
                            str(path),
                        )
                    )
                if not stub_json.exists():
                    findings.append(
                        Finding(
                            "ERROR",
                            (
                                f"SHAPE.json candidate {candidate_slug!r} is discuss-ready but missing feature stub "
                                f"{stub_json.relative_to(root)}."
                            ),
                            str(path),
                        )
                    )

    recommended_sequence = contract.get("recommendedSequence")
    if recommended_sequence is not None:
        if not isinstance(recommended_sequence, list):
            findings.append(Finding("WARN", "SHAPE.json: recommendedSequence should be an array.", str(path)))
        else:
            for idx, slug_value in enumerate(recommended_sequence, start=1):
                if not _is_nonempty_str(slug_value):
                    findings.append(
                        Finding(
                            "WARN",
                            f"SHAPE.json: recommendedSequence[{idx}] should be a non-empty string.",
                            str(path),
                        )
                    )
                    continue
                if seen_feature_slugs and slug_value.strip() not in seen_feature_slugs:
                    findings.append(
                        Finding(
                            "WARN",
                            f"SHAPE.json: recommendedSequence references unknown candidate slug {slug_value!r}.",
                            str(path),
                        )
                    )


def _validate_legacy_brainstorm_contract(contract: Any, findings: list[Finding], path: Path) -> None:
    if not isinstance(contract, dict):
        findings.append(Finding("ERROR", "BRAINSTORM.json must be a JSON object.", str(path)))
        return

    if "schemaVersion" not in contract:
        findings.append(Finding("WARN", "BRAINSTORM.json missing schemaVersion (recommended).", str(path)))
    if contract.get("candidates") is not None and not isinstance(contract.get("candidates"), list):
        findings.append(Finding("WARN", "BRAINSTORM.json: candidates should be an array.", str(path)))
    if contract.get("recommendation") is not None and not isinstance(contract.get("recommendation"), dict):
        findings.append(Finding("WARN", "BRAINSTORM.json: recommendation should be an object.", str(path)))


def _validate_decision_log(entries: Any, findings: list[Finding], path: Path) -> None:
    if entries is None:
        return
    if not isinstance(entries, list):
        findings.append(Finding("WARN", "SHAPE.json: decisionLog should be an array.", str(path)))
        return
    for idx, entry in enumerate(entries, start=1):
        label = f"decisionLog[{idx}]"
        if not isinstance(entry, dict):
            findings.append(Finding("WARN", f"SHAPE.json: {label} should be an object.", str(path)))
            continue
        for field in ("title", "decision"):
            if not _is_nonempty_str(entry.get(field)):
                findings.append(Finding("WARN", f"SHAPE.json: {label}.{field} should be a non-empty string.", str(path)))
        rationale = entry.get("rationale")
        if rationale is not None and not _is_nonempty_str(rationale):
            findings.append(Finding("WARN", f"SHAPE.json: {label}.rationale should be a non-empty string.", str(path)))


def _validate_shape_threads(entries: Any, findings: list[Finding], path: Path) -> None:
    if entries is None:
        return
    if not isinstance(entries, list):
        findings.append(Finding("WARN", "SHAPE.json: shapeThreads should be an array.", str(path)))
        return
    for idx, entry in enumerate(entries, start=1):
        label = f"shapeThreads[{idx}]"
        if not isinstance(entry, dict):
            findings.append(Finding("WARN", f"SHAPE.json: {label} should be an object.", str(path)))
            continue
        for field in ("title", "summary", "status"):
            if not _is_nonempty_str(entry.get(field)):
                findings.append(Finding("WARN", f"SHAPE.json: {label}.{field} should be a non-empty string.", str(path)))
        related_features = entry.get("relatedFeatures")
        if related_features is not None and not isinstance(related_features, list):
            findings.append(Finding("WARN", f"SHAPE.json: {label}.relatedFeatures should be an array.", str(path)))
        elif isinstance(related_features, list):
            for rf_idx, value in enumerate(related_features, start=1):
                if not _is_nonempty_str(value):
                    findings.append(
                        Finding(
                            "WARN",
                            f"SHAPE.json: {label}.relatedFeatures[{rf_idx}] should be a non-empty string.",
                            str(path),
                        )
                    )


def _validate_next_shape_moves(entries: Any, findings: list[Finding], path: Path) -> None:
    if entries is None:
        return
    if not isinstance(entries, list):
        findings.append(Finding("WARN", "SHAPE.json: nextShapeMoves should be an array.", str(path)))
        return
    for idx, value in enumerate(entries, start=1):
        if not _is_nonempty_str(value):
            findings.append(Finding("WARN", f"SHAPE.json: nextShapeMoves[{idx}] should be a non-empty string.", str(path)))


def _validate_shape_feedback(entries: Any, findings: list[Finding], path: Path) -> None:
    if entries is None:
        return
    if not isinstance(entries, list):
        findings.append(Finding("WARN", "CONTEXT.json: shapeFeedback should be an array.", str(path)))
        return
    for idx, entry in enumerate(entries, start=1):
        label = f"shapeFeedback[{idx}]"
        if isinstance(entry, str):
            if not entry.strip():
                findings.append(Finding("WARN", f"CONTEXT.json: {label} should be a non-empty string.", str(path)))
            continue
        if not isinstance(entry, dict):
            findings.append(Finding("WARN", f"CONTEXT.json: {label} should be an object or non-empty string.", str(path)))
            continue
        if not _is_nonempty_str(entry.get("summary")):
            findings.append(Finding("WARN", f"CONTEXT.json: {label}.summary should be a non-empty string.", str(path)))
        suggested_action = entry.get("suggestedAction")
        if suggested_action is not None and not _is_nonempty_str(suggested_action):
            findings.append(Finding("WARN", f"CONTEXT.json: {label}.suggestedAction should be a non-empty string.", str(path)))
        affected_features = entry.get("affectedFeatures")
        if affected_features is not None and not isinstance(affected_features, list):
            findings.append(Finding("WARN", f"CONTEXT.json: {label}.affectedFeatures should be an array.", str(path)))
        elif isinstance(affected_features, list):
            for af_idx, value in enumerate(affected_features, start=1):
                if not _is_nonempty_str(value):
                    findings.append(
                        Finding(
                            "WARN",
                            f"CONTEXT.json: {label}.affectedFeatures[{af_idx}] should be a non-empty string.",
                            str(path),
                        )
                    )


def _validate_feature_stub_contract(
    root: Path,
    feature_dir: Path,
    contract: Any,
    findings: list[Finding],
    path: Path,
) -> None:
    if not isinstance(contract, dict):
        findings.append(Finding("ERROR", "FEATURE.json must be a JSON object.", str(path)))
        return

    if "schemaVersion" not in contract:
        findings.append(Finding("WARN", "FEATURE.json missing schemaVersion (recommended).", str(path)))

    feature = contract.get("feature")
    if _is_nonempty_str(feature):
        if feature != feature_dir.name:
            findings.append(
                Finding(
                    "WARN",
                    f"FEATURE.json feature {feature!r} does not match directory slug {feature_dir.name!r}.",
                    str(path),
                )
            )
    else:
        findings.append(Finding("WARN", "FEATURE.json should include non-empty feature.", str(path)))

    for field in ("displayName", "userOutcome", "scopeSummary", "readinessReason", "handoffSummary"):
        if not _is_nonempty_str(contract.get(field)):
            findings.append(Finding("WARN", f"FEATURE.json should include non-empty {field}.", str(path)))
    for field in ("dependencies", "risks"):
        if not isinstance(contract.get(field), list):
            findings.append(Finding("WARN", f"FEATURE.json: {field} should be an array.", str(path)))

    status = contract.get("status")
    if status not in SHAPE_CANDIDATE_STATUSES:
        findings.append(
            Finding(
                "ERROR",
                f"FEATURE.json status should be one of {sorted(SHAPE_CANDIDATE_STATUSES)}.",
                str(path),
            )
        )

    parent_shape = contract.get("parentShape")
    if parent_shape is not None:
        _validate_contract_link(root, parent_shape, findings, path, field_name="parentShape", required_timestamp=True)
        _warn_if_link_stale(root, parent_shape, findings, path, field_name="parentShape", target_label="SHAPE artifact")


def _validate_contract_link(
    root: Path,
    link: Any,
    findings: list[Finding],
    contract_path: Path,
    *,
    field_name: str,
    required_timestamp: bool,
) -> None:
    if not isinstance(link, dict):
        findings.append(Finding("WARN", f"{contract_path.name}: {field_name} should be an object.", str(contract_path)))
        return

    raw_path = link.get("path")
    if not _is_nonempty_str(raw_path):
        findings.append(Finding("WARN", f"{contract_path.name}: {field_name}.path should be a non-empty string.", str(contract_path)))
    else:
        resolved = _resolve_contract_ref(root, raw_path.strip())
        if not resolved.exists():
            findings.append(
                Finding(
                    "WARN",
                    f"{contract_path.name}: {field_name}.path not found: {raw_path}",
                    str(contract_path),
                )
            )

    raw_timestamp = link.get("timestamp")
    if required_timestamp and _parse_ts(raw_timestamp) is None:
        findings.append(
            Finding(
                "WARN",
                f"{contract_path.name}: {field_name}.timestamp should be an ISO-8601 string.",
                str(contract_path),
            )
        )

    schema_version = link.get("schemaVersion")
    if schema_version is not None and not isinstance(schema_version, int):
        findings.append(
            Finding(
                "WARN",
                f"{contract_path.name}: {field_name}.schemaVersion should be an integer.",
                str(contract_path),
            )
        )


def _warn_if_link_stale(
    root: Path,
    link: Any,
    findings: list[Finding],
    contract_path: Path,
    *,
    field_name: str,
    target_label: str,
) -> None:
    if not isinstance(link, dict):
        return
    raw_path = link.get("path")
    raw_timestamp = link.get("timestamp")
    if not _is_nonempty_str(raw_path):
        return
    recorded_ts = _parse_ts(raw_timestamp)
    if recorded_ts is None:
        return
    actual_ts = _linked_artifact_time(root, raw_path.strip())
    if actual_ts is None:
        return
    if actual_ts > recorded_ts:
        findings.append(
            Finding(
                "WARN",
                (
                    f"{contract_path.name}: {field_name} is stale; linked {target_label} changed "
                    "after this artifact was last refreshed."
                ),
                str(contract_path),
            )
        )


def _validate_worktree_session(root: Path, findings: list[Finding]) -> None:
    """Validate .cnogo/worktree-session.json schema if it exists."""
    session_path = root / ".cnogo" / "worktree-session.json"
    if not session_path.exists():
        return
    try:
        data = _load_json(session_path)
    except Exception as e:
        findings.append(Finding("ERROR", f"Failed to parse worktree-session.json: {e}", str(session_path)))
        return
    if not isinstance(data, dict):
        findings.append(Finding("ERROR", "worktree-session.json must be a JSON object.", str(session_path)))
        return

    # Keep in sync with scripts/memory/worktree.py
    valid_phases = {"setup", "executing", "merging", "merged", "verified", "cleaned"}
    valid_worktree_statuses = {"created", "executing", "completed", "merged", "conflict", "cleaned"}

    sv = data.get("schemaVersion")
    if not isinstance(sv, int):
        findings.append(Finding("WARN", "worktree-session.json: schemaVersion should be an integer.", str(session_path)))
    for field in ("feature", "planNumber", "baseCommit", "baseBranch"):
        val = data.get(field)
        if not isinstance(val, str):
            findings.append(Finding("WARN", f"worktree-session.json: {field} should be a string.", str(session_path)))
    phase = data.get("phase")
    if not isinstance(phase, str) or phase not in valid_phases:
        findings.append(Finding("WARN", f"worktree-session.json: phase should be one of {sorted(valid_phases)}.", str(session_path)))
    for arr_field in ("worktrees", "mergeOrder", "mergedSoFar"):
        val = data.get(arr_field)
        if not isinstance(val, list):
            findings.append(Finding("WARN", f"worktree-session.json: {arr_field} should be an array.", str(session_path)))

    worktrees = data.get("worktrees")
    if isinstance(worktrees, list):
        for i, wt in enumerate(worktrees, start=1):
            if not isinstance(wt, dict):
                findings.append(Finding("WARN", f"worktree-session.json: worktrees[{i}] should be an object.", str(session_path)))
                continue
            st = wt.get("status")
            if not isinstance(st, str) or st not in valid_worktree_statuses:
                findings.append(
                    Finding(
                        "WARN",
                        f"worktree-session.json: worktrees[{i}].status should be one of {sorted(valid_worktree_statuses)}.",
                        str(session_path),
                    )
                )


def _validate_token_budgets(
    root: Path,
    findings: list[Finding],
    touched: Callable[[Path], bool],
    budgets: dict[str, Any],
) -> None:
    """Warn on markdown artifacts that exceed configured word budgets."""
    if not budgets.get("enabled", True):
        return

    command_word_max = int(budgets.get("commandWordMax", DEFAULT_TOKEN_BUDGETS["commandWordMax"]))
    commands_total_word_max = int(
        budgets.get("commandsTotalWordMax", DEFAULT_TOKEN_BUDGETS["commandsTotalWordMax"])
    )
    context_word_max = int(budgets.get("contextWordMax", DEFAULT_TOKEN_BUDGETS["contextWordMax"]))
    plan_word_max = int(budgets.get("planWordMax", DEFAULT_TOKEN_BUDGETS["planWordMax"]))
    summary_word_max = int(budgets.get("summaryWordMax", DEFAULT_TOKEN_BUDGETS["summaryWordMax"]))
    review_word_max = int(budgets.get("reviewWordMax", DEFAULT_TOKEN_BUDGETS["reviewWordMax"]))
    research_word_max = int(budgets.get("researchWordMax", DEFAULT_TOKEN_BUDGETS["researchWordMax"]))
    shape_word_max = int(
        budgets.get(
            "shapeWordMax",
            budgets.get("brainstormWordMax", DEFAULT_TOKEN_BUDGETS["shapeWordMax"]),
        )
    )
    brainstorm_word_max = int(budgets.get("brainstormWordMax", DEFAULT_TOKEN_BUDGETS["brainstormWordMax"]))

    word_cache: dict[Path, int] = {}

    def words_for(path: Path) -> int:
        cached = word_cache.get(path)
        if cached is not None:
            return cached
        val = _word_count(path)
        word_cache[path] = val
        return val

    def check_path(path: Path, max_words: int, label: str) -> None:
        if not path.exists() or not path.is_file() or not touched(path):
            return
        words = words_for(path)
        if words > max_words:
            findings.append(
                Finding(
                    "WARN",
                    f"{label} is {words} words (budget {max_words}). Consider trimming for context efficiency.",
                    str(path),
                )
            )

    # Command artifacts
    cmd_dir = root / ".claude" / "commands"
    command_files = sorted(p for p in cmd_dir.glob("*.md") if p.is_file())
    command_total = 0
    any_command_touched = False
    for path in command_files:
        words = words_for(path)
        command_total += words
        if touched(path):
            any_command_touched = True
            if words > command_word_max:
                findings.append(
                    Finding(
                        "WARN",
                        (
                            f"Command artifact is {words} words "
                            f"(budget {command_word_max}). Consider trimming for context efficiency."
                        ),
                        str(path),
                    )
                )
    if any_command_touched and command_total > commands_total_word_max:
        findings.append(
            Finding(
                "WARN",
                f"Command artifact set totals {command_total} words (budget {commands_total_word_max}).",
                str(cmd_dir),
            )
        )

    # Feature artifacts
    for fdir in _iter_feature_dirs(root):
        if not touched(fdir):
            continue
        check_path(fdir / "FEATURE.md", context_word_max, "Feature stub artifact")
        check_path(fdir / "CONTEXT.md", context_word_max, "Feature CONTEXT artifact")
        check_path(fdir / "REVIEW.md", review_word_max, "Feature REVIEW artifact")
        for plan in fdir.glob("*-PLAN.md"):
            check_path(plan, plan_word_max, "Feature PLAN artifact")
        for summary in fdir.glob("*-SUMMARY.md"):
            check_path(summary, summary_word_max, "Feature SUMMARY artifact")

    # Quick-task artifacts
    quick_root = root / "docs" / "planning" / "work" / "quick"
    if quick_root.exists() and touched(quick_root):
        for qdir in quick_root.iterdir():
            if not qdir.is_dir():
                continue
            if not touched(qdir):
                continue
            check_path(qdir / "PLAN.md", plan_word_max, "Quick PLAN artifact")
            check_path(qdir / "SUMMARY.md", summary_word_max, "Quick SUMMARY artifact")

    # Research and ideas artifacts
    for rdir in _iter_research_dirs(root):
        if not touched(rdir):
            continue
        check_path(rdir / "RESEARCH.md", research_word_max, "Research artifact")
    for idir in _iter_ideas_dirs(root):
        if not touched(idir):
            continue
        check_path(idir / "SHAPE.md", shape_word_max, "Shape artifact")
        check_path(idir / "BRAINSTORM.md", brainstorm_word_max, "Brainstorm artifact")


def _validate_bootstrap_context(
    root: Path,
    findings: list[Finding],
    bootstrap_cfg: dict[str, Any],
) -> None:
    """Always-on checks for baseline context footprint."""
    if not bootstrap_cfg.get("enabled", True):
        return

    checks = [
        (root / "CLAUDE.md", int(bootstrap_cfg.get("rootClaudeWordMax", DEFAULT_BOOTSTRAP_CONTEXT["rootClaudeWordMax"])), "Root CLAUDE.md"),
        (
            root / ".claude" / "CLAUDE.md",
            int(bootstrap_cfg.get("workflowClaudeWordMax", DEFAULT_BOOTSTRAP_CONTEXT["workflowClaudeWordMax"])),
            "Workflow CLAUDE.md",
        ),
    ]
    for path, max_words, label in checks:
        if not path.exists() or not path.is_file():
            continue
        words = _word_count(path)
        if words > max_words:
            findings.append(
                Finding(
                    "WARN",
                    f"{label} is {words} words (budget {max_words}). Consider slimming baseline context.",
                    str(path),
                )
            )

    command_set_word_max = int(
        bootstrap_cfg.get(
            "commandSetWordMax",
            DEFAULT_BOOTSTRAP_CONTEXT["commandSetWordMax"],
        )
    )
    cmd_dir = root / ".claude" / "commands"
    if cmd_dir.exists() and cmd_dir.is_dir():
        total = 0
        for path in cmd_dir.glob("*.md"):
            if path.is_file():
                total += _word_count(path)
        if total > command_set_word_max:
            findings.append(
                Finding(
                    "WARN",
                    f"Command artifact set totals {total} words (bootstrap budget {command_set_word_max}).",
                    str(cmd_dir),
                )
            )


_SKILL_REF_RE = re.compile(r"`?\.claude/skills/([^`\s]+\.md)`?")
_AGENT_REF_RE = re.compile(r"`?\.claude/agents/([^`\s]+\.md)`?")
_SPAWN_SCOUT_LINE_RE = re.compile(r"^- `(?P<name>shape-scout|architecture-scout|risk-challenger)` -> (?P<mapping>.+)$", re.MULTILINE)


def _validate_skills(
    root: Path,
    findings: list[Finding],
    touched: Callable[[Path], bool],
) -> None:
    """Validate skill/agent frontmatter and command cross-references."""
    skills_dir = root / ".claude" / "skills"
    if skills_dir.is_dir():
        # (1) Check all skill files have valid frontmatter (name field)
        for md_path in _iter_skill_paths(skills_dir):
            if not touched(md_path):
                continue
            info = _parse_skill_frontmatter(md_path)
            if info["name"] is None:
                findings.append(
                    Finding(
                        "WARN",
                        f"Skill file missing frontmatter 'name' field.",
                        str(md_path),
                    )
                )

    agents_dir = root / ".claude" / "agents"
    if agents_dir.is_dir():
        for md_path in sorted(agents_dir.glob("*.md")):
            if not touched(md_path):
                continue
            info = _parse_skill_frontmatter(md_path)
            if info["name"] is None:
                findings.append(
                    Finding(
                        "WARN",
                        "Agent file missing frontmatter 'name' field.",
                        str(md_path),
                    )
                )

    # (2) Check command skill references resolve to existing files
    cmd_dir = root / ".claude" / "commands"
    if not cmd_dir.is_dir():
        return
    for cmd_path in sorted(cmd_dir.glob("*.md")):
        if not touched(cmd_path):
            continue
        try:
            text = cmd_path.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in _SKILL_REF_RE.finditer(text):
            skill_file = m.group(1)
            skill_path = root / ".claude" / "skills" / skill_file
            if not skill_path.exists():
                findings.append(
                    Finding(
                        "WARN",
                        f"Skill reference '.claude/skills/{skill_file}' not found.",
                        str(cmd_path),
                    )
                )
        for m in _AGENT_REF_RE.finditer(text):
            agent_file = m.group(1)
            agent_path = root / ".claude" / "agents" / agent_file
            if not agent_path.exists():
                findings.append(
                    Finding(
                        "WARN",
                        f"Agent reference '.claude/agents/{agent_file}' not found.",
                        str(cmd_path),
                    )
                )
        if cmd_path.name == "spawn.md":
            for match in _SPAWN_SCOUT_LINE_RE.finditer(text):
                mapping = match.group("mapping")
                if ".claude/skills/" in mapping:
                    findings.append(
                        Finding(
                            "WARN",
                            f"Scout specialization `{match.group('name')}` should map only to a read-only agent, not shared skills.",
                            str(cmd_path),
                        )
                    )
        if cmd_path.name == "shape.md" and "/spawn research <task>" in text:
            findings.append(
                Finding(
                    "WARN",
                    "Shape workspace should use `/research` directly instead of `/spawn research <task>` to preserve a single-writer flow.",
                    str(cmd_path),
                )
            )


def validate_repo(
    root: Path,
    *,
    staged_only: bool,
    feature_filter: str | None = None,
) -> list[Finding]:
    findings: list[Finding] = []

    cfg = _load_workflow_config(root)
    _validate_workflow_config(cfg, findings, root)
    shape = _detect_repo_shape(root, cfg)
    monorepo_scope_level = _get_monorepo_scope_level(cfg)
    operating_principles_level = _get_operating_principles_level(cfg)
    tdd_mode_level = _get_tdd_mode_level(cfg)
    verification_before_completion_level = _get_verification_before_completion_level(cfg)
    two_stage_review_level = _get_two_stage_review_level(cfg)
    packages_cfg = _packages_from_cfg(cfg)
    freshness_cfg = _freshness_cfg(cfg)
    token_budgets_cfg = _token_budgets_cfg(cfg)
    bootstrap_context_cfg = _bootstrap_context_cfg(cfg)

    # Core files
    _require(root / "docs" / "planning" / "PROJECT.md", findings, "Missing planning doc PROJECT.md")
    _validate_memory_runtime(root, findings)
    _require(root / "docs" / "planning" / "ROADMAP.md", findings, "Missing planning doc ROADMAP.md")

    if staged_only:
        if not _is_git_repo(root):
            findings.append(Finding("ERROR", "--staged requires a git repository.", str(root)))
            return findings
        staged = [p.resolve() for p in _staged_files(root)]
        touched_cache: dict[Path, bool] = {}

        def _contains_path(base: Path, target: Path) -> bool:
            try:
                target.relative_to(base)
                return True
            except ValueError:
                return False

        def touched(path: Path) -> bool:
            resolved = path.resolve()
            cached = touched_cache.get(resolved)
            if cached is not None:
                return cached
            try:
                for f in staged:
                    if f == resolved or _contains_path(resolved, f):
                        touched_cache[resolved] = True
                        return True
                touched_cache[resolved] = False
                return False
            except Exception:
                touched_cache[resolved] = False
                return False
    else:
        def touched(_path: Path) -> bool:
            return True

    _validate_features(
        root,
        findings,
        touched,
        shape,
        monorepo_scope_level,
        operating_principles_level,
        tdd_mode_level,
        verification_before_completion_level,
        two_stage_review_level,
        packages_cfg,
        freshness_cfg,
        feature_filter=feature_filter,
    )
    if feature_filter is None:
        _validate_quick_tasks(root, findings, touched)
        _validate_research(root, findings, touched)
        _validate_shape_artifacts(root, findings, touched)
        _validate_worktree_session(root, findings)
        _validate_token_budgets(root, findings, touched, token_budgets_cfg)
        _validate_bootstrap_context(root, findings, bootstrap_context_cfg)
        _validate_skills(root, findings, touched)

    return findings


# --- Baseline infrastructure (Contract 09) ---

_BASELINE_FILE = "validate-baseline.json"
_LATEST_FILE = "validate-latest.json"
_CNOGO_DIR = ".cnogo"


def _finding_to_warning(f: Finding) -> dict[str, Any]:
    """Convert a Finding to a baseline warning dict with stable signature."""
    file_part = f.path or ""
    raw = f"{f.level}|{file_part}|{f.message}"
    sig = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return {
        "level": f.level,
        "file": f.path,
        "message": f.message,
        "signature": sig,
    }


def save_baseline(warnings: list[dict[str, Any]], root: Path) -> Path:
    """Write warnings to .cnogo/validate-baseline.json, sorted by signature."""
    out_dir = root / _CNOGO_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / _BASELINE_FILE
    sorted_warnings = sorted(warnings, key=lambda w: w.get("signature", ""))
    path.write_text(
        json.dumps(sorted_warnings, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_baseline(root: Path) -> list[dict[str, Any]] | None:
    """Read .cnogo/validate-baseline.json. Returns None if missing."""
    path = root / _CNOGO_DIR / _BASELINE_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else None
    except (json.JSONDecodeError, OSError):
        return None


def _save_latest(warnings: list[dict[str, Any]], root: Path) -> None:
    """Write current warnings snapshot to .cnogo/validate-latest.json."""
    out_dir = root / _CNOGO_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / _LATEST_FILE
    sorted_warnings = sorted(warnings, key=lambda w: w.get("signature", ""))
    path.write_text(
        json.dumps(sorted_warnings, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def diff_baselines(
    baseline: list[dict[str, Any]], current: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """Compare baseline and current warnings by signature.

    Returns {new, resolved, unchanged}.
    """
    base_sigs = {w["signature"]: w for w in baseline}
    curr_sigs = {w["signature"]: w for w in current}

    new = [w for sig, w in curr_sigs.items() if sig not in base_sigs]
    resolved = [w for sig, w in base_sigs.items() if sig not in curr_sigs]
    unchanged = [w for sig, w in curr_sigs.items() if sig in base_sigs]

    return {"new": new, "resolved": resolved, "unchanged": unchanged}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate workflow planning artifacts.")
    parser.add_argument("--root", default=".", help="Repo root (defaults to current directory).")
    parser.add_argument("--staged", action="store_true", help="Validate only areas touched by staged changes.")
    parser.add_argument("--feature", help="Validate only one feature slug under docs/planning/work/features/.")
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON.")
    parser.add_argument("--save-baseline", action="store_true", help="Save current warnings as baseline.")
    parser.add_argument("--diff-baseline", action="store_true", help="Diff current warnings against saved baseline.")
    args = parser.parse_args()

    root = _repo_root(Path(args.root))
    findings = validate_repo(
        root,
        staged_only=args.staged,
        feature_filter=(args.feature.strip() if isinstance(args.feature, str) and args.feature.strip() else None),
    )
    warnings = [_finding_to_warning(f) for f in findings]

    # --save-baseline: capture and save
    if args.save_baseline:
        path = save_baseline(warnings, root)
        print(f"Baseline saved: {path} ({len(warnings)} warnings)")
        return 0

    # --diff-baseline: compare against saved baseline
    if args.diff_baseline:
        baseline = load_baseline(root)
        if baseline is None:
            print("No baseline found. Run with --save-baseline first.")
            return 1
        result = diff_baselines(baseline, warnings)
        print("## Validation Diff")
        print(f"\nNew warnings ({len(result['new'])}):")
        for w in result["new"]:
            loc = f" ({w['file']})" if w.get("file") else ""
            print(f"  [{w['level']}]{loc} {w['message']}")
        print(f"\nResolved warnings ({len(result['resolved'])}):")
        for w in result["resolved"]:
            loc = f" ({w['file']})" if w.get("file") else ""
            print(f"  [{w['level']}]{loc} {w['message']}")
        print(f"\nUnchanged warnings ({len(result['unchanged'])}):")
        for w in result["unchanged"]:
            loc = f" ({w['file']})" if w.get("file") else ""
            print(f"  [{w['level']}]{loc} {w['message']}")
        _save_latest(warnings, root)
        return 1 if result["new"] else 0

    # Normal validation output
    if args.json:
        print(
            json.dumps(
                [
                    {"level": f.level, "message": f.message, "path": f.path}
                    for f in findings
                ],
                indent=2,
                sort_keys=True,
            )
        )
    else:
        if not findings:
            print("✅ Workflow validation passed")
        else:
            for f in findings:
                print(f.format())

    # Always save latest snapshot
    _save_latest(warnings, root)

    errors = [f for f in findings if f.level == "ERROR"]
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
