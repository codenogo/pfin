# Feature: Chart of Accounts & Wallets (Accounting Context — Phase 1)

**Parent shape:** [personal-finance](../../ideas/personal-finance/SHAPE.md)
**Bounded context:** Accounting (core domain)
**Package:** `internal/accounting/domain/account/`

## User Outcome

Users can create and manage financial accounts (wallets) — checking, savings, credit cards, cash, e-wallets, loans — built on the five accounting types.

## Scope

### Domain Layer (`internal/accounting/domain/account/`)
- **Account aggregate root**: id, scope (Scope value object), name, category (AccountCategory), account_type (AccountSubtype), currency (Currency), credit_limit, is_visible, is_archived, presentation (icon, color, display_order), shared_to_household_id
- **AccountCategory value object** (enum): asset, liability, equity, income, expense
- **AccountSubtype value object** (enum): checking, savings, credit_card, cash, e_wallet, loan, mortgage, investment, other_asset, other_liability
- **IsWallet()** domain method: returns true if category IN (asset, liability) AND is_visible AND NOT is_archived
- **Repository interface**: Create, GetByID, List, Update, Archive, GetBalance

### Application Layer (`internal/accounting/app/command/`)
- **CreateAccount**: validate type-category consistency, enforce scope, emit AccountCreated
- **ArchiveAccount**: soft delete (never hard-delete accounts with journal lines)
- **ShareToHousehold**: set shared_to_household_id and visibility level

### Application Layer (`internal/accounting/app/query/`)
- **ListWallets**: filtered to visible asset+liability accounts for current scope
- **AccountBalance**: read from materialized account_balances view

### Event Handlers
- Subscribe to `UserRegistered` → seed system accounts (equity:opening-balances, default expense/income categories)
- Subscribe to `HouseholdCreated` → seed household-scoped default categories

### Domain Events
- `AccountCreated` — for audit trail
- `AccountArchived` — for cleanup in downstream contexts

### Database Migration
- `accounts` table with dual-scope CHECK constraints, presentation fields, credit_limit
- `categories` table (hierarchical, dual-scope) with parent_id, icon, color

### API
- `GET/POST /api/v1/accounts` — full chart of accounts
- `GET /api/v1/wallets` — filtered to visible asset+liability
- `POST /api/v1/accounts/:id/share` — share personal account to household
- `DELETE /api/v1/accounts/:id/share` — unshare

## Dependencies

- `auth-user-management` — requires authenticated user, UserRegistered event
- `household-management` — requires HouseholdContext middleware, HouseholdCreated event

## Risks

- Account type taxonomy must be extensible for future data imports
- System account seeding must match accounting conventions correctly
- Dual-scope CHECK constraints must be enforced at DB level
- Account aggregate boundary must be clean — JournalEntry references by ID only

## Handoff Summary

Implement internal/accounting/domain/account per DDD structure. Account aggregate root with Category, Subtype, Currency value objects. IsWallet() domain method. CreateAccount + ArchiveAccount commands. PostgreSQL accounts table with dual-scope CHECK constraints. Seed system accounts via UserRegistered event handler. Query handlers for wallet list and balance. HTTP handlers with dual endpoints. Next.js wallet list, account forms.

---
*Materialized from shape: 2026-03-20*
