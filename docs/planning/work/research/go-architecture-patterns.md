# Research: Go Architecture Patterns for pfin

**Context:** Production-grade architecture patterns for the pfin personal finance platform (Go + PostgreSQL + Next.js). Covers clean architecture, hexagonal architecture, modular monolith, DI, error handling, testing, middleware, and concrete project structure.
**Date:** 2026-03-20
**Status:** Research complete

---

## Table of Contents

1. [Clean Architecture in Go](#1-clean-architecture-in-go)
2. [Hexagonal Architecture (Ports & Adapters) in Go](#2-hexagonal-architecture-ports--adapters-in-go)
3. [Modular Monolith Pattern](#3-modular-monolith-pattern)
4. [Dependency Injection in Go](#4-dependency-injection-in-go)
5. [Error Handling Patterns](#5-error-handling-patterns)
6. [Testing Patterns](#6-testing-patterns)
7. [Middleware and Cross-Cutting Concerns](#7-middleware-and-cross-cutting-concerns)
8. [Concrete Project Structure for pfin](#8-concrete-project-structure-for-pfin)
9. [Real-World Go Architecture References](#9-real-world-go-architecture-references)
10. [Recommended Libraries](#10-recommended-libraries)
11. [Summary and Recommendations](#11-summary-and-recommendations)

---

## 1. Clean Architecture in Go

### The Dependency Rule

Uncle Bob's clean architecture is built on one principle: **source code dependencies must point inward**. Inner layers define interfaces; outer layers implement them. The domain never imports infrastructure.

```
┌──────────────────────────────────────────────────────┐
│                   Infrastructure                      │
│  (PostgreSQL, HTTP, external APIs, file system)       │
│  ┌──────────────────────────────────────────────┐    │
│  │              Interface / Adapter              │    │
│  │  (HTTP handlers, gRPC servers, CLI, mappers)  │    │
│  │  ┌──────────────────────────────────────┐    │    │
│  │  │          Application Layer            │    │    │
│  │  │  (use cases, application services)    │    │    │
│  │  │  ┌──────────────────────────────┐    │    │    │
│  │  │  │        Domain Layer           │    │    │    │
│  │  │  │  (entities, value objects,    │    │    │    │
│  │  │  │   repository interfaces,      │    │    │    │
│  │  │  │   domain services)            │    │    │    │
│  │  │  └──────────────────────────────┘    │    │    │
│  │  └──────────────────────────────────────┘    │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

Dependencies: Infrastructure -> Adapter -> Application -> Domain. Never the reverse.

### Why Go Is Naturally Suited to Clean Architecture

Go's implicit interface satisfaction makes dependency inversion effortless. In Java, you write `class PostgresRepo implements AccountRepository`. In Go, any struct that has the right method signatures automatically satisfies an interface -- no explicit declaration needed. This means:

1. The domain package defines `type AccountRepository interface { ... }`
2. The postgres package defines `type accountRepo struct { db *pgxpool.Pool }`
3. The postgres package implements the methods -- it never imports the domain interface definition (though it can for documentation clarity)
4. At wire-up time, the compiler verifies the match

This structural typing eliminates the coupling that plagues clean architecture in languages with nominal typing.

### Layer-by-Layer Mapping for pfin

#### Domain Layer (`internal/domain/`)

The innermost layer. Contains:
- **Entities**: Core business objects with identity (Account, JournalEntry, User, Household)
- **Value Objects**: Immutable types without identity (Money, AccountType, EntryStatus, Currency)
- **Domain Services**: Business logic that doesn't belong to a single entity (BalanceCalculator, EntryValidator)
- **Repository Interfaces**: Contracts that the domain expects (defined here, implemented elsewhere)
- **Domain Errors**: Business rule violations (ErrUnbalancedEntry, ErrInsufficientPermission)

```go
// internal/domain/account.go
package domain

import (
    "time"

    "github.com/google/uuid"
    "github.com/shopspring/decimal"
)

// AccountCategory represents the five fundamental account categories.
type AccountCategory string

const (
    AccountCategoryAsset     AccountCategory = "asset"
    AccountCategoryLiability AccountCategory = "liability"
    AccountCategoryEquity    AccountCategory = "equity"
    AccountCategoryIncome    AccountCategory = "income"
    AccountCategoryExpense   AccountCategory = "expense"
)

// NormalBalanceSign returns +1 for debit-normal accounts, -1 for credit-normal.
func (c AccountCategory) NormalBalanceSign() int {
    switch c {
    case AccountCategoryAsset, AccountCategoryExpense:
        return 1
    default:
        return -1
    }
}

// AccountType represents the specific subtype of an account.
type AccountType string

const (
    AccountTypeChecking   AccountType = "checking"
    AccountTypeSavings    AccountType = "savings"
    AccountTypeCreditCard AccountType = "credit_card"
    AccountTypeCash       AccountType = "cash"
    AccountTypeEWallet    AccountType = "e_wallet"
    AccountTypeLoan       AccountType = "loan"
    AccountTypeMortgage   AccountType = "mortgage"
    AccountTypeInvestment AccountType = "investment"
)

// Scope represents whether an entity is personal or household-scoped.
type Scope string

const (
    ScopePersonal  Scope = "personal"
    ScopeHousehold Scope = "household"
)

// Account is a node in the chart of accounts. Under the wallet-as-account
// model, a "wallet" is simply an account where category is asset or liability
// and is_visible is true.
type Account struct {
    ID              uuid.UUID
    Scope           Scope
    UserID          *uuid.UUID // set when Scope == personal
    HouseholdID     *uuid.UUID // set when Scope == household
    Name            string
    Category        AccountCategory
    AccountType     AccountType
    Currency        string
    IsVisible       bool       // visible as a "wallet" in the UI
    IsArchived      bool
    Icon            string
    Color           string
    DisplayOrder    int
    CreditLimit     *decimal.Decimal
    SharedToHousehold *uuid.UUID
    CreatedAt       time.Time
    UpdatedAt       time.Time
}

// Validate enforces domain invariants on the account.
func (a *Account) Validate() error {
    if a.Name == "" {
        return NewValidationError("name", "account name is required")
    }
    if a.Scope == ScopePersonal && a.UserID == nil {
        return NewValidationError("user_id", "personal account requires user_id")
    }
    if a.Scope == ScopeHousehold && a.HouseholdID == nil {
        return NewValidationError("household_id", "household account requires household_id")
    }
    if a.Scope == ScopePersonal && a.HouseholdID != nil {
        return NewValidationError("scope", "personal account cannot have household_id")
    }
    if a.Scope == ScopeHousehold && a.UserID != nil {
        return NewValidationError("scope", "household account cannot have user_id")
    }
    return nil
}

// IsWallet returns true if this account should be displayed as a wallet.
func (a *Account) IsWallet() bool {
    return a.IsVisible &&
        (a.Category == AccountCategoryAsset || a.Category == AccountCategoryLiability)
}
```

```go
// internal/domain/journal.go
package domain

import (
    "time"

    "github.com/google/uuid"
    "github.com/shopspring/decimal"
)

// EntryStatus represents the lifecycle of a journal entry.
type EntryStatus string

const (
    EntryStatusPending    EntryStatus = "pending"
    EntryStatusCleared    EntryStatus = "cleared"
    EntryStatusReconciled EntryStatus = "reconciled"
    EntryStatusVoided     EntryStatus = "voided"
)

// JournalEntry is the atomic unit of the double-entry ledger.
// It consists of a header and two or more lines that must sum to zero.
type JournalEntry struct {
    ID          uuid.UUID
    Scope       Scope
    UserID      *uuid.UUID
    HouseholdID *uuid.UUID
    Date        time.Time
    Description string
    Reference   string
    Status      EntryStatus
    VoidedBy    *uuid.UUID
    CreatedBy   uuid.UUID
    CreatedAt   time.Time
    Lines       []JournalLine
}

// JournalLine is a single posting within a journal entry.
type JournalLine struct {
    ID              uuid.UUID
    EntryID         uuid.UUID
    AccountID       uuid.UUID
    Amount          decimal.Decimal // positive = debit, negative = credit
    Currency        string
    ForeignAmount   *decimal.Decimal
    ForeignCurrency *string
    Description     string
    CategoryID      *uuid.UUID
    CreatedAt       time.Time
}

// Validate enforces the fundamental double-entry invariants.
func (je *JournalEntry) Validate() error {
    if len(je.Lines) < 2 {
        return ErrTooFewLines
    }
    if je.Description == "" {
        return NewValidationError("description", "description is required")
    }

    sum := decimal.Zero
    for _, line := range je.Lines {
        if line.Amount.IsZero() {
            return ErrZeroAmount
        }
        sum = sum.Add(line.Amount)
    }

    if !sum.IsZero() {
        return ErrUnbalancedEntry
    }

    return nil
}
```

```go
// internal/domain/repository.go
package domain

import (
    "context"
    "time"

    "github.com/google/uuid"
    "github.com/shopspring/decimal"
)

// AccountRepository defines the contract for account persistence.
// Defined in the domain layer, implemented in infrastructure.
type AccountRepository interface {
    Create(ctx context.Context, account *Account) error
    GetByID(ctx context.Context, id uuid.UUID) (*Account, error)
    List(ctx context.Context, filter AccountFilter) ([]Account, error)
    Update(ctx context.Context, account *Account) error
    Archive(ctx context.Context, id uuid.UUID) error
    GetBalance(ctx context.Context, accountID uuid.UUID, asOf time.Time) (decimal.Decimal, error)
}

// JournalRepository manages journal entries.
type JournalRepository interface {
    CreateEntry(ctx context.Context, entry *JournalEntry) error
    VoidEntry(ctx context.Context, entryID uuid.UUID, reason string) (*JournalEntry, error)
    GetEntryByID(ctx context.Context, id uuid.UUID) (*JournalEntry, error)
    ListEntries(ctx context.Context, filter EntryFilter) ([]JournalEntry, error)
}

// LedgerReader provides read-model queries for reporting.
type LedgerReader interface {
    AccountLedger(ctx context.Context, accountID uuid.UUID, filter LedgerFilter) ([]LedgerRow, error)
    TrialBalance(ctx context.Context, asOf time.Time) ([]TrialBalanceRow, error)
    BalanceSheet(ctx context.Context, asOf time.Time) (*BalanceSheet, error)
    IncomeStatement(ctx context.Context, from, to time.Time) (*IncomeStatement, error)
}

// UserRepository manages user persistence.
type UserRepository interface {
    Create(ctx context.Context, user *User) error
    GetByID(ctx context.Context, id uuid.UUID) (*User, error)
    GetByEmail(ctx context.Context, email string) (*User, error)
    Update(ctx context.Context, user *User) error
}

// HouseholdRepository manages household persistence.
type HouseholdRepository interface {
    Create(ctx context.Context, household *Household) error
    GetByID(ctx context.Context, id uuid.UUID) (*Household, error)
    ListForUser(ctx context.Context, userID uuid.UUID) ([]Household, error)
    Update(ctx context.Context, household *Household) error
    Delete(ctx context.Context, id uuid.UUID) error
    AddMember(ctx context.Context, member *HouseholdMember) error
    GetMember(ctx context.Context, householdID, userID uuid.UUID) (*HouseholdMember, error)
    ListMembers(ctx context.Context, householdID uuid.UUID) ([]HouseholdMember, error)
    UpdateMember(ctx context.Context, member *HouseholdMember) error
    RemoveMember(ctx context.Context, householdID, userID uuid.UUID) error
}

// AccountFilter holds query parameters for listing accounts.
type AccountFilter struct {
    Scope       *Scope
    UserID      *uuid.UUID
    HouseholdID *uuid.UUID
    Category    *AccountCategory
    IsArchived  *bool
    Limit       int
    Offset      int
}

// EntryFilter holds query parameters for listing journal entries.
type EntryFilter struct {
    Scope       *Scope
    UserID      *uuid.UUID
    HouseholdID *uuid.UUID
    AccountID   *uuid.UUID
    Status      *EntryStatus
    DateFrom    *time.Time
    DateTo      *time.Time
    Limit       int
    Offset      int
}

// LedgerFilter holds query parameters for ledger views.
type LedgerFilter struct {
    DateFrom *time.Time
    DateTo   *time.Time
    Limit    int
    Offset   int
}
```

**Key principle**: These interfaces are the contracts. They mention only domain types (uuid.UUID, decimal.Decimal, domain entities). They never reference pgx, sql, HTTP, or any infrastructure type.

#### Application Layer (`internal/app/`)

Contains use cases that orchestrate domain logic. Each use case:
- Receives a command/query DTO
- Calls repository interfaces
- Enforces business rules via domain methods
- Returns result DTOs

```go
// internal/app/journal/service.go
package journal

import (
    "context"
    "fmt"

    "github.com/google/uuid"
    "pfin/internal/domain"
)

// Service orchestrates journal entry use cases.
type Service struct {
    journals domain.JournalRepository
    accounts domain.AccountRepository
    ledger   domain.LedgerReader
}

// NewService creates a journal service with its dependencies.
func NewService(
    journals domain.JournalRepository,
    accounts domain.AccountRepository,
    ledger domain.LedgerReader,
) *Service {
    return &Service{
        journals: journals,
        accounts: accounts,
        ledger:   ledger,
    }
}

// CreateEntryRequest is the input DTO for creating a journal entry.
type CreateEntryRequest struct {
    Date        string             `json:"date"`
    Description string             `json:"description"`
    Reference   string             `json:"reference,omitempty"`
    Lines       []CreateLineRequest `json:"lines"`
}

type CreateLineRequest struct {
    AccountID   uuid.UUID `json:"account_id"`
    Amount      string    `json:"amount"` // decimal string
    Currency    string    `json:"currency,omitempty"`
    Description string    `json:"description,omitempty"`
    CategoryID  *uuid.UUID `json:"category_id,omitempty"`
}

// CreateEntry validates and persists a new journal entry.
func (s *Service) CreateEntry(ctx context.Context, req CreateEntryRequest) (*domain.JournalEntry, error) {
    // 1. Parse and build domain entity
    entry, err := buildEntryFromRequest(ctx, req)
    if err != nil {
        return nil, fmt.Errorf("build entry: %w", err)
    }

    // 2. Validate all referenced accounts exist and are accessible
    for _, line := range entry.Lines {
        acct, err := s.accounts.GetByID(ctx, line.AccountID)
        if err != nil {
            return nil, fmt.Errorf("account %s: %w", line.AccountID, err)
        }
        if acct.IsArchived {
            return nil, domain.NewValidationError("account_id",
                fmt.Sprintf("account %s is archived", acct.Name))
        }
    }

    // 3. Domain validation (balance check, minimum lines, etc.)
    if err := entry.Validate(); err != nil {
        return nil, err
    }

    // 4. Persist
    if err := s.journals.CreateEntry(ctx, entry); err != nil {
        return nil, fmt.Errorf("persist entry: %w", err)
    }

    return entry, nil
}

// VoidEntry creates a reversing entry and marks the original as voided.
func (s *Service) VoidEntry(ctx context.Context, entryID uuid.UUID, reason string) (*domain.JournalEntry, error) {
    // 1. Load original
    original, err := s.journals.GetEntryByID(ctx, entryID)
    if err != nil {
        return nil, fmt.Errorf("get entry: %w", err)
    }

    // 2. Business rule: can't void an already-voided entry
    if original.Status == domain.EntryStatusVoided {
        return nil, domain.ErrAlreadyVoided
    }

    // 3. Delegate to repository (handles reversal + status update in one tx)
    reversal, err := s.journals.VoidEntry(ctx, entryID, reason)
    if err != nil {
        return nil, fmt.Errorf("void entry: %w", err)
    }

    return reversal, nil
}

// GetAccountLedger returns the ledger view for a single account.
func (s *Service) GetAccountLedger(ctx context.Context, accountID uuid.UUID, filter domain.LedgerFilter) ([]domain.LedgerRow, error) {
    // Verify account exists and is accessible
    if _, err := s.accounts.GetByID(ctx, accountID); err != nil {
        return nil, fmt.Errorf("account %s: %w", accountID, err)
    }

    return s.ledger.AccountLedger(ctx, accountID, filter)
}
```

```go
// internal/app/account/service.go
package account

import (
    "context"
    "fmt"

    "github.com/google/uuid"
    "pfin/internal/domain"
)

// Service orchestrates account use cases.
type Service struct {
    accounts domain.AccountRepository
}

func NewService(accounts domain.AccountRepository) *Service {
    return &Service{accounts: accounts}
}

// CreateAccountRequest is the input DTO.
type CreateAccountRequest struct {
    Name        string `json:"name"`
    Category    string `json:"category"`
    AccountType string `json:"account_type"`
    Currency    string `json:"currency"`
    Icon        string `json:"icon,omitempty"`
    Color       string `json:"color,omitempty"`
}

func (s *Service) CreateAccount(ctx context.Context, req CreateAccountRequest) (*domain.Account, error) {
    // Extract scope from context (set by middleware)
    scope := domain.ScopeFromContext(ctx)

    account := &domain.Account{
        ID:          uuid.New(),
        Scope:       scope.Scope,
        UserID:      scope.UserID,
        HouseholdID: scope.HouseholdID,
        Name:        req.Name,
        Category:    domain.AccountCategory(req.Category),
        AccountType: domain.AccountType(req.AccountType),
        Currency:    req.Currency,
        IsVisible:   true,
        Icon:        req.Icon,
        Color:       req.Color,
    }

    if err := account.Validate(); err != nil {
        return nil, err
    }

    if err := s.accounts.Create(ctx, account); err != nil {
        return nil, fmt.Errorf("create account: %w", err)
    }

    return account, nil
}
```

**Key principle**: Application services depend only on domain interfaces. They never import `pgx`, `net/http`, or any infrastructure package.

#### Infrastructure Layer (`internal/infra/`)

Implements the interfaces defined by the domain. This is where PostgreSQL, HTTP clients, email services, etc. live.

```go
// internal/infra/postgres/account_repo.go
package postgres

import (
    "context"
    "fmt"
    "time"

    "github.com/google/uuid"
    "github.com/jackc/pgx/v5/pgxpool"
    "github.com/shopspring/decimal"
    "pfin/internal/domain"
)

// accountRepo implements domain.AccountRepository using PostgreSQL.
type accountRepo struct {
    pool *pgxpool.Pool
}

// NewAccountRepo creates a new PostgreSQL-backed account repository.
func NewAccountRepo(pool *pgxpool.Pool) domain.AccountRepository {
    return &accountRepo{pool: pool}
}

func (r *accountRepo) Create(ctx context.Context, account *domain.Account) error {
    _, err := r.pool.Exec(ctx, `
        INSERT INTO accounts (
            id, scope, user_id, household_id, name, category, account_type,
            currency, is_visible, is_archived, icon, color, display_order,
            credit_limit, shared_to_household_id, created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17
        )`,
        account.ID, account.Scope, account.UserID, account.HouseholdID,
        account.Name, account.Category, account.AccountType, account.Currency,
        account.IsVisible, account.IsArchived, account.Icon, account.Color,
        account.DisplayOrder, account.CreditLimit, account.SharedToHousehold,
        time.Now(), time.Now(),
    )
    if err != nil {
        return fmt.Errorf("insert account: %w", err)
    }
    return nil
}

func (r *accountRepo) GetByID(ctx context.Context, id uuid.UUID) (*domain.Account, error) {
    row := r.pool.QueryRow(ctx, `
        SELECT id, scope, user_id, household_id, name, category, account_type,
               currency, is_visible, is_archived, icon, color, display_order,
               credit_limit, shared_to_household_id, created_at, updated_at
        FROM accounts
        WHERE id = $1 AND is_archived = false`,
        id,
    )

    var a domain.Account
    err := row.Scan(
        &a.ID, &a.Scope, &a.UserID, &a.HouseholdID, &a.Name,
        &a.Category, &a.AccountType, &a.Currency, &a.IsVisible,
        &a.IsArchived, &a.Icon, &a.Color, &a.DisplayOrder,
        &a.CreditLimit, &a.SharedToHousehold, &a.CreatedAt, &a.UpdatedAt,
    )
    if err != nil {
        return nil, fmt.Errorf("scan account: %w", err)
    }
    return &a, nil
}

func (r *accountRepo) GetBalance(ctx context.Context, accountID uuid.UUID, asOf time.Time) (decimal.Decimal, error) {
    var balance decimal.Decimal
    err := r.pool.QueryRow(ctx, `
        SELECT COALESCE(SUM(jl.amount), 0)
        FROM journal_lines jl
        JOIN journal_entries je ON je.id = jl.entry_id
        WHERE jl.account_id = $1
          AND je.date <= $2
          AND je.status != 'voided'`,
        accountID, asOf,
    ).Scan(&balance)
    if err != nil {
        return decimal.Zero, fmt.Errorf("query balance: %w", err)
    }
    return balance, nil
}

// ... List, Update, Archive follow the same pattern
```

```go
// internal/infra/postgres/journal_repo.go
package postgres

import (
    "context"
    "fmt"

    "github.com/google/uuid"
    "github.com/jackc/pgx/v5"
    "github.com/jackc/pgx/v5/pgxpool"
    "pfin/internal/domain"
)

type journalRepo struct {
    pool *pgxpool.Pool
}

func NewJournalRepo(pool *pgxpool.Pool) domain.JournalRepository {
    return &journalRepo{pool: pool}
}

func (r *journalRepo) CreateEntry(ctx context.Context, entry *domain.JournalEntry) error {
    tx, err := r.pool.Begin(ctx)
    if err != nil {
        return fmt.Errorf("begin tx: %w", err)
    }
    defer tx.Rollback(ctx)

    // Insert header
    _, err = tx.Exec(ctx, `
        INSERT INTO journal_entries (
            id, scope, user_id, household_id, date, description,
            reference, status, created_by, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
        entry.ID, entry.Scope, entry.UserID, entry.HouseholdID,
        entry.Date, entry.Description, entry.Reference, entry.Status,
        entry.CreatedBy, entry.CreatedAt,
    )
    if err != nil {
        return fmt.Errorf("insert entry: %w", err)
    }

    // Insert lines via batch for performance
    batch := &pgx.Batch{}
    for _, line := range entry.Lines {
        batch.Queue(`
            INSERT INTO journal_lines (
                id, entry_id, account_id, amount, currency,
                foreign_amount, foreign_currency, description, category_id, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
            line.ID, entry.ID, line.AccountID, line.Amount, line.Currency,
            line.ForeignAmount, line.ForeignCurrency, line.Description,
            line.CategoryID, line.CreatedAt,
        )
    }
    br := tx.SendBatch(ctx, batch)
    defer br.Close()

    for range entry.Lines {
        if _, err := br.Exec(); err != nil {
            return fmt.Errorf("insert line: %w", err)
        }
    }
    br.Close()

    // Defense-in-depth: verify balance in DB
    var sum string
    err = tx.QueryRow(ctx, `
        SELECT COALESCE(SUM(amount), 0)::TEXT FROM journal_lines WHERE entry_id = $1`,
        entry.ID,
    ).Scan(&sum)
    if err != nil {
        return fmt.Errorf("verify balance: %w", err)
    }
    if sum != "0" && sum != "0.0000" {
        return fmt.Errorf("entry unbalanced in DB: sum=%s", sum)
    }

    return tx.Commit(ctx)
}

func (r *journalRepo) VoidEntry(ctx context.Context, entryID uuid.UUID, reason string) (*domain.JournalEntry, error) {
    tx, err := r.pool.Begin(ctx)
    if err != nil {
        return nil, fmt.Errorf("begin tx: %w", err)
    }
    defer tx.Rollback(ctx)

    // Load original entry with lines
    original, err := r.getEntryWithLinesTx(ctx, tx, entryID)
    if err != nil {
        return nil, fmt.Errorf("load original: %w", err)
    }

    // Create reversal entry
    reversalID := uuid.New()
    _, err = tx.Exec(ctx, `
        INSERT INTO journal_entries (
            id, scope, user_id, household_id, date, description,
            reference, status, created_by, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())`,
        reversalID, original.Scope, original.UserID, original.HouseholdID,
        original.Date, "VOID: "+original.Description,
        fmt.Sprintf("VOID-OF-%s", entryID), domain.EntryStatusCleared,
        original.CreatedBy,
    )
    if err != nil {
        return nil, fmt.Errorf("insert reversal: %w", err)
    }

    // Create reversed lines (negate amounts)
    for _, line := range original.Lines {
        _, err = tx.Exec(ctx, `
            INSERT INTO journal_lines (
                id, entry_id, account_id, amount, currency, description, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, now())`,
            uuid.New(), reversalID, line.AccountID,
            line.Amount.Neg(), line.Currency, line.Description,
        )
        if err != nil {
            return nil, fmt.Errorf("insert reversal line: %w", err)
        }
    }

    // Mark original as voided
    _, err = tx.Exec(ctx, `
        UPDATE journal_entries SET status = 'voided', voided_by = $1 WHERE id = $2`,
        reversalID, entryID,
    )
    if err != nil {
        return nil, fmt.Errorf("mark voided: %w", err)
    }

    if err := tx.Commit(ctx); err != nil {
        return nil, fmt.Errorf("commit: %w", err)
    }

    // Return the reversal entry
    return r.GetEntryByID(ctx, reversalID)
}
```

#### Interface / Adapter Layer (`internal/api/`)

HTTP handlers that translate between HTTP and application services. They parse requests, call services, and format responses.

```go
// internal/api/handler/journal_handler.go
package handler

import (
    "encoding/json"
    "net/http"

    "github.com/go-chi/chi/v5"
    "github.com/google/uuid"
    "pfin/internal/app/journal"
    "pfin/internal/domain"
)

// JournalHandler handles HTTP requests for journal entries.
type JournalHandler struct {
    service *journal.Service
}

func NewJournalHandler(service *journal.Service) *JournalHandler {
    return &JournalHandler{service: service}
}

// Routes registers journal entry routes on the given router.
func (h *JournalHandler) Routes(r chi.Router) {
    r.Route("/journal-entries", func(r chi.Router) {
        r.Post("/", h.CreateEntry)
        r.Get("/", h.ListEntries)
        r.Get("/{id}", h.GetEntry)
        r.Post("/{id}/void", h.VoidEntry)
    })
}

func (h *JournalHandler) CreateEntry(w http.ResponseWriter, r *http.Request) {
    var req journal.CreateEntryRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        writeError(w, http.StatusBadRequest, "invalid request body", err)
        return
    }

    entry, err := h.service.CreateEntry(r.Context(), req)
    if err != nil {
        writeServiceError(w, err)
        return
    }

    writeJSON(w, http.StatusCreated, entry)
}

func (h *JournalHandler) VoidEntry(w http.ResponseWriter, r *http.Request) {
    id, err := uuid.Parse(chi.URLParam(r, "id"))
    if err != nil {
        writeError(w, http.StatusBadRequest, "invalid entry ID", err)
        return
    }

    var req struct {
        Reason string `json:"reason"`
    }
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        writeError(w, http.StatusBadRequest, "invalid request body", err)
        return
    }

    reversal, err := h.service.VoidEntry(r.Context(), id, req.Reason)
    if err != nil {
        writeServiceError(w, err)
        return
    }

    writeJSON(w, http.StatusOK, reversal)
}
```

### Import Rule Enforcement

The dependency rule manifests as a strict import policy:

| Package | CAN import | CANNOT import |
|---------|------------|---------------|
| `internal/domain` | stdlib, `shopspring/decimal`, `google/uuid` | `internal/app`, `internal/infra`, `internal/api` |
| `internal/app/*` | `internal/domain`, stdlib | `internal/infra`, `internal/api`, `pgx`, `net/http` |
| `internal/infra/*` | `internal/domain`, `pgx`, external libs | `internal/app`, `internal/api` |
| `internal/api/*` | `internal/app`, `internal/domain`, `chi`, `net/http` | `internal/infra`, `pgx` |
| `cmd/api` | everything (wiring only) | -- |

This can be enforced with `go-cleanarch` linter or `depguard` in golangci-lint.

---

## 2. Hexagonal Architecture (Ports & Adapters) in Go

### Conceptual Model

Hexagonal architecture (Alistair Cockburn, 2005) frames the application as a hexagon with ports (interfaces) on its edges and adapters (implementations) plugged in from outside.

```
                    ┌─── HTTP Adapter ───┐
                    │   (chi handler)    │
                    └────────┬───────────┘
                             │
                     ┌───────▼────────┐
           ┌─────── │  Primary Port   │ ◄── driving side
           │        │  (Service IF)   │     (things that USE our app)
           │        └───────┬─────────┘
           │                │
           │    ┌───────────▼───────────┐
           │    │     Application       │
           │    │     Core / Domain     │
           │    └───────────┬───────────┘
           │                │
           │        ┌───────▼─────────┐
           └─────── │ Secondary Port  │ ──► driven side
                    │  (Repo IF)      │     (things our app USES)
                    └───────┬─────────┘
                            │
                    ┌───────▼───────────┐
                    │ PostgreSQL Adapter │
                    │   (pgx repo)      │
                    └───────────────────┘
```

### Mapping to Go Packages

| Hexagonal Concept | Go Implementation | pfin Package |
|-------------------|-------------------|-------------|
| **Domain / Core** | Entities, value objects, domain logic | `internal/domain/` |
| **Primary Port** | Interface that external actors call into | `internal/app/journal.Service` (the struct's public methods) |
| **Primary Adapter** | Translates external protocol to service calls | `internal/api/handler/` (HTTP), future `internal/api/grpc/` |
| **Secondary Port** | Interface the domain needs from the outside | `internal/domain/AccountRepository` (interface) |
| **Secondary Adapter** | Implements the port for a specific technology | `internal/infra/postgres/account_repo.go` |

### Primary Ports (Driving Adapters)

These are the entry points into the application. For pfin:

```
HTTP handlers (chi router)          → calls app services
CLI commands (cobra)                → calls app services
Background workers (cron/queue)     → calls app services
gRPC server (future)                → calls app services
```

Each primary adapter translates from its protocol to the application service API:

```go
// Primary adapter: HTTP
func (h *JournalHandler) CreateEntry(w http.ResponseWriter, r *http.Request) {
    var req journal.CreateEntryRequest
    json.NewDecoder(r.Body).Decode(&req)
    entry, err := h.service.CreateEntry(r.Context(), req) // <-- calls primary port
    writeJSON(w, http.StatusCreated, entry)
}

// Primary adapter: CLI (hypothetical)
func createEntryCmd(service *journal.Service) *cobra.Command {
    return &cobra.Command{
        Use: "create-entry",
        RunE: func(cmd *cobra.Command, args []string) error {
            req := journal.CreateEntryRequest{ /* from flags */ }
            entry, err := service.CreateEntry(context.Background(), req) // same port
            fmt.Println(entry)
            return err
        },
    }
}
```

### Secondary Ports (Driven Adapters)

These are things the application depends on. The domain defines the interface; infrastructure implements it:

```
domain.AccountRepository (port)     ← postgres.accountRepo (adapter)
domain.JournalRepository (port)     ← postgres.journalRepo (adapter)
domain.UserRepository (port)        ← postgres.userRepo (adapter)
domain.EmailSender (port)           ← sendgrid.emailSender (adapter)
domain.TokenGenerator (port)        ← jwt.tokenGenerator (adapter)
```

The beauty: to switch from PostgreSQL to MySQL, you write a new adapter. The domain and application layers do not change.

### Practical Difference from Clean Architecture

In practice, hexagonal architecture and clean architecture converge in Go. The key conceptual difference:

- **Clean architecture** thinks in concentric layers (inner/outer)
- **Hexagonal** thinks in symmetric ports (driving/driven)

For pfin, we use **clean architecture terminology** (domain/app/infra/api layers) with **hexagonal thinking** (ports and adapters). This is the pragmatic consensus in the Go community.

---

## 3. Modular Monolith Pattern

### Why Start as a Monolith

Microservices are premature optimization for a greenfield project. The modular monolith provides:

1. **Single deployable**: One binary, one database, one deployment pipeline
2. **Simple local development**: `go run cmd/api/main.go`
3. **No network boundaries**: Service-to-service calls are function calls (nanoseconds vs milliseconds)
4. **Shared transaction guarantees**: Cross-module operations can use database transactions
5. **Refactor freely**: Move code between modules without API versioning
6. **Extract later**: If a module needs independent scaling, the clean boundaries make extraction straightforward

The key insight: **a modular monolith with clean boundaries is easier to split into microservices than a poorly-structured monolith**. You get the deployment simplicity of a monolith with the organizational benefits of service boundaries.

### Module = Bounded Context

Each module maps to a domain bounded context. For pfin:

```
internal/
├── domain/          # Shared domain types (cross-cutting: Scope, Money, etc.)
├── modules/
│   ├── auth/        # Authentication & user management
│   │   ├── domain/  # User, Token, Session entities
│   │   ├── app/     # AuthService, UserService
│   │   ├── infra/   # postgres repo, bcrypt hasher, JWT generator
│   │   └── api/     # HTTP handlers for /auth/*, /users/*
│   │
│   ├── household/   # Household & membership management
│   │   ├── domain/  # Household, Member, Invitation entities
│   │   ├── app/     # HouseholdService, InvitationService
│   │   ├── infra/   # postgres repo, email sender
│   │   └── api/     # HTTP handlers for /households/*
│   │
│   ├── ledger/      # Chart of accounts + double-entry ledger
│   │   ├── domain/  # Account, JournalEntry, JournalLine
│   │   ├── app/     # AccountService, JournalService, LedgerService
│   │   ├── infra/   # postgres repo
│   │   └── api/     # HTTP handlers for /accounts/*, /journal-entries/*, /transactions/*
│   │
│   ├── budget/      # Budget management (future)
│   │   ├── domain/
│   │   ├── app/
│   │   ├── infra/
│   │   └── api/
│   │
│   └── reporting/   # Reports & analytics (future)
│       ├── domain/
│       ├── app/
│       ├── infra/
│       └── api/
```

### Module Boundaries and Encapsulation

Each module exposes a **public API** (its app service) and hides everything else. The rules:

1. **Modules communicate through application services, not repositories.** The `ledger` module never queries the `auth` module's database tables directly.

2. **Shared types live in `internal/domain/`.** Types that cross module boundaries (Scope, UserID, HouseholdID) are defined in the shared domain package.

3. **No circular dependencies between modules.** If `ledger` needs user info, it depends on an interface that `auth` satisfies, not on `auth` directly.

```go
// internal/modules/ledger/app/service.go
package app

// UserResolver is the interface the ledger module needs from auth.
// Defined by the consuming module, satisfied by the providing module.
type UserResolver interface {
    GetUserDisplayName(ctx context.Context, userID uuid.UUID) (string, error)
}

type LedgerService struct {
    journals    domain.JournalRepository
    accounts    domain.AccountRepository
    users       UserResolver  // dependency on auth module, via interface
}
```

```go
// Wired in cmd/api/main.go:
authService := auth.NewService(...)
ledgerService := ledger.NewService(
    journalRepo,
    accountRepo,
    authService,  // authService satisfies ledger.UserResolver
)
```

### Inter-Module Communication Patterns

| Pattern | When to Use | Example |
|---------|-------------|---------|
| **Direct function call** | Synchronous, within same request | Ledger checks account ownership via auth service |
| **Domain events (in-process)** | Async notification, loose coupling | "JournalEntryCreated" triggers balance refresh |
| **Shared database** | OK for read models and reporting | Reporting module reads ledger tables directly (via read-only interface) |
| **Event bus (future)** | When splitting into services | Replace in-process events with message queue |

For pfin v1, use **direct function calls** for synchronous needs and **in-process domain events** for notifications:

```go
// internal/domain/events.go
package domain

type Event interface {
    EventName() string
}

type JournalEntryCreated struct {
    EntryID     uuid.UUID
    HouseholdID *uuid.UUID
    UserID      *uuid.UUID
}

func (e JournalEntryCreated) EventName() string { return "journal.entry.created" }

// EventBus dispatches domain events to subscribers.
type EventBus interface {
    Publish(ctx context.Context, event Event) error
    Subscribe(eventName string, handler EventHandler) error
}

type EventHandler func(ctx context.Context, event Event) error
```

```go
// internal/infra/eventbus/memory.go
package eventbus

import (
    "context"
    "pfin/internal/domain"
    "sync"
)

// InMemory is a simple in-process event bus.
// Replace with NATS/RabbitMQ/Kafka when splitting into services.
type InMemory struct {
    mu       sync.RWMutex
    handlers map[string][]domain.EventHandler
}

func New() *InMemory {
    return &InMemory{
        handlers: make(map[string][]domain.EventHandler),
    }
}

func (b *InMemory) Publish(ctx context.Context, event domain.Event) error {
    b.mu.RLock()
    defer b.mu.RUnlock()

    for _, handler := range b.handlers[event.EventName()] {
        // In-process: run synchronously. For async, spawn goroutines.
        if err := handler(ctx, event); err != nil {
            return err // or log and continue, depending on semantics
        }
    }
    return nil
}

func (b *InMemory) Subscribe(eventName string, handler domain.EventHandler) error {
    b.mu.Lock()
    defer b.mu.Unlock()
    b.handlers[eventName] = append(b.handlers[eventName], handler)
    return nil
}
```

### Extracting to Microservices (Future Path)

When a module needs to be extracted:

1. The module already has clean boundaries (its own domain, app, infra, api)
2. Replace direct function calls with HTTP/gRPC calls
3. Replace in-process events with message queue
4. Give it its own database (if needed)
5. Deploy separately

The modular monolith structure means this extraction is a **deployment concern**, not an **architecture rewrite**.

---

## 4. Dependency Injection in Go

### The Go Way: Constructor Injection

Go does not need a DI framework. Constructor injection with explicit wiring is the idiomatic approach. Every struct receives its dependencies through its constructor:

```go
// Constructor pattern: explicit, testable, no magic
func NewJournalService(
    journals domain.JournalRepository,
    accounts domain.AccountRepository,
    ledger   domain.LedgerReader,
    events   domain.EventBus,
) *JournalService {
    return &JournalService{
        journals: journals,
        accounts: accounts,
        ledger:   ledger,
        events:   events,
    }
}
```

Benefits:
- **Compile-time safety**: Missing dependencies cause compile errors
- **Explicit dependencies**: Reading the constructor tells you everything the service needs
- **Easy testing**: Pass mocks directly
- **No reflection magic**: No runtime surprises
- **IDE-friendly**: Go to definition works perfectly

### DI Framework Comparison

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| **Manual wiring** | Zero magic, full control, compile-time safe | Verbose for large apps (50+ constructors) | **Recommended for pfin** |
| **google/wire** | Compile-time code generation, type-safe | Learning curve, generated code in repo | Good for large apps |
| **uber-go/fx** | Runtime DI, lifecycle management, module system | Reflection-based, errors at runtime, harder to debug | Overkill for most Go apps |
| **samber/do** | Lightweight, generics-based | Less mature | Worth watching |

**Recommendation for pfin**: Start with manual wiring. The app will have ~10-15 services at v1 scale. If it grows past 30-40 services, consider `google/wire` for code generation.

### The Wire-Up File: `cmd/api/main.go`

This is the **composition root** -- the only place that knows about all concrete implementations. It creates everything and wires dependencies together:

```go
// cmd/api/main.go
package main

import (
    "context"
    "fmt"
    "log/slog"
    "net/http"
    "os"
    "os/signal"
    "syscall"
    "time"

    "github.com/jackc/pgx/v5/pgxpool"
    "pfin/internal/api/handler"
    "pfin/internal/api/middleware"
    "pfin/internal/api/router"
    appaccount "pfin/internal/app/account"
    appauth "pfin/internal/app/auth"
    appjournal "pfin/internal/app/journal"
    apphousehold "pfin/internal/app/household"
    "pfin/internal/config"
    "pfin/internal/infra/eventbus"
    "pfin/internal/infra/postgres"
    "pfin/internal/infra/token"
)

func main() {
    if err := run(); err != nil {
        slog.Error("application failed", "error", err)
        os.Exit(1)
    }
}

func run() error {
    // 1. Load configuration
    cfg, err := config.Load()
    if err != nil {
        return fmt.Errorf("load config: %w", err)
    }

    // 2. Set up structured logging
    logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
        Level: cfg.LogLevel,
    }))
    slog.SetDefault(logger)

    // 3. Connect to PostgreSQL
    pool, err := pgxpool.New(context.Background(), cfg.DatabaseURL)
    if err != nil {
        return fmt.Errorf("connect db: %w", err)
    }
    defer pool.Close()

    if err := pool.Ping(context.Background()); err != nil {
        return fmt.Errorf("ping db: %w", err)
    }
    slog.Info("connected to database")

    // 4. Create infrastructure (secondary adapters)
    userRepo := postgres.NewUserRepo(pool)
    householdRepo := postgres.NewHouseholdRepo(pool)
    accountRepo := postgres.NewAccountRepo(pool)
    journalRepo := postgres.NewJournalRepo(pool)
    ledgerReader := postgres.NewLedgerReader(pool)
    tokenGen := token.NewJWTGenerator(cfg.JWTSecret, cfg.JWTExpiry)
    bus := eventbus.New()

    // 5. Create application services
    authService := appauth.NewService(userRepo, tokenGen, cfg.BcryptCost)
    householdService := apphousehold.NewService(householdRepo, userRepo)
    accountService := appaccount.NewService(accountRepo)
    journalService := appjournal.NewService(journalRepo, accountRepo, ledgerReader)

    // 6. Register event handlers
    bus.Subscribe("journal.entry.created", func(ctx context.Context, event domain.Event) error {
        // Refresh materialized views, send notifications, etc.
        slog.Info("journal entry created", "event", event)
        return nil
    })

    // 7. Create HTTP handlers (primary adapters)
    authHandler := handler.NewAuthHandler(authService)
    householdHandler := handler.NewHouseholdHandler(householdService)
    accountHandler := handler.NewAccountHandler(accountService)
    journalHandler := handler.NewJournalHandler(journalService)

    // 8. Build middleware stack
    mw := middleware.New(cfg, authService)

    // 9. Build router
    r := router.New(
        mw,
        authHandler,
        householdHandler,
        accountHandler,
        journalHandler,
    )

    // 10. Start server with graceful shutdown
    srv := &http.Server{
        Addr:         cfg.ListenAddr,
        Handler:      r,
        ReadTimeout:  15 * time.Second,
        WriteTimeout: 15 * time.Second,
        IdleTimeout:  60 * time.Second,
    }

    // Graceful shutdown
    done := make(chan os.Signal, 1)
    signal.Notify(done, os.Interrupt, syscall.SIGTERM)

    go func() {
        slog.Info("server starting", "addr", cfg.ListenAddr)
        if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
            slog.Error("server error", "error", err)
        }
    }()

    <-done
    slog.Info("shutting down gracefully")

    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    return srv.Shutdown(ctx)
}
```

### The Wiring Flow

```
Configuration
    │
    ▼
Database Pool (pgxpool.Pool)
    │
    ├──► Repositories (implement domain interfaces)
    │        │
    │        ▼
    ├──► Application Services (receive repos via constructors)
    │        │
    │        ▼
    ├──► HTTP Handlers (receive services via constructors)
    │        │
    │        ▼
    └──► Router (receives handlers + middleware)
             │
             ▼
         HTTP Server
```

Every arrow is a constructor call. Every dependency is explicit. There is no hidden state, no service locator, no global variables.

---

## 5. Error Handling Patterns

### Error Classification

pfin needs three categories of errors:

| Category | Origin | Example | HTTP Status |
|----------|--------|---------|-------------|
| **Domain errors** | Business rule violations | Unbalanced entry, archived account | 400, 409, 422 |
| **Not found errors** | Entity lookup failures | Account not found | 404 |
| **Infrastructure errors** | System failures | DB connection lost, timeout | 500 |
| **Authorization errors** | Permission violations | Not a household member | 403 |
| **Validation errors** | Input validation | Missing required field | 400 |

### Domain Error Types

```go
// internal/domain/errors.go
package domain

import "fmt"

// ErrorCode is a machine-readable error code for API consumers.
type ErrorCode string

const (
    ErrCodeValidation     ErrorCode = "VALIDATION_ERROR"
    ErrCodeNotFound       ErrorCode = "NOT_FOUND"
    ErrCodeConflict       ErrorCode = "CONFLICT"
    ErrCodeForbidden      ErrorCode = "FORBIDDEN"
    ErrCodeUnauthorized   ErrorCode = "UNAUTHORIZED"
    ErrCodeInternal       ErrorCode = "INTERNAL_ERROR"
    ErrCodeUnbalanced     ErrorCode = "UNBALANCED_ENTRY"
    ErrCodeAlreadyVoided  ErrorCode = "ALREADY_VOIDED"
    ErrCodeAccountArchived ErrorCode = "ACCOUNT_ARCHIVED"
)

// DomainError represents a business rule violation.
type DomainError struct {
    Code    ErrorCode `json:"code"`
    Message string    `json:"message"`
    Field   string    `json:"field,omitempty"` // for validation errors
}

func (e *DomainError) Error() string {
    if e.Field != "" {
        return fmt.Sprintf("%s: %s (%s)", e.Code, e.Message, e.Field)
    }
    return fmt.Sprintf("%s: %s", e.Code, e.Message)
}

// Sentinel-style constructors for common domain errors
var (
    ErrUnbalancedEntry = &DomainError{Code: ErrCodeUnbalanced, Message: "journal entry lines do not sum to zero"}
    ErrTooFewLines     = &DomainError{Code: ErrCodeValidation, Message: "journal entry must have at least 2 lines"}
    ErrZeroAmount      = &DomainError{Code: ErrCodeValidation, Message: "journal line amount cannot be zero"}
    ErrAlreadyVoided   = &DomainError{Code: ErrCodeAlreadyVoided, Message: "entry is already voided"}
)

// NewValidationError creates a field-level validation error.
func NewValidationError(field, message string) *DomainError {
    return &DomainError{
        Code:    ErrCodeValidation,
        Message: message,
        Field:   field,
    }
}

// NewNotFoundError creates a not-found error for an entity.
func NewNotFoundError(entity string, id interface{}) *DomainError {
    return &DomainError{
        Code:    ErrCodeNotFound,
        Message: fmt.Sprintf("%s not found: %v", entity, id),
    }
}

// NewForbiddenError creates a permission violation error.
func NewForbiddenError(message string) *DomainError {
    return &DomainError{
        Code:    ErrCodeForbidden,
        Message: message,
    }
}

// NewConflictError creates a conflict error (duplicate, state violation).
func NewConflictError(message string) *DomainError {
    return &DomainError{
        Code:    ErrCodeConflict,
        Message: message,
    }
}
```

### Error Wrapping in Application and Infrastructure Layers

```go
// Infrastructure layer: wrap with context, preserve original
func (r *accountRepo) GetByID(ctx context.Context, id uuid.UUID) (*domain.Account, error) {
    // ...
    if err != nil {
        if errors.Is(err, pgx.ErrNoRows) {
            return nil, domain.NewNotFoundError("account", id)
        }
        return nil, fmt.Errorf("query account %s: %w", id, err)
    }
    return &account, nil
}

// Application layer: wrap to add business context
func (s *Service) CreateEntry(ctx context.Context, req CreateEntryRequest) (*domain.JournalEntry, error) {
    // ...
    if err := s.journals.CreateEntry(ctx, entry); err != nil {
        return nil, fmt.Errorf("persist journal entry: %w", err)
    }
    return entry, nil
}
```

### Mapping Domain Errors to HTTP Responses

```go
// internal/api/handler/errors.go
package handler

import (
    "encoding/json"
    "errors"
    "log/slog"
    "net/http"

    "pfin/internal/domain"
)

// APIError is the standard error response format.
type APIError struct {
    Code    string `json:"code"`
    Message string `json:"message"`
    Field   string `json:"field,omitempty"`
}

// writeServiceError maps domain/application errors to HTTP responses.
func writeServiceError(w http.ResponseWriter, err error) {
    var domainErr *domain.DomainError
    if errors.As(err, &domainErr) {
        status := domainErrorToHTTPStatus(domainErr.Code)
        writeJSON(w, status, APIError{
            Code:    string(domainErr.Code),
            Message: domainErr.Message,
            Field:   domainErr.Field,
        })
        return
    }

    // Unknown error -- log it, return generic 500
    slog.Error("unhandled error", "error", err)
    writeJSON(w, http.StatusInternalServerError, APIError{
        Code:    string(domain.ErrCodeInternal),
        Message: "an internal error occurred",
    })
}

func domainErrorToHTTPStatus(code domain.ErrorCode) int {
    switch code {
    case domain.ErrCodeValidation, domain.ErrCodeUnbalanced:
        return http.StatusUnprocessableEntity // 422
    case domain.ErrCodeNotFound:
        return http.StatusNotFound // 404
    case domain.ErrCodeConflict, domain.ErrCodeAlreadyVoided, domain.ErrCodeAccountArchived:
        return http.StatusConflict // 409
    case domain.ErrCodeForbidden:
        return http.StatusForbidden // 403
    case domain.ErrCodeUnauthorized:
        return http.StatusUnauthorized // 401
    default:
        return http.StatusInternalServerError // 500
    }
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, message string, err error) {
    slog.Debug("request error", "message", message, "error", err)
    writeJSON(w, status, APIError{
        Code:    "BAD_REQUEST",
        Message: message,
    })
}
```

### Error Wrapping Best Practices

```go
// DO: Wrap with context using fmt.Errorf + %w
return fmt.Errorf("create account for user %s: %w", userID, err)

// DO: Use errors.As to check for typed errors
var domainErr *domain.DomainError
if errors.As(err, &domainErr) {
    // handle domain error
}

// DO: Use errors.Is for sentinel comparisons
if errors.Is(err, pgx.ErrNoRows) {
    return domain.NewNotFoundError("account", id)
}

// DON'T: Return raw infrastructure errors to upper layers
// BAD: return err (leaks pgx error to handler)
// GOOD: return domain.NewNotFoundError("account", id)

// DON'T: Lose error context
// BAD: return fmt.Errorf("failed")
// GOOD: return fmt.Errorf("insert journal line %d: %w", i, err)

// DON'T: Use string comparison for errors
// BAD: if err.Error() == "not found" { ... }
// GOOD: if errors.As(err, &domain.DomainError{}) { ... }
```

---

## 6. Testing Patterns

### Testing Strategy by Layer

| Layer | Test Type | Dependencies | Speed |
|-------|-----------|-------------|-------|
| Domain | Unit tests | None (pure logic) | Fastest |
| Application | Unit tests with mocked repos | Mock interfaces | Fast |
| Infrastructure | Integration tests | Real PostgreSQL | Slower |
| API handlers | Integration tests | Real or mocked services | Medium |
| End-to-end | Full stack | Real DB + HTTP | Slowest |

### Domain Layer: Pure Unit Tests

Domain tests need zero external dependencies. They test business rules in isolation.

```go
// internal/domain/journal_test.go
package domain_test

import (
    "testing"

    "github.com/google/uuid"
    "github.com/shopspring/decimal"
    "pfin/internal/domain"
)

func TestJournalEntry_Validate(t *testing.T) {
    tests := []struct {
        name    string
        entry   domain.JournalEntry
        wantErr error
    }{
        {
            name: "valid balanced entry",
            entry: domain.JournalEntry{
                ID:          uuid.New(),
                Description: "Grocery shopping",
                Lines: []domain.JournalLine{
                    {AccountID: uuid.New(), Amount: decimal.NewFromFloat(85.50), Currency: "USD"},
                    {AccountID: uuid.New(), Amount: decimal.NewFromFloat(-85.50), Currency: "USD"},
                },
            },
            wantErr: nil,
        },
        {
            name: "valid three-leg entry (split)",
            entry: domain.JournalEntry{
                ID:          uuid.New(),
                Description: "Paycheck",
                Lines: []domain.JournalLine{
                    {AccountID: uuid.New(), Amount: decimal.NewFromFloat(3000), Currency: "USD"},
                    {AccountID: uuid.New(), Amount: decimal.NewFromFloat(600), Currency: "USD"},
                    {AccountID: uuid.New(), Amount: decimal.NewFromFloat(-3600), Currency: "USD"},
                },
            },
            wantErr: nil,
        },
        {
            name: "unbalanced entry",
            entry: domain.JournalEntry{
                ID:          uuid.New(),
                Description: "Bad entry",
                Lines: []domain.JournalLine{
                    {AccountID: uuid.New(), Amount: decimal.NewFromFloat(100), Currency: "USD"},
                    {AccountID: uuid.New(), Amount: decimal.NewFromFloat(-99), Currency: "USD"},
                },
            },
            wantErr: domain.ErrUnbalancedEntry,
        },
        {
            name: "too few lines",
            entry: domain.JournalEntry{
                ID:          uuid.New(),
                Description: "One leg",
                Lines: []domain.JournalLine{
                    {AccountID: uuid.New(), Amount: decimal.NewFromFloat(100), Currency: "USD"},
                },
            },
            wantErr: domain.ErrTooFewLines,
        },
        {
            name: "zero amount line",
            entry: domain.JournalEntry{
                ID:          uuid.New(),
                Description: "Zero line",
                Lines: []domain.JournalLine{
                    {AccountID: uuid.New(), Amount: decimal.Zero, Currency: "USD"},
                    {AccountID: uuid.New(), Amount: decimal.NewFromFloat(-100), Currency: "USD"},
                },
            },
            wantErr: domain.ErrZeroAmount,
        },
        {
            name: "missing description",
            entry: domain.JournalEntry{
                ID: uuid.New(),
                Lines: []domain.JournalLine{
                    {AccountID: uuid.New(), Amount: decimal.NewFromFloat(100), Currency: "USD"},
                    {AccountID: uuid.New(), Amount: decimal.NewFromFloat(-100), Currency: "USD"},
                },
            },
            wantErr: &domain.DomainError{}, // will match via errors.As
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            err := tt.entry.Validate()
            if tt.wantErr == nil {
                if err != nil {
                    t.Errorf("expected no error, got: %v", err)
                }
                return
            }
            if err == nil {
                t.Errorf("expected error %v, got nil", tt.wantErr)
            }
        })
    }
}

func TestAccount_IsWallet(t *testing.T) {
    tests := []struct {
        name     string
        account  domain.Account
        expected bool
    }{
        {
            name: "visible asset is a wallet",
            account: domain.Account{
                Category:  domain.AccountCategoryAsset,
                IsVisible: true,
            },
            expected: true,
        },
        {
            name: "visible liability is a wallet",
            account: domain.Account{
                Category:  domain.AccountCategoryLiability,
                IsVisible: true,
            },
            expected: true,
        },
        {
            name: "expense account is not a wallet",
            account: domain.Account{
                Category:  domain.AccountCategoryExpense,
                IsVisible: true,
            },
            expected: false,
        },
        {
            name: "hidden asset is not a wallet",
            account: domain.Account{
                Category:  domain.AccountCategoryAsset,
                IsVisible: false,
            },
            expected: false,
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := tt.account.IsWallet()
            if got != tt.expected {
                t.Errorf("IsWallet() = %v, want %v", got, tt.expected)
            }
        })
    }
}
```

### Service Tests with Mocked Repositories

Use interfaces and mock implementations. No framework needed -- Go interfaces make this trivial.

```go
// internal/app/journal/service_test.go
package journal_test

import (
    "context"
    "testing"

    "github.com/google/uuid"
    "github.com/shopspring/decimal"
    "pfin/internal/app/journal"
    "pfin/internal/domain"
)

// mockJournalRepo is a test double for domain.JournalRepository.
type mockJournalRepo struct {
    createEntryFn func(ctx context.Context, entry *domain.JournalEntry) error
    getEntryFn    func(ctx context.Context, id uuid.UUID) (*domain.JournalEntry, error)
    entries       map[uuid.UUID]*domain.JournalEntry
}

func newMockJournalRepo() *mockJournalRepo {
    return &mockJournalRepo{
        entries: make(map[uuid.UUID]*domain.JournalEntry),
    }
}

func (m *mockJournalRepo) CreateEntry(ctx context.Context, entry *domain.JournalEntry) error {
    if m.createEntryFn != nil {
        return m.createEntryFn(ctx, entry)
    }
    m.entries[entry.ID] = entry
    return nil
}

func (m *mockJournalRepo) GetEntryByID(ctx context.Context, id uuid.UUID) (*domain.JournalEntry, error) {
    if m.getEntryFn != nil {
        return m.getEntryFn(ctx, id)
    }
    entry, ok := m.entries[id]
    if !ok {
        return nil, domain.NewNotFoundError("journal_entry", id)
    }
    return entry, nil
}

// ... other interface methods

// mockAccountRepo is a test double for domain.AccountRepository.
type mockAccountRepo struct {
    accounts map[uuid.UUID]*domain.Account
}

func newMockAccountRepo() *mockAccountRepo {
    return &mockAccountRepo{
        accounts: make(map[uuid.UUID]*domain.Account),
    }
}

func (m *mockAccountRepo) GetByID(ctx context.Context, id uuid.UUID) (*domain.Account, error) {
    acct, ok := m.accounts[id]
    if !ok {
        return nil, domain.NewNotFoundError("account", id)
    }
    return acct, nil
}

// ... other interface methods

func TestService_CreateEntry_Success(t *testing.T) {
    checkingID := uuid.New()
    groceriesID := uuid.New()

    accountRepo := newMockAccountRepo()
    accountRepo.accounts[checkingID] = &domain.Account{
        ID: checkingID, Name: "Checking", Category: domain.AccountCategoryAsset,
    }
    accountRepo.accounts[groceriesID] = &domain.Account{
        ID: groceriesID, Name: "Groceries", Category: domain.AccountCategoryExpense,
    }

    journalRepo := newMockJournalRepo()
    service := journal.NewService(journalRepo, accountRepo, nil)

    req := journal.CreateEntryRequest{
        Date:        "2026-03-15",
        Description: "Grocery shopping",
        Lines: []journal.CreateLineRequest{
            {AccountID: groceriesID, Amount: "85.50"},
            {AccountID: checkingID, Amount: "-85.50"},
        },
    }

    entry, err := service.CreateEntry(context.Background(), req)
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
    if entry == nil {
        t.Fatal("expected entry, got nil")
    }
    if len(journalRepo.entries) != 1 {
        t.Errorf("expected 1 entry in repo, got %d", len(journalRepo.entries))
    }
}

func TestService_CreateEntry_ArchivedAccount(t *testing.T) {
    archivedID := uuid.New()

    accountRepo := newMockAccountRepo()
    accountRepo.accounts[archivedID] = &domain.Account{
        ID: archivedID, Name: "Old Account", IsArchived: true,
    }

    journalRepo := newMockJournalRepo()
    service := journal.NewService(journalRepo, accountRepo, nil)

    req := journal.CreateEntryRequest{
        Date:        "2026-03-15",
        Description: "Bad entry",
        Lines: []journal.CreateLineRequest{
            {AccountID: archivedID, Amount: "100"},
            {AccountID: uuid.New(), Amount: "-100"},
        },
    }

    _, err := service.CreateEntry(context.Background(), req)
    if err == nil {
        t.Fatal("expected error for archived account")
    }
}
```

### Integration Tests with testcontainers-go

For repository tests, use a real PostgreSQL instance via testcontainers-go. This catches SQL bugs that mocks miss.

```go
// internal/infra/postgres/testutil_test.go
package postgres_test

import (
    "context"
    "fmt"
    "testing"
    "time"

    "github.com/jackc/pgx/v5/pgxpool"
    "github.com/testcontainers/testcontainers-go"
    "github.com/testcontainers/testcontainers-go/modules/postgres"
    "github.com/testcontainers/testcontainers-go/wait"
)

// setupTestDB creates a fresh PostgreSQL container for integration tests.
// It runs migrations and returns a connection pool. The container is
// automatically cleaned up when the test finishes.
func setupTestDB(t *testing.T) *pgxpool.Pool {
    t.Helper()
    ctx := context.Background()

    container, err := postgres.Run(ctx,
        "postgres:16-alpine",
        postgres.WithDatabase("pfin_test"),
        postgres.WithUsername("test"),
        postgres.WithPassword("test"),
        testcontainers.WithWaitStrategy(
            wait.ForLog("database system is ready to accept connections").
                WithOccurrence(2).
                WithStartupTimeout(30*time.Second),
        ),
    )
    if err != nil {
        t.Fatalf("start postgres container: %v", err)
    }

    t.Cleanup(func() {
        if err := container.Terminate(ctx); err != nil {
            t.Logf("terminate container: %v", err)
        }
    })

    connStr, err := container.ConnectionString(ctx, "sslmode=disable")
    if err != nil {
        t.Fatalf("get connection string: %v", err)
    }

    pool, err := pgxpool.New(ctx, connStr)
    if err != nil {
        t.Fatalf("connect to test db: %v", err)
    }

    t.Cleanup(func() {
        pool.Close()
    })

    // Run migrations
    if err := runMigrations(pool); err != nil {
        t.Fatalf("run migrations: %v", err)
    }

    return pool
}

func runMigrations(pool *pgxpool.Pool) error {
    // Use golang-migrate or embed SQL files directly.
    // For tests, embedding SQL is simpler:
    ctx := context.Background()
    _, err := pool.Exec(ctx, migrationSQL) // migrationSQL is a const or embedded file
    return err
}
```

```go
// internal/infra/postgres/account_repo_test.go
package postgres_test

import (
    "context"
    "testing"

    "github.com/google/uuid"
    infra "pfin/internal/infra/postgres"
    "pfin/internal/domain"
)

func TestAccountRepo_CreateAndGetByID(t *testing.T) {
    if testing.Short() {
        t.Skip("skipping integration test")
    }

    pool := setupTestDB(t)
    repo := infra.NewAccountRepo(pool)
    ctx := context.Background()

    userID := uuid.New()
    // Seed user first (accounts FK to users)
    seedUser(t, pool, userID)

    account := &domain.Account{
        ID:          uuid.New(),
        Scope:       domain.ScopePersonal,
        UserID:      &userID,
        Name:        "Test Checking",
        Category:    domain.AccountCategoryAsset,
        AccountType: domain.AccountTypeChecking,
        Currency:    "USD",
        IsVisible:   true,
    }

    // Create
    err := repo.Create(ctx, account)
    if err != nil {
        t.Fatalf("create account: %v", err)
    }

    // Get by ID
    got, err := repo.GetByID(ctx, account.ID)
    if err != nil {
        t.Fatalf("get account: %v", err)
    }

    if got.Name != account.Name {
        t.Errorf("name = %q, want %q", got.Name, account.Name)
    }
    if got.Category != account.Category {
        t.Errorf("category = %q, want %q", got.Category, account.Category)
    }
    if got.Currency != account.Currency {
        t.Errorf("currency = %q, want %q", got.Currency, account.Currency)
    }
}

func TestAccountRepo_GetByID_NotFound(t *testing.T) {
    if testing.Short() {
        t.Skip("skipping integration test")
    }

    pool := setupTestDB(t)
    repo := infra.NewAccountRepo(pool)

    _, err := repo.GetByID(context.Background(), uuid.New())
    if err == nil {
        t.Fatal("expected not found error")
    }

    var domainErr *domain.DomainError
    if !errors.As(err, &domainErr) {
        t.Fatalf("expected domain error, got: %T", err)
    }
    if domainErr.Code != domain.ErrCodeNotFound {
        t.Errorf("code = %q, want %q", domainErr.Code, domain.ErrCodeNotFound)
    }
}

func TestJournalRepo_CreateEntry_BalanceEnforced(t *testing.T) {
    if testing.Short() {
        t.Skip("skipping integration test")
    }

    pool := setupTestDB(t)
    repo := infra.NewJournalRepo(pool)
    ctx := context.Background()

    userID := uuid.New()
    seedUser(t, pool, userID)
    checkingID := seedAccount(t, pool, userID, "Checking", domain.AccountCategoryAsset)
    groceriesID := seedAccount(t, pool, userID, "Groceries", domain.AccountCategoryExpense)

    entry := &domain.JournalEntry{
        ID:          uuid.New(),
        Scope:       domain.ScopePersonal,
        UserID:      &userID,
        Date:        time.Now(),
        Description: "Test grocery purchase",
        Status:      domain.EntryStatusCleared,
        CreatedBy:   userID,
        Lines: []domain.JournalLine{
            {ID: uuid.New(), AccountID: groceriesID, Amount: decimal.NewFromFloat(85.50), Currency: "USD"},
            {ID: uuid.New(), AccountID: checkingID, Amount: decimal.NewFromFloat(-85.50), Currency: "USD"},
        },
    }

    err := repo.CreateEntry(ctx, entry)
    if err != nil {
        t.Fatalf("create balanced entry: %v", err)
    }

    // Verify it was persisted
    got, err := repo.GetEntryByID(ctx, entry.ID)
    if err != nil {
        t.Fatalf("get entry: %v", err)
    }
    if len(got.Lines) != 2 {
        t.Errorf("lines = %d, want 2", len(got.Lines))
    }
}
```

### Running Tests

```bash
# Unit tests only (fast)
go test ./internal/domain/... ./internal/app/...

# Integration tests (requires Docker)
go test ./internal/infra/... -count=1

# All tests
go test ./...

# Skip integration tests when Docker is not available
go test -short ./...

# With coverage
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out
```

### Test File Conventions

```
internal/domain/journal.go           # source
internal/domain/journal_test.go      # test (same package for unexported access)
internal/domain/journal_external_test.go  # test (domain_test package for public API)
internal/infra/postgres/account_repo.go
internal/infra/postgres/account_repo_test.go
internal/infra/postgres/testutil_test.go  # shared test helpers
```

---

## 7. Middleware and Cross-Cutting Concerns

### Middleware Chain Architecture

Using `go-chi/chi` (recommended for pfin), middleware forms a chain where each handler wraps the next:

```
Request
  │
  ▼
RequestID middleware
  │
  ▼
Structured Logger middleware
  │
  ▼
Recovery (panic handler)
  │
  ▼
CORS middleware
  │
  ▼
Rate Limiter middleware
  │
  ▼
Auth middleware (JWT validation)
  │
  ▼
Household Context middleware (X-Household-ID)
  │
  ▼
Permission middleware (role check)
  │
  ▼
Route Handler
  │
  ▼
Response
```

### Router Setup

```go
// internal/api/router/router.go
package router

import (
    "net/http"
    "time"

    "github.com/go-chi/chi/v5"
    chimw "github.com/go-chi/chi/v5/middleware"
    "github.com/go-chi/cors"
    "pfin/internal/api/handler"
    "pfin/internal/api/middleware"
)

func New(
    mw *middleware.Middleware,
    authHandler *handler.AuthHandler,
    householdHandler *handler.HouseholdHandler,
    accountHandler *handler.AccountHandler,
    journalHandler *handler.JournalHandler,
) http.Handler {
    r := chi.NewRouter()

    // Global middleware (applied to ALL requests)
    r.Use(chimw.RequestID)
    r.Use(chimw.RealIP)
    r.Use(mw.StructuredLogger)
    r.Use(chimw.Recoverer)
    r.Use(chimw.Timeout(30 * time.Second))

    // CORS
    r.Use(cors.Handler(cors.Options{
        AllowedOrigins:   []string{"http://localhost:3000", "https://pfin.app"},
        AllowedMethods:   []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
        AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-Household-ID"},
        ExposedHeaders:   []string{"Link", "X-Request-ID"},
        AllowCredentials: true,
        MaxAge:           300,
    }))

    // Health check (no auth)
    r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
        w.Write([]byte(`{"status":"ok"}`))
    })

    // Public routes (no auth required)
    r.Route("/api/v1", func(r chi.Router) {
        // Auth endpoints
        r.Post("/auth/register", authHandler.Register)
        r.Post("/auth/login", authHandler.Login)
        r.Post("/auth/refresh", authHandler.RefreshToken)
        r.Post("/auth/forgot-password", authHandler.ForgotPassword)
        r.Post("/auth/reset-password", authHandler.ResetPassword)

        // Invitation acceptance (token-based, no JWT needed)
        r.Post("/invitations/{token}/accept", householdHandler.AcceptInvitation)
        r.Post("/invitations/{token}/decline", householdHandler.DeclineInvitation)
    })

    // Protected routes (auth required)
    r.Route("/api/v1", func(r chi.Router) {
        r.Use(mw.Authenticate) // JWT validation

        // User profile
        r.Get("/me", authHandler.GetProfile)
        r.Patch("/me", authHandler.UpdateProfile)

        // Household management
        r.Route("/households", func(r chi.Router) {
            r.Post("/", householdHandler.Create)
            r.Get("/", householdHandler.List)

            r.Route("/{householdID}", func(r chi.Router) {
                r.Use(mw.HouseholdContext) // extracts household + validates membership
                r.Get("/", householdHandler.Get)
                r.Patch("/", householdHandler.Update)
                r.Delete("/", householdHandler.Delete)
                r.Post("/members/invite", householdHandler.InviteMember)
                r.Get("/members", householdHandler.ListMembers)
                r.Patch("/members/{memberID}", householdHandler.UpdateMember)
                r.Delete("/members/{memberID}", householdHandler.RemoveMember)
                r.Get("/audit-log", householdHandler.AuditLog)
            })
        })

        // Scoped resources (household context from X-Household-ID header)
        r.Route("/accounts", func(r chi.Router) {
            r.Use(mw.ScopeContext) // reads X-Household-ID, sets scope in context
            accountHandler.Routes(r)
        })

        r.Route("/journal-entries", func(r chi.Router) {
            r.Use(mw.ScopeContext)
            journalHandler.Routes(r)
        })

        r.Route("/transactions", func(r chi.Router) {
            r.Use(mw.ScopeContext)
            // Simplified transaction API (sugar over journal entries)
            r.Post("/", journalHandler.CreateSimpleTransaction)
            r.Get("/", journalHandler.ListTransactions)
        })

        r.Route("/wallets", func(r chi.Router) {
            r.Use(mw.ScopeContext)
            // Wallet API (convenience view over accounts where is_visible=true)
            r.Get("/", accountHandler.ListWallets)
        })
    })

    return r
}
```

### Authentication Middleware

```go
// internal/api/middleware/auth.go
package middleware

import (
    "context"
    "log/slog"
    "net/http"
    "strings"

    "pfin/internal/domain"
)

type contextKey string

const (
    userIDKey    contextKey = "user_id"
    scopeKey     contextKey = "scope"
)

// Authenticate validates the JWT token and injects user_id into context.
func (m *Middleware) Authenticate(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        authHeader := r.Header.Get("Authorization")
        if authHeader == "" {
            writeUnauthorized(w, "missing authorization header")
            return
        }

        parts := strings.SplitN(authHeader, " ", 2)
        if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") {
            writeUnauthorized(w, "invalid authorization header format")
            return
        }

        claims, err := m.tokenGenerator.ValidateAccessToken(parts[1])
        if err != nil {
            slog.Debug("invalid token", "error", err)
            writeUnauthorized(w, "invalid or expired token")
            return
        }

        ctx := context.WithValue(r.Context(), userIDKey, claims.UserID)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}

// UserIDFromContext extracts the authenticated user's ID from context.
func UserIDFromContext(ctx context.Context) uuid.UUID {
    id, _ := ctx.Value(userIDKey).(uuid.UUID)
    return id
}
```

### Household Context / Scope Middleware

```go
// internal/api/middleware/scope.go
package middleware

import (
    "context"
    "net/http"

    "github.com/google/uuid"
    "pfin/internal/domain"
)

// ScopeInfo carries the resolved scope for the current request.
type ScopeInfo struct {
    Scope       domain.Scope
    UserID      *uuid.UUID
    HouseholdID *uuid.UUID
    Role        *domain.HouseholdRole // nil for personal scope
}

// ScopeContext reads X-Household-ID header and resolves the request scope.
// If the header is missing or "personal", scope is personal (user-only).
// If it contains a UUID, scope is household (validates membership).
func (m *Middleware) ScopeContext(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        userID := UserIDFromContext(r.Context())
        householdHeader := r.Header.Get("X-Household-ID")

        if householdHeader == "" || householdHeader == "personal" {
            // Personal scope: user's own data
            scope := &ScopeInfo{
                Scope:  domain.ScopePersonal,
                UserID: &userID,
            }
            ctx := context.WithValue(r.Context(), scopeKey, scope)
            next.ServeHTTP(w, r.WithContext(ctx))
            return
        }

        // Household scope: validate membership
        householdID, err := uuid.Parse(householdHeader)
        if err != nil {
            writeError(w, http.StatusBadRequest, "invalid X-Household-ID header")
            return
        }

        member, err := m.householdRepo.GetMember(r.Context(), householdID, userID)
        if err != nil {
            writeError(w, http.StatusForbidden, "not a member of this household")
            return
        }

        scope := &ScopeInfo{
            Scope:       domain.ScopeHousehold,
            UserID:      &userID,
            HouseholdID: &householdID,
            Role:        &member.Role,
        }
        ctx := context.WithValue(r.Context(), scopeKey, scope)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}

// ScopeFromContext extracts scope info from context.
func ScopeFromContext(ctx context.Context) *ScopeInfo {
    scope, _ := ctx.Value(scopeKey).(*ScopeInfo)
    return scope
}
```

### Structured Request Logging

```go
// internal/api/middleware/logger.go
package middleware

import (
    "log/slog"
    "net/http"
    "time"

    chimw "github.com/go-chi/chi/v5/middleware"
)

// StructuredLogger logs each request with structured fields.
func (m *Middleware) StructuredLogger(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        ww := chimw.NewWrapResponseWriter(w, r.ProtoMajor)

        defer func() {
            slog.Info("http request",
                "method", r.Method,
                "path", r.URL.Path,
                "status", ww.Status(),
                "bytes", ww.BytesWritten(),
                "duration_ms", time.Since(start).Milliseconds(),
                "request_id", chimw.GetReqID(r.Context()),
                "remote_addr", r.RemoteAddr,
                "user_agent", r.UserAgent(),
            )
        }()

        next.ServeHTTP(ww, r)
    })
}
```

### Rate Limiting

```go
// internal/api/middleware/ratelimit.go
package middleware

import (
    "net/http"
    "sync"
    "time"

    "golang.org/x/time/rate"
)

// RateLimiter provides per-IP rate limiting.
type RateLimiter struct {
    mu       sync.Mutex
    limiters map[string]*rate.Limiter
    rate     rate.Limit
    burst    int
}

func NewRateLimiter(rps float64, burst int) *RateLimiter {
    return &RateLimiter{
        limiters: make(map[string]*rate.Limiter),
        rate:     rate.Limit(rps),
        burst:    burst,
    }
}

func (rl *RateLimiter) getLimiter(ip string) *rate.Limiter {
    rl.mu.Lock()
    defer rl.mu.Unlock()

    if limiter, exists := rl.limiters[ip]; exists {
        return limiter
    }

    limiter := rate.NewLimiter(rl.rate, rl.burst)
    rl.limiters[ip] = limiter
    return limiter
}

func (rl *RateLimiter) Middleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        limiter := rl.getLimiter(r.RemoteAddr)
        if !limiter.Allow() {
            http.Error(w, `{"code":"RATE_LIMIT_EXCEEDED","message":"too many requests"}`,
                http.StatusTooManyRequests)
            return
        }
        next.ServeHTTP(w, r)
    })
}
```

---

## 8. Concrete Project Structure for pfin

### Full Directory Layout

```
pfin/
├── cmd/
│   └── api/
│       └── main.go                    # Composition root, wires everything
│
├── internal/                           # Private application code
│   ├── config/
│   │   └── config.go                  # Configuration loading (env vars)
│   │
│   ├── domain/                        # Shared domain types
│   │   ├── account.go                 # Account entity, AccountCategory, AccountType
│   │   ├── account_test.go
│   │   ├── journal.go                 # JournalEntry, JournalLine, EntryStatus
│   │   ├── journal_test.go
│   │   ├── user.go                    # User entity
│   │   ├── household.go              # Household, HouseholdMember, HouseholdRole
│   │   ├── scope.go                   # Scope type, ScopeInfo
│   │   ├── money.go                   # Money value object (amount + currency)
│   │   ├── errors.go                  # DomainError, error codes, constructors
│   │   ├── events.go                  # Event interface, event types
│   │   └── repository.go             # All repository interfaces
│   │
│   ├── app/                           # Application services (use cases)
│   │   ├── auth/
│   │   │   ├── service.go            # Register, Login, RefreshToken, ResetPassword
│   │   │   └── service_test.go
│   │   ├── household/
│   │   │   ├── service.go            # Create, Invite, Accept, UpdateRole
│   │   │   └── service_test.go
│   │   ├── account/
│   │   │   ├── service.go            # CreateAccount, ListAccounts, ShareToHousehold
│   │   │   └── service_test.go
│   │   └── journal/
│   │       ├── service.go            # CreateEntry, VoidEntry, CreateSimpleTransaction
│   │       ├── service_test.go
│   │       └── mapper.go             # Converts simple transaction to journal entry
│   │
│   ├── infra/                         # Infrastructure implementations
│   │   ├── postgres/
│   │   │   ├── user_repo.go          # implements domain.UserRepository
│   │   │   ├── user_repo_test.go     # integration test
│   │   │   ├── household_repo.go     # implements domain.HouseholdRepository
│   │   │   ├── household_repo_test.go
│   │   │   ├── account_repo.go       # implements domain.AccountRepository
│   │   │   ├── account_repo_test.go
│   │   │   ├── journal_repo.go       # implements domain.JournalRepository
│   │   │   ├── journal_repo_test.go
│   │   │   ├── ledger_reader.go      # implements domain.LedgerReader
│   │   │   ├── ledger_reader_test.go
│   │   │   └── testutil_test.go      # shared test helpers (container setup)
│   │   ├── token/
│   │   │   ├── jwt.go                # JWT generation/validation
│   │   │   └── jwt_test.go
│   │   ├── hash/
│   │   │   └── bcrypt.go             # bcrypt password hashing
│   │   └── eventbus/
│   │       └── memory.go             # In-process event bus
│   │
│   └── api/                           # HTTP interface layer
│       ├── handler/
│       │   ├── auth_handler.go
│       │   ├── household_handler.go
│       │   ├── account_handler.go
│       │   ├── journal_handler.go
│       │   ├── errors.go             # Error response helpers
│       │   └── response.go           # JSON response helpers
│       ├── middleware/
│       │   ├── middleware.go          # Middleware struct with shared deps
│       │   ├── auth.go               # JWT authentication
│       │   ├── scope.go              # Household/personal scope resolution
│       │   ├── logger.go             # Structured request logging
│       │   ├── ratelimit.go          # Per-IP rate limiting
│       │   └── recovery.go           # Panic recovery
│       ├── router/
│       │   └── router.go             # Chi router setup, route registration
│       └── dto/
│           ├── request.go            # Shared request types
│           └── response.go           # Shared response types
│
├── migrations/                        # Database migration files
│   ├── 001_create_users.up.sql
│   ├── 001_create_users.down.sql
│   ├── 002_create_households.up.sql
│   ├── 002_create_households.down.sql
│   ├── 003_create_accounts.up.sql
│   ├── 003_create_accounts.down.sql
│   ├── 004_create_journal.up.sql
│   ├── 004_create_journal.down.sql
│   └── 005_create_categories.up.sql
│
├── docs/                              # Documentation
│   └── planning/                      # (existing planning docs)
│
├── go.mod
├── go.sum
├── Makefile                           # Build, test, migrate, lint commands
├── Dockerfile                         # Multi-stage build
├── docker-compose.yml                 # Local dev: postgres, api
├── .env.example                       # Example environment variables
├── .golangci.yml                      # Linter configuration
└── CLAUDE.md                          # Agent instructions
```

### Package Naming Conventions

| Convention | Rule | Example |
|-----------|------|---------|
| Package names | Singular, lowercase, short | `account`, `journal`, `postgres` |
| File names | `snake_case.go` | `account_repo.go`, `journal_test.go` |
| Interface names | No `I` prefix; named by what they do | `AccountRepository`, `EventBus` |
| Struct names | PascalCase, implementation detail | `accountRepo` (unexported), `Service` (exported) |
| Constructor functions | `New` + type name | `NewService`, `NewAccountRepo` |
| Test files | `*_test.go` next to source | `service_test.go` |

### Preventing Import Cycles

The most common cause of import cycles in Go is when two packages reference each other's types. Prevention strategies:

1. **Shared domain types**: Put types both packages need in `internal/domain/`
2. **Interface segregation**: The consumer defines the interface it needs, not the provider
3. **Direction of dependency**: Always point inward (infra -> app -> domain, never reverse)
4. **No cross-module imports**: Modules communicate through interfaces wired at the composition root

```
ALLOWED:
  internal/api/handler → internal/app/journal → internal/domain
  internal/infra/postgres → internal/domain

FORBIDDEN:
  internal/domain → internal/infra/postgres  (domain doesn't know about postgres)
  internal/app/journal → internal/api/handler (app doesn't know about HTTP)
  internal/app/account → internal/app/journal (cross-module direct import)
```

For cross-module communication, define an interface in the consuming module:

```go
// internal/app/journal/ports.go
package journal

// AccountReader is what the journal module needs from accounts.
// Defined here (consumer), satisfied by account.Service (provider).
type AccountReader interface {
    GetByID(ctx context.Context, id uuid.UUID) (*domain.Account, error)
}
```

### Configuration

```go
// internal/config/config.go
package config

import (
    "fmt"
    "log/slog"
    "os"
    "strconv"
    "time"
)

type Config struct {
    // Server
    ListenAddr string
    Env        string // "development", "staging", "production"

    // Database
    DatabaseURL string

    // Auth
    JWTSecret       string
    JWTAccessExpiry time.Duration
    JWTRefreshExpiry time.Duration
    BcryptCost      int

    // Rate Limiting
    RateLimitRPS   float64
    RateLimitBurst int

    // CORS
    AllowedOrigins []string

    // Logging
    LogLevel slog.Level
}

func Load() (*Config, error) {
    cfg := &Config{
        ListenAddr:       getEnv("LISTEN_ADDR", ":8080"),
        Env:              getEnv("APP_ENV", "development"),
        DatabaseURL:      requireEnv("DATABASE_URL"),
        JWTSecret:        requireEnv("JWT_SECRET"),
        JWTAccessExpiry:  getDuration("JWT_ACCESS_EXPIRY", 15*time.Minute),
        JWTRefreshExpiry: getDuration("JWT_REFRESH_EXPIRY", 7*24*time.Hour),
        BcryptCost:       getInt("BCRYPT_COST", 12),
        RateLimitRPS:     getFloat("RATE_LIMIT_RPS", 10),
        RateLimitBurst:   getInt("RATE_LIMIT_BURST", 20),
        LogLevel:         parseLogLevel(getEnv("LOG_LEVEL", "info")),
    }
    return cfg, nil
}

func getEnv(key, fallback string) string {
    if v := os.Getenv(key); v != "" {
        return v
    }
    return fallback
}

func requireEnv(key string) string {
    v := os.Getenv(key)
    if v == "" {
        panic(fmt.Sprintf("required environment variable %s is not set", key))
    }
    return v
}
```

### Makefile

```makefile
.PHONY: build test lint migrate run

# Build the API binary
build:
	go build -o bin/api ./cmd/api

# Run all tests
test:
	go test ./...

# Run unit tests only (no Docker required)
test-unit:
	go test -short ./...

# Run integration tests only
test-integration:
	go test -run Integration ./internal/infra/...

# Run with race detector
test-race:
	go test -race ./...

# Coverage report
test-coverage:
	go test -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out -o coverage.html

# Lint
lint:
	golangci-lint run

# Run locally
run:
	go run ./cmd/api

# Database migrations
migrate-up:
	migrate -path migrations -database "$$DATABASE_URL" up

migrate-down:
	migrate -path migrations -database "$$DATABASE_URL" down 1

migrate-create:
	migrate create -ext sql -dir migrations -seq $(name)

# Docker
docker-build:
	docker build -t pfin-api .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down
```

---

## 9. Real-World Go Architecture References

### Production-Grade Template Projects

| Project | Description | Key Patterns |
|---------|-------------|-------------|
| **evrone/go-clean-template** | Clean architecture template for Go | 4-layer structure (entity/usecase/controller/repo), gin router, PostgreSQL, dependency injection via constructors |
| **bxcodec/go-clean-arch** | Another popular clean arch template | Domain-driven layers, interface-based repos, chi router |
| **golang-standards/project-layout** | Standard Go project layout guide | `cmd/`, `internal/`, `pkg/` conventions |
| **ardanlabs/service** | Bill Kennedy's production service template | Business/foundation/app layers, Docker, K8s, observability built in |
| **ThreeDotsLabs/wild-workouts-go-ddd-example** | DDD + CQRS example in Go | Domain events, CQRS separation, multiple bounded contexts |

**URLs:**
- https://github.com/evrone/go-clean-template
- https://github.com/bxcodec/go-clean-arch
- https://github.com/golang-standards/project-layout
- https://github.com/ardanlabs/service
- https://github.com/ThreeDotsLabs/wild-workouts-go-ddd-example

### Style Guides from Major Companies

| Company | Guide | Key Takeaways |
|---------|-------|--------------|
| **Uber** | uber-go/guide | Error wrapping, interface compliance checks, avoid globals, struct init with field names, functional options pattern |
| **Google** | google/go-style | Commentary conventions, package naming, receiver naming, error strings lowercase |
| **HashiCorp** | hashicorp/consul codebase | Clean separation of agent/api/command, interface-driven design |
| **CockroachDB** | cockroachdb/cockroach | Massive Go monorepo, package organization at scale |

**URLs:**
- https://github.com/uber-go/guide/blob/master/style.md
- https://google.github.io/styleguide/go/
- https://go.dev/doc/effective_go

### What Real Companies Actually Use

Based on public codebases and blog posts:

1. **Manual DI** is overwhelmingly the most common pattern. Uber uses `fx` internally but most teams outside Uber use constructors.

2. **chi or standard library** for HTTP routing. Gin has higher GitHub stars but chi's compatibility with `net/http` middleware is preferred for production code.

3. **pgx v5** over `lib/pq` for PostgreSQL. pgx is actively maintained, supports PostgreSQL-specific features (COPY, binary protocol, connection pooling), and has better performance.

4. **slog** (Go 1.21+) for structured logging, replacing zerolog/zap in new projects. slog is in the standard library and good enough for most needs.

5. **Table-driven tests** universally. No test framework (testify assertions are common but not required).

6. **golang-migrate** for database migrations. Alternatives: goose, atlas. All are fine; golang-migrate has the largest community.

7. **golangci-lint** for linting. Configurable, runs many linters in parallel.

---

## 10. Recommended Libraries

### Core Dependencies

| Library | Purpose | Import Path |
|---------|---------|------------|
| **pgx v5** | PostgreSQL driver + connection pool | `github.com/jackc/pgx/v5` |
| **chi v5** | HTTP router (net/http compatible) | `github.com/go-chi/chi/v5` |
| **shopspring/decimal** | Exact decimal arithmetic for money | `github.com/shopspring/decimal` |
| **google/uuid** | UUID generation | `github.com/google/uuid` |
| **golang-jwt/jwt** | JWT token generation/validation | `github.com/golang-jwt/jwt/v5` |
| **golang-migrate** | Database migrations | `github.com/golang-migrate/migrate/v4` |
| **x/crypto/bcrypt** | Password hashing | `golang.org/x/crypto/bcrypt` |
| **x/time/rate** | Rate limiting | `golang.org/x/time/rate` |

### Testing Dependencies

| Library | Purpose | Import Path |
|---------|---------|------------|
| **testcontainers-go** | Real PostgreSQL in tests | `github.com/testcontainers/testcontainers-go` |
| **go-cmp** | Deep equality comparison | `github.com/google/go-cmp/cmp` |

### Development Dependencies

| Library | Purpose | Import Path |
|---------|---------|------------|
| **golangci-lint** | Linter aggregator | (CLI tool, not imported) |
| **air** | Hot reload for development | (CLI tool) |

### What We Explicitly Avoid

| Library | Why Not |
|---------|---------|
| **GORM / any ORM** | ORMs hide SQL, make debugging harder, add abstraction with no benefit for a project that needs precise SQL control (double-entry accounting) |
| **testify** | Built-in `testing` package + `go-cmp` is sufficient; testify's assertion style encourages less readable tests |
| **viper** | Over-engineered for environment variables; `os.Getenv` + a Config struct is simpler and more explicit |
| **uber-go/fx** | Runtime DI adds complexity with no benefit at pfin's scale |
| **gin** | Not `net/http` compatible; chi works with standard middleware |

---

## 11. Summary and Recommendations

### Architecture Decision

**Use clean architecture with hexagonal thinking, organized as a modular monolith.**

- **Domain layer** (`internal/domain/`): Entities, value objects, repository interfaces, domain errors. Zero external dependencies beyond `shopspring/decimal` and `google/uuid`.
- **Application layer** (`internal/app/`): Use case services. Depends only on domain interfaces. One sub-package per bounded context (auth, household, account, journal).
- **Infrastructure layer** (`internal/infra/`): PostgreSQL repositories, JWT generator, bcrypt hasher, event bus. Implements domain interfaces.
- **API layer** (`internal/api/`): HTTP handlers, middleware, router. Translates HTTP to application service calls.
- **Composition root** (`cmd/api/main.go`): Wires everything together. The only place that knows about all concrete types.

### Key Patterns

| Pattern | Implementation |
|---------|---------------|
| Dependency injection | Constructor injection, manual wiring in `main.go` |
| Error handling | Typed `DomainError` with codes, mapped to HTTP status in handlers |
| Testing | Table-driven unit tests for domain, mocked repos for services, testcontainers for infrastructure |
| Middleware chain | chi middleware: RequestID -> Logger -> Recovery -> CORS -> RateLimit -> Auth -> Scope -> Handler |
| Module boundaries | Each module has domain/app/infra/api; cross-module via interfaces |
| Domain events | In-process event bus (replaceable with message queue for microservice extraction) |

### What Makes This Production-Grade

1. **Compile-time safety**: No reflection, no runtime DI, no magic. Missing dependencies are compile errors.
2. **Testable at every layer**: Domain logic is pure. Services use interfaces. Infrastructure uses real databases.
3. **Explicit dependencies**: Every constructor documents what it needs. No hidden state.
4. **Graceful shutdown**: Server handles SIGTERM, drains connections, closes pools.
5. **Structured logging**: slog with JSON output, request IDs, timing.
6. **Security by default**: JWT validation, scope-based access control, rate limiting, CORS.
7. **Financial correctness**: shopspring/decimal for money, balanced entry validation, immutable ledger.
8. **Migration path**: Modular monolith structure allows extracting services when needed.

### Open-Source References

| Reference | URL |
|-----------|-----|
| evrone/go-clean-template | https://github.com/evrone/go-clean-template |
| bxcodec/go-clean-arch | https://github.com/bxcodec/go-clean-arch |
| ardanlabs/service | https://github.com/ardanlabs/service |
| ThreeDotsLabs/wild-workouts-go-ddd-example | https://github.com/ThreeDotsLabs/wild-workouts-go-ddd-example |
| golang-standards/project-layout | https://github.com/golang-standards/project-layout |
| Uber Go Style Guide | https://github.com/uber-go/guide/blob/master/style.md |
| Google Go Style Guide | https://google.github.io/styleguide/go/ |
| Effective Go | https://go.dev/doc/effective_go |

---
*Research completed: 2026-03-20*
