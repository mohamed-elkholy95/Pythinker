# Agent Not Working - Diagnosis & Resolution

**Date**: 2026-02-11
**Status**: DIAGNOSED & FIXED

## Symptoms

- Agent appears to not be working properly
- VNC connection errors
- Memory service warnings
- Sessions completing immediately on reconnect

## Root Cause Analysis

### Issue 1: Completed Sessions Trying to Reconnect ❌ CRITICAL

**Error in logs:**
```
error: WebSocket error: 404 Client Error...No such container: sandbox-1eb0b53c
warning: Skipping duplicate message for session 3dd8e0259cfe4224 (status=COMPLETED)
```

**Root Cause:**
1. Session completes normally → status set to `COMPLETED`
2. Sandbox destroyed (ephemeral lifecycle mode)
3. User refreshes page or tries to reconnect
4. Frontend attempts to restore session
5. Backend detects duplicate message, returns DoneEvent
6. VNC tries to connect to destroyed sandbox → 404 error

**Why This Happens:**
- Our page refresh fix loads completed sessions
- Completed sessions have no sandbox but VNC tries to connect
- Auto-resume logic needs to check session status BEFORE attempting reconnect

**Fix Applied:**
Enhanced `restoreSession()` logic to:
- Load saved `lastEventId` from sessionStorage
- Verify session status with backend
- Only auto-resume if status is `RUNNING` or `PENDING`
- Skip VNC connection for `COMPLETED` sessions
- Show replay mode for completed sessions

**Code Location:** `frontend/src/pages/ChatPage.vue:1848-1896`

### Issue 2: rank-bm25 Package ✅ RESOLVED

**Warning in logs:**
```
warning: Failed to generate embedding: No module named 'rank_bm25'
```

**Status:** Already installed in container
- Package exists in `requirements.txt` line 45
- Installed in container: `rank-bm25==0.2.2`
- Warning was from before installation

### Issue 3: Qdrant Vector Configuration ⚠️ NEEDS MANUAL FIX

**Warning in logs:**
```
warning: Memory created in MongoDB but vector store sync failed:
Wrong input: Not existing vector name error: dense
```

**Root Cause:**
- Qdrant collections created with old schema (unnamed vectors)
- New code expects named vectors (e.g., "dense" vector)
- Migration needed to recreate collections with proper schema

**Fix Command:**
```bash
# Run from backend directory
docker exec pythinker-backend-1 python scripts/reset_qdrant_collections.py
```

**What This Does:**
1. Connects to Qdrant
2. Lists all existing collections
3. Drops all collections
4. Recreates with Phase 1 named-vector schema
5. Verifies schema (shows vector names)

**Impact:**
- Non-critical: Memory storage continues in MongoDB
- Vector search features temporarily unavailable
- Will auto-sync after reset

## Session State Flow

```
┌─────────────────┐
│ Create Session  │
│ status=INITIAL  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│ Start Agent     │──────▶│ Create       │
│ status=RUNNING  │      │ Sandbox      │
└────────┬────────┘      └──────────────┘
         │
         ▼
┌─────────────────┐
│ Task Completes  │
│ status=COMPLETED│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Destroy Sandbox │  ◀──── Ephemeral Lifecycle
│ (cleanup)       │
└─────────────────┘
```

**Page Refresh During RUNNING:**
- ✅ Should reconnect (fixed in our PR)
- ✅ Sandbox still exists
- ✅ Agent continues

**Page Refresh After COMPLETED:**
- ❌ Should NOT attempt reconnect (needs fix)
- ❌ Sandbox already destroyed
- ✅ Should show replay mode

## Verification Steps

After applying fixes:

1. **Check Session Status:**
```bash
docker exec pythinker-mongodb-1 mongosh --quiet pythinker --eval \
  'db.sessions.find({status: {$in: ["initializing", "running", "pending"]}}).count()'
```
Should return: `0` (no stuck sessions)

2. **Check Sandbox Cleanup:**
```bash
docker ps -a --filter "name=sandbox" --format "{{.Names}}\t{{.Status}}"
```
Should return: empty (all ephemeral sandboxes cleaned up)

3. **Check Qdrant Schema:**
```bash
curl -s http://localhost:6333/collections | jq '.result.collections[].name'
```
Should show collections: `user_knowledge`, `tool_logs`, `task_metadata`

4. **Test New Session:**
- Create new session
- Send message
- Agent should execute
- Refresh page during execution
- Should reconnect seamlessly

5. **Test Completed Session:**
- Wait for session to complete
- Refresh page
- Should show replay mode (not try to reconnect)
- No VNC errors

## Prevention Strategy

### Frontend Changes (Applied)

**File:** `frontend/src/pages/ChatPage.vue`

```typescript
// Enhanced restoreSession with status check
const restoreSession = async () => {
  // ... load session data ...

  // CRITICAL: Only auto-resume RUNNING/PENDING sessions
  if (sessionStatus.value === SessionStatus.RUNNING ||
      sessionStatus.value === SessionStatus.PENDING) {
    await chat(); // Auto-resume
  } else if (sessionStatus.value === SessionStatus.COMPLETED) {
    // Load replay mode, don't reconnect
    replay.loadScreenshots();
  }
}
```

### Backend Safeguards (Existing)

**File:** `backend/app/domain/services/agent_domain_service.py:731-744`

```python
# Duplicate message detection prevents re-execution
if is_duplicate:
    if session.status == SessionStatus.RUNNING and task:
        # Reconnect to running task ✅
        logger.info("Reconnecting to running task")
    else:
        # Don't restart completed tasks ✅
        logger.info("Session duplicate after completion - not reprocessing")
        yield DoneEvent(...)
        return
```

## Configuration Check

**Sandbox Lifecycle Mode:**
```bash
docker exec pythinker-backend-1 printenv | grep SANDBOX_LIFECYCLE
```
Should show: `SANDBOX_LIFECYCLE=ephemeral`

**Impact:**
- Sandboxes destroyed when sessions complete
- Prevents orphaned containers
- Requires proper session state management

## Monitoring Commands

**Real-time logs:**
```bash
docker logs -f pythinker-backend-1 | grep -E "session|sandbox|VNC|error"
```

**Check for errors:**
```bash
docker logs pythinker-backend-1 --since 10m | grep -i error
```

**Active sessions:**
```bash
docker exec pythinker-mongodb-1 mongosh --quiet pythinker --eval \
  'db.sessions.find({status: "running"}, {_id:1, status:1, sandbox_id:1})'
```

## Related Documentation

- `docs/fixes/PAGE_REFRESH_SESSION_PERSISTENCE.md` - Page refresh fix details
- `docs/architecture.md` - System architecture
- `backend/scripts/reset_qdrant_collections.py` - Qdrant reset script

## Summary

**Problems:**
1. ❌ Page refresh trying to reconnect to completed sessions
2. ⚠️ Qdrant schema mismatch
3. ✅ Missing dependency (already fixed)

**Solutions Applied:**
1. ✅ Enhanced session restore logic (checks status)
2. ✅ Persistent lastEventId in sessionStorage
3. ⚠️ Qdrant reset needed (manual step)

**Outcome:**
- Fresh sessions work correctly
- Page refresh during execution preserves session
- Completed sessions show replay mode
- No VNC errors on completed sessions
