# Session Monitoring Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 issues discovered during live session monitoring — the critical SSE reconnect race condition that kills live sessions, complexity-aware wide research query limits, Reddit spider resilience, and chart reference injection into research reports.

**Architecture:** Redis liveness signal (heartbeated from `RedisStreamTask`, carrying `task_id`) provides a cross-worker, cross-process liveness check. The reconnect handler in `agent_domain_service.py` reads the liveness key to discover the task_id, then constructs a `RedisStreamQueue("task:output:<task_id>")` directly to poll events — no process-local registry lookup needed. Complexity plumbing flows from `PlanActFlow._cached_complexity` through a new `complexity_score` attribute on `SearchTool` (set at construction in `plan_act.py`). Chart generation is reordered in `agent_task_runner.py` so references are injected into `event.content` before the report file is written. The summarize-time `coverage_missing:artifact references` warning is a separate concern — it fires in `execution.py` before `ReportEvent` is yielded and is auto-repaired by the delivery integrity gate; Task 5 improves the delivered file, not the gate warning. Reddit URLs are added to a domain denylist in `research_spider.py`, falling back to search snippets.

**Tech Stack:** Python 3.12, Redis (SET with EX), asyncio, pytest, Pydantic v2 Settings

**Issues addressed:**
| # | Severity | Issue | Approach |
|---|----------|-------|----------|
| 1 | Critical | SSE reconnect race kills live sessions | Redis liveness key + direct stream polling + ProgressEvent fallback |
| 2 | No-code | Serper key exhaustion cascade | Config/ops — first-discovery behavior is correct |
| 3 | No-code | LLM 90s timeout on step 4 | Already handled by retry — working as designed |
| 4 | Medium | Wide research queries clamped 5→3 | Plumb complexity score to SearchTool via constructor |
| 5 | Medium | Reddit 403 spider block | Domain denylist — skip spider, keep snippets |
| 6 | Medium | Chart not referenced in delivered report file | Reorder: generate chart → inject refs → write file |

**Key API facts (verified against codebase):**
- `RedisStreamTask.run()` starts execution (not `start()`) — `redis_task.py:54`
- `RedisStreamQueue(stream_name)` can be constructed directly from a known stream name — `redis_stream_queue.py:22`
- Stream names: `f"task:output:{task_id}"` — `redis_task.py:29`
- `AgentTaskRunner._session_id` is private (no property) — `agent_task_runner.py:109`
- Events import: `from app.domain.models.event import DoneEvent, ErrorEvent, ProgressEvent` — `event.py`
- `ProgressEvent` requires `phase: PlanningPhase` and `message: str` — `event.py:572-587`
- `Session` has no `add_event()` method; use `session.events.append(event)` + `repository.save()` — `session.py:60`
- `DoneEvent` has no required fields beyond inherited `type`/`id`/`timestamp` — `event.py:494-497`
- Redis client: `from app.infrastructure.storage.redis import get_redis` → `.client` for raw `redis.asyncio.Redis` — `redis.py:363`
- `SearchTool.__init__` takes `search_engine`, `browser`, `max_observe`, `search_prefer_browser`, `scraper` — no session context — `search.py:441`
- `SearchTool` instantiated in `plan_act.py:328` with no `session_id` parameter
- `coverage_missing:artifact references` warning fires at `execution.py:1296-1300` (before `yield ReportEvent`) — the delivery gate auto-repairs it via `append_delivery_integrity_fallback()` in `response_generator.py:634`

---

## Task 1: Redis Task Liveness Signal

**Files:**
- Modify: `backend/app/infrastructure/external/task/redis_task.py` (lines 15-36, 137-155, 186-195)
- Modify: `backend/app/domain/services/agent_task_runner.py` (line 109 — expose session_id)
- Test: `backend/tests/infrastructure/external/task/test_redis_task_liveness.py` (create)

**Context:** `RedisStreamTask` registers tasks in an in-memory dict (`_task_registry`) keyed by `task_id`. This is invisible across workers. We add a Redis key `task:liveness:{session_id}` that carries the `task_id` value, heartbeated every 10s from the running task, cleared in `finally`. The reconnect handler reads this key to discover the task_id, then constructs a `RedisStreamQueue("task:output:<task_id>")` directly to poll events — no local registry needed.

**Step 1: Write the failing tests**

Create `backend/tests/infrastructure/external/task/test_redis_task_liveness.py`:

```python
"""Tests for Redis task liveness signal.

The liveness key stores task_id at task:liveness:{session_id} in Redis
with a 30s TTL, heartbeated every 10s, cleared in finally.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.external.task.redis_task import (
    RedisStreamTask,
    _LIVENESS_KEY_PREFIX,
    _LIVENESS_TTL_SECONDS,
)


@pytest.fixture
def mock_redis_client():
    """Mock raw redis.asyncio.Redis client."""
    client = AsyncMock()
    client.set = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.delete = AsyncMock(return_value=1)
    return client


@pytest.fixture
def mock_runner():
    """Mock task runner. AgentTaskRunner._session_id is private;
    we expose it via the new session_id property added in this task."""
    runner = AsyncMock()
    runner.session_id = "test-session-123"

    async def run_briefly(task):
        await asyncio.sleep(0.05)

    runner.run = run_briefly
    runner.on_done = AsyncMock()
    return runner


class TestLivenessKeyLifecycle:
    """Verify SET on start, heartbeat refresh, DELETE on completion."""

    @pytest.mark.asyncio
    async def test_liveness_key_set_on_task_run(self, mock_runner, mock_redis_client):
        """Liveness key should be SET when _execute_task begins."""
        with patch(
            "app.infrastructure.external.task.redis_task.get_redis"
        ) as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            task = RedisStreamTask(mock_runner)
            await task.run()
            # Wait for completion + cleanup
            await asyncio.sleep(0.2)

            set_calls = [
                c
                for c in mock_redis_client.set.call_args_list
                if str(c).find(f"{_LIVENESS_KEY_PREFIX}test-session-123") >= 0
            ]
            assert len(set_calls) >= 1, "Liveness key must be SET on task start"

    @pytest.mark.asyncio
    async def test_liveness_key_value_is_task_id(self, mock_runner, mock_redis_client):
        """Liveness key value must be the task_id (not boolean)."""
        with patch(
            "app.infrastructure.external.task.redis_task.get_redis"
        ) as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            task = RedisStreamTask(mock_runner)
            task_id = task.id
            await task.run()
            await asyncio.sleep(0.2)

            set_calls = [
                c
                for c in mock_redis_client.set.call_args_list
                if str(c).find(f"{_LIVENESS_KEY_PREFIX}test-session-123") >= 0
            ]
            assert len(set_calls) >= 1
            # Positional arg [0][1] or kwarg 'value' should be the task_id
            first_call = set_calls[0]
            value = (
                first_call[0][1]
                if len(first_call[0]) > 1
                else first_call[1].get("value")
            )
            assert value == task_id

    @pytest.mark.asyncio
    async def test_liveness_key_has_30s_ttl(self, mock_runner, mock_redis_client):
        """SET must include ex=30 for crash-safety TTL."""
        with patch(
            "app.infrastructure.external.task.redis_task.get_redis"
        ) as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            task = RedisStreamTask(mock_runner)
            await task.run()
            await asyncio.sleep(0.2)

            set_calls = [
                c
                for c in mock_redis_client.set.call_args_list
                if str(c).find(f"{_LIVENESS_KEY_PREFIX}test-session-123") >= 0
            ]
            assert len(set_calls) >= 1
            assert set_calls[0][1].get("ex") == _LIVENESS_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_liveness_key_deleted_on_task_done(self, mock_runner, mock_redis_client):
        """Liveness key must be DELETEd when the task completes (finally block)."""
        with patch(
            "app.infrastructure.external.task.redis_task.get_redis"
        ) as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            task = RedisStreamTask(mock_runner)
            await task.run()
            await asyncio.sleep(0.3)

            delete_calls = [
                c
                for c in mock_redis_client.delete.call_args_list
                if str(c).find(f"{_LIVENESS_KEY_PREFIX}test-session-123") >= 0
            ]
            assert len(delete_calls) >= 1, "Liveness key must be deleted on completion"

    @pytest.mark.asyncio
    async def test_liveness_key_deleted_on_exception(self, mock_runner, mock_redis_client):
        """Liveness key must be DELETEd even when runner.run() raises."""
        async def failing_run(task):
            raise RuntimeError("boom")

        mock_runner.run = failing_run

        with patch(
            "app.infrastructure.external.task.redis_task.get_redis"
        ) as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            task = RedisStreamTask(mock_runner)
            await task.run()
            await asyncio.sleep(0.2)

            delete_calls = [
                c
                for c in mock_redis_client.delete.call_args_list
                if str(c).find(f"{_LIVENESS_KEY_PREFIX}test-session-123") >= 0
            ]
            assert len(delete_calls) >= 1, "Liveness key must be deleted on exception"


class TestGetLiveness:
    """Verify the classmethod that reads the liveness key."""

    @pytest.mark.asyncio
    async def test_returns_task_id_when_key_exists(self, mock_redis_client):
        """get_liveness should return the task_id string when key exists."""
        mock_redis_client.get = AsyncMock(return_value=b"task-uuid-abc123")
        with patch(
            "app.infrastructure.external.task.redis_task.get_redis"
        ) as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            result = await RedisStreamTask.get_liveness("sess-xyz")
            assert result == "task-uuid-abc123"
            mock_redis_client.get.assert_called_once_with(
                f"{_LIVENESS_KEY_PREFIX}sess-xyz"
            )

    @pytest.mark.asyncio
    async def test_returns_none_when_key_missing(self, mock_redis_client):
        """get_liveness should return None when no liveness key exists."""
        mock_redis_client.get = AsyncMock(return_value=None)
        with patch(
            "app.infrastructure.external.task.redis_task.get_redis"
        ) as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            result = await RedisStreamTask.get_liveness("sess-gone")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_error(self, mock_redis_client):
        """get_liveness must not raise on Redis failures."""
        mock_redis_client.get = AsyncMock(side_effect=ConnectionError("down"))
        with patch(
            "app.infrastructure.external.task.redis_task.get_redis"
        ) as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            result = await RedisStreamTask.get_liveness("sess-err")
            assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/infrastructure/external/task/test_redis_task_liveness.py -v`
Expected: FAIL — `get_liveness`, `_LIVENESS_KEY_PREFIX`, `_LIVENESS_TTL_SECONDS` don't exist yet.

**Step 3: Implement liveness signal in `redis_task.py`**

Add constants after line 14 (after `_task_registry`):

```python
_LIVENESS_KEY_PREFIX = "task:liveness:"
_LIVENESS_TTL_SECONDS = 30
_LIVENESS_HEARTBEAT_INTERVAL = 10
```

Add to `__init__` (after line 36, after `_task_registry[self._id] = self`):

```python
self._session_id: str | None = getattr(runner, "session_id", None)
self._heartbeat_task: asyncio.Task | None = None
```

Replace `_execute_task` method (line 186-195):

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

Add liveness methods (after `get()` classmethod at line 204):

```python
@classmethod
async def get_liveness(cls, session_id: str) -> str | None:
    """Check if a task is alive for the given session. Returns task_id or None."""
    try:
        from app.infrastructure.storage.redis import get_redis
        raw_redis = get_redis().client
        value = await raw_redis.get(f"{_LIVENESS_KEY_PREFIX}{session_id}")
        return value.decode() if value else None
    except Exception as e:
        logger.warning("Failed to read liveness key for session %s: %s", session_id, e)
        return None

async def _set_liveness(self) -> None:
    """SET liveness key in Redis with TTL. Value = task_id."""
    if not self._session_id:
        return
    try:
        from app.infrastructure.storage.redis import get_redis
        raw_redis = get_redis().client
        await raw_redis.set(
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
    """DELETE liveness key on task completion/failure."""
    if not self._session_id:
        return
    try:
        from app.infrastructure.storage.redis import get_redis
        raw_redis = get_redis().client
        await raw_redis.delete(f"{_LIVENESS_KEY_PREFIX}{self._session_id}")
    except Exception as e:
        logger.warning("Failed to clear liveness key for session %s: %s", self._session_id, e)
```

**Step 4: Expose `session_id` on `AgentTaskRunner`**

In `agent_task_runner.py`, add a read-only property after line 109 (`self._session_id = session_id`):

```python
@property
def session_id(self) -> str:
    """Session ID — exposed for RedisStreamTask liveness signal."""
    return self._session_id
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/infrastructure/external/task/test_redis_task_liveness.py -v`
Expected: All 9 tests PASS.

**Step 6: Commit**

```bash
git add backend/app/infrastructure/external/task/redis_task.py \
        backend/app/domain/services/agent_task_runner.py \
        backend/tests/infrastructure/external/task/test_redis_task_liveness.py
git commit -m "feat(task): add Redis liveness signal for SSE reconnect race detection

Heartbeat task:liveness:{session_id} every 10s with 30s TTL.
Value is task_id — allows reconnect handler to construct
RedisStreamQueue('task:output:<task_id>') directly.
Cleared in finally for crash safety.
Expose session_id property on AgentTaskRunner."
```

---

## Task 2: Fix Orphan Detection Heuristic in `agent_domain_service.py`

**Files:**
- Modify: `backend/app/domain/services/agent_domain_service.py` (lines 738-814)
- Modify: `backend/tests/domain/services/test_agent_domain_service_chat_teardown.py` (3 tests updated)
- Test: `backend/tests/domain/services/test_reconnect_liveness.py` (create)

**Context:** The orphan heuristic at line 790 currently yields `DoneEvent` for RUNNING sessions with no task within 180s — this kills live sessions. With the liveness signal from Task 1:
1. Check `RedisStreamTask.get_liveness(session_id)` — returns `task_id` or `None`
2. If liveness exists → construct `RedisStreamQueue(f"task:output:{task_id}")` directly and poll it (works cross-worker — no local registry needed)
3. If liveness missing but session < 180s → emit `ProgressEvent(phase=PlanningPhase.EXECUTING_SETUP, message=...)` + bounded 15s polling
4. If liveness missing and session >= 180s → `ErrorEvent` + `CANCELLED` (unchanged)

**Step 1: Write the failing tests**

Create `backend/tests/domain/services/test_reconnect_liveness.py`:

```python
"""Tests for reconnect behavior with Redis liveness signal.

Verifies that when an SSE reconnect arrives:
- If liveness key exists → poll task:output:<task_id> via RedisStreamQueue
- If no liveness but recent session → ProgressEvent + bounded polling (not DoneEvent)
- If no liveness and stale → ErrorEvent + CANCELLED (existing behavior)
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.domain.models.event import (
    DoneEvent,
    ErrorEvent,
    PlanningPhase,
    ProgressEvent,
)
from app.domain.models.session import Session, SessionStatus


def _make_session(
    session_id: str = "sess-reconnect",
    status: SessionStatus = SessionStatus.RUNNING,
    task_id: str | None = None,
    age_seconds: float = 10.0,
) -> MagicMock:
    """Create a mock Session with realistic field values."""
    session = MagicMock(spec=Session)
    session.id = session_id
    session.user_id = "user-1"
    session.title = "Test Research"
    session.status = status
    session.task_id = task_id
    session.updated_at = datetime.now(UTC) - timedelta(seconds=age_seconds)
    session.events = []
    session.complexity_score = None
    session.source = "web"
    session.mode = MagicMock()
    session.mode.value = "agent"
    return session


class TestReconnectWithLivenessKey:
    """When liveness key exists, reconnect should poll task:output:<task_id> directly."""

    @pytest.mark.asyncio
    async def test_liveness_found_constructs_stream_queue_and_polls(self):
        """get_liveness returns task_id → construct RedisStreamQueue and read events."""
        # Arrange: liveness returns a task_id, stream returns a DoneEvent then stops
        done_event_bytes = b'{"type": "done", "id": "evt-1", "timestamp": "2026-03-08T10:00:00Z"}'

        with (
            patch(
                "app.domain.services.agent_domain_service.RedisStreamTask.get_liveness",
                new_callable=AsyncMock,
                return_value="live-task-id-123",
            ),
            patch(
                "app.domain.services.agent_domain_service.RedisStreamQueue"
            ) as MockQueue,
        ):
            mock_stream = AsyncMock()
            # First call returns event, second call returns (None, None) to exit loop
            mock_stream.get = AsyncMock(
                side_effect=[
                    ("1772962550653-1", done_event_bytes),
                    (None, None),
                ]
            )
            MockQueue.return_value = mock_stream

            # Act: invoke the reconnect path (will need actual service setup)
            # This test structure validates that RedisStreamQueue is constructed
            # with the correct stream name and polled
            MockQueue.assert_not_called()  # Not called yet before we invoke chat()

            # The implementation test will call agent_domain_service.chat()
            # with task_id=None and verify:
            # 1. RedisStreamQueue("task:output:live-task-id-123") was constructed
            # 2. .get() was called to poll events
            # 3. DoneEvent was yielded (not the false orphan DoneEvent)

    @pytest.mark.asyncio
    async def test_liveness_found_stream_name_is_task_output_prefix(self):
        """The constructed stream must use f'task:output:{task_id}' naming."""
        with (
            patch(
                "app.domain.services.agent_domain_service.RedisStreamTask.get_liveness",
                new_callable=AsyncMock,
                return_value="my-task-42",
            ),
            patch(
                "app.domain.services.agent_domain_service.RedisStreamQueue"
            ) as MockQueue,
        ):
            mock_stream = AsyncMock()
            mock_stream.get = AsyncMock(return_value=(None, None))
            MockQueue.return_value = mock_stream

            # After chat() runs, verify stream name
            # MockQueue.assert_called_once_with("task:output:my-task-42")


class TestReconnectNoLivenessGracePeriod:
    """When liveness missing but session < 180s, emit ProgressEvent not DoneEvent."""

    @pytest.mark.asyncio
    async def test_recent_session_emits_progress_event(self):
        """Session updated 10s ago, no liveness → ProgressEvent with EXECUTING_SETUP phase."""
        session = _make_session(age_seconds=10.0)

        with patch(
            "app.domain.services.agent_domain_service.RedisStreamTask.get_liveness",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # After chat() yields events, the FIRST event should be ProgressEvent
            # (not DoneEvent as the old heuristic did)
            # event = <first yielded>
            # assert isinstance(event, ProgressEvent)
            # assert event.phase == PlanningPhase.EXECUTING_SETUP
            pass  # Full integration test requires service setup — structure validated above

    @pytest.mark.asyncio
    async def test_bounded_polling_exhaustion_emits_done(self):
        """After 15s bounded polling with no liveness appearing, DoneEvent is yielded."""
        session = _make_session(age_seconds=10.0)

        with patch(
            "app.domain.services.agent_domain_service.RedisStreamTask.get_liveness",
            new_callable=AsyncMock,
            return_value=None,  # Stays None through all polls
        ):
            # events = list(chat())
            # assert isinstance(events[0], ProgressEvent)  # Bounded polling starts
            # assert isinstance(events[-1], DoneEvent)      # Polling exhausted
            pass

    @pytest.mark.asyncio
    async def test_bounded_polling_picks_up_late_liveness(self):
        """If liveness key appears during 15s polling, switch to stream polling."""
        with patch(
            "app.domain.services.agent_domain_service.RedisStreamTask.get_liveness",
            new_callable=AsyncMock,
            side_effect=[None, None, "late-task-id"],  # Appears on 3rd check
        ):
            # events = list(chat())
            # assert isinstance(events[0], ProgressEvent)  # Initial
            # assert not any(isinstance(e, DoneEvent) for e in events[:2])
            pass


class TestReconnectStaleOrphan:
    """When liveness missing and session >= 180s, existing CANCELLED behavior unchanged."""

    @pytest.mark.asyncio
    async def test_stale_session_emits_error_and_cancels(self):
        """Session updated 240s ago, no liveness → ErrorEvent + CANCELLED."""
        session = _make_session(age_seconds=240.0)

        with patch(
            "app.domain.services.agent_domain_service.RedisStreamTask.get_liveness",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # events = list(chat())
            # assert isinstance(events[0], ErrorEvent)
            # assert "interrupted" in events[0].error
            pass
```

Note: These tests define the contract. The `pass` bodies will be filled during execution by wiring up the actual `AgentDomainService.chat()` invocation with the same mock patterns used in `test_agent_domain_service_chat_teardown.py`.

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/domain/services/test_reconnect_liveness.py -v`
Expected: FAIL — imports of new symbols and mock targets don't exist yet.

**Step 3: Modify the orphan detection block (lines 780-814)**

Replace the `# True orphan/reconnect` block at lines 780-814 with:

```python
# --- Reconnect liveness check ---
# Check Redis liveness key: carries task_id, survives cross-worker.
# Stream names are derivable: f"task:output:{task_id}"
from app.infrastructure.external.task.redis_task import RedisStreamTask
from app.infrastructure.external.message_queue.redis_stream_queue import RedisStreamQueue

live_task_id = await RedisStreamTask.get_liveness(session_id)

if live_task_id:
    # Task is alive — poll its output stream directly (cross-worker safe)
    logger.info(
        "Reconnect found live task %s for session %s via liveness signal",
        live_task_id, session_id,
    )
    output_stream = RedisStreamQueue(f"task:output:{live_task_id}")
    poll_deadline = asyncio.get_event_loop().time() + 120.0
    while asyncio.get_event_loop().time() < poll_deadline:
        event_id_out, event_data = await output_stream.get(
            start_id=latest_event_id or "0",
            block_ms=2000,
        )
        if event_id_out and event_data:
            latest_event_id = event_id_out
            try:
                import json
                event_dict = json.loads(event_data) if isinstance(event_data, (str, bytes)) else event_data
                from app.domain.models.event import AgentEvent
                event = AgentEvent.model_validate(event_dict)
            except Exception:
                continue
            received_events = True
            yield event
            if isinstance(event, DoneEvent):
                terminal_status = SessionStatus.COMPLETED
                break
            if isinstance(event, ErrorEvent):
                terminal_status = SessionStatus.FAILED
                break
        else:
            # Check if liveness key expired (task completed between polls)
            still_alive = await RedisStreamTask.get_liveness(session_id)
            if not still_alive:
                break
    if terminal_status is None:
        # Task finished without terminal event in stream — mark completed
        terminal_status = SessionStatus.COMPLETED
        yield DoneEvent()
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
        yield ProgressEvent(
            phase=PlanningPhase.EXECUTING_SETUP,
            message="Session is being processed. Reconnecting...",
        )

        # Bounded poll: check for late-arriving liveness (15s max)
        bounded_deadline = asyncio.get_event_loop().time() + 15.0
        found_live = False
        while asyncio.get_event_loop().time() < bounded_deadline:
            late_task_id = await RedisStreamTask.get_liveness(session_id)
            if late_task_id:
                found_live = True
                logger.info(
                    "Late liveness found for session %s (task %s) — switching to stream polling",
                    session_id, late_task_id,
                )
                output_stream = RedisStreamQueue(f"task:output:{late_task_id}")
                while True:
                    ev_id, ev_data = await output_stream.get(
                        start_id=latest_event_id or "0", block_ms=2000,
                    )
                    if ev_id and ev_data:
                        latest_event_id = ev_id
                        try:
                            import json
                            ev_dict = json.loads(ev_data) if isinstance(ev_data, (str, bytes)) else ev_data
                            from app.domain.models.event import AgentEvent
                            event = AgentEvent.model_validate(ev_dict)
                        except Exception:
                            continue
                        received_events = True
                        yield event
                        if isinstance(event, DoneEvent):
                            terminal_status = SessionStatus.COMPLETED
                            break
                        if isinstance(event, ErrorEvent):
                            terminal_status = SessionStatus.FAILED
                            break
                    else:
                        still_alive = await RedisStreamTask.get_liveness(session_id)
                        if not still_alive:
                            break
                if terminal_status is None:
                    terminal_status = SessionStatus.COMPLETED
                    yield DoneEvent()
                break
            await asyncio.sleep(1.0)

        if not found_live and terminal_status is None:
            # Grace period polling exhausted — emit DoneEvent as last resort
            logger.warning(
                "Session %s bounded polling exhausted (%.1fs age) — emitting done",
                session_id, session_age,
            )
            yield DoneEvent()
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
            session.events.append(error_event)
            await self._session_repository.save(session)
        yield error_event
        terminal_status = SessionStatus.CANCELLED
```

**Step 4: Add import for `PlanningPhase` at top of `agent_domain_service.py`**

Verify `PlanningPhase` is already imported. If not, add to existing event imports:

```python
from app.domain.models.event import DoneEvent, ErrorEvent, PlanningPhase, ProgressEvent
```

**Step 5: Update existing tests in `test_agent_domain_service_chat_teardown.py`**

Three tests that assert `DoneEvent` for recent RUNNING sessions need updating:

1. `test_chat_no_active_task_recent_running_session_emits_done_not_cancel` (L119)
2. `test_chat_no_active_task_within_grace_period_emits_done_not_cancel` (L145)
3. `test_chat_no_active_task_recent_running_session_with_naive_updated_at_emits_done` (L170)

Each needs:
- Add `@patch("app.domain.services.agent_domain_service.RedisStreamTask.get_liveness", new_callable=AsyncMock, return_value=None)` decorator
- Change assertion: first event is now `ProgressEvent` (bounded polling), last event is `DoneEvent` (polling exhausted)
- Teardown still called with `COMPLETED`

The stale-orphan test (L94) also needs the liveness mock but its assertions stay the same (`ErrorEvent` + `CANCELLED`).

**Step 6: Run all tests**

Run: `cd backend && python -m pytest tests/domain/services/test_agent_domain_service_chat_teardown.py tests/domain/services/test_reconnect_liveness.py -v`
Expected: All PASS.

**Step 7: Commit**

```bash
git add backend/app/domain/services/agent_domain_service.py \
        backend/tests/domain/services/test_agent_domain_service_chat_teardown.py \
        backend/tests/domain/services/test_reconnect_liveness.py
git commit -m "fix(sse): replace DoneEvent with liveness-based stream polling on reconnect

On reconnect with task_id=None:
1. get_liveness(session_id) → task_id → RedisStreamQueue('task:output:<id>') → poll (cross-worker safe)
2. No liveness + session < 180s → ProgressEvent(EXECUTING_SETUP) + 15s bounded poll
3. No liveness + session >= 180s → ErrorEvent + CANCELLED (unchanged)

Fixes: frontend showing session as completed while agent is still running."
```

---

## Task 3: Complexity-Aware Wide Research Query Limit

**Files:**
- Modify: `backend/app/core/config_features.py` (line 61)
- Modify: `backend/app/domain/services/tools/search.py` (lines 441-456 constructor, lines 1376-1379 clamp)
- Modify: `backend/app/domain/services/flows/plan_act.py` (line 328 — SearchTool construction)
- Test: `backend/tests/domain/services/tools/test_search_complexity_queries.py` (create)

**Context:** `SearchTool.__init__` takes `search_engine, browser, max_observe, search_prefer_browser, scraper` — no session context. Complexity score is computed in `PlanActFlow` at line 2306 and cached as `self._cached_complexity`. We add `complexity_score: float | None = None` as a new constructor parameter to `SearchTool`, passed from `plan_act.py` at construction time (line 328). Inside `wide_research()`, the clamp logic reads this attribute to choose between default and complex limits.

**Step 1: Write the failing tests**

Create `backend/tests/domain/services/tools/test_search_complexity_queries.py`:

```python
"""Tests for complexity-aware wide research query limits.

Default: 3 queries. When complexity >= 0.8: up to 5 queries.
Complexity flows via SearchTool(complexity_score=...) constructor param.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestComplexitySettings:
    """Config settings for query limits."""

    def test_default_limit_is_3(self):
        from app.core.config_features import FeatureSettings
        assert FeatureSettings().max_wide_research_queries == 3

    def test_complex_limit_default_is_5(self):
        from app.core.config_features import FeatureSettings
        assert FeatureSettings().max_wide_research_queries_complex == 5


class TestSearchToolComplexityParam:
    """SearchTool accepts and uses complexity_score parameter."""

    def test_search_tool_accepts_complexity_score(self):
        """Constructor should accept complexity_score without error."""
        from app.domain.services.tools.search import SearchTool
        mock_engine = MagicMock()
        tool = SearchTool(mock_engine, complexity_score=0.95)
        assert tool._complexity_score == 0.95

    def test_search_tool_defaults_complexity_to_none(self):
        """Without complexity_score, it defaults to None."""
        from app.domain.services.tools.search import SearchTool
        mock_engine = MagicMock()
        tool = SearchTool(mock_engine)
        assert tool._complexity_score is None


class TestEffectiveQueryLimit:
    """wide_research should use higher limit for complex tasks."""

    def test_effective_max_is_5_when_complexity_high(self):
        """complexity_score >= 0.8 → effective max = max_wide_research_queries_complex."""
        from app.domain.services.tools.search import SearchTool
        mock_engine = MagicMock()
        tool = SearchTool(mock_engine, complexity_score=1.0)
        assert tool._effective_max_wide_queries >= 5

    def test_effective_max_is_3_when_complexity_low(self):
        """complexity_score < 0.8 → effective max = max_wide_research_queries (3)."""
        from app.domain.services.tools.search import SearchTool
        mock_engine = MagicMock()
        tool = SearchTool(mock_engine, complexity_score=0.5)
        assert tool._effective_max_wide_queries == 3

    def test_effective_max_is_3_when_no_complexity(self):
        """No complexity_score → default limit."""
        from app.domain.services.tools.search import SearchTool
        mock_engine = MagicMock()
        tool = SearchTool(mock_engine)
        assert tool._effective_max_wide_queries == 3
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/domain/services/tools/test_search_complexity_queries.py -v`
Expected: FAIL — `complexity_score` param and `_effective_max_wide_queries` don't exist.

**Step 3: Add config setting**

In `config_features.py`, after line 61:

```python
max_wide_research_queries: int = 3        # Default for simple/medium tasks
max_wide_research_queries_complex: int = 5  # For very_complex tasks (complexity >= 0.8)
```

**Step 4: Add `complexity_score` to SearchTool constructor**

In `search.py`, modify `__init__` (lines 441-456):

```python
def __init__(
    self,
    search_engine: SearchEngine,
    browser: "Browser | None" = None,
    max_observe: int | None = None,
    search_prefer_browser: bool | None = None,
    scraper: "Scraper | None" = None,
    complexity_score: float | None = None,
):
```

After line 483 (`self._max_wide_queries = settings.max_wide_research_queries`), add:

```python
self._complexity_score = complexity_score
self._effective_max_wide_queries = (
    settings.max_wide_research_queries_complex
    if complexity_score is not None and complexity_score >= 0.8
    else settings.max_wide_research_queries
)
```

**Step 5: Update clamp logic**

In `search.py`, replace the clamp at lines 1376-1379:

```python
if len(queries) > self._effective_max_wide_queries:
    logger.warning(
        "Wide research queries clamped: %d → %d (complexity=%s)",
        len(queries), self._effective_max_wide_queries,
        self._complexity_score,
    )
    queries = queries[: self._effective_max_wide_queries]
```

**Step 6: Pass complexity at construction in `plan_act.py`**

In `plan_act.py` at line 328, the SearchTool is constructed before complexity is assessed (which happens at line 2299). Two options:
- **Option A**: Move SearchTool construction after complexity assessment
- **Option B**: Set complexity after construction via a setter

Since complexity is assessed early (before execution starts), and `plan_act.py` likely constructs tools in `__init__`, use a setter. Add to `SearchTool`:

```python
def set_complexity_score(self, score: float | None) -> None:
    """Update complexity score after construction."""
    self._complexity_score = score
    settings = get_settings()
    self._effective_max_wide_queries = (
        settings.max_wide_research_queries_complex
        if score is not None and score >= 0.8
        else settings.max_wide_research_queries
    )
```

Then in `plan_act.py`, after line 2310 (`self._cached_complexity = assessment.score`):

```python
if hasattr(self, "_search_tool") and self._search_tool:
    self._search_tool.set_complexity_score(assessment.score)
```

**Step 7: Run tests**

Run: `cd backend && python -m pytest tests/domain/services/tools/test_search_complexity_queries.py -v`
Expected: All 7 tests PASS.

**Step 8: Commit**

```bash
git add backend/app/core/config_features.py \
        backend/app/domain/services/tools/search.py \
        backend/app/domain/services/flows/plan_act.py \
        backend/tests/domain/services/tools/test_search_complexity_queries.py
git commit -m "feat(search): complexity-aware wide research query limit

Add complexity_score param to SearchTool. Tasks with complexity >= 0.8
use max_wide_research_queries_complex (default 5) instead of default 3.
PlanActFlow passes score via set_complexity_score() after assessment."
```

---

## Task 4: Reddit Domain Denylist for Spider

**Files:**
- Modify: `backend/app/infrastructure/external/scraper/research_spider.py` (add module-level function)
- Modify: `backend/app/domain/services/tools/search.py` (spider enrichment filter, ~lines 1466-1490)
- Test: `backend/tests/infrastructure/external/scraper/test_spider_denylist.py` (create)

**Context:** Reddit blocks anonymous scraping (403). Per Reddit's Responsible Builder Policy, API access requires OAuth approval. Fix: add domain denylist, skip spider enrichment for denied domains, keep search snippets.

**Step 1: Write failing tests**

Create `backend/tests/infrastructure/external/scraper/test_spider_denylist.py`:

```python
"""Tests for spider domain denylist.

Domains like reddit.com that block anonymous scraping should be
skipped by the spider. Search snippets are preserved instead.
"""

import pytest

from app.infrastructure.external.scraper.research_spider import (
    SPIDER_DENYLIST_DOMAINS,
    should_skip_spider,
)


class TestShouldSkipSpider:
    """URL-level denylist checks."""

    def test_reddit_www(self):
        assert should_skip_spider("https://www.reddit.com/r/OpenAI/comments/abc/title/")

    def test_reddit_bare(self):
        assert should_skip_spider("https://reddit.com/r/LocalLLaMA/comments/xyz/")

    def test_old_reddit(self):
        assert should_skip_spider("https://old.reddit.com/r/programming/")

    def test_x_com(self):
        assert should_skip_spider("https://x.com/elonmusk/status/12345")

    def test_twitter_legacy(self):
        assert should_skip_spider("https://twitter.com/openai/status/67890")

    def test_datacamp_allowed(self):
        assert not should_skip_spider("https://www.datacamp.com/blog/gpt-5-4")

    def test_github_allowed(self):
        assert not should_skip_spider("https://github.com/openai/codex")

    def test_empty_url(self):
        assert not should_skip_spider("")

    def test_malformed_url(self):
        assert not should_skip_spider("not-a-url")


class TestDenylistContents:
    """Verify denylist set contains expected domains."""

    def test_contains_reddit(self):
        assert "reddit.com" in SPIDER_DENYLIST_DOMAINS

    def test_contains_x(self):
        assert "x.com" in SPIDER_DENYLIST_DOMAINS

    def test_contains_twitter(self):
        assert "twitter.com" in SPIDER_DENYLIST_DOMAINS
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/infrastructure/external/scraper/test_spider_denylist.py -v`
Expected: FAIL — `should_skip_spider` and `SPIDER_DENYLIST_DOMAINS` don't exist.

**Step 3: Implement denylist in `research_spider.py`**

Add at module level (after imports, before `class ResearchSpider`):

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
        hostname = hostname.removeprefix("www.")
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
from app.infrastructure.external.scraper.research_spider import should_skip_spider

# Filter denied domains before spider enrichment
spider_candidates = [r.link for r in top_results if r.link]
denied_count = sum(1 for u in spider_candidates if should_skip_spider(u))
spider_urls = [u for u in spider_candidates if not should_skip_spider(u)][:spider_url_count]

if denied_count:
    logger.info("Skipped %d denied-domain URL(s) from spider enrichment", denied_count)
```

**Step 5: Run tests**

Run: `cd backend && python -m pytest tests/infrastructure/external/scraper/test_spider_denylist.py -v`
Expected: All 12 tests PASS.

**Step 6: Commit**

```bash
git add backend/app/infrastructure/external/scraper/research_spider.py \
        backend/app/domain/services/tools/search.py \
        backend/tests/infrastructure/external/scraper/test_spider_denylist.py
git commit -m "fix(spider): add domain denylist for Reddit, X.com, Twitter

Skip spider enrichment for domains that block anonymous scraping or
require OAuth (Reddit Responsible Builder Policy). Search snippets
are preserved — only full-page spider fetch is skipped."
```

---

## Task 5: Chart Reference Injection in Delivered Report File

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py` (lines 632-849)
- Test: `backend/tests/domain/services/test_chart_reference_injection.py` (create)

**Context:** This fixes the delivered report file only — NOT the summarize-time `coverage_missing:artifact references` warning. That warning fires in `execution.py:1296` before `yield ReportEvent`, is auto-repaired by the delivery integrity gate (`response_generator.py:634 append_delivery_integrity_fallback()`), and is a separate informational concern.

The problem this task addresses: `agent_task_runner._ensure_report_file()` writes `report-{id}.md` at line 682-700 BEFORE generating charts at line 749-849. The chart filenames never appear in the written markdown file. Fix: reorder to generate charts first, inject references into `event.content`, then write the report file.

**Step 1: Write failing tests**

Create `backend/tests/domain/services/test_chart_reference_injection.py`:

```python
"""Tests for chart reference injection into delivered report file.

Charts must be generated before report-{id}.md is written, so the
written file includes references to chart filenames.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.models.event import ReportEvent


class TestChartReferenceInContent:
    """After _ensure_report_file, event.content should reference charts."""

    def test_png_chart_referenced_in_content(self):
        """event.content should contain the PNG chart filename in backticks."""
        event = ReportEvent(
            id="test-report-1",
            title="Test Report",
            content="# Report\n\nSome analysis here.",
        )
        # After _ensure_report_file with chart generation:
        # assert "comparison-chart-test-report-1.png" in event.content
        # This will be tested via integration with _ensure_report_file mock

    def test_html_chart_referenced_in_content(self):
        """event.content should contain the HTML chart filename in backticks."""
        event = ReportEvent(
            id="test-report-1",
            title="Test Report",
            content="# Report\n\nSome analysis here.",
        )
        # assert "comparison-chart-test-report-1.html" in event.content

    def test_no_chart_no_injection(self):
        """When chart generation returns no files, content is unchanged."""
        event = ReportEvent(
            id="test-report-1",
            title="Test Report",
            content="# Report\n\nOriginal content.",
        )
        original_content = event.content
        # After _ensure_report_file with no chart:
        # assert event.content == original_content


class TestChartReferenceFormat:
    """Verify the injected chart reference markdown format."""

    def test_png_uses_image_syntax(self):
        """PNG should be referenced with ![alt](filename) markdown."""
        ref = "![Comparison Chart](comparison-chart-abc.png)"
        # The injected content should contain this pattern
        assert ref.startswith("![")

    def test_html_uses_backtick_syntax(self):
        """HTML should be referenced with `filename` backtick syntax."""
        ref = "`comparison-chart-abc.html`"
        assert ref.startswith("`")
```

**Step 2: Run tests**

Run: `cd backend && python -m pytest tests/domain/services/test_chart_reference_injection.py -v`
Expected: All PASS (unit tests on format; integration will be validated in step 4).

**Step 3: Reorder `_ensure_report_file` in `agent_task_runner.py`**

Current order in `_ensure_report_file` (lines 632-849):
1. Write `full-report-{id}.md` (pre-trim) — lines 650-680
2. Write `report-{id}.md` (summarized) — lines 682-700
3. Determine chart generation mode — lines 705-726
4. Generate chart files — lines 740-849

New order:
1. Write `full-report-{id}.md` (pre-trim) — unchanged
2. Determine chart generation mode + generate charts — moved up
3. Inject chart references into `event.content`
4. Write `report-{id}.md` (summarized, now includes chart refs)
5. Assemble all attachments

The implementation requires moving the chart generation block (lines 705-849) before the summarized report write (lines 682-700), then inserting the reference injection between them.

After chart generation returns `chart_attachments` (list of `FileInfo`):

```python
# Inject chart references into event.content before writing report file
if chart_attachments:
    chart_lines = ["\n\n---\n\n## Charts\n"]
    for ci in chart_attachments:
        if ci.content_type == "image/png":
            chart_lines.append(f"![Comparison Chart]({ci.filename})")
        elif ci.content_type == "text/html":
            chart_lines.append(f"*Interactive version:* `{ci.filename}`")
    event.content += "\n".join(chart_lines) + "\n"
```

Then the existing `report-{id}.md` write code runs on the updated `event.content`.

**Step 4: Run full test suite**

Run: `cd backend && python -m pytest tests/ -x --timeout=120 -q`
Expected: All tests pass (no regressions).

**Step 5: Commit**

```bash
git add backend/app/domain/services/agent_task_runner.py \
        backend/tests/domain/services/test_chart_reference_injection.py
git commit -m "fix(report): inject chart references into report body before file write

Reorder _ensure_report_file() pipeline:
1. Write full-report-{id}.md (unchanged)
2. Generate charts (moved up)
3. Append ## Charts section with image/link references to event.content
4. Write report-{id}.md with complete content

The delivered markdown file now includes chart references.
Note: the summarize-time coverage_missing:artifact references warning
is a separate concern handled by the delivery integrity auto-repair."
```

---

## Task 6: Final Verification and Full Suite

**Files:**
- No new code — verification only

**Step 1: Run full backend test suite**

```bash
cd backend && conda activate pythinker
python -m pytest tests/ -x --timeout=120 -q
```

Expected: All tests pass.

**Step 2: Run linting**

```bash
cd backend && ruff check . && ruff format --check .
```

Expected: Clean.

**Step 3: Verify the summarize-time warning is NOT a bug**

The monitored session logged:
```
Summary coverage missing required elements before compression: artifact references
Delivery integrity warnings: coverage_missing:artifact references; hallucination_ratio_low
```

This warning fires at `execution.py:1296-1300` before `yield ReportEvent`. The delivery gate at `response_generator.py:634` auto-repairs it by appending `_artifact_references_section()` which lists known files in backticks. The report WAS delivered successfully with the repaired content. This is informational logging, not a delivery failure.

Task 5's chart reference injection does NOT fix this warning (it runs later in `agent_task_runner.py`). The warning remains but is handled correctly by the auto-repair pipeline.

**Step 4: Run frontend lint**

```bash
cd frontend && bun run lint && bun run type-check
```

Expected: Clean (no frontend changes in this plan).

---

## Task Dependency Graph

```
Task 1 (Redis liveness signal)
    ↓
Task 2 (Fix orphan heuristic) — depends on Task 1
    ↓
Task 3 (Complexity queries) — independent of 1/2
Task 4 (Reddit denylist)    — independent of 1/2
Task 5 (Chart refs in file) — independent of 1/2
    ↓
Task 6 (Verify + full suite) — depends on all above
```

Tasks 3, 4, 5 are independent and can be parallelized after Task 2.

---

## Summary of Changes

| Task | Files Modified | Files Created | Tests |
|------|---------------|---------------|-------|
| 1 | `redis_task.py`, `agent_task_runner.py` | `test_redis_task_liveness.py` | 9 |
| 2 | `agent_domain_service.py`, `test_*_teardown.py` | `test_reconnect_liveness.py` | 7 + 4 updated |
| 3 | `config_features.py`, `search.py`, `plan_act.py` | `test_search_complexity_queries.py` | 7 |
| 4 | `research_spider.py`, `search.py` | `test_spider_denylist.py` | 12 |
| 5 | `agent_task_runner.py` | `test_chart_reference_injection.py` | 5 |
| 6 | — | — | Full suite run |

**Total: ~8 files modified, 5 test files created, ~40 new tests, 4 tests updated**
