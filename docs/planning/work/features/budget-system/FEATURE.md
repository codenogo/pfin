# Feature: Budget System (Budgeting Context)

**Parent shape:** [personal-finance](../../ideas/personal-finance/SHAPE.md)
**Bounded context:** Budgeting (core domain)
**Package:** `internal/budgeting/`

## User Outcome

Users can set monthly budgets per category, see real-time progress with visual indicators, get email alerts at thresholds, and optionally roll unused amounts forward.

## Scope

### Domain Layer
- **Budget aggregate root**: id, scope, name, month (YYYY-MM), allocations[]
- **Allocation child entity**: category_id, amount, rollover_enabled, rollover_amount, spent (derived from events)
- **Invariants**: no duplicate categories, amounts non-negative, total allocations optional cap

### Key Decisions
- **Monthly periods only** — weekly/custom deferred
- **Optional rollover per category** — each allocation toggles independently
- **In-app alerts**: progress bars yellow at 80%, red at 100%
- **Email alerts via Resend** at configurable thresholds

### Event Integration
- Subscribes to `JournalEntryRecorded` from Accounting context → updates spent tracking per category
- Emits `BudgetThresholdReached` (async) → triggers email alert via Resend
- Emits `BudgetExceeded` (async) → stronger alert

### Commands
- CreateBudget, UpdateAllocation, ToggleRollover, ClosePeriod (triggers rollover calculation)

### Queries
- BudgetProgress (spent vs allocated per category for current month)
- BudgetOverview (all budgets with status)

## Dependencies

- `double-entry-ledger` — subscribes to JournalEntryRecorded events

## Handoff Summary

Implement internal/budgeting/: Budget aggregate with Allocations, monthly period, per-category rollover toggle. Subscribe to JournalEntryRecorded for spent tracking. Async threshold handler. Nivo progress charts on Next.js. Email via Resend at 80%/100%.

---
*Materialized from shape: 2026-03-20*
