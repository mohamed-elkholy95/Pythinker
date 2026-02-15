# System Architecture

## Overview

Pythinker runs as a multi-service system with a backend coordinator, sandbox containers for tool execution, and a Vue frontend for live monitoring and interaction.

1. Frontend creates/loads a session through backend APIs.
2. Backend allocates a sandbox and starts the agent workflow.
3. Agent runs tools (browser, shell, file, search, etc.) in sandboxed execution.
4. Backend streams events to frontend over SSE.
5. Live browser view is rendered through `LiveViewer`.

## Live View and Replay

### Live view (current)

- Primary renderer: CDP screencast (`SandboxViewer`)
- Runtime fallback: VNC (`VNCViewer`)
- Selection wrapper: `LiveViewer`
- Signed URL flow:
  - `POST /api/v1/sessions/{session_id}/sandbox/signed-url?target=screencast&quality=...&max_fps=...`
  - `WS /api/v1/sessions/{session_id}/screencast?...signature=...`

### Takeover input

- `WS /api/v1/sessions/{session_id}/input?...signature=...`
- Forwards user mouse/keyboard events into sandbox browser.

### Replay (current)

- Replay: screenshot timeline/player

## Core Services

- Frontend: Vite + Vue 3 (`frontend`, default dev port `5174`)
- Backend: FastAPI (`backend`, port `8000`)
- Sandboxes: browser/runtime containers (`sandbox`, `sandbox2`)
- Data stores: MongoDB, Redis, Qdrant

## Sandbox Runtime

- **Browser Engine:** Playwright Chromium (standardized)
- **CDP Control:** Chrome DevTools Protocol on port 9222
- **VNC Display:** x11vnc + websockify for real-time viewing (primary)
- **Screencast API:** `/api/v1/screencast/stream` (fallback)

**Browser Architecture:**
- Three-tier design: Protocol → Implementation → Tools
- Automatic crash recovery with progress events
- Connection pooling via HTTPClientPool (60-75% latency reduction)
- Health monitoring and observable metrics

See `docs/architecture/BROWSER_ARCHITECTURE.md` for complete browser architecture documentation.

## Key Frontend Components

- `frontend/src/components/LiveViewer.vue`
- `frontend/src/components/SandboxViewer.vue`
- `frontend/src/components/VNCViewer.vue`
- `frontend/src/components/ScreenshotReplayViewer.vue`
- `frontend/src/components/ToolPanelContent.vue`

## Key Backend Endpoints

- Session: `PUT /api/v1/sessions`
- Session detail: `GET /api/v1/sessions/{session_id}`
- SSE chat/tool events: `POST /api/v1/sessions/{session_id}/chat`
- Screencast signed URL: `POST /api/v1/sessions/{session_id}/sandbox/signed-url`
- Screencast proxy WS: `WS /api/v1/sessions/{session_id}/screencast`
- Input proxy WS: `WS /api/v1/sessions/{session_id}/input`
- VNC signed URL: `POST /api/v1/sessions/{session_id}/vnc/signed-url`
- VNC proxy WS: `WS /api/v1/sessions/{session_id}/vnc`

## Architecture Documentation

### Browser & Sandbox
- **Browser Architecture:** `docs/architecture/BROWSER_ARCHITECTURE.md` - Comprehensive browser architecture, VNC, CDP, tool layers
- **Browser Standardization ADR:** `docs/architecture/BROWSER_STANDARDIZATION_ADR.md` - Architecture decisions for browser stack
- **Automatic Browser Behavior:** `docs/architecture/AUTOMATIC_BROWSER_BEHAVIOR.md` - Browser automation patterns
- **Agent Computer View:** `docs/architecture/AGENT_COMPUTER_VIEW_ARCHITECTURE.md` - Live view and replay architecture

### Infrastructure
- **HTTP Client Pooling:** `docs/architecture/HTTP_CLIENT_POOLING.md` - Connection pooling for 60-75% latency reduction
- **Multi-API Key Management:** `docs/architecture/MULTI_API_KEY_MANAGEMENT.md` - API key rotation and failover
- **Session Resilience:** `docs/architecture/SESSION_RESILIENCE_SETUP.md` - Session recovery and persistence

### Performance & Monitoring
- **2026 Best Practices:** `docs/architecture/2026_BEST_PRACTICES.md` - Modern FastAPI, Pydantic v2, Docker patterns
- **Session Replay:** `docs/architecture/SESSION_REPLAY_ARCHITECTURE.md` - Screenshot timeline and replay
- **Tool Visualization:** `docs/architecture/TOOL_VISUALIZATION_MAP.md` - Tool usage and visualization

### Guides
- **OpenReplay Integration:** `docs/guides/OPENREPLAY.md` - VNC setup and usage
- **Testing Guide:** `docs/guides/TEST_GUIDE.md` - End-to-end validation procedures
