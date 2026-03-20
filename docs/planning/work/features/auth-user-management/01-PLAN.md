# Plan 1: Implement the Identity domain layer: User aggregate with password validation, Credentials value object with bcrypt hashing, RefreshToken entity, repository interfaces, and database migrations for users + refresh_tokens tables.

## Goal
Implement the Identity domain layer: User aggregate with password validation, Credentials value object with bcrypt hashing, RefreshToken entity, repository interfaces, and database migrations for users + refresh_tokens tables.

## Tasks

### Task 1: User aggregate + Credentials value object
**Files:** `internal/identity/domain/user/user.go`, `internal/identity/domain/user/user_test.go`, `internal/identity/domain/user/credentials.go`, `internal/identity/domain/user/credentials_test.go`, `internal/identity/domain/user/repository.go`
**Action:**
Implement the User entity and Credentials value object in internal/identity/domain/user/. User has ID, Email, DisplayName, PasswordHash, CreatedAt, UpdatedAt. Credentials handles password validation (8+ chars, uppercase, lowercase, number, special char) and bcrypt hashing/verification. UserRepository interface.

**Verify:**
```bash
go test ./internal/identity/domain/user/... -v
```

**Done when:** [Observable outcome]

### Task 2: RefreshToken entity + SessionRepository interface
**Files:** `internal/identity/domain/session/session.go`, `internal/identity/domain/session/session_test.go`, `internal/identity/domain/session/repository.go`
**Action:**
Implement RefreshToken entity in internal/identity/domain/session/. Handles token generation (crypto/rand), hashing (SHA-256), expiry checking, and revocation. SessionRepository interface.

**Verify:**
```bash
go test ./internal/identity/domain/session/... -v
```

**Done when:** [Observable outcome]

### Task 3: Database migrations (users + refresh_tokens)
**Files:** `migrations/003_users.up.sql`, `migrations/003_users.down.sql`, `migrations/004_refresh_tokens.up.sql`, `migrations/004_refresh_tokens.down.sql`
**Action:**
Create SQL migration files for the users and refresh_tokens tables.

**Verify:**
```bash
test -f migrations/003_users.up.sql && grep 'CREATE TABLE users' migrations/003_users.up.sql
test -f migrations/004_refresh_tokens.up.sql && grep 'CREATE TABLE refresh_tokens' migrations/004_refresh_tokens.up.sql
```

**Done when:** [Observable outcome]

## Verification

After all tasks:
```bash
go test ./internal/identity/domain/... -v
go vet ./internal/identity/...
test -f migrations/003_users.up.sql
test -f migrations/004_refresh_tokens.up.sql
```

## Commit Message
```
feat(identity): domain layer — User aggregate, Credentials, RefreshToken, migrations
```
