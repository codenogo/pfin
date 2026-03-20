---
name: worktree-merge-recovery
tags: [workflow, quality, debug]
appliesTo: [spawn]
---
# Worktree Merge Recovery

Use this skill when `session-merge` reports conflicts in team implementation.

## Resolution Tiers

Merge conflicts are resolved automatically where possible, falling back to manual resolution only when needed.

- **Tier 1 — Clean Merge**: `git merge --no-ff` succeeds with no conflicts. Automatic. `resolved_tier: "clean-merge"`
- **Tier 2 — Auto-Resolve (Keep Incoming)**: When files are disjoint across branches, conflict markers are parsed and incoming (agent) changes are kept. Automatic. Gated on `_check_disjoint_files()`. `resolved_tier: "auto-resolve"`
- **Tier 3 — Resolver Agent (Manual)**: When files overlap, the resolver agent performs intent-aware resolution using task descriptions. This is the existing behavior. `resolved_tier: ""`

## Goal

Resolve merge conflicts deterministically, preserve task order, and resume safely.

## Protocol

1. Capture current state:
```bash
python3 .cnogo/scripts/workflow_memory.py session-status --json
python3 .cnogo/scripts/workflow_memory.py session-merge --json
git status --porcelain
```

2. Triage conflict:
- identify `conflictIndex` and `conflictFiles`
- Check `resolvedTier` in the worktree session state — if a branch shows `auto-resolve`, tier 2 already ran. If empty, no automatic resolution was attempted.
- confirm whether conflict is mechanical (format/import/order) or semantic

3. Resolution rules:
- preserve already merged behavior unless conflict proves defect
- prefer smallest edit that satisfies both task intents
- keep change scoped to conflicted files only

4. Verify before retry:
```bash
<task verify commands>
<plan verify commands if available>
```

5. Retry merge:
```bash
python3 .cnogo/scripts/workflow_memory.py session-merge --json
```

6. Retry limits:
- max 2 resolver attempts
- if still blocked: `git merge --abort`, report unresolved conflict with context

## Output

- Conflict root cause
- Resolution applied
- Retry result and remaining risk
