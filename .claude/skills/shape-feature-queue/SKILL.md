---
name: shape-feature-queue
tags: [workflow, planning, decomposition]
appliesTo: [shape, brainstorm]
---
# Shape Feature Queue

Use this skill when decomposing an initiative into feature-ready work.

## Goal

Produce a stable queue of candidate features inside an ongoing shape workspace without duplicating cross-feature context downstream.

## Rules

1. Each candidate feature needs:
- `slug`
- `displayName`
- `userOutcome`
- `scopeSummary`
- `dependencies[]`
- `risks[]`
- `status`
- `readinessReason`
- `handoffSummary`
2. Use only these readiness states:
- `draft`
- `discuss-ready`
- `blocked`
- `parked`
3. When a feature becomes `discuss-ready`, create its `FEATURE.md/json` stub immediately, but keep it visible as an optional exit inside shape.
4. Keep `recommendedSequence[]` aligned with the candidate feature slugs.
5. Add `nextShapeMoves[]` when more shaping work is still valuable.
6. Reject duplicate feature slugs.

## Output

- candidate feature list
- dependency ordering
- readiness state for each feature
- optional exits plus the remaining shaping work
