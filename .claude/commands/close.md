# Close: $ARGUMENTS
<!-- effort: low -->

Post-merge cleanup. Closes memory epic and optionally archives feature artifacts after merge into `main`.

## Arguments

`/close <feature-slug>`

Example: `/close websocket-notifications`

## Your Task

After a feature is merged, close memory epic and clean up artifacts.
Apply `.claude/skills/feature-lifecycle-closure.md` as the closure checklist.

### Step 1: Confirm Merge

Confirm with git:

```bash
git branch --show-current
git log -5 --oneline
```

If the user provides a PR number, include it in notes.

### Step 2: Memory Close

If the memory engine is initialized (`.cnogo/memory.db` exists), close all open issues for this feature:

```bash
python3 -c "
import sys; sys.path.insert(0, '.cnogo')
from scripts.memory import is_initialized, list_issues, close
from pathlib import Path
root = Path('.')
if is_initialized(root):
    issues = list_issues(feature_slug='$ARGUMENTS', root=root)
    closed = 0
    for issue in issues:
        if issue.status != 'closed':
            close(issue.id, reason='shipped', actor='claude', root=root)
            closed += 1
    print(f'Closed {closed} memory issues for $ARGUMENTS')
"
```

Then sync to persist state:

```bash
python3 -c "
import sys; sys.path.insert(0, '.cnogo')
from scripts.memory import is_initialized, sync
from pathlib import Path
root = Path('.')
if is_initialized(root):
    sync(root)
    print('Memory synced')
"
```

### Step 3: Archive Feature Artifacts (Optional)

If user confirms, move:

`docs/planning/work/features/$ARGUMENTS/` → `docs/planning/archive/features/$ARGUMENTS/`

```bash
mkdir -p docs/planning/archive/features
mv "docs/planning/work/features/$ARGUMENTS" "docs/planning/archive/features/$ARGUMENTS"
```

### Step 4: Validate

```bash
python3 .cnogo/scripts/workflow_validate.py
```

## Output

- Memory epic and issues closed
- Whether artifacts were archived
- Next recommended action (`/shape`, `/discuss`, or `/quick`)
