# Review
<!-- effort: medium -->

Quality gate before merge.

## Your Task

Review current changes for correctness, safety, and ship readiness.

## Steps

1. **Branch + scope**
   - Check `git branch --show-current` and `git status --porcelain`.
   - Review should run on `feature/<feature-slug>`; if not, stop and tell the user to switch.
   - A dirty tree is a warning, not a blocker.
   - Run `python3 .cnogo/scripts/workflow_memory.py phase-get <feature-slug>`; expected phase is `implement` or `review`.
   - Collect changed files with `git diff --name-only HEAD~1..HEAD 2>/dev/null || git diff --name-only`.

2. **Automated review**
   - Run `python3 .cnogo/scripts/workflow_checks.py review --feature <feature-slug>` when the slug is known, otherwise omit `--feature`.
   - This writes `REVIEW.md` and `REVIEW.json`.
   - Validate with `python3 .cnogo/scripts/workflow_validate.py --json --feature <feature-slug>`.

3. **Stage 1: spec compliance**
   Check:
   - scope and intent vs plan goal
   - contract and lifecycle compliance
   - changed-scope discipline

   Update `REVIEW.json` under `stageReviews[0]` with stage `spec-compliance`, a `pass|warn|fail` status, findings, and evidence.

   If this stage fails, stop and return blockers.

4. **Stage 2: code quality**
   Apply `.claude/skills/performance-review.md` plus code review, security, release-readiness, boundary/SDK, workflow-contract-integrity, and artifact-token-budgeting skills.

   Update `stageReviews[1]`, `securityFindings[]`, `performanceFindings[]`, `patternCompliance[]`, and `principleNotes[]`, then re-run the validator.

5. **Verdict**
   Use the 7-axis rubric from `.claude/skills/performance-review.md`:
   - `pass`: ready for `/ship`
   - `warn`: call out risks and ask whether to proceed
   - `fail`: block merge and list blockers

   If accepted and memory is enabled, run `python3 .cnogo/scripts/workflow_memory.py phase-set <feature-slug> ship`.

## Output

- review verdict (`pass`, `warn`, or `fail`)
- key blockers or warnings with file references
- token-savings summary from automated checks
- clear next action (`fix`, `ship`, or `follow-up`)
