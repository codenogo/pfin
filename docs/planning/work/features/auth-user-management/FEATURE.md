# Feature: Auth & User Management (Identity Context)

**Parent shape:** [personal-finance](../../ideas/personal-finance/SHAPE.md)
**Bounded context:** Identity & Access (generic subdomain)
**Package:** `internal/identity/`

## User Outcome

Users can sign up, log in, manage their profile, and have secure sessions.

## Scope

### Domain Layer (`internal/identity/domain/user/`)
- **User entity**: id (UUID), email, display_name, avatar_url, email_verified, created_at
- **Credentials value object**: password_hash (bcrypt), last_changed_at
- **Repository interface**: Create, GetByID, GetByEmail, Update

### Application Layer (`internal/identity/app/command/`)
- **Register**: validate email uniqueness, hash password, create user, emit `UserRegistered`
- **Authenticate**: verify credentials, generate JWT access + refresh tokens
- **ResetPassword**: token-based flow, emit `PasswordChanged`
- **UpdateProfile**: display name, avatar

### Infrastructure (`internal/identity/adapters/`)
- PostgreSQL user repository (pgx v5)
- bcrypt password hasher
- JWT token generator (golang-jwt)

### Ports (`internal/identity/ports/`)
- HTTP handlers: POST /auth/register, POST /auth/login, POST /auth/refresh, POST /auth/reset-password, GET /users/me, PATCH /users/me

### Domain Events
- `UserRegistered` — triggers system account seeding in Accounting context
- `UserVerified` — email verification confirmed
- `PasswordChanged` — audit trail

### Middleware (in `internal/common/auth/`)
- JWT validation middleware extracting user_id into context
- Rate limiting on auth endpoints (x/time/rate)

### Database Migration
- `users` table: id, email, password_hash, display_name, avatar_url, email_verified, created_at, updated_at, deleted_at

## Dependencies

- `project-foundation` — requires Go scaffold, event bus, pgx pool, chi router

## Risks

- Auth is security-critical — must get right from the start
- Session management complexity (refresh tokens, revocation)
- JWT secret management and rotation strategy

## Handoff Summary

Implement internal/identity/ bounded context per DDD structure. User aggregate with Credentials value object. Register + Authenticate command handlers. PostgreSQL user repository. HTTP handlers on chi router. JWT middleware in internal/common/auth. Emit UserRegistered event (consumed by Accounting context for system account seeding). Rate limiting. Next.js: login, register, profile, password reset pages.

---
*Materialized from shape: 2026-03-20*
