# Background: $ARGUMENTS
<!-- effort: medium -->

Run long, non-interactive tasks without blocking foreground work.

## Arguments

`/background <task description>`  
`/background status`  
`/background cancel <id>`  
`/background entropy`

## Your Task

1. Parse action.
- `status`: list task files and statuses.
- `cancel <id>`: mark task as cancelled.
- `entropy`: generate tiny cleanup tasks from invariant drift.
- Otherwise: start a new background task.

2. Start mode:
- Create `docs/planning/work/background/<timestamp>-TASK.md` with:
  - request
  - status (`Running`)
  - checkpoints
  - log section
- Launch one subagent to execute the task and update that file.
- Require autonomous execution: no interactive questions, clear assumptions, concrete outputs.

3. If memory engine is initialized, track lifecycle:
```bash
python3 .cnogo/scripts/workflow_memory.py create --title "<task>" --type background --labels background
```
Claim on start; close on completion/cancel.

4. Status mode:
- Read `docs/planning/work/background/*-TASK.md`.
- Return id, state, and truncated request.

5. Cancel mode:
- If task file exists, update status to `Cancelled`.
- If memory issue exists, close with reason `cancelled`.

6. Entropy mode:
```bash
python3 .cnogo/scripts/workflow_checks.py entropy --write-task
```
Then launch subagent(s) for generated tiny tasks. Constraints:
- max 3 files/task
- non-behavioral refactors only
- rerun review checks after completion

## Output

- For start: task id + path + how to check status
- For status: table/list of active/recent tasks
- For cancel: confirmation or not-found error
