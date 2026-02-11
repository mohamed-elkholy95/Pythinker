# AGENTS.md

Concise instructions for automated agents working in this repo.

## Quick Rules

- **Superpowers skills**: only use superpowers skills when explicitly asked.
- **Read first**: read `instructions.md` before making changes.
- **Reuse before creating**: search the codebase for existing components/utilities/services and extend them instead of duplicating.
- **Simplicity first**: prefer straightforward, robust solutions; avoid unnecessary complexity.
- **Integration policy**: when integrating solutions/services, prioritize self-hosted, zero-cost, open-source options; avoid external dependencies and keep integrations fully self-contained.
- **Full-stack design**: consider front-end and back-end impact together.
- **Dependency rule**: Domain → Application → Infrastructure → Interfaces (inward only).
- **SOLID**: single responsibility; depend on abstractions; inject dependencies.
- **Type safety**: full Python type hints / TypeScript strict; no `any`.
- **Layer discipline**: business logic lives in domain, not routes or components.
- **Naming**: Python `snake_case` functions / `PascalCase` classes; Vue `PascalCase` components / `useX` composables.
- **Pydantic v2**: `@field_validator` must be `@classmethod` (guarded by `backend/tests/test_pydantic_validators.py`).
- **Plan execution**: complete all phases; priorities indicate order, not optional steps.
- **Backend env**: always use `conda activate pythinker`.
- **Development-only environment**: this repo is development-only with no production users. Prioritize flexibility and experimentation; unrestricted iteration and breaking changes are allowed, and no decisions need to optimize for production stability, data retention, or user impact.

## Checks (before committing)

- **Frontend**: `cd frontend && bun run lint && bun run type-check`
- **Backend**: `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`

## Single-Test Run (no coverage)

Pytest addopts enforce coverage by default. To run a single test without coverage:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/test_file.py
```
