# Replay & Sandbox Architecture

Pythinker uses screenshot-based replay for completed sessions. Live view defaults to CDP screencast via `LiveViewer`, with VNC as runtime fallback.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Vue 3)                                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  SandboxViewer (Canvas - CDP Screencast)              │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐   │
│  │ Chat Panel   │ │ Tool Panel   │ │ Timeline + Events  │   │
│  └──────────────┘ └──────────────┘ └────────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌──────────────┐ ┌─────────────┐ ┌─────────────┐
    │ Screenshots  │ │ Backend     │ │ Sandbox     │
    │ (Replay)     │ │ - MongoDB   │ │ - Chrome    │
    │              │ │ - Redis     │ │ - CDP 9222  │
    │              │ │ - Qdrant    │ │ - Screencast│
    └──────────────┘ └─────────────┘ └─────────────┘
```

## Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `useScreenshotReplay` | `frontend/src/composables/useScreenshotReplay.ts` | Loads and controls screenshot replay timeline |
| `ScreenshotReplayViewer` | `frontend/src/components/ScreenshotReplayViewer.vue` | Renders replay frame + metadata |
| `LiveViewer` | `frontend/src/components/LiveViewer.vue` | Live renderer with CDP/VNC fallback |
| `SandboxViewer` | `frontend/src/components/SandboxViewer.vue` | CDP screencast canvas viewer |
| `ToolPanelContent` | `frontend/src/components/ToolPanelContent.vue` | Replay mode rendering in tool panel |
| `SessionHistoryPage` | `frontend/src/pages/SessionHistoryPage.vue` | Session browsing |

## Live View Strategy

`LiveViewer` is the single live surface used by main panel, takeover, and mini preview contexts.

- Renderer: CDP screencast (CDP-only architecture, VNC stack removed)

## CDP Screencast (Primary)

CDP is accessed through backend-signed URLs:

- Frontend requests `POST /sessions/{session_id}/sandbox/signed-url?target=screencast&quality=...&max_fps=...`
- Backend signs the full screencast path including `quality` and `max_fps`
- Frontend connects to `WS /sessions/{session_id}/screencast?...signature=...`

Important: `quality` and `max_fps` are part of signature verification and must be included at sign time.

VNC remains available as a backend-proxied fallback via:

- `POST /sessions/{session_id}/vnc/signed-url`
- `WS /sessions/{session_id}/vnc?...signature=...`

## Replay Strategy

Replay uses screenshot timeline data:

- `GET /sessions/{session_id}/screenshots`
- `GET /sessions/{session_id}/screenshots/{screenshot_id}`

The UI enters replay mode for `completed`/`failed` sessions when screenshot data exists.

## Sandbox Architecture

### CDP Screencast API

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
