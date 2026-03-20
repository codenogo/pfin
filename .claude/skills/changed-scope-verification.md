---
name: changed-scope-verification
tags: [workflow, quality, performance]
appliesTo: [verify-ci, spawn]
---
# Changed Scope Verification

Use this skill for fast local verification and deterministic CI verification.

## Goal

Run only necessary checks locally, run full checks in CI, and enforce hard timeouts.

## Rules

1. Scope policy:
- local default: changed-scope checks
- CI default: full checks
- honor `WORKFLOW.json.performance.checkScope`

2. Changed-file behavior:
- default fallback is `none` (no HEAD fallback)
- near-noop when no local changes
- honor `WORKFLOW.json.performance.changedFilesFallback`

3. Timeouts:
- enforce hard timeout for lint/typecheck/test commands
- default 300s unless overridden by `performance.commandTimeoutSec`
- timeout exit code should fail the check

4. Package targeting:
- map changed files to package paths
- skip package checks with explicit reason when untouched

## Commands

```bash
python3 .cnogo/scripts/workflow_checks.py verify-ci <feature>
python3 .cnogo/scripts/workflow_checks.py review --feature <feature>
```

## Output

- Effective scope (changed/all)
- Which packages were run vs skipped
- Failures including timeout details
