---
name: pythinker-testing
description: Testing patterns for the Pythinker project — pytest fixtures, AsyncMock, conda environment, coverage bypass for single tests
---

# Pythinker Testing Skill

## When to Use
When writing or running tests for the Pythinker backend or frontend.

## Backend Testing (pytest)

### Environment
```bash
conda activate pythinker && cd backend
```

### Run All Tests
```bash
pytest tests/
```

### Single Test (without coverage)
pytest addopts enforce coverage by default. Bypass:
```bash
pytest -p no:cov -o addopts= tests/test_file.py
```

### Parallel Execution
```bash
pytest -n auto tests/
```

### Key Patterns
- **AsyncMock**: Always set `.return_value` for numeric comparisons
- **Fixtures**: Use pytest fixtures for dependency injection
- **Async tests**: `@pytest.mark.asyncio` with `pytest-asyncio`
- **Test location**: Tests in `tests/` (NOT in package directories — shadows packages)

### DDD Test Organization
```
tests/
├── domain/          # Domain model and service tests
├── application/     # Use case tests
├── infrastructure/  # Adapter integration tests
├── interfaces/      # API route tests
└── conftest.py      # Shared fixtures
```

## Frontend Testing (Vitest)

### Run Tests
```bash
cd frontend && bun run test:run
```

### Key Patterns
- Vue Test Utils for component testing
- `mount()` / `shallowMount()` for component isolation
- Mock composables with `vi.mock()`
- Test composables independently with `renderHook()`

## Pre-Commit Checks
- **Backend**: `ruff check . && ruff format --check . && pytest tests/`
- **Frontend**: `bun run lint && bun run type-check`
