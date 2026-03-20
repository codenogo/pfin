---
name: shape-architecture-tradeoffs
tags: [workflow, architecture, research]
appliesTo: [shape, brainstorm, research]
---
# Shape Architecture Tradeoffs

Use this skill when initiative-level shaping depends on architectural direction.

## Goal

Surface the smallest set of architectural decisions that meaningfully change feature sequencing, feasibility, or scope.

## Guidance

1. Compare only viable directions.
2. Prefer reversible decisions for early-stage work.
3. Highlight how each option changes:
- candidate features
- dependency order
- operational risk
- later discuss/planning burden
4. Use `/research` only when repo evidence is not enough.
5. Record the chosen direction in `globalDecisions[]` and keep rejected options out of downstream feature contexts unless they remain relevant risk.

## Output

- viable options with tradeoffs
- chosen direction for now
- explicit risks and deferred alternatives
