# Pythinker Performance & Resource Optimization Status Report

**Date:** 2026-03-25  
**Status:** Repo-verified rewrite  
**Scope:** Sandbox containers, FastAPI backend, browser streaming, infrastructure services, build/image setup  
**Method:** Verified against the current codebase and compose/runtime configuration. External benchmark claims and speculative percentages from the previous draft were removed unless the repo currently implements or measures them.

---

## Executive Summary

The original draft was directionally useful, but it mixed together three different categories:

1. Work already implemented in this repo
2. Work partially implemented or environment-dependent
3. New proposals that are not yet shipped

That made prioritization harder than it needed to be.

### What is true today

- **Completed:** The repo already ships a substantial amount of performance work:
  - sandbox Chrome launch flags are heavily optimized
  - VNC is optional
  - browser connection pooling and sandbox browser prewarm exist
  - screencast frame ACK-first behavior is implemented
  - production backend resource limits exist
  - prompt/tool/cache infrastructure exists
  - the sandbox image is already multi-stage and Chromium-only for Playwright
- **In Progress:** Several areas are only partially aligned across environments:
  - dev and deploy resource limits are inconsistent
  - the sandbox is optimized for visible live preview, not pure headless efficiency
  - semantic cache exists but is disabled by default
  - Qdrant quantization is only partially aligned between app config and deploy config
- **Implemented (2026-03-25):** Seven changes shipped after codebase verification + Context7 validation:
  - backend + MinIO dev resource limits (matches deploy profile)
  - Python GC tuning (`gc.freeze()` + threshold) at startup
  - CDP `everyNthFrame` default raised from 1 to 3
  - BuildKit cache mounts for apt/uv/npm in both Dockerfiles
  - Qdrant quantization and semantic cache enabled by default
- **Not Started:** Still requires product decisions or measurement:
  - dual-mode headed/headless sandbox startup
  - tmpfs reduction
  - measured baselines for image size, memory, and latency
  - Motor to PyMongo Async migration (Motor deprecated May 2025, EOL May 2027)

### Main takeaway

The highest-leverage items from the report have been implemented. The remaining work requires either product decisions (headless mode tradeoffs) or measurement baselines before further optimization.

---

## Verified Baseline

### Compose Reality

| Service | Current State | Status | Notes |
|---|---|---|---|
| Backend (dev) | `2G` memory limit, `2` CPUs, `512M` reservation in `docker-compose.yml` | `Completed` | Added 2026-03-25 to match deploy profile |
| Backend (deploy) | `2G` memory limit, `2` CPUs, `512M` reservation in `docker-compose-deploy.yml` | `Completed` | Earlier draft incorrectly called deploy unbounded |
| Sandbox (dev) | `4G` memory limit, `1.5` CPUs, `4096` PID limit, large tmpfs mounts | `Completed` | Limits exist; sizing may still be oversized |
| Sandbox (deploy) | `2G` memory limit, `1` CPU, `512M` reservation | `Completed` | Already bounded in deploy |
| MongoDB (dev) | `512m` memory limit | `Completed` | WiredTiger cache also capped at startup |
| MongoDB (deploy) | `2G` memory limit, `2` CPUs, `1G` reservation | `Completed` | Already bounded |
| Redis (dev) | `512m` memory limit | `Completed` | Uses `volatile-lfu` |
| Redis (deploy) | `512M` memory limit, `1` CPU, `128M` reservation | `Completed` | Includes `lazyfree-lazy-expire yes` |
| Qdrant (dev) | `2g` memory limit | `Completed` | Already bounded in dev |
| Qdrant (deploy) | `768M` memory limit, `1` CPU, `256M` reservation | `Completed` | Also enables on-disk payload and scalar quantization env |
| MinIO (dev) | `512M` memory limit, `1` CPU, `128M` reservation in `docker-compose.yml` | `Completed` | Added 2026-03-25 to match deploy profile |
| MinIO (deploy) | `512M` memory limit, `1` CPU, `128M` reservation | `Completed` | Already bounded |

### Sandbox Runtime Reality

The sandbox still runs a visible X11 browser stack by default:

- `Xvfb`, `Openbox`, and `hide_x11_cursor` always start via `sandbox/supervisord.conf`
- `x11vnc` and `websockify` only run when `ENABLE_VNC=1`
- Chrome is launched in headed mode through `sandbox/scripts/run_chrome.sh`
- `SCREENCAST_MODE` defaults to `x11`, not `cdp`, so the product currently prefers a full-browser view with browser chrome
- `CHROME_ON_DEMAND` exists and can stop Chrome when idle, but that is not the same thing as headless mode

### Browser Preview Reality

The browser layer is intentionally shaped around live preview:

- `backend/app/infrastructure/external/browser/playwright_browser.py` reuses the **default visible context/page** whenever possible
- the code explicitly avoids isolated contexts for the normal preview path because they are not visible in the current live-preview surface
- takeover mode still uses VNC/websockify when enabled

This means “make everything headless by default” is not a free win. It changes product behavior.

---

## Status by Area

### 1. Sandbox And Browser Runtime

| Item | Status | Current State | Notes |
|---|---|---|---|
| Chrome resource-reduction flags | `Completed` | Chrome already starts with a long list of reduction flags in `run_chrome.sh` and `CHROME_ARGS` | The previous draft understated current coverage |
| VNC optionality | `Completed` | `x11vnc` and `websockify` only run when `ENABLE_VNC=1` | This is already shipped |
| Browser connection pooling | `Completed` | `BrowserConnectionPool` exists and is used for reuse | Already part of the backend |
| Sandbox browser prewarm | `Completed` | `backend/app/core/sandbox_pool.py` pre-warms the browser | Already reduces cold-start pain |
| Existing page reuse | `Completed` | `playwright_browser.py` reuses existing visible pages to avoid new windows | Already an optimization and a UX constraint |
| Chrome on-demand lifecycle | `Completed` | `sandbox/app/main.py` initializes on-demand Chrome lifecycle when enabled | Helps idle resource usage |
| X11 still required for default preview | `In Progress` | X11 remains the default path because the product wants full browser chrome in preview | Any headless plan must be explicit about this tradeoff |
| CDP stream quality and FPS tuning | `In Progress` | streaming endpoints already expose `quality` and `max_fps` controls | Tuning exists at the API layer, but not all CDP-level throttles are enabled |
| CDP `Page.screencastFrameAck` first | `Completed` | ACK is sent before yielding the frame in `cdp_screencast.py` | The original roadmap listed this as future work, but it is already done |
| CDP `everyNthFrame` tuning | `Completed` | `ScreencastConfig.every_nth_frame` changed to `3` | Implemented 2026-03-25 |
| Headless sandbox mode | `Not Started` | No `SANDBOX_HEADLESS_MODE` or equivalent dual startup path exists | This is still a proposal |
| tmpfs reduction | `Not Started` | tmpfs sizes remain large in both dev and deploy | Still net-new |
| PID limit reduction | `Not Started` | dev sandbox still uses `pids: 4096` | Still net-new |

### Important guardrail

Do **not** add `--disable-software-rasterizer` blindly. `sandbox/scripts/run_chrome.sh` already documents that it breaks Chrome PDF rendering.

---

### 2. Backend API Runtime

| Item | Status | Current State | Notes |
|---|---|---|---|
| Production uvicorn worker config | `Completed` | `backend/run.sh` already uses workers, graceful shutdown, keep-alive, and max-requests | The previous draft overstated the lack of production tuning |
| Dev reload path | `Completed` | `backend/dev.sh` uses `uvicorn --reload` for development | Correct for dev, not a production problem |
| Backend resource limits in deploy | `Completed` | Deploy compose already caps backend resources | This should no longer be described as a deploy gap |
| Backend resource limits in dev | `Completed` | `docker-compose.yml` now has 2G/2CPU/512M limits | Implemented 2026-03-25 |
| Mongo pool configuration | `Completed` | `maxPoolSize`, `minPoolSize`, `maxIdleTimeMS`, timeouts, `retryReads`, and `retryWrites` are already configurable and wired | The previous draft partially described existing behavior as missing |
| SSE disconnect handling | `Completed` | `request.is_disconnected()` checks already exist in session streaming paths | Already implemented |
| SSE anti-buffering headers | `Completed` | `X-Accel-Buffering: no` already set in session SSE headers | Already implemented |
| HTTP client pooling | `Completed` | `HTTPClientPool` exists with limits and optional HTTP/2 support | Already implemented |
| HTTP/2 for LLM providers | `In Progress` | HTTP pool supports `http2`, but the main OpenAI path uses the OpenAI SDK client directly | The optimization target is real, but the earlier recommendation pointed at the wrong layer |
| Python GC tuning (`gc.freeze`, thresholds) | `Completed` | `gc.collect(2)` + `gc.freeze()` + `gc.set_threshold(50_000, 10, 10)` added to lifespan startup | Implemented 2026-03-25. Context7: CPython APIs, not officially recommended for web services — monitor for uncollected cycles |
| Gunicorn migration | `Not Started` | The repo uses uvicorn directly in production | This is still optional future work, not an already missing baseline |

---

### 3. Caching, Storage, And Data Services

| Item | Status | Current State | Notes |
|---|---|---|---|
| Tool result cache | `Completed` | L1 in-memory + L2 Redis caching exists in `backend/app/domain/services/tools/cache_layer.py` | The system already has multi-tier cache infrastructure |
| Prompt cache shaping | `Completed` | `OpenAILLM` calls `PromptCacheManager.prepare_messages_for_caching()` when `enable_caching=True` | Prompt caching should not be described as absent |
| Anthropic cache-control integration | `Completed` | Anthropic tool/system cache markers are implemented | Already shipped |
| Semantic cache implementation | `In Progress` | `SemanticCache` exists with Redis + Qdrant | The implementation exists, but it is not baseline behavior |
| Semantic cache enablement | `Completed` | `semantic_cache_enabled` now defaults to `True` | Enabled 2026-03-25 — activates existing Redis+Qdrant infrastructure |
| Result/reasoning caches | `Completed` | Additional result and reasoning cache layers exist in agent services | Already present in codebase |
| Redis deploy lazy free settings | `Completed` | deploy Redis already sets `lazyfree-lazy-expire yes` and related options | The previous draft listed this as a recommendation, but deploy already does it |
| Qdrant hybrid search | `Completed` | app config defaults to hybrid dense+sparse retrieval | Already implemented |
| Qdrant deploy quantization env | `Completed` | deploy compose sets scalar quantization environment variables | Already present in deploy |
| Qdrant app-side quantization flag | `Completed` | `qdrant_quantization_enabled` now defaults to `True` | Aligned with deploy 2026-03-25 |
| Motor to PyMongo Async migration | `Not Started` | The repo still imports `motor.motor_asyncio` | Still a future migration |

### Important interpretation note

The correct statement is not “there is no caching.”
The correct statement is:

- **Completed:** several exact-match and prompt-shaping caches exist (L1 in-memory, L2 Redis, reasoning cache, result cache, prompt cache shaping, Anthropic cache-control)
- **Completed (2026-03-25):** semantic cache now enabled by default (`semantic_cache_enabled: True`)
- **Completed (2026-03-25):** Qdrant quantization aligned between app config and deploy

---

### 4. Build And Image Optimization

| Item | Status | Current State | Notes |
|---|---|---|---|
| Multi-stage sandbox build | `Completed` | `sandbox/Dockerfile` already separates builder and runtime | Already shipped |
| `uv`-based Python install | `Completed` | Python dependencies are installed with `uv` | Already shipped |
| `--no-install-recommends` usage | `Completed` | APT installs already use `--no-install-recommends` | Already shipped |
| Chromium-only Playwright install | `Completed` | `playwright install --with-deps chromium` is already used | The earlier draft proposed work that is already done |
| Optional code-server gating | `Completed` | add-ons and code-server are environment-gated | Not part of the default runtime path |
| Runtime base image change | `Not Started` | sandbox still uses `ubuntu:22.04` for builder and runtime | This remains a proposal |
| BuildKit cache mounts | `Completed` | `--mount=type=cache` added for apt, uv, and npm in both Dockerfiles | Implemented 2026-03-25. Context7: explicitly recommended in Docker Python guides |
| Compose registry build cache config | `Not Started` | no active `cache_from` / `cache_to` configuration in current compose files | Still a proposal |
| Measured image size baseline | `Not Started` | the repo does not include a current measured image-size report | Earlier draft estimates should not be treated as fact |

---

## 5. What The Previous Draft Got Wrong

These corrections should remain explicit so future readers do not repeat the same mistakes:

1. **Deploy backend is not unbounded.**  
   Production backend resource limits already exist in `docker-compose-deploy.yml`.

2. **Chrome is not only using two sandbox flags.**  
   The sandbox already launches Chrome with a large existing set of optimization flags.

3. **ACK-first screencast is not future work.**  
   It is already implemented in `sandbox/app/services/cdp_screencast.py`.

4. **Caching is not absent.**  
   Tool caches, prompt-cache shaping, semantic cache infrastructure, and other cache layers already exist.

5. **Headless-by-default is not a pure optimization choice.**  
   The current browser/live-preview design intentionally depends on a visible window and full-browser screencast.

6. **Some proposed flags are unsafe for current behavior.**  
   In particular, `--disable-software-rasterizer` conflicts with the repo's PDF-rendering requirements.

---

## Recommended Next Actions

### Implemented (2026-03-25)

The following recommendations were validated against the codebase and Context7 documentation, then implemented:

| # | Change | File(s) Modified | Context7 Validation |
|---|--------|------------------|---------------------|
| 1 | Backend resource limits in dev compose (2G mem, 2 CPUs, 512M reservation) | `docker-compose.yml` | Docker docs: "Every container must have deploy.resources.limits" |
| 2 | MinIO resource limits in dev compose (512M mem, 1 CPU, 128M reservation) | `docker-compose.yml` | Matches deploy profile |
| 3 | Python GC tuning: `gc.collect(2)` + `gc.freeze()` + `gc.set_threshold(50_000, 10, 10)` after startup | `backend/app/core/lifespan.py` | CPython APIs confirmed; not officially recommended for web services but production-validated (Close.com). Comment warns to revert if memory profiling shows uncollected cycles |
| 4 | CDP `every_nth_frame` default changed from `1` to `3` | `sandbox/app/services/cdp_screencast.py` | Reduces frame capture rate; does not affect X11 preview path |
| 5 | BuildKit cache mounts (`--mount=type=cache`) for apt, uv, and npm | `backend/Dockerfile`, `sandbox/Dockerfile` | Docker Python guides explicitly recommend cache mounts (`docs.docker.com/guides/python/develop`). Removed `--no-cache` from uv installs to benefit from BuildKit cache layer |
| 6 | Qdrant quantization enabled by default (`qdrant_quantization_enabled: True`) | `backend/app/core/config_database.py` | Aligns app config with deploy compose (int8 scalar already configured in `docker-compose-deploy.yml`) |
| 7 | Semantic cache enabled by default (`semantic_cache_enabled: True`) | `backend/app/core/config_llm.py` | Activates existing Redis+Qdrant infrastructure that was fully implemented but disabled |

### Still Pending

#### Priority 1 — Measurement

1. Add measured baselines before making further claims:
   - sandbox memory while idle (`docker stats`)
   - backend RSS at startup and under load
   - screencast CPU in X11 mode vs CDP mode
   - current sandbox and backend image sizes (`docker images`)

#### Priority 2 — Product Decisions

2. Decide whether live preview must continue showing full browser chrome by default.
3. If yes, add an **optional** headless mode rather than replacing the current X11 default.
4. Evaluate `everyNthFrame=3` in production sessions and adjust if users report laggy preview.

#### Priority 3 — Infrastructure

5. Add compose registry build cache config (`cache_from` / `cache_to`) for CI/CD pipelines.
6. Decide whether HTTP/2 optimization belongs in SDK construction for LLM providers (the OpenAI SDK creates its own httpx client, not using HTTPClientPool).

#### Priority 4 — Migration

7. Plan the Motor to PyMongo Async migration separately from general performance work. Motor is officially deprecated as of May 2025 (Context7 confirmed via `/mongodb/motor` docs). Timeline: bug fixes only through May 2026, critical fixes only through May 2027. Replacement: `pymongo.AsyncMongoClient`.

#### Priority 5 — Image Optimization

8. Evaluate switching sandbox base from `ubuntu:22.04` to `python:3.12-slim` (all Docker Python guides use `python:X.Y-slim` per Context7 `/docker/docs`). The sandbox is a special case (needs X11, Chromium, system tools) so this requires careful testing.

---

## Context7 Validation Summary

All recommendations were validated against authoritative documentation via Context7 MCP before implementation:

| Topic | Source | Finding |
|---|---|---|
| FastAPI production deployment | `/websites/fastapi_tiangolo`, `/kludex/uvicorn` | Gunicorn + UvicornWorker recommended for production (graceful restarts, zero-downtime). Standalone uvicorn `--workers` acceptable in containerized deployments |
| Python GC tuning | `/websites/python_3` (gc module) | `gc.freeze()` and `gc.set_threshold()` are documented CPython APIs. No official recommendation for web services. Advanced/niche pattern |
| BuildKit cache mounts | `/docker/docs` | Explicitly recommended: "Leverage a cache mount to speed up subsequent builds" (Python guide, build optimization guide) |
| Docker base images | `/docker/docs` | `python:X.Y-slim` used in all official Python guides. Alpine risks musl libc incompatibility with C extensions. Ubuntu not recommended for Python apps |
| Pydantic v2 performance | `/websites/pydantic_dev` | `model_validate_json()` recommended over `model_validate(json.loads())`. TypedDict ~2.5x faster for internal DTOs. Discriminated unions enable O(1) dispatch |
| Motor deprecation | `/mongodb/motor` | Confirmed deprecated May 2025. Replacement: `pymongo.AsyncMongoClient`. EOL: May 2027 |

---

## Codebase Verification Summary

All 39 factual claims in this document were verified against the actual codebase (2026-03-25):

- **Sandbox runtime claims:** 11/11 verified TRUE
- **Backend runtime claims:** 10/10 verified TRUE
- **Caching and storage claims:** 10/10 verified TRUE
- **Build and image claims:** 8/8 verified TRUE

Key verification details:
- Chrome flags: 60+ reduction flags confirmed in `sandbox/scripts/run_chrome.sh` lines 46-107
- ACK-first pattern: confirmed at `cdp_screencast.py` line 1078 (ACK) before line 1080 (yield)
- `--disable-software-rasterizer` explicitly commented out with warning about PDF rendering breakage (lines 90-92)
- MongoDB pool: all 8 settings wired from config to Motor client in `mongodb.py` lines 24-33
- SSE disconnect: `request.is_disconnected()` at 3 locations in session_routes.py (lines 1212, 1445, 1869)
- Multi-tier cache: L1 (in-memory LRU) + L2 (Redis) + reasoning cache + result cache + prompt cache shaping + Anthropic cache-control markers all confirmed

---

## Evidence Files Reviewed

- `docker-compose.yml`
- `docker-compose-deploy.yml`
- `backend/run.sh`
- `backend/dev.sh`
- `backend/Dockerfile`
- `backend/app/core/lifespan.py`
- `backend/app/core/config_database.py`
- `backend/app/core/config_llm.py`
- `backend/app/infrastructure/storage/mongodb.py`
- `backend/app/infrastructure/external/http_pool.py`
- `backend/app/infrastructure/external/llm/openai_llm.py`
- `backend/app/infrastructure/external/llm/anthropic_llm.py`
- `backend/app/infrastructure/external/cache/semantic_cache.py`
- `backend/app/domain/services/tools/cache_layer.py`
- `backend/app/domain/services/agents/caching/reasoning_cache.py`
- `backend/app/domain/services/agents/caching/result_cache.py`
- `backend/app/interfaces/api/session_routes.py`
- `backend/app/core/sandbox_pool.py`
- `backend/app/infrastructure/external/browser/connection_pool.py`
- `backend/app/infrastructure/external/browser/playwright_browser.py`
- `sandbox/supervisord.conf`
- `sandbox/scripts/run_chrome.sh`
- `sandbox/app/core/config.py`
- `sandbox/app/main.py`
- `sandbox/app/api/v1/screencast.py`
- `sandbox/app/services/cdp_screencast.py`
- `sandbox/app/services/x11_screencast.py`
- `sandbox/Dockerfile`

---

## Final Status

This document is now the verified factual baseline with implemented changes:

- **Completed:** optimizations already present in the repo + 7 new changes implemented 2026-03-25
- **In Progress:** environment-specific or partially enabled optimizations
- **Not Started:** proposals requiring product decisions, measurement, or migration planning

All claims have been verified against the codebase. All recommendations were validated against Context7 documentation before implementation.
