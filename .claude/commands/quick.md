# Quick: $ARGUMENTS
<!-- effort: low -->

Fast path for small fixes with full verification and artifacts.

## When to Use

Use for small, low-risk tasks (typically ≤1 hour, limited file set).

## Your Task

Execute `$ARGUMENTS` with minimal ceremony.

### Step 0: Branch Bootstrap

Derive `<slug>` from `$ARGUMENTS` and ensure the active branch is `fix/<slug>`.

```bash
git branch --show-current
git status --porcelain
```

Rules:
- If already on `fix/<slug>`, pull latest: `git pull --ff-only` (ignore failure if no upstream yet), then continue.
- If switching branches is needed and working tree is dirty, stop and ask user to commit/stash first.
- If `fix/<slug>` exists locally, switch and sync: `git switch fix/<slug> && git pull --ff-only` (ignore failure if no upstream yet).
- Else create it from default branch:

```bash
git switch main || git switch master
git pull --ff-only
git switch -c fix/<slug>
```

### Step 1: Scope

Identify likely files, expected behavior, and verification commands.

**Escalation triggers** — stop and switch to `/discuss` + `/plan` if any:
- Scope exceeds 5 files
- Changes touch core data models or schemas
- Requires migration or breaking API changes
- Risk level is unclear or high

### Step 2: Write Quick Plan Contract

Create:
- `docs/planning/work/quick/NNN-<slug>/PLAN.json`

Minimum fields:
- `schemaVersion`, `id`, `slug`, `goal`, `files[]`, `verify[]`, `timestamp`

Example:

```json
{
  "schemaVersion": 1,
  "id": "001",
  "slug": "fix-typo",
  "goal": "What this accomplishes",
  "files": ["path/to/file.ts"],
  "verify": ["npm test --silent"],
  "timestamp": "2026-01-24T00:00:00Z"
}
```

Render markdown plan:

```bash
python3 .cnogo/scripts/workflow_render.py docs/planning/work/quick/NNN-<slug>/PLAN.json
```

### Step 3: Implement + Verify

- Make the change
- Run task verify commands
- Run any targeted tests for impacted behavior

### Step 4: Write Summary Contract

Create:
- `docs/planning/work/quick/NNN-<slug>/SUMMARY.json`

Minimum fields:
- `schemaVersion`, `id`, `slug`, `outcome`, `changes[]`, `verification[]`, `commit`, `timestamp`

Render markdown summary:

```bash
python3 .cnogo/scripts/workflow_render.py docs/planning/work/quick/NNN-<slug>/SUMMARY.json
```

### Step 5: Optional Memory Tracking

If memory is initialized:

```bash
python3 .cnogo/scripts/workflow_memory.py create "$ARGUMENTS" --type quick --feature <feature-slug-if-known>
```

Then close when done:

```bash
python3 .cnogo/scripts/workflow_memory.py close <issue-id> --reason completed
```

### Step 6: Commit

```bash
git add -A
git commit -m "fix([scope]): $ARGUMENTS"
```

### Step 7: Validate

```bash
python3 .cnogo/scripts/workflow_validate.py
```

## Output

- What changed
- Verification results
- Ready for `/ship` or follow-up `/quick`
