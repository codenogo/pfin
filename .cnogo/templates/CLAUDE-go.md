# CLAUDE.md — Go

Agent instructions for this project. Claude reads this automatically.

## Project Overview

[One paragraph: what this project is, who it's for, what it does]

## Quick Reference

```bash
# Build
go build ./...

# Test
go test ./...

# Test with coverage
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out

# Run locally
go run .

# Lint/format
gofmt -w .
go vet ./...
golangci-lint run

# Tidy dependencies
go mod tidy

# Check vulnerabilities
govulncheck ./...
```

## Code Organisation

```
.
├── cmd/
│   └── [app]/           # Application entry points
│       └── main.go
├── internal/            # Private application code
│   ├── api/             # HTTP handlers
│   ├── service/         # Business logic
│   ├── repository/      # Data access
│   ├── model/           # Domain types
│   └── config/          # Configuration
├── pkg/                 # Public libraries (if any)
├── migrations/          # Database migrations
├── scripts/             # Build/deploy scripts
├── go.mod
└── go.sum
```

## Conventions

### Naming
- Packages: `lowercase`, short, no underscores
- Files: `snake_case.go`
- Types: `PascalCase` (exported), `camelCase` (unexported)
- Functions: `PascalCase` (exported), `camelCase` (unexported)
- Constants: `PascalCase` or `camelCase`

### Code Style
- Max line length: 100 characters (soft limit)
- Use `gofmt` and `goimports`
- Follow Effective Go guidelines
- Use meaningful variable names (short names for short scopes)

### Git
- Branch naming: `feature/description`, `fix/description`
- Commit format: `feat(scope): description` or `fix(scope): description`
- PR: Squash and merge

## Architecture Rules

### Do
- Accept interfaces, return structs
- Use context.Context for cancellation and deadlines
- Handle all errors (no `_` for errors)
- Use table-driven tests
- Keep packages focused and small

### Don't
- Don't use `init()` unless absolutely necessary
- Don't use global state (use dependency injection)
- Don't panic in library code
- Don't import `internal/` packages from outside
- Don't use naked returns

## Key Patterns

### Error Handling
```go
type AppError struct {
    Code    int
    Message string
    Err     error
}

func (e *AppError) Error() string {
    return e.Message
}

func (e *AppError) Unwrap() error {
    return e.Err
}
```

### Response Format
```go
type Response[T any] struct {
    Data    T        `json:"data,omitempty"`
    Message string   `json:"message,omitempty"`
    Errors  []string `json:"errors,omitempty"`
}
```

### Testing
- Use `testing` package
- Use table-driven tests
- Use `testify/assert` for assertions (optional)
- Use `testcontainers-go` for integration tests
- Minimum coverage: 80%

### Dependency Injection
```go
type Server struct {
    userService UserService
    orderRepo   OrderRepository
}

func NewServer(us UserService, or OrderRepository) *Server {
    return &Server{userService: us, orderRepo: or}
}
```

## Security

- Never commit: `.env`, secrets, `*.pem`, `*.key`
- Always validate: Request input
- Always use: parameterized queries (sqlx, pgx)
- Use crypto/rand for random values, not math/rand

## Dependencies

Before adding dependencies:
1. Check if stdlib provides it
2. Prefer minimal dependencies
3. Run `govulncheck` after adding
4. Verify module is actively maintained
