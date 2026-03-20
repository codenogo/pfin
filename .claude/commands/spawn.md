# Spawn: $ARGUMENTS
<!-- effort: medium -->

Launch a focused subagent with specialization-specific guidance.

## Arguments

`/spawn <specialization> <task>`

Specialization -> skill/agent mapping:
- `security` -> `.claude/skills/security-scan.md`
- `tests` -> `.claude/skills/test-writing.md`
- `perf` -> `.claude/skills/performance-review.md`
- `api` -> `.claude/skills/api-review.md`
- `review` -> `.claude/skills/code-review.md` + `.claude/skills/boundary-and-sdk-enforcement.md`
- `refactor` -> `.claude/skills/refactor-safety.md`
- `debug` -> `.claude/agents/debugger.md` + `.claude/skills/debug-investigation.md`
- `workflow` -> `.claude/skills/workflow-contract-integrity.md`
- `merge` -> `.claude/skills/worktree-merge-recovery.md`
- `memory` -> `.claude/skills/memory-sync-reconciliation.md`
- `verify` -> `.claude/skills/changed-scope-verification.md`
- `artifact` -> `.claude/skills/artifact-token-budgeting.md`
- `boundary` -> `.claude/skills/boundary-and-sdk-enforcement.md`
- `lifecycle` -> `.claude/skills/feature-lifecycle-closure.md`
- `release` -> `.claude/skills/release-readiness.md`
- `shape` -> `.claude/skills/shape-facilitator/SKILL.md` + `.claude/skills/shape-feature-queue/SKILL.md`
- `architecture` -> `.claude/skills/shape-architecture-tradeoffs/SKILL.md`
- `handoff` -> `.claude/skills/context-handoff-engineering/SKILL.md`
- `research` -> `.claude/skills/research-evidence-synthesis/SKILL.md`
- `shape-scout` -> `.claude/agents/shape-scout.md`
- `architecture-scout` -> `.claude/agents/architecture-scout.md`
- `risk-challenger` -> `.claude/agents/risk-challenger.md`

## Your Task

1. Parse specialization and task text from `$ARGUMENTS`.
2. Validate specialization against the mapping above. If invalid, return supported values and do not spawn.
3. Resolve execution mode:
- `debug` uses `subagent_type: debugger`
- `shape-scout` uses `subagent_type: shape-scout`
- `architecture-scout` uses `subagent_type: architecture-scout`
- `risk-challenger` uses `subagent_type: risk-challenger`
- all others use `subagent_type: general-purpose`
4. Load only mapped skill/agent instructions (no unrelated skills).
5. Spawn Task prompt with:
- selected specialization contract
- user task
- expected output format (`SCOUT_REPORT` for shape scouts; otherwise findings/diffs/tests/risks)
- explicit file references if provided by user
6. For multi-skill specializations (for example `review`), apply checklists in order listed.
7. Report launch status and track completion.

## Output

- Subagent type + loaded skill path(s)
- Task summary
- Completion handoff with concrete results
