# TDD: $ARGUMENTS
<!-- effort: high -->

Implement via strict test-first workflow. This is the deep mode of cnogo's core TDD principle.

## Your Task

1. Understand behavior contract:
- read relevant plan/context artifacts
- define expected inputs, outputs, and failure modes

2. Write tests first:
- happy path
- edge/boundary cases
- invalid/error cases
- integration seams where relevant
- keep microsteps action-only (no minute/time-box estimates)

3. Run focused tests and confirm they fail for the right reason.
Stop if they pass unexpectedly and explain why. Do not continue with implementation until RED is verified.

4. Approval gate:
- show failing tests summary
- ask user to proceed before implementation when requested workflow requires explicit approval

5. Implement minimal code to satisfy tests.
- iterate one failing test at a time
- refactor only after green
- do not rationalize skips ("too small", "probably fine", "seems fine")

6. Run verification:
- focused suite
- broader affected suite

7. Produce summary artifact with:
- tests added
- files changed
- behavior covered
- known gaps
- explicit failing->passing evidence (commands + outputs)

8. Validate workflow artifacts:
```bash
python3 .cnogo/scripts/workflow_validate.py
```

9. Commit with conventional message (`test(...)` and/or `feat/fix(...)`).

## Output

- failing->passing test progression
- implementation summary
- verification commands/results
- ready-for-review status
