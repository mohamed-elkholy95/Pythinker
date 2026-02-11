# Quick Test Guide

Fast validation checklist for current live/replay stack.

## 1) Service Health (30s)

```bash
docker compose ps
curl -s http://localhost:8000/health
```

Expected:
- backend/frontend/sandbox are up
- backend health endpoint responds

## 2) Live View Smoke Test (1 min)

1. Open `http://localhost:5174`.
2. Start a new session.
3. Ask the agent to open `https://example.com`.
4. Open "Pythinker's Computer" panel.

Expected:
- Live stream appears quickly (CDP path).
- Browser navigation is visible in real time.

## 3) Fallback Test (1 min)

1. While live view is active, restart sandbox:

```bash
docker compose restart sandbox
```

2. Observe the panel after reconnect.

Expected:
- Reconnect behavior is visible.
- Viewer falls back to VNC if CDP is unavailable.

## 4) Replay Test (1 min)

1. Complete a session with browser activity.
2. Open session history replay.

Expected:
- Screenshot replay is shown when screenshots are available.

## 5) Useful Logs

```bash
docker logs pyth-main-backend-1 --tail 200
docker logs pyth-main-sandbox-1 --tail 200
```

Look for:
- Screencast signed-url success
- Screencast websocket accepted
- No repeated invalid-signature errors

## 6) Sandbox Service Check (if fallback looks blank)

```bash
docker exec pyth-main-sandbox-1 supervisorctl status
```

Expected RUNNING:
- `xvfb`
- `x11vnc`
- `websockify`
- `chrome`
