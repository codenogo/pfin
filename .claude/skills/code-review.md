---
name: code-review
tags: [domain, quality, security]
appliesTo: [review, spawn]
---
# Code Review

Review checklist for code quality, security, and maintainability.

## Security

- Auth / access control verified
- Input validation at system boundaries
- No exposed secrets or API keys
- Injection risks checked (SQL, command, XSS)
- No sensitive data in logs

## Performance

- No N+1 queries
- No unbounded loops or collections
- Memory / resource leaks reviewed
- Timeouts and retries configured where needed

## Design Patterns

- Codebase pattern alignment (follows existing conventions)
- API consistency (naming, error shapes, contracts)
- Abstractions minimal and justified (no speculative layers)

## General Quality

- Code is clear and readable
- Functions and variables are well-named
- No duplicated code or unnecessary complexity
- Proper error handling on all paths
- Test coverage for new/changed behavior
- No OWASP Top 10 vulnerabilities introduced

## Refactor Safety

- Behavior is preserved (no silent regressions)
- Changes are minimal and focused
- No mixed concerns (refactor + feature in same change)
- Deprecation strategy if interfaces change

## Output Format

- **Critical** (must fix before merge)
- **Warning** (should fix, creates tech debt)
- **Info** (consider improving)

Include file:line references and specific fix examples.
