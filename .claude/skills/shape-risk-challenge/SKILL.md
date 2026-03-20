---
name: shape-risk-challenge
tags: [workflow, shaping, risk]
appliesTo: [shape, spawn]
---
# Shape Risk Challenge

Use this skill when initiative-level shaping needs a deliberate contrarian pass.

## Goal

Surface the few risks that would actually change feature readiness, sequencing, or architectural direction.

## Guidance

1. Challenge assumptions, not the existence of the initiative.
2. Look for:
- hidden coupling
- missing prerequisites
- irreversible early choices
- weak evidence behind a promoted feature
- discuss-ready features that should regress to `draft` or `blocked`
3. Prefer concrete failure modes over generic caution.
4. If the favored direction survives scrutiny, say so and explain what makes it robust.
5. Route external unknowns to `/research`; keep repo-local risk inside `/shape`.

## Output

- top risks worth acting on
- why they matter now
- mitigation or validation move
- any readiness-state changes worth considering
