# Plan 2: Implement the shared kernel value objects (pkg/) — Money, Currency, Scope, DomainError. These are the foundational types used across all bounded contexts. All with comprehensive tests.

## Goal
Implement the shared kernel value objects (pkg/) — Money, Currency, Scope, DomainError. These are the foundational types used across all bounded contexts. All with comprehensive tests.

## Tasks

### Task 1: Currency + Money value objects
**Files:** `pkg/currency/currency.go`, `pkg/currency/currency_test.go`, `pkg/money/money.go`, `pkg/money/money_test.go`
**Action:**
Implement pkg/currency (ISO 4217 validation, String(), common constants) and pkg/money (shopspring/decimal wrapper, immutable, Currency-aware arithmetic: Add, Sub, Mul, Negate, IsZero, IsNegative, Equal, String, NewFromString, NewFromInt).

**Verify:**
```bash
go test ./pkg/currency/... -v
go test ./pkg/money/... -v
```

**Done when:** [Observable outcome]

### Task 2: Scope value object
**Files:** `pkg/scope/scope.go`, `pkg/scope/scope_test.go`
**Action:**
Implement pkg/scope — the dual-scope type used in every query. Personal(userID) or Household(householdID). Includes validation, accessors, and SQL scanning support.

**Verify:**
```bash
go test ./pkg/scope/... -v
```

**Done when:** [Observable outcome]

### Task 3: DomainError type
**Files:** `pkg/errs/errors.go`, `pkg/errs/errors_test.go`
**Action:**
Implement pkg/errs — typed errors with machine-readable codes that map to HTTP status. Sentinel errors for common cases. Error wrapping support.

**Verify:**
```bash
go test ./pkg/errs/... -v
```

**Done when:** [Observable outcome]

## Verification

After all tasks:
```bash
go test ./pkg/... -v
go vet ./pkg/...
```

## Commit Message
```
feat(foundation): implement shared kernel — Money, Currency, Scope, DomainError value objects with tests
```
