# Replay & Sandbox Architecture

Pythinker runs in a CDP-only live-streaming architecture.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Vue 3)                                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  LiveViewer -> SandboxViewer (Canvas CDP Screencast)  │ │
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
| `LiveViewer` | `frontend/src/components/LiveViewer.vue` | Thin CDP-only live view wrapper |
| `SandboxViewer` | `frontend/src/components/SandboxViewer.vue` | CDP screencast canvas viewer + input forwarding |
| `ToolPanelContent` | `frontend/src/components/ToolPanelContent.vue` | Replay mode rendering in tool panel |
| `SessionHistoryPage` | `frontend/src/pages/SessionHistoryPage.vue` | Session browsing |

## Live View Strategy

`LiveViewer` is the single live surface used by main panel, takeover, and mini preview contexts.

- Renderer: CDP screencast only
- Signed transport: backend `sandbox/signed-url` endpoints

## CDP Screencast

CDP is accessed through backend-signed URLs:

- Frontend requests `POST /sessions/{session_id}/sandbox/signed-url?target=screencast&quality=...&max_fps=...`
- Backend signs the full screencast path including `quality` and `max_fps`
- Frontend connects to `WS /sessions/{session_id}/screencast?...signature=...`

Important: `quality` and `max_fps` are part of signature verification and must be included at sign time.

## Input Forwarding

For interactive takeover, input events are forwarded through a signed backend WebSocket:

- Frontend requests `POST /sessions/{session_id}/sandbox/signed-url?target=input`
- Frontend connects to `WS /sessions/{session_id}/input?...signature=...`

## Replay Strategy

Replay uses screenshot timeline data:

- `GET /sessions/{session_id}/screenshots`
- `GET /sessions/{session_id}/screenshots/{screenshot_id}`

The UI enters replay mode for `completed`/`failed` sessions when screenshot data exists.

## Sandbox APIs

### Screencast

```
GET /api/v1/screencast/stream  # WebSocket - continuous JPEG frames
GET /api/v1/screencast/frame   # Single frame capture
```

### Input

```
WS /api/v1/input/stream        # Mouse/keyboard/wheel events over JSON
```
