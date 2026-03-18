# Python Backend Standards

This document describes the backend conventions that are accurate for the repo today, plus the direction new work should follow.

## Current Repo Reality

The backend is organized into these main layers:

```text
backend/app/
├── application/
├── core/
├── domain/
├── infrastructure/
└── interfaces/
```

The intended dependency direction is inward:

- `interfaces` and `infrastructure` may depend on `application` and `domain`
- `application` may depend on `domain`
- `domain` should not depend on outer layers

There are existing violations of that rule in the repo today. Do not add new ones. When touching those areas, prefer small changes that move composition and infrastructure wiring outward rather than large refactors.

## Enforced by Tooling

- `ruff check .` must pass.
- `ruff format --check .` must pass.
- `pytest tests/` must pass.
- Pydantic v2 `@field_validator` methods must also be `@classmethod`.

### Important Typing Note

The backend is typed, but it is not uniformly strict today.

- There are multiple Pyright configs with different strictness levels.
- Pyright is not part of the required validation commands above.
- Existing code includes untyped parameters and methods.

Use full type hints where practical for new and modified code, but do not document the repo as if strict static typing is already fully enforced.

## Pydantic v2

- Use field validators in this order: `@field_validator(...)` followed by `@classmethod`.
- Use `@model_validator` where model-level consistency checks are clearer than field-local validation.
- Use `ConfigDict` when you need explicit model behavior such as `strict`, `frozen`, `extra`, `validate_assignment`, or `from_attributes`.
- Do not add `ConfigDict` mechanically to every model. Match the model behavior to the use case.

## Layering and Business Logic

- Prefer business rules in `domain` and coordination/orchestration in `application`.
- Keep API routes in `interfaces` focused on I/O, validation, auth, serialization, and dependency wiring.
- Keep infrastructure code implementing repositories, external clients, storage, and adapters.
- Avoid importing `interfaces` or `infrastructure` into `domain`. If you encounter an existing service-locator style import, do not copy that pattern into new code.

## Async and Concurrency

- Prefer `asyncio.TaskGroup` for new structured-concurrency work when failure semantics matter.
- Existing code still uses `asyncio.gather` in many places. Do not refactor unrelated code purely to remove it.
- Use async context managers for resources that need cleanup.
- In FastAPI `yield` dependencies, do not swallow exceptions. Clean up and re-raise.

## Environment Notes

- Prefer `conda activate pythinker` when that environment exists.
- In shells without Conda, use the repo-local backend virtualenv if present: `backend/.venv`.
- The repo currently targets Python 3.11 in `pyproject.toml`, even if local environments may run newer interpreters.

## Known Drift

- Some interface and orchestration files are larger than the preferred target.
- Some domain services still reach outward into infrastructure or interfaces.
- Some type coverage and configuration are inconsistent across the repo.
- Treat this document as the standard for new and modified code, not as a claim that the entire backend already matches it.

## Checks

```bash
cd backend && ruff check . && ruff format --check . && pytest tests/
```

## Single Test Without Coverage

```bash
cd backend && pytest -p no:cov -o addopts= tests/test_file.py
```
