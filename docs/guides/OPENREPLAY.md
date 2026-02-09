# OpenReplay Integration & Sandbox Architecture

Pythinker uses OpenReplay for session recording and replay. Live view defaults to CDP screencast via `LiveViewer`, with VNC used as a runtime fallback.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Vue 3 + OpenReplay Tracker)                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  SandboxViewer (Canvas - CDP Screencast)               │ │
│  │  [Captured by OpenReplay @ 6 FPS]                      │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐   │
│  │ Chat Panel   │ │ Tool Panel   │ │ Timeline + Events  │   │
│  │ [DOM capture]│ │ [DOM capture]│ │ [Agent events]     │   │
│  └──────────────┘ └──────────────┘ └────────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌──────────────┐ ┌─────────────┐ ┌─────────────┐
    │ OpenReplay   │ │ Backend     │ │ Sandbox     │
    │ (Optional)   │ │ ────────────│ │ ────────────│
    │ • PostgreSQL │ │ • MongoDB   │ │ • Chrome    │
    │ • Redis      │ │ • Redis     │ │ • CDP 9222  │
    │ • MinIO      │ │ • Qdrant    │ │ • Screencast│
    └──────────────┘ └─────────────┘ └─────────────┘
```

## Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `useOpenReplay` | `frontend/src/composables/useOpenReplay.ts` | Tracker initialization, session recording |
| `useAgentEvents` | `frontend/src/composables/useAgentEvents.ts` | Bridge SSE events to OpenReplay |
| `useSandboxInput` | `frontend/src/composables/useSandboxInput.ts` | Mouse/keyboard forwarding for takeover |
| `LiveViewer` | `frontend/src/components/LiveViewer.vue` | Live view renderer with CDP/VNC selection |
| `SandboxViewer` | `frontend/src/components/SandboxViewer.vue` | CDP screencast canvas viewer |
| `SessionReplayPlayer` | `frontend/src/components/SessionReplayPlayer.vue` | Embedded replay player |
| `ReplayTimeline` | `frontend/src/components/ReplayTimeline.vue` | Timeline with event markers |
| `SessionHistoryPage` | `frontend/src/pages/SessionHistoryPage.vue` | Session history browsing |
| `OpenReplayClient` | `backend/app/infrastructure/external/openreplay/client.py` | Backend OpenReplay integration |

## Environment Variables

```bash
# Frontend (.env)
VITE_OPENREPLAY_PROJECT_KEY=pythinker-dev
VITE_OPENREPLAY_INGEST_URL=http://localhost:9001
VITE_OPENREPLAY_ASSIST_URL=ws://localhost:9003
VITE_OPENREPLAY_API_URL=http://localhost:8090
VITE_OPENREPLAY_CANVAS_QUALITY=medium  # low | medium | high
VITE_OPENREPLAY_CANVAS_FPS=6
VITE_OPENREPLAY_ENABLED=true
VITE_LIVE_RENDERER=cdp  # cdp | vnc

# Backend (.env)
OPENREPLAY_PROJECT_KEY=pythinker-dev
OPENREPLAY_API_URL=http://localhost:8090
OPENREPLAY_ENABLED=true
```

## Live View Strategy

`LiveViewer` is the single live surface used by main panel, takeover, and mini preview contexts.

- Default renderer: CDP (`VITE_LIVE_RENDERER=cdp`)
- Runtime fallback: VNC when CDP fails/disconnects
- Optional force: set `VITE_LIVE_RENDERER=vnc` to make VNC primary

Mini previews explicitly prefer VNC to avoid competing CDP streams while the main panel is active.

## CDP Screencast (Primary)

The sandbox browser view defaults to Chrome DevTools Protocol (CDP) screencast:

- **Lower latency**: Direct frame streaming (10-50ms vs 100-200ms VNC)
- **Better integration**: Captured natively by OpenReplay canvas recording
- **Simpler architecture**: No VNC server/client needed

CDP is accessed through backend-signed URLs:

- Frontend requests `POST /sessions/{session_id}/sandbox/signed-url?target=screencast&quality=...&max_fps=...`
- Backend signs the full screencast path including `quality` and `max_fps`
- Frontend connects to `WS /sessions/{session_id}/screencast?...signature=...`

Important: `quality` and `max_fps` are part of signature verification and must be included at sign time.

VNC remains available as a backend-proxied fallback via:

- `POST /sessions/{session_id}/vnc/signed-url`
- `WS /sessions/{session_id}/vnc?...signature=...`

## Replay Strategy

Replay surfaces prefer OpenReplay when available:

- Primary: `SessionReplayPlayer` (OpenReplay embed)
- Fallback: screenshot timeline/player for sessions without OpenReplay data

## Starting OpenReplay (Optional)

```bash
# Start OpenReplay services alongside dev stack
docker compose -f docker-compose-openreplay.yml up -d

# Or include in main dev stack
docker compose -f docker-compose-development.yml -f docker-compose-openreplay.yml up -d
```

## Session Model Fields

Sessions include OpenReplay tracking:
```python
# backend/app/domain/models/session.py
class Session:
    # ... existing fields ...
    openreplay_session_id: str | None = None
    openreplay_session_url: str | None = None
```

## Linking Sessions

When a live chat starts, the frontend links the OpenReplay session to the Pythinker session via:

```
POST /sessions/{session_id}/openreplay
```

This enables Session History and replay surfaces to load the correct OpenReplay recording.

## OpenReplay Services (Optional)

| Service | Port |
|---------|------|
| OpenReplay Ingest | 9001 |
| OpenReplay API | 8090 |
| OpenReplay Assist | 9003 |
| OpenReplay Assets | 9002 |
| OpenReplay Postgres | 5433 |
| OpenReplay MinIO | 9100 |

---

## Sandbox Architecture

### CDP Screencast API

The sandbox exposes a screencast WebSocket endpoint for real-time browser view:

```
GET /api/v1/screencast/stream  # WebSocket - continuous JPEG frames
GET /api/v1/screencast/frame   # Single frame capture
```

### Input Forwarding

For interactive takeover, input events are forwarded to the sandbox:

```
POST /api/v1/input/mouse      # { x, y, type, button }
POST /api/v1/input/keyboard   # { key, type, modifiers }
POST /api/v1/input/scroll     # { x, y, deltaX, deltaY }
```

### Container Resources

```yaml
# docker-compose-development.yml sandbox config
shm_size: '2gb'           # Chrome stability
tmpfs:
  - /run:size=100M
  - /tmp:size=500M
deploy:
  resources:
    limits:
      memory: 4G
    reservations:
      memory: 1G
```
