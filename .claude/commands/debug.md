# Debug: $ARGUMENTS
<!-- effort: high -->

Structured debugging with an auditable session log.

## Your Task

Debug `$ARGUMENTS` and produce a root-cause-driven fix.

1. Create session folder:
- `docs/planning/work/debug/<timestamp>-<slug>/SESSION.md`
- Record problem statement, symptoms, repro steps, and status.

2. Gather evidence (repo-first):
```bash
rg -n "<error|keyword>" .
git log -p --since="2 weeks ago" -- <suspect-paths>
```
Capture concrete file/line evidence and relevant logs in `SESSION.md`.

3. Build ranked hypotheses:
- hypothesis
- likelihood
- falsifiable test

4. Test hypotheses in order and log each result (`confirmed`, `ruled_out`, `inconclusive`).

5. Identify root cause:
- exact code location(s)
- why behavior occurs
- affected surface area

6. Propose fix options (A/B if needed) and recommended path.

7. Implementation gate:
- Ask for approval before applying fix when risk is non-trivial.
- After approval, implement minimal fix, run focused tests, then broader regression checks.

8. Close session with:
- fix summary
- verification evidence
- prevention actions (tests/guards/docs)
- final status

## Output

- Root cause with file references
- Applied fix and verification commands/results
- Follow-up prevention tasks
- Session artifact path
