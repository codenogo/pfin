---
name: workflow-contract-integrity
tags: [workflow, quality]
appliesTo: [shape, brainstorm, discuss, review, plan, verify-ci, verify, implement, team, spawn]
---
# Workflow Contract Integrity

Use this skill when authoring or reviewing planning artifacts.

## Goal

Keep planning contracts and rendered markdown aligned with no lifecycle drift.

## Checks

1. Contract validity:
- `SHAPE.json`, `FEATURE.json`,
- `CONTEXT.json`, `*-PLAN.json`, `*-SUMMARY.json`, `REVIEW.json` parse cleanly
- required fields exist and are non-empty

2. Shape integrity:
- `candidateFeatures[]` use unique slugs
- `candidateFeatures[].status` is `draft|discuss-ready|blocked|parked`
- every `discuss-ready` candidate has a matching `FEATURE.md/.json` stub
- `recommendedSequence[]` references known candidate slugs
- optional rich workspace fields (`decisionLog[]`, `shapeThreads[]`, `nextShapeMoves[]`) stay well-formed and additive

3. Plan integrity:
- max 3 tasks per plan
- each task has explicit `files[]`, `action`, `verify[]`
- for `schemaVersion >= 2`: each task has non-empty `microSteps[]` (no time-box/minute fields)
- for `schemaVersion >= 2`: each task has `tdd.required`; if true, failing/passing verify commands; if false, non-rationalized reason
- dependency indices are valid and acyclic

4. Summary integrity:
- `changes[].file` are declared in corresponding plan task `files[]`
- if extra files were touched intentionally, update plan contract to reflect reality

5. Cross-link integrity:
- `FEATURE.json` links back to its parent `SHAPE.json`
- `CONTEXT.json` references `parentShape` / `featureStub` when inherited from shape
- `CONTEXT.json.shapeFeedback[]` stays advisory and never mutates `SHAPE.json` directly
- feature with plans has `CONTEXT.md/.json`
- review exists only after summary artifacts
- phase progression is coherent (`discuss -> plan -> implement -> review -> ship`)

6. Freshness integrity:
- enforce `WORKFLOW.json.freshness` thresholds for stale context/plan/summary
- warn when parent shape changed after a feature stub or feature context was last refreshed

## Commands

```bash
python3 .cnogo/scripts/workflow_validate.py --json
python3 .cnogo/scripts/workflow_render.py <contract.json>
```

## Output

- Blockers: schema or lifecycle violations
- Warnings: drift/freshness risks
- Exact file edits needed to restore consistency
