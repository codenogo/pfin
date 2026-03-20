---
name: memory-sync-reconciliation
tags: [workflow, quality]
appliesTo: [implement, spawn]
---
# Memory Sync Reconciliation

Use this skill for `.cnogo/issues.jsonl` and SQLite reconciliation issues.

## Goal

Keep memory state merge-safe, deduplicated, and dependency-valid across branches.

## Checks

1. Source health:
- JSONL lines parse as JSON objects
- required issue fields (`id`, `title`, `status`, `issue_type`) valid

2. Import behavior:
- dependencies reference existing target IDs
- labels merge idempotently
- events dedupe by stable fingerprint (no duplicate tails)

3. Post-import integrity:
- blocked cache rebuilt
- child counters rebuilt
- issue/event counts are plausible (no unexpected drop)

4. Sync behavior:
- export is atomic
- git stage only `.cnogo/issues.jsonl`

## Commands

```bash
python3 .cnogo/scripts/workflow_memory.py import
python3 .cnogo/scripts/workflow_memory.py export
python3 .cnogo/scripts/workflow_memory.py stats --json
```

## Output

- Reconciliation result (pass/warn/fail)
- Any skipped deps/events with reason
- Follow-up fixes for data integrity
