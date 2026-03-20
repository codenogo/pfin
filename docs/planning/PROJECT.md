# Project: [Project Name]

> One-sentence description of what this project does.

## Vision

[2-3 sentences on the end goal. What does success look like?]

## Constraints

| Constraint | Reason |
|------------|--------|
| [Tech constraint] | [Why] |
| [Business constraint] | [Why] |
| [Compliance constraint] | [Why] |

## Architecture

```
[Simple ASCII or description of system architecture]

┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│   Gateway   │────▶│  Services   │
└─────────────┘     └─────────────┘     └─────────────┘
                                              │
                                              ▼
                                        ┌─────────────┐
                                        │  Database   │
                                        └─────────────┘
```

## Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Backend | [Java/Spring, Node/Express, etc.] | [Version, key libs] |
| Frontend | [React, Vue, etc.] | [Version, key libs] |
| Database | [Postgres, MongoDB, etc.] | [Version] |
| Infra | [K8s, Docker, etc.] | [Cloud provider] |

## Patterns

### Code Organisation
- [How code is structured: by feature, by layer, etc.]
- [Naming conventions]
- [Module boundaries]

### API Design
- [REST/GraphQL/gRPC]
- [Versioning strategy]
- [Error format]

### Testing
- [Unit test framework and patterns]
- [Integration test approach]
- [Coverage expectations]

### Error Handling
- [How errors are handled and propagated]
- [Logging patterns]

## Non-Goals

Things explicitly out of scope:
- [Thing we're not building]
- [Problem we're not solving]

## Key Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| [Decision] | [Why we chose this] | [When] |

---
*Last updated: [date]*
