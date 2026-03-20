# Research: Household/Family Finance Management Architecture

**Context:** Personal finance platform (Go + PostgreSQL + Next.js, multi-tenant SaaS)
**Date:** 2026-03-20
**Status:** Research complete, ready for shaping

---

## 1. What Is a "Household" in Personal Finance Software?

A household is a group of people who share some degree of financial visibility and management. This is distinct from a single-user account in several critical ways:

- **Shared financial context**: Multiple people see the same accounts, transactions, budgets, and net worth figures
- **Mixed ownership**: Some financial accounts belong to the household (joint checking), some are personal (individual credit card)
- **Role-based access**: Not everyone has equal power -- one person may own the household, others may just view
- **Privacy boundaries**: A member may want their personal spending visible only to themselves while still contributing to household budget tracking

### Real-World Household Structures

| Structure | Example | Implications |
|-----------|---------|-------------|
| Married couple, fully merged | Joint accounts, shared budgets | Nearly all accounts shared, minimal privacy needs |
| Couple, partially merged | Joint checking + personal cards | Need clear personal vs shared boundaries |
| Roommates | Split rent/utilities only | Minimal sharing, expense splitting is primary |
| Parent + adult child | Oversight/mentoring | Asymmetric roles, viewer access for parent |
| Multi-generational family | Complex shared expenses | Multiple sub-groups, layered permissions |

---

## 2. How Existing Apps Handle Households

### Monarch Money
- **Collaborative by default**: Designed for couples/families from the ground up
- **Single household model**: One subscription covers the whole household (unlimited members)
- **Shared dashboard**: All linked accounts visible to all household members
- **No privacy tiers within household**: Once you are in, you see everything -- this is a deliberate simplicity choice but a limitation for some users
- **Invitation flow**: Owner invites by email, invitee creates account or links existing
- **Account linking**: Each member links their own bank accounts via Plaid; all flow into the shared household view
- **Categories and budgets**: Household-level (not per-person)
- **Limitation**: No concept of "my private account that the household cannot see"

### YNAB (You Need A Budget)
- **Budget-centric, not household-centric**: The core entity is a "budget," not a household
- **Shared access**: A budget can be shared between multiple users (each with their own login)
- **Multiple budgets**: A user can have multiple budgets (e.g., "Family Budget" + "Side Business")
- **No role differentiation**: All shared users have full access (no viewer/admin distinction)
- **No personal-vs-shared concept**: Every account in a budget is visible to all budget members
- **Implication for us**: YNAB's "budget as the collaboration unit" is simpler but less flexible than a household model

### Copilot (iOS)
- **Single-user focused**: No native multi-user/household support as of early 2026
- **Workaround**: Shared device or shared login (not secure, not recommended)
- **Lesson**: Being single-user-only is a significant limitation that users complain about

### Splitwise
- **Expense splitting only**: Not a full finance platform
- **Group model**: Users create groups (household, trip, project) and log shared expenses
- **Balance tracking**: Tracks who owes whom within a group
- **Settlements**: Simplifies debts (A owes B, B owes C becomes A owes C)
- **No budgeting, accounts, or net worth**: Pure expense splitting
- **Lesson**: Excellent UX for the "split" use case; worth borrowing the settlement algorithm

### Toshl Finance
- **Collaborative features**: Supports sharing finances between partners
- **Connection model**: Two users "connect" their accounts to see combined view
- **Income/expense merging**: Combined view of all connected users' data
- **Limited roles**: No granular permissions

### Key Takeaways from Market Analysis

| Decision Point | Market Consensus | Our Recommendation |
|---------------|-----------------|-------------------|
| Collaboration unit | Household/budget | **Household** (more intuitive than "budget") |
| Privacy within household | Most apps: none | **Support personal + shared accounts** (differentiator) |
| Role granularity | Most apps: all-or-nothing | **Owner/admin/member/viewer** (needed for families) |
| Multiple households | Rare | **Support it** (user may be in couple household + roommate group) |
| Expense splitting | Splitwise-only or absent | **Include basic splitting** (common household need) |

---

## 3. Multi-Tenant + Household Data Model

### Core Entities and Their Relationships

```
                        ┌──────────────┐
                        │     User     │
                        │  (tenant)    │
                        └──────┬───────┘
                               │
                    ┌──────────┼──────────┐
                    │          │          │
              ┌─────▼────┐    │    ┌─────▼─────┐
              │ Personal │    │    │ Personal  │
              │ Accounts │    │    │ Budgets   │
              └──────────┘    │    └───────────┘
                              │
                     ┌────────▼────────┐
                     │ household_members│
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │   Household     │
                     └────────┬────────┘
                              │
               ┌──────────────┼──────────────┐
               │              │              │
        ┌──────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
        │  Household  │ │Household │ │  Household  │
        │  Accounts   │ │ Budgets  │ │  Categories │
        └─────────────┘ └──────────┘ └─────────────┘
```

### The Dual-Scope Model

Every financial entity belongs to exactly one of two scopes:

1. **User scope (personal)**: Owned by a single user, invisible to household members unless explicitly shared
2. **Household scope (shared)**: Owned by a household, visible to all household members per their role

This is the critical architectural decision. The alternatives and why we recommend the dual-scope approach:

| Approach | Pros | Cons |
|----------|------|------|
| **A: Everything is household-scoped** (Monarch) | Simple queries, simple permissions | No privacy, single users need a "household of one" |
| **B: Everything is user-scoped, shared via links** | Maximum privacy | Complex sharing logic, hard to have "household budget" |
| **C: Dual scope (personal + household)** | Privacy + collaboration | Two query paths, more complex schema |

**Recommendation: Approach C (Dual Scope)** with the simplification that a solo user automatically gets a "personal household" (household of one) so that the household abstraction is always present.

### Account Ownership Examples

| Account | Owner | Visible To | Editable By |
|---------|-------|-----------|-------------|
| "My Personal Visa" | User (Arnold) | Arnold only | Arnold only |
| "Joint Checking" | Household (Smith Family) | All household members | Owner + Admin |
| "Household Savings" | Household (Smith Family) | All household members | Owner + Admin |
| "Arnold's 401k" | User (Arnold), shared to household | All household members (read-only) | Arnold only |

The fourth row shows a hybrid: a personal account that the user has opted to share with the household for visibility (e.g., net worth calculations) but not for editing.

---

## 4. Database Schema Design

### Core Tables

```sql
-- ============================================================
-- USERS
-- ============================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    avatar_url      TEXT,
    email_verified  BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ  -- soft delete
);

CREATE INDEX idx_users_email ON users (email) WHERE deleted_at IS NULL;

-- ============================================================
-- HOUSEHOLDS
-- ============================================================
CREATE TABLE households (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,           -- "Smith Family", "Apt 4B Roommates"
    currency        TEXT NOT NULL DEFAULT 'USD',  -- default currency for household
    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

-- ============================================================
-- HOUSEHOLD MEMBERS
-- ============================================================
CREATE TYPE household_role AS ENUM ('owner', 'admin', 'member', 'viewer');
CREATE TYPE invitation_status AS ENUM ('pending', 'accepted', 'declined', 'revoked');

CREATE TABLE household_members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id    UUID NOT NULL REFERENCES households(id),
    user_id         UUID REFERENCES users(id),          -- NULL until invitation accepted
    invited_email   TEXT NOT NULL,                       -- email used for invitation
    role            household_role NOT NULL DEFAULT 'member',
    status          invitation_status NOT NULL DEFAULT 'pending',
    invited_by      UUID NOT NULL REFERENCES users(id),
    invited_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    accepted_at     TIMESTAMPTZ,
    declined_at     TIMESTAMPTZ,
    removed_at      TIMESTAMPTZ,

    UNIQUE (household_id, invited_email)
);

CREATE INDEX idx_hm_household ON household_members (household_id) WHERE removed_at IS NULL;
CREATE INDEX idx_hm_user ON household_members (user_id) WHERE removed_at IS NULL AND status = 'accepted';
CREATE INDEX idx_hm_pending ON household_members (invited_email) WHERE status = 'pending';

-- ============================================================
-- ACCOUNTS (dual-scope: personal OR household)
-- ============================================================
CREATE TYPE account_type AS ENUM (
    'checking', 'savings', 'credit_card', 'loan',
    'investment', 'cash', 'other'
);

CREATE TYPE account_scope AS ENUM ('personal', 'household');

CREATE TABLE accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Ownership: exactly one of these is set based on scope
    scope           account_scope NOT NULL,
    user_id         UUID REFERENCES users(id),       -- set when scope = 'personal'
    household_id    UUID REFERENCES households(id),   -- set when scope = 'household'

    name            TEXT NOT NULL,
    account_type    account_type NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD',
    balance         BIGINT NOT NULL DEFAULT 0,  -- stored in minor units (cents)
    is_asset        BOOLEAN NOT NULL DEFAULT true,  -- true = asset, false = liability

    -- Sharing: personal accounts can be shared to a household for visibility
    shared_to_household_id  UUID REFERENCES households(id),
    shared_visibility       TEXT CHECK (shared_visibility IN ('none', 'balance_only', 'full')),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,

    -- Constraints
    CONSTRAINT chk_scope_user CHECK (
        (scope = 'personal' AND user_id IS NOT NULL AND household_id IS NULL) OR
        (scope = 'household' AND household_id IS NOT NULL AND user_id IS NULL)
    ),
    CONSTRAINT chk_shared_visibility CHECK (
        (shared_to_household_id IS NULL AND shared_visibility IS NULL) OR
        (shared_to_household_id IS NOT NULL AND shared_visibility IS NOT NULL)
    )
);

CREATE INDEX idx_accounts_user ON accounts (user_id) WHERE deleted_at IS NULL AND scope = 'personal';
CREATE INDEX idx_accounts_household ON accounts (household_id) WHERE deleted_at IS NULL AND scope = 'household';
CREATE INDEX idx_accounts_shared ON accounts (shared_to_household_id) WHERE deleted_at IS NULL AND shared_to_household_id IS NOT NULL;

-- ============================================================
-- CATEGORIES (dual-scope)
-- ============================================================
CREATE TABLE categories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    scope           account_scope NOT NULL,  -- reuse the enum: 'personal' or 'household'
    user_id         UUID REFERENCES users(id),
    household_id    UUID REFERENCES households(id),

    name            TEXT NOT NULL,
    parent_id       UUID REFERENCES categories(id),
    icon            TEXT,
    color           TEXT,
    sort_order      INT NOT NULL DEFAULT 0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,

    CONSTRAINT chk_category_scope CHECK (
        (scope = 'personal' AND user_id IS NOT NULL AND household_id IS NULL) OR
        (scope = 'household' AND household_id IS NOT NULL AND user_id IS NULL)
    )
);

-- ============================================================
-- TRANSACTIONS
-- ============================================================
CREATE TABLE transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(id),

    amount          BIGINT NOT NULL,         -- minor units (cents), negative = outflow
    date            DATE NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    notes           TEXT,

    category_id     UUID REFERENCES categories(id),
    tags            JSONB NOT NULL DEFAULT '[]',

    -- Who created this (important for household accounts)
    created_by      UUID NOT NULL REFERENCES users(id),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_txn_account_date ON transactions (account_id, date DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_txn_category ON transactions (category_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_txn_created_by ON transactions (created_by) WHERE deleted_at IS NULL;

-- ============================================================
-- BUDGETS (dual-scope)
-- ============================================================
CREATE TABLE budgets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    scope           account_scope NOT NULL,
    user_id         UUID REFERENCES users(id),
    household_id    UUID REFERENCES households(id),

    category_id     UUID NOT NULL REFERENCES categories(id),
    amount          BIGINT NOT NULL,         -- budget amount in minor units
    period          TEXT NOT NULL DEFAULT 'monthly',  -- 'monthly', 'weekly', 'yearly'
    start_date      DATE NOT NULL,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,

    CONSTRAINT chk_budget_scope CHECK (
        (scope = 'personal' AND user_id IS NOT NULL AND household_id IS NULL) OR
        (scope = 'household' AND household_id IS NOT NULL AND user_id IS NULL)
    )
);

-- ============================================================
-- AUDIT LOG (for shared household actions)
-- ============================================================
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id    UUID NOT NULL REFERENCES households(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    action          TEXT NOT NULL,     -- 'transaction.create', 'account.update', 'member.invite'
    entity_type     TEXT NOT NULL,     -- 'transaction', 'account', 'budget', 'member'
    entity_id       UUID NOT NULL,
    changes         JSONB,            -- { "field": { "old": X, "new": Y } }
    ip_address      INET,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_household ON audit_log (household_id, created_at DESC);
CREATE INDEX idx_audit_entity ON audit_log (entity_type, entity_id);

-- ============================================================
-- HOUSEHOLD INVITATIONS (token-based)
-- ============================================================
CREATE TABLE household_invitations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_member_id UUID NOT NULL REFERENCES household_members(id),
    token           TEXT NOT NULL UNIQUE,   -- secure random token for invite link
    expires_at      TIMESTAMPTZ NOT NULL,
    used_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_invitations_token ON household_invitations (token) WHERE used_at IS NULL;
```

### Schema Design Decisions

| Decision | Rationale |
|----------|-----------|
| UUID primary keys | Distributed generation, no sequence contention, safe to expose in URLs |
| `BIGINT` for money (minor units) | Avoids floating-point errors; 100 = $1.00 |
| Dual scope via CHECK constraints | Enforces at DB level that an account is either personal or household, never both |
| `shared_to_household_id` on accounts | Allows personal accounts to be shared for visibility without changing ownership |
| `created_by` on transactions | Critical for audit trail on household accounts ("who spent this?") |
| Separate `household_invitations` table | Token lifecycle is independent of membership lifecycle |
| Soft deletes (`deleted_at`) | Financial data should never be hard-deleted |
| Audit log with JSONB changes | Captures before/after for every shared financial action |

---

## 5. Permission Model

### Role Definitions

| Role | Description | Typical User |
|------|-------------|-------------|
| **owner** | Full control, can delete household, transfer ownership | Person who created the household |
| **admin** | Can manage members, accounts, budgets. Cannot delete household or transfer ownership | Trusted partner/spouse |
| **member** | Can create/edit transactions on shared accounts, manage personal accounts | Family member, roommate |
| **viewer** | Read-only access to shared accounts | Child, financial advisor |

### Permission Matrix

| Action | Owner | Admin | Member | Viewer |
|--------|-------|-------|--------|--------|
| **Household Management** |||||
| Rename household | Yes | Yes | No | No |
| Delete household | Yes | No | No | No |
| Transfer ownership | Yes | No | No | No |
| **Member Management** |||||
| Invite members | Yes | Yes | No | No |
| Remove members | Yes | Yes (not owner) | No | No |
| Change member roles | Yes | Yes (not to owner) | No | No |
| Leave household | N/A | Yes | Yes | Yes |
| **Shared Accounts** |||||
| Create shared account | Yes | Yes | No | No |
| Edit shared account | Yes | Yes | No | No |
| Delete shared account | Yes | Yes | No | No |
| View shared account | Yes | Yes | Yes | Yes |
| **Shared Transactions** |||||
| Create transaction | Yes | Yes | Yes | No |
| Edit own transaction | Yes | Yes | Yes | No |
| Edit others' transaction | Yes | Yes | No | No |
| Delete transaction | Yes | Yes | Own only | No |
| View transactions | Yes | Yes | Yes | Yes |
| **Shared Budgets** |||||
| Create/edit budget | Yes | Yes | No | No |
| View budget | Yes | Yes | Yes | Yes |
| **Personal Accounts** |||||
| All operations | Own only | Own only | Own only | Own only |
| Share to household | Own only | Own only | Own only | Own only |
| **Audit Log** |||||
| View audit log | Yes | Yes | No | No |

### Permission Implementation (Go)

```go
// Permission check in Go service layer

type HouseholdPermission string

const (
    PermManageHousehold   HouseholdPermission = "manage_household"
    PermDeleteHousehold   HouseholdPermission = "delete_household"
    PermManageMembers     HouseholdPermission = "manage_members"
    PermManageAccounts    HouseholdPermission = "manage_accounts"
    PermCreateTransaction HouseholdPermission = "create_transaction"
    PermEditAnyTransaction HouseholdPermission = "edit_any_transaction"
    PermViewAccounts      HouseholdPermission = "view_accounts"
    PermManageBudgets     HouseholdPermission = "manage_budgets"
    PermViewAuditLog      HouseholdPermission = "view_audit_log"
)

var rolePermissions = map[HouseholdRole][]HouseholdPermission{
    RoleOwner: {
        PermManageHousehold, PermDeleteHousehold, PermManageMembers,
        PermManageAccounts, PermCreateTransaction, PermEditAnyTransaction,
        PermViewAccounts, PermManageBudgets, PermViewAuditLog,
    },
    RoleAdmin: {
        PermManageHousehold, PermManageMembers, PermManageAccounts,
        PermCreateTransaction, PermEditAnyTransaction, PermViewAccounts,
        PermManageBudgets, PermViewAuditLog,
    },
    RoleMember: {
        PermCreateTransaction, PermViewAccounts,
    },
    RoleViewer: {
        PermViewAccounts,
    },
}

// Middleware extracts household context and role from JWT + household_members
// Every household-scoped endpoint checks: HasPermission(ctx, householdID, permission)
```

### Row-Level Security vs Application-Level Isolation

| Approach | Pros | Cons | Recommendation |
|----------|------|------|---------------|
| **PostgreSQL RLS** | Enforced at DB level, impossible to bypass | Complex policies, harder to debug, performance overhead on complex joins | Use for critical boundaries |
| **Application-level** | Simpler, easier to test and debug | Bug = data leak | Use as primary approach |
| **Hybrid** | Defense in depth | More complexity | **Recommended** |

**Recommended hybrid approach:**

1. **Application-level** (primary): Every query includes `WHERE household_id = $1` or `WHERE user_id = $1`, enforced by repository layer
2. **PostgreSQL RLS** (safety net): Enable RLS on accounts, transactions, budgets tables as a defense-in-depth measure

```sql
-- Example RLS policy (defense in depth, not primary enforcement)
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY accounts_personal_policy ON accounts
    FOR ALL
    USING (
        (scope = 'personal' AND user_id = current_setting('app.current_user_id')::UUID)
        OR
        (scope = 'household' AND household_id IN (
            SELECT household_id FROM household_members
            WHERE user_id = current_setting('app.current_user_id')::UUID
            AND status = 'accepted'
            AND removed_at IS NULL
        ))
    );
```

---

## 6. Invitation Flow

### Sequence Diagram

```
Owner/Admin                  System                    Invitee
    │                          │                          │
    │  POST /households/{id}/  │                          │
    │  invite                  │                          │
    │  {email, role}           │                          │
    │─────────────────────────▶│                          │
    │                          │                          │
    │                          │  Create household_member │
    │                          │  (status: pending)       │
    │                          │                          │
    │                          │  Generate invite token   │
    │                          │                          │
    │                          │  Send email with link    │
    │                          │  /invite/{token}         │
    │                          │─────────────────────────▶│
    │                          │                          │
    │     201 Created          │                          │
    │◀─────────────────────────│                          │
    │                          │                          │
    │                          │     Click invite link    │
    │                          │◀─────────────────────────│
    │                          │                          │
    │                          │  If no account:          │
    │                          │  → Redirect to signup    │
    │                          │    (preserving token)    │
    │                          │                          │
    │                          │  If has account:         │
    │                          │  → Show accept/decline   │
    │                          │─────────────────────────▶│
    │                          │                          │
    │                          │     POST /invite/{token} │
    │                          │     /accept              │
    │                          │◀─────────────────────────│
    │                          │                          │
    │                          │  Update household_member │
    │                          │  (status: accepted,      │
    │                          │   user_id: set,          │
    │                          │   accepted_at: now)      │
    │                          │                          │
    │                          │  Mark token as used      │
    │                          │                          │
    │                          │  Redirect to household   │
    │                          │  dashboard               │
    │                          │─────────────────────────▶│
```

### Invitation Rules

- Invitation token expires after 7 days
- Owner/admin can revoke pending invitations
- An email can only have one pending invitation per household
- If the invitee already has a pfin account, they see a simple accept/decline UI
- If the invitee does NOT have an account, they are directed to signup, and the invitation is auto-accepted on signup completion
- Declining sets `status = 'declined'`; they can be re-invited
- A user can belong to multiple households simultaneously

---

## 7. UX Patterns

### 7.1 Household Switcher

Modeled after Slack's workspace switcher / Notion's workspace switcher.

```
┌──────────────────────────────┐
│  ┌────┐  Smith Family    ✓  │  ← current household
│  │ SF │  3 members          │
│  └────┘                     │
│─────────────────────────────│
│  ┌────┐  Apt 4B             │  ← another household
│  │ 4B │  2 members          │
│  └────┘                     │
│─────────────────────────────│
│  ┌────┐  Personal       ✓  │  ← always present "personal" context
│  │ ME │  Just me            │
│  └────┘                     │
│─────────────────────────────│
│  + Create Household         │
│  ⚙ Manage Households        │
│─────────────────────────────│
│  📨 2 pending invitations   │
└──────────────────────────────┘
```

**Key behaviors:**
- Always visible in the top-left of the navigation
- "Personal" context is always available (shows only personal accounts)
- Switching household changes the entire dashboard context
- Pending invitations shown with badge count
- Current household stored in a cookie/local storage; also persisted as `last_active_household` in user preferences

### 7.2 Dashboard Views

**When viewing a household:**

```
┌─────────────────────────────────────────────────┐
│  Smith Family Dashboard                         │
│                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐│
│  │ Net Worth   │  │ This Month  │  │ Budget   ││
│  │ $124,500    │  │ Spent: $3.2k│  │ On Track ││
│  │ ▲ 2.1%     │  │ Income: $8k │  │ 67% used ││
│  └─────────────┘  └─────────────┘  └──────────┘│
│                                                 │
│  Shared Accounts            Personal (yours)    │
│  ┌─────────────────┐       ┌──────────────────┐│
│  │ Joint Checking  │       │ Arnold's Visa    ││
│  │ $5,230          │       │ -$1,200 owed     ││
│  │ Joint Savings   │       │ Arnold's 401k    ││
│  │ $45,000         │       │ $89,000 (shared) ││
│  └─────────────────┘       └──────────────────┘│
│                                                 │
│  ↕ toggle: Show shared only / Show all          │
└─────────────────────────────────────────────────┘
```

**Key behaviors:**
- Net worth calculation includes: shared accounts + personal accounts shared to household
- "Personal (yours)" section shows user's personal accounts that are shared for visibility
- Toggle to show/hide personal accounts in the household view
- Budget progress bars are household-scoped
- Transaction feed shows all household transactions with "by [member name]" attribution

### 7.3 Account Detail View

```
┌─────────────────────────────────────────────────┐
│  Joint Checking                    Household 🔒 │
│  Balance: $5,230.00                             │
│                                                 │
│  Recent Transactions                            │
│  ─────────────────────────────────────────────  │
│  Mar 19  Grocery Store     -$82.50  by Arnold  │
│  Mar 18  Electric Co       -$145.00 by Sarah   │
│  Mar 17  Transfer In       +$2,000  by Arnold  │
│  Mar 16  Restaurant        -$45.00  by Sarah   │
│                                                 │
│  [Add Transaction]  [View All]  [Settings]      │
└─────────────────────────────────────────────────┘
```

### 7.4 Expense Splitting (Within Household)

For households that want to track who-owes-whom (roommate model):

```
┌─────────────────────────────────────────────────┐
│  Split: Electric Bill - $145.00                 │
│                                                 │
│  Split Method:  ○ Equal  ● Custom  ○ Percent    │
│                                                 │
│  Arnold:   $72.50                               │
│  Sarah:    $72.50                               │
│                                                 │
│  Paid by:  Sarah                                │
│                                                 │
│  Result: Arnold owes Sarah $72.50               │
│                                                 │
│  [Save Split]  [Cancel]                         │
└─────────────────────────────────────────────────┘
```

**Split implementation approach:**
- Splits are metadata on transactions, not separate entities
- A `transaction_splits` table tracks per-member shares
- Running balance of "who owes whom" is a computed view
- Settlement transactions zero out balances

```sql
CREATE TABLE transaction_splits (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id  UUID NOT NULL REFERENCES transactions(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    amount          BIGINT NOT NULL,    -- this user's share in minor units
    is_payer        BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 8. Architecture Implications

### 8.1 Tenant Context in Middleware

Every request operates in one of two contexts: **personal** or **household**. This is determined by middleware.

```go
// Middleware chain for household context
//
// 1. AuthMiddleware: extract user_id from JWT
// 2. HouseholdContextMiddleware: extract household context from header/cookie
// 3. PermissionMiddleware: verify user's role in the household

type HouseholdContext struct {
    HouseholdID uuid.UUID
    UserID      uuid.UUID
    Role        HouseholdRole
    IsPersonal  bool  // true when user is in "personal" context (no household)
}

// Header: X-Household-ID: <uuid>  (or "personal")
// This is set by the frontend when the user switches households

func HouseholdContextMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        userID := auth.UserIDFromContext(r.Context())
        householdHeader := r.Header.Get("X-Household-ID")

        if householdHeader == "" || householdHeader == "personal" {
            ctx := context.WithValue(r.Context(), householdCtxKey, &HouseholdContext{
                UserID:     userID,
                IsPersonal: true,
            })
            next.ServeHTTP(w, r.WithContext(ctx))
            return
        }

        householdID := uuid.MustParse(householdHeader)

        // Verify membership and get role
        member, err := memberRepo.GetActiveMember(r.Context(), householdID, userID)
        if err != nil {
            http.Error(w, "not a member of this household", http.StatusForbidden)
            return
        }

        ctx := context.WithValue(r.Context(), householdCtxKey, &HouseholdContext{
            HouseholdID: householdID,
            UserID:      userID,
            Role:        member.Role,
            IsPersonal:  false,
        })
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}
```

### 8.2 Query Scoping

Every repository method must be scope-aware. The pattern:

```go
// AccountRepository methods always filter by scope

func (r *AccountRepo) ListForContext(ctx context.Context, hCtx *HouseholdContext) ([]Account, error) {
    if hCtx.IsPersonal {
        // Personal context: only user's personal accounts
        return r.query(`
            SELECT * FROM accounts
            WHERE user_id = $1 AND scope = 'personal' AND deleted_at IS NULL
            ORDER BY name
        `, hCtx.UserID)
    }

    // Household context: shared accounts + user's accounts shared to this household
    return r.query(`
        SELECT * FROM accounts
        WHERE deleted_at IS NULL AND (
            (scope = 'household' AND household_id = $1)
            OR
            (scope = 'personal' AND shared_to_household_id = $1 AND user_id = $2)
        )
        ORDER BY scope, name
    `, hCtx.HouseholdID, hCtx.UserID)
}
```

### 8.3 Household-Scoped Chart of Accounts

The chart of accounts (categories) must be household-scoped:

- **System defaults**: Seeded when a household is created (Groceries, Rent, Utilities, etc.)
- **Household customization**: Owner/admin can add/rename/reorder categories
- **Personal categories**: Users can have personal categories for their personal accounts
- **Category resolution**: When viewing household context, merge household categories + user's personal categories

```go
func (r *CategoryRepo) ListForContext(ctx context.Context, hCtx *HouseholdContext) ([]Category, error) {
    if hCtx.IsPersonal {
        return r.query(`
            SELECT * FROM categories
            WHERE user_id = $1 AND scope = 'personal' AND deleted_at IS NULL
            ORDER BY sort_order, name
        `, hCtx.UserID)
    }

    // Household categories + user's personal categories (for personal accounts shown in household view)
    return r.query(`
        SELECT * FROM categories
        WHERE deleted_at IS NULL AND (
            (scope = 'household' AND household_id = $1)
            OR
            (scope = 'personal' AND user_id = $2)
        )
        ORDER BY scope, sort_order, name
    `, hCtx.HouseholdID, hCtx.UserID)
}
```

### 8.4 Impact on Existing Feature Plans

The household model affects every existing feature document:

| Feature | Impact |
|---------|--------|
| **Auth & User Management** | Add: household creation on signup (personal household), household switcher state in JWT or session |
| **Account Management** | Rewrite: accounts need `scope`, `household_id`, `shared_to_household_id` columns. Existing `user_id`-only design is insufficient |
| **Transaction Engine** | Add: `created_by` field, household-scoped queries, split tracking |
| **Budget System** | Scope budgets to household. Household budget = sum of all shared account spending in category |
| **Net Worth Dashboard** | Calculate per-household: sum shared accounts + accounts shared to household |
| **Reporting & Analytics** | All reports must be household-scoped with per-member breakdowns |

### 8.5 API Design

All household-scoped endpoints follow a consistent pattern:

```
# Household management
POST   /api/v1/households                          # Create household
GET    /api/v1/households                          # List user's households
GET    /api/v1/households/:id                      # Get household details
PATCH  /api/v1/households/:id                      # Update household
DELETE /api/v1/households/:id                      # Delete household (owner only)

# Member management
POST   /api/v1/households/:id/members/invite       # Invite member
GET    /api/v1/households/:id/members               # List members
PATCH  /api/v1/households/:id/members/:mid          # Update member role
DELETE /api/v1/households/:id/members/:mid           # Remove member
POST   /api/v1/invitations/:token/accept            # Accept invitation
POST   /api/v1/invitations/:token/decline           # Decline invitation

# Scoped resources (X-Household-ID header determines context)
GET    /api/v1/accounts                             # List accounts for current context
POST   /api/v1/accounts                             # Create account in current context
GET    /api/v1/transactions                         # List transactions for current context
POST   /api/v1/transactions                         # Create transaction in current context
GET    /api/v1/categories                           # List categories for current context
GET    /api/v1/budgets                              # List budgets for current context

# Personal account sharing
POST   /api/v1/accounts/:id/share                   # Share personal account to household
DELETE /api/v1/accounts/:id/share                    # Unshare personal account

# Audit log
GET    /api/v1/households/:id/audit-log              # View audit log (owner/admin)
```

---

## 9. Solo User Experience (No Household Overhead)

A critical design constraint: a solo user who never creates a household must have zero friction. The household system must be invisible until they need it.

**Approach: Implicit Personal Context**

- On signup, the user does NOT get a "household of one" created automatically
- The `IsPersonal` flag in the household context middleware defaults to `true` when no `X-Household-ID` header is present
- All accounts created without a household context are `scope = 'personal'`, `user_id = current_user`
- The household switcher only appears in the UI after the user creates or joins their first household
- Until then, the UI looks like a simple single-user finance app

This is important because the majority of users may never use the household feature. The data model supports it, but the UX hides it.

---

## 10. Migration Path from Current Feature Plans

The existing feature documents (auth, accounts, transactions) assume a single-user model. Here is the recommended approach to integrate the household model:

### Option A: Build Household from Day One
- Add household tables and dual-scope columns to the initial schema
- All queries are scope-aware from the start
- More work upfront but avoids migration pain later

### Option B: Build Single-User First, Add Household Later
- Ship auth, accounts, transactions as currently planned (user_id-scoped)
- Add household tables and columns in a later phase
- Requires data migration (add scope column, backfill as 'personal')

**Recommendation: Option A (Household from Day One)**

Rationale:
1. The schema difference is modest (a few extra columns and a join table)
2. Retrofitting scope-awareness into every query is painful and error-prone
3. The personal-only experience (section 9) means zero UX overhead for solo users
4. Multi-tenant SaaS architecture was stated as a day-one requirement in the shape doc

---

## 11. Open Questions for Shaping

| # | Question | Options | Recommendation |
|---|----------|---------|---------------|
| 1 | Should a personal household be auto-created on signup? | Yes (simpler queries) / No (less overhead) | **No** -- use IsPersonal flag, avoid empty household rows |
| 2 | Can a user be owner of multiple households? | Yes / No | **Yes** -- user might have family + roommate households |
| 3 | What happens to shared data when a member leaves? | Keep their transactions / Anonymize / Delete | **Keep with attribution** ("Former Member") |
| 4 | Maximum household size? | Unlimited / Capped | **Cap at 10** initially (prevents abuse, simplifies queries) |
| 5 | Should household have its own currency or follow member preference? | Household currency / Per-member | **Household default currency** with per-account override |
| 6 | Expense splitting: include in v1 or defer? | v1 / v2 | **Defer to v2** -- core household model is enough for v1 |
| 7 | Can viewers see transaction amounts or just categories? | Full visibility / Partial | **Full visibility** -- viewers are trusted (e.g., financial advisor) |
| 8 | Notification system for household events? | In-app / Email / Both / Defer | **Defer** -- align with the notification decision in SHAPE.md |

---

## 12. Summary of Recommendations

1. **Use a dual-scope model** (personal + household) where every financial entity belongs to exactly one scope, with an opt-in sharing mechanism for personal accounts

2. **Build household support into the schema from day one** to avoid costly migrations, but keep the UX invisible for solo users

3. **Implement four household roles** (owner, admin, member, viewer) with a clear permission matrix enforced at the application layer, backed by PostgreSQL RLS as defense-in-depth

4. **Use token-based email invitations** with 7-day expiry, supporting both existing users and new signups

5. **Scope every query through middleware** that extracts household context from an `X-Household-ID` header, making the tenant boundary explicit and consistent

6. **Defer expense splitting to v2** -- the core household model (shared accounts, shared budgets, role-based access) is sufficient for the first milestone

7. **Update existing feature documents** (auth, accounts, transactions) to incorporate the dual-scope model before implementation begins

---
*Research completed: 2026-03-20*
