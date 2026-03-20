# Doctor
<!-- effort: low -->

Run unified diagnostic checks on the cnogo workflow environment. Use this to verify system health before starting work or to diagnose issues.

## Your Task

Run the doctor diagnostic command and interpret results.

### Step 1: Run Diagnostics

```bash
python3 .cnogo/scripts/workflow_checks.py doctor
```

For machine-readable output:

```bash
python3 .cnogo/scripts/workflow_checks.py doctor --json
```

### Step 2: Interpret Results

The doctor runs 6 checks:

1. **Workflow Validation** — Verifies `WORKFLOW.json` and planning contracts are valid. Fix with `/validate`.
2. **Memory DB Integrity** — Runs `PRAGMA integrity_check` on `.cnogo/memory.db`. If failing, re-initialize with `python3 .cnogo/scripts/workflow_memory.py init`.
3. **Orphaned Worktrees** — Detects git worktrees not tracked by any active session. Clean up with `git worktree remove <path>`.
4. **Stale Issues** — Finds open, unassigned issues older than 30 days. Review with `python3 .cnogo/scripts/workflow_memory.py list --status open`.
5. **Hook Config Sanity** — Checks `.claude/settings.json` hook script paths exist on disk.
6. **Git State** — Warns on a dirty worktree, detached HEAD, or excess merged branches.

Status meanings:
- **pass**: Check completed successfully, no issues found.
- **warn**: Non-critical issue detected. Review but safe to continue.
- **fail**: Critical issue that should be fixed before proceeding.

### Step 3: Remediation

- If all checks pass/warn: environment is healthy.
- If any check fails: report the failing check details and suggest the specific fix listed above.

## Output

- Per-check pass/warn/fail status with details
- Summary of environment health
- Recommended next action if issues found
