# AGENTS.md

Working rules for automated agents in this repo.

## Read First

- Read `instructions.md` before making changes.
- Verify behavior against the codebase when docs and code disagree.
- Treat this file as current-repo guidance, not aspirational architecture.

## Instruction Ownership

- `AGENTS.md` is repo law: stable constraints, architecture boundaries, current validation commands, and environment notes.
- `instructions.md` defines engineering behavior and communication rules.
- `skills/` contains workflow guidance for recurring task types.
- `.codex/` is the Codex-local adapter layer for hooks, session artifacts, and harness glue.
- `.opencode/` and `.cursor/` are downstream adapters and should follow the same repo-law and workflow model.

## Enforced Today

- Reuse existing components, utilities, and services before creating new ones.
- Prefer simple, robust solutions over clever abstractions.
- Consider frontend and backend impact together for cross-cutting changes.
- Keep dependency direction moving inward: `interfaces` and `infrastructure` may depend on `application` and `domain`; `application` may depend on `domain`; `domain` should not depend on outer layers. The repo has existing violations, but do not add new ones.
- Keep business logic out of routes and components when practical. The repo has large orchestration files already; prefer incremental extraction over broad refactors.
- Use full Python type hints and TypeScript types where practical. Do not introduce new `any` casually.
- Pydantic v2 `@field_validator` methods must also be `@classmethod`. This is guarded by `backend/tests/test_pydantic_validators.py`.
- Status reports must be strictly factual. Distinguish `Completed`, `In Progress`, and `Not Started`.
- When writing code or docs, do not use placeholders or summary-only substitutions.

## Preferred Direction

- Prefer SOLID-style boundaries and dependency inversion when it improves clarity.
- Prefer domain/application services for reusable business rules.
- Prefer Vue Composition API with `<script setup>` in app code.
- Prefer smaller files and focused units, but follow existing patterns unless the task justifies a split.
- Prefer self-hosted, open-source, zero-cost integrations when they satisfy the requirement.
- Prefer research-backed implementation for library, API, architecture, and debugging work.

## Current Tooling Reality

- Frontend TypeScript runs with `strict: true`, but explicit `any` is still allowed by ESLint today. Treat `any` as an escape hatch, not as a normal pattern.
- Backend type checking is partial. Pyright configuration exists, but it is not part of the required pre-commit checks and is not uniformly strict across configs.
- Current required validation commands are:
  - Frontend: `cd frontend && bun run lint:check && bun run type-check`
  - Backend: `cd backend && ruff check . && ruff format --check . && pytest tests/`
- For a single backend test without coverage: `cd backend && pytest -p no:cov -o addopts= tests/test_file.py`

## Environment Notes

- Prefer `conda activate pythinker` when that environment exists.
- In shells without Conda, use the repo-local backend virtualenv if present: `backend/.venv`.
- For Docker operations and container logs, use Docker CLI by default. Use Docker MCP only when CLI is unavailable or MCP-specific behavior is required.
- For library and API documentation, use Context7 first. If Context7 is thin or stale for the question, verify with official primary sources.
- This repo is development-only. Optimize for correctness and iteration speed, not production hardening for external users.

## Platform-Specific Capabilities

- Agent lists, MCP servers, and skill inventories vary by harness. Verify what is actually available in the current runtime before relying on it.
- Do not assume repo-local paths such as `.opencode/skills/` exist without checking. They are not present in this repo today.
