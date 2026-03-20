---
name: context-handoff-engineering
tags: [workflow, context, tokens]
appliesTo: [shape, brainstorm, discuss]
---
# Context Handoff Engineering

Use this skill when handing work from `shape` into `discuss`.

## Goal

Preserve the cross-feature truth once, then pass only the feature-local slice forward.

## Rules

1. `SHAPE.json` owns initiative-wide decisions.
2. `FEATURE.json` owns the inherited handoff for one feature.
3. `CONTEXT.json` owns only feature-local deltas plus links back to `SHAPE.json` and `FEATURE.json`.
4. Prefer references over repeated prose.
5. If feature-local discussion implies initiative-level follow-up, capture it as advisory `shapeFeedback[]` in `CONTEXT.json` instead of editing `SHAPE.json`.
6. If parent shape changed after a feature stub or context was last refreshed, warn and refresh before planning.
7. Keep scout outputs short, evidence-based, and disposable; the shared source of truth is always the persisted artifact.

## Output

- compact inheritance links
- feature-local context only
- suggested feedback back to `/shape` when needed
- explicit stale-parent warning when needed
