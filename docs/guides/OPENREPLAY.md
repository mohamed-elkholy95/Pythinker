# OpenReplay Integration & Sandbox Architecture

Pythinker uses OpenReplay for session recording, replay, and live co-browsing. This replaces the previous VNC-based visualization.

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
VITE_OPENREPLAY_CANVAS_QUALITY=medium  # low | medium | high
VITE_OPENREPLAY_CANVAS_FPS=6
VITE_OPENREPLAY_ENABLED=true

# Backend (.env)
OPENREPLAY_PROJECT_KEY=pythinker-dev
OPENREPLAY_API_URL=http://localhost:8090
OPENREPLAY_ENABLED=true
```

## CDP Screencast (Replaced VNC)

The sandbox browser view now uses Chrome DevTools Protocol (CDP) screencast instead of VNC:

- **Lower latency**: Direct frame streaming (10-50ms vs 100-200ms VNC)
- **Better integration**: Captured natively by OpenReplay canvas recording
- **Simpler architecture**: No VNC server/client needed

```typescript
// SandboxViewer connects to CDP screencast
const ws = new WebSocket(`ws://${sandboxHost}:8080/api/v1/screencast/stream`)
ws.onmessage = (event) => {
  const frame = JSON.parse(event.data)
  // Render JPEG frame to canvas
  renderFrame(frame.data)
}
```

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
