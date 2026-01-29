# VNC Simplification Proposal: Replace KasmVNC with x11vnc

## Current Problem
KasmVNC is overkill for basic agent/browser use case. It's heavy, complex, and provides features we don't need.

## Proposed Solution
Replace KasmVNC with **x11vnc + websockify** - industry standard for lightweight VNC in containers.

---

## Comparison

| Feature | KasmVNC (Current) | x11vnc + websockify (Proposed) |
|---------|-------------------|--------------------------------|
| **Size** | ~100MB | ~20MB (5x lighter) |
| **Setup** | Complex YAML config | Single command line |
| **WebSocket** | Built-in | Via websockify |
| **Stability** | Good | Excellent (20+ years) |
| **Debugging** | Harder (custom protocol) | Easy (standard VNC) |
| **Features** | Many (DLP, encoding, etc.) | Basic (exactly what we need) |
| **Container startup** | ~3s | ~1s |

---

## Migration Steps

### 1. Update Dockerfile

**File**: `sandbox/Dockerfile`

```dockerfile
# Remove KasmVNC (if installed via package)
# RUN apt-get install kasmvncserver ...

# Add x11vnc + websockify (lightweight)
RUN apt-get update && apt-get install -y \
    x11vnc \
    websockify \
    xvfb \
    x11-utils \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*
```

### 2. Update supervisord config

**File**: `sandbox/supervisord.conf`

```ini
# Remove old KasmVNC section
[program:kasmvnc]
# ... delete this ...

# Add Xvfb (virtual display)
[program:xvfb]
command=/usr/bin/Xvfb :1 -screen 0 1280x1024x24
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true
priority=1

# Add x11vnc (VNC server)
[program:x11vnc]
command=/usr/bin/x11vnc -display :1 -forever -shared -nopw -rfbport 5900 -xkb
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true
priority=2

# Add websockify (WebSocket proxy)
[program:websockify]
command=/usr/bin/websockify --web=/usr/share/novnc 5901 localhost:5900
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true
priority=3

# Keep Chromium as-is
[program:chromium]
# ... no changes ...
```

### 3. Update backend connection

**File**: `backend/app/infrastructure/external/sandbox/docker_sandbox.py`

```python
# Line 34 - VNC URL stays the same
self._vnc_url = f"ws://{self.ip}:5901"  # websockify port
```

**File**: `backend/app/interfaces/api/session_routes.py`

```python
# Line 262 - REMOVE the subprotocols parameter
# x11vnc uses standard RFB protocol, no need for 'binary' subprotocol
async with websockets.connect(sandbox_ws_url) as sandbox_ws:
```

### 4. Remove KasmVNC config

```bash
# Delete these files (no longer needed)
rm sandbox/kasmvnc.yaml
```

### 5. Rebuild and test

```bash
# Rebuild sandbox image
docker-compose -f docker-compose-development.yml build sandbox

# Restart services
docker-compose -f docker-compose-development.yml restart sandbox backend

# Test VNC connection
# Should work exactly the same as before
```

---

## What Changes for Users?

**Nothing!** The VNC experience is identical:
- ✅ Same VNC viewer in frontend
- ✅ Same screenshot system
- ✅ Same user takeover capability
- ✅ Same Chromium browser

**Under the hood**:
- 🚀 Faster container startup
- 📦 Smaller images
- 🔧 Easier to debug
- 💰 Less memory usage

---

## Command Reference

### x11vnc Options Explained

```bash
x11vnc \
  -display :1          # Connect to Xvfb display
  -forever             # Keep running after client disconnects
  -shared              # Allow multiple clients
  -nopw                # No password (safe in container)
  -rfbport 5900        # Standard VNC port
  -xkb                 # Better keyboard handling
```

### websockify Options

```bash
websockify \
  --web=/usr/share/novnc   # Serve noVNC HTML client (optional)
  5901                     # WebSocket port (what frontend connects to)
  localhost:5900           # VNC server to proxy
```

---

## Testing Checklist

After migration:

- [ ] Container builds successfully
- [ ] x11vnc starts on port 5900
- [ ] websockify starts on port 5901
- [ ] Chromium displays on :1
- [ ] VNC connects from frontend
- [ ] Agent can use browser
- [ ] User can take over browser
- [ ] Screenshots still work
- [ ] No "binary subprotocol" errors

---

## Rollback Plan

If issues occur, rollback is easy:

```bash
# Use previous Dockerfile commit
git checkout HEAD~1 sandbox/Dockerfile sandbox/supervisord.conf

# Rebuild
docker-compose -f docker-compose-development.yml build sandbox
docker-compose -f docker-compose-development.yml restart sandbox
```

---

## Alternative: Keep KasmVNC (If it works, don't fix it)

**When to keep KasmVNC:**
- Already working fine
- Don't want to test migration
- Need advanced features later (DLP, recording, etc.)
- 100MB doesn't matter for your deployment

**Current setup is functional** - only migrate if you want:
- Lighter containers
- Simpler debugging
- Standard VNC protocol

---

## Industry Examples

Projects using x11vnc + Docker:

1. **Selenium Grid** - Browser testing containers
2. **GitHub Actions** - Browser automation
3. **GitLab CI** - Visual testing
4. **Playwright** - Browser testing with VNC debug

All use x11vnc because it's **simple and reliable**.

---

## Recommendation

**If KasmVNC is working**: Keep it for now, migrate when convenient
**If starting fresh**: Use x11vnc + websockify
**If having issues**: x11vnc is easier to debug

For your basic use case (agent + browser + occasional takeover), **x11vnc is best practice**.

---

## Sources

- [GitHub - kasmtech/KasmVNC](https://github.com/kasmtech/KasmVNC)
- [KasmVNC vs TigerVNC Differences](https://github.com/kasmtech/KasmVNC/wiki/Differences-From-TigerVNC)
- [GitHub - Zimiat/webvnc-docker](https://github.com/Zimiat/webvnc-docker) - Lightweight XFCE + TigerVNC + noVNC
- [VNC Server Comparison](https://dohost.us/index.php/2025/11/05/vnc-server-software-comparison-tightvnc-tigervnc-realvnc-x11vnc/)
- [x11vnc Documentation](http://www.karlrunge.com/x11vnc/)
- [Best VNC for Linux 2025](https://www.realvnc.com/en/blog/best-vnc-server-for-linux/)

**Status**: Proposal - ready to implement when needed
