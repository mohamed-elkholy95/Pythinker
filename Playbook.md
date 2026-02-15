# Pythinker Technical Playbook

Last validated: 2026-02-15
Scope: this document reflects what is currently implemented in this repository, not aspirational architecture.

## 1) Product and Runtime Model

Pythinker is a multi-service AI agent platform with:
- Vue 3 frontend for chat, session management, tool views, and takeover UI.
- FastAPI backend with DDD-inspired layering and SSE/WebSocket streaming endpoints.
- Dedicated sandbox containers for tool execution, browser automation, and VNC/CDP streaming.
- State/storage split across MongoDB, Redis (runtime + cache), Qdrant, and MinIO.
- Optional monitoring stack (Prometheus, Grafana, Loki, Promtail).

## 2) Canonical Stack Inventory

### Frontend (`frontend/`)
- Framework: `vue@^3.5.27`
- Router: `vue-router@^4.6.4`
- i18n: `vue-i18n@^11.2.8`
- Build tool: `vite@^7.3.1`
- TypeScript: `typescript@^5.9.3`
- Styling: `tailwindcss@^4.1.18`, `@tailwindcss/vite@^4.1.18`, `@tailwindcss/typography@^0.5.16`
- Linting: `eslint@^9.39.2`, `eslint-plugin-vue@^10.7.0`, `@vue/eslint-config-typescript@^14.6.0`
- Testing: `vitest@^3.2.0`, `@vitest/coverage-v8@^3.2.0`, `happy-dom@^18.0.1`, `@vue/test-utils@^2.4.6`
- Streaming/network: `@microsoft/fetch-event-source@^2.0.1`, `axios@^1.13.2`
- Interactive UI/tooling libs:
  - Terminal: `xterm@^5.3.0`, `@xterm/addon-fit@^0.9.0`
  - Remote browser: `@novnc/novnc@^1.5.0`
  - Editor/highlight: `monaco-editor@^0.55.1`, `shiki@^3.22.0`
  - Rich text: Tiptap v3 modules (`@tiptap/*@^3.17.0`)
  - Visualization/canvas: `plotly.js-dist-min@^3.3.1`, `vue-plotly@^1.1.0`, `konva@^10.2.0`, `vue-konva@^3.3.0`

### Backend (`backend/`)
- Python baseline: `requires-python >=3.11` (Ruff target `py311`)
- API framework: `fastapi[standard]>=0.115.0`, `uvicorn>=0.32.0`
- Validation/config: `pydantic>=2.9.0`, `pydantic-settings>=2.6.0`
- Streaming and sockets: `sse-starlette>=2.1.0`, `websockets>=13.1`, `httpx>=0.28.1`
- Data/DB:
  - MongoDB ODM/driver: `beanie>=1.27.0`, `motor>=3.6.0`, `pymongo>=4.10.0`
  - Redis: `redis>=5.2.0`
  - Vector DB: `qdrant-client>=1.12.0`
  - Object storage: `minio>=7.2.0`
- AI/LLM and retrieval:
  - LLM SDK: `openai>=2.7.2`
  - Browser agent: `playwright>=1.48.0`, `browser-use>=0.11.0`
  - Retrieval/reranking: `sentence-transformers>=3.0.0`, `torch>=2.2.0`, `rank-bm25>=0.2.2`, `numpy>=1.24.0`
- Security/auth/logging:
  - Auth/JWT/crypto: `pyjwt[crypto]>=2.9.0`, `cryptography>=43.0.0`, `pyotp>=2.9.0`
  - Structured logging: `structlog>=24.4.0`
- MCP protocol client/server support: `mcp>=1.9.0`

### Infrastructure and Services (Docker Compose)
- Core services:
  - `frontend`
  - `backend`
  - `sandbox`
  - `sandbox2`
  - `mongodb` (`mongo:7.0`)
  - `redis` (`redis:8.4-alpine`)
  - `redis-cache` (`redis:8.4-alpine`)
  - `qdrant` (`qdrant/qdrant:v1.16.3`)
  - `minio` (`minio/minio:latest`)
- Monitoring profile/services:
  - `prometheus`
  - `grafana`
  - `loki`
  - `promtail`
  - `redis-exporter`
  - `redis-cache-exporter`

### Sandbox Runtime (`sandbox/`)
- Base OS: Ubuntu 22.04 (multi-stage Docker build)
- Python runtime: 3.11 (venv at `/opt/base-python-venv`)
- Node runtime: Node.js 22.13.0 (via NVM), pnpm 10.29.2
- Browser stack:
  - Playwright browsers installed in image
  - Chromium-first runtime pathing for sandbox use
  - Optional Chrome for Testing handling
- Display/remote control stack:
  - `xvfb`, `x11vnc`, `websockify`, `openbox`, `supervisord`
- Security posture in compose profile:
  - `no-new-privileges`
  - seccomp profile (`sandbox/seccomp-sandbox.json`)
  - `cap_drop: ALL` with minimal add-backs
  - tmpfs mounts + resource limits + health checks

## 3) Architecture and Layering

Backend structure aligns with DDD-style layering:
- `app/domain`: core domain models, interfaces, services, orchestration, tools
- `app/application`: use-case orchestration and application-level services
- `app/infrastructure`: adapters, external integrations, repositories, storage, observability
- `app/interfaces`: HTTP/SSE/WebSocket API routes, schemas, dependency wiring

Primary API composition is in `backend/app/interfaces/api/routes.py` and mounted by `backend/app/main.py`.

## 4) Communication Patterns

### HTTP + SSE
- Chat/session event streaming is implemented via `EventSourceResponse` in `backend/app/interfaces/api/session_routes.py`.
- SSE protocol headers and heartbeat/retry metadata are explicitly handled in route helpers.
- Frontend consumes SSE with both:
  - `fetch-event-source` transport
  - native `EventSource` transport for resumable/signed URL paths

### WebSockets
- WebSocket proxy routes for sandbox interaction:
  - `/sessions/{session_id}/vnc`
  - `/sessions/{session_id}/screencast`
  - `/sessions/{session_id}/input`
- Frontend uses signed URLs and browser WebSocket clients for takeover and streaming input.

## 5) Persistence and Data Topology

- Document/session/auth domain state: MongoDB via Beanie/Motor.
- Runtime coordination + queues + rate limiting + token revocation: Redis.
- Cache isolation: separate Redis instance (`redis-cache`) for eviction control.
- Vector memory/search artifacts: Qdrant.
- Binary/object artifacts (files/screenshots/presigned URLs): MinIO.

## 6) Build, Quality, and Test Baseline

### Frontend
- Lint: `cd frontend && bun run lint`
- Type check: `cd frontend && bun run type-check`
- Tests: `cd frontend && bun run test:run`

### Backend
- Lint: `conda activate pythinker && cd backend && ruff check .`
- Format check: `conda activate pythinker && cd backend && ruff format --check .`
- Tests: `conda activate pythinker && cd backend && pytest tests/`

### CI (`.github/workflows/test-and-lint.yml`)
- Backend jobs:
  - Ruff lint + format check
  - Pytest suite
  - `pip-audit` (non-blocking via `continue-on-error: true`)
- Frontend jobs:
  - ESLint (`bun run lint:check`)
  - Type check (`bun run type-check`)
  - Vitest (`bun run test:run`)

## 7) Deployment Profiles

- Local development: `docker-compose-development.yml`
- Standard container deployment: `docker-compose.yml`
- Dokploy-oriented deployment: `docker-compose.dokploy.yml`
- Monitoring overlay: `docker-compose-monitoring.yml`

Operational notes:
- Backend requires Docker socket mount to provision/manage sandbox containers.
- Frontend runs behind nginx in containerized profile.
- Dev frontend uses Vite HMR and optional polling settings.

## 8) MCP and Tooling Ecosystem

`mcp.json` defines available MCP servers and enablement states.
Enabled by default in current config:
- `filesystem`
- `git`
- `memory`
- `fetch`
- `sequential-thinking`

Disabled but configured examples include GitHub, Redis, MongoDB, Playwright, Puppeteer, Docker MCP, shell MCP, and custom HTTP endpoints.

## 9) Non-Core / Not Canonical in Current Runtime

- PostgreSQL is present as an optional MCP config example, not as a core runtime service.
- There is no single dedicated SQL primary datastore in active compose stacks.
- State management on frontend is composable/router driven; no Pinia dependency is currently installed.

## 10) Context7 Validation Notes

Validated against Context7 docs during this update:
- FastAPI (`/fastapi/fastapi`): WebSocket endpoint patterns and dependency-based WebSocket auth/validation align with current backend approach.
- Vue 3 (`/vuejs/docs`): `createApp` + SFC + TypeScript (`<script setup lang=\"ts\">`) conventions align with current frontend setup.
- Tailwind CSS (`/tailwindlabs/tailwindcss.com`): Vite plugin integration and CSS-first directives (`@import`, `@source`) align with current frontend config.

## 11) Source-of-Truth Files Used for Validation

- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/tsconfig.app.json`
- `frontend/src/main.ts`
- `frontend/src/assets/global.css`
- `backend/requirements.txt`
- `backend/pyproject.toml`
- `backend/app/main.py`
- `backend/app/interfaces/api/routes.py`
- `backend/app/interfaces/api/session_routes.py`
- `docker-compose.yml`
- `docker-compose-development.yml`
- `docker-compose.dokploy.yml`
- `docker-compose-monitoring.yml`
- `sandbox/Dockerfile`
- `.github/workflows/test-and-lint.yml`
- `mcp.json`

## 12) Maintenance Rule

When adding/changing stack elements, update this playbook in the same PR as:
- dependency file changes (`package.json`, `requirements*.txt`, `pyproject.toml`)
- compose/runtime changes (`docker-compose*.yml`, `Dockerfile*`)
- protocol changes (SSE/WebSocket endpoints and frontend transport code)

