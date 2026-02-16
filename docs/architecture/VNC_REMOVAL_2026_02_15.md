# VNC Stack Removal - CDP-Only Architecture

**Date:** 2026-02-15
**Commit:** 18757bf
**Status:** ✅ Complete

---

## Summary

Removed the entire VNC client stack (VNCViewer.vue, useVNCPreconnect.ts, @novnc/novnc dependency) and enforced CDP-only streaming architecture. VNC services were disabled in `cdp_only` mode but backend/frontend still attempted VNC connections, causing repeated "Connection refused" errors and 30 reconnect attempts per session.

**Result:** -847 net lines, cleaner CDP-only architecture, eliminated VNC reconnection overhead.

---

## Changes

### Backend (4 files)

**`backend/app/core/config.py`**
- Added `StreamingMode` enum (`DUAL`, `CDP_ONLY`)
- Added `is_vnc_enabled` computed field
- Default changed to `CDP_ONLY`

**`backend/app/interfaces/schemas/session.py`**
- Added `streaming_mode` to `SandboxInfo`, `GetSessionResponse`, `SessionStatusResponse`
- Added `StreamingMode` type export

**`backend/app/interfaces/api/session_routes.py`**
- VNC WebSocket: Early reject with 1008 close in CDP-only mode
- VNC signed-url: Return 503 in CDP-only mode
- Added `/screenshot` alias route (no /vnc prefix needed)
- Populate `streaming_mode` in all session responses

**`backend/app/application/services/agent_service.py`**
- Guard `get_vnc_url()` with `NotFoundError` in CDP-only mode

### Frontend (8 files)

**Deleted:**
- `frontend/src/components/VNCViewer.vue` (297 lines)
- `frontend/src/composables/useVNCPreconnect.ts` (210 lines)
- `frontend/src/types/novnc.d.ts` (40 lines)

**Modified:**
- `frontend/src/types/response.ts` — Added `StreamingMode` type
- `frontend/src/components/LiveViewer.vue` — Rewritten to CDP-only (~150 lines removed)
- `frontend/src/api/agent.ts` — Deleted `createVncSignedUrl()`, `getVNCUrl()`, `getVNCScreenshot()`
- `frontend/env.d.ts` — Removed `VITE_LIVE_RENDERER`
- `frontend/vite.config.ts` — Removed noVNC CJS transform, optimizeDeps entry
- `frontend/package.json` / `bun.lock` — Removed `@novnc/novnc` dependency

### Tests (6 files)

**Deleted:**
- `frontend/tests/components/VNCViewer.spec.ts` (123 lines)

**Modified:**
- `frontend/tests/components/LiveViewer.spec.ts` — Rewritten for CDP-only
- `frontend/tests/setup.ts` — Removed noVNC mock
- `frontend/tests/mocks/api.ts` — Removed VNC mock functions
- `backend/tests/interfaces/api/test_session_vnc_websocket.py` — Added CDP-only test, dual-mode patches

### Infrastructure (5 files)

- `docker-compose-development.yml` — Removed `VITE_LIVE_RENDERER` env var
- `.env.example` — Changed default to `SANDBOX_STREAMING_MODE=cdp_only`
- `mockserver/routes/sessions.py` — Added `streaming_mode`, VNC signed-url returns 503
- `docs/guides/OPENREPLAY.md` — Updated to CDP-only description
- `docs/architecture/BROWSER_ARCHITECTURE.md` — Updated all VNC references to CDP

---

## Configuration

### Environment Variables

```bash
# Default (recommended)
SANDBOX_STREAMING_MODE=cdp_only

# Legacy mode (requires X11 stack in sandbox)
SANDBOX_STREAMING_MODE=dual
```

### Session Response Contract

```typescript
interface SandboxInfo {
  sandbox_id: string
  streaming_mode: 'dual' | 'cdp_only'
  vnc_url: string | null  // null in cdp_only mode
  status: string
}

interface GetSessionResponse {
  session_id: string
  title: string | null
  status: SessionStatus
  streaming_mode: string | null
  events: AgentSSEEvent[]
  is_shared: boolean
}
```

---

## Impact

### Eliminated

- 30 VNC reconnection attempts per session (5+ seconds of retry overhead)
- Repeated "Connection refused" errors in logs
- VNC WebSocket connection overhead
- noVNC library bundle size (~400KB)
- X11/VNC process management overhead (in cdp_only mode)

### Preserved

- CDP screencast streaming (primary live view mechanism)
- Sandbox isolation (Docker containers)
- Real-time browser visibility
- All existing browser tools and functionality

---

## Migration Guide

### For Deployments

1. Update `.env`:
   ```bash
   SANDBOX_STREAMING_MODE=cdp_only
   ```

2. Rebuild containers:
   ```bash
   ./dev.sh up -d --build
   ```

3. Verify:
   - Frontend loads without errors
   - Live browser preview works via CDP screencast
   - No VNC connection errors in logs

### For Development

No action needed — CDP-only is the new default.

### For Legacy VNC Support

If VNC is required (e.g., for debugging):

1. Set `SANDBOX_STREAMING_MODE=dual`
2. Ensure sandbox includes X11 stack (Xvfb, x11vnc, websockify)
3. Note: VNC client removed from frontend — dual mode only enables VNC in sandbox, not client-side support

---

## Technical Details

### Two-Phase Deletion Pattern

**Step 1: Gate + Contract**
- Added backend guards (VNC endpoints reject with 1008/503)
- Added `streaming_mode` to all session responses
- Rewrote `LiveViewer.vue` to CDP-only
- Removed VNC imports and API functions

**Step 2: Hard Delete**
- Deleted VNC files (VNCViewer, useVNCPreconnect, novnc.d.ts)
- Removed `@novnc/novnc` dependency
- Cleaned build config, tests, docker-compose, docs

### Why This Approach?

- **Safety:** App stays green between steps (Step 1 makes VNC code unreachable)
- **Verifiability:** Each step can be tested independently
- **Rollback:** Step 1 can be reverted without file resurrection

---

## Testing

### Verification Commands

```bash
# Frontend
cd frontend
bun run lint        # ✅ Clean
bun run type-check  # ✅ Clean (pre-existing errors only)

# Backend
conda activate pythinker
cd backend
ruff check .        # ✅ Clean (pre-existing warnings only)
ruff format --check .  # ✅ Clean
pytest tests/interfaces/api/test_session_vnc_websocket.py -v  # ✅ 3/3 pass
```

### Test Results

- **VNC WebSocket Tests:** 3/3 pass
  - `test_vnc_websocket_rejects_in_cdp_only_mode` — New test for CDP-only guard
  - `test_vnc_websocket_returns_policy_violation_for_missing_sandbox_runtime_error` — Existing test with dual-mode patch
  - `test_vnc_websocket_closes_gracefully_when_client_disconnects` — Existing test with dual-mode patch

- **Frontend Tests:** LiveViewer.spec.ts rewritten for CDP-only (3 tests, all pass)

---

## Documentation Updates

### Memory & Core Docs

- `MEMORY.md` — Added VNC removal milestone, removed VNC references
- `CLAUDE.md` — Updated Browser Architecture section to CDP-only
- `docs/architecture/BROWSER_ARCHITECTURE.md` — Comprehensive VNC → CDP rewrite

### Architecture Docs

All VNC references updated in:
- `docs/architecture/BROWSER_ARCHITECTURE.md`
- `docs/guides/OPENREPLAY.md`
- `docs/architecture/PHASE_1_CDP_ONLY_STREAMING_IMPLEMENTATION.md`

---

## Future Considerations

### If VNC Client Needed Again

VNC server still runs in `dual` mode (sandbox-side). To re-add frontend client:

1. Install `@novnc/novnc`
2. Restore `VNCViewer.vue` from git history (commit before 18757bf)
3. Update `LiveViewer.vue` to support VNC fallback
4. Add `VITE_LIVE_RENDERER` env var

**Not recommended** — CDP screencast is faster, lighter, and simpler.

### Deprecation Timeline

- **2026-02-15:** VNC client removed, CDP-only default
- **2026-Q2:** Monitor for dual-mode usage (should be zero)
- **2026-Q3:** Consider removing dual-mode support from sandbox (X11 stack removal)

---

## References

- **Commit:** [18757bf](https://github.com/pythinker/pythinker/commit/18757bf)
- **Plan:** `/Users/panda/.claude/plans/wondrous-painting-willow.md`
- **Related ADRs:**
  - `docs/architecture/BROWSER_STANDARDIZATION_ADR.md`
  - `docs/architecture/PHASE_1_CDP_ONLY_STREAMING_IMPLEMENTATION.md`

---

**Author:** Claude Opus 4.6 (Assisted)
**Reviewed By:** User (Approved)
**Next Review:** 2026-05-15
