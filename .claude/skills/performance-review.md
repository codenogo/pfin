---
name: performance-review
tags: [domain, quality, security, workflow]
appliesTo: [review]
---
# Performance Review (Final Gate)

Deterministic final-gate review for agentic SDLC. Orchestrates sub-skills in sequence with a scoring rubric.

## Inputs (Token-Minimal)

Use pointers, not full contents:

- **diff_ref**: `git diff` ref or commit range
- **run_ledger**: paths to SUMMARY.json / REVIEW.json artifacts
- **validation_paths**: verify command output locations

## Procedure

### Step A: Scope + Intent

Read the plan goal and diff summary. Confirm:
- Changes match the stated plan goal
- No out-of-scope modifications
- Diff size is proportional to task complexity

### Step B: Code Review Checklist

Apply `.claude/skills/code-review.md` sections:
- Security (auth, input validation, secrets, injection, logging)
- Performance (N+1, unbounded, leaks, timeouts)
- Design Patterns (convention alignment, API consistency, minimal abstractions)
- General Quality (clarity, naming, duplication, error handling, test coverage)
- Refactor Safety (behavior preserved, minimal changes, no mixed concerns)

### Step B2: Performance Deep-Dive

Performance checklist:
- Identify hotspot (profile or log timings)
- Complexity check (watch for O(n^2) or worse)
- IO patterns (DB queries, network calls, file reads)
- N+1 query detection
- Caching opportunities (memoization, HTTP cache, query cache)
- Backpressure, retries, and timeout configuration
- Large payload handling (pagination, streaming, compression)
- Connection pooling and resource lifecycle

Process: measure baseline → identify bottleneck → fix → measure after → check regressions

### Step C: Contract Compliance

Check planning artifact and multi-agent safety:
- PLAN.json tasks match actual changes
- SUMMARY.json changes[] align with plan files[]
- Memory phase progression is coherent
- **Multi-agent rules**:
  - Workers/hooks NEVER close PLAN/EPIC/shared issues
  - `SubagentStop` is observer-only (validates footer syntax, no state mutation)
  - Closure is leader-only via reconciliation
  - No `auto-close-parent` semantics

### Step D: Security / OWASP Quick Pass

Apply `.claude/skills/security-scan.md`:
- OWASP Top 10 spot check on changed files
- Auth/AuthZ boundary correctness
- No secrets in code or logs
- Injection risk assessment

### Step E: PRR-lite (Production Readiness)

Apply `.claude/skills/release-readiness.md`:
- Review/verification artifacts exist and are current
- Rollback plan noted
- Docs updated if applicable
- No breaking changes without migration strategy

### Step F: Validation Baseline Diff

Compare verify-before vs verify-after:
- All plan `verify[]` commands pass
- All `planVerify[]` commands pass
- No new warnings introduced (compare validator output)
- Test coverage for changed behavior confirmed

## Scoring Rubric

7 axes, each scored 0-2:

| Axis | 0 = Blocker | 1 = Concern | 2 = Clear |
|------|-------------|-------------|-----------|
| Correctness | Logic error, broken contract | Edge case gap | Verified correct |
| Security | OWASP violation, secret leak | Missing validation | No issues |
| Contract Compliance | Worker closes plan/epic | Missing artifact field | Full compliance |
| Performance | O(n^2) on hot path, unbounded | Missing pagination | Profiled clean |
| Maintainability | God function, no separation | Weak naming | Clean, readable |
| Test Coverage | No tests for changed behavior | Happy-path only | Edge cases covered |
| Scope Discipline | Drive-by refactor, feature creep | Minor tangent | Surgical |

### Pass Rule

- **Pass**: Total >= 11/14, no 0 in Correctness/Security/Contract Compliance
- **Warn**: Total >= 11/14 but has concerns, OR total 9-10
- **Fail**: Total < 9, OR any 0 in Correctness/Security/Contract Compliance

### Verdict Mapping to REVIEW.json

- Rubric scores populate `securityFindings[]`, `performanceFindings[]`, `patternCompliance[]`
- Scoring summary recorded in `principleNotes[]`
- Verdict field: `pass` / `warn` / `fail`

## Output Format

```
## Verdict: PASS|WARN|FAIL (score/14)

### Blockers (score = 0)
- [axis]: description with file:line

### Concerns (score = 1)
- [axis]: description with file:line

### Improvements
- Suggestions that don't block merge

### Evidence
- Verification commands run and results
- Diff statistics

### Next Actions
- Follow-up tasks if any
```
