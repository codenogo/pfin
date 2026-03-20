# CLAUDE.md — Python

Agent instructions for this project. Claude reads this automatically.

## Project Overview

[One paragraph: what this project is, who it's for, what it does]

## Quick Reference

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -e ".[dev]"

# Test
pytest

# Run locally
python -m [package_name]
# or: uvicorn app.main:app --reload  (FastAPI)
# or: python manage.py runserver     (Django)

# Lint
ruff check .

# Format
black . && isort .

# Type check
mypy .
```

## Code Organisation

```
src/[package_name]/
├── api/              # Route handlers (FastAPI/Flask)
├── services/         # Business logic
├── repositories/     # Data access
├── models/           # Pydantic/SQLAlchemy models
├── schemas/          # Request/response schemas
├── core/             # Configuration, settings
├── utils/            # Shared utilities
└── __main__.py       # Entry point

tests/
├── unit/             # Unit tests
├── integration/      # Integration tests
├── conftest.py       # Pytest fixtures
└── fixtures/         # Test data
```

## Conventions

### Naming
- Files: `snake_case.py` (e.g., `user_service.py`)
- Classes: `PascalCase` (e.g., `UserService`)
- Functions: `snake_case` (e.g., `create_user`)
- Constants: `SCREAMING_SNAKE_CASE`
- Private: `_leading_underscore`

### Code Style
- Max line length: 88 characters (Black default)
- Use type hints for all function signatures
- Use Ruff for linting, Black for formatting
- Follow PEP 8 and PEP 257 (docstrings)

### Git
- Branch naming: `feature/description`, `fix/description`
- Commit format: `feat(scope): description` or `fix(scope): description`
- PR: Squash and merge

## Architecture Rules

### Do
- Use type hints everywhere
- Use Pydantic for data validation
- Use dependency injection (FastAPI) or similar patterns
- Use `async`/`await` for I/O-bound operations
- Write docstrings for public functions

### Don't
- Don't use mutable default arguments
- Don't catch bare `except:`
- Don't use global state
- Don't ignore type checker errors
- Don't mix sync and async code carelessly

## Key Patterns

### Error Handling
```python
class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)
```

### Response Format (FastAPI)
```python
from pydantic import BaseModel
from typing import Generic, TypeVar

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    data: T
    message: str | None = None
    errors: list[str] | None = None
```

### Testing
- Framework: pytest
- Fixtures: Use `conftest.py`
- Async: pytest-asyncio
- Mocking: unittest.mock or pytest-mock
- Minimum coverage: 80%

## Security

- Never commit: `.env`, secrets, API keys, `*.pem`
- Always validate: Request bodies with Pydantic
- Always sanitize: SQL (use ORM), user input
- Use secrets management (environment variables)

## Dependencies

Before adding dependencies:
1. Check if stdlib provides it
2. Verify maintenance status on PyPI
3. Run `pip-audit` for vulnerabilities
4. Prefer pure Python or well-maintained C extensions
