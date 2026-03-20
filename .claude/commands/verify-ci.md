# Verify CI: $ARGUMENTS
<!-- effort: medium -->

Non-interactive verification for CI/nightly/pre-merge.

## Arguments

`/verify-ci <feature>`

## Your Task

Run automated verification for `$ARGUMENTS` and persist machine-checkable artifacts.

### Step 1: Quick Sanity Check

```bash
ls docs/planning/work/features/$ARGUMENTS >/dev/null
```

If the feature directory does not exist, stop and ask for the correct slug.

### Step 2: Run Package-Aware Verification (Primary Path)

Use `.claude/skills/changed-scope-verification.md` as the execution policy (changed-scope locally, full-scope in CI, hard timeouts).

```bash
python3 .cnogo/scripts/workflow_checks.py verify-ci $ARGUMENTS
```

If `WORKFLOW.json` has empty `packages[]`, the checker auto-runs:
`python3 .cnogo/scripts/workflow_detect.py --write-workflow`
then continues.

This writes:
- `docs/planning/work/features/$ARGUMENTS/VERIFICATION-CI.md`
- `docs/planning/work/features/$ARGUMENTS/VERIFICATION-CI.json`
- Includes token telemetry (`tokenTelemetry`) and compact output with optional `fullOutputPath` hints for failed checks.

If no packages are configured in `WORKFLOW.json`, checks are recorded as skipped (artifact still written).

If artifact drift appears, apply `.claude/skills/workflow-contract-integrity.md` before re-running verification.

### Step 3: Validate Workflow Artifacts

```bash
python3 .cnogo/scripts/workflow_validate.py
```

## Output

- Overall CI status (lint/types/tests/invariants)
- Token-savings summary from automated checks
- Location of written artifacts
- Recommended next action (`/review`, fix failures, or update WORKFLOW packages)
