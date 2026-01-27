# Repository Guidelines

## Project Structure & Module Organization
- `frontend/`: Vue 3 + TypeScript UI (Vite, Tailwind, Vitest). Source lives in `frontend/src/` with pages, components, composables, and assets.
- `backend/`: FastAPI service using a DDD layout (`backend/app/domain`, `application`, `interfaces`, `infrastructure`). Tests in `backend/tests/`.
- `sandbox/`: Isolated execution service (FastAPI + Docker). Tests in `sandbox/tests/`.
- `docs/`: Docs site assets and scripts (docsify).
- `mockserver/`, `searxng/`, `scripts/`: Tooling, local mocks, and search config.
- `src/` and `app/`: Additional agent/runtime modules; follow existing directory names for placement.
- Root `docker-compose*.yml`, `dev.sh`, `run.sh`, `build.sh` coordinate multi-service workflows.

## Build, Test, and Development Commands
- `./dev.sh up`: Start the full dev stack with `docker-compose-development.yml` (hot reload).
- `./dev.sh down -v`: Stop dev stack and remove volumes.
- `./run.sh up -d`: Start the production compose stack in the background.
- `./build.sh`: Build images via `docker buildx bake`.
- `backend/dev.sh`: Run backend with reload on port 8000.
- `frontend`:
  - `npm install`
  - `npm run dev` (local UI)
  - `npm run build` (production build)
  - `npm run type-check`
  - `npm run lint`

## Coding Style & Naming Conventions
- Python: 4-space indentation, `snake_case` modules/functions, `PascalCase` classes. Keep the DDD layering (`domain`, `application`, `interfaces`, `infrastructure`) intact.
- Vue/TypeScript: 2-space indentation in `.vue` SFCs, `PascalCase` component files, composables named `useX.ts`.
- Linting/formatting: Frontend uses ESLint (`frontend/eslint.config.js`). The sandbox image ships `black`, `isort`, `flake8`, `pylint`, and `mypy`; if you run Python formatting/linting locally, use defaults or add shared config in the same change, and avoid sweeping reformat-only diffs.

## Testing Guidelines
- Backend: `pytest` from `backend/` (pattern `test_*.py`). Example: `pytest tests/test_auth_routes.py`.
- Sandbox: `pytest` from `sandbox/` (same naming pattern).
- Frontend: `npm run test` or `npm run test:run` (Vitest). Specs live in `frontend/tests/**/*.spec.ts`.
- Coverage: optional via `npm run test:coverage` for the frontend.

## Commit & Pull Request Guidelines
- Commits follow short, imperative, sentence-case summaries (e.g., “Add Whoogle search…”, “Fix VNC viewer…”). Keep messages scoped to one change.
- PRs should include: a concise summary, key testing steps, linked issues (if any), and screenshots for UI changes. Call out any config or `.env` updates.

## Configuration & Secrets
- Copy `.env.example` to `.env` for local runs; do not commit secrets.
- MCP integration is configured via `mcp.json.example`.
