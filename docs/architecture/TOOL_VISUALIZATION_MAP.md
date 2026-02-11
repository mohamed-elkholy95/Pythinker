# Tool Visualization Map

This document defines how tool execution is visualized in the current UI.

## Principles

- Live computer view uses `LiveViewer`.
- `LiveViewer` is CDP-first (`SandboxViewer`) with VNC fallback (`VNCViewer`).
- Mini previews favor stable, lightweight rendering and may force VNC to avoid CDP contention.
- Replay uses screenshot timeline playback.

## Primary Surfaces

- Main panel live view: `frontend/src/components/ToolPanelContent.vue`
- Unified live renderer: `frontend/src/components/LiveViewer.vue`
- CDP renderer: `frontend/src/components/SandboxViewer.vue`
- VNC fallback: `frontend/src/components/VNCViewer.vue`
- Mini preview: `frontend/src/components/VncMiniPreview.vue`
- Replay player: `frontend/src/components/ScreenshotReplayViewer.vue`

## Tool Category Mapping

| Tool Category | Typical Tools | Main Live Surface | Mini Preview | Output Surface |
|---|---|---|---|---|
| Browser automation | `browser`, `playwright`, `browser_agent` | `LiveViewer` (CDP primary) | `VncMiniPreview` (VNC preferred) | Tool output / timeline |
| Shell execution | `shell`, `code_executor`, `git`, `test_runner` | Optional live context | Terminal-style preview | Terminal/output panel |
| File operations | `file`, `workspace`, `code_dev` | Optional live context | Editor/file preview | Editor/output panel |
| Search/research | `search`, deep/wide research tools | Optional live context | Search preview | Search/result panel |
| Generic integrations | `mcp`, `message`, misc tools | Optional live context | Generic preview | Generic/result panel |

## Event Flow

1. Backend emits SSE tool/progress events.
2. Frontend updates ToolPanel timeline and active content view.
3. When live browser context is needed, `LiveViewer` mounts.
4. `LiveViewer` chooses CDP or fallback VNC.
5. Replay surfaces use screenshot metadata and image frames.

## Signed URL Endpoints

- Screencast URL request:
  - `POST /api/v1/sessions/{session_id}/sandbox/signed-url?target=screencast&quality=...&max_fps=...`
- Screencast websocket:
  - `WS /api/v1/sessions/{session_id}/screencast?...signature=...`
- VNC fallback signed URL:
  - `POST /api/v1/sessions/{session_id}/vnc/signed-url`
- VNC websocket:
  - `WS /api/v1/sessions/{session_id}/vnc?...signature=...`

## Validation Checklist

- Browser tool starts in CDP by default.
- CDP disconnect triggers VNC fallback without manual action.
- Mini preview remains responsive while main view is live.
- Replay opens screenshot timeline playback when screenshots are available.
- No signature mismatch errors for screencast URLs.
