# CLAUDE.md — TypeScript/Node.js

Agent instructions for this project. Claude reads this automatically.

## Project Overview

[One paragraph: what this project is, who it's for, what it does]

## Quick Reference

```bash
# Install dependencies
npm install

# Build
npm run build

# Test
npm test

# Run locally
npm run dev

# Lint
npm run lint

# Format
npm run format

# Type check
npx tsc --noEmit
```

## Code Organisation

```
src/
├── api/              # Route handlers/controllers
├── services/         # Business logic
├── repositories/     # Data access
├── models/           # Type definitions and schemas
├── middleware/       # Express/Fastify middleware
├── utils/            # Shared utilities
├── config/           # Configuration loading
└── index.ts          # Application entry point

tests/
├── unit/             # Unit tests (*.test.ts)
├── integration/      # Integration tests (*.integration.ts)
└── fixtures/         # Test data and mocks
```

## Conventions

### Naming
- Files: `kebab-case.ts` (e.g., `user-service.ts`)
- Classes: `PascalCase` (e.g., `UserService`)
- Functions: `camelCase` (e.g., `createUser`)
- Constants: `SCREAMING_SNAKE_CASE` or `camelCase`
- Types/Interfaces: `PascalCase` with `I` prefix optional

### Code Style
- Max line length: 100 characters
- Use ESLint + Prettier
- Prefer `const` over `let`, never `var`
- Use async/await over raw promises
- Prefer named exports over default exports

### Git
- Branch naming: `feature/description`, `fix/description`
- Commit format: `feat(scope): description` or `fix(scope): description`
- PR: Squash and merge

## Architecture Rules

### Do
- Use TypeScript strict mode (`"strict": true`)
- Define explicit return types for public functions
- Use Zod or Joi for runtime validation
- Handle errors with try/catch and proper error types
- Use dependency injection for testability

### Don't
- Don't use `any` (use `unknown` and type guards)
- Don't mutate function parameters
- Don't use synchronous file operations
- Don't ignore TypeScript errors with `// @ts-ignore`
- Don't mix callbacks and promises

## Key Patterns

### Error Handling
```typescript
class AppError extends Error {
  constructor(
    public statusCode: number,
    public message: string,
    public isOperational = true
  ) {
    super(message);
  }
}
```

### Response Format
```typescript
interface ApiResponse<T> {
  data: T;
  message?: string;
  errors?: string[];
}
```

### Testing
- Framework: Jest or Vitest
- Assertions: Built-in Jest matchers
- Mocking: jest.mock() or vi.mock()
- Minimum coverage: 80%

## Security

- Never commit: `.env`, `.env.*`, secrets, API keys
- Always validate: Request bodies with Zod/Joi
- Always sanitize: User input, SQL queries (use ORM)
- Use helmet for HTTP headers

## Dependencies

Before adding dependencies:
1. Check bundle size impact (`bundlephobia.com`)
2. Verify last update and maintenance status
3. Check for known vulnerabilities (`npm audit`)
4. Prefer well-maintained packages with TypeScript support
