# Pause
<!-- effort: low -->

Create a compact handoff for resuming later.

## Your Task

### Step 1: Capture Current State

```bash
git branch --show-current
git status --porcelain
git stash list
python3 .cnogo/scripts/workflow_memory.py checkpoint
python3 .cnogo/scripts/workflow_memory.py prime --limit 5
```

### Step 2: Write Handoff Note

Create/update `docs/planning/work/HANDOFF.md` with:
- timestamp
- current branch
- what was just completed
- exact next step
- open files or commands to run first
- blockers/risks

Keep it short (8-20 lines).

### Step 3: Optional Stash

If user wants to switch branches:

```bash
git stash push -m "WIP: <feature-or-task>"
```

Record stash reference in `HANDOFF.md`.

### Step 4: Optional Memory Note

If memory is enabled, add a handoff comment to active epic/task:

```bash
python3 .cnogo/scripts/workflow_memory.py list --type epic --status in_progress --limit 3
python3 .cnogo/scripts/workflow_memory.py update <issue-id> --description "<brief handoff note>"
```

## Output

- Confirmation handoff was written
- Resume command: `/resume`
