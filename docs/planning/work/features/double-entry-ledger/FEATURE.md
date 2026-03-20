# Feature: Double-Entry Ledger (Accounting Context — Phase 2)

**Parent shape:** [personal-finance](../../ideas/personal-finance/SHAPE.md)
**Bounded context:** Accounting (core domain)
**Package:** `internal/accounting/domain/entry/`

## User Outcome

Users can record income, expenses, and transfers with full double-entry integrity. The UI presents a simple transaction form; the backend records balanced journal entries.

## Scope

### Domain Layer (`internal/accounting/domain/entry/`)
- **JournalEntry aggregate root**: id, scope, date, description, status (EntryStatus), voided_by, lines[], tags, created_by
  - **Invariants**: SUM(lines.amount) = 0, minimum 2 lines, no zero amounts, voided entries are immutable
- **JournalLine child entity**: id, entry_id, account_id, amount (NUMERIC(19,4)), currency, foreign_amount, foreign_currency, category_id, description
- **EntryStatus value object**: pending, cleared, reconciled, voided
- **Factory methods**: `NewExpense(from, category, amount)`, `NewTransfer(from, to, amount)`, `NewIncome(to, source, amount)` — construct balanced entries from simplified input
- **Void()** method: creates reversal entry (negated lines), links via voided_by
- **Validate()**: enforces all invariants using shopspring/decimal

### Application Layer — CQRS Commands (`internal/accounting/app/command/`)
- **RecordTransaction**: accepts simplified input (type, amount, from/to accounts) → constructs balanced JournalEntry via factory → persists → emits JournalEntryRecorded
  - Sync handler: update account balance projection
  - Async handler (outbox): budget spent tracking, threshold checks
- **VoidEntry**: validate entry is not already voided → create reversal → emit JournalEntryVoided

### Application Layer — CQRS Queries (`internal/accounting/app/query/`)
- **AccountLedger**: running balance via PostgreSQL window functions, paginated
- **TrialBalance**: SUM of all account balances, must equal zero
- **AccountBalance**: read from materialized account_balances view

### Event Infrastructure
- **JournalEntryRecorded** (domain event): emitted after successful persist
  - Sync handler: update materialized balance (same transaction)
  - Async handler (via outbox): notify Budgeting context for spent tracking
- **JournalEntryVoided**: same pattern as above
- **PostgreSQL outbox table**: event_outbox (id, event_type, aggregate_id, payload JSONB, created_at, processed_at)
- **Outbox relay**: polling + LISTEN/NOTIFY for sub-second delivery

### Database Migrations
- `journal_entries` table: immutable, status enum, voided_by FK
- `journal_lines` table: NUMERIC(19,4), ON DELETE RESTRICT, nonzero CHECK
- Deferred constraint trigger: `check_entry_balance()` enforces SUM = 0 at COMMIT time
- Covering index: `journal_lines(account_id) INCLUDE (entry_id, amount, currency)`
- `account_balances` materialized view
- `event_outbox` table
- `categories` table (hierarchical, dual-scope) if not created in Phase 1

### API — Dual Surface
- **Simplified**: `POST /api/v1/transactions` (type, amount, from_account, to_account)
- **Power user**: `POST /api/v1/journal-entries` (explicit lines with amounts)
- **Shared**: `GET /api/v1/accounts/:id/ledger`, `GET /api/v1/reports/trial-balance`

## Dependencies

- `chart-of-accounts` — journal lines reference accounts by ID

## Risks

- Running balance computation at scale (millions of transactions)
- Immutability pattern (void + reverse) adds complexity vs simple UPDATE
- Deferred constraint trigger needs careful testing
- Category taxonomy design affects budgets and reports downstream
- Dual API surface must stay in sync
- Event bus integration — sync handler for balance, async outbox for budget checks

## Handoff Summary

Implement internal/accounting/domain/entry per DDD structure. JournalEntry aggregate root with Lines (child entities), Validate() using shopspring/decimal, factory methods (NewExpense/NewTransfer/NewIncome), Void() for reversal. JournalRepository.CreateEntry: single DB transaction with balance verification. LedgerReader for account ledger (window functions), trial balance. RecordTransaction command: validate → construct → persist → emit JournalEntryRecorded (sync: balance update, async: outbox). VoidEntry command with reversal. Materialized account_balances view. PostgreSQL outbox table + relay. HTTP handlers with dual API. Categories table. Next.js: transaction form, ledger view, void action.

---
*Materialized from shape: 2026-03-20*
