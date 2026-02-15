# Browser Standardization Architecture Decision Record (ADR)

**Last Updated:** 2026-02-15
**Status:** ✅ Active Standard
**Decision Date:** 2026-02-15

---

## Context

Pythinker provides AI agents with browser automation capabilities through Docker sandboxes. The browser architecture must support:

1. **Safe Execution:** All browser operations run in isolated Docker containers
2. **Real-Time Visibility:** Users see browser actions live via VNC streaming
3. **Programmatic Control:** Agent controls browser via Chrome DevTools Protocol (CDP)
4. **Autonomous Operation:** AI agent can perform multi-step web tasks independently
5. **Manual Control:** Users can direct specific browser actions through tool calls
6. **Crash Recovery:** Browser crashes should not terminate the entire session

---

## Decision Summary

We standardize on a **three-tier browser architecture** with clear separation between protocol, implementation, and usage layers:

```
┌─────────────────────────────────────────────────────────┐
│  DOMAIN LAYER: Browser Protocol                        │
│  - Abstract interface defining browser capabilities    │
│  - Location: app/domain/external/browser.py            │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  INFRASTRUCTURE LAYER: Browser Implementations          │
│  - PlaywrightBrowser: CDP-based browser control         │
│  - BrowserConnectionPool: Health checks & recovery      │
│  - Location: app/infrastructure/external/browser/      │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  DOMAIN LAYER: Tool Services                            │
│  - BrowserTool: Manual control for user-directed tasks │
│  - BrowserAgentTool: Autonomous multi-step workflows   │
│  - Location: app/domain/services/tools/                │
└─────────────────────────────────────────────────────────┘
```

---

## Key Decisions

### Decision 1: Playwright Chromium as Standard Browser Engine

**Chosen:** Playwright Chromium (via `playwright install chromium`)
**Alternatives Considered:** Chrome for Testing, Firefox (Camoufox), Chromium apt package

**Rationale:**
- ✅ **Lighter weight:** ~200MB vs ~400MB for Chrome for Testing
- ✅ **Better Docker support:** No display server quirks
- ✅ **Consistent across platforms:** Works on amd64 and arm64
- ✅ **Native Playwright integration:** No version mismatches
- ✅ **Stable CDP implementation:** Reliable connection, fewer crashes
- ✅ **Self-hosted:** No external dependencies

**Configuration:**
```dockerfile
# Dockerfile build arg
ARG USE_CHROMIUM=1

# Runtime symlinks
RUN ln -sf "$PW_CHROMIUM" /usr/local/bin/chromium
RUN ln -sf "$PW_CHROMIUM" /usr/bin/chromium-browser
```

**Trade-offs:**
- ❌ Missing some proprietary codecs (H.264, AAC) - acceptable for agent use cases
- ❌ No official Chrome branding - not needed for automation

---

### Decision 2: Separate BrowserTool and BrowserAgentTool

**Chosen:** Two distinct tool services for different use patterns
**Alternatives Considered:** Single unified browser tool with mode parameter

**Rationale:**

#### BrowserTool (Manual Control)
- **Use Case:** User-directed browser actions via explicit tool calls
- **Examples:** "Click button at index 5", "Navigate to https://example.com", "Scroll down"
- **Agent Behavior:** Agent makes one tool call per user instruction
- **VNC Visibility:** User sees immediate feedback for each action
- **Implementation:** `app/domain/services/tools/browser.py`

#### BrowserAgentTool (Autonomous Operation)
- **Use Case:** Multi-step web tasks requiring decision-making
- **Examples:** "Search for laptops under $500 and extract top 5", "Fill out contact form and submit"
- **Agent Behavior:** Agent describes task in natural language, browser-use library executes autonomously
- **VNC Visibility:** User watches AI agent work through entire workflow
- **Implementation:** `app/domain/services/tools/browser_agent.py`

**Benefits of Separation:**
- ✅ **Clear intent:** Tool name indicates expected behavior (single action vs workflow)
- ✅ **Simpler implementations:** Each tool optimized for its pattern
- ✅ **Better prompts:** LLM can choose appropriate tool based on task complexity
- ✅ **Independent evolution:** Can enhance autonomous mode without breaking manual control
- ✅ **Easier testing:** Test simple actions separately from complex workflows

**Trade-offs:**
- ❌ Some code duplication in browser interaction logic (mitigated by shared PlaywrightBrowser)
- ❌ Two tools in LLM context (acceptable - improves tool selection accuracy)

---

### Decision 3: VNC as Primary User Interface for Browser Visualization

**Chosen:** VNC WebSocket (port 5901) for real-time browser display
**Alternatives Considered:** CDP screencast only, screenshot polling, video recording

**Rationale:**
- ✅ **Real-time streaming:** Users see browser actions as they happen
- ✅ **Mature technology:** x11vnc + websockify battle-tested in production
- ✅ **Interactive capability:** VNC supports mouse/keyboard passthrough (optional feature)
- ✅ **Fallback reliability:** Works even when CDP screencast fails
- ✅ **Cross-platform:** Works on all browsers via WebSocket
- ✅ **Low latency:** 50-100ms typical delay at 30 FPS

**Architecture:**
```
Sandbox Container:
├── Xvfb :1 (virtual X server)
├── Chromium --display=:1 (browser)
├── x11vnc --display=:1 -rfbport 5900 (VNC server)
└── websockify 5901:5900 (WebSocket proxy)

Frontend:
└── VNCViewer.vue (noVNC client)
```

**VNC Configuration:**
```python
# SandboxHealth monitoring
@dataclass
class SandboxHealth:
    api_responsive: bool = False
    browser_responsive: bool = False
    vnc_responsive: bool = False  # VNC health check
    vnc_frame_rate: float = 0.0  # Performance monitoring
    vnc_last_frame: datetime = None  # Detect frozen display
```

**Trade-offs:**
- ❌ Higher bandwidth than screenshot polling (mitigated by FPS limiting)
- ❌ Requires WebSocket connection (already required for SSE events)

---

### Decision 4: CDP for Programmatic Control, VNC for Display

**Chosen:** Dual-protocol architecture with clear separation of concerns
**Alternatives Considered:** CDP-only, VNC-only, hybrid CDP+VNC control

**Rationale:**

#### Chrome DevTools Protocol (CDP) - Port 9222
- **Purpose:** Programmatic browser control (navigate, click, input, JavaScript execution)
- **Used By:** PlaywrightBrowser, BrowserTool, BrowserAgentTool
- **Advantages:** Rich API, headless support, screenshot capture, console access
- **Connection:** HTTP + WebSocket to `http://sandbox_ip:9222`

#### Virtual Network Computing (VNC) - Port 5901
- **Purpose:** Real-time visual display of browser state
- **Used By:** Frontend VNCViewer component
- **Advantages:** User visibility, debugging, trust-building (users see what agent does)
- **Connection:** WebSocket to `ws://sandbox_ip:5901`

**Benefits of Dual Protocol:**
- ✅ **Separation of concerns:** Control (CDP) vs Display (VNC)
- ✅ **Independent failure modes:** CDP crash doesn't affect VNC display
- ✅ **Optimal protocols:** Each protocol does what it's best at
- ✅ **User trust:** Transparent browser operations build confidence in agent

**Synchronization:**
```python
# Browser actions update both CDP state and VNC display
async def navigate(self, url: str) -> ToolResult:
    # 1. CDP navigation (programmatic)
    result = await self._playwright.navigate(url)

    # 2. VNC automatically shows updated display (no explicit action needed)
    # x11vnc streams X server changes in real-time

    # 3. Emit event for frontend to highlight VNC viewer
    await self._emit_vnc_update_event("navigate", url=url)

    return result
```

---

### Decision 5: HTTPClientPool for All Browser Communication

**Chosen:** Connection pooling via `HTTPClientPool` for all HTTP-based browser/sandbox communication
**Alternatives Considered:** Direct `httpx.AsyncClient` per request, single shared client

**Rationale:**
- ✅ **Performance:** 60-75% latency reduction through connection reuse
- ✅ **Resource efficiency:** 80% fewer active connections
- ✅ **Observability:** Centralized Prometheus metrics
- ✅ **Consistency:** Same pattern used across application

**Implementation:**
```python
# ❌ WRONG: Direct client creation
async with httpx.AsyncClient() as client:
    response = await client.post(f"{sandbox_url}/api/browser/navigate")

# ✅ CORRECT: Use HTTPClientPool
client = await HTTPClientPool.get_client(
    name=f"sandbox-{session_id}",
    base_url=sandbox_url,
    timeout=600.0,
)
response = await client.post("/api/browser/navigate")
```

**See Also:** `docs/architecture/HTTP_CLIENT_POOLING.md`

---

### Decision 6: Crash Recovery via BrowserConnectionPool

**Chosen:** Automatic browser crash detection and recovery with retry logic
**Alternatives Considered:** Fail session on crash, manual recovery only

**Rationale:**
- ✅ **Reliability:** Browser crashes should not terminate entire agent session
- ✅ **User experience:** Transparent recovery maintains workflow continuity
- ✅ **Observable:** Progress events show "Reconnecting browser (1/3)..." during recovery
- ✅ **Bounded retries:** 3 attempts prevent infinite loops

**Implementation:**
```python
class BrowserConnectionPool:
    """Manages browser connection health and recovery"""

    async def ensure_browser_ready(
        self,
        sandbox: Sandbox,
        progress_callback: Callable[[str], Awaitable[None]] | None = None
    ) -> Browser:
        """Get browser with automatic crash recovery

        Emits progress events via callback during reconnection:
        - "Connecting to browser..."
        - "Retrying browser connection (1/3)..."
        - "Browser ready"
        """
```

**Health Check Strategy:**
```python
# Check CDP endpoint health
async def _check_browser_health(self, browser: Browser) -> bool:
    try:
        # Verify CDP connection responsive
        if not browser.is_connected():
            return False

        # Verify can communicate (lightweight request)
        result = await asyncio.wait_for(
            browser.view_page(wait_for_load=False),
            timeout=5.0
        )
        return result.success

    except (TimeoutError, ConnectionError):
        return False
```

**See Also:** `backend/app/infrastructure/external/browser/connection_pool.py`

---

## Configuration Standards

### Environment Variables

```bash
# Browser Engine
BROWSER_ENGINE=chromium  # chromium | chrome-for-testing
BROWSER_PATH=/usr/local/bin/chromium

# CDP Configuration
BROWSER_CDP_PORT=9222
BROWSER_CDP_TIMEOUT=30
BROWSER_CDP_RETRIES=15

# VNC Configuration
BROWSER_VNC_PORT=5901
BROWSER_VNC_FPS_LIMIT=30
BROWSER_VNC_QUALITY=medium  # low | medium | high

# Browser Agent (Autonomous Mode)
BROWSER_AGENT_MAX_STEPS=25
BROWSER_AGENT_TIMEOUT=300
BROWSER_AGENT_USE_VISION=true
BROWSER_AGENT_FLASH_MODE=false
BROWSER_AGENT_MAX_FAILURES=3
BROWSER_AGENT_LLM_TIMEOUT=30
BROWSER_AGENT_STEP_TIMEOUT=60

# Crash Recovery
BROWSER_AUTO_RETRY_ENABLED=true
BROWSER_CRASH_MAX_RETRIES=3
BROWSER_RETRY_DELAY=2.0
```

### Dockerfile Build Args

```dockerfile
# Use Playwright Chromium instead of Chrome for Testing
ARG USE_CHROMIUM=1

# Enable additional sandbox tools (optional)
ARG ENABLE_SANDBOX_ADDONS=0
```

---

## Testing Standards

### Unit Tests
- `tests/infrastructure/external/browser/test_playwright_browser_recovery.py`
- `tests/infrastructure/external/browser/test_browser_crash_resilience.py`
- `tests/infrastructure/external/browser/test_connection_pool.py`

### Integration Tests
- `tests/domain/services/test_agent_domain_service_browser_timeout.py`
- `tests/infrastructure/test_browser_retry_progress.py`

### Manual Testing
```bash
# 1. Start dev stack
./dev.sh up -d

# 2. Create session and trigger browser action
# Frontend: http://localhost:5174
# Send message: "Navigate to https://example.com"

# 3. Verify VNC display
# VNC should show browser navigating in real-time

# 4. Test crash recovery
docker exec pythinker-sandbox-1 pkill chrome
# Agent should auto-recover with progress events
```

---

## Migration Path

### Phase 1: Documentation (Current)
- ✅ Document browser architecture decisions
- ✅ Create standardization ADR
- ✅ Update CLAUDE.md with browser patterns

### Phase 2: Monitoring Enhancement (Next)
- Add VNC health checks to SandboxHealth
- Implement VNC event streaming in SSE
- Add VNC reconnection progress indicators

### Phase 3: Configuration Standardization
- Add BrowserMode enum (manual | autonomous | hybrid)
- Implement mode selection in AgentDomainService
- Add configuration validation

### Phase 4: Testing & Validation
- Comprehensive browser crash recovery tests
- VNC health monitoring tests
- Performance benchmarks (latency, FPS, bandwidth)

---

## Related Documentation

- **HTTP Client Pooling:** `docs/architecture/HTTP_CLIENT_POOLING.md`
- **Automatic Browser Behavior:** `docs/architecture/AUTOMATIC_BROWSER_BEHAVIOR.md`
- **Sandbox Security:** `backend/app/domain/models/sandbox_security_policy.py`
- **OpenReplay Integration:** `docs/guides/OPENREPLAY.md`

---

## Decision Criteria

When evaluating future browser architecture changes, consider:

1. **Security:** Does it maintain sandbox isolation?
2. **Visibility:** Can users see what the agent is doing?
3. **Reliability:** Does it degrade gracefully on failure?
4. **Simplicity:** Does it avoid unnecessary complexity?
5. **DDD Compliance:** Does it respect layer boundaries?
6. **Self-Hosted:** Does it avoid external dependencies?
7. **Type Safety:** Is it fully type-hinted?
8. **Observable:** Can we monitor it in production?

---

## Approval & Review

**Approved By:** Architecture Review (2026-02-15)
**Next Review:** 2026-05-15 (Quarterly)

**Stakeholders:**
- Backend Team: Browser infrastructure, CDP integration
- Frontend Team: VNC viewer, browser visualization
- Agent Team: Tool implementation, autonomous workflows
- SRE Team: Monitoring, crash recovery, performance
