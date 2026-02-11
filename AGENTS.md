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
- **Context7 validation (always)**: validate all new implementations, files, and configurations against fetched Context7 MCP documentation to ensure accuracy and compliance before deployment.
- **Development-only environment**: this repo is development-only with no production users. Prioritize flexibility and experimentation; unrestricted iteration and breaking changes are allowed, and no decisions need to optimize for production stability, data retention, or user impact.
- **Status report accuracy (absolute)**: summaries/status reports must be 100% factual. Never mark partially done or foundational-only work as `Completed`. Always distinguish `Completed`, `In Progress`, and `Not Started`.
- **Full implementation only (absolute)**: when writing code, provide full unabridged file implementations. Never use placeholders, omitted sections, or summary-only substitutions.
- **Persistence for complex requests (absolute)**: do not reduce scope to fit one reply. Output as much valid complete code as possible, then continue on explicit `Continue` prompts until fully done.

## Checks (before committing)

- **Frontend**: `cd frontend && bun run lint && bun run type-check`
- **Backend**: `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`

## Single-Test Run (no coverage)

Pytest addopts enforce coverage by default. To run a single test without coverage:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/test_file.py
```
