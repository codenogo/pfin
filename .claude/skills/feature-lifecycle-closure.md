---
name: feature-lifecycle-closure
tags: [workflow, release]
appliesTo: [ship, close, spawn]
---
# Feature Lifecycle Closure

Use this skill for `/ship`, `/close`, and phase-completion checks.

## Goal

Close features cleanly across git, artifacts, and memory state.

## Lifecycle Checks

1. Pre-ship:
- review/verification artifacts exist and are current
- branch is not `main/master`
- phase is `ship` or explicitly approved

2. Ship execution:
- commit/push/PR created
- memory sync performed
- phase transition recorded

3. Close execution:
- all open feature issues closed with reason
- `.cnogo/issues.jsonl` synced/staged
- optional archive move completed safely

4. Post-close integrity:
- `workflow_validate.py` passes
- no dangling active worktree session

## Commands

```bash
python3 .cnogo/scripts/workflow_memory.py phase-get <feature>
python3 .cnogo/scripts/workflow_memory.py sync
python3 .cnogo/scripts/workflow_validate.py --json
```

## Output

- Closure checklist status
- Remaining blockers to full closure
- Final next action
