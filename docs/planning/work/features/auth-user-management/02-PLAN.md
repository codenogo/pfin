# Plan 2: Implement application services (CQRS commands) and infrastructure adapters: Register, Authenticate, Refresh, Logout command handlers. JWT token issuer. PostgreSQL repositories for users and sessions. Domain event emission (UserRegistered).

## Goal
Implement application services (CQRS commands) and infrastructure adapters: Register, Authenticate, Refresh, Logout command handlers. JWT token issuer. PostgreSQL repositories for users and sessions. Domain event emission (UserRegistered).

## Tasks

### Task 1: JWT token issuer + PostgreSQL repositories
**Files:** `internal/identity/adapters/jwt_issuer.go`, `internal/identity/adapters/jwt_issuer_test.go`, `internal/identity/adapters/postgres_user_repo.go`, `internal/identity/adapters/postgres_session_repo.go`
**Action:**
Implement the infrastructure adapters: JWT issuer (golang-jwt HS256, signs access tokens with user claims), PostgreSQL user repository, and PostgreSQL session repository. All implement domain interfaces.

**Verify:**
```bash
go test ./internal/identity/adapters/... -v -run TestJWT
```

**Done when:** [Observable outcome]

### Task 2: Command handlers (Register, Authenticate, Refresh, Logout)
**Files:** `internal/identity/app/command/register.go`, `internal/identity/app/command/register_test.go`, `internal/identity/app/command/authenticate.go`, `internal/identity/app/command/authenticate_test.go`, `internal/identity/app/command/refresh.go`, `internal/identity/app/command/logout.go`, `internal/identity/domain/user/events.go`
**Action:**
Implement the CQRS command handlers in internal/identity/app/command/. Each handler orchestrates domain objects and repositories. Register emits UserRegistered domain event via the event bus.

**Verify:**
```bash
go test ./internal/identity/app/command/... -v
```

**Done when:** [Observable outcome]

### Task 3: Service wiring
**Files:** `internal/identity/service/wire.go`
**Action:**
Create the Identity service factory that wires all dependencies together. Takes pgx pool, event publisher, and config — returns a fully assembled application with all command handlers.

**Verify:**
```bash
go build ./internal/identity/...
```

**Done when:** [Observable outcome]

## Verification

After all tasks:
```bash
go test ./internal/identity/... -v
go build ./internal/identity/...
go vet ./internal/identity/...
```

## Commit Message
```
feat(identity): application layer — command handlers, JWT issuer, PostgreSQL repos, UserRegistered event
```
