# Session Resilience & Docker Setup (Context7 Validated)

Robust configuration for session polling, rate limiting, and Chrome sandbox stability. All choices are based on authoritative documentation (FastAPI, Playwright, Docker) via Context7 MCP.

## Chrome / Sandbox Stability

**Issue**: Chrome reports `FATAL` in supervisord when `/dev/shm` is too small—Chromium can run out of shared memory and crash.

**Fix (Playwright Docker docs)**:
- `shm_size: '2gb'` — Selenium/Playwright recommend 2GB for Chromium containers
- Alternative for persistent crash: `ipc: host` (shares IPC namespace; use only in trusted dev environments)

**Applied in**:
- `docker-compose-development.yml` — sandbox service
- `docker-compose.yml` — sandbox, sandbox2
- `docker-compose.dokploy.yml` — sandbox, sandbox2
- `backend/app/core/config.py` — `sandbox_shm_size: "2g"` default

## Rate Limiting

**Issue**: Aggressive session polling triggers 429; clients need actionable `Retry-After`.

**Fix (FastAPI-Limiter convention)**:
- Accurate `Retry-After` header from Redis TTL (or in-memory window)
- Include `retry_after` in JSON body for programmatic use
- Exempt lightweight `GET /sessions/{id}/status` (high-freq, low-payload)

**Applied in**:
- `backend/app/main.py` — `RateLimitMiddleware`

## Frontend Polling

**Issue**: `waitForSessionReady` polls every 500ms; `getSession` is heavy.

**Fix**:
- Use `getSessionStatus` instead of `getSession` (lighter endpoint)
- Poll interval 2000ms (default)
- On 429: respect `Retry-After` header and wait before retry

**Applied in**:
- `frontend/src/pages/ChatPage.vue` — `waitForSessionReady(..., agentApi.getSessionStatus, { pollIntervalMs: 2000 })`
- `frontend/src/utils/sessionReady.ts` — 429 handling with `getRetryAfterMs()`

## References

- Playwright Docker: `--shm-size="2g"` for Chromium, `--ipc=host` to prevent OOM
- FastAPI-Limiter: `Retry-After` header, per-endpoint limits
- Docker: `shm_size`, `mem_limit` for container resource constraints
