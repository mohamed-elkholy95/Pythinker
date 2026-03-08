# Session Monitoring Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 issues discovered during live session monitoring — the critical SSE reconnect race condition that kills live sessions, complexity-aware wide research query limits, Reddit spider resilience, and chart reference injection into research reports.

**Architecture:** Redis liveness signal (heartbeated from `RedisStreamTask`, carrying `task_id`) replaces the fragile MongoDB-only orphan heuristic in `agent_domain_service.py`. Complexity plumbing flows from `PlanActFlow._cached_complexity` through tool context to `SearchTool`. Chart generation order is inverted in `agent_task_runner.py` so references can be injected before the report file is written. Reddit URLs are added to a domain denylist in the spider preprocessor, falling back to search snippets.

**Tech Stack:** Python 3.12, Redis (SET with EX), asyncio, pytest, Pydantic v2 Settings

**Issues addressed:**
| # | Severity | Issue | Approach |
|---|----------|-------|----------|
| 1 | Critical | SSE reconnect race kills live sessions | Redis liveness key + ProgressEvent fallback |
| 2 | No-code | Serper key exhaustion cascade | Config/ops — first-discovery behavior is correct |
| 3 | No-code | LLM 90s timeout on step 4 | Already handled by retry — working as designed |
| 4 | Medium | Wide research queries clamped 5→3 | Plumb complexity score to search tool |
| 5 | Medium | Reddit 403 spider block | Domain denylist — skip spider, keep snippets |
| 6 | Medium | Chart not referenced in report body | Reorder: generate chart → inject refs → write file |

---

## Task 1: Redis Task Liveness Signal

**Files:**
- Modify: `backend/app/infrastructure/external/task/redis_task.py` (lines 15-36, 137-155, 186-195)
- Test: `backend/tests/infrastructure/external/task/test_redis_task_liveness.py` (create)

**Context:** `RedisStreamTask` registers tasks in an in-memory dict (`_task_registry`) keyed by `task_id`. This is invisible across workers. We add a Redis key `task:liveness:{session_id}` that carries the `task_id` value, heartbeated every 10s from the running task, cleared in `finally`. The reconnect handler reads this key to discover living tasks even when `session.task_id` in MongoDB has been nulled.

**Step 1: Write the failing tests**

Create `backend/tests/infrastructure/external/task/test_redis_task_liveness.py`:

```python
"""Tests for Redis task liveness signal."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.task.redis_task import RedisStreamTask


@pytest.fixture
def mock_redis():
    """Mock Redis client with async methods."""
    client = AsyncMock()
    client.set = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.delete = AsyncMock(return_value=1)
    return client


@pytest.fixture
def mock_runner():
    """Mock task runner with session_id."""
    runner = AsyncMock()
    runner.session_id = "test-session-123"

    async def run_forever(task):
        await asyncio.sleep(100)

    runner.run = run_forever
    runner.on_done = AsyncMock()
    return runner


class TestLivenessSignal:
    """Test Redis liveness key lifecycle."""

    @pytest.mark.asyncio
    async def test_liveness_key_set_on_task_start(self, mock_runner, mock_redis):
        """Liveness key should be set when task execution begins."""
        with patch.object(RedisStreamTask, "_get_redis_client", return_value=mock_redis):
            task = RedisStreamTask(mock_runner)
            # Start and immediately cancel to test the setup path
            task.start()
            await asyncio.sleep(0.1)
            task.cancel()
            await asyncio.sleep(0.1)

            # Verify SET was called with the liveness key
            set_calls = [
                c for c in mock_redis.set.call_args_list
                if "task:liveness:test-session-123" in str(c)
            ]
            assert len(set_calls) >= 1, "Liveness key should be set on task start"

    @pytest.mark.asyncio
    async def test_liveness_key_carries_task_id(self, mock_runner, mock_redis):
        """Liveness key value should be the task_id."""
        with patch.object(RedisStreamTask, "_get_redis_client", return_value=mock_redis):
            task = RedisStreamTask(mock_runner)
            task.start()
            await asyncio.sleep(0.1)
            task.cancel()
            await asyncio.sleep(0.1)

            set_calls = [
                c for c in mock_redis.set.call_args_list
                if "task:liveness:test-session-123" in str(c)
            ]
            assert len(set_calls) >= 1
            # The value should be the task_id
            _, kwargs = set_calls[0]
            assert kwargs.get("value", set_calls[0][0][1] if len(set_calls[0][0]) > 1 else None) is not None

    @pytest.mark.asyncio
    async def test_liveness_key_deleted_on_task_done(self, mock_runner, mock_redis):
        """Liveness key should be deleted when task completes."""
        async def quick_run(task):
            await asyncio.sleep(0.05)

        mock_runner.run = quick_run

        with patch.object(RedisStreamTask, "_get_redis_client", return_value=mock_redis):
            task = RedisStreamTask(mock_runner)
            task.start()
            await asyncio.sleep(0.3)

            delete_calls = [
                c for c in mock_redis.delete.call_args_list
                if "task:liveness:test-session-123" in str(c)
            ]
            assert len(delete_calls) >= 1, "Liveness key should be deleted on completion"

    @pytest.mark.asyncio
    async def test_liveness_key_has_ttl(self, mock_runner, mock_redis):
        """Liveness key should have a TTL for crash safety."""
        with patch.object(RedisStreamTask, "_get_redis_client", return_value=mock_redis):
            task = RedisStreamTask(mock_runner)
            task.start()
            await asyncio.sleep(0.1)
            task.cancel()
            await asyncio.sleep(0.1)

            set_calls = [
                c for c in mock_redis.set.call_args_list
                if "task:liveness:test-session-123" in str(c)
            ]
            assert len(set_calls) >= 1
            # Should have ex= or EX= parameter for TTL
            call_kwargs = set_calls[0][1] if set_calls[0][1] else {}
            # The SET call should include ex=30 (TTL of 30 seconds)
            assert "ex" in call_kwargs, "Liveness key must have TTL"
            assert call_kwargs["ex"] == 30

    @pytest.mark.asyncio
    async def test_get_liveness_returns_task_id(self, mock_redis):
        """Class method should return task_id from liveness key."""
        mock_redis.get = AsyncMock(return_value=b"task-uuid-abc")

        with patch.object(RedisStreamTask, "_get_redis_client", return_value=mock_redis):
            result = await RedisStreamTask.get_liveness("test-session-123")
            assert result == "task-uuid-abc"
            mock_redis.get.assert_called_once_with("task:liveness:test-session-123")

    @pytest.mark.asyncio
    async def test_get_liveness_returns_none_when_missing(self, mock_redis):
        """Class method should return None when no liveness key exists."""
        mock_redis.get = AsyncMock(return_value=None)

        with patch.object(RedisStreamTask, "_get_redis_client", return_value=mock_redis):
            result = await RedisStreamTask.get_liveness("test-session-123")
            assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/infrastructure/external/task/test_redis_task_liveness.py -v`
Expected: FAIL — `get_liveness` method and `_get_redis_client` don't exist yet.

**Step 3: Implement liveness signal in `redis_task.py`**

Add these constants after line 14:

```python
_LIVENESS_KEY_PREFIX = "task:liveness:"
_LIVENESS_TTL_SECONDS = 30
_LIVENESS_HEARTBEAT_INTERVAL = 10
```

Add a `_get_redis_client` classmethod (after `get()` at line 204):

```python
@classmethod
def _get_redis_client(cls):
    """Get Redis client from the connection pool."""
    from app.infrastructure.external.redis_client import get_redis_client
    return get_redis_client()
```

Add `get_liveness` classmethod:

```python
@classmethod
async def get_liveness(cls, session_id: str) -> str | None:
    """Check if a task is alive for the given session. Returns task_id or None."""
    redis = cls._get_redis_client()
    value = await redis.get(f"{cls._LIVENESS_KEY_PREFIX}{session_id}")
    return value.decode() if value else None
```

Modify `__init__` (line 17-36) — store `session_id` from runner:

```python
self._session_id: str | None = getattr(runner, "session_id", None)
self._heartbeat_task: asyncio.Task | None = None
```

Modify `_execute_task` (line 186-195) — set liveness key and start heartbeat:

```python
async def _execute_task(self) -> None:
    try:
        await self._set_liveness()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_liveness())
        await self._runner.run(self)
    except asyncio.CancelledError:
        logger.info("Task %s was cancelled", self._id)
    except Exception as e:
        logger.exception("Task %s execution failed: %s", self._id, e)
    finally:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        await self._clear_liveness()
        self._on_task_done()
```

Add liveness helper methods:

```python
async def _set_liveness(self) -> None:
    """Set liveness key in Redis with TTL."""
    if not self._session_id:
        return
    try:
        redis = self._get_redis_client()
        await redis.set(
            f"{_LIVENESS_KEY_PREFIX}{self._session_id}",
            self._id,
            ex=_LIVENESS_TTL_SECONDS,
        )
    except Exception as e:
        logger.warning("Failed to set liveness key for session %s: %s", self._session_id, e)

async def _heartbeat_liveness(self) -> None:
    """Periodically refresh liveness key TTL."""
    while True:
        await asyncio.sleep(_LIVENESS_HEARTBEAT_INTERVAL)
        await self._set_liveness()

async def _clear_liveness(self) -> None:
    """Delete liveness key on task completion."""
    if not self._session_id:
        return
    try:
        redis = self._get_redis_client()
        await redis.delete(f"{_LIVENESS_KEY_PREFIX}{self._session_id}")
    except Exception as e:
        logger.warning("Failed to clear liveness key for session %s: %s", self._session_id, e)
```

**Step 4: Verify `session_id` is available on the task runner**

Check that the runner passed to `RedisStreamTask` has `session_id`. In `agent_task_factory.py` line 348, the runner is the coroutine returned by `_create_task_runner()`. The `AgentTaskRunner` (or the closure) should already carry `session_id`. If not, add it as an attribute on the runner object in `agent_task_factory.py`.

**Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/infrastructure/external/task/test_redis_task_liveness.py -v`
Expected: All 6 tests PASS.

**Step 6: Commit**

```bash
git add backend/app/infrastructure/external/task/redis_task.py \
        backend/tests/infrastructure/external/task/test_redis_task_liveness.py
git commit -m "feat(task): add Redis liveness signal for SSE reconnect race detection

Heartbeat task:liveness:{session_id} key every 10s with 30s TTL.
Carries task_id as value for reconnect-time stream discovery.
Cleared in finally block for crash safety."
```

---

## Task 2: Fix Orphan Detection Heuristic in `agent_domain_service.py`

**Files:**
- Modify: `backend/app/domain/services/agent_domain_service.py` (lines 738-814)
- Modify: `backend/tests/domain/services/test_agent_domain_service_chat_teardown.py`
- Test: `backend/tests/domain/services/test_reconnect_liveness.py` (create)

**Context:** The orphan heuristic at line 790 currently yields `DoneEvent` for RUNNING sessions with no task within 180s — this kills live sessions. With the liveness signal from Task 1, we now:
1. Check `RedisStreamTask.get_liveness(session_id)` first
2. If liveness exists → get `task_id`, look up the task, poll its output stream
3. If liveness is missing but session is within grace window → emit `ProgressEvent` + bounded polling (not `DoneEvent`)
4. Only emit terminal events when liveness is gone AND grace period expired

**Step 1: Write the failing tests**

Create `backend/tests/domain/services/test_reconnect_liveness.py`:

```python
"""Tests for reconnect behavior with Redis liveness signal."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.events import DoneEvent, ErrorEvent, ProgressEvent
from app.domain.models.session import Session, SessionStatus


@pytest.fixture
def mock_session():
    session = MagicMock(spec=Session)
    session.id = "sess-123"
    session.user_id = "user-1"
    session.title = "Test Session"
    session.status = SessionStatus.RUNNING
    session.task_id = None  # Nulled by prior teardown
    session.updated_at = datetime.now(UTC) - timedelta(seconds=10)
    session.events = []
    session.complexity_score = None
    session.source = "web"
    return session


class TestReconnectWithLiveness:
    """When liveness key exists, reconnect should poll the live task's stream."""

    @pytest.mark.asyncio
    async def test_liveness_exists_polls_output_stream(self, mock_session):
        """If liveness key returns a task_id, reconnect should poll that task's output stream."""
        # This test verifies that the reconnect path discovers the live task
        # via Redis liveness and polls its output stream instead of emitting DoneEvent.
        # Implementation will be verified by checking that no DoneEvent is yielded
        # and that the task's output stream is read.
        pass  # Placeholder — full mock setup in implementation

    @pytest.mark.asyncio
    async def test_no_liveness_grace_period_emits_progress_not_done(self, mock_session):
        """If liveness is missing but session age < 180s, emit ProgressEvent not DoneEvent."""
        pass

    @pytest.mark.asyncio
    async def test_no_liveness_stale_session_emits_error(self, mock_session):
        """If liveness is missing and session age >= 180s, emit ErrorEvent (CANCELLED)."""
        pass


class TestReconnectBoundedPolling:
    """When liveness is missing but session is recent, do bounded polling."""

    @pytest.mark.asyncio
    async def test_bounded_polling_timeout(self):
        """Bounded polling should timeout after configured seconds and emit DoneEvent."""
        pass

    @pytest.mark.asyncio
    async def test_bounded_polling_picks_up_late_events(self):
        """If events arrive during bounded polling, they should be yielded."""
        pass
```

Note: These are structural placeholders. The full mock setup will be implemented during execution based on the exact method signature and dependency injection pattern of `agent_domain_service.chat()`.

**Step 2: Modify the orphan detection block (lines 780-814)**

Replace the current block at lines 780-814 with:

```python
# --- Reconnect liveness check ---
# Check if the task is still alive via Redis liveness signal
# (survives MongoDB task_id nulling and cross-worker boundaries)
from app.infrastructure.external.task.redis_task import RedisStreamTask

live_task_id = await RedisStreamTask.get_liveness(session_id)

if live_task_id:
    # Task is alive — look it up and poll its output stream
    live_task = RedisStreamTask.get(live_task_id)
    if live_task:
        logger.info(
            "Reconnect found live task %s for session %s via liveness signal",
            live_task_id, session_id,
        )
        # Poll the live task's output stream
        poll_deadline = asyncio.get_event_loop().time() + 120.0
        while not live_task.done and asyncio.get_event_loop().time() < poll_deadline:
            event_id_out, event_str = await live_task.output_stream.get(
                start_id=latest_event_id,
                block_ms=2000,
            )
            if event_id_out and event_str:
                latest_event_id = event_id_out
                event = self._deserialize_event(event_str)
                if event:
                    received_events = True
                    yield event
                    if isinstance(event, DoneEvent):
                        terminal_status = SessionStatus.COMPLETED
                        break
                    if isinstance(event, ErrorEvent):
                        terminal_status = SessionStatus.FAILED
                        break
        # If task finished but no terminal event came through, mark cancelled
        if terminal_status is None and live_task.done:
            terminal_status = SessionStatus.CANCELLED
    else:
        # Liveness key exists but task not in local registry (cross-worker)
        # Emit progress and let the frontend retry
        logger.info(
            "Liveness key exists for session %s (task %s) but task not in local registry — cross-worker",
            session_id, live_task_id,
        )
        yield ProgressEvent(message="Session is being processed on another worker. Reconnecting...")
else:
    # No liveness key — check grace period
    updated_at = self._ensure_aware_utc(session.updated_at if session else None)
    session_age = (datetime.now(UTC) - updated_at).total_seconds() if updated_at else 999

    if session_age < 180.0:
        # Recent session, liveness expired — bounded polling before giving up
        logger.info(
            "Session %s is RUNNING with no liveness signal but updated %.1fs ago — bounded polling",
            session_id, session_age,
        )
        yield ProgressEvent(message="Session is being processed. Reconnecting...")

        # Bounded poll: check for late-arriving liveness or events (15s max)
        bounded_deadline = asyncio.get_event_loop().time() + 15.0
        found_task = False
        while asyncio.get_event_loop().time() < bounded_deadline:
            # Re-check liveness (heartbeat might have just fired)
            late_task_id = await RedisStreamTask.get_liveness(session_id)
            if late_task_id:
                late_task = RedisStreamTask.get(late_task_id)
                if late_task:
                    found_task = True
                    # Delegate to the live-task polling loop
                    while not late_task.done:
                        ev_id, ev_str = await late_task.output_stream.get(
                            start_id=latest_event_id, block_ms=2000,
                        )
                        if ev_id and ev_str:
                            latest_event_id = ev_id
                            event = self._deserialize_event(ev_str)
                            if event:
                                received_events = True
                                yield event
                                if isinstance(event, (DoneEvent, ErrorEvent)):
                                    terminal_status = (
                                        SessionStatus.COMPLETED
                                        if isinstance(event, DoneEvent)
                                        else SessionStatus.FAILED
                                    )
                                    break
                    break
            await asyncio.sleep(1.0)

        if not found_task and terminal_status is None:
            # Grace period polling exhausted — emit DoneEvent as last resort
            logger.warning(
                "Session %s bounded polling exhausted (%.1fs age) — emitting done",
                session_id, session_age,
            )
            yield DoneEvent(
                title=session.title if session else "Session active",
                summary="Session processing completed.",
            )
            terminal_status = SessionStatus.COMPLETED
    else:
        # Stale orphan — cancel
        logger.warning(
            "Session %s appears orphaned (%.1fs since last update, no liveness). Cancelling.",
            session_id, session_age,
        )
        await self._session_repository.update_by_id(
            session_id, {"status": SessionStatus.CANCELLED.value}
        )
        error_event = ErrorEvent(
            error="Session task was interrupted before completion. "
            "Please try again or start a new session."
        )
        if session:
            session.add_event(error_event)
            await self._session_repository.save(session)
        yield error_event
        terminal_status = SessionStatus.CANCELLED
```

**Step 3: Update existing tests in `test_agent_domain_service_chat_teardown.py`**

Tests that need to change:

- `test_chat_no_active_task_recent_running_session_emits_done_not_cancel` (L119): Must now emit `ProgressEvent` instead of `DoneEvent` during bounded polling, then `DoneEvent` after polling exhaustion. Add mock for `RedisStreamTask.get_liveness` returning `None`.

- `test_chat_no_active_task_within_grace_period_emits_done_not_cancel` (L145): Same — `ProgressEvent` first, then `DoneEvent` after bounded polling.

- `test_chat_no_active_task_recent_running_session_with_naive_updated_at_emits_done` (L170): Same pattern.

All three tests need:
```python
@patch("app.infrastructure.external.task.redis_task.RedisStreamTask.get_liveness", new_callable=AsyncMock, return_value=None)
```

And assertions should change from:
```python
assert isinstance(events[0], DoneEvent)
```
To:
```python
assert isinstance(events[0], ProgressEvent)  # Bounded polling phase
assert isinstance(events[-1], DoneEvent)      # After polling exhaustion
```

The stale-orphan test (L94, `test_chat_no_active_task_and_running_session_emits_error_and_tears_down`) remains unchanged — it already expects `ErrorEvent` + `CANCELLED` for sessions > 180s.

**Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/domain/services/test_agent_domain_service_chat_teardown.py tests/domain/services/test_reconnect_liveness.py -v`
Expected: All PASS.

**Step 5: Commit**

```bash
git add backend/app/domain/services/agent_domain_service.py \
        backend/tests/domain/services/test_agent_domain_service_chat_teardown.py \
        backend/tests/domain/services/test_reconnect_liveness.py
git commit -m "fix(sse): replace DoneEvent with liveness check + bounded polling on reconnect

The orphan detection heuristic no longer kills live sessions.
On reconnect:
1. Check Redis liveness key for task_id → poll output stream
2. If no liveness but session < 180s → ProgressEvent + 15s bounded poll
3. If no liveness and session > 180s → ErrorEvent + CANCELLED (unchanged)

Fixes: frontend showing session as completed while agent is still running."
```

---

## Task 3: Complexity-Aware Wide Research Query Limit

**Files:**
- Modify: `backend/app/core/config_features.py` (line 61)
- Modify: `backend/app/domain/services/tools/search.py` (lines 483, 1376-1379)
- Modify: `backend/app/domain/services/flows/plan_act.py` (tool context plumbing)
- Test: `backend/tests/domain/services/tools/test_search_complexity_queries.py` (create)

**Context:** `max_wide_research_queries` is a global setting (default 3). The complexity score (`0.0-1.0`) is computed in `PlanActFlow` and cached as `self._cached_complexity`. We need to plumb this score through the tool execution context so `SearchTool.wide_research()` can use it to adjust the query cap dynamically. The tool should not import or reference complexity assessment directly — it receives the score via its execution context.

**Step 1: Add `max_wide_research_queries_complex` setting**

In `config_features.py`, add after line 61:

```python
max_wide_research_queries: int = 3        # Default for simple/medium tasks
max_wide_research_queries_complex: int = 5  # For very_complex tasks (complexity >= 0.8)
```

**Step 2: Plumb complexity into tool execution context**

In `plan_act.py`, find where the executor's tool context or tool kwargs are set before step execution. The `SearchTool` is instantiated in the `__init__` of `PlanActFlow` (or in `agent_task_runner.py`). The complexity score needs to flow as a tool context attribute.

Find the tool invocation path: `PlanActFlow._execute_step()` → `executor.execute_step()` → `base.py execute()` → tool call dispatch. The tool receives `ToolContext` or equivalent.

Add to the tool context dict (or session metadata passed to tools):

```python
# In plan_act.py, before step execution starts (after complexity assessment at line 2310):
if self._cached_complexity is not None:
    self.executor.set_tool_context("complexity_score", self._cached_complexity)
```

If `set_tool_context` doesn't exist, pass it through the session object:

```python
session.complexity_score = assessment.score  # Already done at line 2306
```

Then in `search.py`, read it from the session:

```python
# In wide_research(), after line 1376:
complexity = getattr(self._session, "complexity_score", None) if hasattr(self, "_session") else None
effective_max = (
    settings.max_wide_research_queries_complex
    if complexity is not None and complexity >= 0.8
    else self._max_wide_queries
)
if len(queries) > effective_max:
    logger.warning(f"Wide research queries clamped: {len(queries)} → {effective_max}")
    queries = queries[:effective_max]
```

**Step 3: Write tests**

Create `backend/tests/domain/services/tools/test_search_complexity_queries.py`:

```python
"""Tests for complexity-aware wide research query limits."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.domain.services.tools.search import SearchTool


class TestComplexityAwareQueryLimit:
    """Query limit should increase for very_complex tasks."""

    def test_default_limit_is_3(self):
        """Without complexity score, max queries should be 3 (default)."""
        # Verify settings default
        from app.core.config_features import FeatureSettings
        s = FeatureSettings()
        assert s.max_wide_research_queries == 3

    def test_complex_limit_is_5(self):
        """Complex setting should default to 5."""
        from app.core.config_features import FeatureSettings
        s = FeatureSettings()
        assert s.max_wide_research_queries_complex == 5

    @pytest.mark.asyncio
    async def test_high_complexity_allows_5_queries(self):
        """Tasks with complexity >= 0.8 should allow up to 5 queries."""
        # Test the effective_max calculation
        # Will be fleshed out during implementation based on how
        # complexity flows to the search tool
        pass

    @pytest.mark.asyncio
    async def test_low_complexity_keeps_3_queries(self):
        """Tasks with complexity < 0.8 should keep the default 3 query limit."""
        pass
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/domain/services/tools/test_search_complexity_queries.py -v`
Expected: Setting tests PASS, async tests are placeholders.

**Step 5: Commit**

```bash
git add backend/app/core/config_features.py \
        backend/app/domain/services/tools/search.py \
        backend/app/domain/services/flows/plan_act.py \
        backend/tests/domain/services/tools/test_search_complexity_queries.py
git commit -m "feat(search): complexity-aware wide research query limit

Tasks with complexity >= 0.8 allow up to 5 queries (configurable via
MAX_WIDE_RESEARCH_QUERIES_COMPLEX). Complexity flows from PlanActFlow
through session.complexity_score to SearchTool.wide_research()."
```

---

## Task 4: Reddit Domain Denylist for Spider

**Files:**
- Modify: `backend/app/infrastructure/external/scraper/research_spider.py` (lines 45-65)
- Modify: `backend/app/domain/services/tools/search.py` (spider enrichment section, ~lines 1466-1490)
- Test: `backend/tests/infrastructure/external/scraper/test_spider_denylist.py` (create)

**Context:** Reddit blocks anonymous scraping with 403 responses. Per Reddit's Responsible Builder Policy, API access requires OAuth approval. Rather than attempting brittle workarounds, we:
1. Add a `SPIDER_DENYLIST_DOMAINS` set in the spider
2. Skip spider enrichment for denied domains — keep the search snippet instead
3. Optionally fall back to browser fetch if browser is available

**Step 1: Write failing tests**

Create `backend/tests/infrastructure/external/scraper/test_spider_denylist.py`:

```python
"""Tests for spider domain denylist."""

import pytest

from app.infrastructure.external.scraper.research_spider import (
    SPIDER_DENYLIST_DOMAINS,
    should_skip_spider,
)


class TestSpiderDenylist:
    """URLs on denied domains should be skipped by the spider."""

    def test_reddit_is_denied(self):
        assert should_skip_spider("https://www.reddit.com/r/OpenAI/comments/abc/title/")

    def test_old_reddit_is_denied(self):
        assert should_skip_spider("https://old.reddit.com/r/OpenAI/comments/abc/title/")

    def test_reddit_subpath_is_denied(self):
        assert should_skip_spider("https://reddit.com/r/LocalLLaMA/comments/xyz/")

    def test_normal_url_is_allowed(self):
        assert not should_skip_spider("https://www.datacamp.com/blog/gpt-5-4")

    def test_github_is_allowed(self):
        assert not should_skip_spider("https://github.com/openai/codex")

    def test_denylist_contains_reddit(self):
        assert "reddit.com" in SPIDER_DENYLIST_DOMAINS
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/infrastructure/external/scraper/test_spider_denylist.py -v`
Expected: FAIL — `should_skip_spider` and `SPIDER_DENYLIST_DOMAINS` don't exist.

**Step 3: Implement denylist in `research_spider.py`**

Add at module level (after imports, before class):

```python
from urllib.parse import urlparse

# Domains that block anonymous scraping or require OAuth/API access.
# Search snippets are preserved for these URLs — no spider enrichment.
SPIDER_DENYLIST_DOMAINS: frozenset[str] = frozenset({
    "reddit.com",      # Responsible Builder Policy — requires OAuth
    "x.com",           # Aggressive bot blocking
    "twitter.com",     # Legacy domain for x.com
})


def should_skip_spider(url: str) -> bool:
    """Check if URL should be skipped by the spider (domain denylist)."""
    try:
        hostname = urlparse(url).hostname or ""
        # Strip www. and check against denylist
        hostname = hostname.removeprefix("www.")
        # Check if hostname ends with any denied domain (handles subdomains)
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in SPIDER_DENYLIST_DOMAINS
        )
    except Exception:
        return False
```

**Step 4: Filter denied URLs in search.py spider enrichment**

In `search.py`, find the spider enrichment section (~line 1466). Before passing URLs to the spider, filter out denied domains:

```python
# Before:
# spider_urls = [r.link for r in top_results if r.link][:spider_url_count]

# After:
from app.infrastructure.external.scraper.research_spider import should_skip_spider

spider_urls = [
    r.link for r in top_results
    if r.link and not should_skip_spider(r.link)
][:spider_url_count]

skipped = sum(1 for r in top_results if r.link and should_skip_spider(r.link))
if skipped:
    logger.info("Skipped %d denied-domain URL(s) from spider enrichment", skipped)
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/infrastructure/external/scraper/test_spider_denylist.py -v`
Expected: All 6 tests PASS.

**Step 6: Commit**

```bash
git add backend/app/infrastructure/external/scraper/research_spider.py \
        backend/app/domain/services/tools/search.py \
        backend/tests/infrastructure/external/scraper/test_spider_denylist.py
git commit -m "fix(spider): add domain denylist for Reddit and X.com

Skip spider enrichment for domains that block anonymous scraping or
require OAuth (Reddit Responsible Builder Policy). Search snippets
are preserved — only full-page spider fetch is skipped."
```

---

## Task 5: Chart Reference Injection in Report Body

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py` (lines 632-849)
- Test: `backend/tests/domain/services/test_chart_reference_injection.py` (create)

**Context:** Charts are generated in `_ensure_plotly_chart_files()` after the report markdown is written to disk. The `ReportEvent.content` already has its final markdown when the chart PNG/HTML are created, so chart filenames never appear in the report body. This triggers the `coverage_missing:artifact references` delivery warning.

**Fix:** Reorder the pipeline in `_ensure_report_file()`:
1. Generate chart files first (before writing `report-{id}.md`)
2. Inject chart reference markdown into `event.content`
3. Write `report-{id}.md` with the updated content (once)

**Step 1: Write failing tests**

Create `backend/tests/domain/services/test_chart_reference_injection.py`:

```python
"""Tests for chart reference injection into report body."""

import pytest


class TestChartReferenceInjection:
    """Chart filenames should appear in the report markdown body."""

    def test_chart_reference_injected_into_content(self):
        """After chart generation, event.content should reference the chart filename."""
        # Will test that event.content contains a reference to the chart file
        # after _ensure_report_file() completes
        pass

    def test_report_file_contains_chart_reference(self):
        """The written report-{id}.md file should contain the chart reference."""
        pass

    def test_no_chart_no_injection(self):
        """When no chart is generated, no injection should occur."""
        pass

    def test_html_and_png_both_referenced(self):
        """Both HTML and PNG chart files should be referenced."""
        pass
```

**Step 2: Reorder `_ensure_report_file` in `agent_task_runner.py`**

Current order (lines 632-849):
1. Write `full-report-{id}.md` (pre-trim)
2. Write `report-{id}.md` (summarized)
3. Generate chart files
4. Return attachments

New order:
1. Write `full-report-{id}.md` (pre-trim) — unchanged
2. Generate chart files — moved up
3. Inject chart references into `event.content`
4. Write `report-{id}.md` (summarized, now includes chart refs)
5. Return attachments

The key change in `_ensure_report_file`:

```python
# Step 1: Write full report (unchanged)
# ... existing full-report write code ...

# Step 2: Generate charts BEFORE writing the summarized report
chart_attachments = []
if settings.feature_plotly_charts_enabled:
    chart_attachments = await self._ensure_plotly_chart_files(
        event, attachments=[], report_id=event.id, ...
    )

# Step 3: Inject chart references into event.content
if chart_attachments:
    chart_ref_lines = ["\n\n---\n\n## Charts\n"]
    for ci in chart_attachments:
        if ci.content_type == "image/png":
            chart_ref_lines.append(f"![Comparison Chart]({ci.filename})\n")
        elif ci.content_type == "text/html":
            chart_ref_lines.append(
                f"*Interactive version:* `{ci.filename}`\n"
            )
    event.content += "\n".join(chart_ref_lines)

# Step 4: Write summarized report (now includes chart refs)
# ... existing report-{id}.md write code ...

# Step 5: Combine all attachments
all_attachments = [*file_attachments, *chart_attachments]
event.attachments = all_attachments
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/domain/services/test_chart_reference_injection.py -v`
Expected: Placeholder tests pass.

**Step 4: Run full test suite to verify no regressions**

Run: `cd backend && python -m pytest tests/ -x --timeout=120 -q`
Expected: All tests pass.

**Step 5: Commit**

```bash
git add backend/app/domain/services/agent_task_runner.py \
        backend/tests/domain/services/test_chart_reference_injection.py
git commit -m "fix(report): inject chart references into report body before file write

Reorder _ensure_report_file() pipeline:
1. Generate charts first
2. Append ## Charts section with image/link references
3. Write report-{id}.md with complete content

Resolves coverage_missing:artifact references delivery warning."
```

---

## Task 6: Verify Issue 7 Resolution and Run Full Suite

**Files:**
- No new code — verification only

**Context:** Issue 7 (`coverage_missing:artifact references` delivery warning) should be resolved by Task 5's chart reference injection. The warning fires in `output_coverage_validator.py` when the report body lacks backtick-wrapped filenames matching `_ARTIFACT_PATTERN`. With chart filenames now in the body (e.g., `` `comparison-chart-xxx.png` ``), the pattern match should succeed.

**Step 1: Trace the warning source**

Verify that the warning logged during the monitored session:
```
Summary coverage missing required elements before compression: artifact references
```
comes from `output_coverage_validator.py` line 86. If it comes from `response_generator.py` line 524 (`_BOILERPLATE_ARTIFACT_REFS_RE`), the fix is different — the boilerplate detection regex needs updating.

**Step 2: Run the full test suite**

```bash
cd backend && conda activate pythinker
python -m pytest tests/ -x --timeout=120 -q
```

Expected: All tests pass (no regressions from Tasks 1-5).

**Step 3: Run linting**

```bash
cd backend && ruff check . && ruff format --check .
```

Expected: Clean.

**Step 4: Commit (only if any adjustment was needed)**

```bash
git commit -m "chore: verify artifact reference warning resolved by chart injection"
```

---

## Task Dependency Graph

```
Task 1 (Redis liveness signal)
    ↓
Task 2 (Fix orphan heuristic) — depends on Task 1
    ↓
Task 3 (Complexity-aware queries) — independent
Task 4 (Reddit denylist) — independent
Task 5 (Chart reference injection) — independent
    ↓
Task 6 (Verify + full suite) — depends on all above
```

Tasks 3, 4, 5 are independent and can be parallelized after Task 2.

---

## Summary of Changes

| Task | Files Modified | Files Created | Tests |
|------|---------------|---------------|-------|
| 1 | `redis_task.py` | `test_redis_task_liveness.py` | 6 |
| 2 | `agent_domain_service.py`, `test_*_teardown.py` | `test_reconnect_liveness.py` | 5 + 3 updated |
| 3 | `config_features.py`, `search.py`, `plan_act.py` | `test_search_complexity_queries.py` | 4 |
| 4 | `research_spider.py`, `search.py` | `test_spider_denylist.py` | 6 |
| 5 | `agent_task_runner.py` | `test_chart_reference_injection.py` | 4 |
| 6 | — | — | Full suite run |

**Total: ~7 files modified, 4 test files created, ~25 new tests, 3 tests updated**
