---
name: test-writing
tags: [domain, testing, quality]
appliesTo: [spawn]
---
# Test Writing

Test strategy and patterns for unit and integration tests.

## Unit Tests

- Pure logic and edge cases
- Error paths and boundary conditions
- Deterministic (no flaky tests)
- Fast execution (mock external dependencies)

## Integration Tests

- API contract verification
- Database interactions
- External service boundaries
- End-to-end workflows

## Patterns

- Regression test: every reported bug gets a test
- Arrange-Act-Assert structure
- Test names describe the behavior being verified
- Minimize test coupling (each test is independent)

## Coverage

- New/changed behavior must have tests
- Edge cases: empty input, null, boundaries, overflow
- Error paths: invalid input, network failures, timeouts
