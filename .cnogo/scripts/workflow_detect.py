#!/usr/bin/env python3
"""
Repo detection + workflow bootstrap helpers.

Goals:
- Detect repo shape (single/monorepo/polyglot)
- Detect "packages" (subprojects) by manifest files
- Optionally update docs/planning/WORKFLOW.json packages[]
- Print a per-package quick reference (commands)

No external dependencies.
"""

from __future__ import annotations

try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass  # imported as module; caller manages sys.path

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from workflow_utils import load_json, repo_root, write_json


def find_files(root: Path, name: str) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob(name):
        if ".git" in p.parts:
            continue
        if "node_modules" in p.parts:
            continue
        out.append(p)
    return sorted(out)


@dataclass
class Package:
    name: str
    path: str
    kind: str  # node|java|python|go|rust|other
    commands: dict[str, str]


def guess_kind(dir_path: Path) -> str:
    if (dir_path / "package.json").exists():
        return "node"
    if (dir_path / "pom.xml").exists() or (dir_path / "build.gradle").exists() or (dir_path / "build.gradle.kts").exists():
        return "java"
    if (
        (dir_path / "pyproject.toml").exists()
        or (dir_path / "setup.py").exists()
        or (dir_path / "setup.cfg").exists()
        or (dir_path / "requirements.txt").exists()
        or (dir_path / "Pipfile").exists()
        or (dir_path / "poetry.lock").exists()
    ):
        return "python"
    if (dir_path / "go.mod").exists():
        return "go"
    if (dir_path / "Cargo.toml").exists():
        return "rust"
    return "other"


def _node_commands(dir_path: Path) -> dict[str, str]:
    pkg = dir_path / "package.json"
    cmds: dict[str, str] = {}
    if not pkg.exists():
        return cmds
    try:
        j = load_json(pkg)
        scripts = j.get("scripts", {}) if isinstance(j, dict) else {}
        if isinstance(scripts, dict):
            if "test" in scripts:
                cmds["test"] = "npm test --silent"
            if "lint" in scripts:
                cmds["lint"] = "npm run -s lint"
            if "build" in scripts:
                cmds["build"] = "npm run -s build"
            if "dev" in scripts:
                cmds["run"] = "npm run -s dev"
            if "typecheck" in scripts:
                cmds["typecheck"] = "npm run -s typecheck"
            elif (dir_path / "tsconfig.json").exists():
                cmds["typecheck"] = "npx tsc --noEmit"
            if "format" in scripts:
                cmds["format"] = "npm run -s format"
    except Exception:
        # best-effort only
        pass
    return cmds


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _maven_has_spotless(pom_path: Path) -> bool:
    text = _safe_read_text(pom_path)
    return "spotless-maven-plugin" in text


def _is_maven_aggregator(pom_path: Path) -> bool:
    text = _safe_read_text(pom_path).lower()
    if "<packaging>pom</packaging>" in text:
        return True
    if "<modules>" in text and "</modules>" in text:
        return True
    return False


def _gradle_has_spotless(dir_path: Path) -> bool:
    for name in ("build.gradle", "build.gradle.kts"):
        path = dir_path / name
        if path.exists() and "spotless" in _safe_read_text(path).lower():
            return True
    return False


def _java_commands(dir_path: Path) -> dict[str, str]:
    cmds: dict[str, str] = {}
    pom_path = dir_path / "pom.xml"
    if pom_path.exists():
        if _is_maven_aggregator(pom_path):
            return cmds
        cmds["test"] = "mvn -q test -DskipITs"
        cmds["build"] = "mvn -q -DskipTests package"
        if _maven_has_spotless(pom_path):
            cmds["format"] = "mvn -q spotless:apply"
            cmds["lint"] = "mvn -q spotless:check"
        return cmds
    if (dir_path / "build.gradle").exists() or (dir_path / "build.gradle.kts").exists():
        cmds["test"] = "./gradlew -q test"
        cmds["build"] = "./gradlew -q build -x test"
        if _gradle_has_spotless(dir_path):
            cmds["format"] = "./gradlew -q spotlessApply"
            cmds["lint"] = "./gradlew -q spotlessCheck"
        return cmds
    return cmds


def _python_commands(dir_path: Path) -> dict[str, str]:
    cmds: dict[str, str] = {}
    if (
        (dir_path / "pyproject.toml").exists()
        or (dir_path / "setup.py").exists()
        or (dir_path / "setup.cfg").exists()
        or (dir_path / "requirements.txt").exists()
        or (dir_path / "Pipfile").exists()
        or (dir_path / "poetry.lock").exists()
    ):
        cmds["test"] = "pytest -q --tb=short"
        cmds["lint"] = "ruff check ."
        cmds["format"] = "python3 -m black . && python3 -m isort ."
    return cmds


def _go_commands(_dir_path: Path) -> dict[str, str]:
    return {"test": "go test ./... -short", "lint": "go vet ./...", "format": "gofmt -w ."}


def _rust_commands(_dir_path: Path) -> dict[str, str]:
    return {"test": "cargo test --quiet", "format": "cargo fmt"}


def build_packages(root: Path) -> list[Package]:
    # Identify candidate package directories by manifest files.
    manifests = []
    for name in [
        "package.json",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "Pipfile",
        "poetry.lock",
        "go.mod",
        "Cargo.toml",
    ]:
        manifests.extend(find_files(root, name))

    dirs = sorted({p.parent for p in manifests})
    pkgs: list[Package] = []
    for d in dirs:
        rel = str(d.relative_to(root)).replace("\\", "/")
        kind = guess_kind(d)
        name = d.name
        commands: dict[str, str] = {}
        if kind == "node":
            commands = _node_commands(d)
        elif kind == "java":
            commands = _java_commands(d)
        elif kind == "python":
            commands = _python_commands(d)
        elif kind == "go":
            commands = _go_commands(d)
        elif kind == "rust":
            commands = _rust_commands(d)
        pkgs.append(Package(name=name, path=rel if rel != "." else ".", kind=kind, commands=commands))

    # If there is a root manifest and also nested ones, keep both; user can prune.
    return pkgs


def detect_shape(pkgs: list[Package]) -> str:
    if len(pkgs) <= 1:
        return "single"
    kinds = {p.kind for p in pkgs if p.kind != "other"}
    if len(kinds) > 1:
        return "polyglot"
    return "monorepo"


def update_workflow_json(root: Path, pkgs: list[Package], *, overwrite: bool) -> None:
    wf = root / "docs" / "planning" / "WORKFLOW.json"
    if not wf.exists():
        raise SystemExit("WORKFLOW.json not found; install the pack first.")
    obj = load_json(wf)
    if not isinstance(obj, dict):
        raise SystemExit("WORKFLOW.json must be a JSON object.")

    packages = []
    for p in pkgs:
        packages.append(
            {
                "name": p.name,
                "path": p.path,
                "kind": p.kind,
                "commands": p.commands,
            }
        )

    if overwrite or not obj.get("packages"):
        obj["packages"] = packages
    else:
        # Merge by path (preserve existing)
        existing = obj.get("packages")
        if not isinstance(existing, list):
            existing = []
        seen = {e.get("path") for e in existing if isinstance(e, dict)}
        for p in packages:
            if p["path"] not in seen:
                existing.append(p)
        obj["packages"] = existing

    # Update repoShape if auto
    if obj.get("repoShape") == "auto":
        obj["repoShape"] = detect_shape(pkgs) if pkgs else "single"

    write_json(wf, obj)


def print_quick_reference(pkgs: list[Package]) -> None:
    print("## Per-Package Quick Reference\n")
    if not pkgs:
        print("_No packages detected._")
        return
    print("| Package | Kind | Path | Build | Test | Lint | Typecheck |")
    print("|--------:|------|------|-------|------|------|----------|")
    for p in pkgs:
        cmds = p.commands
        def f(key: str) -> str:
            return f"`{cmds[key]}`" if key in cmds and cmds[key] else "-"
        print(
            f"| {p.name} | {p.kind} | `{p.path}` | {f('build')} | {f('test')} | {f('lint')} | {f('typecheck')} |"
        )
    print("")


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect repo packages and optionally update WORKFLOW.json.")
    parser.add_argument("--write-workflow", action="store_true", help="Update docs/planning/WORKFLOW.json packages[].")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite packages[] instead of merging.")
    args = parser.parse_args()

    root = repo_root()
    pkgs = build_packages(root)

    print(f"Detected repo shape: {detect_shape(pkgs)}")
    print(f"Detected packages: {len(pkgs)}")
    print("")
    print_quick_reference(pkgs)

    if args.write_workflow:
        update_workflow_json(root, pkgs, overwrite=args.overwrite)
        print("✅ Updated docs/planning/WORKFLOW.json")
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
