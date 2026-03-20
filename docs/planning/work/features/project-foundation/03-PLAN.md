# Plan 3: Implement the event bus, HTTP server with middleware chain, health endpoint, config loading, and graceful shutdown. Wire everything in cmd/api/main.go. This is the running application skeleton.

## Goal
Implement the event bus, HTTP server with middleware chain, health endpoint, config loading, and graceful shutdown. Wire everything in cmd/api/main.go. This is the running application skeleton.

## Tasks

### Task 1: Event bus (sync + async + composite)
**Files:** `internal/common/event/event.go`, `internal/common/event/bus.go`, `internal/common/event/bus_test.go`, `internal/common/event/async.go`, `internal/common/event/async_test.go`, `internal/common/event/composite.go`, `internal/common/event/composite_test.go`
**Action:**
Implement internal/common/event — the in-process event bus with sync dispatch, async dispatch, and composite publisher. ~300 lines total. All with tests.

**Verify:**
```bash
go test ./internal/common/event/... -v -race
```

**Done when:** [Observable outcome]

### Task 2: Config + server + error responses + middleware
**Files:** `internal/config/config.go`, `internal/common/server/server.go`, `internal/common/server/response.go`, `internal/common/server/response_test.go`, `internal/common/server/middleware.go`, `internal/common/server/health.go`, `internal/common/server/health_test.go`
**Action:**
Implement config loading (env vars → struct), HTTP server with chi + middleware chain (RequestID, slog, Recovery, CORS, RateLimit), error response helper mapping DomainError → JSON, and health handler.

**Verify:**
```bash
go test ./internal/config/... -v
go test ./internal/common/server/... -v
```

**Done when:** [Observable outcome]

### Task 3: Composition root — cmd/api/main.go wiring
**Files:** `cmd/api/main.go`
**Action:**
Wire everything together in main.go: load config, connect pgx pool, create event bus, build chi router with middleware + health endpoint, start server with graceful shutdown. Add go.sum by running go mod tidy.

**Verify:**
```bash
go build ./cmd/api/...
go vet ./...
```

**Done when:** [Observable outcome]

## Verification

After all tasks:
```bash
go build ./cmd/api/...
go test ./internal/common/... -v -race
go test ./pkg/... -v
go vet ./...
```

## Commit Message
```
feat(foundation): implement event bus, HTTP server, middleware, health endpoint, and composition root
```
