# Sync
<!-- effort: medium -->

Sync shared progress across memory and (optionally) Agent Teams.

## Arguments

`/sync`  
`/sync status`  
`/sync message <teammate> <msg>`

## Your Task

1. Parse mode from `$ARGUMENTS`.
- Default and `status`: run memory sync/status path.
- `message`: send to teammate mailbox.

2. Memory sync path (always primary):
```bash
python3 .cnogo/scripts/workflow_memory.py sync
python3 .cnogo/scripts/workflow_memory.py prime
python3 .cnogo/scripts/workflow_memory.py stats
```
This updates `.cnogo/issues.jsonl`, stages it for git, and prints compact context + counts.

3. Agent Teams detection (optional overlay):
- Check `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` and active team config under `~/.claude/teams/*/config.json`.
- If active, append teammate/task summary from TaskList (do not replace memory output).

4. Message mode:
- Parse teammate and message from `$ARGUMENTS`.
- Use `SendMessage`.
- Confirm delivery or show clear failure reason.

## Output

### Default/Status
- Memory sync confirmation
- Prime summary
- Stats (`total/open/in_progress/ready/blocked`)
- If Agent Teams active: teammate/task snapshot

### Message
`Message delivered to <teammate>`

## Notes

- `/sync` is status/coordination only.
- Use `/team` for orchestration and task assignment.
