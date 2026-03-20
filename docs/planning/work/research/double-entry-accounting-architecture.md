# Research: Double-Entry Accounting Architecture

**Context:** Resolves open question #2 from [SHAPE.md](../ideas/personal-finance/SHAPE.md): "Double-entry bookkeeping vs simple ledger -- what level of accounting rigor?"
**Recommendation:** Double-entry. The incremental complexity is modest, and it eliminates an entire class of data-integrity bugs while making transfers, multi-currency, and reporting first-class.
**Date:** 2026-03-20

---

## Table of Contents

1. [Double-Entry Fundamentals for Software](#1-double-entry-fundamentals-for-software)
2. [Database Schema Design](#2-database-schema-design)
3. [Open-Source Implementations -- Patterns Worth Stealing](#3-open-source-implementations--patterns-worth-stealing)
4. [Go-Specific Patterns](#4-go-specific-patterns)
5. [PostgreSQL-Specific Patterns](#5-postgresql-specific-patterns)
6. [API Design](#6-api-design)
7. [Multi-Currency Architecture](#7-multi-currency-architecture)
8. [Verdict and Recommendations](#8-verdict-and-recommendations)

---

## 1. Double-Entry Fundamentals for Software

### The Accounting Equation

```
Assets = Liabilities + Equity + (Income - Expenses)
```

This equation must **always** balance. Double-entry bookkeeping enforces this structurally: every financial event is recorded as a **journal entry** consisting of two or more **line items** (postings) whose debits and credits sum to zero.

### The Five Account Types

| Type | Normal Balance | Debit Effect | Credit Effect | Examples |
|------|---------------|-------------|--------------|----------|
| **Asset** | Debit | Increase | Decrease | Checking, Savings, Investment, Cash, Accounts Receivable |
| **Liability** | Credit | Decrease | Increase | Credit Card, Mortgage, Loan, Accounts Payable |
| **Equity** | Credit | Decrease | Increase | Opening Balance, Retained Earnings |
| **Income** | Credit | Decrease | Increase | Salary, Interest Income, Dividends |
| **Expense** | Credit (reversed) | Increase | Decrease | Groceries, Rent, Utilities |

**Key insight for software:** You don't need separate "debit" and "credit" columns. Use a single **signed amount** column where positive = debit, negative = credit (or vice versa). The constraint is that all line items in a journal entry sum to zero.

### How Common Personal Finance Events Map

| Event | Debit Account | Credit Account |
|-------|--------------|----------------|
| Receive salary | Asset:Checking +3000 | Income:Salary -3000 |
| Pay rent | Expense:Rent +1500 | Asset:Checking -1500 |
| Transfer savings | Asset:Savings +500 | Asset:Checking -500 |
| Credit card purchase | Expense:Groceries +80 | Liability:CreditCard -80 |
| Pay credit card bill | Liability:CreditCard +500 | Asset:Checking -500 |
| Loan payment (principal) | Liability:Mortgage +800 | Asset:Checking -800 |
| Loan payment (interest) | Expense:Interest +200 | Asset:Checking -200 |
| Stock purchase | Asset:Brokerage +1000 | Asset:Checking -1000 |

### Journal Entries and Splits

A **journal entry** (also called a **transaction**) is the atomic unit of record. It contains:
- A header: date, description, reference number, status
- Two or more **line items** (also called postings, splits, or legs)

**Simple entry** (2 legs):
```
2026-03-15  "Grocery shopping"
  Expense:Groceries     +85.50   (debit)
  Asset:Checking        -85.50   (credit)
                        ------
  Sum:                    0.00   (balanced)
```

**Split entry** (3+ legs):
```
2026-03-15  "Paycheck"
  Asset:Checking       +3000.00  (debit: net pay deposited)
  Expense:Tax:Federal   +600.00  (debit: federal tax withheld)
  Expense:Tax:State     +200.00  (debit: state tax withheld)
  Income:Salary        -3800.00  (credit: gross pay)
                        -------
  Sum:                     0.00  (balanced)
```

### Trial Balance

A **trial balance** is the sum of all debit balances minus all credit balances across every account. If the books are correct, the trial balance is zero. In software, this is a critical integrity check:

```sql
SELECT COALESCE(SUM(amount), 0) AS trial_balance
FROM journal_lines;
-- Must always return 0.00
```

### Ledger Views

A **general ledger** shows all entries affecting a specific account, with running balance:

```
Account: Asset:Checking
Date        Description          Debit     Credit    Balance
2026-03-01  Opening Balance      5000.00             5000.00
2026-03-05  Salary               3000.00             8000.00
2026-03-10  Rent                           1500.00   6500.00
2026-03-15  Groceries                        85.50   6414.50
```

---

## 2. Database Schema Design

### Core Tables

```sql
-- ============================================================
-- CHART OF ACCOUNTS
-- ============================================================
CREATE TYPE account_type AS ENUM (
    'asset', 'liability', 'equity', 'income', 'expense'
);

CREATE TABLE accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    parent_id       UUID REFERENCES accounts(id),  -- hierarchical chart of accounts
    code            TEXT,                           -- optional: "1000", "2100", etc.
    name            TEXT NOT NULL,
    account_type    account_type NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD',    -- ISO 4217
    is_placeholder  BOOLEAN NOT NULL DEFAULT FALSE, -- grouping-only account (no direct postings)
    is_archived     BOOLEAN NOT NULL DEFAULT FALSE,
    metadata        JSONB NOT NULL DEFAULT '{}',    -- tags, institution, account number, etc.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT accounts_user_name_unique UNIQUE (user_id, name),
    CONSTRAINT accounts_user_code_unique UNIQUE (user_id, code)
);

CREATE INDEX idx_accounts_user_id ON accounts(user_id);
CREATE INDEX idx_accounts_parent_id ON accounts(parent_id);
CREATE INDEX idx_accounts_type ON accounts(user_id, account_type);

-- ============================================================
-- JOURNAL ENTRIES (transaction headers)
-- ============================================================
CREATE TYPE entry_status AS ENUM (
    'pending',    -- imported but unreviewed
    'cleared',    -- confirmed by user
    'reconciled', -- matched to bank statement
    'voided'      -- reversed (original preserved, reversal entry linked)
);

CREATE TABLE journal_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    date            DATE NOT NULL,
    description     TEXT NOT NULL,
    reference       TEXT,           -- check number, import reference, etc.
    status          entry_status NOT NULL DEFAULT 'cleared',
    voided_by       UUID REFERENCES journal_entries(id),  -- links to reversing entry
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- No updated_at: journal entries are immutable once created.
    -- Corrections are made by voiding + creating a new entry.

    CONSTRAINT journal_entries_not_self_void CHECK (voided_by != id)
);

CREATE INDEX idx_journal_entries_user_date ON journal_entries(user_id, date DESC);
CREATE INDEX idx_journal_entries_status ON journal_entries(user_id, status);

-- ============================================================
-- JOURNAL LINES (postings / splits / legs)
-- ============================================================
CREATE TABLE journal_lines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id        UUID NOT NULL REFERENCES journal_entries(id) ON DELETE RESTRICT,
    account_id      UUID NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    amount          NUMERIC(19, 4) NOT NULL,  -- positive = debit, negative = credit
    currency        TEXT NOT NULL DEFAULT 'USD',
    description     TEXT,                      -- line-level memo (optional)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT journal_lines_nonzero CHECK (amount != 0)
);

CREATE INDEX idx_journal_lines_entry_id ON journal_lines(entry_id);
CREATE INDEX idx_journal_lines_account_id ON journal_lines(account_id);
CREATE INDEX idx_journal_lines_account_date ON journal_lines(account_id, (
    SELECT date FROM journal_entries WHERE id = entry_id
));  -- Note: this functional index needs to be a covering index instead; see below.

-- ============================================================
-- BALANCE CONSTRAINT: Every journal entry must balance to zero
-- ============================================================
-- Option A: Enforced at application level (recommended for Go)
-- Option B: Deferred constraint trigger (shown below)

CREATE OR REPLACE FUNCTION check_entry_balance()
RETURNS TRIGGER AS $$
DECLARE
    entry_sum NUMERIC(19, 4);
BEGIN
    SELECT COALESCE(SUM(amount), 0) INTO entry_sum
    FROM journal_lines
    WHERE entry_id = NEW.entry_id;

    -- Only check when we might be done inserting lines
    -- This is called as a CONSTRAINT TRIGGER deferred to end of transaction
    IF entry_sum != 0 THEN
        RAISE EXCEPTION 'Journal entry % is unbalanced: sum = %', NEW.entry_id, entry_sum;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER trg_check_entry_balance
    AFTER INSERT OR UPDATE ON journal_lines
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION check_entry_balance();

-- ============================================================
-- ACCOUNT BALANCES (materialized for performance)
-- ============================================================
CREATE MATERIALIZED VIEW account_balances AS
SELECT
    jl.account_id,
    a.user_id,
    a.name AS account_name,
    a.account_type,
    a.currency,
    COALESCE(SUM(jl.amount), 0) AS balance,
    COUNT(jl.id) AS entry_count,
    MAX(je.date) AS last_activity
FROM journal_lines jl
JOIN accounts a ON a.id = jl.account_id
JOIN journal_entries je ON je.id = jl.entry_id
WHERE je.status != 'voided'
GROUP BY jl.account_id, a.user_id, a.name, a.account_type, a.currency;

CREATE UNIQUE INDEX idx_account_balances_pk ON account_balances(account_id);
CREATE INDEX idx_account_balances_user ON account_balances(user_id);

-- Refresh after batch operations:
-- REFRESH MATERIALIZED VIEW CONCURRENTLY account_balances;

-- For real-time balances (use this in queries, materialized view for dashboards):
CREATE OR REPLACE FUNCTION get_account_balance(
    p_account_id UUID,
    p_as_of_date DATE DEFAULT CURRENT_DATE
) RETURNS NUMERIC(19, 4) AS $$
    SELECT COALESCE(SUM(jl.amount), 0)
    FROM journal_lines jl
    JOIN journal_entries je ON je.id = jl.entry_id
    WHERE jl.account_id = p_account_id
      AND je.date <= p_as_of_date
      AND je.status != 'voided';
$$ LANGUAGE sql STABLE;
```

### Why NUMERIC(19, 4)?

- 19 total digits, 4 after the decimal point
- Supports values up to +/- 999,999,999,999,999.9999
- Sufficient for any personal finance amount including crypto fractional units
- PostgreSQL NUMERIC is arbitrary precision -- no floating point errors
- For most personal finance, NUMERIC(15, 2) suffices, but 19,4 gives headroom for multi-currency and investment lots

### Audit Trail / Immutability Pattern

The schema enforces immutability through several mechanisms:

1. **No UPDATE on journal_lines**: The application layer never issues UPDATE or DELETE on journal_lines. Corrections are made by creating a **reversing entry** (same amounts with opposite signs) and then creating the corrected entry.

2. **Voided status + voided_by**: When voiding an entry, the original is marked `voided` and a new reversing entry is created. The `voided_by` FK links them.

3. **No updated_at on journal_entries**: Deliberate omission. If you need to track metadata changes (like status transitions), use a separate audit log table.

4. **ON DELETE RESTRICT**: Foreign keys prevent deletion of accounts that have postings, or entries that have lines.

```sql
-- Example: Voiding a transaction
-- Step 1: Create the reversing entry
INSERT INTO journal_entries (user_id, date, description, reference, status)
VALUES ('user-uuid', '2026-03-20', 'VOID: Grocery shopping', 'VOID-OF-original-uuid', 'cleared')
RETURNING id;  -- returns 'reversal-uuid'

-- Step 2: Create reversed lines (negate all amounts)
INSERT INTO journal_lines (entry_id, account_id, amount, currency)
SELECT 'reversal-uuid', account_id, -amount, currency
FROM journal_lines
WHERE entry_id = 'original-uuid';

-- Step 3: Mark original as voided
UPDATE journal_entries
SET status = 'voided', voided_by = 'reversal-uuid'
WHERE id = 'original-uuid';
```

### Optimized Index for Ledger Queries

```sql
-- Composite index for the most common query: "show me all transactions
-- for account X ordered by date"
CREATE INDEX idx_ledger_view ON journal_lines(account_id)
    INCLUDE (entry_id, amount, currency);

-- Pair with an index on journal_entries for the join
CREATE INDEX idx_journal_entries_date ON journal_entries(id, date DESC, description);
```

---

## 3. Open-Source Implementations -- Patterns Worth Stealing

### hledger / Ledger CLI (Plain Text Accounting)

**Repository:** https://github.com/simonmichael/hledger (Haskell), https://github.com/ledger/ledger (C++)

**Data model:**
- A **transaction** has a date, description, and 2+ **postings**
- Each posting targets an **account** (hierarchical, colon-separated: `Assets:Bank:Checking`)
- Amounts are signed; the last posting can be inferred if it makes the transaction balance
- Account types inferred from top-level name (`Assets:`, `Liabilities:`, `Income:`, `Expenses:`, `Equity:`)
- Multi-currency: each posting carries its own commodity; exchange rates are recorded inline

**Patterns to steal:**
- **Hierarchical accounts via naming convention.** `Expenses:Food:Groceries` automatically rolls up into `Expenses:Food` which rolls up into `Expenses`. In a database, model this with `parent_id` and a `path` column (ltree or materialized path).
- **Inferred balancing posting.** For simple 2-leg entries, the UI can infer the second leg. Only require explicit amounts when there are 3+ legs.
- **Per-posting commodity.** Each journal_line has its own currency, enabling multi-currency entries natively.

### GnuCash

**Repository:** https://github.com/Gnucash/gnucash

**Data model (SQL backend):**
- `accounts` table: guid, name, account_type, commodity_guid (currency), parent_guid, code, description
- `transactions` table: guid, currency_guid, num (reference), post_date, enter_date, description
- `splits` table: guid, tx_guid, account_guid, memo, value_num, value_denom, quantity_num, quantity_denom

**Patterns to steal:**
- **Rational numbers for amounts.** GnuCash stores amounts as numerator/denominator pairs (e.g., 1050/100 = $10.50). This avoids all rounding issues. For PostgreSQL, NUMERIC(19,4) achieves the same goal more simply.
- **value vs quantity distinction.** `value` is the amount in the transaction's currency; `quantity` is the amount in the account's currency. This is critical for multi-currency and investment tracking (100 shares at $50 each: quantity=100, value=5000).
- **Separate transaction currency.** The transaction header has a currency, and each split has both a value (in transaction currency) and a quantity (in account currency). This cleanly models currency exchange.

### Firefly III

**Repository:** https://github.com/firefly-iii/firefly-iii (PHP/Laravel)

**Data model:**
- `accounts` table with types: asset, expense, revenue, liability, initial-balance, reconciliation
- `transaction_journals` table: the header (date, description, type)
- `transactions` table: the legs (journal_id, account_id, amount -- positive for destination, negative for source)
- `transaction_types`: withdrawal, deposit, transfer, opening-balance, reconciliation
- `transaction_currencies` with foreign_amount/foreign_currency support per transaction

**Patterns to steal:**
- **Transaction type as enum.** `withdrawal`, `deposit`, `transfer` simplify UI logic while the underlying double-entry stays pure.
- **Explicit "source" and "destination" accounts.** For simple 2-leg entries, the API accepts `source_account` and `destination_account` rather than raw debits/credits. The server constructs the balanced journal entry. This is much friendlier for personal finance UIs.
- **Foreign amount support.** Each transaction can optionally carry a `foreign_amount` + `foreign_currency`, enabling multi-currency without requiring a full currency conversion table for every entry.

### Akaunting

**Repository:** https://github.com/akaunting/akaunting (PHP/Laravel)

**Data model:**
- Uses the `akaunting/laravel-double-entry` package
- `accounts` with `type_id` mapping to the 5 standard types
- `transactions` table (simplified view for non-accountants)
- `journal_entries` + `journal_entry_items` for full double-entry under the hood
- Reconciliation system with statement matching

**Patterns to steal:**
- **Dual interface.** Simple transaction view for users who don't think in debits/credits; full journal entry view for power users. The same data powers both.
- **Account type metadata.** Each account type has a "normal balance" direction, enabling the system to automatically determine whether an amount is a debit or credit based on the account type.

### ERPNext Accounting Module

**Repository:** https://github.com/frappe/erpnext

**Data model:**
- `GL Entry` (General Ledger Entry): account, debit, credit, voucher_type, voucher_no
- Every business document (Invoice, Payment, Journal Entry) creates GL Entries
- `Account` with parent, account_type, root_type (Asset/Liability/Equity/Income/Expense)

**Patterns to steal:**
- **Voucher pattern.** The GL entry references a "voucher type" and "voucher number" -- meaning the same ledger stores entries from invoices, payments, manual journals, etc. This is extensible: when you add bank imports or recurring transactions later, they just generate GL entries.
- **Account hierarchy with root_type.** Even deeply nested accounts always know their root type (the 5 fundamentals), enabling instant balance sheet/income statement classification.

---

## 4. Go-Specific Patterns

### Domain Types

```go
package accounting

import (
    "time"

    "github.com/google/uuid"
    "github.com/shopspring/decimal"
)

// AccountType represents the five fundamental account types.
type AccountType string

const (
    AccountTypeAsset     AccountType = "asset"
    AccountTypeLiability AccountType = "liability"
    AccountTypeEquity    AccountType = "equity"
    AccountTypeIncome    AccountType = "income"
    AccountTypeExpense   AccountType = "expense"
)

// NormalBalance returns the sign convention for this account type.
// Positive = debit-normal, Negative = credit-normal.
func (t AccountType) NormalBalance() int {
    switch t {
    case AccountTypeAsset, AccountTypeExpense:
        return 1 // debit-normal: positive amounts increase balance
    case AccountTypeLiability, AccountTypeEquity, AccountTypeIncome:
        return -1 // credit-normal: negative amounts increase balance
    default:
        return 0
    }
}

// Account represents a node in the chart of accounts.
type Account struct {
    ID            uuid.UUID   `json:"id" db:"id"`
    UserID        uuid.UUID   `json:"user_id" db:"user_id"`
    ParentID      *uuid.UUID  `json:"parent_id,omitempty" db:"parent_id"`
    Code          string      `json:"code,omitempty" db:"code"`
    Name          string      `json:"name" db:"name"`
    AccountType   AccountType `json:"account_type" db:"account_type"`
    Currency      string      `json:"currency" db:"currency"`
    IsPlaceholder bool        `json:"is_placeholder" db:"is_placeholder"`
    IsArchived    bool        `json:"is_archived" db:"is_archived"`
    Metadata      JSONMap     `json:"metadata" db:"metadata"`
    CreatedAt     time.Time   `json:"created_at" db:"created_at"`
    UpdatedAt     time.Time   `json:"updated_at" db:"updated_at"`
}

// EntryStatus represents the lifecycle of a journal entry.
type EntryStatus string

const (
    EntryStatusPending    EntryStatus = "pending"
    EntryStatusCleared    EntryStatus = "cleared"
    EntryStatusReconciled EntryStatus = "reconciled"
    EntryStatusVoided     EntryStatus = "voided"
)

// JournalEntry is the header for a balanced set of postings.
type JournalEntry struct {
    ID          uuid.UUID   `json:"id" db:"id"`
    UserID      uuid.UUID   `json:"user_id" db:"user_id"`
    Date        time.Time   `json:"date" db:"date"`
    Description string      `json:"description" db:"description"`
    Reference   string      `json:"reference,omitempty" db:"reference"`
    Status      EntryStatus `json:"status" db:"status"`
    VoidedBy    *uuid.UUID  `json:"voided_by,omitempty" db:"voided_by"`
    Metadata    JSONMap     `json:"metadata" db:"metadata"`
    CreatedAt   time.Time   `json:"created_at" db:"created_at"`
    Lines       []JournalLine `json:"lines" db:"-"` // loaded eagerly or via separate query
}

// JournalLine is a single posting within a journal entry.
type JournalLine struct {
    ID          uuid.UUID       `json:"id" db:"id"`
    EntryID     uuid.UUID       `json:"entry_id" db:"entry_id"`
    AccountID   uuid.UUID       `json:"account_id" db:"account_id"`
    Amount      decimal.Decimal `json:"amount" db:"amount"`
    Currency    string          `json:"currency" db:"currency"`
    Description string          `json:"description,omitempty" db:"description"`
    CreatedAt   time.Time       `json:"created_at" db:"created_at"`
}

// Validate checks that the journal entry is balanced and has at least 2 lines.
func (je *JournalEntry) Validate() error {
    if len(je.Lines) < 2 {
        return ErrTooFewLines
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

### Decimal Handling: shopspring/decimal

**Use `github.com/shopspring/decimal`.** It is the de facto standard for monetary arithmetic in Go.

Why not alternatives:
- `float64`: **Never** use floats for money. 0.1 + 0.2 != 0.3.
- `int64` cents: Works for single-currency, but breaks down with multi-currency, fractional shares, crypto (8+ decimal places), and exchange rate arithmetic.
- `cockroachdb/apd`: More powerful (arbitrary precision), but heavier. Good if you need configurable rounding modes. Overkill for personal finance.

```go
import "github.com/shopspring/decimal"

// Safe monetary arithmetic
price := decimal.NewFromString("19.99")
qty := decimal.NewFromInt(3)
total := price.Mul(qty) // 59.97 exactly

// Rounding for display
total.StringFixed(2) // "59.97"

// Comparison
total.Equal(decimal.NewFromFloat(59.97)) // true

// Database scanning -- shopspring/decimal implements sql.Scanner and driver.Valuer
// so it works directly with database/sql and pgx.
```

### Repository Interface (Clean Architecture)

```go
package accounting

import (
    "context"

    "github.com/google/uuid"
    "github.com/shopspring/decimal"
)

// AccountRepository manages the chart of accounts.
type AccountRepository interface {
    Create(ctx context.Context, account *Account) error
    GetByID(ctx context.Context, userID, accountID uuid.UUID) (*Account, error)
    List(ctx context.Context, userID uuid.UUID, filter AccountFilter) ([]Account, error)
    Update(ctx context.Context, account *Account) error
    Archive(ctx context.Context, userID, accountID uuid.UUID) error
    GetBalance(ctx context.Context, accountID uuid.UUID, asOf time.Time) (decimal.Decimal, error)
}

// JournalRepository manages journal entries (the write side).
type JournalRepository interface {
    // CreateEntry inserts the header and all lines in a single DB transaction.
    // It validates that the entry is balanced before persisting.
    CreateEntry(ctx context.Context, entry *JournalEntry) error

    // VoidEntry creates a reversing entry and marks the original as voided.
    // Both operations happen in a single DB transaction.
    VoidEntry(ctx context.Context, userID, entryID uuid.UUID, reason string) error

    GetEntryByID(ctx context.Context, userID, entryID uuid.UUID) (*JournalEntry, error)
    ListEntries(ctx context.Context, userID uuid.UUID, filter EntryFilter) ([]JournalEntry, error)
}

// LedgerReader provides read-model queries (the read side).
type LedgerReader interface {
    // AccountLedger returns all postings for an account, ordered by date, with running balance.
    AccountLedger(ctx context.Context, accountID uuid.UUID, filter LedgerFilter) ([]LedgerRow, error)

    // TrialBalance returns the sum of all balances; must equal zero.
    TrialBalance(ctx context.Context, userID uuid.UUID, asOf time.Time) ([]TrialBalanceRow, error)

    // BalanceSheet returns asset, liability, equity balances grouped by account.
    BalanceSheet(ctx context.Context, userID uuid.UUID, asOf time.Time) (*BalanceSheet, error)

    // IncomeStatement returns income and expense totals for a date range.
    IncomeStatement(ctx context.Context, userID uuid.UUID, from, to time.Time) (*IncomeStatement, error)
}

// LedgerRow is a single row in the account ledger view.
type LedgerRow struct {
    Date           time.Time       `json:"date"`
    EntryID        uuid.UUID       `json:"entry_id"`
    Description    string          `json:"description"`
    Amount         decimal.Decimal `json:"amount"`
    RunningBalance decimal.Decimal `json:"running_balance"`
}

// TrialBalanceRow is one account's contribution to the trial balance.
type TrialBalanceRow struct {
    AccountID   uuid.UUID       `json:"account_id"`
    AccountName string          `json:"account_name"`
    AccountType AccountType     `json:"account_type"`
    Debit       decimal.Decimal `json:"debit"`
    Credit      decimal.Decimal `json:"credit"`
}
```

### Transaction Safety Pattern

```go
// CreateEntry demonstrates the critical pattern: header + all lines in one DB transaction.
func (r *PostgresJournalRepo) CreateEntry(ctx context.Context, entry *JournalEntry) error {
    // 1. Validate in-memory first (fail fast, no DB round-trip)
    if err := entry.Validate(); err != nil {
        return fmt.Errorf("validation failed: %w", err)
    }

    // 2. Execute everything in a single database transaction
    tx, err := r.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
    if err != nil {
        return fmt.Errorf("begin tx: %w", err)
    }
    defer tx.Rollback() // no-op if committed

    // 3. Insert journal entry header
    _, err = tx.ExecContext(ctx, `
        INSERT INTO journal_entries (id, user_id, date, description, reference, status, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7)`,
        entry.ID, entry.UserID, entry.Date, entry.Description,
        entry.Reference, entry.Status, entry.Metadata,
    )
    if err != nil {
        return fmt.Errorf("insert entry: %w", err)
    }

    // 4. Insert all lines
    for _, line := range entry.Lines {
        _, err = tx.ExecContext(ctx, `
            INSERT INTO journal_lines (id, entry_id, account_id, amount, currency, description)
            VALUES ($1, $2, $3, $4, $5, $6)`,
            line.ID, entry.ID, line.AccountID, line.Amount,
            line.Currency, line.Description,
        )
        if err != nil {
            return fmt.Errorf("insert line: %w", err)
        }
    }

    // 5. Verify balance (defense in depth -- application already checked,
    //    but verify in DB in case of concurrent modification)
    var sum decimal.Decimal
    err = tx.QueryRowContext(ctx, `
        SELECT COALESCE(SUM(amount), 0) FROM journal_lines WHERE entry_id = $1`,
        entry.ID,
    ).Scan(&sum)
    if err != nil {
        return fmt.Errorf("verify balance: %w", err)
    }
    if !sum.IsZero() {
        return fmt.Errorf("entry unbalanced in DB: sum=%s", sum.String())
    }

    // 6. Commit
    if err := tx.Commit(); err != nil {
        return fmt.Errorf("commit: %w", err)
    }

    return nil
}
```

---

## 5. PostgreSQL-Specific Patterns

### Money Storage: NUMERIC, Never FLOAT

```sql
-- CORRECT: exact decimal arithmetic
amount NUMERIC(19, 4) NOT NULL

-- WRONG: floating point errors accumulate
amount DOUBLE PRECISION  -- DO NOT USE
amount REAL              -- DO NOT USE
amount MONEY             -- DO NOT USE (locale-dependent, limited precision)
```

PostgreSQL's `NUMERIC` type stores values as exact decimal numbers with no rounding errors. The `MONEY` type, despite its name, is locale-dependent and problematic -- avoid it.

### CHECK Constraints for Data Integrity

```sql
-- Journal lines must have non-zero amounts
ALTER TABLE journal_lines ADD CONSTRAINT chk_nonzero_amount CHECK (amount != 0);

-- Account types must be valid
ALTER TABLE accounts ADD CONSTRAINT chk_account_type
    CHECK (account_type IN ('asset', 'liability', 'equity', 'income', 'expense'));

-- Currency must be 3-character ISO 4217
ALTER TABLE accounts ADD CONSTRAINT chk_currency_format CHECK (currency ~ '^[A-Z]{3}$');
ALTER TABLE journal_lines ADD CONSTRAINT chk_line_currency_format CHECK (currency ~ '^[A-Z]{3}$');

-- Dates must be reasonable (not in far future)
ALTER TABLE journal_entries ADD CONSTRAINT chk_date_reasonable
    CHECK (date <= CURRENT_DATE + INTERVAL '1 day');
```

### Deferred Constraint Trigger for Balance Enforcement

The trigger shown in section 2 uses `DEFERRABLE INITIALLY DEFERRED`, meaning PostgreSQL checks the constraint at COMMIT time, not at each INSERT. This is essential because you insert lines one at a time but they only balance as a complete set.

### Materialized View for Account Balances

```sql
-- Fast dashboard queries
CREATE MATERIALIZED VIEW account_balances AS
SELECT
    jl.account_id,
    a.user_id,
    a.name,
    a.account_type,
    a.currency,
    SUM(jl.amount) FILTER (WHERE jl.amount > 0) AS total_debits,
    SUM(jl.amount) FILTER (WHERE jl.amount < 0) AS total_credits,
    SUM(jl.amount) AS balance,
    COUNT(*) AS posting_count,
    MAX(je.date) AS last_activity
FROM journal_lines jl
JOIN accounts a ON a.id = jl.account_id
JOIN journal_entries je ON je.id = jl.entry_id
WHERE je.status != 'voided'
GROUP BY jl.account_id, a.user_id, a.name, a.account_type, a.currency;

CREATE UNIQUE INDEX ON account_balances(account_id);
CREATE INDEX ON account_balances(user_id);

-- Refresh strategy: call CONCURRENTLY after each write, or on a schedule
-- REFRESH MATERIALIZED VIEW CONCURRENTLY account_balances;
```

**When to use materialized view vs live query:**
- **Dashboard / net worth / balance overview:** Materialized view (refreshed after writes or on 30s interval)
- **Single account balance:** Live query with `SUM(amount)` -- fast with proper index
- **Ledger view with running balance:** Live query with window function

### Running Balance via Window Function

```sql
-- Ledger view for a single account with running balance
SELECT
    je.date,
    je.id AS entry_id,
    je.description,
    jl.amount,
    SUM(jl.amount) OVER (ORDER BY je.date, je.created_at) AS running_balance
FROM journal_lines jl
JOIN journal_entries je ON je.id = jl.entry_id
WHERE jl.account_id = $1
  AND je.status != 'voided'
ORDER BY je.date, je.created_at;
```

### Indexing Strategy for Large Volumes

```sql
-- Primary access pattern: "all postings for account X"
CREATE INDEX idx_lines_account ON journal_lines(account_id);

-- With covering columns to avoid table lookups
CREATE INDEX idx_lines_account_covering ON journal_lines(account_id)
    INCLUDE (entry_id, amount, currency);

-- Date-range queries: "transactions for user X in March 2026"
CREATE INDEX idx_entries_user_date ON journal_entries(user_id, date DESC);

-- Status filtering: "all pending transactions"
CREATE INDEX idx_entries_user_status ON journal_entries(user_id, status)
    WHERE status = 'pending';  -- partial index for common filter

-- Full-text search on descriptions
CREATE INDEX idx_entries_description_trgm ON journal_entries
    USING gin (description gin_trgm_ops);
-- Requires: CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Trial balance (aggregate over all lines for a user)
-- No special index needed beyond idx_lines_account -- the join through
-- journal_entries for user filtering is the bottleneck.
-- For users with >100k transactions, consider partitioning journal_lines by date range.
```

### Partitioning for Scale (Future)

```sql
-- If a single user accumulates millions of transactions,
-- partition journal_entries by date range:
CREATE TABLE journal_entries (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    date DATE NOT NULL,
    -- ... other columns ...
) PARTITION BY RANGE (date);

CREATE TABLE journal_entries_2026 PARTITION OF journal_entries
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

-- Similarly for journal_lines (partition by created_at or by entry date via FK)
```

---

## 6. API Design

### Resource Hierarchy

```
/api/v1/accounts                          # Chart of accounts
/api/v1/accounts/{id}
/api/v1/accounts/{id}/ledger              # Ledger view for one account

/api/v1/journal-entries                   # Journal entries (transactions)
/api/v1/journal-entries/{id}
/api/v1/journal-entries/{id}/void         # Void an entry

/api/v1/transactions                      # Simplified transaction API (sugar over journal entries)

/api/v1/reports/trial-balance
/api/v1/reports/balance-sheet
/api/v1/reports/income-statement
```

### Accounts API

```
POST   /api/v1/accounts          Create account
GET    /api/v1/accounts          List accounts (with balance summary)
GET    /api/v1/accounts/{id}     Get account details + balance
PATCH  /api/v1/accounts/{id}     Update account metadata (name, code, parent)
DELETE /api/v1/accounts/{id}     Archive account (soft delete; fails if has postings)
GET    /api/v1/accounts/{id}/ledger   Account ledger with running balance
```

**Create Account request:**
```json
{
  "name": "Checking Account",
  "account_type": "asset",
  "currency": "USD",
  "parent_id": null,
  "code": "1010",
  "metadata": {
    "institution": "Chase",
    "last_four": "4242"
  }
}
```

**List Accounts response (includes balances):**
```json
{
  "accounts": [
    {
      "id": "a1b2c3d4-...",
      "name": "Checking Account",
      "account_type": "asset",
      "currency": "USD",
      "balance": "6414.50",
      "parent_id": null,
      "children": [
        {
          "id": "e5f6g7h8-...",
          "name": "Emergency Fund",
          "account_type": "asset",
          "balance": "10000.00"
        }
      ]
    }
  ]
}
```

### Journal Entries API (Power User / Full Control)

```
POST   /api/v1/journal-entries           Create balanced entry
GET    /api/v1/journal-entries           List entries (paginated, filterable)
GET    /api/v1/journal-entries/{id}      Get entry with all lines
POST   /api/v1/journal-entries/{id}/void Void entry (creates reversal)
```

**Create Journal Entry request:**
```json
{
  "date": "2026-03-15",
  "description": "Monthly paycheck",
  "lines": [
    { "account_id": "checking-uuid", "amount": "3000.00" },
    { "account_id": "federal-tax-uuid", "amount": "600.00" },
    { "account_id": "state-tax-uuid", "amount": "200.00" },
    { "account_id": "salary-uuid", "amount": "-3800.00" }
  ]
}
```

The server validates that `SUM(lines.amount) == 0` before persisting.

**Response:**
```json
{
  "id": "entry-uuid",
  "date": "2026-03-15",
  "description": "Monthly paycheck",
  "status": "cleared",
  "lines": [
    {
      "id": "line-uuid-1",
      "account_id": "checking-uuid",
      "account_name": "Checking Account",
      "amount": "3000.00",
      "currency": "USD"
    },
    {
      "id": "line-uuid-2",
      "account_id": "salary-uuid",
      "account_name": "Salary",
      "amount": "-3800.00",
      "currency": "USD"
    }
  ]
}
```

### Simplified Transaction API (Consumer-Friendly)

Most personal finance users don't think in debits and credits. Provide a **simplified transaction API** that abstracts the double-entry mechanics.

```
POST   /api/v1/transactions              Create a simple transaction
GET    /api/v1/transactions              List transactions (for an account)
```

**Create Transaction request (simplified):**
```json
{
  "type": "expense",
  "date": "2026-03-15",
  "description": "Grocery shopping",
  "amount": "85.50",
  "from_account_id": "checking-uuid",
  "to_account_id": "groceries-uuid",
  "currency": "USD"
}
```

The server converts this into a balanced journal entry:
- `Expense:Groceries +85.50` (debit)
- `Asset:Checking -85.50` (credit)

**Transaction types and their mapping:**

| Simplified Type | From Account Type | To Account Type | Example |
|----------------|------------------|----------------|---------|
| `expense` | Asset (source) | Expense (destination) | Buying groceries |
| `income` | Income (source) | Asset (destination) | Receiving salary |
| `transfer` | Asset (source) | Asset (destination) | Checking to Savings |
| `payment` | Asset (source) | Liability (destination) | Paying credit card |
| `charge` | Liability (source) | Expense (destination) | Credit card purchase |

**Important design note:** The simplified API is a **presentation layer** -- it creates real journal entries underneath. A transaction created via `/transactions` is visible in `/journal-entries` and vice versa.

### Transfer Between Accounts

```json
POST /api/v1/transactions
{
  "type": "transfer",
  "date": "2026-03-15",
  "description": "Monthly savings transfer",
  "amount": "500.00",
  "from_account_id": "checking-uuid",
  "to_account_id": "savings-uuid"
}
```

Becomes journal entry:
```
Asset:Savings   +500.00
Asset:Checking  -500.00
```

### Reports API

```
GET /api/v1/reports/trial-balance?as_of=2026-03-20
GET /api/v1/reports/balance-sheet?as_of=2026-03-20
GET /api/v1/reports/income-statement?from=2026-03-01&to=2026-03-31
GET /api/v1/reports/net-worth?as_of=2026-03-20
GET /api/v1/reports/cash-flow?from=2026-03-01&to=2026-03-31
```

**Balance Sheet response:**
```json
{
  "as_of": "2026-03-20",
  "assets": {
    "total": "16414.50",
    "accounts": [
      { "name": "Checking", "balance": "6414.50" },
      { "name": "Savings", "balance": "10000.00" }
    ]
  },
  "liabilities": {
    "total": "1200.00",
    "accounts": [
      { "name": "Credit Card", "balance": "1200.00" }
    ]
  },
  "equity": {
    "total": "15214.50"
  }
}
```

---

## 7. Multi-Currency Architecture

### Design Approach

Follow GnuCash's proven model of **value vs quantity** at the line level:

```sql
ALTER TABLE journal_lines ADD COLUMN
    foreign_amount   NUMERIC(19, 4),         -- amount in foreign currency (nullable)
    foreign_currency TEXT;                     -- ISO 4217 code (nullable)

-- When foreign_amount is set, `amount` is in the journal entry's base currency
-- and `foreign_amount` is in the foreign currency.

-- Exchange rate is implicit: amount / foreign_amount
```

**Example: Buying EUR with USD**

```
2026-03-15  "Buy euros for trip"
  Asset:EUR_Wallet     +850.00 EUR  (foreign_amount=850.00, foreign_currency=EUR)
                       +935.00 USD  (amount=935.00, the USD equivalent)
  Asset:Checking       -935.00 USD  (amount=-935.00)
```

The journal entry balances in the base currency (USD): 935.00 + (-935.00) = 0.

### Exchange Rate Table (Optional)

```sql
CREATE TABLE exchange_rates (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    base        TEXT NOT NULL,       -- 'USD'
    quote       TEXT NOT NULL,       -- 'EUR'
    rate        NUMERIC(19, 8) NOT NULL,
    date        DATE NOT NULL,
    source      TEXT NOT NULL,       -- 'manual', 'ecb', 'openexchangerates'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(base, quote, date, source)
);

CREATE INDEX idx_exchange_rates_lookup ON exchange_rates(base, quote, date DESC);
```

### Go Types for Multi-Currency

```go
type JournalLine struct {
    ID              uuid.UUID        `json:"id"`
    EntryID         uuid.UUID        `json:"entry_id"`
    AccountID       uuid.UUID        `json:"account_id"`
    Amount          decimal.Decimal  `json:"amount"`           // in entry's base currency
    Currency        string           `json:"currency"`
    ForeignAmount   *decimal.Decimal `json:"foreign_amount,omitempty"`
    ForeignCurrency *string          `json:"foreign_currency,omitempty"`
    Description     string           `json:"description,omitempty"`
}
```

### Recommendation for This Project

Start with single-currency (USD). The schema already accommodates multi-currency via the `currency` column on accounts and lines. Add `foreign_amount`/`foreign_currency` columns when multi-currency becomes a priority. The exchange_rates table is only needed if you want automatic conversion for reporting.

---

## 8. Verdict and Recommendations

### Double-Entry: Yes

The incremental cost of double-entry over a simple ledger is:
- **One additional table** (journal_lines vs putting amount directly on transactions)
- **One validation rule** (lines must sum to zero)
- **Slightly more complex writes** (insert header + N lines in a transaction)

The benefits are substantial:
- **Transfers are native.** No special "transfer" table or linking transactions.
- **Balances are derived, not stored.** No need to maintain a mutable `balance` column that can drift.
- **Trial balance as integrity check.** `SUM(all amounts) = 0` catches bugs instantly.
- **Multi-currency falls out naturally.** Each leg can have its own currency.
- **Reporting is built-in.** Balance sheet and income statement are just queries over the same data.
- **Audit trail is structural.** Immutable entries + reversals = complete history.

### Recommended Schema Summary

| Table | Purpose | Key Columns |
|-------|---------|------------|
| `accounts` | Chart of accounts (per user) | id, user_id, parent_id, name, account_type, currency |
| `journal_entries` | Transaction headers (immutable) | id, user_id, date, description, status |
| `journal_lines` | Balanced postings (immutable) | id, entry_id, account_id, amount, currency |
| `account_balances` | Materialized view for dashboards | account_id, balance, last_activity |
| `exchange_rates` | Optional: multi-currency support | base, quote, rate, date |

### Impact on Existing Feature Docs

The existing `account-management` FEATURE.md describes accounts with a mutable `balance` column. Under double-entry, the balance is **computed** from journal_lines, not stored on the account. The account table becomes the **chart of accounts** (metadata only), and balances are derived.

The existing `transaction-engine` FEATURE.md describes transactions with an `amount` column directly. Under double-entry, a "transaction" becomes a journal_entry + journal_lines pair. The simplified transaction API preserves the same user experience while storing proper double-entry data underneath.

### Key Libraries

| Library | Purpose | URL |
|---------|---------|-----|
| `shopspring/decimal` | Exact decimal arithmetic | https://github.com/shopspring/decimal |
| `google/uuid` | UUID generation | https://github.com/google/uuid |
| `jackc/pgx` | PostgreSQL driver (preferred over lib/pq) | https://github.com/jackc/pgx |
| `golang-migrate/migrate` | Database migrations | https://github.com/golang-migrate/migrate |

### Open-Source References

| Project | Language | What to Study | URL |
|---------|----------|--------------|-----|
| hledger | Haskell | Account hierarchy, plain text format, reporting | https://github.com/simonmichael/hledger |
| GnuCash | C/C++ | Value vs quantity (multi-currency), splits model | https://github.com/Gnucash/gnucash |
| Firefly III | PHP | Source/destination UX pattern, foreign amounts | https://github.com/firefly-iii/firefly-iii |
| Akaunting | PHP | Dual interface (simple + double-entry) | https://github.com/akaunting/akaunting |
| ERPNext | Python | Voucher pattern, GL entry model | https://github.com/frappe/erpnext |
| Ledger CLI | C++ | Reference accounting engine, multi-commodity | https://github.com/ledger/ledger |
| Beancount | Python | Double-entry with explicit balance assertions | https://github.com/beancount/beancount |
| medici | Node.js | MongoDB double-entry ledger (simpler model) | https://github.com/flash-oss/medici |
| go-finance | Go | Go accounting primitives | https://github.com/alpeb/go-finance |

### Recommended Next Steps

1. **Resolve:** Accept double-entry as the accounting model for this platform
2. **Update:** Revise `account-management` FEATURE.md to reflect chart-of-accounts model (no mutable balance column)
3. **Update:** Revise `transaction-engine` FEATURE.md to use journal entry + lines model
4. **Decide:** Multi-currency as day-one schema columns (nullable) vs v2 migration
5. **Decide:** Whether to expose both journal-entry API and simplified transaction API, or simplified only
6. **Implement:** Database migrations for core three tables (accounts, journal_entries, journal_lines)

---
*Research completed: 2026-03-20*
