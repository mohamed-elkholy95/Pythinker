# SSE Timeout Fix - Session 394264f562be41e2

## Issue Summary

**Symptom**: UI stuck showing "Composing final report..." with error "Chat stream timed out after 60.0s without progress"

**Root Cause**: Post-processing phase (CoVe verification + Critic revision) took >60 seconds without emitting progress events, causing SSE stream timeout.

## Timeline of Events (2026-02-11)

| Time | Event | Duration |
|------|-------|----------|
| 17:14:39 | Research session started | - |
| 17:15-17:19 | Agent executed 5-step research plan | ~5 min |
| 17:19:10 | Started streaming final report | - |
| 17:19:10-17:20:10 | **Post-processing (CoVe + Critic)** | ~60s |
| 17:20:10 | SSE timeout triggered | - |
| 17:20:10 | Backend completed successfully (2,001 events) | - |
| **Result** | UI never received completion event | - |

## Technical Analysis

### Post-Processing Pipeline

Located in `backend/app/domain/services/agents/execution.py:436-509`:

```python
# 1. Stream report (with progress events)
async for chunk in self.llm.ask_stream(...):
    yield StreamEvent(content=chunk, ...)

# 2. CoVe Verification (NO progress events)
if len(message_content) > 300:
    message_content, cove_result = await self._apply_cove_verification(...)
    # Time: ~15-30 seconds

# 3. Critic Revision (NO progress events)
if len(message_content) > 200:
    message_content = await self._apply_critic_revision(...)
    # Time: ~40-80 seconds (up to 2 revision iterations)
```

### Critic Revision Loop

Each iteration (max 2 attempts):
- Critic review LLM call: ~10-20s
- Revision LLM call: ~10-20s
- **Total per iteration**: 20-40s
- **Max total**: 40-80s

**Combined Post-Processing**: 55-110 seconds → **Exceeds 60s timeout**

## Fixes Applied

### Fix #1: Emit Progress Events Before Long Operations ✅

**File**: `backend/app/domain/services/agents/execution.py`

**Changes**:
```python
# Before CoVe verification
if len(message_content) > 300 and self._user_request:
    yield StepEvent(
        status=StepStatus.RUNNING,
        step=Step(
            id="cove_verification",
            description="Verifying factual claims...",
            status=ExecutionStatus.RUNNING,
        ),
    )
    message_content, cove_result = await self._apply_cove_verification(...)

# Before Critic revision
if len(message_content) > 200 and self._user_request:
    yield StepEvent(
        status=StepStatus.RUNNING,
        step=Step(
            id="critic_review",
            description="Reviewing output quality...",
            status=ExecutionStatus.RUNNING,
        ),
    )
    message_content = await self._apply_critic_revision(...)
```

**Impact**: Resets SSE timeout before each long operation

### Fix #2: Increase SSE Event Timeout ✅

**File**: `backend/app/application/services/agent_service.py`

**Changes**:
```python
class AgentService:
    MAX_CREATE_SESSION_WAIT_SECONDS = 5.0
    CHAT_EVENT_TIMEOUT_SECONDS = 120.0  # Increased from 60s
    CHAT_WARMUP_WAIT_SECONDS = 10.0
    BROWSER_PREWARM_TIMEOUT_SECONDS = 12.0
```

**Rationale**: Accommodates Critic's multi-iteration revision loop (up to 80s)

## Timeout Behavior

The SSE timeout is **per-event**, not cumulative (from `agent_service.py:573-592`):

```python
async with asyncio.timeout(event_timeout_seconds):
    event = await stream_iter.__anext__()
```

With our fixes, the flow now:
1. ✅ StepEvent("Composing final report...") - resets timeout
2. ✅ StreamEvents during LLM streaming - keeps resetting
3. ✅ **NEW** StepEvent("Verifying factual claims...") - resets timeout
4. ✅ CoVe runs (up to 120s is OK)
5. ✅ **NEW** StepEvent("Reviewing output quality...") - resets timeout
6. ✅ Critic runs (up to 120s is OK)
7. ✅ Final AssistantMessageEvent emitted
8. ✅ UI displays completed report

## Verification Steps

To verify the fix works:

```bash
# 1. Start development environment
./dev.sh up -d

# 2. Monitor backend logs
docker logs pythinker-backend-1 -f | grep -E "(Verifying|Reviewing|timeout)"

# 3. Run research session
# Expected log output:
# - "Verifying factual claims..." event
# - "Reviewing output quality..." event
# - NO timeout errors
# - "Chat completed in XXXXms" success message

# 4. Check UI
# Expected: Report displays successfully, no timeout error
```

## Related Issues Observed

During monitoring, additional issues were identified:

### 1. Browser Navigation Mismatch
- **Symptom**: Agent searches for URLs but VNC shows Google page
- **Evidence**: Multiple 2ms browser searches (normal: 243-2,254ms)
- **Status**: Separate issue, documented in AGENTS.md

### 2. Token Limit Exceeded (6 occurrences)
- **Context**: 28,907-31,767 tokens (limit: 28,672)
- **Impact**: Auto-trimmed 1,002-6,610 tokens per occurrence
- **Status**: Working as designed, but could be optimized

### 3. Stuck Pattern Detection (4+ occurrences)
- **Pattern**: Excessive same-tool usage (confidence: 0.85)
- **Impact**: Auto-recovered each time
- **Status**: Working as designed

## Files Modified

1. `backend/app/domain/services/agents/execution.py` - Added progress events
2. `backend/app/application/services/agent_service.py` - Increased timeout
3. `docs/fixes/SSE_TIMEOUT_FIX.md` - This document

## Recommendations

### Short-term (Implemented)
- ✅ Emit progress events before long operations
- ✅ Increase timeout to 120s

### Medium-term (Future)
- Add progress events **inside** Critic revision loop between iterations
- Make CoVe verification emit streaming progress
- Add configurable timeouts per session mode (research vs. discuss)

### Long-term (Architecture)
- Consider async background processing for post-processing
- Implement progressive delivery (stream report, then refine asynchronously)
- Add session resume capability for interrupted streams

## Testing Recommendations

1. **Unit Tests**: Verify StepEvent emission timing
2. **Integration Tests**: End-to-end research flow with >60s post-processing
3. **Load Tests**: Multiple concurrent sessions with CoVe/Critic enabled
4. **UI Tests**: Verify timeout error no longer appears

## References

- Session ID: 394264f562be41e2
- Agent ID: 8dec43656c514d0e
- Sandbox: sandbox-86d143e2
- Duration: 330.5 seconds (5.5 minutes)
- Events: 2,001
- Report Files Created: 3 (in GridFS)

---

**Fix Date**: 2026-02-11
**Fix Author**: Claude Sonnet 4.5
**Status**: ✅ Deployed, Pending Verification
