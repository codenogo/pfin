# CLAUDE.md

Agent instructions for this project. Claude reads this automatically.

## Project Overview

[One paragraph: what this project is, who it's for, what it does]

## Quick Reference

```bash
# Build
[build command]

# Test
[test command]

# Run locally
[run command]

# Lint/format
[lint command]
```

## Code Organisation

```
src/
├── [layer or feature]/     # [Purpose]
├── [layer or feature]/     # [Purpose]
└── [layer or feature]/     # [Purpose]

tests/
├── unit/                   # Unit tests
└── integration/            # Integration tests
```

## Conventions

### Naming
- Files: `kebab-case.ts` or `PascalCase.java`
- Classes: `PascalCase`
- Functions: `camelCase`
- Constants: `SCREAMING_SNAKE_CASE`

### Code Style
- [Max line length]
- [Import ordering]
- [Any other conventions]

### Git
- Branch naming: `feature/description`, `fix/description`
- Commit format: `type(scope): description`
- PR: Squash and merge

## Architecture Rules

### Do
- [Pattern to follow]
- [Pattern to follow]

### Don't
- [Anti-pattern to avoid]
- [Anti-pattern to avoid]

## Key Files

| File | Purpose | Notes |
|------|---------|-------|
| `src/config/` | Configuration | Don't hardcode values |
| `src/types/` | Type definitions | Keep in sync with API |

## Testing Requirements

- Unit tests required for: [what]
- Integration tests required for: [what]
- Minimum coverage: [X%]

## Security

- Never commit: secrets, keys, credentials
- Always validate: [inputs]
- Always sanitize: [outputs]

## Dependencies

Before adding dependencies:
1. Check if existing dep solves problem
2. Evaluate security (last update, maintainers, CVEs)
3. Consider bundle size impact
