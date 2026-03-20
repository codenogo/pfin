# Feature: Net Worth Dashboard (Reporting Context — Phase 1)

**Parent shape:** [personal-finance](../../ideas/personal-finance/SHAPE.md)
**Bounded context:** Reporting (supporting subdomain)
**Package:** `internal/reporting/`

## User Outcome

Users can see total net worth (assets minus liabilities) and track changes over time with rich Nivo visualizations. Household view includes shared + personally-shared accounts.

## Scope

- **Daily cron job** at midnight snapshots all account balances into `net_worth_snapshots` table
- **Nivo line chart** for net worth trend over time (daily/monthly/yearly views)
- **Nivo pie chart** for breakdown by account type (checking, savings, credit cards, etc.)
- **KPI cards**: total assets, total liabilities, net worth, month-over-month change
- **Scope-aware**: household net worth includes shared accounts + accounts shared from personal
- **Query handlers only** — pure read model, no commands
- **Time range selector**: 1M, 3M, 6M, 1Y, ALL

## Dependencies

- `chart-of-accounts` + `double-entry-ledger` — reads from account_balances materialized view

## Handoff Summary

Implement net_worth_snapshots table + daily cron job. Query handlers for current + historical net worth. Next.js dashboard page with Nivo charts and KPI cards. Scope-aware queries for household view.

---
*Materialized from shape: 2026-03-20*
