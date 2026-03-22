---
name: pythinker-plan-execute
description: Plan and execute multi-step Pythinker work with explicit file mapping, DDD-aware decomposition, factual status reporting, and repo-specific validation paths.
---

# Pythinker Plan Execute

Use this skill for multi-step work that spans more than one file or crosses backend, frontend, or harness boundaries.

## Plan Requirements

Every plan should identify:

- the goal
- the relevant files
- the architectural layer for each file
- the validation commands that prove success
- the main risks or edge cases

## Layer Mapping

- `backend/app/domain/`: domain rules and models
- `backend/app/application/`: orchestration and use cases
- `backend/app/infrastructure/`: adapters and external integrations
- `backend/app/interfaces/`: HTTP/SSE transport surfaces
- `frontend/src/components/`: presentational UI
- `frontend/src/composables/`: frontend orchestration
- `skills/`, `.codex/`, `.opencode/`, `.cursor/`: harness layers

## Execution Rules

- Touch only the files needed for the approved scope.
- Keep status reports factual: `Completed`, `In Progress`, `Not Started`.
- When the work affects both product code and harness surfaces, describe both impacts explicitly.

## Validation

Choose the smallest correct validation set for the changed area:

- frontend: `cd frontend && bun run lint:check && bun run type-check`
- backend: `cd backend && ruff check . && ruff format --check . && pytest tests/`
- single backend file: `cd backend && pytest -p no:cov -o addopts= tests/test_file.py`

Do not claim completion without fresh evidence.
