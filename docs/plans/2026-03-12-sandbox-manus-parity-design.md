# Sandbox Enhancement Design — Full Manus Parity

**Date:** 2026-03-12
**Status:** Approved
**Scope:** 7 phases, ~5 new files, ~22 modified files

## Background

Analysis of the Manus sandbox environment (`7.0.30`) revealed significant architectural capabilities
that Pythinker's sandbox lacks. This design brings Pythinker's sandbox to feature parity with Manus
across 7 independently deployable phases.

### Key Gaps Identified

| Category | Manus | Pythinker (Current) |
|---|---|---|
| Terminal parsing | `[CMD_BEGIN]`/`[CMD_END]` structured markers | Unstructured PS1, implicit boundary detection |
| LLM access | OpenAI proxy inside sandbox | No LLM access in sandbox |
| Bidirectional comms | `RUNTIME_API_HOST` callback | One-way (backend → sandbox only) |
| IDE | code-server (VS Code web) | Not integrated (detected only) |
| Observability | Full OTEL + Sentry | Stdlib logging only |
| Encoding/locale | `PYTHONIOENCODING=utf-8`, `LANG=C.UTF-8`, `TZ` | Not set |
| Cloud tokens | `GH_TOKEN`, Google Drive/Workspace | Per-request git token only |

## Design Principles

1. **Feature-flagged:** Every phase is gated by env vars. Default = off (no behavioral change).
2. **Backward compatible:** Old sandbox images work with new backends and vice versa.
3. **Self-hosted first:** No external dependencies. LLM proxy goes through our backend, not direct API.
4. **Security-first:** No real API keys in sandbox. All auth via scoped JWTs or backend proxy.
5. **Incremental:** Each phase is independently deployable and testable.

---

## Phase 1: Environment Polish

**Goal:** Match Manus's env var hygiene — encoding safety, timezone, locale, version tracking.

**Rationale:** `PYTHONIOENCODING=utf-8` prevents encoding crashes when agents write non-ASCII.
`LANG=C.UTF-8` ensures consistent locale. `TZ` prevents timezone confusion in logs/timestamps.
`PW_TEST_SCREENSHOT_NO_FONTS_READY=1` skips Playwright font-ready waits.

### Changes

**`sandbox/Dockerfile` (runtime stage):**
```dockerfile
ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8
ENV PW_TEST_SCREENSHOT_NO_FONTS_READY=1
```

**`docker-compose*.yml` (sandbox service environment):**
```yaml
- TZ=${TZ:-UTC}
- SANDBOX_VERSION=${IMAGE_TAG:-dev}
```

**`sandbox/app/core/config.py`:**
```python
SANDBOX_VERSION: str = "dev"
TZ: str = "UTC"
```

**`sandbox/scripts/generate_sandbox_context.py`:**
- Include `SANDBOX_VERSION` and `TZ` in system info section.

### Impact
- Zero breaking changes
- Pure additive
- No feature flag needed (these are always-on env defaults)

---

## Phase 2: Structured Terminal Markers

**Goal:** Add `[CMD_BEGIN]`/`[CMD_END]` PS1 markers for reliable command output boundary parsing.

**Rationale:** Currently the backend relies on session-level output accumulation and ConsoleRecord
tracking. Boundary detection is implicit (EOF/returncode). Structured markers give the backend a
clear, parseable boundary between commands — exactly how Manus does it.

### Marker Format

```
[CMD_BEGIN]ubuntu@sandbox:~/workspace $  ls -la
total 8
-rw-r--r-- 1 ubuntu ubuntu  0 Mar 12 00:00 file.txt
[CMD_END]
```

The PS1 prompt becomes: `\n{user}@{host}:{path}\n[CMD_END]`

When the shell service prepends a command to the output, it prefixes with `[CMD_BEGIN]`.

### Changes

**`sandbox/app/services/shell.py`:**
```python
CMD_BEGIN_MARKER = "[CMD_BEGIN]"
CMD_END_MARKER = "[CMD_END]"

def _format_ps1(self, exec_dir: str) -> str:
    if not settings.SHELL_USE_STRUCTURED_MARKERS:
        # Legacy format
        username = getpass.getuser()
        hostname = socket.gethostname()
        display_path = self._get_display_path(exec_dir)
        return f"{username}@{hostname}:{display_path} $"

    # Manus-style structured format
    username = getpass.getuser()
    hostname = socket.gethostname()
    display_path = self._get_display_path(exec_dir)
    return f"\n{username}@{hostname}:{display_path}\n{CMD_END_MARKER}"
```

In `exec_command()`, prepend `CMD_BEGIN_MARKER` before the PS1+command in output:
```python
header = f"{CMD_BEGIN_MARKER}{ps1} {command}\n"
```

**`sandbox/app/models/shell.py`:**
```python
class ConsoleRecord(BaseModel):
    ps1: str
    command: str
    output: str = Field(default="")
    exit_code: Optional[int] = None  # NEW: capture per-command exit code
```

**`backend/app/domain/services/tools/shell.py`:**
```python
CMD_BEGIN = "[CMD_BEGIN]"
CMD_END = "[CMD_END]"

def _parse_structured_output(self, raw: str) -> str:
    """Extract clean output from structured markers if present."""
    if CMD_BEGIN not in raw:
        return raw  # Fallback: old sandbox without markers

    # Split on markers, extract content between CMD_BEGIN and CMD_END
    blocks = []
    for block in raw.split(CMD_BEGIN):
        if not block.strip():
            continue
        if CMD_END in block:
            content, _ = block.rsplit(CMD_END, 1)
            blocks.append(content)
        else:
            blocks.append(block)
    return "\n".join(blocks)
```

**`sandbox/app/core/config.py`:**
```python
SHELL_USE_STRUCTURED_MARKERS: bool = True
```

### Backward Compatibility
- Feature-flagged via `SHELL_USE_STRUCTURED_MARKERS`
- Backend parser falls back to raw output when markers are absent
- Old sandbox images → no markers → backend uses existing logic

---

## Phase 3: Sandbox → Backend Callback (RUNTIME_API_HOST)

**Goal:** Enable bidirectional communication — sandbox can notify the backend of events.

**Rationale:** Currently the sandbox is a passive target. Manus's sandbox can call back to
`https://api.manus.im` for event reporting, resource requests, and progress updates. This
enables the sandbox to report crashes, OOM events, and completion signals proactively.

### Architecture

```
Backend                              Sandbox
   │                                    │
   │──── exec_command ────────────────>│
   │                                    │
   │<──── POST /callback/event ────────│  (crash, OOM, timeout)
   │<──── POST /callback/progress ─────│  (step completion)
   │<──── POST /callback/request ──────│  (file upload URL, secret)
   │                                    │
```

### Callback API (Backend-Side, New Routes)

```
POST /api/v1/sandbox/callback/event
  Body: { "type": "crash"|"oom"|"timeout"|"ready", "details": {...}, "session_id": "..." }
  Auth: X-Sandbox-Callback-Token (scoped JWT)

POST /api/v1/sandbox/callback/progress
  Body: { "session_id": "...", "step": "...", "percent": 50, "message": "..." }
  Auth: X-Sandbox-Callback-Token

POST /api/v1/sandbox/callback/request
  Body: { "type": "upload_url"|"secret", "params": {...} }
  Auth: X-Sandbox-Callback-Token
  Response: { "url": "...", "expires_in": 3600 }
```

### Changes

**New: `sandbox/app/services/callback.py`**
- `CallbackClient` class using `httpx.AsyncClient` (lightweight — sandbox doesn't have HTTPClientPool)
- Methods: `report_event()`, `report_progress()`, `request_resource()`
- No-op when `RUNTIME_API_HOST` is unset
- Fire-and-forget with 5s timeout (sandbox doesn't block on callback delivery)

**New: `backend/app/interfaces/api/sandbox_callback_routes.py`**
- FastAPI router with 3 endpoints
- JWT validation middleware (sandbox-scoped tokens only)
- Events forwarded to `AgentService` for session correlation
- Rate-limited: 60 requests/minute per sandbox

**Modified: `docker-compose*.yml`**
```yaml
# sandbox service environment
- RUNTIME_API_HOST=${RUNTIME_API_HOST:-http://backend:8000}
- RUNTIME_API_TOKEN=${SANDBOX_CALLBACK_TOKEN:-}
```

**Modified: `sandbox/app/core/config.py`**
```python
RUNTIME_API_HOST: Optional[str] = None
RUNTIME_API_TOKEN: Optional[str] = None
```

**Modified: `backend/app/core/config_sandbox.py`**
```python
sandbox_callback_enabled: bool = False
sandbox_callback_token: Optional[str] = None
```

### Security
- Sandbox gets a scoped JWT (not a general auth token)
- JWT claims: `{"sub": "sandbox", "sandbox_id": "...", "scope": "callback"}`
- Backend validates: issuer, expiry, scope claim
- Rate-limited to prevent abuse

---

## Phase 4: LLM Proxy Inside Sandbox

**Goal:** Let code running inside the sandbox call LLMs via OpenAI-compatible API.

**Rationale:** Manus agents can call LLMs from within the sandbox for code generation, analysis,
and reasoning. Our agents currently can only call LLMs through the backend's agent loop. An LLM
proxy enables sandbox scripts, code-server extensions, and MCP tools to use LLMs directly.

### Architecture

```
Sandbox                           Backend                        LLM Provider
  │                                  │                               │
  │── POST /llm-proxy/v1/           │                               │
  │   chat/completions ────────────>│                               │
  │   (OPENAI_API_KEY=scoped-jwt)   │── forward to UniversalLLM ──>│
  │                                  │<── streaming response ───────│
  │<── streaming response ──────────│                               │
```

### Proxy API (Backend-Side)

**`POST /api/v1/llm-proxy/v1/chat/completions`**
- Accepts OpenAI-format request body
- Validates sandbox JWT
- Enforces rate limit + max_tokens cap
- Forwards to configured LLM provider via existing `UniversalLLM`
- Returns OpenAI-format response (streaming or non-streaming)

**`POST /api/v1/llm-proxy/v1/embeddings`**
- Forwards to embedding provider
- Same auth/rate-limit model

**`GET /api/v1/llm-proxy/v1/models`**
- Returns list of available models (filtered for sandbox use)

### Changes

**New: `backend/app/interfaces/api/llm_proxy_routes.py`**
- OpenAI-compatible FastAPI router
- Request validation + transformation
- Streaming SSE response forwarding
- Rate limiting: configurable per-minute cap
- Token counting and cost attribution

**Modified: `docker-compose*.yml`**
```yaml
# sandbox service environment
- OPENAI_API_BASE=${SANDBOX_LLM_PROXY_URL:-http://backend:8000/api/v1/llm-proxy/v1}
- OPENAI_BASE_URL=${SANDBOX_LLM_PROXY_URL:-http://backend:8000/api/v1/llm-proxy/v1}
- OPENAI_API_KEY=${SANDBOX_LLM_PROXY_KEY:-}
```

**Modified: `backend/app/core/config_sandbox.py`**
```python
sandbox_llm_proxy_enabled: bool = False
sandbox_llm_proxy_max_tokens: int = 4096
sandbox_llm_proxy_rate_limit: int = 30  # requests/min
sandbox_llm_proxy_allowed_models: list[str] = []  # empty = all
sandbox_llm_proxy_key: Optional[str] = None
```

**Modified: `sandbox/app/core/config.py`**
```python
OPENAI_API_BASE: Optional[str] = None
OPENAI_API_KEY: Optional[str] = None
OPENAI_BASE_URL: Optional[str] = None
```

**Modified: `sandbox/scripts/generate_sandbox_context.py`**
- Detect `OPENAI_API_BASE` and report LLM proxy availability + model list

### Security Model
- Sandbox receives a scoped JWT, not the real API key
- Backend validates JWT before proxying any request
- `max_tokens` capped at backend level (prevents cost explosion)
- Rate limited per sandbox instance
- All LLM calls logged with session attribution
- No direct internet LLM access from sandbox

---

## Phase 5: Code-Server (VS Code Web IDE)

**Goal:** Run code-server inside the sandbox for a full VS Code experience.

**Rationale:** Manus runs code-server on port 8329 inside every sandbox. Users can see a real
IDE with syntax highlighting, extensions, integrated terminal, and file explorer. This transforms
the sandbox from a tool-execution container into a full development environment.

### Architecture

```
Frontend (CodeServerView.vue)
    │
    │── iframe src="signed-url"
    │
    ▼
Backend (proxy endpoint)
    │
    │── WebSocket proxy to sandbox:8443
    │
    ▼
Sandbox (code-server on 8443)
    │
    │── VS Code Web UI
    │── Integrated terminal (shares sandbox shell)
    │── File explorer (sandbox filesystem)
```

### Changes

**Modified: `sandbox/Dockerfile` (builder stage)**
```dockerfile
# code-server — optional VS Code web IDE (addons profile only)
RUN if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        curl -fsSL https://code-server.dev/install.sh | sh && \
        code-server --install-extension ms-python.python && \
        code-server --install-extension dbaeumer.vscode-eslint; \
    fi
```

**Modified: `sandbox/supervisord.conf`**
```ini
[program:code_server]
command=/bin/bash -c "if [ '%(ENV_ENABLE_CODE_SERVER)s' = '1' ] || [ '%(ENV_ENABLE_CODE_SERVER)s' = 'true' ]; then exec code-server --bind-addr 0.0.0.0:%(ENV_CODE_SERVER_PORT)s --auth password --disable-telemetry --disable-update-check /workspace; else echo 'code-server disabled'; exit 0; fi"
autostart=true
autorestart=unexpected
exitcodes=0
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
environment=HOME=/home/ubuntu,PASSWORD=%(ENV_CODE_SERVER_PASSWORD)s
user=ubuntu
priority=60
```

**Modified: `sandbox/app/core/config.py`**
```python
CODE_SERVER_PORT: int = 8443
CODE_SERVER_PASSWORD: Optional[str] = None
ENABLE_CODE_SERVER: bool = False
```

**Modified: `docker-compose*.yml`**
```yaml
# sandbox service environment
- CODE_SERVER_PORT=${CODE_SERVER_PORT:-8443}
- CODE_SERVER_PASSWORD=${CODE_SERVER_PASSWORD:-}
- ENABLE_CODE_SERVER=${ENABLE_CODE_SERVER:-0}
# sandbox service ports (add)
- "127.0.0.1:8443:8443"  # code-server (localhost only)
```

**Modified: `backend/app/interfaces/api/session_routes.py`**
- Add `get_code_server_url()` endpoint — mirrors `getVncUrl()` pattern
- Returns signed URL for iframe embedding

**New: `frontend/src/components/CodeServerView.vue`**
- iframe-based code-server viewer
- Auth passthrough via signed URL query param
- Connection state management (loading, connected, error)
- Resize handling for responsive layout

**Modified: `sandbox/scripts/generate_sandbox_context.py`**
- Report code-server availability, port, and version in context

### Gating
- Only installed when `ENABLE_SANDBOX_ADDONS=1` (Dockerfile build arg)
- Only runs when `ENABLE_CODE_SERVER=1` (runtime env var)
- Two independent gates: install ≠ run

---

## Phase 6: Observability (OTEL + Sentry)

**Goal:** Add distributed tracing and error tracking inside the sandbox.

**Rationale:** Manus traces 100% of sandbox requests via OTEL (`OTEL_TRACES_SAMPLER_RATIO=1.0`)
and captures errors via Sentry. This gives deep visibility into what happens inside the sandbox
during agent execution — critical for debugging failures in production.

### Architecture

```
Sandbox (FastAPI + OTEL SDK)
    │
    │── OTLP/HTTP traces ──> OTEL Collector / Jaeger / Tempo
    │── Sentry events ──────> Sentry (self-hosted or cloud)
    │
Backend (FastAPI + OTEL SDK — already partially supported)
    │
    │── Same collector ──> Unified trace view
```

### Changes

**Modified: `sandbox/requirements.runtime.txt`**
```
# Observability (only imported when OTEL_ENABLED=true or SENTRY_DSN is set)
opentelemetry-api>=1.29.0
opentelemetry-sdk>=1.29.0
opentelemetry-instrumentation-fastapi>=0.50b0
opentelemetry-instrumentation-httpx>=0.50b0
opentelemetry-exporter-otlp-proto-http>=1.29.0
sentry-sdk[fastapi]>=2.19.0
```

**New: `sandbox/app/core/telemetry.py`**
```python
def setup_telemetry(app: FastAPI) -> None:
    """Initialize OTEL + Sentry if configured. No-op when disabled."""

    if settings.OTEL_ENABLED:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        resource = Resource.create({
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.env": "sandbox",
        })
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(
            exporter,
            max_export_batch_size=settings.OTEL_BSP_MAX_EXPORT_BATCH_SIZE,
            schedule_delay_millis=settings.OTEL_BSP_SCHEDULE_DELAY,
        ))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()

    if settings.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[FastApiIntegration()],
            traces_sample_rate=settings.OTEL_TRACES_SAMPLER_RATIO,
            environment="sandbox",
        )
```

**Modified: `sandbox/app/core/config.py`**
```python
# Observability
OTEL_ENABLED: bool = False
OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
OTEL_SERVICE_NAME: str = "sandbox-runtime"
OTEL_TRACES_SAMPLER_RATIO: float = 1.0
OTEL_BSP_MAX_EXPORT_BATCH_SIZE: int = 1024
OTEL_BSP_SCHEDULE_DELAY: int = 10000
OTEL_PYTHON_LOG_CORRELATION: bool = True
OTEL_RESOURCE_ATTRIBUTES: str = "service.name=sandbox-runtime,service.env=sandbox"
SENTRY_DSN: Optional[str] = None
```

**Modified: `sandbox/app/main.py`**
```python
from app.core.telemetry import setup_telemetry

# In lifespan or startup:
setup_telemetry(app)
```

**Modified: `docker-compose*.yml`**
```yaml
# sandbox service environment
- OTEL_ENABLED=${OTEL_ENABLED:-false}
- OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT:-}
- OTEL_SERVICE_NAME=sandbox-runtime
- OTEL_TRACES_SAMPLER_RATIO=${OTEL_TRACES_SAMPLER_RATIO:-1.0}
- SENTRY_DSN=${SANDBOX_SENTRY_DSN:-}
```

### Gating
- OTEL: only activates when `OTEL_ENABLED=true` AND `OTEL_EXPORTER_OTLP_ENDPOINT` is set
- Sentry: only activates when `SENTRY_DSN` is set
- Zero overhead when disabled (lazy imports)

---

## Phase 7: GitHub Token + Cloud Integrations

**Goal:** Pass cloud service tokens into the sandbox for seamless git/GitHub/Google operations.

**Rationale:** Manus injects `GH_TOKEN`, `GOOGLE_DRIVE_TOKEN`, and `GOOGLE_WORKSPACE_CLI_TOKEN`
into every sandbox. This lets agents clone private repos, push commits, create PRs, access Google
Drive files, and use Google Workspace APIs without per-request token passing.

### Changes

**Modified: `sandbox/supervisord.conf`**
```ini
; GitHub CLI authentication (one-shot, runs after runtime_init)
[program:gh_auth_setup]
command=/bin/bash -c "if [ -n \"$GH_TOKEN\" ]; then echo \"$GH_TOKEN\" | gh auth login --with-token 2>/dev/null && gh auth setup-git 2>/dev/null && echo 'gh auth: configured'; else echo 'gh auth: skipped (no GH_TOKEN)'; fi; exit 0"
autostart=true
autorestart=false
startsecs=0
exitcodes=0
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
environment=HOME=/home/ubuntu,GH_TOKEN=%(ENV_GH_TOKEN)s
user=ubuntu
priority=3
```

**Modified: `sandbox/app/core/config.py`**
```python
GH_TOKEN: Optional[str] = None
GOOGLE_DRIVE_TOKEN: Optional[str] = None
GOOGLE_WORKSPACE_CLI_TOKEN: Optional[str] = None
```

**Modified: `docker-compose*.yml`**
```yaml
# sandbox service environment
- GH_TOKEN=${GH_TOKEN:-}
- GOOGLE_DRIVE_TOKEN=${GOOGLE_DRIVE_TOKEN:-}
- GOOGLE_WORKSPACE_CLI_TOKEN=${GOOGLE_WORKSPACE_CLI_TOKEN:-}
```

**Modified: `sandbox/scripts/generate_sandbox_context.py`**
- Check `gh auth status` and report authentication state
- Report availability of Google tokens (without exposing values)

**Modified: `.env.example`**
```bash
# GitHub token for sandbox git operations (optional)
# Enables: gh auth, git clone private repos, gh pr create
#GH_TOKEN=ghp_your_github_token

# Google service tokens for sandbox (optional)
#GOOGLE_DRIVE_TOKEN=
#GOOGLE_WORKSPACE_CLI_TOKEN=
```

**Modified: `backend/app/core/config_sandbox.py`**
```python
sandbox_gh_token: Optional[str] = None
sandbox_google_drive_token: Optional[str] = None
sandbox_google_workspace_token: Optional[str] = None
```

### Security
- Tokens passed via Docker environment variables (not baked into image)
- Container lifecycle ensures tokens expire with the sandbox
- `generate_sandbox_context.py` reports auth state but never exposes token values
- For ephemeral sandboxes: tokens are per-session and revocable

---

## Testing Strategy

Each phase includes:
1. **Unit tests** for new services/parsers
2. **Integration tests** via Docker Compose (spin up sandbox, execute scenarios)
3. **Backward compatibility tests** — new backend + old sandbox image, and vice versa

Key test scenarios:
- Phase 2: Structured markers parsed correctly; fallback when markers absent
- Phase 3: Callback delivery; rate limiting; JWT validation; no-op when disabled
- Phase 4: LLM proxy streaming; token cap enforcement; rate limiting
- Phase 5: code-server starts/stops; WebSocket proxy works; iframe loads
- Phase 6: OTEL traces exported; Sentry captures errors; zero overhead when off
- Phase 7: `gh auth status` succeeds; git clone private repo works

---

## Configuration Summary (.env additions)

```bash
# Phase 1: Environment Polish
TZ=UTC

# Phase 2: Terminal Markers
SHELL_USE_STRUCTURED_MARKERS=true

# Phase 3: Sandbox Callback
SANDBOX_CALLBACK_ENABLED=false
SANDBOX_CALLBACK_TOKEN=

# Phase 4: LLM Proxy
SANDBOX_LLM_PROXY_ENABLED=false
SANDBOX_LLM_PROXY_KEY=
SANDBOX_LLM_PROXY_MAX_TOKENS=4096
SANDBOX_LLM_PROXY_RATE_LIMIT=30

# Phase 5: Code-Server
ENABLE_CODE_SERVER=0
CODE_SERVER_PASSWORD=
CODE_SERVER_PORT=8443

# Phase 6: Observability
OTEL_ENABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=
SANDBOX_SENTRY_DSN=

# Phase 7: Cloud Tokens
GH_TOKEN=
GOOGLE_DRIVE_TOKEN=
GOOGLE_WORKSPACE_CLI_TOKEN=
```

---

## Rollout Plan

1. **Phase 1 + 2** together (both low complexity, no dependencies)
2. **Phase 3** alone (foundational for phases 4-5)
3. **Phase 4** after phase 3 (uses callback for health reporting)
4. **Phase 6 + 7** together (both independent, low-medium complexity)
5. **Phase 5** last (highest complexity, depends on phases 1+3, needs Dockerfile rebuild)

Each phase gets its own PR with feature flags defaulting to off.
