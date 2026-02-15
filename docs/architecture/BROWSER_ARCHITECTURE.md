# Browser Architecture

**Last Updated:** 2026-02-15
**Status:** ✅ Production Standard

---

## Overview

Pythinker's browser architecture provides AI agents with safe, observable, and reliable web automation capabilities. All browser operations execute in isolated Docker sandboxes with real-time user visibility via VNC streaming.

### Core Capabilities

- 🔒 **Isolated Execution:** Chromium runs in Docker sandbox, no host access
- 👁️ **Real-Time Visibility:** VNC streaming shows browser actions as they happen
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
│  │                │     │  (VNC Primary)  │                         │
│  └────────────────┘     └─────────────────┘                         │
│                                  │                                   │
│                         WebSocket (VNC)                              │
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
│  │  - Headless rendering to Xvfb                                  │ │
│  └──────────────┬─────────────────────────────────────────────────┘ │
│                 │                          │                         │
│        ┌────────▼────────┐        ┌───────▼───────┐                │
│        │  x11vnc :5900   │        │  CDP :9222    │                │
│        │  (VNC Server)   │        │  (Control)    │                │
│        └────────┬────────┘        └───────────────┘                │
│                 │                                                    │
│        ┌────────▼────────┐                                          │
│        │ websockify      │                                          │
│        │   5901→5900     │                                          │
│        │ (WS Proxy)      │                                          │
│        └─────────────────┘                                          │
│                                                                      │
│  Ports Exposed:                                                     │
│  - 8080  : Sandbox API                                             │
│  - 9222  : CDP (Chrome DevTools Protocol)                          │
│  - 5900  : VNC (native)                                            │
│  - 5901  : VNC WebSocket (websockify)                              │
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

## VNC Architecture

### VNC Streaming Pipeline

```
Browser Actions (Chromium)
         │
         ▼
Xvfb :1 (Virtual Display)
         │
         ▼
x11vnc (VNC Server) :5900
         │
         ▼
websockify (WS Proxy) :5901
         │
         ▼
Backend WS Proxy /api/v1/sessions/{id}/vnc
         │
         ▼
Frontend VNCViewer.vue (noVNC)
         │
         ▼
User's Browser
```

### VNC Configuration

**Sandbox supervisord.conf:**
```ini
[program:xvfb]
command=/usr/bin/Xvfb :1 -screen 0 1280x720x24 -ac +extension GLX +render -noreset
priority=10
autorestart=true

[program:x11vnc]
command=/usr/bin/x11vnc -display :1 -forever -shared -rfbport 5900 -nopw
priority=20
autorestart=true

[program:websockify]
command=/usr/bin/websockify --web=/usr/share/novnc 5901 localhost:5900
priority=30
autorestart=true
```

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

### VNC Streaming Performance

| Quality | FPS | Bandwidth | Latency |
|---------|-----|-----------|---------|
| Low | 15 | 200-400 KB/s | 30-50ms |
| Medium | 30 | 500-800 KB/s | 50-100ms |
| High | 60 | 1-2 MB/s | 80-150ms |

**Recommended:** Medium quality at 30 FPS for optimal balance

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

### VNC Display Frozen

**Symptoms:** VNC viewer shows static image, no updates

**Solutions:**
- Restart VNC services via supervisord
- Check x11vnc, websockify, Xvfb processes
- Verify port 5901 is accessible

### Slow Browser Performance

**Symptoms:** Browser actions take 5+ seconds

**Solutions:**
- Verify HTTPClientPool usage (not direct httpx)
- Check Docker resource limits
- Reduce VNC quality/FPS if bandwidth-limited
- Check Prometheus metrics for connection reuse rate

---

## Related Documentation

- **ADR:** `docs/architecture/BROWSER_STANDARDIZATION_ADR.md`
- **HTTP Pooling:** `docs/architecture/HTTP_CLIENT_POOLING.md`
- **Automatic Behavior:** `docs/architecture/AUTOMATIC_BROWSER_BEHAVIOR.md`
- **VNC Guide:** `docs/guides/OPENREPLAY.md`
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
| VNC Viewer | `frontend/src/components/VNCViewer.vue` |
| Live Viewer | `frontend/src/components/LiveViewer.vue` |

---

**Last Updated:** 2026-02-15
**Maintained By:** Pythinker Architecture Team
**Next Review:** 2026-05-15
