---
name: artifact-token-budgeting
tags: [workflow, quality, performance]
appliesTo: [shape, brainstorm, discuss, review, plan, spawn]
---
# Artifact Token Budgeting

Use this skill when editing command docs or planning artifacts.

## Goal

Minimize context cost while preserving correctness and operator clarity.

## Strategy

1. Contract-first:
- JSON contract is source of truth
- markdown rendered from contract when supported

2. Content compression:
- prefer short imperative steps
- avoid repeated examples and duplicate prose
- include only fields needed for execution
- keep initiative-wide truth in `SHAPE.json`; keep feature-local deltas in `CONTEXT.json`

3. Budget enforcement:
- keep artifacts under `WORKFLOW.json.performance.tokenBudgets`
- prefer warnings + targeted trims over broad rewrites

4. Scope-aware editing:
- touch only artifacts relevant to the requested workflow path
- avoid context inflation in unrelated commands

## Commands

```bash
python3 .cnogo/scripts/workflow_validate.py --json
```

## Output

- Over-budget artifacts with exact sizes
- Minimal trim plan
- Post-trim validation status
