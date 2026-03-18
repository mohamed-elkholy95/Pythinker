# Contributing to Pythinker

Thank you for your interest in contributing to Pythinker! This guide will help you get started.

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/Pythinker.git
   cd Pythinker
   ```
3. **Set up** the development environment:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   docker compose up --watch
   ```

## Development Workflow

### Branch Naming

Use descriptive branch names with a prefix:

- `feat/browser-pool-optimization` — New features
- `fix/sse-reconnect-race` — Bug fixes
- `refactor/sandbox-cleanup` — Code refactoring
- `docs/contributing-guide` — Documentation
- `test/agent-lifecycle` — Test additions

### Commit Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(scope): add browser connection pooling
fix(sandbox): prevent orphaned containers on crash
refactor(backend): extract search enrichment pipeline
docs(api): update SSE streaming examples
test(agent): add lifecycle teardown coverage
chore(deps): bump fastapi to 0.119
```

### Code Style

**Backend (Python)**
- Python 3.12+, type hints required on all public functions
- Formatter: `ruff format .`
- Linter: `ruff check .`
- Architecture: Domain-Driven Design — business logic in `domain/`, never in routes or components

**Frontend (TypeScript/Vue)**
- Vue 3 Composition API with `<script setup lang="ts">`
- Linter: `bun run lint`
- Type check: `bun run type-check`
- Composables use `useX` naming, components use `PascalCase`

### Dependency Management

The backend uses **`requirements.txt`** as the source of truth for dependencies. A `uv.lock` file is also present for contributors who use [uv](https://github.com/astral-sh/uv) as their package manager.

- **pip users**: `pip install -r requirements.txt` (standard workflow)
- **uv users**: `uv sync` (faster, uses uv.lock for deterministic installs)

When adding or updating dependencies, always update `requirements.txt` first. The `uv.lock` will be regenerated automatically on the next `uv sync`.

### Running Tests

```bash
# Backend (3,800+ tests)
cd backend
ruff check . && ruff format --check .
pytest tests/ -v --tb=short

# Frontend
cd frontend
bun run lint
bun run type-check
bun run test:run
```

## Pull Request Process

1. **Create a focused PR** — one concern per PR, keep diffs small
2. **Write a clear description** — explain *what* and *why*, not just *how*
3. **Include tests** — new features need tests, bug fixes need regression tests
4. **Pass CI** — lint, type-check, tests, and security scan must all pass
5. **Request review** — a maintainer will review within a few days

### PR Template

Your PR should include:
- A summary of the changes (2-3 bullet points)
- A test plan describing how to verify
- Screenshots for UI changes

## Architecture Overview

```
backend/app/
├── core/           # Config, settings, lifespan
├── domain/         # Models, services, agents, tools (business logic)
├── application/    # Use case orchestration, DTOs
├── infrastructure/ # External integrations (LLM, DB, browser, search)
└── interfaces/     # API routes, request/response schemas
```

**Key principle**: Dependencies point inward. Domain has no external imports. Infrastructure implements domain protocols.

## Reporting Bugs

Open a [GitHub Issue](https://github.com/mohamed-elkholy95/Pythinker/issues/new?template=bug_report.md) with:
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Docker version, browser)
- Relevant logs (backend container logs are most useful)

## Suggesting Features

Open a [Feature Request](https://github.com/mohamed-elkholy95/Pythinker/issues/new?template=feature_request.md) describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this standard.

## Questions?

Open a [Discussion](https://github.com/mohamed-elkholy95/Pythinker/discussions) or reach out via GitHub Issues.
