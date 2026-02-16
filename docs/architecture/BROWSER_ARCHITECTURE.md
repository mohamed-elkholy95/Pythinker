# Browser Architecture

**Last Updated:** 2026-02-15
**Status:** ✅ Production Standard

---

## Overview

Pythinker's browser architecture provides AI agents with safe, observable, and reliable web automation capabilities. All browser operations execute in isolated Docker sandboxes with real-time user visibility via CDP screencast streaming.

### Core Capabilities

- 🔒 **Isolated Execution:** Chromium runs in Docker sandbox, no host access
- 👁️ **Real-Time Visibility:** CDP screencast streaming shows browser actions as they happen
- 🤖 **Autonomous Operation:** AI agent performs multi-step web tasks independently
- 🎯 **Manual Control:** Users direct specific browser actions via tool calls
- 🔄 **Auto-Recovery:** Crash detection and automatic reconnection with progress events
- 📊 **Observable:** Prometheus metrics, health checks, connection pooling

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Vue 3)                              │
│                                                                      │
│  ┌────────────────┐     ┌─────────────────┐                         │
│  │  ChatPage      │────▶│  LiveViewer     │                         │
│  │                │     │  (CDP-Only)     │                         │
│  └────────────────┘     └─────────────────┘                         │
│                                  │                                   │
│                      WebSocket (CDP Screencast)                      │
└──────────────────────────────────┼──────────────────────────────────┘
                                   │
┌──────────────────────────────────┼──────────────────────────────────┐
│                        BACKEND (FastAPI)                             │
│                                  │                                   │
│  ┌──────────────────────────────▼────────────────────────────────┐  │
│  │           AgentDomainService (Orchestrator)                   │  │
│  └──────────┬────────────────────────────────────────────┬───────┘  │
│             │                                            │            │
│    ┌────────▼──────────┐                    ┌───────────▼─────────┐ │
│    │   BrowserTool     │                    │ BrowserAgentTool    │ │
│    │ (Manual Control)  │                    │ (Autonomous Agent)  │ │
│    └────────┬──────────┘                    └───────────┬─────────┘ │
│             │                                            │            │
│             └──────────────┬───────────────────────────┘            │
│                            │                                         │
│              ┌─────────────▼─────────────┐                          │
│              │ BrowserConnectionPool     │                          │
│              │ - Health checks           │                          │
│              │ - Crash recovery          │                          │
│              │ - Progress events         │                          │
│              └─────────────┬─────────────┘                          │
│                            │                                         │
│              ┌─────────────▼─────────────┐                          │
│              │   PlaywrightBrowser       │                          │
│              │   (CDP Implementation)    │                          │
│              └─────────────┬─────────────┘                          │
│                            │                                         │
│              ┌─────────────▼─────────────┐                          │
│              │    HTTPClientPool         │                          │
│              │  (Connection Pooling)     │                          │
│              └─────────────┬─────────────┘                          │
└────────────────────────────┼─────────────────────────────────────────┘
                             │
                    HTTP + WebSocket
                             │
┌────────────────────────────┼─────────────────────────────────────────┐
│                   SANDBOX (Docker Container)                         │
│                            │                                         │
│  ┌─────────────────────────▼──────────────────────────────────────┐ │
│  │               Xvfb :1 (Virtual X Server)                        │ │
│  └─────────────────────────┬──────────────────────────────────────┘ │
│                            │                                         │
│  ┌─────────────────────────▼──────────────────────────────────────┐ │
│  │  Chromium --display=:1 --remote-debugging-port=9222            │ │
│  │  - Playwright-installed Chromium                               │ │
│  │  - CDP on 0.0.0.0:9222                                         │ │
│  │  - Headless rendering (no X11 in cdp_only mode)               │ │
│  └──────────────┬─────────────────────────────────────────────────┘ │
│                 │                                                    │
│        ┌────────▼────────┐                                          │
│        │  CDP :9222      │                                          │
│        │  (Control +     │                                          │
│        │   Screencast)   │                                          │
│        └─────────────────┘                                          │
│                                                                      │
│  Ports Exposed:                                                     │
│  - 8080  : Sandbox API                                             │
│  - 9222  : CDP (Chrome DevTools Protocol + Screencast)             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Layer Architecture

### 1. Domain Layer: Browser Protocol

**File:** `backend/app/domain/external/browser.py`

Defines the abstract interface for all browser implementations using Protocol (structural typing).

### 2. Infrastructure Layer: Browser Implementation

**File:** `backend/app/infrastructure/external/browser/playwright_browser.py`

Implements the Browser protocol using Playwright's CDP connection with error handling, recovery, and health monitoring.

### 3. Infrastructure Layer: Connection Pool

**File:** `backend/app/infrastructure/external/browser/connection_pool.py`

Manages browser connection lifecycle, health checks, and crash recovery with automatic retries and progress events.

### 4. Domain Layer: Tool Services

**BrowserTool** (Manual Control): `backend/app/domain/services/tools/browser.py`
**BrowserAgentTool** (Autonomous): `backend/app/domain/services/tools/browser_agent.py`

---

## CDP Screencast Architecture

### CDP Streaming Pipeline

```
Browser Actions (Chromium)
         │
         ▼
CDP :9222 (Page.startScreencast)
         │
         ▼
Backend WS Proxy /api/v1/sandbox/proxy
         │
         ▼
Frontend SandboxViewer.vue (CDP Binary WS)
         │
         ▼
User's Browser (JPEG frames via WebSocket)
```

### CDP Screencast Configuration

**Backend CDP Proxy:**
```python
# backend/app/interfaces/api/session_routes.py
# Proxies CDP screencast stream with signed URLs
# Quality: 1-100 (JPEG compression)
# Max FPS: 1-30 (frame rate limit)
```

**Streaming Mode** (`SANDBOX_STREAMING_MODE`):
- `cdp_only` (default): CDP screencast only, no X11 stack (-50% image size)
- `dual` (deprecated): CDP + X11 for legacy VNC support

---

## Browser Modes

### Manual Mode (Default)

**Use Case:** User directs browser through explicit tool calls

**Tools Used:** `browser_navigate`, `browser_click`, `browser_input`, `browser_scroll`

### Autonomous Mode

**Use Case:** AI agent performs multi-step workflow independently

**Tools Used:** `browser_agent_run`, `browser_agent_extract`

---

## Performance Characteristics

### Latency Benchmarks

| Operation | Without Pooling | With Pooling | Improvement |
|-----------|----------------|--------------|-------------|
| Navigate | 150-200ms | 50-80ms | 66% |
| Click | 100-150ms | 30-50ms | 70% |
| Input | 80-120ms | 25-40ms | 68% |
| Screenshot | 200-300ms | 80-120ms | 60% |

### CDP Screencast Performance

| Quality | FPS | Bandwidth | Latency |
|---------|-----|-----------|---------|
| Low (50) | 15 | 150-300 KB/s | 20-40ms |
| Medium (70) | 15 | 200-400 KB/s | 30-50ms |
| High (90) | 30 | 500-800 KB/s | 40-80ms |

**Recommended:** Medium quality (70) at 15 FPS for optimal balance
**Default:** Quality 70, FPS 15

---

## Error Handling & Recovery

### Recovery Flow

```
1. Detect browser crash (health check failure)
   ↓
2. Emit progress event: "Browser disconnected, reconnecting..."
   ↓
3. Close existing CDP connection
   ↓
4. Retry connection with exponential backoff (3 attempts)
   ↓
5. Emit progress event: "Retrying browser connection (1/3)..."
   ↓
6. If successful: "Browser ready"
   If failed: "Browser connection failed, please restart session"
```

### Error Categories

| Error Type | Recovery Strategy | User Impact |
|------------|-------------------|-------------|
| CDP Timeout | Auto-retry (3x) | Transparent recovery |
| CDP Connection Lost | Auto-reconnect | "Reconnecting..." message |
| Navigation Timeout | Return error | User informed, can retry |
| Element Not Found | Return error | User informed, can adjust |
| JavaScript Error | Return error | User informed, can debug |
| Sandbox Crash | Session termination | User must create new session |

---

## Security Considerations

### Sandbox Isolation

- Docker security constraints (no-new-privileges, seccomp)
- Minimal capabilities (SYS_ADMIN for Chromium, NET_ADMIN for network)
- Read-only filesystem with tmpfs mounts
- Network isolation (bridge mode)

### VNC Authentication

- Signed URLs with 60-second expiration
- Signature includes session_id, user_id, timestamp
- WebSocket upgrade requires valid signature

---

## Testing Strategy

### Unit Tests

- `tests/infrastructure/external/browser/test_playwright_browser_recovery.py`
- `tests/infrastructure/external/browser/test_browser_crash_resilience.py`
- `tests/infrastructure/external/browser/test_connection_pool.py`

### Integration Tests

- `tests/domain/services/test_agent_domain_service_browser_timeout.py`
- `tests/infrastructure/test_browser_retry_progress.py`

---

## Troubleshooting

### Browser Won't Connect

**Symptoms:** "Browser connection failed after 3 attempts"

**Solutions:**
- Restart sandbox container
- Check Docker resources (2GB+ RAM required)
- Verify Chromium installation
- Check CDP endpoint health

### CDP Screencast Frozen

**Symptoms:** Screen viewer shows static image, no updates

**Solutions:**
- Check CDP WebSocket connection status
- Restart browser via connection pool health check
- Verify port 9222 is accessible

### Slow Browser Performance

**Symptoms:** Browser actions take 5+ seconds

**Solutions:**
- Verify HTTPClientPool usage (not direct httpx)
- Check Docker resource limits
- Reduce CDP screencast quality/FPS if bandwidth-limited
- Check Prometheus metrics for connection reuse rate

---

## Related Documentation

- **ADR:** `docs/architecture/BROWSER_STANDARDIZATION_ADR.md`
- **HTTP Pooling:** `docs/architecture/HTTP_CLIENT_POOLING.md`
- **Automatic Behavior:** `docs/architecture/AUTOMATIC_BROWSER_BEHAVIOR.md`
- **Streaming Guide:** `docs/guides/OPENREPLAY.md`
- **Testing:** `docs/guides/TEST_GUIDE.md`

---

## Appendix: Key Files

| Component | File Path |
|-----------|-----------|
| Browser Protocol | `backend/app/domain/external/browser.py` |
| Playwright Implementation | `backend/app/infrastructure/external/browser/playwright_browser.py` |
| Connection Pool | `backend/app/infrastructure/external/browser/connection_pool.py` |
| Browser Tool | `backend/app/domain/services/tools/browser.py` |
| Browser Agent Tool | `backend/app/domain/services/tools/browser_agent.py` |
| Sandbox Manager | `backend/app/core/sandbox_manager.py` |
| Docker Sandbox | `backend/app/infrastructure/external/sandbox/docker_sandbox.py` |
| CDP Screencast Viewer | `frontend/src/components/SandboxViewer.vue` |
| Live Viewer (CDP-Only) | `frontend/src/components/LiveViewer.vue` |

---

**Last Updated:** 2026-02-15
**Maintained By:** Pythinker Architecture Team
**Next Review:** 2026-05-15
