# Rollback: $ARGUMENTS
<!-- effort: medium -->

Safely undo changes with explicit confirmation.

## Arguments

`/rollback`  
`/rollback last`  
`/rollback <commit-hash>`  
`/rollback branch` (destructive; explicit opt-in only)

## Your Task

1. Show state before action:
```bash
git branch --show-current
git log --oneline -10
git status --porcelain
```

2. Decide mode:
- No argument: show recent commits and ask which to revert.
- `last`: preview `HEAD` and confirm, then `git revert HEAD --no-edit`.
- `<hash>`: preview commit and confirm, then `git revert <hash> --no-edit`.
- `branch`: destructive reset path, only after user types `DISCARD` exactly.

3. Destructive reset (`branch`) path:
```bash
git fetch origin
git reset --hard origin/main
```
Never run without explicit confirmation.

4. Verify repo health after rollback:
- show new `HEAD`
- run quick project check (build/test command if known)

## Safety Rules

- Prefer `git revert` over history rewrite.
- Never force-push from this command.
- Always show what will change before executing.

## Output

- Action taken
- New commit/hash state
- Verification result
- Recommended next step
