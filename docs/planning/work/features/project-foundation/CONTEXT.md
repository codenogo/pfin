# Context: Project Foundation & Shared Kernel

**Feature:** project-foundation
**Branch:** `feature/project-foundation`
**Status:** Discussed, ready for `/plan`

## Decisions

| ID | Decision | Choice |
|----|----------|--------|
| PF-001 | Go module path | `github.com/codenogo/pfin` |
| PF-002 | Go version | 1.26 (latest stable, Feb 2026) |
| PF-003 | PostgreSQL | 18 (18.3, latest stable) |
| PF-004 | Health + OpenAPI | Yes — GET /health + GET /api/v1/openapi.yaml |
| PF-005 | Shared kernel | pkg/money, pkg/currency, pkg/scope, pkg/errs |
| PF-006 | Event bus | Custom sync+async composite (~300 lines) |
| PF-007 | HTTP router | chi v5 with middleware chain |
| PF-008 | DB driver | pgx v5, no ORM |
| PF-009 | Migrations | golang-migrate v4, SQL files |
| PF-010 | DI | Constructor injection, manual wiring |
| PF-011 | Logging | log/slog (stdlib), JSON in prod |
| PF-012 | Config | os.Getenv + Config struct |
| PF-013 | Docker | Compose with PostgreSQL 18 |
| PF-014 | Makefile | build, test, lint, migrate, docker, run |
| PF-015 | Initial migrations | pgcrypto + pg_trgm extensions, event_outbox table |

## What Gets Built

### Directory Structure
```
github.com/codenogo/pfin/
├── cmd/api/main.go                     # Composition root
├── internal/
│   ├── accounting/domain/              # Stub (empty, structure only)
│   ├── household/domain/               # Stub
│   ├── identity/domain/                # Stub
│   ├── budgeting/domain/               # Stub
│   ├── debt/domain/                    # Stub
│   ├── portfolio/domain/               # Stub
│   ├── reporting/domain/               # Stub
│   ├── importing/domain/               # Stub
│   └── common/
│       ├── auth/                       # JWT middleware (stub)
│       ├── server/                     # HTTP server, error responses
│       ├── event/                      # Bus, AsyncBus, CompositePublisher
│       └── decorator/                  # Command/query decorators (stub)
├── pkg/
│   ├── money/money.go                  # Money value object
│   ├── currency/currency.go            # Currency value object
│   ├── scope/scope.go                  # Scope value object
│   └── errs/errors.go                  # Typed DomainError
├── migrations/
│   ├── 001_extensions.up.sql
│   ├── 001_extensions.down.sql
│   ├── 002_event_outbox.up.sql
│   └── 002_event_outbox.down.sql
├── api/openapi.yaml                    # OpenAPI spec skeleton
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
└── go.mod
```

### Shared Kernel (pkg/)
- **Money**: shopspring/decimal wrapper, immutable, currency-aware Add/Sub/Mul, negative check, zero check, String formatting
- **Currency**: ISO 4217 enum with validation (USD, EUR, GBP, etc.)
- **Scope**: Personal(userID) | Household(householdID) — used in every dual-scope query
- **DomainError**: code (VALIDATION_ERROR, NOT_FOUND, CONFLICT, etc.), message, wrapped error. Maps to HTTP status in server package.

### Event Bus (internal/common/event/)
- **Event interface**: `EventName() string`
- **Bus** (sync): handlers run in caller's goroutine/transaction
- **AsyncBus**: handlers run in background goroutines
- **CompositePublisher**: sync first (critical), then async (non-critical)
- All handler registration at startup

### Infrastructure
- pgx v5 pool with env-based config
- golang-migrate with `migrations/` directory
- chi v5 router: RequestID → slog → Recovery → CORS → RateLimit → routes
- GET /health (DB ping + uptime JSON)
- Graceful shutdown on SIGTERM

## Constraints

- Domain layers: zero external deps beyond pkg/ + shopspring/decimal + google/uuid
- Shared kernel stays minimal
- No circular imports between context packages
- Constructors accept interfaces, not concrete types

## Open Questions

None.

## Inherited from Shape

- All global architecture decisions (DDD, event-inspired, CQRS-lite, etc.)
- 8 bounded context structure
- Core library choices (pgx, chi, shopspring/decimal, etc.)

---
*Discussed: 2026-03-20 | Ready for `/plan project-foundation`*
