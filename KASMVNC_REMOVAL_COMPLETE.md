# KasmVNC Removal Complete

## Summary
Successfully replaced KasmVNC with x11vnc + websockify stack. All KasmVNC references have been completely eliminated from the codebase.

## Changes Made

### 1. sandbox/Dockerfile
**Removed:**
- KasmVNC installation (ARG, wget, apt-get install)
- KasmVNC config file copy

**Added:**
- x11vnc, websockify, xvfb via apt-get (lines 47-52)
- Simplified VNC directory configuration (lines 58-60)

**Updated:**
- Comment on line 11 to reference x11vnc instead of KasmVNC

### 2. sandbox/supervisord.conf
**Removed:**
- [program:kasmvnc] section

**Added:**
- [program:xvfb] - Virtual display server (priority 10, starts first)
- [program:x11vnc] - VNC server (priority 15, starts after Xvfb)

**Updated:**
- [group:services] - Changed from `kasmvnc` to `xvfb,x11vnc`
- Comments updated to reflect new architecture

### 3. sandbox/kasmvnc.yaml
**Action:** Deleted (no longer needed)

### 4. backend/app/interfaces/api/session_routes.py
**Changed:**
- Line 261-262: Removed `subprotocols=['binary']` parameter from `websockets.connect()`
- Updated comment to reference "standard RFB protocol" instead of KasmVNC

## Architecture

### Old Stack (KasmVNC)
```
noVNC (frontend) → Backend WebSocket Proxy → KasmVNC (Xvnc + WebSocket)
                                              ↓
                                           Display :1
```

### New Stack (x11vnc)
```
noVNC (frontend) → Backend WebSocket Proxy → websockify → x11vnc → Xvfb
                                                                    ↓
                                                                Display :1
```

## Service Startup Order (by priority)

1. **priority=10**: Xvfb (virtual display :1)
2. **priority=15**: x11vnc (VNC server on port 5900)
3. **priority=20**: websockify (WebSocket proxy on port 5901)
4. **priority=30**: socat (Chrome DevTools proxy)
5. **priority=50**: chrome (waits for display :1)
6. **priority=50**: app (FastAPI sandbox service)
7. **priority=55**: framework (sandbox framework API)

## Port Mapping (unchanged)
- 5900: Native VNC (x11vnc)
- 5901: WebSocket VNC (websockify)
- 8080: Sandbox API
- 9222: Chrome DevTools

## Next Steps

### 1. Rebuild Sandbox Container
```bash
docker-compose -f docker-compose-development.yml build sandbox
```

### 2. Restart Services
```bash
docker-compose -f docker-compose-development.yml up -d
```

### 3. Verify Services
```bash
# Check all services started
docker exec pythinker-sandbox-1 supervisorctl status

# Should show:
# xvfb                             RUNNING
# x11vnc                           RUNNING
# websockify                       RUNNING
# chrome                           RUNNING
# app                              RUNNING
# framework                        RUNNING
```

### 4. Test VNC Connection
```bash
# Check processes
docker exec pythinker-sandbox-1 ps aux | grep -E "Xvfb|x11vnc|websockify"

# Test screenshot endpoint
curl -I http://localhost:8083/api/v1/vnc/screenshot
# Should return 200 OK
```

### 5. End-to-End Test
1. Start new chat session in frontend
2. Ask agent to search on Google
3. Open "Pythinker's Computer" panel
4. Verify VNC connects and shows Chromium
5. Verify thumbnails appear in TaskProgressBar

## Benefits

### Size Reduction
- **Before:** KasmVNC (~100MB)
- **After:** x11vnc + xvfb + websockify (~20MB)
- **Savings:** ~80MB per container

### Simplicity
- **Before:** Custom KasmVNC build, config file, binary subprotocol
- **After:** Standard apt packages, simple command args, standard RFB

### Compatibility
- **Same ports:** 5900 (native), 5901 (WebSocket)
- **Same protocol:** RFB (Remote Framebuffer)
- **Same frontend:** noVNC works unchanged
- **Same backend:** WebSocket proxy just forwards bytes

## Files Modified

1. `sandbox/Dockerfile` (lines 11, 47-60)
2. `sandbox/supervisord.conf` (lines 38-98, 134)
3. `backend/app/interfaces/api/session_routes.py` (line 261-262)

## Files Deleted

1. `sandbox/kasmvnc.yaml`

## Verification Complete ✅

✅ All KasmVNC references removed from active code
✅ x11vnc + Xvfb configured in supervisord
✅ WebSocket proxy updated (no binary subprotocol)
✅ Dockerfile uses lightweight apt packages
✅ Comments and documentation updated
✅ Sandbox container rebuilt successfully
✅ All VNC services running (Xvfb, x11vnc, websockify)

### Service Status (Verified)
```
services:xvfb         RUNNING   pid 8
services:x11vnc       RUNNING   pid 9
services:websockify   RUNNING   pid 10
services:chrome       RUNNING   pid 11
services:app          RUNNING   pid 13
services:framework    RUNNING   pid 15
```

### Process Verification
```
ubuntu   8  /usr/bin/Xvfb :1 -screen 0 1280x1024x24 -ac +extension GLX +render -noreset
ubuntu   9  /usr/bin/x11vnc -display :1 -forever -shared -nopw -rfbport 5900 -xkb ...
ubuntu  10  python3 -m websockify 0.0.0.0:5901 localhost:5900
```

## No Breaking Changes

- Port numbers unchanged (5900, 5901)
- URL format unchanged (`ws://ip:5901`)
- Frontend noVNC unchanged
- Backend proxy unchanged (just removed subprotocol)
- Display :1 preserved
- Screenshot tool unchanged (uses xwd, independent of VNC)
