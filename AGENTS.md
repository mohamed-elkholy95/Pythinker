# AGENTS.md

Concise instructions for automated agents working in this repo.

## Quick Rules

- **Pydantic v2**: `@field_validator` must be `@classmethod` (guarded by `backend/tests/test_pydantic_validators.py`).
- **Backend env**: always use `conda activate pythinker`.
- **Backend checks**: `cd backend && ruff check . && ruff format --check . && pytest tests/`.

## Single-Test Run (no coverage)

Pytest addopts enforce coverage by default. To run a single test without coverage:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= backend/tests/test_pydantic_validators.py
```

