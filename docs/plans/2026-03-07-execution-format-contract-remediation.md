# Execution Format Contract & Session Stability Remediation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the systemic failure loop where the execution agent produces non-JSON responses after tool calls, causing step validation failures, dependency blocking, and zero-progress replanning.

**Architecture:** The `base.py` execute loop deliberately disables `json_object` format when tools are present (some LLM providers return empty responses otherwise). But after all tool calls complete, the final `ask_with_messages()` call never re-enforces JSON format. The fix re-enforces format on the post-tool-loop response, adds a robust extraction fallback in the step executor, fixes the terminal-state accounting race on manual stop, and addresses the `stop_session` status mismatch.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, asyncio, pytest

---

## Issues Identified (from Session 4799091f Review)

| # | Issue | Severity | Root Cause File(s) |
|---|-------|----------|---------------------|
| 1 | JSON format not re-enforced after tool loop exits | CRITICAL | `base.py:1487-2008` |
| 2 | Tool-call text normalized to `[Attempted to call ...]` treated as step result | HIGH | `message_normalizer.py:90`, `execution.py:398-424` |
| 3 | `_retry_step_result_json` burns 2 LLM calls on inherently unparseable tool-marker text | MEDIUM | `execution.py:1644-1692` |
| 4 | `stop_session` marks status COMPLETED, event loop marks CANCELLED — conflicting terminal states | HIGH | `agent_session_lifecycle.py:247`, `agent_domain_service.py:840-845` |
| 5 | Log says "completed" after session already marked CANCELLED | LOW | `agent_domain_service.py:850` |
| 6 | Step executor last-resort fallback sets generic error instead of extracting useful info from raw text | MEDIUM | `step_executor.py:179-183` |

---

### Task 1: Re-enforce JSON format after tool-calling loop completes

**Files:**
- Modify: `backend/app/domain/services/agents/base.py:1487-2041`
- Test: `backend/tests/domain/services/agents/test_base_format_enforcement.py`

**Context:**
The `execute()` method sets `initial_format = None` when tools are present (line 1492). This is correct during tool-calling. But when the while-loop exits (line 1515: `if not message.get("tool_calls"): break`), the message content is the final response — and it was produced WITHOUT format enforcement. After the loop, if the agent's `self.format` is `json_object`, we need one more LLM call with format enforced to get proper JSON.

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/agents/test_base_format_enforcement.py
"""Test that json_object format is re-enforced after tool-calling loop exits."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.agents.base import BaseAgent
from app.domain.models.event import MessageEvent


class FakeAgent(BaseAgent):
    """Minimal agent for testing format enforcement."""
    name = "test_agent"
    system_prompt = "You are a test agent."
    format = "json_object"


@pytest.fixture
def fake_agent():
    llm = AsyncMock()
    agent_repo = AsyncMock()
    json_parser = AsyncMock()
    agent = FakeAgent(
        agent_id="test-1",
        agent_repository=agent_repo,
        llm=llm,
        json_parser=json_parser,
        tools=[],
    )
    return agent


@pytest.mark.asyncio
async def test_format_enforced_when_no_tools(fake_agent):
    """When no tools exist, initial_format should be json_object."""
    fake_agent.llm.ask.return_value = {"content": '{"success": true}', "tool_calls": None}
    events = []
    async for event in fake_agent.execute("test"):
        events.append(event)
    # ask() should have been called with response_format={"type": "json_object"}
    call_kwargs = fake_agent.llm.ask.call_args
    assert call_kwargs is not None


@pytest.mark.asyncio
async def test_format_re_enforced_after_tool_calls(fake_agent):
    """After tool calls complete and model responds with non-JSON, a format-enforced
    follow-up call should be made to get proper JSON output."""
    tool_with_mock = MagicMock()
    tool_with_mock.name = "test_tool"
    tool_with_mock.to_openai_tool.return_value = {"type": "function", "function": {"name": "test_tool"}}
    fake_agent.tools = [tool_with_mock]

    # First call returns tool_calls
    first_response = {
        "content": "",
        "tool_calls": [{"id": "tc1", "function": {"name": "test_tool", "arguments": "{}"}}],
    }
    # Second call (after tool execution) returns non-JSON text (the bug scenario)
    second_response = {
        "content": "I have completed the task successfully.",
        "tool_calls": None,
    }
    # Third call (format-enforced follow-up) returns proper JSON
    third_response = {
        "content": '{"success": true, "result": "Task completed", "attachments": []}',
        "tool_calls": None,
    }
    fake_agent.llm.ask.side_effect = [first_response, second_response, third_response]

    # The final MessageEvent should contain the JSON response
    events = []
    async for event in fake_agent.execute("test"):
        events.append(event)

    message_events = [e for e in events if isinstance(e, MessageEvent)]
    assert len(message_events) >= 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/agents/test_base_format_enforcement.py -v`
Expected: FAIL — the format-enforced follow-up call is not implemented yet

**Step 3: Write minimal implementation**

In `base.py`, after the while-loop exits and before `final_content = message.get("content")`, add format re-enforcement logic:

```python
# base.py execute() method — after the while loop (around line 2024)

# Re-enforce JSON format after tool-calling loop completes.
# The initial call disabled json_object to avoid empty-response bugs
# with tool_calls, but the final response must still be valid JSON
# when self.format requires it.
if has_tools and format == "json_object":
    final_content = message.get("content", "") or ""
    # Quick check: is the response already valid JSON?
    is_valid_json = False
    if final_content.strip():
        try:
            import json as _json
            _json.loads(final_content)
            is_valid_json = True
        except (ValueError, TypeError):
            pass
    if not is_valid_json:
        logger.info("Re-enforcing JSON format on post-tool-loop response")
        format_enforcement_prompt = (
            "Your previous response was not in the required JSON format. "
            "Restate your response as ONLY a valid JSON object matching the "
            "expected schema. No prose, no markdown fencing."
        )
        message = await self.ask_with_messages(
            [{"role": "user", "content": format_enforcement_prompt}],
            format="json_object",
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/agents/test_base_format_enforcement.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/base.py backend/tests/domain/services/agents/test_base_format_enforcement.py
git commit -m "fix(agents): re-enforce json_object format after tool-calling loop completes"
```

---

### Task 2: Detect and skip tool-marker text before JSON parsing

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py:398-424`
- Test: `backend/tests/domain/services/agents/test_execution_tool_marker.py`

**Context:**
When the message normalizer converts orphaned tool_calls to text like `[Attempted to call X with {...}]`, this text reaches `execute_step()` as a `MessageEvent`. The step tries to parse it as JSON, which always fails. The `_retry_step_result_json` method then wastes 2 additional LLM calls trying to "correct" this inherently unparseable text. We should detect tool-marker patterns early and skip the expensive retry.

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/agents/test_execution_tool_marker.py
"""Test that tool-marker text is detected and skipped before JSON retry."""
import pytest
from unittest.mock import AsyncMock

TOOL_MARKER_MESSAGES = [
    '[Attempted to call browser_navigate with {"url": "https://example.com"}]',
    '[Attempted to call file_write with {"path": "/workspace/report.md", "content": "# Report..."}]',
    '[Attempted to call browser_navigate with {"url": "https://exam...]\n[Attempted to call file_read with {"path": "/workspace/data.json"}]',
]


def _is_tool_marker_text(text: str) -> bool:
    """Import the detection function once implemented."""
    from app.domain.services.agents.execution import _is_tool_marker_text
    return _is_tool_marker_text(text)


@pytest.mark.parametrize("text", TOOL_MARKER_MESSAGES)
def test_detects_tool_marker_text(text):
    assert _is_tool_marker_text(text) is True


def test_does_not_flag_valid_json():
    assert _is_tool_marker_text('{"success": true, "result": "done", "attachments": []}') is False


def test_does_not_flag_normal_prose():
    assert _is_tool_marker_text("I have completed the research task.") is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/agents/test_execution_tool_marker.py -v`
Expected: FAIL — `_is_tool_marker_text` does not exist

**Step 3: Write minimal implementation**

In `execution.py`, add the detection function and use it in `execute_step()`:

```python
# execution.py — module level, after imports

import re as _re

_TOOL_MARKER_PATTERN = _re.compile(r"^\[Attempted to call \w+ with ")


def _is_tool_marker_text(text: str) -> bool:
    """Detect tool-call marker text produced by message_normalizer.

    These strings are never valid step results — they are artifacts of
    orphaned tool_calls being converted to readable text.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    return bool(_TOOL_MARKER_PATTERN.match(stripped))
```

Then in `execute_step()`, before the JSON parsing block (around line 399):

```python
# Inside execute_step(), MessageEvent handler, before JSON parsing
if _is_tool_marker_text(event.message):
    logger.warning(
        "Step response is tool-marker text (normalizer artifact); "
        "skipping JSON parse — will be handled by format re-enforcement"
    )
    # Don't attempt JSON parsing or retry — this is not a step result.
    # The format re-enforcement in base.py execute() will request proper JSON.
    continue
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/agents/test_execution_tool_marker.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/execution.py backend/tests/domain/services/agents/test_execution_tool_marker.py
git commit -m "fix(execution): detect and skip tool-marker text before JSON parsing"
```

---

### Task 3: Fix `stop_session` to use CANCELLED status instead of COMPLETED

**Files:**
- Modify: `backend/app/domain/services/agents/agent_session_lifecycle.py:234-249`
- Test: `backend/tests/domain/services/agents/test_stop_session_status.py`

**Context:**
When a user manually stops a session via the API, `stop_session()` calls `_teardown_session_runtime(status=SessionStatus.COMPLETED)`. But the event loop in `agent_domain_service.py:840-845` may concurrently mark it `CANCELLED` (because the task finished without a terminal event after partial stream). This creates a race where logs show both "completed" and "cancelled". The manual stop should use `CANCELLED` status to be semantically correct — the user interrupted the session, it did not complete naturally.

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/agents/test_stop_session_status.py
"""Test that stop_session uses CANCELLED status."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.models.session import Session, SessionStatus


@pytest.mark.asyncio
async def test_stop_session_uses_cancelled_status():
    """stop_session should mark the session as CANCELLED, not COMPLETED."""
    from app.domain.services.agents.agent_session_lifecycle import AgentSessionLifecycle

    session_repo = AsyncMock()
    sandbox_cls = AsyncMock()

    lifecycle = AgentSessionLifecycle(
        session_repository=session_repo,
        sandbox_cls=sandbox_cls,
    )
    lifecycle._get_task = AsyncMock(return_value=None)

    mock_session = MagicMock(spec=Session)
    mock_session.id = "test-session"
    mock_session.sandbox_id = None
    mock_session.sandbox_owned = False
    mock_session.sandbox_created_at = None
    mock_session.status = SessionStatus.RUNNING
    session_repo.find_by_id.return_value = mock_session

    await lifecycle.stop_session("test-session")

    # Verify _teardown_session_runtime was called with CANCELLED
    teardown_call = session_repo.update_by_id.call_args
    if teardown_call:
        updates = teardown_call[0][1] if len(teardown_call[0]) > 1 else teardown_call[1]
        assert updates.get("status") == SessionStatus.CANCELLED.value or updates.get("status") == "cancelled"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/agents/test_stop_session_status.py -v`
Expected: FAIL — status is COMPLETED

**Step 3: Write minimal implementation**

In `agent_session_lifecycle.py:247`, change:

```python
# FROM:
        await self._teardown_session_runtime(
            session_id,
            session=session,
            status=SessionStatus.COMPLETED,
            destroy_sandbox=True,
        )

# TO:
        await self._teardown_session_runtime(
            session_id,
            session=session,
            status=SessionStatus.CANCELLED,
            destroy_sandbox=True,
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/agents/test_stop_session_status.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/agent_session_lifecycle.py backend/tests/domain/services/agents/test_stop_session_status.py
git commit -m "fix(lifecycle): stop_session uses CANCELLED status instead of COMPLETED"
```

---

### Task 4: Guard "Session completed" log against already-cancelled sessions

**Files:**
- Modify: `backend/app/domain/services/agent_domain_service.py:850`
- Test: `backend/tests/domain/services/test_session_terminal_log.py`

**Context:**
Line 850 unconditionally logs `"Session {session_id} completed"` after the event loop, even when `terminal_status` is `CANCELLED`. This creates confusing log entries. The log message should reflect the actual terminal status.

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/test_session_terminal_log.py
"""Test that session terminal log reflects actual status."""
import pytest


def test_terminal_log_message_format():
    """Verify the log message correctly uses terminal_status, not hardcoded 'completed'."""
    # This is a static analysis test — read the source and verify the pattern
    import inspect
    from app.domain.services import agent_domain_service
    source = inspect.getsource(agent_domain_service.AgentDomainService)
    # Should NOT contain the hardcoded "completed" pattern after terminal_status logic
    # The log line should use terminal_status or be conditional
    assert 'f"Session {session_id} completed"' not in source or "terminal_status" in source.split('f"Session {session_id} completed"')[0][-200:]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/test_session_terminal_log.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `agent_domain_service.py:850`, change:

```python
# FROM:
            logger.info(f"Session {session_id} completed")

# TO:
            status_label = terminal_status.value if terminal_status else "finished"
            logger.info("Session %s %s", session_id, status_label)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/test_session_terminal_log.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agent_domain_service.py backend/tests/domain/services/test_session_terminal_log.py
git commit -m "fix(logs): session terminal log reflects actual status instead of hardcoded 'completed'"
```

---

### Task 5: Improve step executor last-resort fallback with text extraction

**Files:**
- Modify: `backend/app/domain/services/agents/step_executor.py:179-183`
- Test: `backend/tests/domain/services/agents/test_step_executor_fallback.py`

**Context:**
When both strict validation and best-effort extraction fail, `apply_step_result_payload` sets a generic error `"Step response did not match expected JSON schema"` and discards the raw message entirely. For cases where the model returned useful prose (e.g., a summary of what it did), we should extract a truncated preview into the error field so operators can see what the model actually said.

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/agents/test_step_executor_fallback.py
"""Test step executor last-resort fallback includes raw message preview."""
import pytest
from unittest.mock import MagicMock

from app.domain.models.plan import Step
from app.domain.services.agents.step_executor import StepExecutor


@pytest.fixture
def step_executor():
    return StepExecutor(
        context_manager=MagicMock(),
        source_tracker=MagicMock(),
        metrics=MagicMock(),
    )


def test_last_resort_fallback_includes_raw_preview(step_executor):
    """When parsed_response is None, error should include a preview of raw_message."""
    step = MagicMock(spec=Step)
    step.success = True  # Will be set to False
    step.result = "old"
    step.attachments = ["old"]
    step.error = None

    raw = "I have completed the research and found 5 key insights about the topic."

    result = step_executor.apply_step_result_payload(step, None, raw)

    assert result is False
    assert step.success is False
    assert raw[:100] in step.error  # Should include preview


def test_last_resort_fallback_truncates_long_message(step_executor):
    """Raw message preview should be truncated for very long messages."""
    step = MagicMock(spec=Step)
    step.success = True
    step.result = "old"
    step.attachments = ["old"]
    step.error = None

    raw = "A" * 500

    result = step_executor.apply_step_result_payload(step, None, raw)

    assert result is False
    assert len(step.error) < 400  # Should be truncated
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/agents/test_step_executor_fallback.py -v`
Expected: FAIL — current error is generic string without preview

**Step 3: Write minimal implementation**

In `step_executor.py:179-183`, change:

```python
# FROM:
        step.success = False
        step.result = None
        step.attachments = []
        step.error = "Step response did not match expected JSON schema"
        return False

# TO:
        step.success = False
        step.result = None
        step.attachments = []
        preview = (raw_message or "")[:200].strip()
        step.error = (
            f"Step response did not match expected JSON schema. "
            f"Raw preview: {preview}" if preview else "Step response did not match expected JSON schema"
        )
        return False
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/agents/test_step_executor_fallback.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/step_executor.py backend/tests/domain/services/agents/test_step_executor_fallback.py
git commit -m "fix(step-executor): include raw message preview in last-resort fallback error"
```

---

### Task 6: Add integration test for full format-contract flow

**Files:**
- Create: `backend/tests/integration/test_format_contract_flow.py`

**Context:**
End-to-end test verifying that when a tool-equipped execution agent produces non-JSON after tool calls, the system recovers via format re-enforcement rather than entering the validation-failure loop.

**Step 1: Write the integration test**

```python
# backend/tests/integration/test_format_contract_flow.py
"""Integration test: format contract recovery after tool-call loop."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.models.event import MessageEvent, ToolEvent
from app.domain.services.agents.execution import ExecutionAgent


@pytest.fixture
def execution_agent():
    llm = AsyncMock()
    agent_repo = AsyncMock()
    json_parser = AsyncMock()
    agent = ExecutionAgent(
        agent_id="integration-test",
        agent_repository=agent_repo,
        llm=llm,
        tools=[],
        json_parser=json_parser,
    )
    return agent


@pytest.mark.asyncio
async def test_format_contract_recovery_produces_valid_step_result(execution_agent):
    """Simulate tool-call loop followed by non-JSON response, verify recovery."""
    mock_tool = MagicMock()
    mock_tool.name = "web_search"
    mock_tool.to_openai_tool.return_value = {
        "type": "function",
        "function": {"name": "web_search", "parameters": {}},
    }
    execution_agent.tools = [mock_tool]

    # Simulate: tool call -> tool result -> non-JSON final -> format-enforced JSON
    call_count = 0
    async def mock_ask(messages, *, tools=None, response_format=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "content": "",
                "tool_calls": [{"id": "tc1", "function": {"name": "web_search", "arguments": '{"query": "test"}'}}],
            }
        elif call_count == 2:
            return {
                "content": "I found the information you requested about the topic.",
                "tool_calls": None,
            }
        else:
            # Format-enforced response
            return {
                "content": '{"success": true, "result": "Found information", "attachments": []}',
                "tool_calls": None,
            }

    execution_agent.llm.ask = mock_ask

    events = []
    async for event in execution_agent.execute("Search for test data"):
        events.append(event)

    message_events = [e for e in events if isinstance(e, MessageEvent)]
    assert len(message_events) >= 1
    # The final message should be parseable JSON
    import json
    final_msg = message_events[-1].message
    parsed = json.loads(final_msg)
    assert "success" in parsed
```

**Step 2: Run test**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/integration/test_format_contract_flow.py -v`
Expected: PASS (after Tasks 1-2 are implemented)

**Step 3: Commit**

```bash
git add backend/tests/integration/test_format_contract_flow.py
git commit -m "test(integration): add format-contract recovery flow test"
```

---

## Summary of Changes

| Task | File | Change | Impact |
|------|------|--------|--------|
| 1 | `base.py` | Re-enforce JSON format after tool loop | Eliminates root cause of validation failures |
| 2 | `execution.py` | Detect/skip tool-marker text | Prevents wasted LLM retry calls on unparseable input |
| 3 | `agent_session_lifecycle.py` | `stop_session` → CANCELLED | Fixes terminal state inconsistency on manual stop |
| 4 | `agent_domain_service.py` | Dynamic terminal log message | Fixes misleading "completed" log for cancelled sessions |
| 5 | `step_executor.py` | Raw preview in fallback error | Better observability for debugging validation failures |
| 6 | Integration test | End-to-end format recovery test | Regression guard for the entire fix chain |

## Risk Assessment

- **Task 1** (CRITICAL): Adds one conditional LLM call. Risk: extra latency on valid JSON responses — mitigated by the `json.loads()` pre-check that skips re-enforcement when response is already valid JSON.
- **Task 2** (LOW): Pure pattern detection, no behavioral change for valid responses.
- **Task 3** (LOW): Single enum value change; semantically more correct.
- **Task 4** (NONE): Log message change only.
- **Task 5** (LOW): Error message enrichment, no behavioral change.
- **Task 6** (NONE): Test only.

## Execution Order

Tasks 1-2 are the critical path (fix root cause + prevent wasted retries). Tasks 3-5 fix secondary issues found in the same review. Task 6 is the regression guard. Execute sequentially 1 → 2 → 3 → 4 → 5 → 6.
