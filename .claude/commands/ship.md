# Ship Current Changes
<!-- effort: high -->

Commit, push, and open a PR after review passes.

## Your Task

### Step 0: Branch Verification (verify-only — do NOT create)

```bash
git branch --show-current
git status --porcelain
```

Rules:
- Refuse to ship from `main/master`.
- Must be on `feature/<feature-slug>`. If not, stop and tell user to switch first.

**Step 0a: Clean up merged branches**

```bash
git branch --merged main | grep -v '^\*\|main' | xargs -r git branch -d
git remote prune origin
```

### Step 1: Phase Check + Preflight

```bash
python3 .cnogo/scripts/workflow_memory.py phase-get <feature-slug>
```

Warn if not in `ship` phase; continue only with confirmation.
- ensure review/verify artifacts are up to date
- require staged review + freshness gate:
```bash
python3 .cnogo/scripts/workflow_checks.py ship-ready --feature <feature-slug>
```
If this fails, stop and return the failing checks.

### Step 2: Commit (if needed)

```bash
git add -A
git commit -m "<conventional-commit-message>"
```
Choose `feat|fix|refactor|docs|test|chore` based on diff.

### Step 3: Push Branch

```bash
git push -u origin $(git branch --show-current)
```

### Step 4: Create PR

```bash
gh pr create --title "<title>" --body "<summary/testing/links>"
```
PR body should include summary, key changes, testing evidence, and planning artifact links.

### Step 5: Memory Sync (if enabled)

```bash
python3 .cnogo/scripts/workflow_memory.py sync
```
If feature IDs are known, close shipped issues and set phase accordingly.

### Step 6: Feature Lifecycle Closure

Apply `.claude/skills/feature-lifecycle-closure.md` checklist before final handoff.

### Step 7: Local Cleanup

Optional local cleanup after confirmation (switch back to main and pull).

## Output

- PR URL
- commit(s) shipped
- verification summary
- any remaining follow-up actions
