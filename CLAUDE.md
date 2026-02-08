# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pythinker is an AI Agent system that runs tools (browser, terminal, files, search) in isolated Docker sandbox environments. It uses a FastAPI backend with Domain-Driven Design, a Vue 3 frontend, and Docker containers for task isolation.

## Quick Reference

> **Core Principles:**
> 1. **Reuse First**: Search existing codebase for components, utilities, and services before creating new ones
> 2. **Simplicity First**: Design with simplicity and directness — prefer straightforward solutions that maintain robustness, reliability, and best practices; avoid unnecessary complexity or overcomplication
> 3. **Full-Stack Design**: Design each feature by thoroughly evaluating and integrating front-end and back-end architecture considerations, ensuring seamless compatibility, optimal performance, and cohesive system integration across all components
> 4. **Dependency Rule**: Domain → Application → Infrastructure → Interfaces (inward only)
> 5. **SOLID**: Single responsibility, depend on abstractions, inject dependencies
> 6. **Type Safety**: Full type hints (Python) / strict mode (TypeScript); no `any`
> 7. **Layer Discipline**: Business logic in domain, not in API routes or components
> 8. **Naming**: Python `snake_case` functions / `PascalCase` classes; Vue `PascalCase` components / `useX` composables
>
> **Before committing:**
> - **Frontend**: `cd frontend && bun run lint && bun run type-check`
> - **Backend**: `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`

## Development Guidelines

- **Read [instructions.md](instructions.md) first** - Core engineering behaviors and patterns
- **Reuse Before Creating**: Before implementing any new code, component, utility, or feature, **search the existing codebase** for similar functionality. Check composables, services, utilities, domain models, and components that may already solve the problem or can be extended. Never create a duplicate when an existing piece can be reused or adapted.
- **Pydantic v2**: `@field_validator` methods **must** be `@classmethod`
- **Python Environment**: Always `conda activate pythinker` before running tests
- **Plan Execution**: Complete ALL phases - priorities indicate order, not optional phases

## Detailed Standards

For comprehensive coding standards, see:
- **[Engineering Instructions](instructions.md)** - Core behaviors, leverage patterns, output standards (MUST READ)
- **[Python Standards](docs/guides/PYTHON_STANDARDS.md)** - Pydantic v2, FastAPI, LangGraph, async patterns
- **[Vue Standards](docs/guides/VUE_STANDARDS.md)** - Composition API, Pinia, TypeScript
- **[Superpowers Workflow](docs/guides/SUPERPOWERS.md)** - `/brainstorm`, `/tdd`, `/debug` commands
- **[OpenReplay & Sandbox](docs/guides/OPENREPLAY.md)** - Session replay, CDP screencast

---

## Development Commands

### Full Stack
```bash
./dev.sh up -d              # Start dev stack
./dev.sh down -v            # Stop and remove volumes
./dev.sh logs -f backend    # Follow logs
```

### Backend
```bash
cd backend && conda activate pythinker
ruff check . && ruff format --check .   # Lint
ruff check --fix . && ruff format .     # Auto-fix
pytest tests/                           # Test
pytest -p no:cov -o addopts= tests/test_file.py  # Single test without coverage
```

### Frontend
```bash
cd frontend
bun run dev          # Dev server (5173)
bun run lint         # ESLint fix
bun run type-check   # TypeScript check
bun run test:run     # Single test run
```

---

## Architecture

### Backend DDD Structure (`backend/app/`)
- **domain/**: Core business logic, models, services, abstract repositories
- **application/**: Use case orchestration, DTOs
- **infrastructure/**: MongoDB/Redis implementations, external adapters (LLM, browser, search)
- **interfaces/api/**: REST routes, request/response schemas
- **core/**: Config, sandbox manager, workflow manager

### Frontend Structure (`frontend/src/`)
- **pages/**: Route components (ChatPage, HomePage)
- **components/**: UI components (ChatMessage, SandboxViewer, ToolPanel)
- **composables/**: Shared logic (useChat, useSession, useAgentEvents)
- **api/**: HTTP client with SSE support

### Key Patterns
- **Event Sourcing**: Session events in MongoDB
- **SSE Streaming**: Real-time events to frontend
- **LangGraph Workflows**: Planning → Execution → Reflection → Verification
- **Sandbox Isolation**: Docker containers with CDP screencast

---

## Port Mapping (Development)

| Service | Port |
|---------|------|
| Frontend | 5174 |
| Backend | 8000 |
| Sandbox API | 8083 |
| MongoDB | 27017 |
| Redis | 6379 |
| Qdrant | 6333/6334 |

---

## Code Style

- **Python**: 4-space indent, `snake_case` functions, `PascalCase` classes
- **Vue/TS**: 2-space indent, `PascalCase` components, `useX` composables
- **Linting**: Ruff (backend), ESLint (frontend)

---

## Anti-Patterns to Avoid

1. **God Classes** - Split large classes with multiple responsibilities
2. **Leaky Abstractions** - Infrastructure details must not leak into domain
3. **Circular Dependencies** - Maintain strict layer boundaries
4. **Magic Strings** - Use enums and constants
5. **Deep Nesting** - Prefer early returns and guard clauses
6. **Redundant Code** - Never create new files, components, utilities, or services without first searching for existing ones that serve the same or similar purpose
7. **Over-Engineering** - Avoid unnecessary abstractions, premature generalization, or complex patterns when a simple direct solution works equally well

---

## Refactoring Checklist

- [ ] Searched codebase for existing similar functionality before creating new code
- [ ] Dependencies point inward (domain has no external imports)
- [ ] Each class/function has single responsibility
- [ ] Type hints/annotations complete
- [ ] Business logic in domain layer
- [ ] No `any` types (TS) / untyped functions (Python)
- [ ] Tests pass, linting passes

---

## Configuration

- Copy `.env.example` to `.env` for local runs
- MCP integration via `mcp.json.example`
- Docker socket mount: `-v /var/run/docker.sock:/var/run/docker.sock`
