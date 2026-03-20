---
name: boundary-and-sdk-enforcement
tags: [domain, security, quality]
appliesTo: [review, verify, team, spawn]
---
# Boundary And SDK Enforcement

Use this skill for API, security, and architecture reviews.

## Goal

Enforce boundary validation and typed-client usage across system edges.

## Boundary Checks

1. API boundary:
- validate request/response payloads
- reject malformed/oversized input with explicit errors

2. Storage boundary:
- validate query inputs and migration assumptions
- avoid unsafe dynamic query construction

3. Filesystem boundary:
- validate paths and permissions
- avoid blind reads/writes outside intended scope

4. Network boundary:
- timeouts, retries, and error mapping are explicit
- secrets are never logged

## SDK Checks

- prefer official typed SDKs/clients
- avoid ad-hoc HTTP wrappers when typed SDK exists
- keep DTOs/types aligned with provider schema versions

## Output

- **Critical** — must-fix boundary/SDK violations
- **Warning** — should-fix gaps
- **Info** — improvement suggestions
- Exact remediation edits
