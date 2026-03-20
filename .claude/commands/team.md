# Team: $ARGUMENTS
<!-- effort: high -->

Coordinate multi-agent work with explicit task boundaries and worktree sessions.

## Arguments

`/team create <task>`  
`/team implement <feature> <plan>`  
`/team status`  
`/team message <teammate> <msg>`  
`/team dismiss`

## Your Task

0. Verify Agent Teams is enabled in `.claude/settings.json` (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`).

1. Parse action from `$ARGUMENTS`.

## Action: `create`

1. Split request into specialized teammates (small team, clear file boundaries, no overlap).
2. Create team + tasks via TeamCreate/TaskCreate.
3. Spawn teammates with deterministic specialization->skill mapping from `/spawn`.
4. For architecture/contract-heavy tasks, include `.claude/skills/workflow-contract-integrity.md` in lead or reviewer prompts.
5. For safety-critical tasks, include `.claude/skills/boundary-and-sdk-enforcement.md`.
6. If memory initialized, create an epic issue tagged `team`.

## Action: `implement`

1. Parse `<feature>` and `<plan>`. Verify phase (`phase-get`).
2. Load plan JSON. Generate run_id via `bridge.generate_run_id(feature)`.
3. Generate TaskDescV2 list via `bridge.plan_to_task_descriptions()`. Run `detect_file_conflicts()` (advisory).
4. Create worktree session. Set phase to `implement`.
5. Create TaskCreate entries (two-pass: create, then wire blockedBy).
6. Spawn one implementer per task via `bridge.generate_implement_prompt(taskdesc, actor_name=...)`.
   Leader is orchestration-only: do not execute task implementation or verify commands.
   Require footer protocol: `TASK_EVIDENCE: {...}` then `TASK_DONE: [cn-...]`.

**Guaranteed lifecycle — try/finally:**
```
try:
  7. Monitor TaskList. Poll stalls via `workflow_memory.py stalled`.
     For stalled tasks: takeover + spawn replacement implementer.
  8. Leader reconciliation via `reconcile_leader.reconcile(epic_id)`.
  9. Merge branches: `workflow_memory.py session-merge`. Resolver agent on conflict (max 2 retries).
  10. Run planVerify, then `/review` staged gate. Stop if `fail`.
  11. Write summary artifacts, commit, set phase `review`.
finally:
  12. Cleanup: `workflow_memory.py session-cleanup` + `workflow_validate.py`.
  13. Dismiss team via TeamDelete.
```

## Action: `status`

Report active teammates, task states, blockers, and next unblock action.

## Action: `message`

Send teammate message and confirm delivery.

## Action: `dismiss`

Request teammate shutdown, wait for confirmation, then TeamDelete.

## Output

- Team state summary
- Task/blocker snapshot
- Any merge/conflict incidents and resolution status
