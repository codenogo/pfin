# Feature: Reporting & Analytics (Reporting Context — Phase 2)

**Parent shape:** [personal-finance](../../ideas/personal-finance/SHAPE.md)
**Bounded context:** Reporting (supporting subdomain)
**Package:** `internal/reporting/`

## User Outcome

Users can generate balance sheets, income statements, trial balances, spending reports, and export to CSV.

## Scope

### Key Decisions
- **Full accounting reports** from day one (native to double-entry)
- **CSV export only** (PDF/OFX deferred)

### Reports (all read-only query handlers)
- **Trial Balance**: SUM of all account balances, must = 0 — integrity check
- **Balance Sheet**: assets vs liabilities vs equity at a point in time
- **Income Statement**: income vs expenses for a date range
- **Spending by Category**: GROUP BY category with period comparison
- **Per-member breakdown** for household reports (using created_by on journal entries)

### Export
- CSV via Go `encoding/csv` — one endpoint per report type with date range params

### Visualization
- Nivo charts: bar charts for category spending, line charts for trends, tables for detailed reports
- Date range selectors (current month, last month, custom range)

## Dependencies

- `double-entry-ledger` — all reports query journal_lines
- `budget-system` — spending reports can overlay budget allocations

## Handoff Summary

Implement query handlers: TrialBalance (SUM by account), BalanceSheet (assets/liabilities/equity), IncomeStatement (income/expenses), SpendingByCategory (GROUP BY). CSV export. Per-member breakdown. Next.js report pages with Nivo charts, date pickers, export buttons.

---
*Materialized from shape: 2026-03-20*
