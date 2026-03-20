# Research: Event-Driven & Event-Sourcing Architecture for pfin

**Context:** Personal finance platform (Go + PostgreSQL + Next.js). Full double-entry accounting with immutable journal entries, household management with dual-scope, and wallet-as-account model.
**Date:** 2026-03-20
**Status:** Research complete, ready for shaping
**Related:**
- [Double-Entry Accounting Architecture](./double-entry-accounting-architecture.md)
- [Household Architecture](./household-family-finance-architecture.md)
- [Wallet System Architecture](./wallet-system-architecture.md)
- [SHAPE.md](../ideas/personal-finance/SHAPE.md)

---

## Table of Contents

1. [Event-Driven Architecture Fundamentals for Go](#1-event-driven-architecture-fundamentals-for-go)
2. [Event Sourcing -- Should pfin Use It?](#2-event-sourcing--should-pfin-use-it)
3. [CQRS (Command Query Responsibility Segregation)](#3-cqrs-command-query-responsibility-segregation)
4. [Domain Events for pfin -- Complete Event Catalog](#4-domain-events-for-pfin--complete-event-catalog)
5. [Event Infrastructure in Go + PostgreSQL](#5-event-infrastructure-in-go--postgresql)
6. [Concrete Patterns for pfin](#6-concrete-patterns-for-pfin)
7. [Go Libraries and Tools Evaluation](#7-go-libraries-and-tools-evaluation)
8. [Recommendation](#8-recommendation)

---

## 1. Event-Driven Architecture Fundamentals for Go

### 1.1 What Is Event-Driven Architecture (EDA)?

Event-driven architecture is a design pattern where state changes are communicated as **events** -- immutable facts about something that happened. Components react to events rather than being called directly, enabling loose coupling between bounded contexts.

There are two fundamentally different kinds of events:

| Kind | Purpose | Audience | Coupling | Example |
|------|---------|----------|----------|---------|
| **Domain events** | Record something that happened within a bounded context | Internal to the domain/service | Low | `JournalEntryRecorded`, `BudgetThresholdReached` |
| **Integration events** | Communicate across bounded contexts or services | External consumers | Minimal (contract-based) | `household.member.accepted`, `accounting.entry.recorded` |

**Domain events** carry rich, context-specific data and use domain language. They are used within a single bounded context to trigger side effects (update projections, enforce invariants, trigger workflows).

**Integration events** are a curated, stable subset designed for cross-context communication. They carry minimal data (usually just IDs and the fact that something happened) and have versioned schemas. Consumers fetch full details via APIs if needed.

For pfin (a modular monolith, not microservices), domain events are the primary concern. Integration events become relevant if/when bounded contexts are extracted into separate services.

### 1.2 Event Bus / Event Dispatcher Patterns in Go

An event dispatcher is the in-process mechanism that routes events from producers to consumers. Go's concurrency primitives (goroutines, channels) make it natural to implement.

#### Pattern A: Synchronous In-Process Dispatcher

The simplest pattern: events are dispatched within the same goroutine/transaction. All handlers run before the function returns. This guarantees that side effects complete before the user gets a response.

```go
package event

import (
    "context"
    "fmt"
    "sync"
)

// Event is the base interface all domain events implement.
type Event interface {
    EventName() string
}

// Handler processes a single event type.
type Handler func(ctx context.Context, event Event) error

// Bus is a synchronous in-process event dispatcher.
type Bus struct {
    mu       sync.RWMutex
    handlers map[string][]Handler
}

func NewBus() *Bus {
    return &Bus{handlers: make(map[string][]Handler)}
}

// Subscribe registers a handler for an event type.
func (b *Bus) Subscribe(eventName string, handler Handler) {
    b.mu.Lock()
    defer b.mu.Unlock()
    b.handlers[eventName] = append(b.handlers[eventName], handler)
}

// Publish dispatches an event to all registered handlers synchronously.
// If any handler fails, it returns the error immediately.
// All handlers run within the caller's context (and transaction, if any).
func (b *Bus) Publish(ctx context.Context, events ...Event) error {
    b.mu.RLock()
    defer b.mu.RUnlock()

    for _, evt := range events {
        handlers, ok := b.handlers[evt.EventName()]
        if !ok {
            continue
        }
        for _, h := range handlers {
            if err := h(ctx, evt); err != nil {
                return fmt.Errorf("handler for %s failed: %w", evt.EventName(), err)
            }
        }
    }
    return nil
}
```

**When to use:** Within a database transaction where all side effects must succeed or fail atomically. Example: recording a journal entry and updating the balance projection in the same transaction.

**Pros:**
- Simple mental model
- Strong consistency (all-or-nothing with the transaction)
- Easy to debug (synchronous stack traces)

**Cons:**
- Slower writes (all handlers block the response)
- Tight coupling to handler performance
- Cannot independently retry failed handlers

#### Pattern B: Async Event Processing (Background Workers)

For side effects that do not need to complete before responding to the user (sending notifications, checking budget thresholds, updating analytics):

```go
package event

import (
    "context"
    "log/slog"
)

// AsyncBus dispatches events to handlers via goroutines.
// Events are buffered in a channel; workers process them.
type AsyncBus struct {
    ch       chan envelope
    handlers map[string][]Handler
    logger   *slog.Logger
}

type envelope struct {
    ctx   context.Context
    event Event
}

func NewAsyncBus(bufferSize int, logger *slog.Logger) *AsyncBus {
    b := &AsyncBus{
        ch:       make(chan envelope, bufferSize),
        handlers: make(map[string][]Handler),
        logger:   logger,
    }
    return b
}

// Start spawns worker goroutines to process events.
func (b *AsyncBus) Start(ctx context.Context, workers int) {
    for i := 0; i < workers; i++ {
        go b.worker(ctx)
    }
}

func (b *AsyncBus) worker(ctx context.Context) {
    for {
        select {
        case <-ctx.Done():
            return
        case env := <-b.ch:
            b.dispatch(env)
        }
    }
}

func (b *AsyncBus) dispatch(env envelope) {
    handlers, ok := b.handlers[env.event.EventName()]
    if !ok {
        return
    }
    for _, h := range handlers {
        if err := h(env.ctx, env.event); err != nil {
            b.logger.Error("async handler failed",
                "event", env.event.EventName(),
                "error", err,
            )
            // TODO: dead-letter queue, retry logic
        }
    }
}

// Publish sends events to the async processing channel.
// Returns immediately; handlers run in background workers.
func (b *AsyncBus) Publish(ctx context.Context, events ...Event) error {
    for _, evt := range events {
        select {
        case b.ch <- envelope{ctx: ctx, event: evt}:
        default:
            b.logger.Warn("event buffer full, dropping event",
                "event", evt.EventName(),
            )
        }
    }
    return nil
}

func (b *AsyncBus) Subscribe(eventName string, handler Handler) {
    b.handlers[eventName] = append(b.handlers[eventName], handler)
}
```

**When to use:** Non-critical side effects that can tolerate brief delays. Notifications, analytics updates, budget threshold checks.

**Cons of pure in-memory async:** Events are lost if the process crashes. For durability, combine with the outbox pattern (section 5).

#### Pattern C: Hybrid (Synchronous + Async)

The recommended pattern for pfin: use **both**. Critical side effects (balance projections) are synchronous within the transaction. Non-critical side effects (notifications, budget checks) are dispatched asynchronously after commit.

```go
// CompositePublisher dispatches to both sync and async buses.
type CompositePublisher struct {
    sync  *Bus
    async *AsyncBus
}

func (p *CompositePublisher) Publish(ctx context.Context, events ...Event) error {
    // Sync handlers run first (within transaction context)
    if err := p.sync.Publish(ctx, events...); err != nil {
        return err
    }
    // Async handlers are enqueued after sync handlers succeed
    return p.async.Publish(ctx, events...)
}
```

### 1.3 Key Principles for Go EDA

1. **Events are value objects.** Immutable structs, no pointers to mutable state. Copy data into the event at creation time.

2. **Events carry what happened, not what to do.** `JournalEntryRecorded` (fact), not `UpdateBalances` (command). This preserves loose coupling -- the publisher does not know or care what handlers do.

3. **Handler registration at startup.** Wire all subscriptions in `main()` or a DI container. No runtime dynamic registration.

4. **Context propagation.** Pass `context.Context` through events for cancellation, timeouts, and tracing.

5. **Idempotent handlers.** Async handlers may be retried. Design them to be safe to run multiple times with the same event.

---

## 2. Event Sourcing -- Should pfin Use It?

### 2.1 What Is Event Sourcing?

Event sourcing is an architectural pattern where the **source of truth** for an entity's state is a sequence of events, not a mutable row in a database. Current state is derived by replaying all events from the beginning (or from a snapshot).

```
Traditional:
  State table:  Account { id: 1, balance: 500 }    ← mutable, overwritten

Event Sourcing:
  Event log:    AccountOpened { id: 1, balance: 0 }
                DepositReceived { id: 1, amount: 1000 }
                ExpenseRecorded { id: 1, amount: 500 }
  Current state = replay(events) = balance: 500     ← derived, never stored directly
```

### 2.2 Double-Entry Accounting IS Already Event-Sourced

This is the crucial insight for pfin. The existing double-entry architecture already exhibits the core properties of event sourcing:

| Event Sourcing Concept | pfin's Double-Entry Equivalent |
|----------------------|-------------------------------|
| **Event log** | `journal_entries` + `journal_lines` table (immutable, append-only) |
| **Events** | Journal entries ARE the events (each records a financial fact) |
| **Derived state** | Account balances ARE derived state (materialized from `SUM(journal_lines.amount)`) |
| **Replay** | Any balance can be reconstructed by replaying journal lines for an account |
| **Temporal queries** | `get_account_balance(account_id, as_of_date)` already works via date filtering |
| **Corrections via compensation** | Voiding creates a reversal entry, never mutates the original |
| **Audit trail** | Complete by construction -- every state change has a corresponding journal entry |

The journal IS the event store. This is not a coincidence -- event sourcing was heavily inspired by accounting ledgers. The accounting profession has been doing event sourcing for 500 years.

### 2.3 Full Event Sourcing vs Event-Inspired Patterns

| Approach | Description | Complexity | Fit for pfin |
|----------|-------------|-----------|-------------|
| **Full Event Sourcing** | ALL state derived from events. No mutable tables. Event store is the only write model. Projections rebuild all read models. | Very High | Overkill |
| **Event-Sourced Aggregates** | Specific aggregates (e.g., Account) are event-sourced. Other entities use traditional CRUD. | High | Partial fit (the ledger already does this) |
| **Event-Inspired / Domain Events** | Traditional state storage (mutable tables) + domain events emitted on state changes. Events used for side effects, not as source of truth. | Moderate | Best fit |
| **Ledger-as-Event-Log** | The double-entry journal IS the event log for financial state. Other domains (identity, household) use traditional CRUD + domain events. | Moderate | Optimal for pfin |

### 2.4 Pros and Cons of Full Event Sourcing for pfin

**Pros:**
- Perfect audit trail -- but pfin ALREADY has this via immutable journal entries
- Temporal queries ("what was the balance on March 1?") -- but pfin ALREADY supports this via `get_account_balance(account_id, as_of_date)`
- Event replay -- useful for debugging, but journal entries already provide this for financial data
- Flexibility to add new projections -- domain events (without full ES) provide this too

**Cons:**
- **Complexity explosion.** Every piece of state must be reconstructable from events. For user profiles, household memberships, budget configurations -- this is pure overhead with no benefit.
- **Eventual consistency.** Read models lag behind write models. For a personal finance app where users expect immediate balance updates, this creates confusing UX.
- **Read model management.** Every query needs a projection. Schema changes require replaying the entire event log. For a personal finance app with diverse reporting needs, this is burdensome.
- **Event versioning.** As the domain evolves, event schemas change. Managing upcasters/downcasters for every event version is significant ongoing cost.
- **Tooling gap.** Go's event sourcing ecosystem is immature compared to C#/.NET (where libraries like Marten and EventStoreDB have mature ecosystems). No production-grade Go event sourcing framework exists with wide adoption.
- **Snapshot management.** For accounts with thousands of transactions, replaying from event zero is slow. Snapshots add another layer of complexity.
- **Team cognitive load.** Event sourcing requires a fundamentally different mental model. For a project that already has significant domain complexity (double-entry accounting + households + dual-scope), adding ES compounds the learning curve.

### 2.5 Verdict: Do NOT Use Full Event Sourcing

**Recommendation: Event-Inspired Architecture with Ledger-as-Event-Log.**

pfin should use:

1. **The double-entry journal as the event log for financial state.** Journal entries are already immutable, append-only, and support temporal queries. This IS event sourcing for the accounting domain -- it is just called "double-entry bookkeeping."

2. **Domain events for cross-cutting concerns.** Emit events when significant things happen (`JournalEntryRecorded`, `MemberAccepted`, `BudgetThresholdReached`). Use these to trigger side effects (update projections, send notifications, enforce business rules).

3. **Traditional CRUD for non-financial state.** User profiles, household memberships, budget configurations, categories -- these are simple entities where mutable rows in PostgreSQL are the right model.

4. **CQRS-lite for reporting.** Separate write path (journal entries) from read path (materialized views, reporting queries). Not full CQRS with separate databases -- just clean separation of write and read concerns within PostgreSQL.

This gives pfin all the benefits of event-driven architecture (loose coupling, audit trail, extensibility) without the crushing complexity of full event sourcing.

---

## 3. CQRS (Command Query Responsibility Segregation)

### 3.1 What Is CQRS?

CQRS separates the write model (commands that change state) from the read model (queries that return data). Instead of a single model that handles both reads and writes, you have two distinct paths:

```
                 ┌───────────────────┐
  Commands ──────▶  Write Model      │  ── Domain Events ──▶ Update Read Models
  (record entry, │  (journal entries) │
   void entry)   └───────────────────┘
                                          ┌───────────────────┐
  Queries  ──────────────────────────────▶│  Read Models       │
  (balances,                              │  (materialized     │
   reports,                               │   views, reports)  │
   ledger view)                           └───────────────────┘
```

### 3.2 Why CQRS Naturally Fits Double-Entry Accounting

pfin's architecture already exhibits CQRS characteristics:

| CQRS Concept | pfin Equivalent |
|-------------|----------------|
| **Write model** | `journal_entries` + `journal_lines` (append-only, balanced) |
| **Read model** | `account_balances` materialized view, reporting queries |
| **Command** | "Record an expense", "Void an entry", "Transfer funds" |
| **Query** | "Show account balance", "Generate income statement", "Show ledger" |
| **Projection** | Balance recalculation from journal lines |

The write side is strict (must balance, immutable, validated) while the read side is flexible (materialized views, window functions, aggregations).

### 3.3 CQRS Implementation for pfin

#### Command Side: Command Handlers

```go
package command

import (
    "context"
    "fmt"
    "time"

    "github.com/google/uuid"
    "github.com/shopspring/decimal"
)

// RecordExpense is a command to record an expense transaction.
type RecordExpense struct {
    UserID      uuid.UUID
    HouseholdID *uuid.UUID // nil for personal scope
    Date        time.Time
    Description string
    Amount      decimal.Decimal
    FromAccount uuid.UUID // asset account (e.g., checking)
    CategoryID  uuid.UUID // expense category
    Tags        []string
}

// RecordExpenseHandler processes the RecordExpense command.
type RecordExpenseHandler struct {
    journalRepo JournalRepository
    accountRepo AccountRepository
    categoryRepo CategoryRepository
    eventBus    event.Publisher
    txManager   TxManager
}

func (h *RecordExpenseHandler) Handle(ctx context.Context, cmd RecordExpense) (*JournalEntry, error) {
    // 1. Validate
    fromAccount, err := h.accountRepo.GetByID(ctx, cmd.FromAccount)
    if err != nil {
        return nil, fmt.Errorf("source account not found: %w", err)
    }
    if fromAccount.Category != CategoryAsset {
        return nil, fmt.Errorf("source must be an asset account")
    }

    category, err := h.categoryRepo.GetByID(ctx, cmd.CategoryID)
    if err != nil {
        return nil, fmt.Errorf("category not found: %w", err)
    }

    // 2. Build the journal entry
    expenseAccountID := h.categoryRepo.GetExpenseAccountForCategory(ctx, cmd.CategoryID)

    entry := &JournalEntry{
        ID:          uuid.New(),
        UserID:      cmd.UserID,
        Date:        cmd.Date,
        Description: cmd.Description,
        Status:      EntryStatusCleared,
        Lines: []JournalLine{
            {
                ID:         uuid.New(),
                AccountID:  expenseAccountID,
                Amount:     cmd.Amount,              // debit expense
                CategoryID: &cmd.CategoryID,
            },
            {
                ID:        uuid.New(),
                AccountID: cmd.FromAccount,
                Amount:    cmd.Amount.Neg(),          // credit asset
            },
        },
    }

    // 3. Validate balance
    if err := entry.Validate(); err != nil {
        return nil, err
    }

    // 4. Persist within a transaction
    err = h.txManager.WithTx(ctx, func(txCtx context.Context) error {
        if err := h.journalRepo.CreateEntry(txCtx, entry); err != nil {
            return err
        }

        // 5. Emit domain event (synchronous handlers run within the tx)
        return h.eventBus.Publish(txCtx, &JournalEntryRecorded{
            EntryID:     entry.ID,
            UserID:      cmd.UserID,
            HouseholdID: cmd.HouseholdID,
            Date:        cmd.Date,
            Description: cmd.Description,
            Lines:       entry.Lines,
            RecordedAt:  time.Now(),
        })
    })

    if err != nil {
        return nil, err
    }

    return entry, nil
}
```

#### Query Side: Query Handlers

```go
package query

import (
    "context"
    "time"

    "github.com/google/uuid"
    "github.com/shopspring/decimal"
)

// AccountBalance is a query to get the current balance of an account.
type AccountBalance struct {
    AccountID uuid.UUID
    AsOfDate  *time.Time // nil = current
}

type AccountBalanceResult struct {
    AccountID   uuid.UUID
    AccountName string
    Balance     decimal.Decimal
    Currency    string
    AsOfDate    time.Time
}

// AccountBalanceHandler reads from the materialized view or computes live.
type AccountBalanceHandler struct {
    reader LedgerReader
}

func (h *AccountBalanceHandler) Handle(ctx context.Context, q AccountBalance) (*AccountBalanceResult, error) {
    if q.AsOfDate != nil {
        // Historical query: compute from journal lines (cannot use materialized view)
        return h.reader.GetBalanceAsOf(ctx, q.AccountID, *q.AsOfDate)
    }
    // Current balance: read from materialized view for speed
    return h.reader.GetCurrentBalance(ctx, q.AccountID)
}

// IncomeStatement is a query for an income statement over a date range.
type IncomeStatement struct {
    UserID      uuid.UUID
    HouseholdID *uuid.UUID
    From        time.Time
    To          time.Time
}

type IncomeStatementResult struct {
    Period       DateRange
    TotalIncome  decimal.Decimal
    TotalExpense decimal.Decimal
    NetIncome    decimal.Decimal
    IncomeByCategory  []CategoryAmount
    ExpenseByCategory []CategoryAmount
}

type IncomeStatementHandler struct {
    reader LedgerReader
}

func (h *IncomeStatementHandler) Handle(ctx context.Context, q IncomeStatement) (*IncomeStatementResult, error) {
    return h.reader.GetIncomeStatement(ctx, q.UserID, q.HouseholdID, q.From, q.To)
}
```

### 3.4 Read Model Strategies for PostgreSQL

| Strategy | Description | Freshness | Cost | Best For |
|----------|-------------|-----------|------|----------|
| **Live queries** | `SUM(journal_lines.amount)` computed on each request | Real-time | High CPU per query | Single account balance, account ledger |
| **Materialized views** | `REFRESH MATERIALIZED VIEW CONCURRENTLY` | Near real-time (refresh after each write or on schedule) | Low read cost, refresh overhead | Dashboard balances, net worth |
| **Dedicated read tables** | Separate tables updated by event handlers | Real-time (updated in same tx) | Extra write cost | Budget spent tracking, running totals |
| **In-memory projections** | Go maps/structs rebuilt from events on startup | Real-time after rebuild | Memory cost, cold start | Small datasets, session-scoped views |

**Recommended for pfin:**

- **Single account balance:** Live query (fast with proper index, correct by construction)
- **Dashboard / net worth:** Materialized view, refreshed after each journal write
- **Budget tracking (spent vs limit):** Dedicated read table (`budget_spent`), updated by `JournalEntryRecorded` handler in the same transaction
- **Reports (income statement, balance sheet):** Live queries with date range filters (these are infrequent and can afford full computation)

### 3.5 CQRS Without Separate Databases

pfin does NOT need separate databases for read and write. PostgreSQL serves both roles:

```
PostgreSQL
├── Write tables:
│   ├── journal_entries (append-only)
│   └── journal_lines (append-only)
│
├── Read models:
│   ├── account_balances (materialized view)
│   ├── budget_spent (dedicated table, event-driven)
│   └── Live queries (SUM/GROUP BY on journal_lines)
│
└── Shared tables (CRUD, not event-sourced):
    ├── users
    ├── households
    ├── household_members
    ├── accounts
    ├── categories
    └── budgets
```

This is "CQRS-lite" -- the separation of command and query concerns at the application layer, without the infrastructure complexity of separate databases, eventual consistency, or event streams.

---

## 4. Domain Events for pfin -- Complete Event Catalog

### 4.1 Event Schema Design

Every domain event follows a consistent structure:

```go
package event

import (
    "time"

    "github.com/google/uuid"
)

// Metadata is common to all domain events.
type Metadata struct {
    EventID       uuid.UUID `json:"event_id"`
    EventType     string    `json:"event_type"`
    AggregateID   uuid.UUID `json:"aggregate_id"`
    AggregateType string    `json:"aggregate_type"`
    UserID        uuid.UUID `json:"user_id"`
    HouseholdID   *uuid.UUID `json:"household_id,omitempty"`
    OccurredAt    time.Time `json:"occurred_at"`
    Version       int       `json:"version"` // schema version for this event type
}

// Base provides a default implementation of the Event interface.
type Base struct {
    Meta Metadata `json:"metadata"`
}

func (b Base) EventName() string       { return b.Meta.EventType }
func (b Base) GetMetadata() Metadata   { return b.Meta }
```

### 4.2 Event Catalog by Bounded Context

#### Identity Context

```go
// UserRegistered is emitted when a new user account is created.
type UserRegistered struct {
    Base
    Email       string `json:"email"`
    DisplayName string `json:"display_name"`
}

// UserVerified is emitted when the user confirms their email.
type UserVerified struct {
    Base
    Email string `json:"email"`
}

// PasswordChanged is emitted when the user changes their password.
type PasswordChanged struct {
    Base
    // No sensitive data in events. The fact itself is the event.
}

// UserDeactivated is emitted when a user account is soft-deleted.
type UserDeactivated struct {
    Base
    Reason string `json:"reason,omitempty"`
}
```

#### Household Context

```go
// HouseholdCreated is emitted when a new household is created.
type HouseholdCreated struct {
    Base
    Name     string `json:"name"`
    Currency string `json:"currency"`
}

// MemberInvited is emitted when an invitation is sent.
type MemberInvited struct {
    Base
    InvitedEmail string `json:"invited_email"`
    Role         string `json:"role"` // owner, admin, member, viewer
    InvitedBy    uuid.UUID `json:"invited_by"`
}

// MemberAccepted is emitted when an invitation is accepted.
type MemberAccepted struct {
    Base
    MemberUserID uuid.UUID `json:"member_user_id"`
    Role         string    `json:"role"`
}

// MemberDeclined is emitted when an invitation is declined.
type MemberDeclined struct {
    Base
    InvitedEmail string `json:"invited_email"`
}

// MemberRemoved is emitted when a member is removed from a household.
type MemberRemoved struct {
    Base
    MemberUserID uuid.UUID `json:"member_user_id"`
    RemovedBy    uuid.UUID `json:"removed_by"`
    Reason       string    `json:"reason,omitempty"`
}

// MemberRoleChanged is emitted when a member's role is updated.
type MemberRoleChanged struct {
    Base
    MemberUserID uuid.UUID `json:"member_user_id"`
    OldRole      string    `json:"old_role"`
    NewRole      string    `json:"new_role"`
    ChangedBy    uuid.UUID `json:"changed_by"`
}

// HouseholdRenamed is emitted when a household name is changed.
type HouseholdRenamed struct {
    Base
    OldName string `json:"old_name"`
    NewName string `json:"new_name"`
}

// HouseholdDeleted is emitted when a household is soft-deleted.
type HouseholdDeleted struct {
    Base
    DeletedBy uuid.UUID `json:"deleted_by"`
}
```

#### Accounting Context (Core)

```go
// AccountCreated is emitted when a new account is added to the chart of accounts.
type AccountCreated struct {
    Base
    Name        string `json:"name"`
    Category    string `json:"category"`     // asset, liability, income, expense, equity
    AccountType string `json:"account_type"` // checking, savings, credit_card, etc.
    Currency    string `json:"currency"`
    Scope       string `json:"scope"`        // personal or household
}

// AccountArchived is emitted when an account is soft-deleted.
type AccountArchived struct {
    Base
    AccountName string `json:"account_name"`
}

// AccountUnarchived is emitted when an archived account is restored.
type AccountUnarchived struct {
    Base
    AccountName string `json:"account_name"`
}

// AccountSharedToHousehold is emitted when a personal account is shared.
type AccountSharedToHousehold struct {
    Base
    HouseholdID uuid.UUID `json:"household_id"`
    Visibility  string    `json:"visibility"` // balance_only, full
}

// JournalEntryRecorded is the most important event in the system.
// It is emitted every time a financial transaction is recorded.
type JournalEntryRecorded struct {
    Base
    EntryID     uuid.UUID       `json:"entry_id"`
    Date        time.Time       `json:"date"`
    Description string          `json:"description"`
    EntryType   string          `json:"entry_type"` // standard, transfer, opening, adjustment
    Lines       []JournalLineData `json:"lines"`
}

type JournalLineData struct {
    AccountID  uuid.UUID       `json:"account_id"`
    Amount     decimal.Decimal `json:"amount"`
    Currency   string          `json:"currency"`
    CategoryID *uuid.UUID      `json:"category_id,omitempty"`
}

// JournalEntryVoided is emitted when a journal entry is reversed.
type JournalEntryVoided struct {
    Base
    OriginalEntryID uuid.UUID `json:"original_entry_id"`
    ReversalEntryID uuid.UUID `json:"reversal_entry_id"`
    Reason          string    `json:"reason"`
}

// BalanceRecalculated is emitted after balance projections are updated.
type BalanceRecalculated struct {
    Base
    AccountID  uuid.UUID       `json:"account_id"`
    OldBalance decimal.Decimal `json:"old_balance"`
    NewBalance decimal.Decimal `json:"new_balance"`
}
```

#### Budget Context

```go
// BudgetCreated is emitted when a new budget is set up.
type BudgetCreated struct {
    Base
    CategoryID uuid.UUID       `json:"category_id"`
    Amount     decimal.Decimal `json:"amount"`
    Period     string          `json:"period"` // monthly, weekly, yearly
}

// BudgetUpdated is emitted when a budget amount or period changes.
type BudgetUpdated struct {
    Base
    CategoryID uuid.UUID       `json:"category_id"`
    OldAmount  decimal.Decimal `json:"old_amount"`
    NewAmount  decimal.Decimal `json:"new_amount"`
}

// BudgetThresholdReached is emitted when spending hits a warning threshold.
type BudgetThresholdReached struct {
    Base
    BudgetID    uuid.UUID       `json:"budget_id"`
    CategoryID  uuid.UUID       `json:"category_id"`
    Threshold   int             `json:"threshold_pct"` // e.g., 80, 90
    SpentAmount decimal.Decimal `json:"spent_amount"`
    BudgetLimit decimal.Decimal `json:"budget_limit"`
}

// BudgetExceeded is emitted when spending surpasses the budget limit.
type BudgetExceeded struct {
    Base
    BudgetID    uuid.UUID       `json:"budget_id"`
    CategoryID  uuid.UUID       `json:"category_id"`
    SpentAmount decimal.Decimal `json:"spent_amount"`
    BudgetLimit decimal.Decimal `json:"budget_limit"`
    OverAmount  decimal.Decimal `json:"over_amount"`
}

// BudgetDeleted is emitted when a budget is removed.
type BudgetDeleted struct {
    Base
    CategoryID uuid.UUID `json:"category_id"`
}
```

#### Portfolio / Investment Context (Future)

```go
// HoldingAdded is emitted when an investment position is opened.
type HoldingAdded struct {
    Base
    Symbol   string          `json:"symbol"`
    Quantity decimal.Decimal `json:"quantity"`
    Price    decimal.Decimal `json:"price_per_unit"`
    Currency string          `json:"currency"`
}

// HoldingSold is emitted when an investment position is (partially) closed.
type HoldingSold struct {
    Base
    Symbol       string          `json:"symbol"`
    Quantity     decimal.Decimal `json:"quantity"`
    SalePrice    decimal.Decimal `json:"sale_price_per_unit"`
    CostBasis    decimal.Decimal `json:"cost_basis"`
    RealizedGain decimal.Decimal `json:"realized_gain"`
}

// DividendReceived is emitted when a dividend payment is recorded.
type DividendReceived struct {
    Base
    Symbol   string          `json:"symbol"`
    Amount   decimal.Decimal `json:"amount"`
    Currency string          `json:"currency"`
}

// PortfolioRebalanced is emitted after a rebalancing operation.
type PortfolioRebalanced struct {
    Base
    Trades []RebalanceTrade `json:"trades"`
}

type RebalanceTrade struct {
    Symbol   string          `json:"symbol"`
    Action   string          `json:"action"` // buy, sell
    Quantity decimal.Decimal `json:"quantity"`
}
```

### 4.3 Event Versioning Strategy

Events will evolve as the domain matures. Strategy:

1. **Version field on every event.** The `Version` field in `Metadata` tracks the schema version. Start at `1`.

2. **Additive changes only.** Add new optional fields; never remove or rename existing fields. This maintains backward compatibility.

3. **New event type for breaking changes.** If an event's semantics change fundamentally, create a new event type (e.g., `JournalEntryRecordedV2`) rather than modifying the existing one.

4. **Upcaster pattern (only if needed).** If stored events must be replayed (for event sourcing -- which we are NOT doing for most domains), register upcasters that transform old event versions to current. Since pfin uses event-inspired (not event-sourced), this is less critical -- events are consumed in real-time, not replayed from history.

```go
// Versioning example: adding a field to JournalEntryRecorded
// v1: original fields
// v2: added Tags field (optional, nil for v1 events)

type JournalEntryRecorded struct {
    Base
    EntryID     uuid.UUID         `json:"entry_id"`
    Date        time.Time         `json:"date"`
    Description string            `json:"description"`
    EntryType   string            `json:"entry_type"`
    Lines       []JournalLineData `json:"lines"`
    Tags        []string          `json:"tags,omitempty"` // Added in v2, optional
}
// Metadata.Version = 2 for events with Tags, 1 for older events
```

---

## 5. Event Infrastructure in Go + PostgreSQL

### 5.1 The Outbox Pattern

The outbox pattern solves the **dual-write problem**: when you need to both update the database and publish an event, you risk one succeeding and the other failing (broken consistency).

**The solution:** Write events to an `outbox` table in the **same database transaction** as the state change. A separate process reads the outbox and dispatches events to handlers/queues.

```
┌────────────────────────────────────────────────────┐
│  Database Transaction                              │
│                                                    │
│  1. INSERT INTO journal_entries (...)              │
│  2. INSERT INTO journal_lines (...)               │
│  3. INSERT INTO outbox (event_type, payload, ...)  │
│                                                    │
│  COMMIT                                            │
└──────────────────────────┬─────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────┐
│  Outbox Relay (background goroutine)     │
│                                          │
│  SELECT * FROM outbox                    │
│  WHERE processed_at IS NULL              │
│  ORDER BY created_at                     │
│  FOR UPDATE SKIP LOCKED                  │
│                                          │
│  For each row:                           │
│    → dispatch to handlers                │
│    → UPDATE outbox SET processed_at=now()│
│                                          │
└──────────────────────────────────────────┘
```

### 5.2 Outbox Table Design

```sql
-- ============================================================
-- EVENT OUTBOX
-- Events are written transactionally with state changes,
-- then relayed asynchronously to handlers.
-- ============================================================
CREATE TABLE event_outbox (
    id              BIGSERIAL PRIMARY KEY,        -- monotonically increasing for ordering
    event_id        UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    event_type      TEXT NOT NULL,                 -- e.g., 'accounting.journal_entry.recorded'
    aggregate_type  TEXT NOT NULL,                 -- e.g., 'journal_entry', 'household'
    aggregate_id    UUID NOT NULL,                 -- ID of the entity that changed
    payload         JSONB NOT NULL,                -- serialized event data
    metadata        JSONB NOT NULL DEFAULT '{}',   -- user_id, household_id, trace_id, etc.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at    TIMESTAMPTZ,                   -- NULL until relay processes it
    retry_count     INT NOT NULL DEFAULT 0,
    last_error      TEXT                           -- last processing error, if any
);

-- Index for the relay query (unprocessed events, in order)
CREATE INDEX idx_outbox_unprocessed ON event_outbox (created_at)
    WHERE processed_at IS NULL;

-- Index for cleanup (processed events older than retention period)
CREATE INDEX idx_outbox_processed ON event_outbox (processed_at)
    WHERE processed_at IS NOT NULL;
```

### 5.3 Outbox Relay Implementation in Go

```go
package outbox

import (
    "context"
    "database/sql"
    "encoding/json"
    "log/slog"
    "time"
)

// Relay polls the outbox table and dispatches events to handlers.
type Relay struct {
    db       *sql.DB
    bus      event.Publisher
    logger   *slog.Logger
    pollInterval time.Duration
    batchSize    int
}

func NewRelay(db *sql.DB, bus event.Publisher, logger *slog.Logger) *Relay {
    return &Relay{
        db:           db,
        bus:          bus,
        logger:       logger,
        pollInterval: 500 * time.Millisecond, // half-second polling
        batchSize:    100,
    }
}

// Start begins polling the outbox in a background goroutine.
func (r *Relay) Start(ctx context.Context) {
    go func() {
        ticker := time.NewTicker(r.pollInterval)
        defer ticker.Stop()

        for {
            select {
            case <-ctx.Done():
                return
            case <-ticker.C:
                if err := r.processBatch(ctx); err != nil {
                    r.logger.Error("outbox relay batch failed", "error", err)
                }
            }
        }
    }()
}

func (r *Relay) processBatch(ctx context.Context) error {
    tx, err := r.db.BeginTx(ctx, nil)
    if err != nil {
        return err
    }
    defer tx.Rollback()

    // SELECT ... FOR UPDATE SKIP LOCKED ensures concurrent relays
    // don't process the same events.
    rows, err := tx.QueryContext(ctx, `
        SELECT id, event_id, event_type, aggregate_type, aggregate_id,
               payload, metadata, created_at
        FROM event_outbox
        WHERE processed_at IS NULL
        ORDER BY created_at
        LIMIT $1
        FOR UPDATE SKIP LOCKED
    `, r.batchSize)
    if err != nil {
        return err
    }
    defer rows.Close()

    var processedIDs []int64

    for rows.Next() {
        var (
            id            int64
            eventID       string
            eventType     string
            aggregateType string
            aggregateID   string
            payload       json.RawMessage
            metadata      json.RawMessage
            createdAt     time.Time
        )

        if err := rows.Scan(&id, &eventID, &eventType, &aggregateType,
            &aggregateID, &payload, &metadata, &createdAt); err != nil {
            return err
        }

        // Deserialize and dispatch the event
        evt, err := deserializeEvent(eventType, payload, metadata)
        if err != nil {
            r.logger.Error("failed to deserialize event",
                "event_type", eventType,
                "event_id", eventID,
                "error", err,
            )
            // Mark as failed, don't reprocess immediately
            r.markFailed(tx, id, err.Error())
            continue
        }

        if err := r.bus.Publish(ctx, evt); err != nil {
            r.logger.Error("failed to dispatch event",
                "event_type", eventType,
                "event_id", eventID,
                "error", err,
            )
            r.markFailed(tx, id, err.Error())
            continue
        }

        processedIDs = append(processedIDs, id)
    }

    if len(processedIDs) > 0 {
        _, err = tx.ExecContext(ctx, `
            UPDATE event_outbox
            SET processed_at = now()
            WHERE id = ANY($1)
        `, processedIDs)
        if err != nil {
            return err
        }
    }

    return tx.Commit()
}

func (r *Relay) markFailed(tx *sql.Tx, id int64, errMsg string) {
    tx.ExecContext(context.Background(), `
        UPDATE event_outbox
        SET retry_count = retry_count + 1, last_error = $2
        WHERE id = $1
    `, id, errMsg)
}
```

### 5.4 Writing Events to the Outbox (Within Transaction)

```go
// AppendToOutbox writes an event to the outbox table within the current
// database transaction. This ensures the event is persisted atomically
// with the state change.
func AppendToOutbox(ctx context.Context, tx *sql.Tx, evt event.Event) error {
    meta := evt.GetMetadata()

    payload, err := json.Marshal(evt)
    if err != nil {
        return fmt.Errorf("marshal event payload: %w", err)
    }

    metadataJSON, err := json.Marshal(meta)
    if err != nil {
        return fmt.Errorf("marshal event metadata: %w", err)
    }

    _, err = tx.ExecContext(ctx, `
        INSERT INTO event_outbox (event_id, event_type, aggregate_type,
            aggregate_id, payload, metadata)
        VALUES ($1, $2, $3, $4, $5, $6)
    `, meta.EventID, meta.EventType, meta.AggregateType,
        meta.AggregateID, payload, metadataJSON,
    )
    return err
}
```

### 5.5 PostgreSQL LISTEN/NOTIFY for Low-Latency Event Notification

Instead of polling the outbox on a timer, PostgreSQL's LISTEN/NOTIFY can wake the relay immediately when new events are inserted:

```sql
-- Trigger to notify on new outbox events
CREATE OR REPLACE FUNCTION notify_outbox_event()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('outbox_events', NEW.event_type);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_outbox_notify
    AFTER INSERT ON event_outbox
    FOR EACH ROW
    EXECUTE FUNCTION notify_outbox_event();
```

```go
// Enhanced relay using LISTEN/NOTIFY for immediate wakeup
func (r *Relay) StartWithNotify(ctx context.Context) {
    // Use pgx for LISTEN support (database/sql does not support it)
    conn, err := r.pgxPool.Acquire(ctx)
    if err != nil {
        r.logger.Error("failed to acquire connection for LISTEN", "error", err)
        return
    }

    _, err = conn.Exec(ctx, "LISTEN outbox_events")
    if err != nil {
        r.logger.Error("LISTEN failed", "error", err)
        return
    }

    go func() {
        defer conn.Release()
        for {
            // WaitForNotification blocks until a notification arrives or context is cancelled
            notification, err := conn.Conn().WaitForNotification(ctx)
            if err != nil {
                if ctx.Err() != nil {
                    return // context cancelled, shutting down
                }
                r.logger.Error("notification wait failed", "error", err)
                time.Sleep(time.Second) // backoff
                continue
            }

            r.logger.Debug("outbox notification received",
                "event_type", notification.Payload,
            )

            // Process immediately
            if err := r.processBatch(ctx); err != nil {
                r.logger.Error("batch processing failed", "error", err)
            }
        }
    }()

    // Fallback: also poll every 5 seconds in case notifications are missed
    go func() {
        ticker := time.NewTicker(5 * time.Second)
        defer ticker.Stop()
        for {
            select {
            case <-ctx.Done():
                return
            case <-ticker.C:
                r.processBatch(ctx)
            }
        }
    }()
}
```

### 5.6 Do We Need Kafka/NATS/RabbitMQ?

**No. PostgreSQL is sufficient for pfin.**

| Criterion | Kafka/NATS/RabbitMQ | PostgreSQL Outbox |
|-----------|-------------------|-------------------|
| **Throughput** | Millions of events/sec | Thousands of events/sec |
| **pfin's actual load** | A few events per second (personal finance) | More than sufficient |
| **Operational complexity** | Separate cluster to manage, monitor, secure | Already running PostgreSQL |
| **Ordering guarantees** | Partition-based (Kafka), queue-based (RabbitMQ) | Sequential by `created_at` + `BIGSERIAL` |
| **Exactly-once delivery** | Complex (Kafka transactions, consumer offsets) | Simple (outbox + idempotent handlers) |
| **Transactional writes** | Requires Kafka transactions (complex) | Same DB transaction (trivial) |
| **Cost** | Additional infrastructure cost | Zero marginal cost |
| **Team expertise** | Requires ops knowledge | Already known |

**When would pfin need Kafka/NATS?**
- If pfin becomes a multi-service distributed system (microservices)
- If event throughput exceeds what PostgreSQL can handle (extremely unlikely for personal finance)
- If consumers need to be in different data centers
- If real-time streaming analytics is required

None of these apply to pfin's current or foreseeable architecture. The PostgreSQL outbox with LISTEN/NOTIFY provides sub-second event delivery with full transactional guarantees.

### 5.7 Outbox Cleanup

Processed events should be cleaned up to prevent unbounded table growth:

```sql
-- Scheduled job: delete processed events older than 30 days
DELETE FROM event_outbox
WHERE processed_at IS NOT NULL
AND processed_at < now() - INTERVAL '30 days';

-- Or archive to a separate table for long-term audit
INSERT INTO event_archive
SELECT * FROM event_outbox
WHERE processed_at IS NOT NULL
AND processed_at < now() - INTERVAL '7 days';

DELETE FROM event_outbox
WHERE processed_at IS NOT NULL
AND processed_at < now() - INTERVAL '7 days';
```

---

## 6. Concrete Patterns for pfin

### 6.1 Recording an Expense (End-to-End Flow)

```
User clicks "Add Expense: $85.50 Groceries from Checking"
                    │
                    ▼
┌─────────────────────────────────────────┐
│  API Handler: POST /api/v1/transactions │
│  Parse request, extract HouseholdContext│
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  Command: RecordExpense                 │
│  { amount: 85.50, from: checking,      │
│    category: groceries, date: today }   │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  BEGIN TRANSACTION                                          │
│                                                             │
│  1. Validate accounts exist and are correct types           │
│  2. Build journal entry:                                    │
│     - Expense:Groceries  +85.50 (debit)                    │
│     - Asset:Checking     -85.50 (credit)                   │
│  3. Validate entry.Lines sum to zero                        │
│  4. INSERT journal_entries (...)                            │
│  5. INSERT journal_lines (...)                              │
│                                                             │
│  6. SYNC EVENT HANDLERS (within transaction):               │
│     ┌──────────────────────────────────────────────────┐   │
│     │  BalanceProjectionHandler:                        │   │
│     │    UPDATE account_balances SET balance = ...      │   │
│     │    (or REFRESH MATERIALIZED VIEW CONCURRENTLY)    │   │
│     │                                                   │   │
│     │  BudgetSpentHandler:                              │   │
│     │    UPDATE budget_spent SET amount = amount + 85.50│   │
│     │    WHERE category_id = groceries                  │   │
│     │    AND period covers today                        │   │
│     └──────────────────────────────────────────────────┘   │
│                                                             │
│  7. INSERT event_outbox (JournalEntryRecorded, ...)        │
│                                                             │
│  COMMIT                                                     │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │  (after commit, outbox relay picks up)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  ASYNC EVENT HANDLERS (via outbox relay):                   │
│                                                             │
│  BudgetThresholdChecker:                                    │
│    SELECT spent, limit FROM budget_spent                    │
│    WHERE category_id = groceries                            │
│    → if spent/limit >= 0.80 → emit BudgetThresholdReached  │
│    → if spent > limit → emit BudgetExceeded                │
│                                                             │
│  NotificationHandler (future):                              │
│    → if BudgetThresholdReached or BudgetExceeded:           │
│      send push notification / email / in-app alert          │
│                                                             │
│  AuditLogHandler (for household-scoped transactions):       │
│    INSERT INTO audit_log (...)                              │
│                                                             │
│  AnalyticsHandler (future):                                 │
│    Update spending trends, category aggregations            │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Household Member Joins (Cross-Context Event Flow)

```
Invitee clicks accept on invite link
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Command: AcceptInvitation              │
│  { token: "abc123", user_id: "u-456" } │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  BEGIN TRANSACTION                                          │
│                                                             │
│  1. Validate token exists, not expired, not used            │
│  2. UPDATE household_members SET                            │
│       status = 'accepted',                                  │
│       user_id = 'u-456',                                   │
│       accepted_at = now()                                   │
│  3. UPDATE household_invitations SET used_at = now()        │
│                                                             │
│  4. INSERT event_outbox (MemberAccepted, ...)              │
│                                                             │
│  COMMIT                                                     │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  ASYNC HANDLERS (via outbox relay):                         │
│                                                             │
│  DefaultCategorySeeder:                                     │
│    → Check if user has personal categories                  │
│    → If not, seed default categories for the household      │
│      context (Groceries, Rent, Utilities, etc.)             │
│                                                             │
│  WelcomeNotificationHandler:                                │
│    → Notify existing household members about new member     │
│    → Send welcome information to new member                 │
│                                                             │
│  AuditLogHandler:                                           │
│    → INSERT INTO audit_log (household_id, user_id,         │
│       action='member.accepted', ...)                        │
│                                                             │
│  DashboardCacheInvalidator (future):                        │
│    → Invalidate cached household net worth / member list    │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 Voiding an Entry (Saga-Like Multi-Step Process)

Voiding a journal entry requires multiple coordinated steps. This is NOT a distributed saga (it is a single-database operation), but it demonstrates how domain events orchestrate the flow:

```
User clicks "Void" on a journal entry
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  Command: VoidJournalEntry                                  │
│  { entry_id: "je-123", reason: "Duplicate entry" }         │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  BEGIN TRANSACTION                                          │
│                                                             │
│  1. Load original entry + lines                             │
│  2. Verify entry is not already voided                      │
│                                                             │
│  3. Create reversal entry:                                  │
│     INSERT journal_entries (description: 'VOID: ...',      │
│       status: 'cleared')                                    │
│     INSERT journal_lines (negate all original amounts)      │
│                                                             │
│  4. Mark original as voided:                                │
│     UPDATE journal_entries SET status='voided',             │
│       voided_by = reversal_id                               │
│     WHERE id = 'je-123'                                    │
│                                                             │
│  5. SYNC HANDLERS (within transaction):                     │
│     BalanceProjectionHandler:                               │
│       → Recalculate balances for all affected accounts      │
│     BudgetSpentHandler:                                     │
│       → Reduce spent amount for affected categories         │
│                                                             │
│  6. INSERT event_outbox (JournalEntryVoided, ...)          │
│  7. INSERT event_outbox (JournalEntryRecorded for reversal)│
│                                                             │
│  COMMIT                                                     │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  ASYNC HANDLERS:                                            │
│                                                             │
│  BudgetThresholdChecker:                                    │
│    → Re-check budget thresholds (spending decreased)        │
│                                                             │
│  AuditLogHandler:                                           │
│    → Log the void action with reason                        │
│                                                             │
│  NotificationHandler (for household entries):               │
│    → Notify household members of voided entry               │
└─────────────────────────────────────────────────────────────┘
```

### 6.4 How Domain Events Enable Loose Coupling

Without events, the journal entry service would need direct knowledge of budgets, notifications, and analytics:

```go
// BAD: Tight coupling
func (s *JournalService) RecordEntry(ctx context.Context, entry *JournalEntry) error {
    s.journalRepo.Create(ctx, entry)
    s.balanceService.Recalculate(ctx, entry)    // direct dependency
    s.budgetService.UpdateSpent(ctx, entry)     // direct dependency
    s.notificationService.CheckAlerts(ctx, entry) // direct dependency
    s.analyticsService.RecordEvent(ctx, entry)  // direct dependency
    s.auditService.LogAction(ctx, entry)        // direct dependency
    return nil
}
```

With events, the journal service only knows about its own domain and the event bus:

```go
// GOOD: Loose coupling via events
func (s *JournalService) RecordEntry(ctx context.Context, entry *JournalEntry) error {
    err := s.txManager.WithTx(ctx, func(txCtx context.Context) error {
        if err := s.journalRepo.Create(txCtx, entry); err != nil {
            return err
        }
        // Emit event -- handlers are registered elsewhere
        return s.eventBus.Publish(txCtx, &JournalEntryRecorded{...})
    })
    return err
}

// Wiring happens at startup, not in the service:
func main() {
    bus := event.NewBus()
    bus.Subscribe("journal_entry.recorded", balanceHandler.Handle)
    bus.Subscribe("journal_entry.recorded", budgetHandler.Handle)
    // Add new handlers without touching JournalService
}
```

The journal service has zero imports from the budget, notification, or analytics packages. Adding a new reaction to `JournalEntryRecorded` requires zero changes to the accounting code.

### 6.5 Process Manager for Multi-Step Workflows

For complex workflows that span multiple events (not a single transaction), use a process manager:

```go
// BudgetAlertProcess monitors budget thresholds across multiple events.
type BudgetAlertProcess struct {
    budgetRepo BudgetRepository
    eventBus   event.Publisher
}

// HandleJournalEntryRecorded checks if the new entry pushes any budget past a threshold.
func (p *BudgetAlertProcess) HandleJournalEntryRecorded(ctx context.Context, evt event.Event) error {
    recorded := evt.(*JournalEntryRecorded)

    // Find which expense categories are affected
    for _, line := range recorded.Lines {
        if line.CategoryID == nil {
            continue
        }

        // Look up active budgets for this category
        budgets, err := p.budgetRepo.FindActiveBudgets(ctx, *line.CategoryID, recorded.Date)
        if err != nil {
            return err
        }

        for _, budget := range budgets {
            spent, err := p.budgetRepo.GetSpentInPeriod(ctx, budget.ID, budget.CurrentPeriodStart(), budget.CurrentPeriodEnd())
            if err != nil {
                return err
            }

            pct := spent.Div(budget.Amount).Mul(decimal.NewFromInt(100)).IntPart()

            if spent.GreaterThan(budget.Amount) {
                p.eventBus.Publish(ctx, &BudgetExceeded{
                    BudgetID:    budget.ID,
                    CategoryID:  budget.CategoryID,
                    SpentAmount: spent,
                    BudgetLimit: budget.Amount,
                    OverAmount:  spent.Sub(budget.Amount),
                })
            } else if pct >= 90 {
                p.eventBus.Publish(ctx, &BudgetThresholdReached{
                    BudgetID:   budget.ID,
                    CategoryID: budget.CategoryID,
                    Threshold:  90,
                    SpentAmount: spent,
                    BudgetLimit: budget.Amount,
                })
            } else if pct >= 80 {
                p.eventBus.Publish(ctx, &BudgetThresholdReached{
                    BudgetID:   budget.ID,
                    CategoryID: budget.CategoryID,
                    Threshold:  80,
                    SpentAmount: spent,
                    BudgetLimit: budget.Amount,
                })
            }
        }
    }

    return nil
}
```

---

## 7. Go Libraries and Tools Evaluation

### 7.1 Watermill (github.com/ThreeDotsLabs/watermill)

**What it is:** The most mature Go library for event-driven applications. Built by ThreeDotsLabs, the team behind the "Three Dots Labs" Go blog and "Wild Workouts" reference architecture.

**Features:**
- Publisher/Subscriber abstraction over multiple backends (Kafka, RabbitMQ, NATS, Google Pub/Sub, AMQP, SQL/PostgreSQL)
- Built-in PostgreSQL pub/sub adapter (stores messages in PostgreSQL tables)
- Router with middleware (retry, throttle, circuit breaker, correlation ID, metrics)
- CQRS component with command/event buses
- Exactly-once processing with deduplication middleware
- OpenTelemetry integration

**PostgreSQL adapter:** Watermill has a `watermill-sql` adapter that implements pub/sub using PostgreSQL tables. It uses polling with configurable intervals and supports `FOR UPDATE SKIP LOCKED` for concurrent consumers.

**Evaluation:**

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Maturity | High | v1.3+, used in production by many companies |
| PostgreSQL support | Good | Native SQL adapter, no external message broker needed |
| Go idioms | Good | Clean interfaces, context-aware, standard error handling |
| CQRS support | Good | Built-in command bus and event bus with handler routing |
| Complexity | Moderate | Adds abstractions; learning curve for the router |
| Active maintenance | Yes | Regular releases, responsive maintainers |

**Verdict: Strong candidate if pfin wants a proven library rather than building its own event bus.** The PostgreSQL adapter means no additional infrastructure. The CQRS component provides ready-made command/event handler patterns.

**Trade-off:** Watermill adds a dependency and its own abstractions. For a personal finance app with modest event throughput, the custom in-process bus (section 1.2) is simpler and sufficient. Watermill becomes more valuable if pfin needs durable message delivery, complex routing, or multi-backend support later.

### 7.2 go-cqrs / cqrs Libraries

There is no single dominant Go CQRS library. The landscape:

| Library | Status | Notes |
|---------|--------|-------|
| `github.com/ThreeDotsLabs/watermill` (CQRS component) | Active, mature | Best option if using Watermill |
| `github.com/looplab/eventhorizon` | Active | Full DDD/CQRS/ES framework. Supports MongoDB, PostgreSQL. Heavier than needed for pfin |
| `github.com/mishudark/eventhus` | Stale (last commit 2020) | Interesting design but unmaintained |
| `github.com/jetbasrawi/goes` | Stale | EventStore client only, not a full framework |

**Verdict:** Do not adopt a standalone CQRS library. Either use Watermill's CQRS component or implement the simple command/query handler pattern shown in section 3.3. The pattern is straightforward enough that a library adds more coupling than value.

### 7.3 EventStoreDB Go Client

**What it is:** Official Go client for EventStoreDB, a purpose-built event-sourcing database.

**Evaluation:**

| Criterion | Assessment |
|-----------|-----------|
| Use case | Full event sourcing with dedicated event store |
| pfin fit | Poor -- pfin is NOT doing full event sourcing |
| Operational overhead | Requires running EventStoreDB alongside PostgreSQL |
| Cost | Additional infrastructure and operational complexity |

**Verdict: Do not use.** pfin's recommendation is event-inspired architecture, not full event sourcing. Adding EventStoreDB would be adding a second database for a pattern we are not adopting.

### 7.4 PostgreSQL-Based Event Stores for Go

| Project | Description | Status |
|---------|-------------|--------|
| Watermill SQL adapter | Pub/sub via PostgreSQL tables | Active, production-ready |
| `github.com/modernice/goes` | Event sourcing framework for Go, supports PostgreSQL | Active, v0.x (pre-1.0) |
| `github.com/hallgren/eventsourcing` | Lightweight ES library, multiple backends | Active, small community |
| Custom outbox (section 5) | Hand-rolled outbox table + relay | Simple, tailored to pfin |

**Verdict:** For pfin, the custom outbox pattern (section 5) is the right choice. It is simple, tailored to the use case, requires no external dependencies, and provides exactly the guarantees needed (transactional event persistence, async delivery).

If the custom implementation proves insufficient, Watermill's SQL adapter is the natural upgrade path.

### 7.5 Library Recommendation Summary

| Tool | Recommendation | Rationale |
|------|---------------|-----------|
| **Watermill** | **Defer, but preferred upgrade path** | Start with custom event bus. Adopt Watermill if event complexity grows (multiple consumers, retry policies, dead-letter queues). |
| **EventStoreDB** | **Do not use** | Requires full event sourcing; pfin uses event-inspired pattern |
| **looplab/eventhorizon** | **Do not use** | Full DDD/ES framework, too heavy for pfin's needs |
| **Custom event bus + outbox** | **Start here** | Simple, no dependencies, tailored to pfin. ~200 lines of Go code |
| **pgx** (PostgreSQL driver) | **Use** | Already planned; needed for LISTEN/NOTIFY support |

---

## 8. Recommendation

### 8.1 Architecture Decision: Event-Inspired with Ledger-as-Event-Log

pfin should adopt an **event-inspired architecture** with the following characteristics:

1. **The double-entry journal IS the event log for financial state.** No separate event store needed for accounting. Journal entries are immutable, append-only events. Account balances are derived projections.

2. **Domain events for side effects and cross-context communication.** Significant state changes emit events. Handlers react to perform secondary effects (update projections, check budgets, log audits, send notifications).

3. **Synchronous handlers for critical projections.** Balance updates and budget spent tracking run within the same database transaction as the journal entry write. This ensures strong consistency.

4. **Asynchronous handlers for non-critical side effects.** Budget threshold checks, notifications, analytics, and audit logging run via the outbox relay after commit. This keeps writes fast.

5. **PostgreSQL outbox for durability.** Events are written to the outbox table in the same transaction as the state change. A background relay dispatches them. No external message broker needed.

6. **CQRS-lite, not full CQRS.** Separate command handlers (writes) from query handlers (reads) in the application layer. Both use the same PostgreSQL database. No separate read database.

7. **Traditional CRUD for non-financial domains.** User profiles, households, memberships, categories, and budget configurations use standard mutable tables. Domain events are emitted on significant changes but are NOT the source of truth for these entities.

### 8.2 What NOT to Do

| Anti-Pattern | Why Not |
|-------------|---------|
| Full event sourcing for all aggregates | Massive complexity for zero benefit on non-financial entities |
| EventStoreDB or separate event database | Additional infrastructure for a pattern we are not adopting |
| Kafka/NATS/RabbitMQ | Personal finance app does not need distributed messaging. PostgreSQL outbox is sufficient |
| Separate read database | Single PostgreSQL instance handles both read and write at pfin's scale |
| Event-sourced user profiles | A user's name changing is not an event worth replaying from the beginning of time |

### 8.3 Implementation Sequence

```
Phase 1: Foundation (with double-entry ledger)
├── Custom event bus (sync + async)
├── Domain event types for accounting context
├── JournalEntryRecorded event emission in journal service
├── Synchronous balance projection handler
└── In-memory async bus for non-critical handlers

Phase 2: Outbox Pattern
├── event_outbox table
├── Outbox relay (polling + LISTEN/NOTIFY)
├── Migrate async handlers from in-memory to outbox
├── Budget threshold checking via async handler
└── Audit log handler for household actions

Phase 3: Cross-Context Events
├── Household context events (MemberAccepted, etc.)
├── Identity context events (UserRegistered, etc.)
├── Event-driven category seeding for new household members
└── Event-driven notification system (when notification feature is built)

Phase 4: Evaluate Watermill (if needed)
├── If event routing complexity grows
├── If retry/dead-letter policies are needed
├── If monitoring/observability of event flow is insufficient
└── Watermill's SQL adapter as drop-in replacement for custom outbox
```

### 8.4 Impact on Existing Architecture

| Component | Change |
|-----------|--------|
| `journal_entries` + `journal_lines` | No change -- already serves as the event log |
| `account_balances` materialized view | Becomes a projection updated by event handler instead of manual refresh |
| `CreateEntry` in journal repository | Emits `JournalEntryRecorded` event within the transaction |
| `VoidEntry` in journal repository | Emits `JournalEntryVoided` event within the transaction |
| `AcceptInvitation` in household service | Emits `MemberAccepted` event, triggers category seeding |
| Budget service | Subscribes to `JournalEntryRecorded` for spent tracking; emits threshold events |
| New: `event_outbox` table | Added to schema |
| New: `event` package | ~200-300 lines of Go code for bus, outbox, relay |

### 8.5 Key Files to Create

| File | Purpose |
|------|---------|
| `internal/event/event.go` | Event interface, Metadata, Base types |
| `internal/event/bus.go` | Synchronous in-process event bus |
| `internal/event/async.go` | Async event bus with goroutine workers |
| `internal/event/composite.go` | Composite publisher (sync + async) |
| `internal/event/outbox/relay.go` | Outbox relay with polling + LISTEN/NOTIFY |
| `internal/event/outbox/writer.go` | AppendToOutbox helper |
| `internal/domain/accounting/events.go` | Accounting domain events |
| `internal/domain/household/events.go` | Household domain events |
| `internal/domain/identity/events.go` | Identity domain events |
| `internal/domain/budget/events.go` | Budget domain events |
| `internal/handler/balance_projection.go` | Sync handler: update balance on entry recorded |
| `internal/handler/budget_spent.go` | Sync handler: update budget spent |
| `internal/handler/budget_threshold.go` | Async handler: check budget thresholds |
| `internal/handler/audit_log.go` | Async handler: write audit log for household actions |
| `migrations/xxx_create_event_outbox.sql` | Outbox table migration |

### 8.6 Open Questions for Shaping

| # | Question | Options | Recommendation |
|---|----------|---------|---------------|
| 1 | Start with custom event bus or adopt Watermill from day one? | Custom (simpler) / Watermill (more features) | **Custom** -- adopt Watermill only if complexity warrants it |
| 2 | Balance projection: materialized view refresh or dedicated table update? | `REFRESH MATERIALIZED VIEW CONCURRENTLY` / `UPDATE account_balances SET ...` | **Dedicated table** (trigger-based update is faster and more predictable than full view refresh) |
| 3 | Outbox cleanup strategy? | TTL-based deletion / Archive to separate table / Keep forever | **TTL deletion (30 days)** with option to archive if audit requirements change |
| 4 | Should budget threshold checks be sync or async? | Sync (immediate feedback) / Async (faster writes) | **Async** -- budget alerts can tolerate sub-second delay; keeps writes fast |
| 5 | Event schema format? | Go structs with JSON marshaling / Protobuf / Avro | **Go structs + JSON** -- simplest option, sufficient for single-service architecture |
| 6 | Should the outbox relay use LISTEN/NOTIFY or pure polling? | LISTEN/NOTIFY (lower latency) / Polling (simpler) | **Both** -- LISTEN/NOTIFY for immediate wakeup, polling as fallback |

---

## Summary

pfin's double-entry accounting architecture is already event-sourced by nature -- journal entries ARE events, balances ARE derived state. Full event sourcing would add tremendous complexity for zero benefit on top of what the ledger already provides.

The recommended architecture is **event-inspired**: emit domain events on significant state changes, handle critical projections synchronously within transactions, handle non-critical side effects asynchronously via the PostgreSQL outbox pattern. This provides loose coupling between bounded contexts, a clean audit trail, and extensibility for future features (notifications, analytics, integrations) -- all without external message brokers or the complexity of full event sourcing.

Start simple (custom event bus, ~300 lines of Go), evolve to Watermill if needed, and never adopt Kafka/NATS unless pfin becomes a distributed system.

---
*Research completed: 2026-03-20*
