# Shape: Personal Finance Platform

## Problem

People lack a unified, performant tool to track expenses, manage budgets, monitor net worth, and follow investments — with proper accounting rigor, household collaboration, and wallet-based UX. Existing tools are fragmented, lack double-entry integrity, or force single-user silos.

## Target User

General public — anyone who wants control over their finances. Supports both solo users and households (couples, families, roommates). Multi-tenant SaaS architecture from day one.

## Core Architecture

### Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend | Go (clean architecture, DDD, modular monolith) | High concurrency, low memory, proven fintech stack |
| Frontend | Next.js (React, TypeScript) | SSR performance, strong typing, large ecosystem |
| Database | PostgreSQL | ACID guarantees, NUMERIC for money, mature ecosystem |
| API | REST + OpenAPI (dual surface) | Simplified `/transactions` + power-user `/journal-entries` |
| Auth | JWT + X-Household-ID header | Stateless auth + explicit tenant scope |
| Money | shopspring/decimal (Go) + NUMERIC(19,4) (PG) | Exact decimal arithmetic, never floats |
| Router | chi v5 | net/http compatible, middleware chains |
| DB Driver | pgx v5 | PostgreSQL-native, LISTEN/NOTIFY support |
| Migrations | golang-migrate | SQL-based, versioned |
| Testing | testcontainers-go + go-cmp | Real PostgreSQL in tests, no mocks for infra |

### Domain-Driven Design

**7 Bounded Contexts:**

| Context | Type | Role |
|---------|------|------|
| **Accounting** | Core Domain | Chart of accounts, journal entries, balances — the competitive differentiator |
| **Budgeting** | Core Domain | Budget allocation, period tracking, category-based spending limits |
| **Identity** | Generic Subdomain | Auth, users, sessions — replaceable by Auth0/Clerk later |
| **Household** | Supporting Subdomain | Multi-user households, roles, invitations, scope model |
| **Portfolio** | Supporting Subdomain | Investment holdings, market data, performance tracking |
| **Reporting** | Supporting Subdomain | Read-only projections — balance sheet, income statement, cash flow |
| **Import** | Generic Subdomain | CSV parsing, bank sync, deduplication |

**Context Mapping:** Conformist (Identity→all), Shared Kernel (Scope value object), Customer-Supplier (Accounting→Budgeting), Anti-Corruption Layer (Import→Accounting).

### Go Project Structure

```
pfin/
├── cmd/api/main.go                    # Composition root (manual DI wiring)
├── internal/
│   ├── accounting/                    # ── Core Domain ──
│   │   ├── domain/account/            # Account aggregate + value objects
│   │   ├── domain/entry/              # JournalEntry aggregate + Lines
│   │   ├── app/command/               # RecordExpense, VoidEntry, CreateAccount
│   │   ├── app/query/                 # AccountLedger, TrialBalance
│   │   ├── adapters/                  # PostgreSQL repos
│   │   ├── ports/                     # HTTP handlers + DTOs
│   │   └── service/                   # DI wiring
│   ├── household/                     # ── Supporting ──
│   │   ├── domain/household/          # Household + Members aggregate
│   │   ├── app/command/               # CreateHousehold, InviteMember
│   │   ├── adapters/ ports/ service/
│   ├── identity/                      # ── Generic ──
│   │   ├── domain/user/               # User + Credentials
│   │   ├── app/command/               # Register, Authenticate
│   │   ├── adapters/ ports/ service/
│   ├── budgeting/                     # ── Core Domain ──
│   ├── portfolio/                     # ── Supporting (deferred) ──
│   ├── reporting/                     # ── Supporting (deferred) ──
│   ├── importing/                     # ── Generic (parked) ──
│   └── common/                        # Auth middleware, error handling, server
├── pkg/                               # Shared kernel
│   ├── scope/                         # Scope value object (personal/household)
│   ├── money/                         # Money value object (amount + currency)
│   └── errs/                          # Typed DomainError with codes
├── migrations/                        # PostgreSQL migration files
└── api/openapi.yaml                   # OpenAPI spec
```

**Dependency rule:** `ports` → `app` → `domain` ← `adapters`. Domain depends on nothing except `pkg/`.

### Event-Driven Architecture (Event-Inspired)

- **NOT full event sourcing** — the double-entry journal IS already the event log
- **Domain events** emitted on state changes (JournalEntryRecorded, MemberAccepted, BudgetThresholdReached)
- **Custom event bus** (~300 lines Go): sync handlers for critical side effects (balance projections), async for non-critical (notifications, budget checks)
- **PostgreSQL outbox pattern** for durable async delivery — no Kafka/NATS/RabbitMQ needed
- **CQRS-lite**: command handlers (write journal entries) separated from query handlers (read materialized views)
- **30+ domain events** cataloged across all bounded contexts

### Five Architectural Pillars

**1. Full Double-Entry Accounting**
- Every transaction is a balanced journal entry (debits + credits = 0)
- Three core tables: `accounts`, `journal_entries`, `journal_lines`
- Immutable ledger: corrections via voiding + reversal entries
- Materialized `account_balances` view for dashboard performance
- Trial balance (`SUM(all amounts) = 0`) as integrity check
- Simplified transaction API hides debits/credits from users

**2. Wallet = Account (No Separate Entity)**
- A "wallet" is an account where `category IN (asset, liability) AND is_visible = TRUE`
- Five account categories: Asset, Liability, Equity, Income, Expense
- Account subtypes: checking, savings, credit_card, cash, e_wallet, loan, mortgage, investment
- Presentation metadata (icon, color, display_order) on accounts table
- `/wallets` API is syntactic sugar over `/accounts`

**3. Dual-Scope Model (Personal + Household)**
- Every entity has `scope = personal` (user_id) or `scope = household` (household_id)
- CHECK constraints enforce mutual exclusivity at DB level
- Solo users have zero household overhead — household UI hidden until needed
- Personal accounts can be optionally shared to household for visibility
- Scope-aware middleware extracts `HouseholdContext` from `X-Household-ID` header
- Four roles: owner, admin, member, viewer with permission matrix

## Constraints

- Financial accuracy is non-negotiable (exact decimals, balanced entries)
- Immutable ledger (no UPDATE/DELETE on journal entries)
- Security-first: encryption at rest, tenant isolation, audit trail
- Multi-tenant from day one
- Data ingestion strategy deferred — architecture supports both manual and bank sync
- Monetization model deferred — architecture agnostic

## Candidate Features

| # | Feature | Context | Status | Dependencies |
|---|---------|---------|--------|-------------|
| 0 | **Project Foundation & Shared Kernel** | cross-cutting | **discuss-ready** | — |
| 1 | Auth & User Management | Identity | **discuss-ready** | foundation |
| 2 | Household Management | Household | **discuss-ready** | auth |
| 3 | Chart of Accounts & Wallets | Accounting (P1) | **discuss-ready** | auth, household |
| 4 | Double-Entry Ledger | Accounting (P2) | **discuss-ready** | accounts |
| 5 | **Debt & Loan Management** | **Debt** | **discuss-ready** | accounts, ledger |
| 6 | Budget System | Budgeting | **discuss-ready** | ledger |
| 7 | Net Worth Dashboard | Reporting (P1) | **discuss-ready** | accounts, ledger |
| 8 | Investment Portfolio | Portfolio | **discuss-ready** | ledger |
| 9 | Reporting & Analytics | Reporting (P2) | **discuss-ready** | ledger, budgets |
| 10 | Data Import Pipeline | Import | parked | ledger |

## Recommended Sequence

```
foundation → auth (Identity) → household → accounts/wallets (Accounting P1)
                                                    │
                                             double-entry ledger (Accounting P2)
                                                    │
                                    ┌───────────────┼───────────────┐
                                    │               │               │
                              budget system    net worth    investment portfolio
                             (Budgeting)      (Reporting P1)  (Portfolio)
                                    │               │
                                    └───────┬───────┘
                                            │
                                     reporting & analytics
                                     (Reporting P2)

                                     (parked: data import)
```

Auth, Household, Accounts, and Ledger are the critical path. Budget, Net Worth, and Investments can proceed in parallel after ledger.

## Core Schema Overview

```sql
-- Users + Auth
users (id, email, password_hash, display_name, ...)

-- Households + Roles
households (id, name, currency, created_by, ...)
household_members (id, household_id, user_id, role, status, invited_email, ...)
household_invitations (id, household_member_id, token, expires_at, ...)

-- Chart of Accounts (wallet = account)
accounts (id, scope, user_id, household_id, name, category, account_type,
          currency, is_visible, icon, color, display_order, credit_limit,
          is_archived, shared_to_household_id, ...)

-- Double-Entry Ledger
journal_entries (id, user_id, date, description, status, voided_by, ...)
journal_lines (id, entry_id, account_id, amount NUMERIC(19,4), currency,
              foreign_amount, foreign_currency, category_id, ...)

-- Categories
categories (id, scope, user_id, household_id, name, parent_id, icon, color, ...)

-- Materialized Balances
account_balances (account_id, balance, total_debits, total_credits, last_activity)
```

## Research Completed

| Topic | Doc | Lines | Key Finding |
|-------|-----|-------|-------------|
| Double-entry architecture | [double-entry-accounting-architecture.md](../../research/double-entry-accounting-architecture.md) | ~1150 | journal_entries + journal_lines, NUMERIC(19,4), deferred constraint triggers |
| Household model | [household-family-finance-architecture.md](../../research/household-family-finance-architecture.md) | ~930 | Dual-scope, 4 roles, scope-aware middleware, zero solo-user overhead |
| Wallet system | [wallet-system-architecture.md](../../research/wallet-system-architecture.md) | ~810 | Wallet = Account, no separate entity, /wallets as convenience API |
| **DDD architecture** | [ddd-architecture-go-personal-finance.md](../../research/ddd-architecture-go-personal-finance.md) | **2405** | 7 bounded contexts, aggregate designs, value objects, Go project structure |
| **Event-driven architecture** | [event-driven-architecture.md](../../research/event-driven-architecture.md) | **1742** | Event-inspired (not ES), CQRS-lite, outbox pattern, 30+ domain events |
| **Go clean architecture** | [go-architecture-patterns.md](../../research/go-architecture-patterns.md) | **2938** | Modular monolith, DI, error handling, testing, middleware, library recs |

## Open Questions

None — all resolved. See decision log.

## Global Decisions

| Decision | Date |
|----------|------|
| Full double-entry accounting | 2026-03-20 |
| Wallet = Account (no separate entity) | 2026-03-20 |
| Dual-scope model (personal + household) from day one | 2026-03-20 |
| Go + Next.js + PostgreSQL | 2026-03-20 |
| shopspring/decimal + NUMERIC(19,4) | 2026-03-20 |
| Multi-currency: schema day-one, logic v2 | 2026-03-20 |
| **DDD: 7 bounded contexts (Accounting + Budgeting = core)** | 2026-03-20 |
| **Modular monolith, context-per-package under internal/** | 2026-03-20 |
| **Event-inspired (NOT full event sourcing)** | 2026-03-20 |
| **CQRS-lite within PostgreSQL** | 2026-03-20 |
| **Constructor injection, manual wiring, no DI framework** | 2026-03-20 |
| **Core libs: pgx v5, chi v5, golang-jwt, golang-migrate** | 2026-03-20 |
| **No ORMs (GORM), no testify, no viper, no gin** | 2026-03-20 |
| **PostgreSQL outbox for async events, no external MQ** | 2026-03-20 |
| Expense splitting deferred to v2 | 2026-03-20 |
| Data ingestion deferred | 2026-03-20 |
| Monetization deferred | 2026-03-20 |
| **Budget: monthly periods, optional rollover per category** | 2026-03-20 |
| **Budget alerts: in-app + email via Resend** | 2026-03-20 |
| **Net worth: daily cron snapshots** | 2026-03-20 |
| **Charts: Nivo (D3-based)** | 2026-03-20 |
| **Investments: manual prices, FIFO, simple return for v1** | 2026-03-20 |
| **Reports: full accounting suite, CSV export only** | 2026-03-20 |
| **Household cap: 10 members** | 2026-03-20 |
| **Account hierarchy: optional parent_id** | 2026-03-20 |
| **Email: Resend + React Email** | 2026-03-20 |

## Next Shape Moves

None — all features are discuss-ready or parked. Shape is complete. Ready to `/discuss` any feature.

---
*Shaped: 2026-03-20 | Last updated: 2026-03-20*
