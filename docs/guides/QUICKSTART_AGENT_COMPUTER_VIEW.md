# Quick Start: Agent Computer View

This guide reflects the current live/replay setup.

## What You Get

- Live view through `LiveViewer`
- CDP screencast as primary renderer
- Automatic VNC fallback when CDP fails
- Screenshot-based replay for completed sessions

## Prerequisites

- Dev stack running via docker compose
- Frontend at `http://localhost:5174`
- Backend at `http://localhost:8000`

## Start Dev Stack

```bash
docker compose -f docker-compose.yml -f docker-compose-development.yml up -d --build
```

## Verify Live View

1. Open `http://localhost:5174`.
2. Create a new agent session.
3. Run a browser task (for example: navigate to a site).
4. Open the computer panel.

Expected behavior:
- Live feed starts in CDP mode by default.
- If CDP disconnects, UI falls back to VNC automatically.

## Verify Replay

1. Complete a session with browser activity.
2. Open session history.
3. Open replay.

Expected behavior:
- Screenshot replay is shown for completed/failed sessions when screenshots exist.

## Key Config

Set frontend env (via compose env vars):

```bash
VITE_LIVE_RENDERER=cdp   # cdp | vnc
```

Notes:
- Keep `cdp` as default for production-quality live view.
- Use `vnc` only if you want forced fallback behavior for troubleshooting.

## Troubleshooting

### Reconnecting loop on live view

- Check backend logs for signed URL errors:
  - invalid signature
  - missing `quality/max_fps` on signed URL path

### Blank VNC fallback

- Check sandbox supervisor status:

```bash
docker exec pyth-main-sandbox-1 supervisorctl status
```

### Replay not showing screenshots

- Confirm session has screenshots available from backend endpoints.
- Confirm the session is in `completed` or `failed` status.

## References

- `docs/guides/OPENREPLAY.md`
- `docs/architecture/AGENT_COMPUTER_VIEW_ARCHITECTURE.md`
