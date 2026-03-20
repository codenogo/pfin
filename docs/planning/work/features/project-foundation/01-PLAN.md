# Plan 1: Scaffold the Go module, DDD directory structure, Docker Compose, Makefile, initial migrations, and .gitignore. No Go code yet — just the skeleton and devops files.

## Goal
Scaffold the Go module, DDD directory structure, Docker Compose, Makefile, initial migrations, and .gitignore. No Go code yet — just the skeleton and devops files.

## Tasks

### Task 1: Go module + DDD directory skeleton
**Files:** `go.mod`, `.gitignore`, `.env.example`, `cmd/api/main.go`, `internal/accounting/domain/.gitkeep`, `internal/household/domain/.gitkeep`, `internal/identity/domain/.gitkeep`, `internal/budgeting/domain/.gitkeep`, `internal/debt/domain/.gitkeep`, `internal/portfolio/domain/.gitkeep`, `internal/reporting/domain/.gitkeep`, `internal/importing/domain/.gitkeep`, `internal/common/event/.gitkeep`, `internal/common/auth/.gitkeep`, `internal/common/server/.gitkeep`, `pkg/money/.gitkeep`, `pkg/currency/.gitkeep`, `pkg/scope/.gitkeep`, `pkg/errs/.gitkeep`
**Action:**
Initialize Go module (github.com/codenogo/pfin, go 1.26). Create all directories per DDD structure. Add .gitkeep files to preserve empty dirs. Create .gitignore (Go standard + .env + .cnogo/memory.db). Create .env.example with placeholder config.

**Verify:**
```bash
test -f go.mod && grep 'github.com/codenogo/pfin' go.mod
test -f cmd/api/main.go
test -d internal/accounting/domain
test -d internal/common/event
test -d pkg/money
```

**Done when:** [Observable outcome]

### Task 2: Docker Compose + Makefile + migrations
**Files:** `docker-compose.yml`, `Makefile`, `migrations/001_extensions.up.sql`, `migrations/001_extensions.down.sql`, `migrations/002_event_outbox.up.sql`, `migrations/002_event_outbox.down.sql`
**Action:**
Create docker-compose.yml with PostgreSQL 18 service. Create Makefile with standard targets. Create initial SQL migration files for extensions and event outbox table.

**Verify:**
```bash
test -f docker-compose.yml && grep 'postgres:18' docker-compose.yml
test -f Makefile && make -n build 2>/dev/null
test -f migrations/001_extensions.up.sql
test -f migrations/002_event_outbox.up.sql
```

**Done when:** [Observable outcome]

### Task 3: OpenAPI spec skeleton
**Files:** `api/openapi.yaml`
**Action:**
Create minimal OpenAPI 3.1 spec with /health endpoint and info section. This serves as the starting point for all future endpoint definitions.

**Verify:**
```bash
test -f api/openapi.yaml && grep 'openapi: 3.1' api/openapi.yaml
```

**Done when:** [Observable outcome]

## Verification

After all tasks:
```bash
test -f go.mod
test -f docker-compose.yml
test -f Makefile
test -f api/openapi.yaml
test -d internal/accounting/domain
test -d internal/common/event
test -d pkg/money
test -f migrations/001_extensions.up.sql
test -f migrations/002_event_outbox.up.sql
```

## Commit Message
```
feat(foundation): scaffold Go module, DDD directories, Docker, Makefile, migrations
```
