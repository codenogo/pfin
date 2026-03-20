# Research: Domain-Driven Design Architecture for pfin

**Context:** Go + PostgreSQL + Next.js personal finance platform with full double-entry accounting, household management, and wallet-as-account model.
**Date:** 2026-03-20
**Status:** Research complete

---

## Table of Contents

1. [Strategic Design: Bounded Contexts](#1-strategic-design-bounded-contexts)
2. [Context Mapping](#2-context-mapping)
3. [Tactical Design in Go](#3-tactical-design-in-go)
4. [Go Project Structure](#4-go-project-structure)
5. [Aggregate Design](#5-aggregate-design)
6. [Value Objects in Go](#6-value-objects-in-go)
7. [Repository Pattern in Go](#7-repository-pattern-in-go)
8. [Application Services & CQRS](#8-application-services--cqrs)
9. [Domain Events](#9-domain-events)
10. [Concrete Code: pfin Domain Model](#10-concrete-code-pfin-domain-model)
11. [Reference Projects & Sources](#11-reference-projects--sources)

---

## 1. Strategic Design: Bounded Contexts

A bounded context is a semantic boundary within which a particular domain model applies. Each context has its own ubiquitous language -- the same word (e.g., "account") can mean different things in different contexts.

### pfin Bounded Contexts

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        pfin Platform                                    │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │  Identity &   │  │  Household   │  │        Accounting            │  │
│  │  Access       │  │              │  │  (Chart of Accounts,         │  │
│  │  ─────────    │  │  ──────────  │  │   Journal Entries,           │  │
│  │  Users        │  │  Households  │  │   Balances)                  │  │
│  │  Sessions     │  │  Members     │  │                              │  │
│  │  Auth tokens  │  │  Roles       │  │  CORE DOMAIN                │  │
│  │  Passwords    │  │  Invitations │  │                              │  │
│  │              │  │              │  └──────────────────────────────┘  │
│  │  GENERIC     │  │  SUPPORTING  │                                    │
│  │  SUBDOMAIN   │  │  SUBDOMAIN   │  ┌──────────────────────────────┐  │
│  └──────────────┘  └──────────────┘  │        Budgeting             │  │
│                                       │  ──────────                  │  │
│  ┌──────────────┐  ┌──────────────┐  │  Budgets, Categories,        │  │
│  │  Portfolio    │  │  Reporting   │  │  Period tracking,            │  │
│  │  ──────────   │  │  ──────────  │  │  Allocations                 │  │
│  │  Holdings     │  │  Balance     │  │                              │  │
│  │  Market data  │  │   sheet      │  │  CORE DOMAIN                │  │
│  │  Performance  │  │  Income stmt │  └──────────────────────────────┘  │
│  │  Cost basis   │  │  Cash flow   │                                    │
│  │              │  │  Net worth   │  ┌──────────────────────────────┐  │
│  │  SUPPORTING  │  │              │  │        Import                │  │
│  │  SUBDOMAIN   │  │  SUPPORTING  │  │  ──────────                  │  │
│  └──────────────┘  │  SUBDOMAIN   │  │  CSV parsing                 │  │
│                     └──────────────┘  │  Bank sync (Plaid)           │  │
│                                       │  Deduplication               │  │
│                                       │  GENERIC SUBDOMAIN           │  │
│                                       └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Context Classification

| Context | Type | Rationale |
|---------|------|-----------|
| **Accounting** | Core Domain | The double-entry ledger is the competitive differentiator -- financial integrity, wallet-as-account model, immutable ledger. This is where the most domain expertise and the highest code quality is needed. |
| **Budgeting** | Core Domain | Budget allocation, envelope tracking, and period rollover are central to the user value proposition. Tightly coupled to accounting data but with its own aggregate rules. |
| **Identity & Access** | Generic Subdomain | Auth is well-understood. Use proven patterns (JWT, bcrypt). Not a differentiator. Could be replaced by an external provider (Auth0, Clerk) later. |
| **Household** | Supporting Subdomain | Multi-tenant collaboration is important but not the core value. It provides the scope/tenancy model that other contexts depend on. |
| **Portfolio** | Supporting Subdomain | Investment tracking adds value but is secondary. Relies on external market data. Can be built after the core ledger. |
| **Reporting** | Supporting Subdomain | Read-only projections of accounting data. No write-side complexity. Mostly query optimization and presentation logic. |
| **Import** | Generic Subdomain | CSV parsing, bank sync, and deduplication are commodity problems. Integration-heavy, not domain-rich. |

### Ubiquitous Language Per Context

**Accounting context:**
- **Account** -- A node in the chart of accounts (asset, liability, equity, income, expense). A wallet IS an account.
- **Journal Entry** -- The atomic unit of record. A balanced set of lines (debits + credits = 0).
- **Journal Line** -- A single posting within a journal entry targeting one account.
- **Balance** -- The sum of all postings to an account. Debits are positive, credits are negative.
- **Void** -- To cancel an entry by creating a reversing entry. The original is never deleted.
- **Trial Balance** -- Sum of all account balances; must equal zero.

**Household context:**
- **Household** -- A group of users who share financial visibility.
- **Member** -- A user's role within a household (owner, admin, member, viewer).
- **Scope** -- Whether an entity belongs to a user (personal) or a household (shared).
- **Invitation** -- A pending request for a user to join a household.

**Budgeting context:**
- **Budget** -- A spending plan for a period, containing category allocations.
- **Category** -- A classification for spending (groceries, rent, utilities). Not the same as an account.
- **Allocation** -- The amount assigned to a category for a budget period.
- **Period** -- A time range (monthly, weekly) over which a budget operates.
- **Rollover** -- Carrying unused allocation from one period to the next.

**Identity context:**
- **User** -- An authenticated person with credentials.
- **Session** -- An active authentication state.
- **Credential** -- Email + password hash, or OAuth token.

---

## 2. Context Mapping

Context mapping defines how bounded contexts relate to each other -- who owns the data, who depends on whom, and what integration patterns are used.

### Context Map Diagram

```
                    ┌───────────────┐
                    │   Identity    │
                    │   & Access    │
                    └───────┬───────┘
                            │
                    Conformist (user ID)
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
     ┌────────────┐  ┌───────────┐  ┌──────────┐
     │ Household  │  │Accounting │  │ Budgeting│
     │            │◀─┤  (CORE)   │─▶│  (CORE)  │
     └──────┬─────┘  └─────┬─────┘  └──────────┘
            │              │
            │         ACL  │  Published
            │              │  Language
            │              │
            │    ┌─────────┼─────────┐
            │    │         │         │
            │    ▼         ▼         ▼
            │  ┌─────┐ ┌────────┐ ┌──────┐
            │  │Port-│ │Report- │ │Import│
            │  │folio│ │ing     │ │      │
            │  └─────┘ └────────┘ └──────┘
            │
            └──── Shared Kernel (scope, tenant ID)
```

### Integration Patterns Between Contexts

| Upstream | Downstream | Pattern | Mechanism |
|----------|------------|---------|-----------|
| Identity | All others | **Conformist** | All contexts accept user IDs as opaque identifiers. No rich user model outside Identity. Downstream contexts conform to Identity's user ID format. |
| Household | Accounting, Budgeting | **Shared Kernel** | The `Scope` concept (personal vs household, user_id vs household_id) is a shared kernel. Both contexts depend on the same scope resolution logic. Kept minimal: just scope type + ID. |
| Accounting | Reporting | **Published Language** | Accounting publishes a stable read API (account balances, ledger entries, trial balance). Reporting consumes this. Accounting owns the data; Reporting only reads. |
| Accounting | Budgeting | **Customer-Supplier** | Budgeting needs transaction data to calculate "spent this period." Accounting is the supplier. Budgeting defines what it needs (spent per category per period); Accounting provides it. |
| Accounting | Portfolio | **Customer-Supplier** | Portfolio needs investment account balances and cost basis data. Accounting supplies it via a defined query interface. |
| Import | Accounting | **Anti-Corruption Layer** | Import ingests external data (CSV, bank feeds) in foreign formats. The ACL translates external formats into the Accounting context's JournalEntry aggregate. Import never directly writes to accounting tables; it produces commands that the Accounting context validates and applies. |
| External (Plaid, market data) | Import, Portfolio | **Anti-Corruption Layer** | External APIs have their own models. ACL adapters translate to internal domain types. |

### Shared Kernel: Scope

The `Scope` value object is the one concept that spans multiple bounded contexts. It is intentionally minimal:

```go
// pkg/scope/scope.go -- shared kernel, kept in pkg/ for cross-context use
package scope

import (
    "errors"

    "github.com/google/uuid"
)

// Type identifies whether an entity belongs to a user or a household.
type Type string

const (
    Personal  Type = "personal"
    Household Type = "household"
)

// Scope identifies the owner of a multi-tenant entity.
// Exactly one of UserID or HouseholdID is set.
type Scope struct {
    typ         Type
    userID      uuid.UUID
    householdID uuid.UUID
}

func NewPersonalScope(userID uuid.UUID) (Scope, error) {
    if userID == uuid.Nil {
        return Scope{}, errors.New("personal scope requires a user ID")
    }
    return Scope{typ: Personal, userID: userID}, nil
}

func NewHouseholdScope(householdID uuid.UUID) (Scope, error) {
    if householdID == uuid.Nil {
        return Scope{}, errors.New("household scope requires a household ID")
    }
    return Scope{typ: Household, householdID: householdID}, nil
}

func (s Scope) Type() Type           { return s.typ }
func (s Scope) UserID() uuid.UUID    { return s.userID }
func (s Scope) HouseholdID() uuid.UUID { return s.householdID }
func (s Scope) IsPersonal() bool     { return s.typ == Personal }
func (s Scope) IsHousehold() bool    { return s.typ == Household }

func (s Scope) IsZero() bool {
    return s == Scope{}
}
```

### Anti-Corruption Layer: Import-to-Accounting

```go
// internal/import/acl/accounting_adapter.go
package acl

import (
    "context"

    "pfin/internal/accounting/app/command"
    "pfin/internal/import/domain"
)

// AccountingPort defines what the Import context needs from Accounting.
// This interface lives in the Import context -- Import is the consumer.
type AccountingPort interface {
    RecordTransaction(ctx context.Context, cmd command.RecordTransaction) error
}

// Translator converts imported bank transactions into accounting commands.
type Translator struct {
    accountMappings map[string]uuid.UUID // bank account ID -> pfin account ID
}

func (t *Translator) Translate(imported domain.BankTransaction) (command.RecordTransaction, error) {
    accountID, ok := t.accountMappings[imported.BankAccountID]
    if !ok {
        return command.RecordTransaction{}, fmt.Errorf("unmapped bank account: %s", imported.BankAccountID)
    }

    return command.RecordTransaction{
        Date:            imported.Date,
        Description:     imported.Description,
        SourceAccountID: accountID,
        // ... map other fields
    }, nil
}
```

---

## 3. Tactical Design in Go

Go's DDD patterns differ significantly from Java/C#. Go lacks classes, inheritance, annotations, and traditional OOP encapsulation. Go-idiomatic DDD relies on:

- **Unexported struct fields** for encapsulation (lowercase fields are private to the package)
- **Constructor functions** (e.g., `NewAccount()`) to enforce invariants at creation
- **Method receivers** for domain behavior on entities/aggregates
- **Interfaces** defined by the consumer (not the provider) for dependency inversion
- **Package boundaries** as the primary architectural enforcement mechanism
- **Struct composition** instead of inheritance

### Key Patterns from Production Go DDD Projects

The patterns below are derived from:
- **ThreeDotsLabs/wild-workouts-go-ddd-example** -- The most comprehensive open-source Go DDD example. Demonstrates CQRS, clean architecture, and domain modeling in a real application.
- **marcusolsson/goddd** -- Port of the classic DDD shipping sample to Go. Shows aggregates, value objects, repositories, and domain services.
- **ThreeDotsLabs/watermill** -- Event-driven architecture library for Go. Provides CQRS, pub/sub, and event sourcing building blocks.

### Pattern 1: Unexported Fields + Constructor + Getters

Go achieves encapsulation at the package level. All domain struct fields are unexported (lowercase). The only way to create a valid instance is through a constructor function. The only way to read fields is through getter methods.

```go
// internal/accounting/domain/account/account.go
package account

type Account struct {
    id          AccountID
    scope       scope.Scope
    name        string
    category    Category
    accountType AccountSubtype
    currency    Currency
    isArchived  bool
    creditLimit Money  // for liability accounts
    metadata    Metadata
    createdAt   time.Time
}

// NewAccount is the only way to create a valid Account.
// It enforces all creation-time invariants.
func NewAccount(
    id AccountID,
    s scope.Scope,
    name string,
    category Category,
    accountType AccountSubtype,
    currency Currency,
) (*Account, error) {
    if name == "" {
        return nil, errors.New("account name is required")
    }
    if s.IsZero() {
        return nil, errors.New("scope is required")
    }
    if !category.IsValid() {
        return nil, fmt.Errorf("invalid category: %s", category)
    }
    if !accountType.BelongsTo(category) {
        return nil, fmt.Errorf("account type %s does not belong to category %s", accountType, category)
    }

    return &Account{
        id:          id,
        scope:       s,
        name:        name,
        category:    category,
        accountType: accountType,
        currency:    currency,
        createdAt:   time.Now(),
    }, nil
}

// Getter methods -- read-only access to unexported fields
func (a Account) ID() AccountID       { return a.id }
func (a Account) Scope() scope.Scope  { return a.scope }
func (a Account) Name() string        { return a.name }
func (a Account) Category() Category  { return a.category }
func (a Account) Currency() Currency  { return a.currency }
func (a Account) IsArchived() bool    { return a.isArchived }
```

### Pattern 2: Behavior on Domain Objects

Domain logic lives on the entity/aggregate, not in services. Methods enforce invariants and return errors when business rules are violated.

```go
// Domain behavior methods on Account
func (a *Account) Rename(newName string) error {
    if newName == "" {
        return errors.New("account name cannot be empty")
    }
    if a.isArchived {
        return ErrAccountArchived
    }
    a.name = newName
    return nil
}

func (a *Account) Archive() error {
    if a.isArchived {
        return ErrAccountAlreadyArchived
    }
    a.isArchived = true
    return nil
}

func (a *Account) SetCreditLimit(limit Money) error {
    if a.category != CategoryLiability {
        return errors.New("credit limit only applies to liability accounts")
    }
    if limit.IsNegative() {
        return errors.New("credit limit must be non-negative")
    }
    a.creditLimit = limit
    return nil
}
```

### Pattern 3: Unmarshal From Database (Reconstitution)

The `UnmarshalFromDatabase` function is a pattern from ThreeDotsLabs. It bypasses normal validation to reconstitute an entity from persisted state. It is explicitly named to signal that it should only be used by repository implementations.

```go
// UnmarshalAccountFromDatabase reconstitutes an Account from persisted state.
// This function bypasses normal validation -- use ONLY in repository implementations.
func UnmarshalAccountFromDatabase(
    id AccountID,
    s scope.Scope,
    name string,
    category Category,
    accountType AccountSubtype,
    currency Currency,
    isArchived bool,
    creditLimit Money,
    metadata Metadata,
    createdAt time.Time,
) (*Account, error) {
    return &Account{
        id:          id,
        scope:       s,
        name:        name,
        category:    category,
        accountType: accountType,
        currency:    currency,
        isArchived:  isArchived,
        creditLimit: creditLimit,
        metadata:    metadata,
        createdAt:   createdAt,
    }, nil
}
```

### Pattern 4: Value Objects as Structs (Not Type Aliases)

Go value objects use structs (not type aliases like `type Money string`) to prevent arbitrary construction. The struct is immutable -- all fields are unexported, all operations return new values.

From ThreeDotsLabs' Wild Workouts, the `Availability` value object uses this pattern:

```go
// Using struct instead of `type Availability string` ensures we control
// what values are possible. With `type Availability string` you could create
// `Availability("i_can_put_anything_here")`.
type Availability struct {
    a string
}

var (
    Available         = Availability{"available"}
    NotAvailable      = Availability{"not_available"}
    TrainingScheduled = Availability{"training_scheduled"}
)
```

### Pattern 5: Factory for Complex Creation

When an aggregate has complex creation rules (e.g., the `Hour` aggregate in Wild Workouts), use a Factory that holds configuration and validates constraints.

```go
type Factory struct {
    fc FactoryConfig  // unexported -- config cannot be changed after creation
}

func NewFactory(fc FactoryConfig) (Factory, error) {
    if err := fc.Validate(); err != nil {
        return Factory{}, errors.Wrap(err, "invalid config")
    }
    return Factory{fc: fc}, nil
}

func (f Factory) NewAvailableHour(hour time.Time) (*Hour, error) {
    if err := f.validateTime(hour); err != nil {
        return nil, err
    }
    return &Hour{hour: hour, availability: Available}, nil
}
```

---

## 4. Go Project Structure

### Recommended Structure for pfin

```
pfin/
├── cmd/
│   └── api/
│       └── main.go                        # Entry point, wiring
│
├── internal/                              # Application code (not importable externally)
│   │
│   ├── accounting/                        # ══ Bounded Context: Accounting ══
│   │   ├── domain/                        # Pure domain model (no framework deps)
│   │   │   ├── account/                   # Account aggregate
│   │   │   │   ├── account.go             # Entity + behavior
│   │   │   │   ├── account_test.go        # Unit tests for domain logic
│   │   │   │   ├── category.go            # Category value object (enum)
│   │   │   │   ├── subtype.go             # AccountSubtype value object
│   │   │   │   └── repository.go          # Repository interface (defined in domain)
│   │   │   │
│   │   │   └── entry/                     # JournalEntry aggregate
│   │   │       ├── entry.go               # Aggregate root + Lines
│   │   │       ├── entry_test.go
│   │   │       ├── line.go                # JournalLine entity (part of aggregate)
│   │   │       ├── status.go              # EntryStatus value object
│   │   │       └── repository.go          # Repository interface
│   │   │
│   │   ├── app/                           # Application layer (use cases)
│   │   │   ├── app.go                     # Application struct (CQRS wiring)
│   │   │   ├── command/                   # Write operations
│   │   │   │   ├── record_transaction.go  # "Record an expense" use case
│   │   │   │   ├── void_entry.go          # "Void a journal entry" use case
│   │   │   │   ├── create_account.go
│   │   │   │   └── archive_account.go
│   │   │   └── query/                     # Read operations
│   │   │       ├── account_ledger.go
│   │   │       ├── trial_balance.go
│   │   │       ├── account_balance.go
│   │   │       └── types.go              # Query result types (read models)
│   │   │
│   │   ├── adapters/                      # Infrastructure implementations
│   │   │   ├── postgres_account_repo.go   # PostgreSQL AccountRepository
│   │   │   ├── postgres_journal_repo.go   # PostgreSQL JournalRepository
│   │   │   └── postgres_ledger_reader.go  # PostgreSQL LedgerReader
│   │   │
│   │   ├── ports/                         # Inbound adapters (HTTP, gRPC)
│   │   │   ├── http.go                    # HTTP handlers
│   │   │   ├── openapi_types.gen.go       # Generated OpenAPI types
│   │   │   └── mappers.go                # DTO <-> Domain mappers
│   │   │
│   │   └── service/                       # Dependency wiring
│   │       └── service.go                 # NewApplication() factory
│   │
│   ├── household/                         # ══ Bounded Context: Household ══
│   │   ├── domain/
│   │   │   └── household/
│   │   │       ├── household.go           # Household aggregate root
│   │   │       ├── member.go              # Member entity
│   │   │       ├── role.go                # Role value object
│   │   │       ├── invitation.go          # Invitation entity
│   │   │       └── repository.go
│   │   ├── app/
│   │   │   ├── app.go
│   │   │   └── command/
│   │   │       ├── create_household.go
│   │   │       ├── invite_member.go
│   │   │       └── accept_invitation.go
│   │   ├── adapters/
│   │   │   └── postgres_household_repo.go
│   │   ├── ports/
│   │   │   └── http.go
│   │   └── service/
│   │       └── service.go
│   │
│   ├── identity/                          # ══ Bounded Context: Identity ══
│   │   ├── domain/
│   │   │   └── user/
│   │   │       ├── user.go
│   │   │       ├── credentials.go
│   │   │       └── repository.go
│   │   ├── app/
│   │   │   └── command/
│   │   │       ├── register.go
│   │   │       └── authenticate.go
│   │   ├── adapters/
│   │   │   └── postgres_user_repo.go
│   │   ├── ports/
│   │   │   └── http.go
│   │   └── service/
│   │       └── service.go
│   │
│   ├── budgeting/                         # ══ Bounded Context: Budgeting ══
│   │   ├── domain/
│   │   │   └── budget/
│   │   │       ├── budget.go              # Budget aggregate root
│   │   │       ├── allocation.go          # Allocation entity
│   │   │       ├── period.go              # Period value object
│   │   │       └── repository.go
│   │   ├── app/
│   │   ├── adapters/
│   │   ├── ports/
│   │   └── service/
│   │
│   ├── portfolio/                         # ══ Bounded Context: Portfolio ══
│   │   └── ...                            # (deferred)
│   │
│   ├── reporting/                         # ══ Bounded Context: Reporting ══
│   │   └── ...                            # (read-only projections)
│   │
│   ├── importing/                         # ══ Bounded Context: Import ══
│   │   ├── domain/
│   │   ├── acl/                           # Anti-corruption layer
│   │   │   └── accounting_adapter.go      # Translates imports -> accounting commands
│   │   ├── app/
│   │   ├── adapters/
│   │   └── ports/
│   │
│   └── common/                            # Cross-cutting (minimal)
│       ├── auth/                          # Auth middleware, context helpers
│       ├── server/                        # HTTP server setup, error responses
│       └── decorator/                     # Command/query decorators (logging, metrics)
│
├── pkg/                                   # Shared kernel + utilities
│   ├── scope/                             # Scope value object (shared kernel)
│   │   └── scope.go
│   ├── money/                             # Money value object
│   │   └── money.go
│   ├── currency/                          # Currency value object
│   │   └── currency.go
│   └── errs/                              # Domain error types
│       └── errors.go
│
├── migrations/                            # PostgreSQL migrations
│   ├── 001_identity.up.sql
│   ├── 002_household.up.sql
│   ├── 003_accounting.up.sql
│   └── ...
│
├── api/                                   # OpenAPI specs
│   └── openapi.yaml
│
└── go.mod
```

### Why This Structure?

**Each bounded context is a top-level package under `internal/`.** This is the primary enforcement mechanism in Go -- packages cannot have circular imports. If `accounting` imports from `household`, then `household` cannot import from `accounting`. This naturally enforces context boundaries.

**Within each context, the layers are:**
1. `domain/` -- Pure domain model. Zero external dependencies (no HTTP, no SQL, no frameworks). Only imports from `pkg/` (shared kernel). This is the inner ring of clean architecture.
2. `app/` -- Application services (use cases). Orchestrates domain objects and repositories. Depends on domain.
3. `adapters/` -- Infrastructure implementations (PostgreSQL, external APIs). Depends on domain interfaces.
4. `ports/` -- Inbound adapters (HTTP handlers, gRPC). Depends on application layer.
5. `service/` -- Dependency wiring (constructor that assembles the application).

**The dependency rule:** dependencies point inward. `ports` -> `app` -> `domain`. `adapters` implements `domain` interfaces. `domain` depends on nothing except `pkg/`.

### Enforcing Boundaries via Go Imports

```go
// ALLOWED: ports imports app
package ports
import "pfin/internal/accounting/app"

// ALLOWED: app imports domain
package app
import "pfin/internal/accounting/domain/entry"

// ALLOWED: adapters imports domain (to implement interface)
package adapters
import "pfin/internal/accounting/domain/entry"

// FORBIDDEN: domain imports adapters (would break clean arch)
// package entry
// import "pfin/internal/accounting/adapters"  // COMPILATION ERROR

// FORBIDDEN: accounting imports household domain directly
// Cross-context communication uses interfaces, not direct imports
// package accounting_app
// import "pfin/internal/household/domain/household"  // DON'T DO THIS

// CORRECT: accounting defines its own port for household data
package command
type HouseholdReader interface {
    GetMemberRole(ctx context.Context, householdID, userID uuid.UUID) (string, error)
}
```

---

## 5. Aggregate Design

Aggregates define transactional consistency boundaries. Everything within an aggregate is modified atomically in a single database transaction. References between aggregates use IDs, not direct object references.

### pfin Aggregate Map

```
┌─────────────────────────────────────────────────────────┐
│ Accounting Context                                       │
│                                                          │
│  ┌─────────────────────┐   ┌──────────────────────────┐ │
│  │ Account Aggregate    │   │ JournalEntry Aggregate   │ │
│  │ ═══════════════════  │   │ ════════════════════════ │ │
│  │                      │   │                          │ │
│  │  Account (root)      │   │  JournalEntry (root)     │ │
│  │    ├─ AccountID      │   │    ├─ EntryID            │ │
│  │    ├─ Scope          │   │    ├─ Scope              │ │
│  │    ├─ Name           │   │    ├─ Date               │ │
│  │    ├─ Category       │   │    ├─ Description        │ │
│  │    ├─ AccountSubtype │   │    ├─ Status             │ │
│  │    ├─ Currency       │   │    └─ []JournalLine      │ │
│  │    ├─ CreditLimit    │   │         ├─ AccountID ──────┼──ref
│  │    └─ Metadata       │   │         ├─ Amount        │ │
│  │                      │   │         └─ Currency      │ │
│  │  Invariants:         │   │                          │ │
│  │  - name not empty    │   │  Invariants:             │ │
│  │  - type ∈ category   │   │  - SUM(amounts) = 0     │ │
│  │  - archived accts    │   │  - >= 2 lines           │ │
│  │    cannot be renamed │   │  - no zero amounts      │ │
│  │                      │   │  - voided entries are    │ │
│  └─────────────────────┘   │    immutable             │ │
│                             └──────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Household Context                                        │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ Household Aggregate                                  │ │
│  │ ═══════════════════                                  │ │
│  │                                                      │ │
│  │  Household (root)                                    │ │
│  │    ├─ HouseholdID                                    │ │
│  │    ├─ Name                                           │ │
│  │    ├─ DefaultCurrency                                │ │
│  │    ├─ CreatedBy (UserID)                             │ │
│  │    └─ []Member                                       │ │
│  │         ├─ MemberID                                  │ │
│  │         ├─ UserID ────────── ref to Identity context  │ │
│  │         ├─ Role (owner/admin/member/viewer)          │ │
│  │         └─ Status (active/invited/removed)           │ │
│  │                                                      │ │
│  │  Invariants:                                         │ │
│  │  - exactly one owner at all times                    │ │
│  │  - max 10 members                                   │ │
│  │  - owner cannot be removed                           │ │
│  │  - cannot invite same user twice                     │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ Invitation Aggregate                                 │ │
│  │  Invitation (root)                                   │ │
│  │    ├─ InvitationID                                   │ │
│  │    ├─ HouseholdID ──── ref                           │ │
│  │    ├─ InvitedEmail                                   │ │
│  │    ├─ Token                                          │ │
│  │    ├─ ExpiresAt                                      │ │
│  │    └─ Status (pending/accepted/expired/revoked)      │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Budgeting Context                                        │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ Budget Aggregate                                     │ │
│  │  Budget (root)                                       │ │
│  │    ├─ BudgetID                                       │ │
│  │    ├─ Scope                                          │ │
│  │    ├─ Name                                           │ │
│  │    ├─ Period (monthly/weekly/custom)                 │ │
│  │    ├─ RolloverEnabled                                │ │
│  │    └─ []Allocation                                   │ │
│  │         ├─ CategoryID ──── ref                       │ │
│  │         ├─ Amount                                    │ │
│  │         └─ RolloverAmount                            │ │
│  │                                                      │ │
│  │  Invariants:                                         │ │
│  │  - no duplicate categories                           │ │
│  │  - amounts non-negative                              │ │
│  │  - total allocations <= optional cap                 │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Aggregate Design Decisions

**Why JournalEntry contains Lines (not a separate aggregate):**
The JournalEntry and its Lines form a single aggregate because:
1. Lines cannot exist without an entry.
2. The balance invariant (sum of amounts = 0) spans all lines within an entry.
3. They must be created and validated atomically.
4. A line has no independent lifecycle.

**Why Account is a separate aggregate from JournalEntry:**
Although JournalLine references an AccountID, the Account and JournalEntry have independent lifecycles. You can create journal entries targeting an account without loading the full Account aggregate. The reference is by ID, not by object.

**Why Household contains Members:**
Members have no meaningful lifecycle outside their household. The "exactly one owner" and "max 10 members" invariants span all members within a household. They must be checked atomically.

**Why Invitation is a separate aggregate from Household:**
Invitations have their own lifecycle (pending -> accepted/expired/revoked) and their own identity (token-based lookup). They reference a household by ID. Accepting an invitation triggers a command on the Household aggregate, but they are modified independently.

---

## 6. Value Objects in Go

Value objects are immutable, compared by value (not identity), and have no side effects. In Go, they are implemented as structs with unexported fields and constructor functions.

### Money Value Object

```go
// pkg/money/money.go
package money

import (
    "errors"
    "fmt"

    "github.com/shopspring/decimal"
)

// Money represents a monetary amount with a currency.
// It is immutable -- all operations return new Money values.
type Money struct {
    amount   decimal.Decimal
    currency string
}

func New(amount decimal.Decimal, currency string) (Money, error) {
    if currency == "" {
        return Money{}, errors.New("currency is required")
    }
    if len(currency) != 3 {
        return Money{}, fmt.Errorf("currency must be 3-letter ISO 4217 code, got %q", currency)
    }
    return Money{amount: amount, currency: currency}, nil
}

func MustNew(amount decimal.Decimal, currency string) Money {
    m, err := New(amount, currency)
    if err != nil {
        panic(err)
    }
    return m
}

func Zero(currency string) Money {
    return MustNew(decimal.Zero, currency)
}

// FromString creates Money from a string amount (e.g., "19.99").
func FromString(amount string, currency string) (Money, error) {
    d, err := decimal.NewFromString(amount)
    if err != nil {
        return Money{}, fmt.Errorf("invalid amount %q: %w", amount, err)
    }
    return New(d, currency)
}

// Getters
func (m Money) Amount() decimal.Decimal { return m.amount }
func (m Money) Currency() string        { return m.currency }
func (m Money) IsZero() bool            { return m.amount.IsZero() }
func (m Money) IsNegative() bool        { return m.amount.IsNegative() }
func (m Money) IsPositive() bool        { return m.amount.IsPositive() }

// String returns the amount formatted to 2 decimal places with currency.
func (m Money) String() string {
    return fmt.Sprintf("%s %s", m.amount.StringFixed(2), m.currency)
}

// Arithmetic -- all return new Money, never mutate
func (m Money) Add(other Money) (Money, error) {
    if m.currency != other.currency {
        return Money{}, fmt.Errorf("cannot add %s to %s: currency mismatch", m.currency, other.currency)
    }
    return Money{amount: m.amount.Add(other.amount), currency: m.currency}, nil
}

func (m Money) Subtract(other Money) (Money, error) {
    if m.currency != other.currency {
        return Money{}, fmt.Errorf("cannot subtract %s from %s: currency mismatch", m.currency, other.currency)
    }
    return Money{amount: m.amount.Sub(other.amount), currency: m.currency}, nil
}

func (m Money) Negate() Money {
    return Money{amount: m.amount.Neg(), currency: m.currency}
}

func (m Money) Multiply(factor decimal.Decimal) Money {
    return Money{amount: m.amount.Mul(factor), currency: m.currency}
}

// Comparison
func (m Money) Equal(other Money) bool {
    return m.currency == other.currency && m.amount.Equal(other.amount)
}

func (m Money) GreaterThan(other Money) bool {
    return m.currency == other.currency && m.amount.GreaterThan(other.amount)
}

func (m Money) LessThan(other Money) bool {
    return m.currency == other.currency && m.amount.LessThan(other.amount)
}

// Abs returns the absolute value.
func (m Money) Abs() Money {
    return Money{amount: m.amount.Abs(), currency: m.currency}
}
```

### AccountID Value Object

```go
// internal/accounting/domain/account/id.go
package account

import (
    "github.com/google/uuid"
)

// AccountID is a strongly-typed identifier for accounts.
// Using a distinct type prevents accidentally passing a UserID where an AccountID is expected.
type AccountID struct {
    id uuid.UUID
}

func NewAccountID() AccountID {
    return AccountID{id: uuid.New()}
}

func AccountIDFromUUID(id uuid.UUID) (AccountID, error) {
    if id == uuid.Nil {
        return AccountID{}, errors.New("account ID cannot be nil")
    }
    return AccountID{id: id}, nil
}

func AccountIDFromString(s string) (AccountID, error) {
    id, err := uuid.Parse(s)
    if err != nil {
        return AccountID{}, fmt.Errorf("invalid account ID %q: %w", s, err)
    }
    return AccountIDFromUUID(id)
}

func (a AccountID) UUID() uuid.UUID { return a.id }
func (a AccountID) String() string  { return a.id.String() }
func (a AccountID) IsZero() bool    { return a.id == uuid.Nil }
```

### Category Value Object (Enum Pattern)

```go
// internal/accounting/domain/account/category.go
package account

import "fmt"

// Category represents the five fundamental account categories.
// Using a struct prevents arbitrary string construction.
type Category struct {
    s string
}

var (
    CategoryAsset     = Category{"asset"}
    CategoryLiability = Category{"liability"}
    CategoryEquity    = Category{"equity"}
    CategoryIncome    = Category{"income"}
    CategoryExpense   = Category{"expense"}
)

var allCategories = []Category{
    CategoryAsset, CategoryLiability, CategoryEquity,
    CategoryIncome, CategoryExpense,
}

func CategoryFromString(s string) (Category, error) {
    for _, c := range allCategories {
        if c.s == s {
            return c, nil
        }
    }
    return Category{}, fmt.Errorf("unknown account category: %q", s)
}

func (c Category) String() string  { return c.s }
func (c Category) IsZero() bool    { return c == Category{} }
func (c Category) IsValid() bool   { return !c.IsZero() }

// IsDebitNormal returns true for asset and expense accounts,
// where increases are recorded as positive (debit) amounts.
func (c Category) IsDebitNormal() bool {
    return c == CategoryAsset || c == CategoryExpense
}

// IsCreditNormal returns true for liability, equity, and income accounts,
// where increases are recorded as negative (credit) amounts.
func (c Category) IsCreditNormal() bool {
    return c == CategoryLiability || c == CategoryEquity || c == CategoryIncome
}
```

### Currency Value Object

```go
// pkg/currency/currency.go
package currency

import "fmt"

// Currency represents an ISO 4217 currency code.
type Currency struct {
    code string
}

// Common currencies -- pre-defined for convenience and to avoid typos.
var (
    USD = Currency{"USD"}
    EUR = Currency{"EUR"}
    GBP = Currency{"GBP"}
    JPY = Currency{"JPY"}
    KES = Currency{"KES"}
)

func FromCode(code string) (Currency, error) {
    if len(code) != 3 {
        return Currency{}, fmt.Errorf("currency code must be 3 characters, got %q", code)
    }
    // Optionally validate against a known list of ISO 4217 codes
    return Currency{code: code}, nil
}

func (c Currency) Code() string { return c.code }
func (c Currency) String() string { return c.code }
func (c Currency) IsZero() bool { return c == Currency{} }
func (c Currency) Equal(other Currency) bool { return c.code == other.code }
```

### DateRange Value Object

```go
// pkg/daterange/daterange.go
package daterange

import (
    "errors"
    "time"
)

type DateRange struct {
    from time.Time
    to   time.Time
}

func New(from, to time.Time) (DateRange, error) {
    if from.IsZero() {
        return DateRange{}, errors.New("from date is required")
    }
    if to.IsZero() {
        return DateRange{}, errors.New("to date is required")
    }
    if to.Before(from) {
        return DateRange{}, errors.New("to date must be after from date")
    }
    return DateRange{from: from, to: to}, nil
}

func (d DateRange) From() time.Time { return d.from }
func (d DateRange) To() time.Time   { return d.to }
func (d DateRange) IsZero() bool    { return d.from.IsZero() && d.to.IsZero() }

func (d DateRange) Contains(t time.Time) bool {
    return !t.Before(d.from) && !t.After(d.to)
}

func (d DateRange) Days() int {
    return int(d.to.Sub(d.from).Hours() / 24)
}
```

---

## 7. Repository Pattern in Go

### Key Principles

1. **Repository interfaces are defined in the domain package** -- the domain owns the contract; infrastructure implements it.
2. **Interfaces are small** -- prefer multiple small interfaces over one large one (Interface Segregation).
3. **All methods take `context.Context` as the first parameter** -- for cancellation, timeouts, and request-scoped values.
4. **The `UpdateFn` pattern** (from ThreeDotsLabs) ensures optimistic locking: the repository loads the aggregate inside a transaction, passes it to the update function, and persists the result.

### Account Repository

```go
// internal/accounting/domain/account/repository.go
package account

import (
    "context"

    "pfin/pkg/scope"
)

type Repository interface {
    // Create persists a new account.
    Create(ctx context.Context, account *Account) error

    // GetByID returns a single account. Returns NotFoundError if missing.
    GetByID(ctx context.Context, id AccountID, s scope.Scope) (*Account, error)

    // List returns accounts matching the filter.
    List(ctx context.Context, s scope.Scope, filter Filter) ([]*Account, error)

    // Update loads the account, applies updateFn, and persists the result
    // within a single database transaction.
    Update(
        ctx context.Context,
        id AccountID,
        s scope.Scope,
        updateFn func(ctx context.Context, a *Account) error,
    ) error
}

// Filter for listing accounts.
type Filter struct {
    Category    *Category
    IsArchived  *bool
    IsVisible   *bool
}

// NotFoundError is returned when an account is not found.
type NotFoundError struct {
    AccountID AccountID
}

func (e NotFoundError) Error() string {
    return fmt.Sprintf("account %s not found", e.AccountID)
}
```

### JournalEntry Repository

```go
// internal/accounting/domain/entry/repository.go
package entry

import (
    "context"
    "time"

    "pfin/pkg/scope"
    "github.com/shopspring/decimal"
)

type Repository interface {
    // CreateEntry inserts the entry header and all lines atomically.
    // Validates the balance invariant before persisting.
    CreateEntry(ctx context.Context, entry *JournalEntry) error

    // VoidEntry creates a reversing entry and marks the original as voided.
    // Both operations happen in a single database transaction.
    VoidEntry(ctx context.Context, entryID EntryID, s scope.Scope, reason string) error

    // GetByID returns a journal entry with its lines loaded.
    GetByID(ctx context.Context, entryID EntryID, s scope.Scope) (*JournalEntry, error)

    // List returns journal entries matching the filter.
    List(ctx context.Context, s scope.Scope, filter EntryFilter) ([]*JournalEntry, error)
}

// LedgerReader is a read-side interface for reporting queries.
// Separated from Repository because read and write models may diverge.
type LedgerReader interface {
    // AccountLedger returns postings for an account with running balance.
    AccountLedger(ctx context.Context, accountID AccountID, filter LedgerFilter) ([]LedgerRow, error)

    // TrialBalance returns the trial balance (must sum to zero).
    TrialBalance(ctx context.Context, s scope.Scope, asOf time.Time) ([]TrialBalanceRow, error)

    // AccountBalance returns the current balance for a single account.
    AccountBalance(ctx context.Context, accountID AccountID, asOf time.Time) (decimal.Decimal, error)
}

type EntryFilter struct {
    DateFrom *time.Time
    DateTo   *time.Time
    Status   *Status
    Limit    int
    Offset   int
}

type LedgerFilter struct {
    DateFrom *time.Time
    DateTo   *time.Time
    Limit    int
    Offset   int
}
```

### PostgreSQL Repository Implementation

```go
// internal/accounting/adapters/postgres_journal_repo.go
package adapters

import (
    "context"
    "database/sql"
    "fmt"

    "pfin/internal/accounting/domain/entry"
    "pfin/pkg/scope"
    "github.com/jackc/pgx/v5/pgxpool"
    "github.com/shopspring/decimal"
)

type PostgresJournalRepository struct {
    pool *pgxpool.Pool
}

func NewPostgresJournalRepository(pool *pgxpool.Pool) *PostgresJournalRepository {
    return &PostgresJournalRepository{pool: pool}
}

func (r *PostgresJournalRepository) CreateEntry(ctx context.Context, e *entry.JournalEntry) error {
    // 1. Validate in domain (fail fast)
    if err := e.Validate(); err != nil {
        return fmt.Errorf("entry validation: %w", err)
    }

    // 2. Begin transaction
    tx, err := r.pool.Begin(ctx)
    if err != nil {
        return fmt.Errorf("begin tx: %w", err)
    }
    defer tx.Rollback(ctx) // no-op if committed

    // 3. Insert journal entry header
    _, err = tx.Exec(ctx, `
        INSERT INTO journal_entries (id, scope, user_id, household_id, date, description, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7)`,
        e.ID().UUID(),
        e.Scope().Type(),
        nullableUUID(e.Scope().UserID()),
        nullableUUID(e.Scope().HouseholdID()),
        e.Date(),
        e.Description(),
        e.Status().String(),
    )
    if err != nil {
        return fmt.Errorf("insert entry: %w", err)
    }

    // 4. Insert all lines
    for _, line := range e.Lines() {
        _, err = tx.Exec(ctx, `
            INSERT INTO journal_lines (id, entry_id, account_id, amount, currency)
            VALUES ($1, $2, $3, $4, $5)`,
            line.ID().UUID(),
            e.ID().UUID(),
            line.AccountID().UUID(),
            line.Amount(),
            line.Currency().Code(),
        )
        if err != nil {
            return fmt.Errorf("insert line: %w", err)
        }
    }

    // 5. Verify balance in DB (defense in depth)
    var sum decimal.Decimal
    err = tx.QueryRow(ctx, `
        SELECT COALESCE(SUM(amount), 0) FROM journal_lines WHERE entry_id = $1`,
        e.ID().UUID(),
    ).Scan(&sum)
    if err != nil {
        return fmt.Errorf("verify balance: %w", err)
    }
    if !sum.IsZero() {
        return fmt.Errorf("entry unbalanced in DB: sum=%s", sum.String())
    }

    // 6. Commit
    if err := tx.Commit(ctx); err != nil {
        return fmt.Errorf("commit: %w", err)
    }
    return nil
}
```

### The UpdateFn Pattern (Optimistic Locking)

This pattern, pioneered by ThreeDotsLabs, is critical for safe aggregate mutations:

```go
// From Wild Workouts -- the repository loads the entity inside a transaction,
// passes it to the caller's function, then persists the result.
func (r *PostgresAccountRepository) Update(
    ctx context.Context,
    id account.AccountID,
    s scope.Scope,
    updateFn func(ctx context.Context, a *account.Account) error,
) error {
    tx, err := r.pool.Begin(ctx)
    if err != nil {
        return fmt.Errorf("begin tx: %w", err)
    }
    defer tx.Rollback(ctx)

    // SELECT ... FOR UPDATE (pessimistic lock within the transaction)
    row := tx.QueryRow(ctx, `
        SELECT id, scope, user_id, household_id, name, category, account_type,
               currency, is_archived, credit_limit, metadata, created_at
        FROM accounts
        WHERE id = $1 AND scope = $2
        FOR UPDATE`, id.UUID(), s.Type())

    acct, err := scanAccount(row)
    if err != nil {
        return fmt.Errorf("load account: %w", err)
    }

    // Let the caller mutate the loaded aggregate
    if err := updateFn(ctx, acct); err != nil {
        return err
    }

    // Persist the mutated aggregate
    _, err = tx.Exec(ctx, `
        UPDATE accounts SET name = $1, is_archived = $2, credit_limit = $3, metadata = $4
        WHERE id = $5`,
        acct.Name(), acct.IsArchived(), acct.CreditLimit(), acct.Metadata(), acct.ID().UUID())
    if err != nil {
        return fmt.Errorf("update account: %w", err)
    }

    return tx.Commit(ctx)
}
```

Usage in an application service:

```go
func (h archiveAccountHandler) Handle(ctx context.Context, cmd ArchiveAccount) error {
    return h.repo.Update(ctx, cmd.AccountID, cmd.Scope,
        func(ctx context.Context, a *account.Account) error {
            return a.Archive() // domain logic
        },
    )
}
```

---

## 8. Application Services & CQRS

The application layer orchestrates domain objects without containing business logic. CQRS (Command Query Responsibility Segregation) separates write operations (commands) from read operations (queries).

### Application Struct (CQRS Wiring)

```go
// internal/accounting/app/app.go
package app

import (
    "pfin/internal/accounting/app/command"
    "pfin/internal/accounting/app/query"
)

type Application struct {
    Commands Commands
    Queries  Queries
}

type Commands struct {
    CreateAccount    command.CreateAccountHandler
    ArchiveAccount   command.ArchiveAccountHandler
    RecordExpense    command.RecordExpenseHandler
    RecordTransfer   command.RecordTransferHandler
    RecordIncome     command.RecordIncomeHandler
    VoidEntry        command.VoidEntryHandler
}

type Queries struct {
    GetAccount      query.GetAccountHandler
    ListAccounts    query.ListAccountsHandler
    AccountLedger   query.AccountLedgerHandler
    AccountBalance  query.AccountBalanceHandler
    TrialBalance    query.TrialBalanceHandler
}
```

### Command Handler Example: Record Expense

```go
// internal/accounting/app/command/record_expense.go
package command

import (
    "context"
    "time"

    "pfin/internal/accounting/domain/account"
    "pfin/internal/accounting/domain/entry"
    "pfin/pkg/money"
    "pfin/pkg/scope"
    "github.com/shopspring/decimal"
)

// RecordExpense is a command DTO representing the user's intent.
type RecordExpense struct {
    Date             time.Time
    Description      string
    Amount           decimal.Decimal
    Currency         string
    SourceAccountID  account.AccountID  // e.g., checking account (debit source: asset)
    ExpenseAccountID account.AccountID  // e.g., groceries (debit target: expense)
    Scope            scope.Scope
}

// RecordExpenseHandler is the public type exposed to ports.
type RecordExpenseHandler struct {
    entryRepo   entry.Repository
    accountRepo account.Repository
}

func NewRecordExpenseHandler(
    entryRepo entry.Repository,
    accountRepo account.Repository,
) RecordExpenseHandler {
    if entryRepo == nil {
        panic("nil entryRepo")
    }
    if accountRepo == nil {
        panic("nil accountRepo")
    }
    return RecordExpenseHandler{
        entryRepo:   entryRepo,
        accountRepo: accountRepo,
    }
}

func (h RecordExpenseHandler) Handle(ctx context.Context, cmd RecordExpense) error {
    // 1. Validate that both accounts exist and belong to the same scope
    sourceAcct, err := h.accountRepo.GetByID(ctx, cmd.SourceAccountID, cmd.Scope)
    if err != nil {
        return fmt.Errorf("source account: %w", err)
    }
    expenseAcct, err := h.accountRepo.GetByID(ctx, cmd.ExpenseAccountID, cmd.Scope)
    if err != nil {
        return fmt.Errorf("expense account: %w", err)
    }

    // 2. Validate business rules
    if sourceAcct.IsArchived() {
        return errors.New("source account is archived")
    }
    if expenseAcct.Category() != account.CategoryExpense {
        return errors.New("target account must be an expense account")
    }

    // 3. Build the journal entry using the domain factory
    je, err := entry.NewExpenseEntry(
        cmd.Scope,
        cmd.Date,
        cmd.Description,
        cmd.Amount,
        cmd.Currency,
        cmd.SourceAccountID,
        cmd.ExpenseAccountID,
    )
    if err != nil {
        return fmt.Errorf("create entry: %w", err)
    }

    // 4. Persist atomically
    if err := h.entryRepo.CreateEntry(ctx, je); err != nil {
        return fmt.Errorf("persist entry: %w", err)
    }

    return nil
}
```

### Query Handler Example: Account Ledger

```go
// internal/accounting/app/query/account_ledger.go
package query

import (
    "context"
    "time"

    "pfin/internal/accounting/domain/account"
    "pfin/internal/accounting/domain/entry"
)

type AccountLedger struct {
    AccountID account.AccountID
    DateFrom  *time.Time
    DateTo    *time.Time
    Limit     int
    Offset    int
}

type AccountLedgerHandler struct {
    reader entry.LedgerReader
}

func NewAccountLedgerHandler(reader entry.LedgerReader) AccountLedgerHandler {
    return AccountLedgerHandler{reader: reader}
}

func (h AccountLedgerHandler) Handle(ctx context.Context, q AccountLedger) ([]entry.LedgerRow, error) {
    return h.reader.AccountLedger(ctx, q.AccountID, entry.LedgerFilter{
        DateFrom: q.DateFrom,
        DateTo:   q.DateTo,
        Limit:    q.Limit,
        Offset:   q.Offset,
    })
}
```

### Command/Query Decorators

Following ThreeDotsLabs' pattern, use decorators for cross-cutting concerns (logging, metrics, tracing) without polluting business logic:

```go
// internal/common/decorator/command.go
package decorator

import (
    "context"
    "fmt"
    "time"

    "log/slog"
)

// CommandHandler is the generic interface for all command handlers.
type CommandHandler[C any] interface {
    Handle(ctx context.Context, cmd C) error
}

// commandLoggingDecorator wraps a handler with structured logging.
type commandLoggingDecorator[C any] struct {
    base   CommandHandler[C]
    logger *slog.Logger
}

func (d commandLoggingDecorator[C]) Handle(ctx context.Context, cmd C) error {
    handlerType := fmt.Sprintf("%T", d.base)
    logger := d.logger.With("command", handlerType)

    logger.Info("executing command", "command_body", cmd)

    start := time.Now()
    err := d.base.Handle(ctx, cmd)
    duration := time.Since(start)

    if err != nil {
        logger.Error("command failed", "error", err, "duration", duration)
    } else {
        logger.Info("command succeeded", "duration", duration)
    }

    return err
}

// ApplyCommandDecorators wraps a handler with logging and metrics.
func ApplyCommandDecorators[C any](
    handler CommandHandler[C],
    logger *slog.Logger,
) CommandHandler[C] {
    return commandLoggingDecorator[C]{
        base:   handler,
        logger: logger,
    }
}
```

### Service Wiring (Dependency Injection)

```go
// internal/accounting/service/service.go
package service

import (
    "log/slog"

    "pfin/internal/accounting/adapters"
    "pfin/internal/accounting/app"
    "pfin/internal/accounting/app/command"
    "pfin/internal/accounting/app/query"
    "github.com/jackc/pgx/v5/pgxpool"
)

func NewApplication(pool *pgxpool.Pool, logger *slog.Logger) app.Application {
    accountRepo := adapters.NewPostgresAccountRepository(pool)
    journalRepo := adapters.NewPostgresJournalRepository(pool)
    ledgerReader := adapters.NewPostgresLedgerReader(pool)

    return app.Application{
        Commands: app.Commands{
            CreateAccount:  command.NewCreateAccountHandler(accountRepo),
            ArchiveAccount: command.NewArchiveAccountHandler(accountRepo),
            RecordExpense:  command.NewRecordExpenseHandler(journalRepo, accountRepo),
            RecordTransfer: command.NewRecordTransferHandler(journalRepo, accountRepo),
            RecordIncome:   command.NewRecordIncomeHandler(journalRepo, accountRepo),
            VoidEntry:      command.NewVoidEntryHandler(journalRepo),
        },
        Queries: app.Queries{
            GetAccount:     query.NewGetAccountHandler(accountRepo),
            ListAccounts:   query.NewListAccountsHandler(accountRepo),
            AccountLedger:  query.NewAccountLedgerHandler(ledgerReader),
            AccountBalance: query.NewAccountBalanceHandler(ledgerReader),
            TrialBalance:   query.NewTrialBalanceHandler(ledgerReader),
        },
    }
}
```

---

## 9. Domain Events

Domain events represent something meaningful that happened in the domain. They are named in past tense and capture the facts of what occurred.

### Event vs Command

| | Command | Event |
|---|---------|-------|
| **Tense** | Imperative: "RecordExpense" | Past: "ExpenseRecorded" |
| **Semantics** | Request to do something (may be rejected) | Notification that something happened (fact) |
| **Handler count** | Exactly one | Zero or more |
| **Failure** | The command fails, operation is rolled back | The event already happened; handlers must be idempotent |

### Domain Event Definitions

```go
// internal/accounting/domain/entry/events.go
package entry

import (
    "time"

    "pfin/internal/accounting/domain/account"
    "pfin/pkg/scope"
    "github.com/google/uuid"
    "github.com/shopspring/decimal"
)

// Event is the base interface for all domain events.
type Event interface {
    EventName() string
    OccurredAt() time.Time
}

// EntryRecorded is emitted when a new journal entry is persisted.
type EntryRecorded struct {
    EntryID     EntryID
    Scope       scope.Scope
    Date        time.Time
    Description string
    Lines       []EntryRecordedLine
    occurredAt  time.Time
}

type EntryRecordedLine struct {
    AccountID account.AccountID
    Amount    decimal.Decimal
    Currency  string
}

func (e EntryRecorded) EventName() string    { return "accounting.entry_recorded" }
func (e EntryRecorded) OccurredAt() time.Time { return e.occurredAt }

// EntryVoided is emitted when a journal entry is voided.
type EntryVoided struct {
    OriginalEntryID EntryID
    ReversalEntryID EntryID
    Scope           scope.Scope
    Reason          string
    occurredAt      time.Time
}

func (e EntryVoided) EventName() string    { return "accounting.entry_voided" }
func (e EntryVoided) OccurredAt() time.Time { return e.occurredAt }

// AccountBalanceChanged is emitted when an account's balance changes
// (as a result of an entry being recorded or voided).
type AccountBalanceChanged struct {
    AccountID  account.AccountID
    NewBalance decimal.Decimal
    ChangeAmount decimal.Decimal
    occurredAt time.Time
}

func (e AccountBalanceChanged) EventName() string    { return "accounting.account_balance_changed" }
func (e AccountBalanceChanged) OccurredAt() time.Time { return e.occurredAt }
```

### Collecting Events on an Aggregate

The aggregate collects events during its lifecycle. After the repository persists the aggregate, it dispatches the collected events.

```go
// internal/accounting/domain/entry/entry.go
package entry

type JournalEntry struct {
    id          EntryID
    scope       scope.Scope
    date        time.Time
    description string
    status      Status
    lines       []JournalLine
    voidedBy    *EntryID

    // Domain events collected during the lifecycle of this aggregate.
    // Not persisted -- dispatched after successful save.
    events []Event
}

// Events returns and clears the collected domain events.
func (je *JournalEntry) Events() []Event {
    events := je.events
    je.events = nil
    return events
}

func (je *JournalEntry) recordEvent(e Event) {
    je.events = append(je.events, e)
}
```

### Where Events Are Dispatched

Events are dispatched after the repository successfully persists the aggregate. This ensures events are only published for changes that actually happened.

```go
// internal/accounting/adapters/postgres_journal_repo.go
func (r *PostgresJournalRepository) CreateEntry(ctx context.Context, e *entry.JournalEntry) error {
    // ... (insert header + lines + verify balance as shown above) ...

    if err := tx.Commit(ctx); err != nil {
        return fmt.Errorf("commit: %w", err)
    }

    // Dispatch events AFTER successful commit
    for _, event := range e.Events() {
        if err := r.eventPublisher.Publish(ctx, event); err != nil {
            // Log but don't fail -- the entry is already committed.
            // Use an outbox pattern for guaranteed delivery in production.
            r.logger.Error("failed to publish event", "event", event.EventName(), "error", err)
        }
    }

    return nil
}
```

### Event Consumers (Cross-Context Communication)

```go
// Budgeting context listens for EntryRecorded events to update budget tracking.
// internal/budgeting/app/subscriber/on_entry_recorded.go
package subscriber

type OnEntryRecorded struct {
    budgetRepo budget.Repository
}

func (h OnEntryRecorded) Handle(ctx context.Context, event entry.EntryRecorded) error {
    // Extract category from the entry lines, update budget spent amounts.
    // This is the subscriber's responsibility to map accounting events
    // into budgeting concepts.
    for _, line := range event.Lines {
        // ... update budget tracking for this category/period
    }
    return nil
}
```

### Outbox Pattern for Reliable Events (Production)

For production reliability, use the transactional outbox pattern: write events to an `outbox` table in the same database transaction as the aggregate, then asynchronously publish them. This guarantees at-least-once delivery.

```sql
CREATE TABLE outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_name TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    retry_count INT NOT NULL DEFAULT 0
);
```

---

## 10. Concrete Code: pfin Domain Model

### JournalEntry Aggregate (the most complex aggregate)

```go
// internal/accounting/domain/entry/entry.go
package entry

import (
    "errors"
    "fmt"
    "time"

    "pfin/internal/accounting/domain/account"
    "pfin/pkg/scope"
    "github.com/google/uuid"
    "github.com/shopspring/decimal"
)

var (
    ErrTooFewLines     = errors.New("journal entry must have at least 2 lines")
    ErrUnbalancedEntry = errors.New("journal entry must be balanced (sum of amounts = 0)")
    ErrZeroAmount      = errors.New("journal line amount cannot be zero")
    ErrVoidedEntry     = errors.New("voided entries cannot be modified")
    ErrAlreadyVoided   = errors.New("entry is already voided")
    ErrEmptyDescription = errors.New("journal entry description is required")
)

// EntryID is a strongly-typed identifier.
type EntryID struct {
    id uuid.UUID
}

func NewEntryID() EntryID             { return EntryID{id: uuid.New()} }
func EntryIDFromUUID(id uuid.UUID) EntryID { return EntryID{id: id} }
func (e EntryID) UUID() uuid.UUID     { return e.id }
func (e EntryID) String() string      { return e.id.String() }
func (e EntryID) IsZero() bool        { return e.id == uuid.Nil }

// JournalEntry is the aggregate root for the double-entry ledger.
type JournalEntry struct {
    id          EntryID
    scope       scope.Scope
    date        time.Time
    description string
    status      Status
    lines       []JournalLine
    voidedBy    *EntryID
    createdAt   time.Time

    events []Event
}

// NewJournalEntry creates a validated journal entry.
func NewJournalEntry(
    s scope.Scope,
    date time.Time,
    description string,
    lines []JournalLine,
) (*JournalEntry, error) {
    if s.IsZero() {
        return nil, errors.New("scope is required")
    }
    if description == "" {
        return nil, ErrEmptyDescription
    }
    if date.IsZero() {
        return nil, errors.New("date is required")
    }

    je := &JournalEntry{
        id:          NewEntryID(),
        scope:       s,
        date:        date,
        description: description,
        status:      StatusCleared,
        lines:       lines,
        createdAt:   time.Now(),
    }

    if err := je.Validate(); err != nil {
        return nil, err
    }

    je.recordEvent(EntryRecorded{
        EntryID:     je.id,
        Scope:       je.scope,
        Date:        je.date,
        Description: je.description,
        Lines:       je.toEventLines(),
        occurredAt:  time.Now(),
    })

    return je, nil
}

// NewExpenseEntry is a convenience factory for the common "record an expense" case.
// It creates a balanced 2-line entry: debit expense account, credit source account.
func NewExpenseEntry(
    s scope.Scope,
    date time.Time,
    description string,
    amount decimal.Decimal,
    currency string,
    sourceAccountID account.AccountID,
    expenseAccountID account.AccountID,
) (*JournalEntry, error) {
    if amount.LessThanOrEqual(decimal.Zero) {
        return nil, errors.New("expense amount must be positive")
    }

    lines := []JournalLine{
        NewJournalLine(expenseAccountID, amount, currency),         // debit expense (+)
        NewJournalLine(sourceAccountID, amount.Neg(), currency),    // credit source (-)
    }

    return NewJournalEntry(s, date, description, lines)
}

// NewTransferEntry creates a balanced 2-line entry for account-to-account transfers.
func NewTransferEntry(
    s scope.Scope,
    date time.Time,
    description string,
    amount decimal.Decimal,
    currency string,
    fromAccountID account.AccountID,
    toAccountID account.AccountID,
) (*JournalEntry, error) {
    if amount.LessThanOrEqual(decimal.Zero) {
        return nil, errors.New("transfer amount must be positive")
    }

    lines := []JournalLine{
        NewJournalLine(toAccountID, amount, currency),          // debit destination (+)
        NewJournalLine(fromAccountID, amount.Neg(), currency),  // credit source (-)
    }

    return NewJournalEntry(s, date, description, lines)
}

// Validate checks the balance invariant.
func (je *JournalEntry) Validate() error {
    if len(je.lines) < 2 {
        return ErrTooFewLines
    }

    sum := decimal.Zero
    for _, line := range je.lines {
        if line.Amount().IsZero() {
            return ErrZeroAmount
        }
        sum = sum.Add(line.Amount())
    }

    if !sum.IsZero() {
        return fmt.Errorf("%w: sum=%s", ErrUnbalancedEntry, sum.String())
    }

    return nil
}

// Void marks this entry as voided and records a reversal entry ID.
func (je *JournalEntry) Void(reversalID EntryID) error {
    if je.status == StatusVoided {
        return ErrAlreadyVoided
    }
    je.status = StatusVoided
    je.voidedBy = &reversalID

    je.recordEvent(EntryVoided{
        OriginalEntryID: je.id,
        ReversalEntryID: reversalID,
        Scope:           je.scope,
        occurredAt:      time.Now(),
    })

    return nil
}

// CreateReversalEntry creates a new entry with all amounts negated.
func (je *JournalEntry) CreateReversalEntry(reason string) (*JournalEntry, error) {
    if je.status == StatusVoided {
        return nil, ErrAlreadyVoided
    }

    reversedLines := make([]JournalLine, len(je.lines))
    for i, line := range je.lines {
        reversedLines[i] = NewJournalLine(
            line.AccountID(),
            line.Amount().Neg(),
            line.Currency(),
        )
    }

    desc := fmt.Sprintf("VOID: %s — %s", je.description, reason)
    return NewJournalEntry(je.scope, time.Now(), desc, reversedLines)
}

// Getters
func (je JournalEntry) ID() EntryID            { return je.id }
func (je JournalEntry) Scope() scope.Scope      { return je.scope }
func (je JournalEntry) Date() time.Time          { return je.date }
func (je JournalEntry) Description() string      { return je.description }
func (je JournalEntry) Status() Status           { return je.status }
func (je JournalEntry) Lines() []JournalLine     { return je.lines }
func (je JournalEntry) VoidedBy() *EntryID       { return je.voidedBy }
func (je JournalEntry) CreatedAt() time.Time     { return je.createdAt }

func (je *JournalEntry) Events() []Event {
    events := je.events
    je.events = nil
    return events
}

func (je *JournalEntry) recordEvent(e Event) {
    je.events = append(je.events, e)
}

func (je *JournalEntry) toEventLines() []EntryRecordedLine {
    result := make([]EntryRecordedLine, len(je.lines))
    for i, line := range je.lines {
        result[i] = EntryRecordedLine{
            AccountID: line.AccountID(),
            Amount:    line.Amount(),
            Currency:  line.Currency(),
        }
    }
    return result
}

// UnmarshalJournalEntryFromDatabase reconstitutes from persisted state.
// ONLY for use in repository implementations.
func UnmarshalJournalEntryFromDatabase(
    id EntryID,
    s scope.Scope,
    date time.Time,
    description string,
    status Status,
    lines []JournalLine,
    voidedBy *EntryID,
    createdAt time.Time,
) *JournalEntry {
    return &JournalEntry{
        id:          id,
        scope:       s,
        date:        date,
        description: description,
        status:      status,
        lines:       lines,
        voidedBy:    voidedBy,
        createdAt:   createdAt,
    }
}
```

### JournalLine (Child Entity within the Aggregate)

```go
// internal/accounting/domain/entry/line.go
package entry

import (
    "pfin/internal/accounting/domain/account"
    "github.com/google/uuid"
    "github.com/shopspring/decimal"
)

type LineID struct {
    id uuid.UUID
}

func NewLineID() LineID             { return LineID{id: uuid.New()} }
func LineIDFromUUID(id uuid.UUID) LineID { return LineID{id: id} }
func (l LineID) UUID() uuid.UUID    { return l.id }

// JournalLine is a single posting within a journal entry.
// It is not an aggregate root -- it has no independent lifecycle.
type JournalLine struct {
    id        LineID
    accountID account.AccountID
    amount    decimal.Decimal
    currency  string
}

func NewJournalLine(
    accountID account.AccountID,
    amount decimal.Decimal,
    currency string,
) JournalLine {
    return JournalLine{
        id:        NewLineID(),
        accountID: accountID,
        amount:    amount,
        currency:  currency,
    }
}

func UnmarshalJournalLineFromDatabase(
    id LineID,
    accountID account.AccountID,
    amount decimal.Decimal,
    currency string,
) JournalLine {
    return JournalLine{
        id:        id,
        accountID: accountID,
        amount:    amount,
        currency:  currency,
    }
}

func (l JournalLine) ID() LineID                   { return l.id }
func (l JournalLine) AccountID() account.AccountID { return l.accountID }
func (l JournalLine) Amount() decimal.Decimal      { return l.amount }
func (l JournalLine) Currency() string             { return l.currency }
```

### Entry Status Value Object

```go
// internal/accounting/domain/entry/status.go
package entry

import "fmt"

type Status struct {
    s string
}

var (
    StatusPending    = Status{"pending"}
    StatusCleared    = Status{"cleared"}
    StatusReconciled = Status{"reconciled"}
    StatusVoided     = Status{"voided"}
)

var allStatuses = []Status{StatusPending, StatusCleared, StatusReconciled, StatusVoided}

func StatusFromString(s string) (Status, error) {
    for _, status := range allStatuses {
        if status.s == s {
            return status, nil
        }
    }
    return Status{}, fmt.Errorf("unknown entry status: %q", s)
}

func (s Status) String() string { return s.s }
func (s Status) IsZero() bool   { return s == Status{} }
```

### Household Aggregate

```go
// internal/household/domain/household/household.go
package household

import (
    "errors"
    "fmt"
    "time"

    "pfin/pkg/scope"
    "github.com/google/uuid"
)

var (
    ErrMaxMembersReached    = errors.New("household has reached maximum member count")
    ErrUserAlreadyMember    = errors.New("user is already a member of this household")
    ErrCannotRemoveOwner    = errors.New("cannot remove the household owner")
    ErrMustHaveOneOwner     = errors.New("household must have exactly one owner")
    ErrMemberNotFound       = errors.New("member not found in household")
    ErrInsufficientRole     = errors.New("insufficient role for this action")
)

const MaxMembers = 10

type HouseholdID struct {
    id uuid.UUID
}

func NewHouseholdID() HouseholdID              { return HouseholdID{id: uuid.New()} }
func HouseholdIDFromUUID(id uuid.UUID) HouseholdID { return HouseholdID{id: id} }
func (h HouseholdID) UUID() uuid.UUID          { return h.id }
func (h HouseholdID) String() string           { return h.id.String() }

type Household struct {
    id              HouseholdID
    name            string
    defaultCurrency string
    createdBy       uuid.UUID
    members         []Member
    createdAt       time.Time
}

func NewHousehold(name string, defaultCurrency string, ownerUserID uuid.UUID) (*Household, error) {
    if name == "" {
        return nil, errors.New("household name is required")
    }

    h := &Household{
        id:              NewHouseholdID(),
        name:            name,
        defaultCurrency: defaultCurrency,
        createdBy:       ownerUserID,
        createdAt:       time.Now(),
    }

    // The creator is automatically the owner
    ownerMember := NewMember(ownerUserID, RoleOwner)
    h.members = []Member{ownerMember}

    return h, nil
}

func (h *Household) AddMember(userID uuid.UUID, role Role) error {
    if len(h.members) >= MaxMembers {
        return ErrMaxMembersReached
    }
    for _, m := range h.members {
        if m.UserID() == userID {
            return ErrUserAlreadyMember
        }
    }
    if role == RoleOwner {
        return errors.New("cannot add a second owner; use TransferOwnership")
    }

    h.members = append(h.members, NewMember(userID, role))
    return nil
}

func (h *Household) RemoveMember(userID uuid.UUID) error {
    for i, m := range h.members {
        if m.UserID() == userID {
            if m.Role() == RoleOwner {
                return ErrCannotRemoveOwner
            }
            h.members = append(h.members[:i], h.members[i+1:]...)
            return nil
        }
    }
    return ErrMemberNotFound
}

func (h *Household) ChangeMemberRole(userID uuid.UUID, newRole Role) error {
    for i, m := range h.members {
        if m.UserID() == userID {
            if m.Role() == RoleOwner && newRole != RoleOwner {
                return ErrCannotRemoveOwner
            }
            h.members[i] = m.WithRole(newRole)
            return nil
        }
    }
    return ErrMemberNotFound
}

func (h *Household) TransferOwnership(currentOwnerID, newOwnerID uuid.UUID) error {
    var currentOwnerIdx, newOwnerIdx int = -1, -1
    for i, m := range h.members {
        if m.UserID() == currentOwnerID {
            currentOwnerIdx = i
        }
        if m.UserID() == newOwnerID {
            newOwnerIdx = i
        }
    }
    if currentOwnerIdx == -1 || h.members[currentOwnerIdx].Role() != RoleOwner {
        return errors.New("current owner not found")
    }
    if newOwnerIdx == -1 {
        return ErrMemberNotFound
    }

    h.members[currentOwnerIdx] = h.members[currentOwnerIdx].WithRole(RoleAdmin)
    h.members[newOwnerIdx] = h.members[newOwnerIdx].WithRole(RoleOwner)
    return nil
}

// Getters
func (h Household) ID() HouseholdID       { return h.id }
func (h Household) Name() string           { return h.name }
func (h Household) Members() []Member      { return h.members }
func (h Household) MemberCount() int       { return len(h.members) }
func (h Household) CreatedBy() uuid.UUID   { return h.createdBy }

func (h Household) IsMember(userID uuid.UUID) bool {
    for _, m := range h.members {
        if m.UserID() == userID {
            return true
        }
    }
    return false
}

func (h Household) GetMemberRole(userID uuid.UUID) (Role, error) {
    for _, m := range h.members {
        if m.UserID() == userID {
            return m.Role(), nil
        }
    }
    return Role{}, ErrMemberNotFound
}
```

### Role Value Object

```go
// internal/household/domain/household/role.go
package household

import "fmt"

type Role struct {
    s string
}

var (
    RoleOwner  = Role{"owner"}
    RoleAdmin  = Role{"admin"}
    RoleMember = Role{"member"}
    RoleViewer = Role{"viewer"}
)

var allRoles = []Role{RoleOwner, RoleAdmin, RoleMember, RoleViewer}

func RoleFromString(s string) (Role, error) {
    for _, r := range allRoles {
        if r.s == s {
            return r, nil
        }
    }
    return Role{}, fmt.Errorf("unknown household role: %q", s)
}

func (r Role) String() string { return r.s }
func (r Role) IsZero() bool   { return r == Role{} }

// CanManageMembers returns true if this role can invite/remove/change members.
func (r Role) CanManageMembers() bool {
    return r == RoleOwner || r == RoleAdmin
}

// CanWrite returns true if this role can create/edit transactions, accounts, budgets.
func (r Role) CanWrite() bool {
    return r == RoleOwner || r == RoleAdmin || r == RoleMember
}

// CanRead returns true if this role can view data. All roles can read.
func (r Role) CanRead() bool {
    return !r.IsZero()
}
```

### Member Entity

```go
// internal/household/domain/household/member.go
package household

import (
    "github.com/google/uuid"
)

type MemberID struct {
    id uuid.UUID
}

func NewMemberID() MemberID { return MemberID{id: uuid.New()} }

type Member struct {
    id     MemberID
    userID uuid.UUID
    role   Role
}

func NewMember(userID uuid.UUID, role Role) Member {
    return Member{
        id:     NewMemberID(),
        userID: userID,
        role:   role,
    }
}

func (m Member) ID() MemberID       { return m.id }
func (m Member) UserID() uuid.UUID  { return m.userID }
func (m Member) Role() Role          { return m.role }

func (m Member) WithRole(newRole Role) Member {
    return Member{
        id:     m.id,
        userID: m.userID,
        role:   newRole,
    }
}
```

---

## 11. Reference Projects & Sources

### Primary Go DDD Example Projects

| Project | URL | What It Demonstrates |
|---------|-----|---------------------|
| **Wild Workouts (ThreeDotsLabs)** | https://github.com/ThreeDotsLabs/wild-workouts-go-ddd-example | CQRS + DDD + Clean Architecture in Go. The gold standard for Go DDD examples. Shows: unexported fields, constructor functions, repository pattern with `UpdateFn`, command/query handlers, domain events, decorators, service wiring. |
| **GoDDD (Marcus Olsson)** | https://github.com/marcusolsson/goddd | Port of the classic DDD shipping sample to Go. Shows: aggregate roots (Cargo), value objects (TrackingID, RouteSpecification), repository interfaces, domain services (RoutingService), application services (booking). |
| **Watermill (ThreeDotsLabs)** | https://github.com/ThreeDotsLabs/watermill | Event-driven architecture library. Provides: pub/sub, CQRS components, outbox pattern. Not a DDD example itself, but the library used by Wild Workouts for event handling. |

### Key Articles (ThreeDotsLabs)

| Article | Topic |
|---------|-------|
| "When microservices in Go are not enough: introduction to DDD Lite" | Why DDD in Go, basic patterns |
| "Repository pattern: painless way to simplify your Go service logic" | Repository interface, UpdateFn pattern |
| "Introducing Clean Architecture by refactoring a Go project" | Layer separation, dependency rule |
| "Introducing basic CQRS by refactoring" | Command/query separation |
| "Combining DDD, CQRS, and Clean Architecture" | Full integration of all patterns |
| "Repository secure by design" | How to prevent unauthorized data access through repository design |

All articles at: https://threedots.tech/

### GoDDD Talk

"Building an Enterprise Service in Go" by Marcus Olsson at Golang UK Conference 2016 -- YouTube. Walks through the goddd project design decisions.

### Patterns Summary

**What production Go services actually use:**

1. **Unexported fields + constructors** -- Universal. Every serious Go DDD project uses this.
2. **Repository interfaces in domain** -- Universal. The domain defines what persistence looks like; infrastructure implements it.
3. **CQRS (command/query separation)** -- Very common. Even without separate read/write databases, separating the handler types clarifies intent.
4. **UpdateFn pattern** -- ThreeDotsLabs' signature pattern. Load-in-transaction, mutate, persist. Prevents lost updates.
5. **Value objects as structs** -- Common for enums and typed IDs. Prevents invalid states at compile time.
6. **Factory pattern** -- Used when creation is complex. ThreeDotsLabs uses `Factory` structs; simpler cases use `NewX()` functions.
7. **UnmarshalFromDatabase** -- ThreeDotsLabs pattern. Separates "create new" validation from "reconstitute existing" hydration.
8. **Domain events** -- Used for cross-context communication and projections. Dispatched after successful persistence.
9. **Package boundaries for context separation** -- Go's package import rules naturally enforce bounded context boundaries.
10. **Decorator pattern for cross-cutting concerns** -- Logging, metrics, tracing wrapped around command/query handlers.

---

*Research complete: 2026-03-20*
