---
name: api-review
tags: [domain, quality]
appliesTo: [spawn]
---
# API Design Review

Checklist for adding or modifying endpoints, contracts, and schemas.

## Contract

- Request/response format defined
- Error format consistent across endpoints
- Pagination strategy for list endpoints
- Idempotency for write operations
- Versioning strategy documented

## Auth

- Required scopes/roles specified
- Authorization checks at handler level

## Validation

- Runtime validation on all inputs
- Error messages are helpful but don't leak internals

## Compatibility

- Backwards compatibility maintained (or migration plan documented)
- Deprecation notices for removed fields

## Observability

- Request IDs for tracing
- Structured logging
- Metrics for latency and error rates
