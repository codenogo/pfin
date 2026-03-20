# Shape: $ARGUMENTS
<!-- effort: high -->

Run a persistent initiative workspace.

## Arguments

`/shape <initiative>`

## Your Task

Treat `/shape` as the workspace for broad or multi-feature work. Keep cross-feature truth here. A `discuss-ready` feature is an available exit from shape, not a stop signal.

1. Load only the essentials:
- `docs/planning/PROJECT.md`
- `docs/planning/WORKFLOW.json`
- existing `docs/planning/work/ideas/<initiative-slug>/SHAPE.json` when re-entering an initiative
- only the needed skills and scout agents: `shape-facilitator`, `shape-feature-queue`, `shape-architecture-tradeoffs`, `shape-risk-challenge`, `context-handoff-engineering`, `shape-scout`, `architecture-scout`, `risk-challenger`

2. Run an iterative shaping conversation:
- clarify users, jobs-to-be-done, success criteria, scope boundaries, constraints, sequencing, and major risks
- revise direction when feasibility, architecture, or sequencing changes
- accept natural-language follow-ups such as split, merge, compare, resequence, promote, park, or reopen
- use `/research "$ARGUMENTS"` only for targeted uncertainty reduction
- do not branch or create feature memory issues here
- end a pass only after persisting workspace state plus next shape moves or optional exits

3. Persist the initiative source of truth:
- `docs/planning/work/ideas/<initiative-slug>/SHAPE.md`
- `docs/planning/work/ideas/<initiative-slug>/SHAPE.json`
- if only legacy `BRAINSTORM.*` exists, read it and migrate forward into `SHAPE.*`

`SHAPE.json` minimum fields:
- `schemaVersion`, `initiative`, `slug`, `problem`, `constraints[]`, `globalDecisions[]`, `researchRefs[]`, `openQuestions[]`, `candidateFeatures[]`, `recommendedSequence[]`, `timestamp`
- each `candidateFeatures[]` entry needs `slug`, `displayName`, `userOutcome`, `scopeSummary`, `dependencies[]`, `risks[]`, `status`, `readinessReason`, `handoffSummary`
- valid `status`: `draft`, `discuss-ready`, `blocked`, `parked`
- optional: `decisionLog[]`, `shapeThreads[]`, `nextShapeMoves[]`

4. Materialize delivery-ready features immediately:
- for each `discuss-ready` candidate, create `docs/planning/work/features/<feature-slug>/FEATURE.md`
- create matching `FEATURE.json` with `parentShape` linkage plus inherited outcome, scope, dependencies, risks, readiness, and handoff fields
- do not create `CONTEXT.*` yet
- leave those features as optional exits; do not imply they must be discussed next

5. Optional scouts:
- never use `/team` inside `/shape`
- stay single-agent
- spawn at most 3 read-only scouts total:
  - `/spawn shape-scout <question>` for fit
  - `/spawn architecture-scout <question>` for option comparison
  - `/spawn risk-challenger <question>` to pressure-test the favored direction
- scouts must not edit artifacts, branch, commit, or touch memory state
- require a concise answer plus final `SCOUT_REPORT: {...}` with `kind`, `question`, `confidence`, `summary`, `implication`, and `sources[]`
- fold back only useful evidence into `SHAPE.*`

6. Validate:
```bash
python3 .cnogo/scripts/workflow_validate.py --json
```

## Output

- initiative workspace summary
- stable cross-feature decisions and active shaping threads
- feature queue snapshot with any `discuss-ready` features that were materialized
- stay-in-shape continuation moves first
- optional exits second: `/discuss <feature-slug>` for any ready feature
