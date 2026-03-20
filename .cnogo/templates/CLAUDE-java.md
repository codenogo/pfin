# CLAUDE.md — Java/Spring Boot

Agent instructions for this project. Claude reads this automatically.

## Project Overview

[One paragraph: what this project is, who it's for, what it does]

## Quick Reference

```bash
# Build
mvn clean compile

# Test (unit only)
mvn test

# Test (with integration)
mvn verify

# Run locally
mvn spring-boot:run

# Lint/format
mvn spotless:apply

# Check for vulnerabilities
mvn org.owasp:dependency-check-maven:check
```

## Code Organisation

```
src/
├── main/java/com/[company]/[project]/
│   ├── config/          # Spring configuration
│   ├── controller/      # REST controllers
│   ├── service/         # Business logic
│   ├── repository/      # Data access (JPA)
│   ├── model/           # Domain entities
│   ├── dto/             # Data transfer objects
│   └── exception/       # Custom exceptions
│
├── main/resources/
│   ├── application.yml  # Main config
│   └── db/migration/    # Flyway migrations
│
└── test/java/
    ├── unit/            # Unit tests
    └── integration/     # Integration tests (@SpringBootTest)
```

## Conventions

### Naming
- Classes: `PascalCase` (e.g., `UserService`, `OrderController`)
- Methods: `camelCase` (e.g., `findById`, `createOrder`)
- Constants: `SCREAMING_SNAKE_CASE`
- Packages: `lowercase`
- DTOs: Suffix with `Request`, `Response`, or `Dto`

### Code Style
- Max line length: 120 characters
- Use Lombok for boilerplate (`@Data`, `@Builder`, `@Slf4j`)
- Prefer constructor injection over field injection
- Use `Optional` for nullable returns, never for parameters

### Git
- Branch naming: `feature/JIRA-123-description`, `fix/JIRA-456-description`
- Commit format: `feat(scope): description` or `fix(scope): description`
- PR: Squash and merge

## Architecture Rules

### Do
- Use `@Transactional` at service layer, not repository
- Return DTOs from controllers, not entities
- Use `@Valid` for request validation
- Log at appropriate levels (DEBUG for internals, INFO for business events)
- Use pagination for list endpoints (`Pageable`)

### Don't
- Don't expose entity IDs in URLs (use UUIDs or slugs)
- Don't catch generic `Exception`
- Don't use `@Autowired` on fields
- Don't put business logic in controllers
- Don't skip integration tests for database operations

## Key Patterns

### Exception Handling
```java
@RestControllerAdvice
public class GlobalExceptionHandler {
    // Centralized exception handling
}
```

### Response Format
```java
public class ApiResponse<T> {
    private T data;
    private String message;
    private List<String> errors;
}
```

### Testing
- Unit tests: JUnit 5 + Mockito
- Integration tests: `@SpringBootTest` with Testcontainers
- Minimum coverage: 80% for services

## Security

- Never commit: `application-prod.yml`, secrets, credentials
- Always validate: Request bodies with `@Valid`
- Always sanitize: SQL (use JPA), user input
- Use Spring Security for auth

## Dependencies

Before adding dependencies:
1. Check if Spring Boot starter already provides it
2. Prefer Spring ecosystem libraries
3. Check for CVEs on new dependencies
