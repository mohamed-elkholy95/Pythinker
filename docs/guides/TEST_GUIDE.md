# Test Guide - Browser Live View and Replay

This guide matches the current setup:
- Live view: CDP first, VNC fallback
- Replay: screenshot timeline playback

## Stack Health

Expected running services:

- Backend (`:8000`)
- Frontend (`:5174`)
- Sandbox API (`:8083` / internal `:8080`)
- MongoDB, Redis, Qdrant
- Sandbox display services (`xvfb`, `x11vnc`, `websockify`, `chrome`)

Quick checks:

```bash
docker compose ps
curl -s http://localhost:8000/health
```

## Test Scenarios

### Test 1: CDP Live View Path

Goal: verify primary renderer is CDP.

1. Open `http://localhost:5174`.
2. Create a new session.
3. Ask: `Go to example.com and summarize the page.`
4. Open "Pythinker's Computer" panel.

Expected:
- Live stream appears without manual refresh.
- Browser actions are visible in near real time.
- No forced switch to VNC unless CDP fails.

### Test 2: Runtime Fallback to VNC

Goal: verify fallback behavior when CDP disconnects.

1. Keep a live browser task running.
2. Interrupt screencast path (for example, restart sandbox container).
3. Observe panel behavior.

Expected:
- Live view reports reconnect/disconnect.
- `LiveViewer` falls back to VNC automatically.
- Session remains usable for monitoring.

### Test 3: Signed URL and Proxy Flow

Goal: verify signed URL flow for screencast.

1. Start a browser task.
2. Watch backend logs.

Expected logs:
- Signed URL request for `target=screencast` includes `quality` and `max_fps`.
- WebSocket accepted on `/sessions/{id}/screencast`.
- Proxy connects to sandbox `/api/v1/screencast/stream`.

### Test 4: Replay Surface Selection

Goal: verify replay priority.

1. Complete a browser session.
2. Open session history replay.

Expected:
- Screenshot replay is shown when session screenshots exist.

### Test 5: Takeover Input Channel

Goal: verify interactive takeover still works.

1. Open takeover mode in a live session.
2. Click/type in the remote browser.

Expected:
- Input is forwarded through `/sessions/{id}/input`.
- Browser responds to user interactions.

## Log Expectations

Backend logs should show healthy transitions, not signature errors.

Look for:
- `POST /api/v1/sessions/{id}/sandbox/signed-url ... 200`
- `Accepted screencast WebSocket for session ...`
- `Connected to screencast at ws://.../api/v1/screencast/stream?...`

Avoid seeing repeatedly:
- `Invalid signature`
- Continuous reconnect loops with no frames

## Troubleshooting

### Live panel stuck reconnecting

Check backend and sandbox logs for screencast path/signature issues.

```bash
docker logs pyth-main-backend-1 --tail 200
docker logs pyth-main-sandbox-1 --tail 200
```

### Fallback VNC blank

Check sandbox supervisor services.

```bash
docker exec pyth-main-sandbox-1 supervisorctl status
```

Expected RUNNING:
- `xvfb`
- `x11vnc`
- `websockify`
- `chrome`

### Replay missing

- Confirm screenshot replay endpoints return data for the session.
- Confirm the session has reached `completed` or `failed`.

## Success Criteria

- Live view works reliably with CDP as default.
- Fallback to VNC works automatically when CDP fails.
- Replay works from screenshot timeline data.
- No signature mismatch regressions in screencast URL flow.
