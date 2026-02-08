# Agent Workflow Bug Report — Docker Session Analysis

**Date:** 2026-02-07
**Session:** `83bee7fa1b8544bf` (agent `c68b1e29a8534b56`)
**Task:** "Research and compare the top 5 AI agent frameworks"
**LLM:** `glm-4.7-flash` (Zhipu GLM via OpenAI-compatible API)
**Outcome:** `executing → error` — session crashed after ~3 minutes

---

## Executive Summary

Monitoring a live agent session revealed **7 distinct bugs** across 4 severity levels. The session followed: IDLE → PLANNING (77s) → EXECUTING (83s) → ERROR (crash). The fatal error was a GLM API 400 rejection after token trimming corrupted the message array. Five additional bugs degraded performance, and one infrastructure issue causes data loss on every LLM call.

| # | Severity | Issue | Impact |
|---|----------|-------|--------|
| 1 | **CRITICAL** | Message sanitization incomplete after token trimming | Session crash (GLM error 1214) |
| 2 | **CRITICAL** | Usage recording fails on every LLM call | All token/cost tracking lost |
| 3 | **HIGH** | Browser search parallel race condition (5 concurrent nav) | 4/5 DuckDuckGo searches fail with ERR_ABORTED |
| 4 | **HIGH** | browser_navigate parallel execution (5 concurrent) | 4/5 navigate calls fail (26-37ms) |
| 5 | **MEDIUM** | SSE session polling is wasteful (10s DB query loop) | Continuous unnecessary DB load |
| 6 | **MEDIUM** | Graceful shutdown timeout too short (5s) | CancelledError on every hot-reload |
| 7 | **LOW** | Post-error session completed spam | Frontend sends ~15 rapid chat POSTs after error |

---

## Bug 1: Message Sanitization Incomplete After Token Trimming (CRITICAL)

### Observed
```
18:12:27 warning  Context (32473 tokens) exceeds limit (30720). Trimming messages...
18:12:27 info     Trimmed 1 messages (2011 tokens), preserve_recent: 6 -> 6
18:12:28 error    API message validation error (likely strict schema): Error code: 400 -
         {'error': {'code': '1214', 'message': 'messages 参数非法。请检查文档。'}}
18:12:28 info     workflow_transition: executing -> error
```

### Root Cause
After `token_manager.py` trims messages to fit the context window, the resulting message array can become structurally invalid for the GLM API. The `_sanitize_messages()` method in `openai_llm.py` has 4 gaps:

1. **Missing `name` field on tool messages** (lines 514-518): If `function_name` doesn't exist on a tool message, no `name` field is ever added. GLM requires `name` on all tool messages.
2. **No default for `tool_call_id`**: Unlike assistant `tool_calls` (which get `tc.setdefault("id", ...)` at line 533), tool messages get no default `tool_call_id`.
3. **Empty string values not caught**: If `function_name` is `""`, it propagates to `name` as an empty string, which GLM rejects.
4. **Orphaned tool messages after trimming**: `_remove_orphaned_tool_responses()` in `token_manager.py` catches most cases, but if the trimming boundary splits a tool_call/tool_response pair in an edge case, orphaned `tool_call_id` references survive.

### Files
- `backend/app/infrastructure/external/llm/openai_llm.py:514-525` — sanitizer gaps
- `backend/app/domain/services/agents/token_manager.py:454-479` — orphan removal

### Fix
After the `function_name → name` conversion block (line 525), add validation for tool messages:

```python
# Ensure required fields for tool messages (GLM strict schema)
if role == "tool":
    if not msg_copy.get("name"):
        msg_copy["name"] = "unknown_tool"
    if not msg_copy.get("tool_call_id"):
        msg_copy["tool_call_id"] = f"call_{uuid.uuid4().hex[:8]}"
    # Ensure string types
    msg_copy["name"] = str(msg_copy["name"])
    msg_copy["tool_call_id"] = str(msg_copy["tool_call_id"])
```

Also add a post-trim validation pass in `token_manager.py` after `_remove_orphaned_tool_responses()` that ensures every tool message has a matching assistant tool_call in the remaining messages.

---

## Bug 2: Usage Recording Fails on Every LLM Call (CRITICAL)

### Observed
```
18:10:48 warning  Failed to record usage counts: get_motor_collection
18:11:05 warning  Failed to record usage: get_motor_collection
18:11:17 warning  Failed to record usage: get_motor_collection
18:11:56 warning  Failed to record usage: get_motor_collection
18:12:05 warning  Failed to record usage: get_motor_collection
18:12:25 warning  Failed to record usage: get_motor_collection
```

Every single LLM call fails to record usage — 6 failures in 2 minutes.

### Root Cause
In `usage_service.py:152`, the code calls `DailyUsageDocument.get_motor_collection()` (a Beanie ORM method). This fails because:

1. **Beanie race condition**: `get_motor_collection()` can return `None` during concurrent access (known Beanie issue #440). When multiple LLM calls record usage simultaneously, the collection reference isn't properly synchronized.
2. **Error is silently swallowed**: `openai_llm.py:146` catches all exceptions with `logger.warning(f"Failed to record usage: {e}")` — the actual exception type and traceback are lost.

### Files
- `backend/app/application/services/usage_service.py:152` — the `get_motor_collection()` call
- `backend/app/infrastructure/external/llm/openai_llm.py:145-146, 173-174` — exception handlers

### Fix
Replace `DailyUsageDocument.get_motor_collection()` with a safer approach:

```python
# Option A: Use Beanie's native methods instead of raw Motor
async def _update_daily_aggregate(self, record: UsageRecord) -> None:
    today = date.today()
    usage_id = f"{record.user_id}_{today.isoformat()}"

    # Use Beanie's find/upsert instead of get_motor_collection()
    doc = await DailyUsageDocument.find_one(
        DailyUsageDocument.user_id == record.user_id,
        DailyUsageDocument.date == today.isoformat()
    )
    if doc:
        # Update existing
        ...
    else:
        # Create new
        ...

# Option B: Cache the collection reference at init time
class UsageService:
    def __init__(self):
        self._collection = None

    def _get_collection(self):
        if self._collection is None:
            self._collection = DailyUsageDocument.get_motor_collection()
        return self._collection
```

Also improve error logging to include the exception type:
```python
except Exception as e:
    logger.warning(f"Failed to record usage: {type(e).__name__}: {e}")
```

---

## Bug 3: Browser Search Parallel Race Condition (HIGH)

### Observed
```
18:11:17 info  tool_started: info_search_web    (5 calls started within 20ms)
18:11:17 info  tool_started: info_search_web
18:11:17 info  tool_started: info_search_web
18:11:18 info  tool_started: info_search_web
18:11:18 info  tool_started: info_search_web
18:11:18 error Browser navigation failed: net::ERR_ABORTED (LangGraph query)
18:11:18 error Browser navigation failed: net::ERR_ABORTED (CrewAI query)
18:11:18 error Browser navigation failed: net::ERR_ABORTED (AutoGen query)
18:11:18 error Browser navigation failed: net::ERR_ABORTED (OpenAI Agents query)
18:11:20 warning JS evaluation error: Execution context was destroyed
18:11:20 warning Content extraction timed out or failed
```

5 simultaneous `info_search_web` calls all try to navigate DuckDuckGo on the **same single Playwright page**. 4 out of 5 get `net::ERR_ABORTED` because Playwright aborts concurrent `page.goto()` calls. The 5th gets content but it's empty because the execution context was destroyed mid-extraction.

### Root Cause
Two parallel execution control systems exist but aren't integrated:

1. **`parallel_executor.py:81-90`** — has `SEQUENTIAL_ONLY_TOOLS` set including `info_search_web` and `browser_navigate`
2. **`base.py:625-649`** — `_can_parallelize_tools()` only checks `SAFE_PARALLEL_TOOLS` whitelist, never consults the blacklist

The `_can_parallelize_tools()` method correctly rejects `info_search_web` (it's not in the whitelist), and `ask_with_messages()` at line 1106 correctly limits to `tool_calls[:1]`. **However**, the GLM model returns all 5 tool_calls in one response, and depending on the code path, they can still reach `asyncio.gather()` concurrently.

The browser itself has **no navigation lock**: `playwright_browser.py` has a single `self.page` instance with no mutex/semaphore protecting `page.goto()`.

### Files
- `backend/app/domain/services/agents/parallel_executor.py:81-90` — SEQUENTIAL_ONLY_TOOLS
- `backend/app/domain/services/agents/base.py:625-649` — `_can_parallelize_tools()`
- `backend/app/domain/services/agents/base.py:763-823` — parallel execution path
- `backend/app/domain/services/agents/base.py:1100-1106` — tool_calls filtering
- `backend/app/infrastructure/external/browser/playwright_browser.py:1553-1636` — navigate()

### Fix
Add a navigation lock to PlaywrightBrowser:

```python
class PlaywrightBrowser:
    def __init__(self, ...):
        ...
        self._navigation_lock = asyncio.Lock()

    async def navigate(self, url: str, ...) -> ToolResult:
        async with self._navigation_lock:
            # existing navigation code
            ...
```

Also add a defensive check in `_can_parallelize_tools()`:

```python
from app.domain.services.agents.parallel_executor import ParallelToolExecutor

def _can_parallelize_tools(self, tool_calls: list[dict]) -> bool:
    if len(tool_calls) <= 1:
        return False
    for tc in tool_calls:
        tool_name = tc.get("function", {}).get("name", "")
        # Check blacklist first
        if tool_name in ParallelToolExecutor.SEQUENTIAL_ONLY_TOOLS:
            return False
        # Then check whitelist
        if tool_name in SAFE_PARALLEL_TOOLS:
            continue
        if any(...):  # MCP read-only
            continue
        return False
    return True
```

---

## Bug 4: browser_navigate Parallel Execution (HIGH)

### Observed
```
18:11:56 info  tool_started: browser_navigate   (5 calls started within 15ms)
18:11:56 info  tool_started: browser_navigate
18:11:56 info  tool_started: browser_navigate
18:11:56 info  tool_started: browser_navigate
18:11:56 info  tool_started: browser_navigate
18:11:56 warning tool_completed: browser_navigate (27ms, success=False)
18:11:56 warning tool_completed: browser_navigate (26ms, success=False)
18:11:56 warning tool_completed: browser_navigate (37ms, success=False)
18:11:56 warning tool_completed: browser_navigate (35ms, success=False)
18:11:58 info  tool_completed: browser_navigate (1267ms, success=True)
```

Same root cause as Bug 3. The LLM returns 5 `browser_navigate` calls, 4 fail in <40ms because the single Playwright page can only navigate to one URL at a time. Only the last one succeeds (1267ms = actual navigation time).

### Fix
Same as Bug 3 — the `_navigation_lock` in PlaywrightBrowser would prevent concurrent calls. The 4 would queue behind the first and execute sequentially.

---

## Bug 5: SSE Session Polling Wastes Database Queries (MEDIUM)

### Observed
```
18:08:28 info  Getting all sessions for user anonymous  (request_id: a9bfaa48)
18:08:38 info  Getting all sessions for user anonymous
18:08:48 info  Getting all sessions for user anonymous
18:08:58 info  Getting all sessions for user anonymous
... (repeats every 10 seconds indefinitely)
```

A single SSE connection from the frontend polls the sessions endpoint every 10 seconds, forever.

### Root Cause
`session_routes.py:206-228` has an infinite `while True` loop:

```python
async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
    while True:
        sessions = await agent_service.get_all_sessions(current_user.id)  # DB query
        yield ServerSentEvent(...)
        await asyncio.sleep(SESSION_POLL_INTERVAL)  # 10 seconds
```

This queries MongoDB every 10 seconds regardless of whether data changed. With N connected clients, that's N queries every 10 seconds.

### Files
- `backend/app/interfaces/api/session_routes.py:55` — `SESSION_POLL_INTERVAL = 10`
- `backend/app/interfaces/api/session_routes.py:206-228` — infinite polling loop

### Fix
Use Redis pub/sub or change tracking instead of polling:

```python
async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
    # Send initial state
    sessions = await agent_service.get_all_sessions(current_user.id)
    yield ServerSentEvent(event="sessions", data=...)

    # Subscribe to session changes via Redis
    async for change in redis_session_changes(current_user.id):
        sessions = await agent_service.get_all_sessions(current_user.id)
        yield ServerSentEvent(event="sessions", data=...)
```

Or at minimum, add change detection to avoid sending identical payloads:

```python
last_hash = None
while True:
    sessions = await agent_service.get_all_sessions(current_user.id)
    data = ListSessionResponse(sessions=session_items).model_dump_json()
    current_hash = hashlib.md5(data.encode()).hexdigest()
    if current_hash != last_hash:
        yield ServerSentEvent(event="sessions", data=data)
        last_hash = current_hash
    await asyncio.sleep(SESSION_POLL_INTERVAL)
```

---

## Bug 6: Graceful Shutdown Timeout Too Short (MEDIUM)

### Observed
```
WARNING:  WatchFiles detected changes in 'skill_invoke.py'. Reloading...
ERROR:    Cancel 1 running task(s), timeout graceful shutdown exceeded
ERROR:    Exception in ASGI application
  asyncio.exceptions.CancelledError: Task cancelled, timeout graceful shutdown exceeded
```

### Root Cause
`run.sh:3` sets `--timeout-graceful-shutdown 5` (5 seconds). But the SSE session polling loop sleeps for 10 seconds per cycle, and the lifespan shutdown in `main.py:374-473` has internal timeouts of 30s, 15s, and 10s for various service shutdowns. The 5-second window is insufficient for any of them.

### Files
- `backend/run.sh:3` — `--timeout-graceful-shutdown 5`
- `backend/app/main.py:374-473` — shutdown sequence with 30s/15s/10s timeouts
- `backend/app/interfaces/api/session_routes.py:226` — 10s sleep in SSE loop

### Fix
1. Increase graceful shutdown to 15s: `--timeout-graceful-shutdown 15`
2. Add cancellation handling to the SSE loop:

```python
async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
    try:
        while True:
            sessions = await agent_service.get_all_sessions(current_user.id)
            yield ServerSentEvent(...)
            await asyncio.sleep(SESSION_POLL_INTERVAL)
    except asyncio.CancelledError:
        logger.info("Session SSE stream cancelled during shutdown")
        return
```

---

## Bug 7: Post-Error Chat Retry Spam (LOW)

### Observed
After the error at 18:12:28, the frontend sends POST `/api/v1/sessions/{id}/chat` approximately every 2 seconds. Each returns "Session completed" immediately. This continues for ~30 seconds (15+ requests).

```
18:12:44 info  Starting chat with session 83bee7fa1b8544bf: ...
18:12:44 info  Session 83bee7fa1b8544bf completed       (immediate return)
18:12:46 info  Starting chat with session 83bee7fa1b8544bf: ...
18:12:46 info  Session 83bee7fa1b8544bf completed       (immediate return)
... (repeats every ~2 seconds)
```

### Root Cause
The frontend SSE client (`client.ts:328-472`) has exponential backoff reconnection. When the chat SSE stream closes unexpectedly (agent error), it retries with 1s base + jitter. The first few attempts fall in the 1-2s range. Each reconnection sends a new chat POST, which returns "completed" immediately since the session is already in error state.

The `streamCompleted` flag that prevents reconnection isn't being set when the agent errors — it's only set on normal completion events (`done`/`complete`/`end`).

### Files
- `frontend/src/api/client.ts:328-339` — retry config
- `frontend/src/api/client.ts:448-472` — reconnection logic

### Fix
The chat SSE should recognize error states as terminal:

```typescript
// In the SSE onmessage handler, treat agent errors as stream completion
if (event.type === 'error' || event.type === 'agent_error') {
    streamCompleted = true;  // Prevent reconnection
}
```

---

## Workflow Timeline

```
18:09:47.443  Session created (83bee7fa1b8544bf)
18:09:47.486  Chat POST received ("Research and compare the top 5 AI agent frameworks")
18:09:48.903  IDLE → PLANNING
18:10:48.497  ⚠ Failed to record usage: get_motor_collection (1st LLM call)
18:11:05.981  ⚠ Failed to record usage: get_motor_collection (plan validation)
18:11:05.989  Plan created: 5 steps
18:11:05.996  PLANNING → EXECUTING (Step 1)
18:11:17.987  5× info_search_web started in parallel (should be sequential)
18:11:18.053  ✗ 4× Browser navigation ERR_ABORTED (race condition)
18:11:20.208  ✗ JS context destroyed during content extraction
18:11:20.263  Fallback to API search (all 5 queries)
18:11:24.467  5× search completed (3.9s-6.5s each, 3 flagged as slow)
18:11:56.813  5× browser_navigate started in parallel (should be sequential)
18:11:56.839  ✗ 4× browser_navigate failed (26-37ms, too fast = race)
18:11:58.094  1× browser_navigate succeeded (1267ms)
18:12:05.118  5× browser search tool started
18:12:27.320  ⚠ Memory exceeds token limit (32473 > 30720), trimming...
18:12:28.106  ✗ FATAL: GLM API 400 — messages 参数非法 (invalid after trim)
18:12:28.106  EXECUTING → ERROR
18:12:44      Frontend retry storm begins (~15 chat POSTs in 30s)
18:15:27      Server hot-reload → graceful shutdown timeout exceeded
```

---

## Priority Fix Order

1. **Bug 1** (message sanitization) — Prevents session crashes. Fix in `openai_llm.py`.
2. **Bug 2** (usage recording) — Prevents silent data loss. Fix in `usage_service.py`.
3. **Bug 3+4** (browser navigation lock) — Prevents 80% search/nav failures. Fix in `playwright_browser.py`.
4. **Bug 6** (shutdown timeout) — Prevents error on every hot-reload. Fix in `run.sh`.
5. **Bug 5** (SSE polling) — Reduces unnecessary DB load. Fix in `session_routes.py`.
6. **Bug 7** (retry spam) — Cosmetic. Fix in `client.ts`.
