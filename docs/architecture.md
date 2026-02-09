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

- Primary replay: OpenReplay (`SessionReplayPlayer`)
- Fallback replay: screenshot timeline/player

## Core Services

- Frontend: Vite + Vue 3 (`frontend`, default dev port `5174`)
- Backend: FastAPI (`backend`, port `8000`)
- Sandboxes: browser/runtime containers (`sandbox`, `sandbox2`)
- Data stores: MongoDB, Redis, Qdrant

## Sandbox Runtime

- Chrome/Chromium with CDP exposed internally
- Screencast API (`/api/v1/screencast/stream`)
- VNC stack (`x11vnc` + `websockify`) for fallback

## Key Frontend Components

- `frontend/src/components/LiveViewer.vue`
- `frontend/src/components/SandboxViewer.vue`
- `frontend/src/components/VNCViewer.vue`
- `frontend/src/components/SessionReplayPlayer.vue`
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

For implementation detail, see:
- `docs/guides/OPENREPLAY.md`
- `docs/architecture/AGENT_COMPUTER_VIEW_ARCHITECTURE.md`
