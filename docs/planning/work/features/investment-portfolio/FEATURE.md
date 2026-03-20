# Feature: Investment Portfolio Tracker (Portfolio Context)

**Parent shape:** [personal-finance](../../ideas/personal-finance/SHAPE.md)
**Bounded context:** Portfolio (supporting subdomain)
**Package:** `internal/portfolio/`

## User Outcome

Users can track investment holdings with manual price entry, see simple return performance, asset allocation visualization, and dividend income. FIFO cost basis tracking.

## Scope

### Key Decisions
- **Manual price entry** for v1 (market data API deferred to v2)
- **FIFO only** for cost basis (LIFO, specific ID deferred)
- **Simple return only** ((current value - cost basis) / cost basis)

### Domain
- Holdings modeled as journal entries (buy/sell on investment accounts)
- **Lots table**: purchase_date, ticker, quantity, cost_basis_per_unit, remaining_quantity
- **Holdings prices table**: ticker, price, updated_at (manual entry)
- FIFO lot matching on sell: consume oldest lots first
- Dividends recorded as income journal entries

### Commands
- AddHolding (buy), RecordSale (sell with FIFO), UpdatePrice (manual), RecordDividend

### Queries
- PortfolioSummary (total value, total cost, simple return)
- HoldingDetail (per ticker: lots, cost basis, current value, return)
- AllocationBreakdown (Nivo pie chart data)

## Dependencies

- `double-entry-ledger` — holdings are journal entries on investment accounts

## Handoff Summary

Implement internal/portfolio/: Holdings as journal entries. FIFO lot tracking table. Manual price update. Simple return queries. Nivo pie chart for allocation. Dividend recording. Next.js: portfolio dashboard, holding detail, batch price update form.

---
*Materialized from shape: 2026-03-20*
