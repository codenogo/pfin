# Plan 3: Implement HTTP handlers (auth routes + user profile), JWT auth middleware, rate limiting on auth endpoints, and wire Identity context into cmd/api/main.go router.

## Goal
Implement HTTP handlers (auth routes + user profile), JWT auth middleware, rate limiting on auth endpoints, and wire Identity context into cmd/api/main.go router.

## Tasks

### Task 1: JWT auth middleware
**Files:** `internal/common/auth/middleware.go`, `internal/common/auth/middleware_test.go`, `internal/common/auth/context.go`
**Action:**
Implement JWT validation middleware in internal/common/auth/. Extracts Bearer token from Authorization header, validates JWT, injects UserID + Email into request context. Reusable by all bounded contexts.

**Verify:**
```bash
go test ./internal/common/auth/... -v
```

**Done when:** [Observable outcome]

### Task 2: HTTP handlers (auth + profile)
**Files:** `internal/identity/ports/auth_handler.go`, `internal/identity/ports/auth_handler_test.go`, `internal/identity/ports/user_handler.go`, `internal/identity/ports/user_handler_test.go`
**Action:**
Implement HTTP handlers in internal/identity/ports/. Auth handlers: register, login, refresh (cookie-based), logout. User handlers: get profile, update profile. Rate limiting on auth endpoints.

**Verify:**
```bash
go test ./internal/identity/ports/... -v
```

**Done when:** [Observable outcome]

### Task 3: Wire into main.go router
**Files:** `cmd/api/main.go`
**Action:**
Update cmd/api/main.go to create the Identity application and mount auth + user routes on the chi router. Add JWT middleware to protected routes group.

**Verify:**
```bash
go build -o bin/pfin ./cmd/api/...
go vet ./...
```

**Done when:** [Observable outcome]

## Verification

After all tasks:
```bash
go test ./internal/identity/... -v
go test ./internal/common/auth/... -v
go build -o bin/pfin ./cmd/api/...
go vet ./...
```

## Commit Message
```
feat(identity): HTTP handlers, JWT middleware, rate limiting, router integration
```
