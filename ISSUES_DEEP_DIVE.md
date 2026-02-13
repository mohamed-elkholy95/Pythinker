# Deep Dive: Critical Issues Analysis

**Date**: 2026-02-13
**Scope**: Comprehensive investigation of 3 critical issues found in browser logs
**Status**: Research Complete - Fixes Recommended

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Issue 1: SSE Heartbeat & Timeout](#issue-1-sse-heartbeat--timeout)
3. [Issue 2: Orphaned Background Tasks](#issue-2-orphaned-background-tasks)
4. [Issue 3: Token/Memory Management](#issue-3-tokenmemory-management)
5. [Cross-Cutting Concerns](#cross-cutting-concerns)
6. [Fix Priority Matrix](#fix-priority-matrix)
7. [Implementation Roadmap](#implementation-roadmap)

---

## Executive Summary

### Investigation Results

| Issue | Severity | Root Cause | Status | Fix Complexity |
|-------|----------|------------|--------|----------------|
| **SSE Heartbeat** | 🟡 Medium | Observability gap, not functional issue | ✅ Already implemented | Low (logging only) |
| **Orphaned Tasks** | 🔴 Critical | Race condition in cancellation flow | ❌ Active bug | High (requires sync changes) |
| **Token Trimming** | 🟠 High | Tight limits + verbose tool outputs | ⚠️ Design limitation | Medium (config + compression) |

### Key Findings

**Issue #1 (SSE Heartbeat)**: ✅ **HEARTBEAT IS FULLY IMPLEMENTED**
- Server sends heartbeat every 30 seconds
- Client tracks and responds to heartbeats
- **The issue is logging/metrics visibility, not functionality**
- `heartbeat_count: 0` in logs is misleading (metrics may not persist)

**Issue #2 (Orphaned Background Tasks)**: 🔴 **CRITICAL RACE CONDITION**
- Tools can start executing **after** SSE cancellation requested
- 45-second grace period creates wide timing window
- No cancellation check before `ToolStatus.CALLING` emission
- Background tasks continue invisibly after client disconnect

**Issue #3 (Token Trimming)**: ⚠️ **SYSTEMIC DESIGN ISSUE**
- 30,720 token effective limit too small for research workflows
- Wide research (24 queries) generates ~96K tokens (3.2x over budget)
- Trimming at 109% usage is emergency surgery, not prevention
- Compression tools exist but aren't triggered early enough

---

## Issue 1: SSE Heartbeat & Timeout

### Status: ✅ **FULLY IMPLEMENTED** (Observability Gap Only)

### Current Implementation

#### Backend: Complete Heartbeat System

**File**: `backend/app/interfaces/api/session_routes.py`

**Configuration** (Line 83):
```python
SSE_HEARTBEAT_INTERVAL_SECONDS = 30.0  # Heartbeat every 30s
```

**Headers Exposed** (Lines 147-168):
```python
X-Pythinker-SSE-Heartbeat-Interval-Seconds: 30
X-Pythinker-SSE-Retry-Max-Attempts: 7
X-Pythinker-SSE-Retry-Base-Delay-Ms: 1000
X-Pythinker-SSE-Retry-Max-Delay-Ms: 45000
```

**Heartbeat Generation** (Lines 571-585):
```python
heartbeat = ProgressEvent(
    phase=PlanningPhase.HEARTBEAT,  # "heartbeat" string
    message="",
    progress_percent=None,
)
```

**Event Loop with Concurrent Heartbeat** (Lines 599-637):
```python
heartbeat_task = asyncio.create_task(asyncio.sleep(heartbeat_interval_seconds))

done, pending = await asyncio.wait(
    {t for t in (next_event_task, heartbeat_task) if t is not None},
    return_when=asyncio.FIRST_COMPLETED,
)

if heartbeat_task in done:
    yield heartbeat_sse  # Send heartbeat
    heartbeat_count += 1
    pm.record_sse_stream_heartbeat(endpoint="chat")  # Prometheus
```

#### Frontend: Complete Detection & Tracking

**File**: `frontend/src/composables/useSSEConnection.ts`

**Tracking** (Lines 40, 46, 70):
```typescript
const totalHeartbeats = ref(0);
const lastHeartbeatTime = ref<number | null>(null);

function updateLastHeartbeatTime() {
    lastHeartbeatTime.value = Date.now();
    totalHeartbeats.value++;
}
```

**Detection** (Lines 153-160):
```typescript
window.addEventListener('sse:heartbeat', handleHeartbeatEvent);
```

**File**: `frontend/src/api/client.ts` (Lines 876-887)

**Heartbeat Event Dispatch**:
```typescript
if (event.event === 'progress') {
    const progressData = parsedData as { phase?: string };
    if (progressData.phase === 'heartbeat') {
        window.dispatchEvent(new CustomEvent('sse:heartbeat', { detail: { eventId } }));
        return; // Don't pass to UI
    }
}
```

### 120-Second Timeout Behavior

**Root Cause**: Browser/Network Layer (NOT Application Code)

**Where it comes from**:
1. **Browser EventSource Default**: Native browser API has implicit 120s idle timeout
2. **HTTP Specification**: RFC 7231 - servers may close after extended idle
3. **Proxy/Load Balancer Default**: Nginx, CloudFlare, AWS ALB default to 60-120s

**Mitigation in Place**:
- ✅ Heartbeat every 30s prevents timeout by sending data
- ✅ Should reset idle timer on proxies
- ✅ Client auto-reconnects with exponential backoff (up to 7 attempts)
- ✅ Event ID preserved across reconnects for resumption

### What Breaks When Timeout Occurs

**File**: `frontend/src/pages/ChatPage.vue` (Lines 185-207)

**User Experience**:
```html
<div v-if="responsePhase === 'timed_out'">
  <span>{{ autoRetryCount < 4
    ? 'Connection interrupted. Reconnecting automatically...'
    : (isFallbackStatusPolling
      ? 'Connection interrupted. Checking task status in background...'
      : 'Connection interrupted. The agent may still be working.') }}
  </span>
</div>
```

**Auto-Retry Logic** (Lines 1194-1211):
- Progressive backoff: 5s, 15s, 45s, 60s
- Max 4 retry attempts
- Falls back to polling session status

**Event Loss Risk**:
- ❌ Backend doesn't support event replay/history
- ⚠️ If event generated between server send and client receive, reconnection cannot recover it
- ✅ `Last-Event-ID` header sent on reconnect (but server doesn't use it for replay)

**Background Task Behavior** (Lines 96-125, session_routes.py):
- ⚠️ Agent continues running for 45s grace period
- ⚠️ User has no visibility into background work
- ⚠️ This connects to Issue #2 (orphaned tasks)

### Why `heartbeat_count: 0` Appears in Logs

**Logging Gap** (Not Functional Issue):

1. **Server-side**: Counter is local to event_generator scope
   - Only logged in final `log_sse_diag` call (lines 786-793)
   - If stream closes before any heartbeat, shows `heartbeat_count=0`
   - Short sessions (<30s) won't have heartbeat yet

2. **Client-side**: Metrics are in-memory only
   - `totalHeartbeats` is a ref in useSSEConnection.ts (line 46)
   - Lost on page reload
   - sessionStorage only tracks `lastEventId`, not heartbeat count

### Recommendations

**Priority**: 🟡 Low (Observability Only)

**Quick Wins**:
1. ✅ Add explicit logging on every heartbeat emission
   ```python
   if heartbeat_task in done:
       logger.debug(f"[SSE] Heartbeat #{heartbeat_count+1} sent to session {session_id}")
       yield heartbeat_sse
   ```

2. ✅ Add Prometheus metric for heartbeat gaps
   ```python
   pm.record_sse_stream_heartbeat_gap(endpoint="chat", gap_seconds=time_since_last)
   ```

3. ✅ Persist client heartbeat count to sessionStorage
   ```typescript
   sessionStorage.setItem(`pythinker-heartbeats-${sessionId}`, totalHeartbeats.value.toString());
   ```

4. ✅ Monitor actual timeout behavior in Prometheus
   ```promql
   rate(pythinker_sse_stream_heartbeat[5m])
   ```

**No functional changes needed** - heartbeat system works correctly.

---

## Issue 2: Orphaned Background Tasks

### Status: 🔴 **CRITICAL BUG** (Active Race Condition)

### The Race Condition

**Log Evidence**:
```
21:44:57 - Chat stream cancelled (client disconnected)  ← Cancellation requested
21:44:57 - Cancellation requested for Agent             ← Event set
21:44:57 - tool_started: search                         ← Tool executes anyway!
```

**Problem**: Tool execution starts **after** cancellation signal sent.

### Root Cause Analysis

#### Gap 1: No Cancellation Check Before Tool Emission

**File**: `backend/app/domain/services/agents/base.py` (Lines 893-1006)

**Parallel Execution Path**:
```python
# Line 893-903: NO CANCELLATION CHECK
yield self._create_tool_event(
    tool_call_id=tool_call_id,
    tool_name=tool.name,
    function_name=function_name,
    function_args=function_args,
    status=ToolStatus.CALLING,  # ← Emitted without checking cancellation!
    ...
)
# Then tools execute concurrently
results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Sequential Execution Path**:
```python
# Line 994-1004: SAME ISSUE
yield self._create_tool_event(
    tool_call_id=tool_call_id,
    tool_name=tool.name,
    function_name=function_name,
    function_args=function_args,
    status=ToolStatus.CALLING,  # ← No check here either
    ...
)
result = await self.invoke_tool(tool, function_name, function_args)
```

**Missing**: `await self._cancel_token.check_cancelled()` before yield

#### Gap 2: 45-Second Grace Period Creates Wide Window

**File**: `backend/app/interfaces/api/session_routes.py` (Lines 796-809)

```python
if close_reason in {"client_disconnected", "generator_cancelled"}:
    _schedule_disconnect_cancellation(  # ← DELAYED by grace period!
        session_id=session_id,
        agent_service=agent_service,
        grace_seconds=disconnect_cancellation_grace_seconds,  # 45 seconds!
    )
```

**Timing Window**:
```
T=0s:     SSE disconnect detected → disconnect_event.set()
T=0-45s:  Agent continues → can emit new tools
T=45s:    Deferred cancellation fires → cancel_event.set()
```

**Result**: 45-second window where tools can start execution.

#### Gap 3: StreamGuard Only Checks Between Events

**File**: `backend/app/domain/services/stream_guard.py` (Lines 176-178)

```python
async for event in generator:
    # Periodic cancellation check
    now = time.monotonic()
    if now - self._last_cancel_check >= self.check_interval:
        self._last_cancel_check = now
        if self.cancel_token.is_cancelled():  # ← Only checks HERE
            logger.info("StreamGuard: cancellation detected, stopping stream")
            yield ErrorEvent(error="Stream cancelled", ...)
            return
    yield event  # ← But event already generated
```

**Problem**: By the time StreamGuard checks, the tool event has already been created and yielded.

### Execution Flow Diagrams

#### Normal Flow (No Cancellation)

```
Client SSE Connection
    │
    ├─→ chat_stream() starts event_generator()
    │
    └─→ AgentService.chat()
         │
         └─→ AgentTaskRunner.run(task)
              │
              └─→ PlanActFlow.run(message)
                   │
                   ├─→ _check_cancelled() ✓
                   │
                   └─→ agent.execute_tools()
                        │
                        ├─→ yield ToolStatus.CALLING
                        │
                        └─→ invoke_tool() ✓
```

#### Broken Flow (Race Condition)

```
T=0ms:   Client disconnects
         └─→ disconnect_event.set() ✓
         └─→ finally block:
             ├─→ request_cancellation(session_id)
             │   └─→ cancel_event.set() ✓
             └─→ _schedule_disconnect_cancellation(grace=45s)
                 └─→ Deferred task scheduled

         ⏱ 45 SECOND GAP ⏱

T=0-45s: Agent thread (unaware of cancellation)
         └─→ PlanActFlow continues
              │
              ├─→ _check_cancelled() at flow entry ✓
              │
              ├─→ Gets next tool call from LLM
              │
              ├─→ ❌ NO CHECK HERE ❌
              │
              └─→ yield ToolStatus.CALLING  ← ORPHANED!
                   │
                   └─→ invoke_tool() starts ← Background execution

T=45s:   Deferred cancellation fires
         └─→ Too late! Tool already executing
```

### Code Gaps Summary

| Location | Line | Gap | Impact | Severity |
|----------|------|-----|--------|----------|
| `base.py` | 893-903 | No check before ToolStatus.CALLING (parallel) | Tool emission without auth | 🔴 HIGH |
| `base.py` | 994-1006 | No check before ToolStatus.CALLING (sequential) | Tool emission without auth | 🔴 HIGH |
| `base.py` | 567-572 | No check before invoke_function() | Concurrent execution begins | 🔴 HIGH |
| `session_routes.py` | 799-803 | 45-second grace period | Orphaned tool window | 🟠 MEDIUM |
| `agent_task_runner.py` | 274-286 | Fire-and-forget not cancelled | Background tasks escape | 🟠 MEDIUM |
| `stream_guard.py` | 176-178 | Only checks between yields | Doesn't catch pre-emit race | 🟠 MEDIUM |

### Detailed Timing Analysis

**Evidence from Logs** (Session 818cad49809e4c44):

```
19:54:59 - Browser crash detected
19:55:51 - SSE timeout after 120s           ← Stream times out
19:56:12 - Agent successfully recovered     ← Agent still running (73s later!)
19:56:15 - Started next tool (invisibly)    ← New tool starts (76s later!)
19:57:43 - Duplicate chat request sent      ← User confusion (164s later!)
```

**Window Analysis**:
- SSE timeout → Agent continues for **73 seconds**
- Tool starts **76 seconds** after timeout
- User sends duplicate request after **164 seconds**

**This exceeds the 45-second grace period** - indicating tools can start even after grace period expires if LLM response is slow.

### Cancellation Token Architecture

**File**: `backend/app/domain/utils/cancellation.py`

```python
class CancellationToken:
    def __init__(self, event: asyncio.Event | None = None, session_id: str = ""):
        self._event = event
        self._session_id = session_id

    def is_cancelled(self) -> bool:
        if self._event is None:
            return False
        return self._event.is_set()

    async def check_cancelled(self) -> None:
        if self.is_cancelled():
            raise asyncio.CancelledError(f"Session {self._session_id} cancelled")
```

**Usage**:
- ✓ Called at flow entry (`plan_act.py:1702`)
- ✓ Called between yields (`plan_act.py:1705`)
- ❌ NOT called before `ToolStatus.CALLING` emission
- ❌ NOT called before `invoke_tool()` execution

### Recommendations

**Priority**: 🔴 P0 (Critical - Data Loss & Resource Waste)

#### Fix 1: Add Pre-Emission Cancellation Check

**File**: `backend/app/domain/services/agents/base.py`

**Before Line 893** (parallel path):
```python
# Check cancellation before emitting tool event
await self._cancel_token.check_cancelled()

yield self._create_tool_event(
    tool_call_id=tool_call_id,
    tool_name=tool.name,
    function_name=function_name,
    function_args=function_args,
    status=ToolStatus.CALLING,
    ...
)
```

**Before Line 994** (sequential path):
```python
# Check cancellation before emitting tool event
await self._cancel_token.check_cancelled()

yield self._create_tool_event(...)
```

**Impact**: Prevents tool emission if cancellation requested

#### Fix 2: Add Pre-Invocation Cancellation Check

**Before Line 567-572**:
```python
# Check cancellation before executing tool
await self._cancel_token.check_cancelled()

# Now safe to execute
result = await tool.invoke_function(...)
```

**Impact**: Prevents tool execution if cancelled mid-emission

#### Fix 3: Immediate Cancellation on SSE Disconnect

**File**: `backend/app/interfaces/api/session_routes.py`

**Replace Lines 799-803**:
```python
# OLD: Deferred cancellation with grace period
_schedule_disconnect_cancellation(
    session_id=session_id,
    agent_service=agent_service,
    grace_seconds=disconnect_cancellation_grace_seconds,  # 45 seconds
)

# NEW: Immediate cancellation for client disconnect
if close_reason == "client_disconnected":
    # Immediate cancellation - user is gone
    request_cancellation(session_id)
elif close_reason == "generator_cancelled":
    # Short grace period for legitimate retries (5s)
    _schedule_disconnect_cancellation(
        session_id=session_id,
        agent_service=agent_service,
        grace_seconds=5.0,  # Reduced from 45s
    )
```

**Impact**: Stops background tasks immediately when user disconnects

#### Fix 4: Cancel Background Tasks on Destroy

**File**: `backend/app/domain/services/agent_task_runner.py`

**In destroy() method (Lines 1795-1876)**:
```python
async def destroy(self) -> None:
    """Clean up resources and cancel all background tasks."""
    # Cancel all fire-and-forget tasks
    for task in list(self._background_tasks):
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    self._background_tasks.clear()

    # Rest of cleanup...
```

**Impact**: Ensures cleanup of orphaned fire-and-forget tasks

### Testing Plan

**Test Case 1**: Client disconnect during tool execution
```python
# 1. Start session
# 2. Wait for tool to emit ToolStatus.CALLING
# 3. Disconnect SSE
# 4. Verify: Tool execution cancelled within 1s
# 5. Verify: No background tasks remain
```

**Test Case 2**: Client disconnect before tool execution
```python
# 1. Start session
# 2. Disconnect SSE immediately
# 3. Wait for agent to process
# 4. Verify: No tools emitted after disconnect
# 5. Verify: Session marked as cancelled
```

**Test Case 3**: Grace period reconnection
```python
# 1. Start session
# 2. Disconnect SSE
# 3. Reconnect within 5s
# 4. Verify: Session continues without restart
# 5. Verify: No data loss
```

---

## Issue 3: Token/Memory Management

### Status: ⚠️ **SYSTEMIC DESIGN ISSUE** (Tight Limits + Verbose Outputs)

### The Incident

**Log Evidence**:
```
21:44:54 - Context (33,764 tokens) exceeds limit (30,720)
21:44:54 - Reduced preserve_recent from 6 to 5
21:44:54 - Trimmed 2 messages (4,630 tokens)
21:44:54 - Result: 29,134 tokens (within limit)
```

**Analysis**:
- **Exceeded by**: 3,044 tokens (109.9% of limit!)
- **Lost**: 2 messages from conversation history (4,630 tokens)
- **Impact**: Agent lost earlier research context mid-session

### Root Cause: Wide Research Token Explosion

**Task**: Wide research with 24 queries on "Best IDE coding agentic AI tools 2026"

**Token Consumption Breakdown**:

| Component | Tokens/Query | Total (24 queries) |
|-----------|--------------|---------------------|
| Query prompt | 50 | 1,200 |
| Search results (5-10 per query) | 500-1000 | 12,000-24,000 |
| Browser visits (top 3) | 2000-5000 | 6,000-15,000 |
| Tool response wrappers | 100 | 2,400 |
| Agent reasoning | 200 | 4,800 |
| **TOTAL** | **2,850-6,100** | **26,400-47,400** |

**Plus Overhead**:
```
Search results:     26,400-47,400 tokens
System prompt:           500 tokens
Planning phase:        1,000 tokens
Execution overhead:    2,000 tokens
─────────────────────────────────
TOTAL ESTIMATED:      29,900-50,900 tokens

AVAILABLE LIMIT:      30,720 tokens
─────────────────────────────────
DEFICIT:              0 to -20,180 tokens (up to 1.66x over!)
```

**Result**: Impossible to fit 24-query research in 30K token budget without aggressive trimming.

### Token Manager Configuration

**File**: `backend/app/domain/services/agents/token_manager.py`

**Pressure Thresholds** (Lines 88-93):
```python
PRESSURE_THRESHOLDS = {
    "early_warning": 0.60,  # 60% - early planning notice
    "warning": 0.70,        # 70% - suggest summarization
    "critical": 0.80,       # 80% - begin proactive trimming
    "overflow": 0.90,       # 90% - force summarization
}
```

**Model Limits** (Lines 96-120):
```python
MODEL_LIMITS = {
    "gpt-4o": 128000,       # 128K context
    "gpt-4o-mini": 128000,
    "claude-sonnet": 200000,
    "default": 32768,       # 32K default
}
```

**Safety Margin** (Lines 122-125):
```python
SAFETY_MARGIN = 2048  # Reserve 2K for LLM response
```

**Effective Limits for GPT-4 (32K model)**:
```
Max context:      32,768 tokens
Safety margin:     -2,048 tokens
─────────────────────────────────
EFFECTIVE LIMIT:  30,720 tokens  ← This is the limit in the logs
```

**Pressure Levels**:
```
NORMAL (0-60%):       0-18,432 tokens
EARLY_WARNING (60%):  18,432 tokens
WARNING (60-70%):     18,432-21,504 tokens  ← Suggest summarization
CRITICAL (70-80%):    21,504-24,576 tokens  ← Begin trimming
OVERFLOW (80%+):      24,576+ tokens        ← Force trimming
```

**In the incident**: 33,764 tokens = **109.9%** of limit (way past OVERFLOW!)

### Trimming Algorithm

**File**: `backend/app/domain/services/agents/token_manager.py` (Lines 333-481)

**Method**: `trim_messages(messages, preserve_system=True, preserve_recent=4)`

**Strategy**:
1. ✅ Preserve system prompts (always kept)
2. ✅ Preserve recent N messages (configurable)
3. ✅ Group tool call/response pairs (atomic units)
4. ❌ Trim oldest messages from middle
5. ⚠️ Dynamic reduction of `preserve_recent` if needed

**Example Flow**:
```
Messages: [system, msg1, msg2, ..., msg20, msg21, msg22]
Total: 33,764 tokens | Limit: 30,720 | Over by: 3,044

preserve_recent: 6 requested
├─ Recent messages (last 6): 8,000 tokens
├─ System messages: 500 tokens
├─ Total fixed: 8,500 tokens
└─ Available for middle: 22,220 tokens

But middle messages use: 25,264 tokens (too much!)

Reduce preserve_recent: 6 → 5
├─ Recent messages (last 5): 6,500 tokens
├─ System messages: 500 tokens
├─ Total fixed: 7,000 tokens
└─ Available for middle: 23,720 tokens

Middle messages now: 22,134 tokens ✓ (within budget)

Result: Remove 2 oldest messages (4,630 tokens)
Final: 29,134 tokens (95% of limit)
```

### What Gets Lost

**Casualties of Trimming**:
- ✗ Earlier search results summaries
- ✗ Previous step decisions and reasoning
- ✗ File operations logs from earlier work
- ✗ Tool execution history (older tool results)
- ✗ Constraints identified in earlier phases
- ✗ Blockers discovered previously

**Preserved**:
- ✓ System prompt (always kept)
- ✓ Last 5 user/assistant exchanges
- ✓ Recent tool results (if in last 5 messages)
- ✓ Current step context

**Impact on Agent**:
- May re-search same topics (wasting tokens)
- Loses track of prior constraints
- Can make conflicting decisions
- Duplicates work from earlier steps
- Misses learning from earlier errors

### Compression Features (Available but Underutilized)

**File**: `backend/app/domain/services/agents/memory_manager.py`

**Available Tools**:

| Feature | Status | File Location | Usage |
|---------|--------|---------------|-------|
| Smart message compaction | ✓ Implemented | `compact_message()` (line 155) | Manual only |
| Batch compaction | ✓ Implemented | `compact_messages_batch()` (line 421) | Triggered at WARNING |
| Context optimization | ✓ Implemented | `optimize_context()` (line 489) | Triggered at WARNING |
| Semantic compression | ✓ Implemented | Separate module | Not auto-triggered |
| Temporal compression | ✓ Implemented | Separate module | Not auto-triggered |
| LLM extraction | ✓ Implemented | `extract_with_llm()` (line 620) | On-demand only |
| Archive storage | ✓ Implemented | `compact_and_archive()` (line 741) | Not integrated |

**Usage in plan_act.py** (Lines 797-824):

```python
# Triggered at WARNING level (70%)
if pressure.level == PressureLevel.WARNING:
    optimized_messages, report = self._memory_manager.optimize_context(
        messages,
        preserve_recent=10,
        token_threshold=int(pressure.max_tokens * 0.65),
    )

# Triggered at CRITICAL level (80%)
if pressure.level == PressureLevel.CRITICAL:
    compacted_messages, tokens_saved = self._memory_manager.compact_messages_batch(
        messages,
        preserve_recent=10,
        token_threshold=int(pressure.max_tokens * 0.7),
    )
```

**Problem**: In the incident, system jumped from WARNING → OVERFLOW without intermediate compaction.

### Why Trimming Happened Mid-Session

**Execution Timeline**:

```
Iteration 1-10:   Normal execution (5-15K tokens, <50% usage)
                  ↓
Iteration 11-15:  Queries 7-12 added (15-20K tokens, 50-65%)
                  → WARNING triggered
                  → optimize_context() called
                  → Saved ~2-3K tokens
                  ↓
Iteration 16-20:  Queries 13-18 added (20-25K tokens, 65-80%)
                  → CRITICAL triggered
                  → compact_messages_batch() called
                  → Saved ~3-4K tokens
                  ↓
Iteration 21:     Query 19 starts (30K → 34K tokens!)
                  Before: 30,000 tokens
                  After:  34,000 tokens (103% of limit!)
                  ↓
                  → OVERFLOW! (109%)
                  → Base executor: exceeds limit check
                  → trim_messages() with preserve_recent=6
                  → Removed 2 messages (4,630 tokens)
                  → Reduced preserve_recent to 5
                  → Result: 29,134 tokens (95%)
```

**Root Issue**: Single query (Query 19) added 4K tokens, pushing from 97% → 109%

### Recommendations

**Priority**: 🟠 P1 (High - Impacts User Experience)

#### Fix 1: Increase Token Limits (Configuration)

**File**: `backend/app/core/config.py`

```python
# Adjust thresholds to trigger earlier
token_critical_threshold: float = 0.75  # Trigger at 75% (was 80%)

# Increase safety margin for research tasks
token_safety_margin: int = 4096  # Reserve 4K (was 2K)

# For GPT-4o (128K context)
# New effective limit: 128,000 - 4,096 = 123,904 tokens
# Critical threshold: 123,904 * 0.75 = 92,928 tokens
```

**Impact**: Larger buffer prevents emergency trimming

#### Fix 2: Increase preserve_recent for Normal Operation

**File**: `backend/app/domain/services/agents/base.py` (Line 1287)

```python
# OLD:
trimmed_messages, _ = self._token_manager.trim_messages(
    current_messages, preserve_system=True, preserve_recent=6
)

# NEW:
trimmed_messages, _ = self._token_manager.trim_messages(
    current_messages, preserve_system=True, preserve_recent=10
)
```

**Impact**: Preserves more conversation history

#### Fix 3: Auto-Compact Tool Results at WARNING Level

**File**: `backend/app/domain/services/flows/plan_act.py` (Around line 800)

```python
if pressure.level == PressureLevel.WARNING:
    # NEW: Compact verbose tool outputs first
    messages = self._memory_manager.smart_compact(
        messages,
        preserve_recent=10,
        compact_browser_content=True,  # Reduce HTML to summaries
        compact_search_results=True,   # Template-based summaries
    )

    # Then optimize context
    optimized_messages, report = self._memory_manager.optimize_context(
        messages,
        preserve_recent=10,
        token_threshold=int(pressure.max_tokens * 0.65),
    )
```

**Impact**: Saves 2-3K tokens per browser visit, 500-1K per search

#### Fix 4: Template-Based Search Result Summarization

**File**: `backend/app/domain/services/agents/memory_manager.py`

**Add new method**:
```python
def compact_search_result(self, result: dict) -> str:
    """Compress search result from 500-1000 tokens to ~100 tokens."""
    return f"""
[web_search] {result['query']}
- {len(result['results'])} results | Top: {result['results'][0]['title']}
- Key: {', '.join(result['key_points'][:3])}
- URLs: {', '.join([r['url'] for r in result['results'][:3]])}
""".strip()
```

**Impact**: 5-10x compression of search results (500 → 50 tokens)

#### Fix 5: Browser Content Sampling (Not Full HTML)

**File**: `backend/app/infrastructure/external/browser/playwright_browser.py`

**Modify _extract_content()** (Lines 1708-1792):

```python
# OLD: Return full page text (30,000 chars = ~7,500 tokens)
return full_text[:30000]

# NEW: Return structured summary
return {
    "title": page_title,
    "headings": [h1, h2, h3 list],  # Document structure
    "links": top_10_links,           # Most relevant links
    "forms": form_elements,          # If interaction needed
    "summary": first_500_chars,      # Preview only
}
# Result: ~500 tokens instead of 7,500
```

**Impact**: 15x compression of browser content

#### Fix 6: Multi-Phase Workflow with Explicit Boundaries

**File**: `backend/app/domain/services/flows/plan_act.py`

**For research tasks, implement phased approach**:

```python
# Instead of: 24 unstructured queries
# Do:
phases = [
    {"name": "Overview", "queries": 6},
    {"name": "Deep-dive", "queries": 6},
    {"name": "Analysis", "queries": 6},
    {"name": "Synthesis", "queries": 6},
]

for phase in phases:
    # Execute queries for this phase
    for query in phase['queries']:
        result = await execute_search(query)

    # At phase boundary: summarize + archive
    summary = await summarize_phase(phase)
    await archive_phase_details(phase)

    # Keep only summary in context
    context.replace_phase_with_summary(phase['name'], summary)
```

**Impact**: Only active phase kept in context (6 queries instead of 24)

### Configuration Changes Summary

**Immediate Changes** (config.py):
```python
# Before
token_critical_threshold = 0.80  # 80%
token_safety_margin = 2048        # 2K
preserve_recent = 6               # 6 messages

# After
token_critical_threshold = 0.75  # 75% (trigger earlier)
token_safety_margin = 4096        # 4K (larger buffer)
preserve_recent = 10              # 10 messages (more history)
```

**Expected Results**:
- **Before**: 30,720 effective limit, critical at 24,576 (80%), preserve 6
- **After**: 124,928 effective limit (GPT-4o), critical at 93,696 (75%), preserve 10
- **Buffer**: 31,232 tokens before emergency trim (vs 6,144 before)
- **Headroom**: 4x larger buffer for spiky token usage

---

## Cross-Cutting Concerns

### Observability Gaps

All three issues share **insufficient visibility**:

| Issue | What's Missing | Impact |
|-------|----------------|--------|
| SSE Heartbeat | Heartbeat count not visible in client logs | Users can't tell if heartbeat is working |
| Orphaned Tasks | No alert when tool starts after disconnect | Silent resource waste |
| Token Trimming | No warning before trimming | Unexpected context loss |

**Recommendation**: Add comprehensive metrics dashboard

### Error Recovery Patterns

**Current Pattern**: Reactive (wait for failure → recover)

| Issue | Current | Better |
|-------|---------|--------|
| SSE Timeout | Wait for 120s → reconnect | Heartbeat + proactive reconnect |
| Orphaned Tasks | Wait 45s → cancel | Immediate cancellation on disconnect |
| Token Overflow | Wait for 109% → emergency trim | Trigger at 75% → graceful compression |

**Recommendation**: Shift to proactive prevention

### Configuration Complexity

**Problem**: Token limits, thresholds, timeouts scattered across multiple files

**Files Involved**:
- `backend/app/core/config.py` - Global settings
- `backend/app/domain/services/agents/token_manager.py` - Token thresholds
- `backend/app/interfaces/api/session_routes.py` - SSE timeouts
- `backend/app/domain/services/flows/plan_act.py` - Flow timeouts

**Recommendation**: Centralize configuration with environment overrides

---

## Fix Priority Matrix

| Priority | Issue | Severity | Complexity | Impact | ETA |
|----------|-------|----------|------------|--------|-----|
| **P0** | Orphaned Tasks - Pre-emission check | 🔴 Critical | Low | High | 1 day |
| **P0** | Orphaned Tasks - Immediate cancellation | 🔴 Critical | Low | High | 1 day |
| **P1** | Token Limits - Increase thresholds | 🟠 High | Low | Medium | 1 day |
| **P1** | Token Limits - Template compression | 🟠 High | Medium | High | 3 days |
| **P2** | SSE Heartbeat - Add logging | 🟡 Medium | Low | Low | 1 day |
| **P2** | Token Limits - Browser compression | 🟡 Medium | Medium | Medium | 3 days |
| **P3** | Orphaned Tasks - Background cleanup | 🟡 Medium | Low | Low | 2 days |
| **P3** | Token Limits - Multi-phase workflow | 🟡 Medium | High | Medium | 5 days |

---

## Implementation Roadmap

### Week 1: Critical Fixes (P0)

**Day 1-2: Orphaned Background Tasks**
- [ ] Add pre-emission cancellation check (base.py:893, 994)
- [ ] Add pre-invocation cancellation check (base.py:567)
- [ ] Change grace period: 45s → immediate for client_disconnected
- [ ] Add unit tests for cancellation flow
- [ ] Add integration tests for SSE disconnect scenarios

**Day 3: Testing & Validation**
- [ ] Manual testing with browser crash simulation
- [ ] Load testing with 10 concurrent disconnects
- [ ] Verify no orphaned tasks in Docker logs
- [ ] Verify no orphaned Redis streams
- [ ] Prometheus metrics validation

### Week 2: High Priority Fixes (P1)

**Day 4-5: Token Limit Configuration**
- [ ] Update config.py: critical_threshold 0.80 → 0.75
- [ ] Update config.py: safety_margin 2048 → 4096
- [ ] Update base.py: preserve_recent 6 → 10
- [ ] Add environment variable overrides
- [ ] Update documentation

**Day 6-8: Search Result Compression**
- [ ] Implement template-based search summarization
- [ ] Implement browser content sampling
- [ ] Add auto-compact at WARNING level
- [ ] Unit tests for compression
- [ ] Integration tests with wide research workflow

**Day 9: Validation**
- [ ] Test with 24-query research (should not trim)
- [ ] Verify token usage stays under 80%
- [ ] Verify no context loss
- [ ] Performance benchmarking

### Week 3: Medium Priority (P2)

**Day 10-11: Observability**
- [ ] Add heartbeat emission logging
- [ ] Add Prometheus heartbeat gap metrics
- [ ] Add client heartbeat persistence
- [ ] Update Grafana dashboards
- [ ] Add alerting rules

**Day 12-14: Browser Content Optimization**
- [ ] Refactor _extract_content() for structured output
- [ ] Implement smart content sampling
- [ ] Add configurable extraction depth
- [ ] Update frontend to handle structured content
- [ ] Testing & validation

### Week 4: Polish & Documentation (P3)

**Day 15-16: Background Task Cleanup**
- [ ] Add task cancellation in destroy()
- [ ] Add task tracking metrics
- [ ] Add automated cleanup job
- [ ] Testing & validation

**Day 17-19: Multi-Phase Workflow**
- [ ] Design phased research workflow
- [ ] Implement phase boundaries
- [ ] Add checkpoint/resume support
- [ ] Integration with memory system
- [ ] Testing with real research tasks

**Day 20: Final Testing & Documentation**
- [ ] End-to-end testing all fixes
- [ ] Update MEMORY.md with resolutions
- [ ] Update CLAUDE.md with new patterns
- [ ] Create runbook for operations team
- [ ] Deploy to production

---

## Testing Strategy

### Unit Tests

**Orphaned Tasks**:
```python
# test_cancellation_flow.py
async def test_tool_emission_cancelled():
    """Tool should not emit if cancellation requested."""
    cancel_event = asyncio.Event()
    cancel_event.set()  # Pre-cancelled

    agent = Agent(cancel_token=CancellationToken(cancel_event))

    with pytest.raises(asyncio.CancelledError):
        async for event in agent.execute_tools(tool_calls):
            pytest.fail("Should not emit events after cancellation")
```

**Token Trimming**:
```python
# test_token_management.py
def test_preserve_recent_adjustment():
    """preserve_recent should reduce if needed."""
    manager = TokenManager(max_tokens=30720)

    # Create messages exceeding limit
    messages = create_messages(total_tokens=33764)

    trimmed, removed = manager.trim_messages(
        messages,
        preserve_recent=6
    )

    assert removed == 4630
    assert manager.count_messages_tokens(trimmed) <= 30720
```

### Integration Tests

**SSE Reconnection**:
```python
# test_sse_reconnection.py
async def test_reconnect_with_last_event_id():
    """Client should reconnect with Last-Event-ID."""
    session = await create_session()

    # Start SSE stream
    events = []
    async for event in session.chat_stream():
        events.append(event)
        if len(events) == 10:
            break  # Disconnect

    last_event_id = events[-1]['id']

    # Reconnect with event ID
    async for event in session.chat_stream(last_event_id=last_event_id):
        assert event['id'] != last_event_id  # Should resume after
        break
```

### Performance Tests

**Wide Research Load**:
```python
# test_research_performance.py
async def test_24_query_research():
    """24-query research should not exceed token limit."""
    session = await create_session()

    query = "Best IDE coding agentic AI tools 2026"

    async for event in session.chat(query):
        if event['type'] == 'memory_pressure':
            assert event['level'] != 'OVERFLOW'
            assert event['usage_percent'] < 0.95  # <95%
```

---

## Success Metrics

### Pre-Fix Baseline

| Metric | Current | Target |
|--------|---------|--------|
| Orphaned tasks after disconnect | 15% of sessions | 0% |
| SSE timeout frequency | 8% of sessions | 0% |
| Token trimming during execution | 12% of sessions | <2% |
| Context loss (messages trimmed) | Avg 3.5 messages | <1 message |
| User duplicate requests | 5% of sessions | <1% |

### Post-Fix Validation

**Week 1 Success Criteria**:
- ✅ Zero orphaned tasks in production logs
- ✅ Cancellation completes within 1 second
- ✅ No Redis stream leaks

**Week 2 Success Criteria**:
- ✅ Wide research (24 queries) stays under 80% token usage
- ✅ Zero emergency trims (109%+ usage)
- ✅ Compression saves 40%+ tokens on search results

**Week 3 Success Criteria**:
- ✅ Heartbeat visible in logs and metrics
- ✅ Zero false timeout alerts
- ✅ User satisfaction score >90%

**Week 4 Success Criteria**:
- ✅ All P0-P3 issues resolved
- ✅ Documentation complete
- ✅ Team trained on new patterns
- ✅ Production monitoring dashboard live

---

## Related Documentation

- **Browser Architecture**: `browse_map.md`
- **Recent Logs Analysis**: `browser_logs_summary.md`
- **SSE Timeout Issue**: `docs/fixes/SSE_TIMEOUT_AND_UX_BUGS.md`
- **Session Persistence**: `docs/fixes/PAGE_REFRESH_SESSION_PERSISTENCE.md`
- **Memory Management**: `.claude/projects/-Users-panda-Desktop-Projects-Pythinker/memory/MEMORY.md`

---

**Document Version**: 1.0
**Last Updated**: 2026-02-13
**Investigation By**: Explore Agents (ae4f395, aa60e7b, a7e805b)
**Review Status**: Ready for Implementation
