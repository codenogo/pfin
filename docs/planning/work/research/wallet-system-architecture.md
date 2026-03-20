# Research: Wallet System Architecture

**Context:** Personal finance platform (Go + PostgreSQL + Next.js)
**Date:** 2026-03-20
**Status:** Complete
**Related:** [Account Management](../features/account-management/FEATURE.md), [Transaction Engine](../features/transaction-engine/FEATURE.md)

---

## 1. What Is a "Wallet" in Personal Finance?

### 1.1 Industry Survey

Personal finance apps use "wallet" as a user-facing concept for any container that holds or owes money:

| App | Term Used | What It Means |
|-----|-----------|---------------|
| **Toshl Finance** | "Account" (with wallet-like UI) | Each bank account, credit card, cash stash is an "account" with a balance, icon, and color |
| **Wallet by BudgetBakers** | "Account" (marketed as "wallet") | Checking, savings, cash, credit card, loan. Supports bank sync. Groups into "account groups" |
| **Bluecoins** | "Account" | Asset accounts (bank, cash, e-wallet) and liability accounts (credit card, loan). Transfer between them |
| **Money Manager** | "Account" / "Asset" | Simple accounts with types. Transfers are special transaction types |
| **YNAB** | "Account" (budget vs tracking) | On-budget accounts (checking, credit card) vs off-budget (investment, mortgage) |
| **Firefly III** | "Account" (with strict types) | Asset, expense, revenue, liability, reconciliation accounts. Full double-entry |
| **GnuCash** | "Account" (chart of accounts) | Pure double-entry: Assets, Liabilities, Income, Expenses, Equity. Every account is a node in a tree |

**Key finding:** No major personal finance app uses "wallet" as the primary domain term. They all use "account." The word "wallet" appears only in marketing copy or app names. Internally, the data model is always "accounts."

### 1.2 Wallet Types (User Mental Model)

Users think in terms of these wallet/account types:

| User Concept | Accounting Nature | Examples |
|-------------|-------------------|----------|
| Cash wallet | Asset | Physical cash, petty cash |
| Bank account | Asset | Checking, savings |
| Credit card | Liability | Visa, Mastercard |
| E-wallet | Asset | PayPal, Venmo, Apple Pay, M-Pesa |
| Loan | Liability | Mortgage, car loan, student loan |
| Investment | Asset | Brokerage, 401k, crypto |

### 1.3 Wallet vs Account -- Is There a Meaningful Distinction?

**Short answer: No.** They are the same concept with different UX framing.

**Analysis:**

| Dimension | "Wallet" framing | "Account" framing |
|-----------|-----------------|-------------------|
| Mental model | Container I put money in/take money out of | Ledger that tracks a balance |
| Feels natural for | Cash, e-wallets, prepaid cards | Bank accounts, credit cards, loans |
| Accounting mapping | IS an account (asset or liability) | IS an account |
| Operations | Add money, spend, transfer | Debit, credit, transfer |
| Balance semantics | "How much is in here?" | "What is the current balance?" |

The distinction is purely UX. A "wallet" IS an account. Some apps use "wallet" because it sounds friendlier than "account" for casual users. But the data model underneath is identical.

### 1.4 How Wallets Relate to Double-Entry Accounting

In double-entry bookkeeping:
- Every account belongs to one of five types: **Asset, Liability, Equity, Income, Expense**
- A "wallet" (user-facing) maps to an **Asset** or **Liability** account
- Spending from a wallet creates a journal entry: debit an Expense account, credit the Asset account
- Receiving income: debit the Asset account, credit an Income account
- Transfer between wallets: debit one Asset, credit another Asset

A wallet does not "wrap" an account. A wallet IS an account in the chart of accounts, with additional presentation metadata (icon, color, display order).

---

## 2. Wallet Features

### 2.1 Balance Tracking

| Balance Type | Definition | Use Case |
|-------------|-----------|----------|
| **Current balance** | Sum of all posted transactions | Primary display |
| **Available balance** | Current balance minus pending holds | Bank-synced accounts |
| **Cleared balance** | Sum of reconciled transactions | Reconciliation workflows |

For a manual-entry personal finance app (no bank sync initially), **current balance** is the only one needed at launch. Available/cleared balance become relevant when bank sync or reconciliation features are added.

**Implementation approaches:**

1. **Real-time computation** (`SELECT SUM(amount) FROM journal_lines WHERE account_id = ?`): Always accurate, but expensive at scale.
2. **Cached/materialized balance** (store `balance` on the accounts table, update on each transaction): Fast reads, requires careful concurrency handling.
3. **Hybrid** (materialized balance + periodic reconciliation against ledger sum): Best of both worlds.

**Recommendation:** Start with **materialized balance** (option 2) with a reconciliation check. Personal finance apps are read-heavy (dashboard shows balances), write-light (a few transactions per day per account). The materialized balance avoids expensive aggregations on every page load.

### 2.2 Transfers Between Wallets

A transfer is a double-entry transaction:
- **Debit** the destination account (increases asset)
- **Credit** the source account (decreases asset)

This is a single journal entry with two lines. No special "transfer" entity is needed -- it's just a regular transaction where both sides are user-visible accounts (as opposed to a spend, where one side is an expense account the user may not see).

Firefly III marks transfers with a `transaction_type = 'transfer'` flag on the journal entry. This is a good pattern -- it lets the UI distinguish transfers from income/expenses without needing a separate table.

### 2.3 Wallet-Level Budgets or Spending Limits

Two approaches:

1. **Budget system is separate from wallets.** Budgets are assigned to categories (e.g., "Food: $500/month"), not to specific wallets. This is the YNAB/Firefly III model.
2. **Spending limits on wallets.** Credit card limits, overdraft limits. This is account metadata, not a budget.

**Recommendation:** Keep budgets as a separate domain (already planned as Feature #4). Add optional `credit_limit` field on liability accounts for credit card/overdraft tracking.

### 2.4 Multi-Currency Wallets

Each account has a **single native currency.** A USD checking account holds USD. A EUR savings account holds EUR.

Multi-currency considerations:
- Transfers between accounts with different currencies require an **exchange rate** on the journal entry
- Net worth dashboard needs a **reporting currency** to aggregate across currencies
- Exchange rates can be user-entered per transaction or fetched from an API

**Recommendation:** Per the SHAPE.md open question, multi-currency can be deferred to v2. Design the schema to support it (currency field on accounts, optional exchange rate on journal entries) but don't build the conversion logic yet.

### 2.5 Shared Wallets (Household Context)

Shared wallets allow multiple users to transact against the same account. This requires:
- An `account_members` join table (account_id, user_id, role)
- Permission model (owner, editor, viewer)
- Audit trail (who made each transaction)

**Recommendation:** Defer to v2. The current architecture is per-user (tenant-scoped). Shared wallets add significant complexity to authorization, conflict resolution, and data isolation.

### 2.6 Wallet Categories / Grouping

Users want to group accounts for display:
- "Everyday" (checking, cash, PayPal)
- "Savings" (savings accounts, CDs)
- "Debt" (credit cards, loans)

This can be achieved with:
1. **Automatic grouping by account type** (all checking accounts together)
2. **User-defined groups** (custom grouping with display order)
3. **Both** (default grouping by type, with user override)

**Recommendation:** Start with automatic grouping by account type. Add user-defined groups as a future enhancement. This avoids premature complexity while still providing a clean UI.

---

## 3. Database Schema

### 3.1 Core Question: Wallet = Account, or Wallet Wraps Account?

**Option A: Wallet IS the Account (Recommended)**

```
accounts table = the single source of truth
  - Contains accounting fields (type, balance, currency)
  - Contains presentation fields (icon, color, display_order)
  - No separate "wallets" table
```

**Option B: Wallet Wraps Account**

```
accounts table = pure accounting (chart of accounts)
wallets table = user-facing presentation layer
  - wallet has FK to account
  - wallet adds icon, color, display_order
  - some accounts (expense, income, equity) have no wallet
```

**Analysis:**

| Criterion | Option A (wallet = account) | Option B (wallet wraps account) |
|-----------|---------------------------|-------------------------------|
| Simplicity | One table, one concept | Two tables, mapping layer |
| Query complexity | Simple JOINs | Extra JOIN for every wallet query |
| Domain clarity | "Account" does double duty | Clean separation of concerns |
| Extensibility | Presentation fields clutter accounting table | Easy to add wallet-only features |
| Precedent | Firefly III, YNAB, Bluecoins | No major app does this |

**Recommendation: Option A -- Wallet IS the Account.**

Reasons:
1. Every major personal finance app models it this way
2. For a personal finance app (not an ERP), the user-facing account IS the accounting account. There is no need for invisible internal accounts that don't correspond to a user wallet
3. The presentation fields (icon, color, display_order) are lightweight and don't warrant a separate table
4. Expense and Income accounts (which have no "wallet" representation) can simply have `is_user_visible = false` or be filtered by account category
5. Adding a wrapper layer creates an impedance mismatch that complicates every query

### 3.2 Recommended Schema

```sql
-- Account types enum
CREATE TYPE account_category AS ENUM (
    'asset',      -- Things you own (checking, savings, cash, investments)
    'liability',  -- Things you owe (credit cards, loans)
    'income',     -- Money coming in (salary, interest)
    'expense',    -- Money going out (food, rent, utilities)
    'equity'      -- Opening balances, adjustments
);

CREATE TYPE account_type AS ENUM (
    -- Asset subtypes
    'checking',
    'savings',
    'cash',
    'e_wallet',        -- PayPal, Venmo, M-Pesa
    'investment',
    'other_asset',
    -- Liability subtypes
    'credit_card',
    'loan',
    'mortgage',
    'other_liability',
    -- Income/Expense (can be extended)
    'income',
    'expense',
    -- Equity
    'equity'
);

CREATE TABLE accounts (
    -- Identity
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),

    -- Accounting core
    name            VARCHAR(255) NOT NULL,
    category        account_category NOT NULL,  -- asset, liability, income, expense, equity
    account_type    account_type NOT NULL,       -- checking, savings, credit_card, etc.
    currency        CHAR(3) NOT NULL DEFAULT 'USD',  -- ISO 4217
    balance         BIGINT NOT NULL DEFAULT 0,   -- stored in minor units (cents)
    is_asset        BOOLEAN GENERATED ALWAYS AS (category = 'asset') STORED,

    -- Presentation (the "wallet" layer)
    icon            VARCHAR(64),                 -- icon identifier (e.g., 'bank', 'credit-card', 'cash')
    color           VARCHAR(7),                  -- hex color (e.g., '#4A90D9')
    display_order   INTEGER NOT NULL DEFAULT 0,
    is_visible      BOOLEAN NOT NULL DEFAULT TRUE,  -- false for system accounts (expense/income categories)

    -- Metadata
    institution     VARCHAR(255),                -- bank name, e.g., "Chase", "PayPal"
    account_number  VARCHAR(64),                 -- last 4 digits, masked
    credit_limit    BIGINT,                      -- for credit cards/lines of credit (minor units)
    notes           TEXT,

    -- Lifecycle
    is_archived     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT accounts_name_unique UNIQUE (user_id, name),
    CONSTRAINT accounts_balance_check CHECK (
        -- Credit cards/loans can have negative balances (from user perspective, they owe money)
        -- Assets should generally be >= 0 but we don't enforce (overdrafts exist)
        TRUE
    )
);

-- Indexes
CREATE INDEX idx_accounts_user_id ON accounts(user_id);
CREATE INDEX idx_accounts_user_category ON accounts(user_id, category);
CREATE INDEX idx_accounts_user_visible ON accounts(user_id, is_visible, is_archived);

-- Journal entries (transactions)
CREATE TABLE journal_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    date            DATE NOT NULL,
    description     VARCHAR(500),
    transaction_type VARCHAR(20) NOT NULL DEFAULT 'standard',
        -- 'standard' = income/expense
        -- 'transfer' = between user accounts
        -- 'opening'  = opening balance
        -- 'adjustment' = reconciliation adjustment
    reference       VARCHAR(255),        -- external reference number
    notes           TEXT,
    is_reconciled   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_journal_entries_user_date ON journal_entries(user_id, date DESC);
CREATE INDEX idx_journal_entries_type ON journal_entries(user_id, transaction_type);

-- Journal lines (the double-entry split)
CREATE TABLE journal_lines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_entry_id UUID NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id      UUID NOT NULL REFERENCES accounts(id),
    amount          BIGINT NOT NULL,     -- positive = debit, negative = credit
    -- OR use separate debit/credit columns:
    -- debit         BIGINT NOT NULL DEFAULT 0,
    -- credit        BIGINT NOT NULL DEFAULT 0,
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    exchange_rate   DECIMAL(18, 8),      -- only set for multi-currency transactions
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_journal_lines_entry ON journal_lines(journal_entry_id);
CREATE INDEX idx_journal_lines_account ON journal_lines(account_id);
CREATE INDEX idx_journal_lines_account_date ON journal_lines(account_id, created_at);

-- Categories (for expense/income classification)
CREATE TABLE categories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    name            VARCHAR(255) NOT NULL,
    parent_id       UUID REFERENCES categories(id),
    icon            VARCHAR(64),
    color           VARCHAR(7),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT categories_name_unique UNIQUE (user_id, parent_id, name)
);

-- Link journal entries to categories
-- (A single transaction can be categorized; splits can have different categories)
ALTER TABLE journal_lines ADD COLUMN category_id UUID REFERENCES categories(id);

-- Tags
ALTER TABLE journal_entries ADD COLUMN tags JSONB DEFAULT '[]'::jsonb;
```

### 3.3 How Wallets Map to the Chart of Accounts

```
Chart of Accounts (user: Alice)
================================

Assets (category = 'asset', is_visible = true)
  ├── Chase Checking    (account_type = 'checking')     ← USER SEES AS "WALLET"
  ├── Ally Savings      (account_type = 'savings')      ← USER SEES AS "WALLET"
  ├── Cash              (account_type = 'cash')          ← USER SEES AS "WALLET"
  └── PayPal            (account_type = 'e_wallet')      ← USER SEES AS "WALLET"

Liabilities (category = 'liability', is_visible = true)
  ├── Visa Credit Card  (account_type = 'credit_card')   ← USER SEES AS "WALLET"
  └── Student Loan      (account_type = 'loan')          ← USER SEES AS "WALLET"

Income (category = 'income', is_visible = false -- or true if user wants to see)
  ├── Salary
  └── Interest Income

Expenses (category = 'expense', is_visible = false -- managed via categories instead)
  ├── (not typically used if using categories table)
  └── ...

Equity (category = 'equity', is_visible = false)
  └── Opening Balances
```

The "wallet list" in the UI is simply:
```sql
SELECT * FROM accounts
WHERE user_id = $1
  AND is_visible = TRUE
  AND is_archived = FALSE
  AND category IN ('asset', 'liability')
ORDER BY display_order, name;
```

### 3.4 Simplified vs Full Double-Entry

The SHAPE.md has an open question about double-entry vs simple ledger. Here is the key insight:

**You can have full double-entry internally while presenting a simple UX.**

When a user records "Spent $50 at Grocery Store from Chase Checking":
- Internally: Create a journal entry with two lines:
  - Debit: Expense category "Groceries" +$50
  - Credit: "Chase Checking" -$50
- User sees: One transaction, "$50, Grocery Store, from Chase Checking, category: Groceries"

The user never needs to know about debits and credits. The double-entry is invisible plumbing that guarantees mathematical consistency and enables proper reporting.

**Recommendation:** Implement double-entry internally. Present a single-entry UX. This is exactly what Firefly III does and it works extremely well.

---

## 4. Architecture Patterns

### 4.1 Wallet as First-Class Entity vs View Over Accounts

| Approach | Description | Verdict |
|----------|-------------|---------|
| **First-class entity** | Separate `wallets` table with own logic | Over-engineered for personal finance |
| **View over accounts** | SQL view or application-layer filter | Unnecessary indirection |
| **Account with presentation metadata** | Single `accounts` table, filtered by category | **Recommended** |

The "wallet" is not a separate concept. It is an account where `category IN ('asset', 'liability') AND is_visible = TRUE`. The API can expose a `/wallets` endpoint that is syntactic sugar over the accounts query.

### 4.2 How Transfers Map to Journal Entries

**Example: Transfer $200 from Checking to Savings**

```
journal_entries:
  id: "je-001"
  description: "Transfer to savings"
  transaction_type: "transfer"
  date: 2026-03-20

journal_lines:
  [1] account_id: "checking-account"  amount: -20000  (credit, money leaving)
  [2] account_id: "savings-account"   amount: +20000  (debit, money arriving)
```

The sum of all journal_lines for a given journal_entry MUST equal zero. This is the fundamental double-entry invariant.

### 4.3 Balance Computation Strategy

**Recommended: Materialized balance with transactional updates.**

```sql
-- Within a transaction:
BEGIN;

-- Insert journal entry + lines
INSERT INTO journal_entries (...) VALUES (...);
INSERT INTO journal_lines (...) VALUES (...);

-- Update account balances atomically
UPDATE accounts SET balance = balance - 20000, updated_at = NOW()
WHERE id = 'checking-account';

UPDATE accounts SET balance = balance + 20000, updated_at = NOW()
WHERE id = 'savings-account';

COMMIT;
```

**Reconciliation job** (run periodically or on demand):
```sql
-- Verify materialized balance matches ledger
SELECT
    a.id,
    a.name,
    a.balance AS materialized_balance,
    COALESCE(SUM(jl.amount), 0) AS computed_balance,
    a.balance - COALESCE(SUM(jl.amount), 0) AS drift
FROM accounts a
LEFT JOIN journal_lines jl ON jl.account_id = a.id
WHERE a.user_id = $1
GROUP BY a.id
HAVING a.balance != COALESCE(SUM(jl.amount), 0);
```

### 4.4 Concurrency Handling

**Problem:** Two simultaneous transactions on the same account could corrupt the balance.

**Solution: Row-level locking with `SELECT ... FOR UPDATE`.**

```sql
BEGIN;

-- Lock the affected accounts (always lock in consistent order to avoid deadlocks)
SELECT id, balance FROM accounts
WHERE id IN ('checking-account', 'savings-account')
ORDER BY id
FOR UPDATE;

-- Proceed with inserts and updates
INSERT INTO journal_entries ...;
INSERT INTO journal_lines ...;
UPDATE accounts SET balance = balance + $amount WHERE id = ...;

COMMIT;
```

This is the standard pattern for financial systems. PostgreSQL's MVCC handles it efficiently.

**Alternative:** Use `SERIALIZABLE` isolation level. Simpler code but higher retry rate under contention. For a personal finance app (low contention -- one user, a few transactions per day), either approach works.

---

## 5. Go Implementation Patterns

### 5.1 Domain Model

```go
// domain/account.go

type AccountCategory string

const (
    CategoryAsset     AccountCategory = "asset"
    CategoryLiability AccountCategory = "liability"
    CategoryIncome    AccountCategory = "income"
    CategoryExpense   AccountCategory = "expense"
    CategoryEquity    AccountCategory = "equity"
)

type AccountType string

const (
    TypeChecking      AccountType = "checking"
    TypeSavings       AccountType = "savings"
    TypeCash          AccountType = "cash"
    TypeEWallet       AccountType = "e_wallet"
    TypeInvestment    AccountType = "investment"
    TypeOtherAsset    AccountType = "other_asset"
    TypeCreditCard    AccountType = "credit_card"
    TypeLoan          AccountType = "loan"
    TypeMortgage      AccountType = "mortgage"
    TypeOtherLiability AccountType = "other_liability"
    TypeIncome        AccountType = "income"
    TypeExpense       AccountType = "expense"
    TypeEquity        AccountType = "equity"
)

type Account struct {
    ID           uuid.UUID
    UserID       uuid.UUID
    Name         string
    Category     AccountCategory
    AccountType  AccountType
    Currency     string           // ISO 4217
    Balance      int64            // minor units (cents)
    Icon         *string
    Color        *string
    DisplayOrder int
    IsVisible    bool
    Institution  *string
    AccountNumber *string
    CreditLimit  *int64
    Notes        *string
    IsArchived   bool
    CreatedAt    time.Time
    UpdatedAt    time.Time
}

// IsWallet returns true if this account is user-facing (what users think of as a "wallet")
func (a *Account) IsWallet() bool {
    return (a.Category == CategoryAsset || a.Category == CategoryLiability) &&
        a.IsVisible && !a.IsArchived
}

// AvailableCredit returns remaining credit for liability accounts
func (a *Account) AvailableCredit() *int64 {
    if a.CreditLimit == nil {
        return nil
    }
    available := *a.CreditLimit - a.Balance
    return &available
}
```

### 5.2 Service Layer

```go
// service/account_service.go

type AccountService struct {
    repo    AccountRepository
    txMgr   TransactionManager  // manages DB transactions
}

// CreateWallet creates a user-facing account (asset or liability)
func (s *AccountService) CreateWallet(ctx context.Context, params CreateWalletParams) (*Account, error) {
    // Validate category is asset or liability
    if params.Category != CategoryAsset && params.Category != CategoryLiability {
        return nil, ErrInvalidWalletCategory
    }

    // Validate account type matches category
    if err := validateTypeForCategory(params.AccountType, params.Category); err != nil {
        return nil, err
    }

    account := &Account{
        ID:          uuid.New(),
        UserID:      params.UserID,
        Name:        params.Name,
        Category:    params.Category,
        AccountType: params.AccountType,
        Currency:    params.Currency,
        Balance:     params.InitialBalance, // will create opening balance journal entry
        IsVisible:   true,
        // ... presentation fields
    }

    err := s.txMgr.WithTx(ctx, func(tx context.Context) error {
        if err := s.repo.Create(tx, account); err != nil {
            return err
        }

        // If initial balance is non-zero, create opening balance journal entry
        if params.InitialBalance != 0 {
            return s.createOpeningBalance(tx, account)
        }
        return nil
    })

    return account, err
}

// Transfer moves money between two user accounts
func (s *AccountService) Transfer(ctx context.Context, params TransferParams) (*JournalEntry, error) {
    return s.txMgr.WithTxResult(ctx, func(tx context.Context) (*JournalEntry, error) {
        // Lock accounts in consistent order (by ID) to prevent deadlocks
        accounts, err := s.repo.LockAccountsForUpdate(tx, sortIDs(params.FromAccountID, params.ToAccountID))
        if err != nil {
            return nil, err
        }

        from := accounts[params.FromAccountID]
        to := accounts[params.ToAccountID]

        // Validate same user owns both accounts
        if from.UserID != to.UserID {
            return nil, ErrCrossUserTransfer
        }

        // Create journal entry
        entry := &JournalEntry{
            ID:              uuid.New(),
            UserID:          from.UserID,
            Date:            params.Date,
            Description:     params.Description,
            TransactionType: TransactionTypeTransfer,
            Lines: []JournalLine{
                {AccountID: from.ID, Amount: -params.Amount},  // credit source
                {AccountID: to.ID, Amount: params.Amount},     // debit destination
            },
        }

        if err := s.journalRepo.Create(tx, entry); err != nil {
            return nil, err
        }

        // Update balances
        if err := s.repo.AdjustBalance(tx, from.ID, -params.Amount); err != nil {
            return nil, err
        }
        if err := s.repo.AdjustBalance(tx, to.ID, params.Amount); err != nil {
            return nil, err
        }

        return entry, nil
    })
}
```

### 5.3 How Wallet Operations Wrap Accounting Operations

The key pattern: **wallet operations are convenience methods that generate proper journal entries.**

| User Action | Wallet Operation | Underlying Accounting |
|-------------|-----------------|----------------------|
| "Add income" | `RecordIncome(walletID, amount, category)` | Debit asset account, credit income account |
| "Record expense" | `RecordExpense(walletID, amount, category)` | Debit expense account, credit asset account |
| "Transfer" | `Transfer(fromWalletID, toWalletID, amount)` | Debit destination, credit source |
| "Set initial balance" | `SetOpeningBalance(walletID, amount)` | Debit asset, credit equity (or vice versa) |
| "Pay credit card" | `Transfer(checkingID, creditCardID, amount)` | Debit liability (reduces debt), credit asset |

The user never writes journal entries directly. The service layer translates user-intent operations into proper double-entry journal entries.

---

## 6. Existing Implementations Analysis

### 6.1 Firefly III (PHP/Laravel, most relevant comparison)

**Architecture:**
- **Accounts** are the core entity. Types: asset, expense, revenue, liability, reconciliation, initial-balance
- Asset accounts are what users see as "wallets" (checking, savings, cash, etc.)
- **Transactions** are "transaction journals" with "transaction" line items (their double-entry split)
- Transfers are transactions where both accounts are asset accounts
- Balance is computed from transaction sums (not materialized), with caching at the API layer
- Account metadata includes: name, IBAN, BIC, account number, virtual balance, active flag, order

**Key lessons:**
- Proving that account = wallet works at scale
- Virtual balance feature (for accounts where the real balance differs from tracked transactions -- useful for partial tracking)
- Account grouping by type is sufficient for UI

### 6.2 GnuCash (C/Scheme, gold standard for accounting)

**Architecture:**
- Pure chart of accounts: hierarchical tree with 5 root types
- Every account can have sub-accounts (e.g., Assets > Bank > Checking)
- "Splits" are their journal lines (each transaction has 2+ splits that sum to zero)
- Balance is computed from splits (no materialization)
- Handles multi-currency via price database and exchange splits

**Key lessons:**
- Hierarchical accounts are powerful but complex UX
- The five-type model (Asset, Liability, Income, Expense, Equity) is complete and proven
- For personal finance, a flat account list with category grouping is simpler than a hierarchy

### 6.3 hledger / Beancount (Plain-text accounting)

**Architecture:**
- Text files with journal entries
- Account names are hierarchical (e.g., `Assets:Bank:Checking`)
- Balance is always computed from the journal (no state)
- Extremely strict double-entry (every transaction must balance)

**Key lessons:**
- Proves that the journal is the single source of truth
- Account hierarchy via naming convention (colon-separated) is elegant
- Balance assertions (verify expected balance at a point in time) are a powerful feature

### 6.4 Go-Specific Open Source

| Project | Notes |
|---------|-------|
| **github.com/mattermost/focalboard** | Not finance but shows Go clean architecture patterns |
| **github.com/dariubs/GoBooks** | Reference for Go project structure |
| Various Go accounting libs | Most are toy projects; no production-grade Go personal finance app exists publicly |

The Go ecosystem lacks a mature personal finance reference implementation, which means we design from accounting principles rather than copying an existing Go codebase.

---

## 7. Recommendation

### Primary Recommendation: Wallet = Account (Single Entity)

**A wallet is an account with `category IN ('asset', 'liability')` and `is_visible = TRUE`.**

There is no separate wallets table. The API exposes two complementary interfaces:

1. **`/api/v1/accounts`** -- Full account management (for power users, reports, accounting views)
2. **`/api/v1/wallets`** -- Convenience endpoint that filters to user-visible asset/liability accounts (for the main dashboard)

Both endpoints read from and write to the same `accounts` table. The `/wallets` endpoint is syntactic sugar.

### Secondary Recommendation: Double-Entry Internally, Simple UX Externally

Implement full double-entry bookkeeping with journal entries and journal lines. Never expose debits/credits in the UI. Translate user actions into journal entries in the service layer.

### Architecture Summary

```
User Interface (Next.js)
    |
    | "Wallets" = filtered view of accounts
    | "Transactions" = simplified journal entries
    |
API Layer (Go handlers)
    |
    | /wallets  -> AccountService (filtered)
    | /transactions -> TransactionService (simplified journal creation)
    |
Service Layer (Go)
    |
    | AccountService: CRUD, balance queries, wallet filtering
    | TransactionService: income, expense, transfer -> journal entries
    | ReconciliationService: balance verification
    |
Domain Layer (Go)
    |
    | Account (with IsWallet() helper)
    | JournalEntry + JournalLines
    | Category
    |
Repository Layer (Go)
    |
    | PostgreSQL with row-level locking for balance updates
    | Materialized balances on accounts table
    | Journal as source of truth (reconcilable)
```

### What This Means for Existing Feature Docs

The current [Account Management FEATURE.md](../features/account-management/FEATURE.md) describes:
> "accounts table (id, user_id, name, type, balance, currency, is_asset, created_at, updated_at)"

This aligns with the recommendation but needs enrichment:
- Add `category` (the five accounting types) alongside `account_type` (the subtype)
- Add presentation fields: `icon`, `color`, `display_order`, `is_visible`
- Add metadata: `institution`, `account_number`, `credit_limit`, `notes`
- Add `is_archived` for soft-delete with historical preservation
- Store balance in minor units (BIGINT cents, not DECIMAL) for precision

The current [Transaction Engine FEATURE.md](../features/transaction-engine/FEATURE.md) describes a single-entry model. This research recommends upgrading to double-entry internally while keeping the UX unchanged.

### Schema Migration Path

If the project starts with the simpler single-entry model from the existing feature docs, migration to double-entry is straightforward:
1. Create `journal_entries` and `journal_lines` tables
2. Migrate existing transactions: each becomes a journal entry with two lines
3. Add computed expense/income accounts
4. Verify balance consistency

However, **starting with double-entry is cheaper than migrating later.** The service layer hides the complexity from the UI, so the UX cost is zero.

---

## Open Questions Resolved

| Question | Resolution |
|----------|-----------|
| Wallet vs Account? | Same concept. Use "account" in the domain, "wallet" optionally in UX |
| Separate wallets table? | No. Single accounts table with presentation metadata |
| Double-entry vs simple ledger? | Double-entry internally, simple UX externally |
| Multi-currency? | Schema supports it (currency field, exchange_rate). Logic deferred to v2 |
| Balance computation? | Materialized on accounts table, reconcilable against journal |

## Open Questions Remaining

| Question | Impact | Suggested Resolution |
|----------|--------|---------------------|
| Should expense/income tracking use the `accounts` table or only the `categories` table? | Schema design. If using full double-entry, expenses need accounts OR we use categories as virtual accounts | Recommend: use categories for user-facing classification, create system expense/income accounts automatically per category for ledger integrity |
| Account hierarchy (sub-accounts) or flat list? | UX complexity, reporting | Recommend: flat list for v1, optional parent_id for v2 |
| How to handle account deletion with existing transactions? | Data integrity | Recommend: soft-delete only (is_archived). Never hard-delete accounts with journal lines |

---
*Research completed: 2026-03-20*
