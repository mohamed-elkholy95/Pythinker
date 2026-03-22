---
name: pythinker-ai-dev
description: Clean-code and clean-architecture execution guide for the Pythinker repository (FastAPI, Beanie/MongoDB, Redis, Qdrant, MinIO, Anthropic/OpenAI, Vue 3). Use when implementing, refactoring, reviewing, or debugging backend/frontend features in this repo and you need strict layer boundaries, async-safe patterns, type safety, and project-specific quality gates.
---

# Pythinker AI Dev

Use this skill to execute engineering work in Pythinker with strong architectural discipline and minimal ambiguity.

## Quick Start Workflow

1. Read `instructions.md` and `AGENTS.md` in the repository root before edits.
2. Surface assumptions before non-trivial implementation using this exact format:

```text
ASSUMPTIONS I'M MAKING:
1. ...
2. ...
-> Correct me now or I'll proceed with these.
```

3. Reuse existing modules before creating new ones.
4. Keep dependency direction inward only: Domain -> Application -> Infrastructure -> Interfaces.
5. Keep business logic out of routers, controllers, and UI components.
6. Validate implementation details against Context7 docs before finalizing.
7. Run relevant checks before handoff.

## Architecture Guardrails

- Keep `domain/` framework-agnostic.
- Define use-case orchestration in `application/`.
- Define ports (Protocols/interfaces) in `application/ports/`.
- Implement ports in `infrastructure/` adapters.
- Keep FastAPI routers/schemas/dependencies in `interfaces/`.
- Inject abstractions into use cases and routes; avoid importing infrastructure directly into domain/application logic.

## Backend Rules

- Use FastAPI `lifespan` to initialize/cleanup shared clients.
- Use `app.dependency_overrides` for test DI overrides.
- Keep Pydantic validation at boundaries (API schemas, infra documents, DTOs when needed).
- Use Pydantic v2 patterns (`ConfigDict`, `@field_validator` + `@classmethod`).
- Bound outbound I/O with explicit HTTPX timeouts and pool limits.
- Prefer structured concurrency (`asyncio.TaskGroup`) when fan-out is required.
- Ensure cancellation-safe streaming paths (SSE/WebSocket/background tasks).

## Frontend Rules

- Keep Vue components presentational where possible.
- Move orchestration and side effects into focused composables (`useX`).
- Ensure SSE/WebSocket/timer cleanup on unmount.
- Keep TypeScript strict and avoid `any`.
- Treat `import.meta.env` as non-secret client configuration only.

## Data and Integration Rules

- Keep Beanie `Document` models in infrastructure.
- Map persistence models to domain entities in repositories.
- Separate Redis runtime state from cache concerns and set explicit TTL/persistence policies.
- Treat hybrid retrieval (dense+sparse+rerank) as a staged subsystem with debuggable score traces.
- Use short-lived pre-signed object-storage URLs instead of exposing credentials.
- Keep LLM providers behind a shared internal `LLMClient` port.

## Required Checks

- Frontend: `cd frontend && bun run lint && bun run type-check`
- Backend: `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`

Single-test run without coverage:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/test_file.py
```

## Context7 Validation

Before finalizing changes, fetch authoritative docs via Context7 for any framework-specific behavior you implemented or changed. Prefer primary sources and match versions used in the codebase.

## Reference Files

Load these only when needed:

- `references/clean-code-and-architecture-guidelines.md`: Full long-form guidelines for architecture, async patterns, data systems, SSE, AI providers, frontend composition, and observability/security practices.
