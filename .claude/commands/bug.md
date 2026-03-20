# Bug: $ARGUMENTS
<!-- effort: high -->

Bug workflow router. Helps choose the right path and ensures bugfix work happens safely (branch, regression test guidance, and verification).

## Arguments

`/bug <bug description>`

Example: `/bug "Checkout fails with 500 when coupon is applied"`

## Your Task

Triage "$ARGUMENTS" and route to the right workflow:

### Step 1: Ask Triage Questions (keep it short)

Ask 3–5 questions:

- Severity: **prod outage / degraded / minor**
- Reproducible? steps + frequency
- Scope: single module vs multi-service vs contract/schema
- Risk: security, payments, data integrity?
- Any rollback/feature flag available?

### Step 2: Choose a Path

- **Small + clear fix** → `/quick "$ARGUMENTS"`
- **Unknown root cause / flaky** → `/debug "$ARGUMENTS"`
- **Large/risky (multi-service, contracts, schema, security)** → `/discuss "$ARGUMENTS"` then `/plan <feature-slug>`

### Step 3: Branch Safety (before committing)

Regardless of path, derive a bug slug from `$ARGUMENTS` and ensure branch isolation.

```bash
git branch --show-current
git status --porcelain
```

Rules:
- Target branch is `fix/<slug>`.
- If already on `fix/<slug>`, pull latest: `git pull --ff-only` (ignore failure if no upstream yet), then continue.
- If switching branches is needed and working tree is dirty, stop and ask user to commit/stash first.
- If `fix/<slug>` exists locally, switch and sync: `git switch fix/<slug> && git pull --ff-only` (ignore failure if no upstream yet).
- Else create it from default branch:

```bash
git switch main || git switch master
git pull --ff-only
git switch -c fix/<slug>
```

### Step 4: Regression Test Guidance

If the bug is non-trivial, recommend adding a regression test:

- Use `/tdd` for test-first fixes when feasible
- Or add a targeted unit/integration test in the relevant suite

## Output

- The recommended workflow command to run next
- The suggested branch name (`fix/<slug>`)
- What verification should prove the bug is fixed
