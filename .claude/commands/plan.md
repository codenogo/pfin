# Plan: $ARGUMENTS
<!-- effort: medium -->

Create small implementation plans for a feature.

## Your Task

`$ARGUMENTS` must be the feature slug matching `docs/planning/work/features/<feature-slug>/`. If the user gives only a display name, route through `/discuss` first.

## Steps

1. **Branch**
   - Check `git branch --show-current` and `git status --porcelain`.
   - Planning must run on `feature/$ARGUMENTS`.
   - If a switch is needed and the tree is dirty, stop and ask the user to stash or commit.
   - If the branch is missing, stop and send the user to `/discuss` first.
   - Optional cleanup: prune merged branches and remotes.

2. **Load context**
   - Run `python3 .cnogo/scripts/workflow_memory.py phase-get $ARGUMENTS`; expected phase is `discuss` or `plan`.
   - Read `docs/planning/work/features/$ARGUMENTS/CONTEXT.json`.
   - Run `python3 .cnogo/scripts/workflow_memory.py prime --limit 5`.
   - Optional: `python3 .cnogo/scripts/workflow_memory.py graph-suggest-scope --keywords "<keywords>" --files "<relatedCode>" --json` to help choose task `files[]`.

3. **Partition work**
   Split by boundary, layer, or risk. Use `.claude/skills/workflow-contract-integrity.md` and `.claude/skills/artifact-token-budgeting.md`.

4. **Write `NN-PLAN.json`**
   - Create `docs/planning/work/features/$ARGUMENTS/NN-PLAN.json` as source of truth.
   - Required fields: `schemaVersion`, `feature`, `planNumber`, `goal`, `tasks[]`, `planVerify[]`, `commitMessage`, `timestamp`.
   - `tasks.length <= 3`.
   - Each task needs `files[]`, `action`, `verify[]`, `microSteps[]`, and `tdd`.
   - `tdd` is either `required=true` with failing/passing verify commands or `required=false` with a reason.
   - `blockedBy` uses zero-based task indices.
   - `deletions` is optional; if used, it should leave a later task to absorb cleanup scope.

5. **Render `NN-PLAN.md`**
   Run `python3 .cnogo/scripts/workflow_render.py docs/planning/work/features/$ARGUMENTS/NN-PLAN.json`, then make only small readability edits in Markdown.

6. **Optional memory**
   If memory is initialized, run `python3 .cnogo/scripts/workflow_memory.py phase-set $ARGUMENTS plan`. Optionally create task issues with `python3 .cnogo/scripts/workflow_memory.py create ... --plan NN`.

7. **Validate**
   Run `python3 .cnogo/scripts/workflow_validate.py --feature $ARGUMENTS`.

## Output

- plans created (`NN-PLAN.json` and `NN-PLAN.md`)
- execution order and dependencies
- which plans can run in parallel
