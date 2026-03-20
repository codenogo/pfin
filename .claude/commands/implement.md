# Implement: $ARGUMENTS
<!-- effort: medium -->

Execute a plan with verification.

## Arguments

`/implement <feature> <plan-number> [--team]`

## Your Task

Execute the specified plan for `$ARGUMENTS`.

## Steps

1. **Branch**
   - Check `git branch --show-current` and `git status --porcelain`.
   - Work must run on `feature/<feature-slug>`.
   - If the branch exists but the tree is dirty, stop before switching.
   - If the branch is missing, stop and tell the user to run `/discuss` first.
   - Optional cleanup: prune merged branches and remotes.

2. **Load contracts**
   - Run `python3 .cnogo/scripts/workflow_memory.py phase-get <feature-slug>`; expected phase is `plan` or `implement`.
   - Read `docs/planning/work/features/<feature>/<NN>-PLAN.json` and `NN-PLAN.md`.
   - If memory is enabled, run `python3 .cnogo/scripts/workflow_memory.py ready --feature <feature-slug>` and `python3 .cnogo/scripts/workflow_memory.py phase-set <feature-slug> implement`.
   - If `--team` is passed or the plan sets `parallelizable: true`, route to `/team implement` and fall back to serial if needed.
   - Build TaskDescV2 objects via `plan_to_task_descriptions(plan_path, root)`.

3. **Execute each task**
   - Skip tasks marked `skipped`.
   - Follow `micro_steps` in order and honor the `tdd` contract.
   - If `task_id` exists, run `python3 .cnogo/scripts/workflow_memory.py claim <task-id> --actor implementer`.
   - Edit only files in `task["file_scope"]["paths"]`.
   - Run task `verify[]`; optional `python3 .cnogo/scripts/workflow_memory.py graph-validate-scope ...` is advisory.
   - On success, run `python3 .cnogo/scripts/workflow_memory.py report-done <task-id> --actor implementer`; on failure, run `python3 .cnogo/scripts/workflow_memory.py checkpoint --feature <feature-slug>`, inspect `python3 .cnogo/scripts/workflow_memory.py history <task-id>`, fix, and retry up to 2 times before stopping.
   - Workers never close issues. Use footer `TASK_DONE: [cn-xxx, ...]` when needed.

4. **Plan verification**
   - Run all `planVerify[]` commands.
   - If they pass and memory is enabled, run `python3 .cnogo/scripts/workflow_memory.py phase-set <feature-slug> review`.

5. **Commit**
   - `git add -A`
   - `git commit -m "<commitMessage from plan>"`

6. **Summary + validation**
   - Write `<NN>-SUMMARY.json` with `schemaVersion`, `feature`, `planNumber`, `outcome`, `changes[]`, `verification[]`, `commit`, and `timestamp`.
   - Render with `workflow_render.py`.
   - Apply `.claude/skills/workflow-contract-integrity.md`.
   - Run `python3 .cnogo/scripts/workflow_validate.py --feature <feature-slug>`.

## Output

- completed tasks and verification outcomes
- commit hash and message
- ready for `/review`
