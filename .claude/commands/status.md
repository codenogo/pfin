# Status
<!-- effort: low -->

Show current position, progress, and next actions.

## Your Task

### Step 1: Memory Status (Primary)

```bash
python3 .cnogo/scripts/workflow_memory.py prime --limit 8
python3 .cnogo/scripts/workflow_memory.py stats
```

If memory is not initialized, report that and continue with git/artifact status.

### Step 2: Git Status

```bash
git branch --show-current
git status --porcelain
git log origin/main..HEAD --oneline 2>/dev/null || echo "No remote tracking"
git log -5 --oneline
```

### Step 3: Artifact Status

```bash
ls docs/planning/work/features/ 2>/dev/null
ls docs/planning/work/quick/ 2>/dev/null | tail -10
```

If team execution is active, recommend `/team status` for detailed teammate progress.

### Step 4: Summarize

Report:
- current branch + dirty/clean state
- active feature/plan progress from memory
- commits ahead of remote
- token optimization drift from `python3 .cnogo/scripts/workflow_checks.py discover --since-days 7` (optional)
- immediate next action

### Step 5: Recommended Next Command

Choose one:
- `/implement <feature> <plan>` when mid-plan
- `/review` when implementation is complete
- `/ship` when review passed
- `/discuss <feature>` or `/quick <task>` when idle

## Output

Concise status summary plus one recommended next step.
