# Resume
<!-- effort: low -->

Restore context from the latest handoff and current memory/git state.

## Your Task

### Step 1: Load Handoff + Memory Summary

```bash
cat docs/planning/work/HANDOFF.md 2>/dev/null || echo "No handoff file"
python3 .cnogo/scripts/workflow_memory.py prime --limit 8
python3 .cnogo/scripts/workflow_memory.py checkpoint
python3 .cnogo/scripts/workflow_memory.py ready --limit 10
```

### Step 2: Verify Git State

```bash
git branch --show-current
git status --porcelain
git stash list
```

If stash was referenced in handoff and needed:

```bash
git stash pop
```

### Step 3: Rehydrate Working Context

Open only files mentioned in handoff or active task metadata. Avoid broad file loading.

### Step 4: Team/Worktree Recovery Check (If Relevant)

If resuming team execution:

```bash
python3 .cnogo/scripts/workflow_memory.py list --type epic --status in_progress --limit 5
python3 .cnogo/scripts/workflow_memory.py session-status
python3 .cnogo/scripts/workflow_memory.py session-reconcile
```

This auto-closes any memory issues whose worktrees were already merged/cleaned, fixing orphaned state from context compaction.

If reconcile found orphaned issues, they are now closed. Check memory status with `python3 .cnogo/scripts/workflow_memory.py prime`.

If an active worktree session exists, continue with `/team implement <feature> <plan>`; otherwise continue with normal `/implement`.

### Step 5: Confirm Next Action

Summarize:
- where execution stopped
- current readiness (clean/dirty tree, ready tasks)
- exact next command

## Output

- Restored context summary
- One explicit next step
