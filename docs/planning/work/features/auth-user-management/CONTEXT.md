# Context: Auth & User Management (Identity Context)

**Feature:** auth-user-management
**Branch:** `feature/auth-user-management`
**Status:** Discussed, ready for `/plan`

## Key Decision: Custom Go Auth for v1

Keycloak (1.5GB Java), SuperTokens (Java core), and Ory Kratos (extra service) are all overkill for email+password v1. Custom Go auth is ~500 lines with golang-jwt + bcrypt + pgx. Clean port boundary in `internal/identity/` enables swapping to Keycloak/SuperTokens when OAuth/MFA is needed.

## Decisions

| ID | Decision | Choice |
|----|----------|--------|
| AUTH-001 | Auth approach | Custom Go (JWT + bcrypt + refresh tokens) |
| AUTH-002 | Access token lifetime | 15 minutes |
| AUTH-003 | Refresh token lifetime | 14 days, single-use rotation, 90-day absolute limit |
| AUTH-004 | Refresh token storage (server) | PostgreSQL `refresh_tokens` table (hashed) |
| AUTH-005 | Token storage (client) | Access: in-memory. Refresh: httpOnly cookie |
| AUTH-006 | Silent refresh | Axios interceptor: 401 → refresh → retry |
| AUTH-007 | Password requirements | 8+ chars, uppercase + lowercase + number + special |
| AUTH-008 | Email verification | Skipped for v1 |
| AUTH-009 | OAuth/social login | Skipped for v1 |
| AUTH-010 | Password hashing | bcrypt, cost=10 |
| AUTH-011 | JWT signing | HS256 with JWT_SECRET from env |

## "Always Logged In" Flow

```
1. User logs in → Go issues access token (15min) + refresh token (14 days)
2. Refresh token set as httpOnly cookie
3. Access token held in React memory
4. On 401 → Axios interceptor calls /auth/refresh
5. Go validates refresh token, rotates it (new token, old revoked)
6. New access + refresh tokens returned → retry original request
7. User stays logged in for up to 14 days without interaction
8. After 90 days absolute → force re-login
```

## Database Tables

```sql
-- 003_users.up.sql
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 004_refresh_tokens.up.sql
CREATE TABLE refresh_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Package Structure

```
internal/identity/
  domain/user/
    user.go              # User aggregate
    credentials.go       # Password validation + hashing
    repository.go        # UserRepository interface
  domain/session/
    session.go           # RefreshToken entity
    repository.go        # SessionRepository interface
  app/command/
    register.go          # Register → create user → emit UserRegistered
    authenticate.go      # Login → verify password → issue token pair
    refresh.go           # Refresh → validate + rotate → new token pair
    logout.go            # Logout → revoke refresh token
  adapters/
    postgres_user_repo.go
    postgres_session_repo.go
    jwt_issuer.go        # golang-jwt HS256 signing
  ports/
    auth_handler.go      # POST /auth/register, /login, /refresh, /logout
    user_handler.go      # GET /users/me, PATCH /users/me
  service/
    wire.go
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /auth/register | Public | Create account |
| POST | /auth/login | Public | Authenticate, set refresh cookie |
| POST | /auth/refresh | Cookie | Rotate refresh token, new access token |
| POST | /auth/logout | Cookie | Revoke refresh token |
| GET | /users/me | Bearer | Get current user profile |
| PATCH | /users/me | Bearer | Update display name |

## Constraints

- internal/identity/ imports only from pkg/ (shared kernel)
- JWT middleware in internal/common/auth/ (shared)
- Refresh tokens hashed before storage
- All auth endpoints rate-limited
- Password validation in domain layer

---
*Discussed: 2026-03-20 | Ready for `/plan auth-user-management`*
