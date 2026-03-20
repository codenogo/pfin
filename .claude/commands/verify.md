# Verify: $ARGUMENTS
<!-- effort: medium -->

Human acceptance verification (UAT). Confirms the feature works for real user flows.

## When to Use

After implementation, before `/review`.

## Your Task

Verify `$ARGUMENTS` from the user's perspective and record outcomes.

### Step 1: Load Compact Context

Prefer contracts over full markdown to keep context small:

```bash
cat docs/planning/work/features/$ARGUMENTS/CONTEXT.json
ls docs/planning/work/features/$ARGUMENTS/*-SUMMARY.json
python3 .cnogo/scripts/workflow_memory.py checkpoint --feature $ARGUMENTS
```

Only open full `CONTEXT.md`/`*-SUMMARY.md` if contract data is insufficient.

### Step 2: Define Deliverables to Validate

Create a short checklist (3-7 items) of user-observable outcomes:
- happy path
- key edge case
- key failure path

Use:
- `.claude/skills/workflow-contract-integrity.md` for artifact consistency
- `.claude/skills/boundary-and-sdk-enforcement.md` for boundary/SDK correctness on failure analysis

### Step 3: Run Interactive UAT

For each deliverable:
1. Ask user to test it
2. Record result: `pass | fail | partial`
3. Capture concise notes/evidence

If failures occur, capture:
- repro steps
- observed behavior
- expected behavior
- likely impacted files

### Step 4: Persist Verification Artifacts

Write:
- `docs/planning/work/features/$ARGUMENTS/VERIFICATION.json`
- `docs/planning/work/features/$ARGUMENTS/VERIFICATION.md`

`VERIFICATION.json` minimum fields:
- `schemaVersion`
- `feature`
- `timestamp`
- `results[]` (deliverable, status, notes)
- `failed[]` (only failures/partials; include planned fix path)

`VERIFICATION.md` should be a concise human summary of the same results.

### Step 5: If Failures Exist

Create follow-up fix plans under the same feature directory, then route back to implementation.

### Step 6: Validate Workflow

```bash
python3 .cnogo/scripts/workflow_validate.py
```

## Output

- UAT summary by deliverable
- Pass/fail/partial counts
- Follow-up fix plan references (if any)
