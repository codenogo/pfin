---
name: refactor-safety
tags: [quality, domain]
appliesTo: [spawn]
---
# Refactor Safety

Checklist for cleanup, re-architecture, and moving code.

## Checklist

- Preserve behavior (tests pass before and after)
- Small commits, easy rollback
- Avoid mixed concerns (refactor separate from feature work)
- Deprecation strategy if interfaces change
- No silent regressions

## Data & Migrations

- Backward compatibility with rollout plan
- Reversible migrations
- Backfill strategy (online vs offline)
- Indexing and performance impact
- Data integrity constraints maintained
