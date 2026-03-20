# Feature: Project Foundation & Shared Kernel

**Parent shape:** [personal-finance](../../ideas/personal-finance/SHAPE.md)

## User Outcome

Development team has a working Go project scaffold with DDD structure, shared value objects, event bus, database connectivity, and CI pipeline.

## Scope

### Go Module & Directory Structure
- `cmd/api/main.go` — composition root with manual DI wiring
- `internal/` — bounded contexts: accounting, household, identity, budgeting, portfolio, reporting, importing
- Each context: `domain/` → `app/` → `adapters/` → `ports/` → `service/`
- `pkg/` — shared kernel (minimal)
- `migrations/` — PostgreSQL migration files
- `api/` — OpenAPI specs

### Shared Kernel (pkg/)
- `pkg/money/` — Money value object (shopspring/decimal wrapper, immutable, Currency-aware arithmetic)
- `pkg/currency/` — Currency value object (ISO 4217 validation)
- `pkg/scope/` — Scope value object (Personal with user_id / Household with household_id)
- `pkg/errs/` — Typed DomainError with machine-readable codes (VALIDATION_ERROR, NOT_FOUND, CONFLICT, UNBALANCED_ENTRY, etc.), mapped to HTTP status codes

### Event Bus
- `internal/common/event/bus.go` — Synchronous in-process event bus
- `internal/common/event/async.go` — Async event bus with goroutine workers
- `internal/common/event/composite.go` — CompositePublisher (sync critical + async non-critical)
- Event interface, Handler type, subscription registration at startup

### Infrastructure
- pgx v5 connection pool with config from env vars
- golang-migrate for versioned SQL migrations
- chi v5 router skeleton with middleware chain: RequestID → Logger → Recovery → CORS → RateLimit
- Config loading from environment variables (no viper)
- Structured logging with slog (JSON output)
- Graceful shutdown (SIGTERM handling)

### DevOps
- Docker Compose: PostgreSQL 16, app service
- Makefile: build, test, lint (golangci-lint), migrate, docker-up, docker-down
- Initial migration: enable pgcrypto, pg_trgm extensions

## Dependencies

None — this is the foundation.

## Risks

- DDD structure must be right from the start — restructuring packages later is painful
- Event bus design must support both sync and async from day one
- Shared kernel must be minimal — over-sharing breaks context boundaries

## Handoff Summary

Scaffold Go module with DDD directory layout per research docs. Implement shared kernel value objects (Money, Currency, Scope, DomainError). Build custom event bus (sync + async + composite). Set up pgx v5 pool, golang-migrate, chi v5 router with full middleware chain. Docker Compose with PostgreSQL 16. Makefile with standard targets. Manual DI wiring in cmd/api/main.go with graceful shutdown.

---
*Materialized from shape: 2026-03-20*
