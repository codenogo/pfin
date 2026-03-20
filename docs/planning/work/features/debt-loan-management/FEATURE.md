# Feature: Debt & Loan Management (Debt Context)

**Parent shape:** [personal-finance](../../ideas/personal-finance/SHAPE.md)
**Bounded context:** Debt (supporting subdomain)
**Package:** `internal/debt/`

## User Outcome

Users can track loans with full amortization schedules, see upcoming payments, have payments auto-split into principal vs interest, compare payoff strategies, and run what-if scenarios for extra payments.

## Scope

### Domain Layer (`internal/debt/domain/loan/`)
- **Loan aggregate root**: id, account_id (FK to liability account), scope, interest_rate, term_months, original_principal, start_date, minimum_payment, due_day_of_month, extra_payment_amount
- **AmortizationSchedule**: computed from loan terms — list of AmortizationRow (month, payment, principal, interest, remaining_balance)
- **PayoffStrategy value object**: snowball, avalanche, hybrid, custom

### Auto-Split Payments
When a user records a loan payment:
1. Debt service looks up the loan's amortization schedule for the current period
2. Calculates principal portion vs interest portion
3. Creates a **split journal entry** via Accounting context:
   - Debit `Liability:Mortgage` (principal — reduces debt)
   - Debit `Expense:Interest` (interest — cost of borrowing)
   - Credit `Asset:Checking` (total payment amount)
4. This gives users accurate tracking of where their money goes

### Payoff Strategies
All four computed side-by-side for comparison:
- **Snowball**: pay minimums on all, extra goes to smallest balance first
- **Avalanche**: pay minimums on all, extra goes to highest interest rate first
- **Hybrid**: weighted score of balance size + interest rate
- **Custom**: user sets priority order manually

Each strategy shows: total interest paid, payoff date, monthly payment schedule

### What-If Scenarios
- "What if I pay an extra $200/month on my mortgage?"
- "What if I refinance at 5.5% instead of 6.8%?"
- Interactive sliders in Next.js, compute results in real-time

### Upcoming Payments Dashboard
- All debts with next due date, minimum payment, remaining balance
- Calendar view of payments due this month
- Total monthly debt obligation

### Commands
- CreateLoan (link to liability account, set terms)
- RecordLoanPayment (auto-split into principal + interest journal entry)
- UpdateLoanTerms (refinance scenario)
- SetPayoffPriority (custom strategy ordering)

### Queries
- LoanDetail (amortization schedule, payment history, remaining balance)
- UpcomingPayments (all debts, sorted by due date)
- PayoffComparison (all four strategies for all debts)
- WhatIfSimulation (parameter-adjusted projections)
- DebtOverview (total debt, total monthly payments, projected payoff date)

### Event Integration
- Subscribes to `JournalEntryRecorded` — reconcile actual payments against expected schedule
- Emits `PaymentRecorded`, `LoanPaidOff` (triggers celebration UX + net worth update)

### Database
- `loans` table: id, account_id, scope, interest_rate, term_months, original_principal, start_date, minimum_payment, due_day_of_month, payoff_priority
- `loan_payments` table: id, loan_id, journal_entry_id, principal_amount, interest_amount, payment_date (denormalized for fast queries)

## Dependencies

- `chart-of-accounts` — loans reference liability accounts
- `double-entry-ledger` — payments create split journal entries

## Risks

- Amortization calculation must handle variable rates and extra payments correctly
- Auto-split accuracy depends on schedule staying in sync with actual payments
- Payoff strategy comparison is computationally intensive with many loans
- What-if scenarios need responsive UI (compute in Go, render in Next.js)

## Handoff Summary

Implement internal/debt/ bounded context: Loan aggregate wrapping liability account_id + loan terms. Amortization schedule generator (standard amortization formula). Auto-split payment service creating split journal entries via Accounting. Payoff engine computing snowball/avalanche/hybrid/custom strategies. What-if calculator with adjustable parameters. Upcoming payments query. Subscribe to JournalEntryRecorded for reconciliation. Next.js: debt dashboard (Nivo charts), loan detail with amortization table, strategy comparison page, what-if simulator with sliders, upcoming payments calendar.

---
*Materialized from shape: 2026-03-20*
