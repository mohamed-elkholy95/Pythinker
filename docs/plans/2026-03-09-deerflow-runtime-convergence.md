# DeerFlow Runtime Convergence — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Borrow DeerFlow's runtime ergonomics (ordered middleware pipeline, first-class delegation, session-scoped workspace, structured memory tiers) while preserving Pythinker's stronger reasoning, grounding, and quality-gate stack.

**Architecture:** A `LeadAgentRuntime` facade wraps the existing `PlanActFlow` state machine, replacing 31 ad-hoc injected collaborators with an ordered middleware pipeline. Delegation is unified into a single `delegate` tool. Workspace contracts replace hardcoded sandbox paths. A new `RESEARCH_TRACE` memory tier separates transient search breadcrumbs from durable project knowledge.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, asyncio, MongoDB, Qdrant (named vectors), Redis streams, pytest + pytest-asyncio

**DeerFlow Reference Files (read-only, do not modify):**
- `nanobot-main/deer-flow-main/backend/src/agents/lead_agent/agent.py` — middleware pipeline shape
- `nanobot-main/deer-flow-main/backend/src/agents/middlewares/` — all 8 middleware implementations
- `nanobot-main/deer-flow-main/backend/src/tools/builtins/task_tool.py` — delegation tool
- `nanobot-main/deer-flow-main/backend/src/agents/thread_state.py` — session-scoped state
- `nanobot-main/deer-flow-main/backend/src/channels/manager.py` — config overlay pattern

---

## Phase 0 — P0: Core Runtime Facade

### Task 1: Agent Runtime Middleware Protocol

> Define the middleware abstraction that all runtime hooks will implement. Borrows DeerFlow's
> `AgentMiddleware` hook shape but adds Pythinker-specific hooks for tool dispatch and quality
> gates.

**Files:**
- Create: `backend/app/domain/services/runtime/middleware.py`
- Test: `backend/tests/domain/services/runtime/test_middleware.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/runtime/test_middleware.py
"""Tests for the agent runtime middleware protocol and pipeline."""
import pytest
from unittest.mock import AsyncMock

from app.domain.services.runtime.middleware import (
    RuntimeMiddleware,
    RuntimePipeline,
    RuntimeContext,
    RuntimeHook,
)


class RecordingMiddleware(RuntimeMiddleware):
    """Test middleware that records which hooks fire."""

    def __init__(self, name: str, log: list[str]):
        self._name = name
        self._log = log

    async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self._name}:before_run")
        return ctx

    async def after_run(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self._name}:after_run")
        return ctx

    async def before_step(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self._name}:before_step")
        return ctx

    async def after_step(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self._name}:after_step")
        return ctx

    async def before_tool(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self._name}:before_tool")
        return ctx

    async def after_tool(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self._name}:after_tool")
        return ctx


@pytest.mark.asyncio
class TestRuntimePipeline:
    async def test_hooks_execute_in_order(self):
        log: list[str] = []
        m1 = RecordingMiddleware("first", log)
        m2 = RecordingMiddleware("second", log)
        pipeline = RuntimePipeline(middlewares=[m1, m2])

        ctx = RuntimeContext(session_id="test-1", agent_id="a-1")
        await pipeline.run_hook(RuntimeHook.BEFORE_RUN, ctx)

        assert log == ["first:before_run", "second:before_run"]

    async def test_context_flows_through_chain(self):
        class InjectMiddleware(RuntimeMiddleware):
            async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
                ctx.metadata["injected"] = True
                return ctx

        pipeline = RuntimePipeline(middlewares=[InjectMiddleware()])
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        result = await pipeline.run_hook(RuntimeHook.BEFORE_RUN, ctx)

        assert result.metadata["injected"] is True

    async def test_empty_pipeline_passes_through(self):
        pipeline = RuntimePipeline(middlewares=[])
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        result = await pipeline.run_hook(RuntimeHook.BEFORE_RUN, ctx)
        assert result.session_id == "s-1"

    async def test_middleware_error_propagates(self):
        class BrokenMiddleware(RuntimeMiddleware):
            async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
                raise ValueError("broken")

        pipeline = RuntimePipeline(middlewares=[BrokenMiddleware()])
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        with pytest.raises(ValueError, match="broken"):
            await pipeline.run_hook(RuntimeHook.BEFORE_RUN, ctx)

    async def test_all_six_hooks_exist(self):
        hooks = {h.value for h in RuntimeHook}
        assert hooks == {
            "before_run", "after_run",
            "before_step", "after_step",
            "before_tool", "after_tool",
        }
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.services.runtime'`

**Step 3: Write minimal implementation**

```python
# backend/app/domain/services/runtime/__init__.py
"""Agent runtime middleware pipeline — DeerFlow-inspired ordered hooks."""

# backend/app/domain/services/runtime/middleware.py
"""
Core middleware protocol for the LeadAgentRuntime pipeline.

Borrows DeerFlow's ordered-middleware shape (agent.py:207-251) but adds
Pythinker-specific hooks: before_tool/after_tool for quality gates, and
before_step/after_step for context synthesis and checkpoint management.

Hook execution order mirrors construction order (first-added runs first).
Each hook receives a mutable RuntimeContext and returns it (possibly enriched).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class RuntimeHook(str, enum.Enum):
    BEFORE_RUN = "before_run"
    AFTER_RUN = "after_run"
    BEFORE_STEP = "before_step"
    AFTER_STEP = "after_step"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"


@dataclass
class RuntimeContext:
    """Mutable bag passed through the middleware chain."""

    session_id: str
    agent_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    workspace: dict[str, str] = field(default_factory=dict)  # virtual paths
    artifacts: list[str] = field(default_factory=list)
    tools: list[Any] = field(default_factory=list)
    events: list[Any] = field(default_factory=list)  # buffered events to yield


class RuntimeMiddleware:
    """Base class. Override only the hooks you need; defaults are pass-through."""

    async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx

    async def after_run(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx

    async def before_step(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx

    async def after_step(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx

    async def before_tool(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx

    async def after_tool(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx


class RuntimePipeline:
    """Executes an ordered list of middlewares for a given hook."""

    __slots__ = ("_middlewares",)

    def __init__(self, middlewares: list[RuntimeMiddleware]) -> None:
        self._middlewares = list(middlewares)

    async def run_hook(self, hook: RuntimeHook, ctx: RuntimeContext) -> RuntimeContext:
        for mw in self._middlewares:
            handler = getattr(mw, hook.value)
            ctx = await handler(ctx)
        return ctx
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_middleware.py -v`
Expected: 5 PASSED

**Step 5: Commit**

```bash
git add backend/app/domain/services/runtime/__init__.py \
        backend/app/domain/services/runtime/middleware.py \
        backend/tests/domain/services/runtime/__init__.py \
        backend/tests/domain/services/runtime/test_middleware.py
git commit -m "feat(runtime): add middleware protocol and pipeline for LeadAgentRuntime"
```

---

### Task 2: Workspace Contract Middleware (replace hardcoded paths)

> Replace `TASK_STATE_PATH = "/home/ubuntu/task_state.md"` (task_state_manager.py:23) with
> session-scoped virtual paths. Borrows DeerFlow's ThreadDataMiddleware shape
> (thread_data_middleware.py:17) but keeps Pythinker's richer TaskState model.

**Files:**
- Create: `backend/app/domain/services/runtime/workspace_middleware.py`
- Modify: `backend/app/domain/services/agents/task_state_manager.py:23` — remove hardcoded path
- Test: `backend/tests/domain/services/runtime/test_workspace_middleware.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/runtime/test_workspace_middleware.py
"""Tests for workspace contract middleware."""
import pytest

from app.domain.services.runtime.middleware import RuntimeContext, RuntimeHook
from app.domain.services.runtime.workspace_middleware import (
    WorkspaceMiddleware,
    WorkspaceContract,
)


@pytest.mark.asyncio
class TestWorkspaceMiddleware:
    async def test_before_run_populates_workspace_paths(self):
        mw = WorkspaceMiddleware(base_dir="/sessions")
        ctx = RuntimeContext(session_id="abc-123", agent_id="a-1")

        result = await mw.before_run(ctx)

        assert result.workspace["workspace"] == "/sessions/abc-123/workspace"
        assert result.workspace["uploads"] == "/sessions/abc-123/uploads"
        assert result.workspace["outputs"] == "/sessions/abc-123/outputs"
        assert result.workspace["task_state"] == "/sessions/abc-123/workspace/task_state.md"
        assert result.workspace["scratchpad"] == "/sessions/abc-123/workspace/scratchpad.md"

    async def test_contract_is_serializable(self):
        contract = WorkspaceContract(
            session_id="abc-123",
            workspace="/sessions/abc-123/workspace",
            uploads="/sessions/abc-123/uploads",
            outputs="/sessions/abc-123/outputs",
        )
        d = contract.model_dump()
        assert d["session_id"] == "abc-123"
        restored = WorkspaceContract.model_validate(d)
        assert restored.task_state_path == "/sessions/abc-123/workspace/task_state.md"

    async def test_contract_prompt_block(self):
        contract = WorkspaceContract(
            session_id="s-1",
            workspace="/w",
            uploads="/u",
            outputs="/o",
        )
        block = contract.to_prompt_block()
        assert "<workspace_contract>" in block
        assert "/w" in block
        assert "/u" in block
        assert "/o" in block
        assert "</workspace_contract>" in block

    async def test_metadata_includes_contract(self):
        mw = WorkspaceMiddleware(base_dir="/sessions")
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")

        result = await mw.before_run(ctx)

        assert "workspace_contract" in result.metadata
        assert isinstance(result.metadata["workspace_contract"], WorkspaceContract)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_workspace_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/app/domain/services/runtime/workspace_middleware.py
"""
Session-scoped workspace contract middleware.

Replaces the hardcoded TASK_STATE_PATH = "/home/ubuntu/task_state.md"
(task_state_manager.py:23) with session-scoped virtual paths.

Borrows DeerFlow's ThreadDataMiddleware shape (thread_data_middleware.py:17):
every session gets workspace/, uploads/, outputs/ under a root keyed by session_id.
The agent sees these paths in a <workspace_contract> prompt block and all tools
resolve paths relative to them.
"""
from __future__ import annotations

from pydantic import BaseModel, computed_field

from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware


class WorkspaceContract(BaseModel):
    """Immutable workspace paths for a session. Injected into system prompt."""

    session_id: str
    workspace: str
    uploads: str
    outputs: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def task_state_path(self) -> str:
        return f"{self.workspace}/task_state.md"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def scratchpad_path(self) -> str:
        return f"{self.workspace}/scratchpad.md"

    def to_prompt_block(self) -> str:
        return (
            "<workspace_contract>\n"
            f"  workspace: {self.workspace}\n"
            f"  uploads:   {self.uploads}\n"
            f"  outputs:   {self.outputs}\n"
            f"  task_state: {self.task_state_path}\n"
            f"  scratchpad: {self.scratchpad_path}\n"
            "</workspace_contract>"
        )


class WorkspaceMiddleware(RuntimeMiddleware):
    """Populates session-scoped workspace paths in RuntimeContext.

    Runs at position 1 (first middleware) — all subsequent middlewares
    can read ctx.workspace to resolve paths.
    """

    def __init__(self, base_dir: str = "/home/ubuntu") -> None:
        self._base_dir = base_dir.rstrip("/")

    async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
        root = f"{self._base_dir}/{ctx.session_id}"
        contract = WorkspaceContract(
            session_id=ctx.session_id,
            workspace=f"{root}/workspace",
            uploads=f"{root}/uploads",
            outputs=f"{root}/outputs",
        )
        ctx.workspace = {
            "workspace": contract.workspace,
            "uploads": contract.uploads,
            "outputs": contract.outputs,
            "task_state": contract.task_state_path,
            "scratchpad": contract.scratchpad_path,
        }
        ctx.metadata["workspace_contract"] = contract
        return ctx
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_workspace_middleware.py -v`
Expected: 4 PASSED

**Step 5: Wire TaskStateManager to accept workspace path**

Modify `backend/app/domain/services/agents/task_state_manager.py`:

- At line 23, change:
  ```python
  # OLD:
  TASK_STATE_PATH = "/home/ubuntu/task_state.md"
  ```
  to:
  ```python
  # NEW:
  DEFAULT_TASK_STATE_PATH = "/home/ubuntu/task_state.md"
  ```

- In the `TaskStateManager.__init__` (around line 270), add an optional `task_state_path` parameter:
  ```python
  def __init__(self, sandbox: SandboxPort, task_state_path: str = DEFAULT_TASK_STATE_PATH):
      ...
      self._task_state_path = task_state_path
  ```

- Replace all references to `TASK_STATE_PATH` inside `TaskStateManager` methods with `self._task_state_path`.

**Step 6: Write test for parameterized TaskStateManager**

```python
# Add to existing tests/domain/services/agents/test_task_state_manager.py
@pytest.mark.asyncio
async def test_custom_task_state_path(mock_sandbox):
    mgr = TaskStateManager(sandbox=mock_sandbox, task_state_path="/custom/state.md")
    mgr._state = TaskState(objective="test")
    await mgr.save_to_sandbox()
    mock_sandbox.file_write.assert_called_once()
    call_args = mock_sandbox.file_write.call_args
    assert call_args[0][0] == "/custom/state.md"
```

**Step 7: Run full test suite for task_state_manager**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/agents/test_task_state_manager.py -v`
Expected: All PASSED

**Step 8: Commit**

```bash
git add backend/app/domain/services/runtime/workspace_middleware.py \
        backend/tests/domain/services/runtime/test_workspace_middleware.py \
        backend/app/domain/services/agents/task_state_manager.py \
        backend/tests/domain/services/agents/test_task_state_manager.py
git commit -m "feat(runtime): add workspace contract middleware, parameterize TaskStateManager paths"
```

---

### Task 3: Clarification Gate Middleware

> Add human-in-the-loop clarification as a first-class runtime hook. Borrows DeerFlow's
> ClarificationMiddleware (clarification_middleware.py:20-173) pattern: typed question →
> interrupt → resume. Pythinker already has `feature_hitl_enabled` and `WaitEvent` — this
> wires them into the middleware pipeline.

**Files:**
- Create: `backend/app/domain/services/runtime/clarification_middleware.py`
- Create: `backend/app/domain/models/clarification.py`
- Test: `backend/tests/domain/services/runtime/test_clarification_middleware.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/runtime/test_clarification_middleware.py
"""Tests for clarification gate middleware."""
import pytest

from app.domain.models.clarification import (
    ClarificationType,
    ClarificationRequest,
)
from app.domain.services.runtime.clarification_middleware import (
    ClarificationMiddleware,
)
from app.domain.services.runtime.middleware import RuntimeContext


@pytest.mark.asyncio
class TestClarificationMiddleware:
    async def test_no_pending_clarification_passes_through(self):
        mw = ClarificationMiddleware()
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")

        result = await mw.before_step(ctx)

        assert result is ctx
        assert len(result.events) == 0

    async def test_pending_clarification_emits_wait_event(self):
        mw = ClarificationMiddleware()
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        ctx.metadata["pending_clarification"] = ClarificationRequest(
            question="Which product should I research?",
            clarification_type=ClarificationType.MISSING_INFO,
            options=["Product A", "Product B"],
        )

        result = await mw.before_step(ctx)

        assert result.metadata.get("awaiting_clarification") is True
        assert len(result.events) == 1
        event = result.events[0]
        assert event["type"] == "clarification"
        assert "Which product" in event["question"]
        assert event["options"] == ["Product A", "Product B"]

    async def test_all_clarification_types(self):
        for ct in ClarificationType:
            req = ClarificationRequest(
                question="test",
                clarification_type=ct,
            )
            assert req.clarification_type == ct

    async def test_clarification_request_format(self):
        req = ClarificationRequest(
            question="Choose an approach",
            clarification_type=ClarificationType.APPROACH_CHOICE,
            context="User wants a comparison report",
            options=["Deep analysis", "Quick summary"],
        )
        formatted = req.format()
        assert "Choose an approach" in formatted
        assert "1. Deep analysis" in formatted
        assert "2. Quick summary" in formatted
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_clarification_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write domain model**

```python
# backend/app/domain/models/clarification.py
"""
Typed clarification requests for human-in-the-loop interrupts.

Borrows DeerFlow's 5-type clarification system (clarification_middleware.py:46-89)
but integrates with Pythinker's existing WaitEvent and feature_hitl_enabled flag.
"""
from __future__ import annotations

import enum

from pydantic import BaseModel


class ClarificationType(str, enum.Enum):
    MISSING_INFO = "missing_info"
    AMBIGUOUS_REQUIREMENT = "ambiguous_requirement"
    APPROACH_CHOICE = "approach_choice"
    RISK_CONFIRMATION = "risk_confirmation"
    SUGGESTION = "suggestion"


_TYPE_ICONS = {
    ClarificationType.MISSING_INFO: "[?]",
    ClarificationType.AMBIGUOUS_REQUIREMENT: "[~]",
    ClarificationType.APPROACH_CHOICE: "[>]",
    ClarificationType.RISK_CONFIRMATION: "[!]",
    ClarificationType.SUGGESTION: "[*]",
}


class ClarificationRequest(BaseModel):
    """A typed question the agent needs answered before proceeding."""

    question: str
    clarification_type: ClarificationType
    context: str | None = None
    options: list[str] | None = None

    def format(self) -> str:
        icon = _TYPE_ICONS.get(self.clarification_type, "")
        parts = [f"{icon} {self.question}"]
        if self.context:
            parts.insert(0, f"Context: {self.context}")
        if self.options:
            for i, opt in enumerate(self.options, 1):
                parts.append(f"  {i}. {opt}")
        return "\n".join(parts)
```

**Step 4: Write middleware implementation**

```python
# backend/app/domain/services/runtime/clarification_middleware.py
"""
Clarification gate middleware.

When the agent (or a prior middleware) sets ctx.metadata["pending_clarification"]
to a ClarificationRequest, this middleware:
1. Emits a clarification event (rendered as a WaitEvent in the SSE stream)
2. Sets ctx.metadata["awaiting_clarification"] = True
3. The outer runtime loop detects this flag and suspends execution

On resume (user responds), the runtime clears the flag and injects the
user's answer into the step context.
"""
from __future__ import annotations

from app.domain.models.clarification import ClarificationRequest
from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware


class ClarificationMiddleware(RuntimeMiddleware):
    """Intercepts pending clarification requests and emits wait events.

    Pipeline position: after workspace, before execution-related middlewares.
    """

    async def before_step(self, ctx: RuntimeContext) -> RuntimeContext:
        pending: ClarificationRequest | None = ctx.metadata.get("pending_clarification")
        if pending is None:
            return ctx

        ctx.metadata["awaiting_clarification"] = True
        ctx.events.append({
            "type": "clarification",
            "question": pending.question,
            "clarification_type": pending.clarification_type.value,
            "context": pending.context,
            "options": pending.options,
            "formatted": pending.format(),
        })
        # Clear the pending request so it doesn't re-trigger
        ctx.metadata.pop("pending_clarification", None)
        return ctx
```

**Step 5: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_clarification_middleware.py -v`
Expected: 4 PASSED

**Step 6: Commit**

```bash
git add backend/app/domain/models/clarification.py \
        backend/app/domain/services/runtime/clarification_middleware.py \
        backend/tests/domain/services/runtime/test_clarification_middleware.py
git commit -m "feat(runtime): add clarification gate middleware with typed question model"
```

---

### Task 4: Dangling Tool Call Recovery Middleware

> Borrows DeerFlow's DanglingToolCallMiddleware (dangling_tool_call_middleware.py:28-110)
> to sanitize conversation history after user cancellation. Prevents the crash-after-cancel
> bug where orphaned tool_calls cause "invalid message sequence" errors.

**Files:**
- Create: `backend/app/domain/services/runtime/dangling_tool_middleware.py`
- Test: `backend/tests/domain/services/runtime/test_dangling_tool_middleware.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/runtime/test_dangling_tool_middleware.py
"""Tests for dangling tool call recovery middleware."""
import pytest

from app.domain.services.runtime.dangling_tool_middleware import (
    DanglingToolCallMiddleware,
    sanitize_tool_history,
)


class TestSanitizeToolHistory:
    def test_no_dangling_calls_unchanged(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc-1", "function": {"name": "search", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "tc-1", "content": "results"},
            {"role": "assistant", "content": "Here are the results."},
        ]
        result = sanitize_tool_history(messages)
        assert len(result) == 4

    def test_dangling_call_gets_placeholder(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc-1", "function": {"name": "search", "arguments": "{}"}},
                {"id": "tc-2", "function": {"name": "browse", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "tc-1", "content": "results"},
            # tc-2 is dangling — no tool message
        ]
        result = sanitize_tool_history(messages)
        assert len(result) == 5  # original 3 + 1 injected placeholder
        placeholder = result[3]
        assert placeholder["role"] == "tool"
        assert placeholder["tool_call_id"] == "tc-2"
        assert "[Interrupted]" in placeholder["content"]

    def test_multiple_dangling_across_messages(self):
        messages = [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc-1", "function": {"name": "a", "arguments": "{}"}},
            ]},
            # no tool response at all
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc-2", "function": {"name": "b", "arguments": "{}"}},
            ]},
        ]
        result = sanitize_tool_history(messages)
        tool_msgs = [m for m in result if m["role"] == "tool"]
        assert len(tool_msgs) == 2
        assert all("[Interrupted]" in m["content"] for m in tool_msgs)

    def test_empty_messages_returns_empty(self):
        assert sanitize_tool_history([]) == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_dangling_tool_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# backend/app/domain/services/runtime/dangling_tool_middleware.py
"""
Dangling tool call recovery middleware.

Borrows DeerFlow's DanglingToolCallMiddleware (dangling_tool_call_middleware.py:28-110).
After user cancellation or error recovery, the conversation history may contain
AIMessages with tool_calls that never received ToolMessage responses. This
middleware scans for these orphans and injects synthetic placeholders so the
next LLM call receives a valid message sequence.
"""
from __future__ import annotations

from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware

_PLACEHOLDER = "[Interrupted] Tool call was cancelled and did not return a result."


def sanitize_tool_history(messages: list[dict]) -> list[dict]:
    """Insert placeholder tool messages for any dangling tool calls.

    Algorithm (mirrors DeerFlow's _build_patched_messages):
    1. Collect all existing tool_call_ids from tool messages.
    2. For each assistant message with tool_calls, check if every call_id
       has a corresponding tool message.
    3. If not, insert a synthetic tool message immediately after the
       assistant message.
    """
    if not messages:
        return []

    existing_tool_ids: set[str] = {
        m["tool_call_id"]
        for m in messages
        if m.get("role") == "tool" and "tool_call_id" in m
    }

    result: list[dict] = []
    for msg in messages:
        result.append(msg)
        if msg.get("role") != "assistant" or not msg.get("tool_calls"):
            continue
        for tc in msg["tool_calls"]:
            tc_id = tc.get("id", "")
            if tc_id and tc_id not in existing_tool_ids:
                result.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": _PLACEHOLDER,
                })
                existing_tool_ids.add(tc_id)

    return result


class DanglingToolCallMiddleware(RuntimeMiddleware):
    """Sanitizes message history before each step to handle interrupted tool calls.

    Pipeline position: early (after workspace, before execution).
    """

    async def before_step(self, ctx: RuntimeContext) -> RuntimeContext:
        history = ctx.metadata.get("message_history")
        if history and isinstance(history, list):
            ctx.metadata["message_history"] = sanitize_tool_history(history)
        return ctx
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_dangling_tool_middleware.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add backend/app/domain/services/runtime/dangling_tool_middleware.py \
        backend/tests/domain/services/runtime/test_dangling_tool_middleware.py
git commit -m "feat(runtime): add dangling tool call recovery middleware"
```

---

### Task 5: Unified Delegate Tool

> Package CoordinatorFlow (coordinator_flow.py:68), WideResearchFlow (wide_research.py:91),
> and SpawnTool (spawn_tool.py:39) into a single `delegate` tool with typed roles, concurrency
> caps, and streamed child progress. Borrows DeerFlow's task_tool pattern (task_tool.py:21)
> with polling + stream events.

**Files:**
- Create: `backend/app/domain/services/tools/delegate_tool.py`
- Create: `backend/app/domain/models/delegation.py`
- Test: `backend/tests/domain/services/tools/test_delegate_tool.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/tools/test_delegate_tool.py
"""Tests for the unified delegate tool."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.models.delegation import (
    DelegateRequest,
    DelegateRole,
    DelegateResult,
    DelegateStatus,
)
from app.domain.services.tools.delegate_tool import DelegateTool


@pytest.mark.asyncio
class TestDelegateTool:
    def _make_tool(self, max_concurrent: int = 3) -> DelegateTool:
        return DelegateTool(
            subagent_manager=AsyncMock(),
            research_flow_factory=AsyncMock(),
            max_concurrent=max_concurrent,
            event_sink=AsyncMock(),
        )

    async def test_rejects_empty_task(self):
        tool = self._make_tool()
        req = DelegateRequest(task="", role=DelegateRole.RESEARCHER)
        result = await tool.execute(req)
        assert result.status == DelegateStatus.REJECTED
        assert "empty" in result.error.lower()

    async def test_rejects_over_concurrency_cap(self):
        tool = self._make_tool(max_concurrent=2)
        tool._subagent_manager.get_running_count = AsyncMock(return_value=2)
        req = DelegateRequest(task="do something", role=DelegateRole.EXECUTOR)
        result = await tool.execute(req)
        assert result.status == DelegateStatus.REJECTED
        assert "concurrent" in result.error.lower()

    async def test_researcher_role_routes_to_research_flow(self):
        tool = self._make_tool()
        tool._subagent_manager.get_running_count = AsyncMock(return_value=0)
        mock_flow = AsyncMock()
        mock_flow.execute_streaming = AsyncMock(return_value=AsyncMock(
            __aiter__=AsyncMock(return_value=iter([])),
        ))
        tool._research_flow_factory = AsyncMock(return_value=mock_flow)
        req = DelegateRequest(
            task="Research AI trends",
            role=DelegateRole.RESEARCHER,
            search_types=["INFO", "NEWS"],
        )
        result = await tool.execute(req)
        assert result.status in (DelegateStatus.COMPLETED, DelegateStatus.STARTED)

    async def test_all_roles_defined(self):
        roles = {r.value for r in DelegateRole}
        assert "researcher" in roles
        assert "executor" in roles
        assert "coder" in roles
        assert "browser" in roles

    async def test_delegate_request_has_timeout(self):
        req = DelegateRequest(task="test", role=DelegateRole.EXECUTOR)
        assert req.timeout_seconds == 900  # 15 min default
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/tools/test_delegate_tool.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write domain model**

```python
# backend/app/domain/models/delegation.py
"""
Delegation model for the unified delegate tool.

Combines the typed-role pattern from DeerFlow's task_tool (task_tool.py:21)
with Pythinker's AgentType registry (agent_types.py:52).
"""
from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class DelegateRole(str, enum.Enum):
    """Available delegation roles. Maps to Pythinker's AgentType."""
    RESEARCHER = "researcher"
    EXECUTOR = "executor"
    CODER = "coder"
    BROWSER = "browser"
    ANALYST = "analyst"
    WRITER = "writer"


class DelegateStatus(str, enum.Enum):
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    REJECTED = "rejected"


class DelegateRequest(BaseModel):
    """What the LLM passes to the delegate tool."""
    task: str
    role: DelegateRole
    label: str = ""
    search_types: list[str] | None = None  # for RESEARCHER role
    timeout_seconds: int = Field(default=900, ge=30, le=3600)
    max_turns: int = Field(default=50, ge=1, le=200)


class DelegateResult(BaseModel):
    """What the delegate tool returns."""
    task_id: str = ""
    status: DelegateStatus
    result: str | None = None
    error: str | None = None
```

**Step 4: Write tool implementation**

```python
# backend/app/domain/services/tools/delegate_tool.py
"""
Unified delegate tool — single agent-facing interface for all delegation.

Replaces the need for the LLM to know about SpawnTool, CoordinatorFlow,
and WideResearchFlow separately. Routes by DelegateRole:
- RESEARCHER → WideResearchFlow (parallel search)
- EXECUTOR/CODER/BROWSER/ANALYST/WRITER → SubagentManager.spawn()

Borrows DeerFlow's task_tool pattern: typed roles, concurrency cap,
streamed progress events via event_sink callback.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Awaitable

from app.domain.models.delegation import (
    DelegateRequest,
    DelegateResult,
    DelegateRole,
    DelegateStatus,
)


class DelegateTool:
    """First-class delegation tool for the agent."""

    def __init__(
        self,
        subagent_manager: Any,  # SubagentManagerProtocol
        research_flow_factory: Callable[..., Awaitable[Any]] | None = None,
        max_concurrent: int = 3,
        event_sink: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        self._subagent_manager = subagent_manager
        self._research_flow_factory = research_flow_factory
        self._max_concurrent = max_concurrent
        self._event_sink = event_sink

    async def execute(self, request: DelegateRequest) -> DelegateResult:
        # Guard: empty task
        if not request.task.strip():
            return DelegateResult(
                status=DelegateStatus.REJECTED,
                error="Empty task description — nothing to delegate.",
            )

        # Guard: concurrency cap
        running = await self._subagent_manager.get_running_count()
        if running >= self._max_concurrent:
            return DelegateResult(
                status=DelegateStatus.REJECTED,
                error=f"Concurrent delegation limit reached ({self._max_concurrent}). "
                      f"Wait for a running task to complete.",
            )

        task_id = str(uuid.uuid4())[:12]

        # Emit started event
        if self._event_sink:
            await self._event_sink({
                "type": "delegate_started",
                "task_id": task_id,
                "role": request.role.value,
                "label": request.label or request.task[:60],
            })

        # Route by role
        if request.role == DelegateRole.RESEARCHER and self._research_flow_factory:
            return await self._execute_research(task_id, request)

        return await self._execute_subagent(task_id, request)

    async def _execute_research(
        self, task_id: str, request: DelegateRequest
    ) -> DelegateResult:
        try:
            flow = await self._research_flow_factory(
                topic=request.task,
                search_types=request.search_types,
            )
            # The flow is expected to have execute_streaming() or execute()
            if hasattr(flow, "execute_streaming"):
                async for event in flow.execute_streaming():
                    if self._event_sink:
                        await self._event_sink({
                            "type": "delegate_progress",
                            "task_id": task_id,
                            **event if isinstance(event, dict) else {"data": str(event)},
                        })
            elif hasattr(flow, "execute"):
                await flow.execute()

            return DelegateResult(
                task_id=task_id,
                status=DelegateStatus.COMPLETED,
                result="Research delegation completed.",
            )
        except Exception as e:
            return DelegateResult(
                task_id=task_id,
                status=DelegateStatus.FAILED,
                error=f"{type(e).__name__}: {e}",
            )

    async def _execute_subagent(
        self, task_id: str, request: DelegateRequest
    ) -> DelegateResult:
        try:
            spawn_id = await self._subagent_manager.spawn(
                task=request.task,
                label=request.label or f"{request.role.value}:{task_id}",
            )
            return DelegateResult(
                task_id=spawn_id or task_id,
                status=DelegateStatus.STARTED,
                result=f"Delegated to {request.role.value} agent.",
            )
        except Exception as e:
            return DelegateResult(
                task_id=task_id,
                status=DelegateStatus.FAILED,
                error=f"{type(e).__name__}: {e}",
            )
```

**Step 5: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/tools/test_delegate_tool.py -v`
Expected: 5 PASSED

**Step 6: Commit**

```bash
git add backend/app/domain/models/delegation.py \
        backend/app/domain/services/tools/delegate_tool.py \
        backend/tests/domain/services/tools/test_delegate_tool.py
git commit -m "feat(tools): add unified delegate tool with typed roles and concurrency cap"
```

---

### Task 6: RESEARCH_TRACE Memory Tier

> Separate transient search breadcrumbs (URLs, queries, snippets) from durable project
> knowledge in long-term memory. Create an expiry-based trace store that SourceTracker
> writes to. Only distilled outcomes feed into MemoryService and KnowledgeTransfer.

**Files:**
- Create: `backend/app/domain/models/research_trace.py`
- Create: `backend/app/domain/services/research_trace_store.py`
- Modify: `backend/app/domain/services/agents/source_tracker.py` — add trace emission hook
- Test: `backend/tests/domain/services/test_research_trace_store.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/test_research_trace_store.py
"""Tests for the RESEARCH_TRACE memory tier."""
import pytest
import time

from app.domain.models.research_trace import (
    TraceEntry,
    TraceType,
    TraceTier,
)
from app.domain.services.research_trace_store import ResearchTraceStore


@pytest.mark.asyncio
class TestResearchTraceStore:
    async def test_store_and_retrieve_trace(self):
        store = ResearchTraceStore(ttl_seconds=3600)
        entry = TraceEntry(
            session_id="s-1",
            trace_type=TraceType.SEARCH_QUERY,
            content="best laptops 2026",
            source_tool="info_search_web",
        )
        await store.add(entry)
        traces = await store.get_session_traces("s-1")
        assert len(traces) == 1
        assert traces[0].content == "best laptops 2026"

    async def test_expired_traces_excluded(self):
        store = ResearchTraceStore(ttl_seconds=0)  # immediate expiry
        entry = TraceEntry(
            session_id="s-1",
            trace_type=TraceType.URL_VISITED,
            content="https://example.com",
        )
        await store.add(entry)
        time.sleep(0.01)
        traces = await store.get_session_traces("s-1")
        assert len(traces) == 0

    async def test_distill_returns_only_outcomes(self):
        store = ResearchTraceStore(ttl_seconds=3600)
        # Add transient traces
        await store.add(TraceEntry(
            session_id="s-1",
            trace_type=TraceType.SEARCH_QUERY,
            content="laptop reviews",
        ))
        await store.add(TraceEntry(
            session_id="s-1",
            trace_type=TraceType.URL_VISITED,
            content="https://reviews.com/laptops",
        ))
        # Add an outcome trace
        await store.add(TraceEntry(
            session_id="s-1",
            trace_type=TraceType.DISTILLED_OUTCOME,
            content="Top laptops: MacBook Pro M5, ThinkPad X1",
            tier=TraceTier.DURABLE,
        ))
        outcomes = await store.get_distilled_outcomes("s-1")
        assert len(outcomes) == 1
        assert "MacBook Pro" in outcomes[0].content

    async def test_trace_types_cover_source_tracker_events(self):
        types = {t.value for t in TraceType}
        assert "search_query" in types
        assert "url_visited" in types
        assert "search_snippet" in types
        assert "distilled_outcome" in types

    async def test_clear_session_traces(self):
        store = ResearchTraceStore(ttl_seconds=3600)
        await store.add(TraceEntry(
            session_id="s-1",
            trace_type=TraceType.SEARCH_QUERY,
            content="test",
        ))
        await store.clear_session("s-1")
        assert len(await store.get_session_traces("s-1")) == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/test_research_trace_store.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write domain model**

```python
# backend/app/domain/models/research_trace.py
"""
RESEARCH_TRACE memory tier model.

Separates transient search breadcrumbs from durable project knowledge.
Transient traces (URLs, queries, snippets) have TTL-based expiry.
Only DISTILLED_OUTCOME entries are promoted to long-term MemoryService.
"""
from __future__ import annotations

import enum
import time

from pydantic import BaseModel, Field


class TraceType(str, enum.Enum):
    SEARCH_QUERY = "search_query"
    URL_VISITED = "url_visited"
    SEARCH_SNIPPET = "search_snippet"
    BROWSER_CONTENT = "browser_content"
    DISTILLED_OUTCOME = "distilled_outcome"


class TraceTier(str, enum.Enum):
    TRANSIENT = "transient"  # expires after TTL
    DURABLE = "durable"      # promoted to long-term memory


class TraceEntry(BaseModel):
    """A single research trace entry."""
    session_id: str
    trace_type: TraceType
    content: str
    source_tool: str = ""
    tier: TraceTier = TraceTier.TRANSIENT
    created_at: float = Field(default_factory=time.time)
    metadata: dict = Field(default_factory=dict)
```

**Step 4: Write store implementation**

```python
# backend/app/domain/services/research_trace_store.py
"""
In-memory research trace store with TTL-based expiry.

Phase 1: In-memory dict keyed by session_id.
Phase 2: Redis-backed with EXPIRE for multi-instance coordination.

Only DISTILLED_OUTCOME entries feed into MemoryService. All other
trace types are ephemeral research breadcrumbs.
"""
from __future__ import annotations

import time
from collections import defaultdict

from app.domain.models.research_trace import TraceEntry, TraceTier, TraceType


class ResearchTraceStore:
    """Session-scoped trace store with TTL expiry."""

    __slots__ = ("_ttl", "_traces")

    def __init__(self, ttl_seconds: int = 7200) -> None:
        self._ttl = ttl_seconds
        self._traces: dict[str, list[TraceEntry]] = defaultdict(list)

    async def add(self, entry: TraceEntry) -> None:
        self._traces[entry.session_id].append(entry)

    async def get_session_traces(
        self,
        session_id: str,
        trace_types: set[TraceType] | None = None,
    ) -> list[TraceEntry]:
        now = time.time()
        result = []
        for entry in self._traces.get(session_id, []):
            # TTL check for transient entries
            if entry.tier == TraceTier.TRANSIENT and (now - entry.created_at) > self._ttl:
                continue
            if trace_types and entry.trace_type not in trace_types:
                continue
            result.append(entry)
        return result

    async def get_distilled_outcomes(self, session_id: str) -> list[TraceEntry]:
        return await self.get_session_traces(
            session_id,
            trace_types={TraceType.DISTILLED_OUTCOME},
        )

    async def clear_session(self, session_id: str) -> None:
        self._traces.pop(session_id, None)

    async def prune_expired(self) -> int:
        """Remove all expired transient entries. Returns count removed."""
        now = time.time()
        removed = 0
        for sid in list(self._traces.keys()):
            before = len(self._traces[sid])
            self._traces[sid] = [
                e for e in self._traces[sid]
                if e.tier == TraceTier.DURABLE or (now - e.created_at) <= self._ttl
            ]
            removed += before - len(self._traces[sid])
            if not self._traces[sid]:
                del self._traces[sid]
        return removed
```

**Step 5: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/test_research_trace_store.py -v`
Expected: 5 PASSED

**Step 6: Commit**

```bash
git add backend/app/domain/models/research_trace.py \
        backend/app/domain/services/research_trace_store.py \
        backend/tests/domain/services/test_research_trace_store.py
git commit -m "feat(memory): add RESEARCH_TRACE tier with TTL-based expiry for search breadcrumbs"
```

---

### Task 7: LeadAgentRuntime Facade — Assembly

> Wire Tasks 1-6 into a single runtime facade that `AgentTaskRunner._init_plan_act_flow()`
> (line 301) can construct. The facade owns the middleware pipeline and injects workspace
> contracts, clarification gates, and tool-call recovery into PlanActFlow without modifying it.

**Files:**
- Create: `backend/app/domain/services/runtime/lead_agent_runtime.py`
- Modify: `backend/app/domain/services/agent_task_runner.py:301` — add runtime construction
- Test: `backend/tests/domain/services/runtime/test_lead_agent_runtime.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/runtime/test_lead_agent_runtime.py
"""Tests for the LeadAgentRuntime facade."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.services.runtime.lead_agent_runtime import (
    LeadAgentRuntime,
    build_runtime_pipeline,
)
from app.domain.services.runtime.middleware import RuntimeContext, RuntimeHook


@pytest.mark.asyncio
class TestLeadAgentRuntime:
    async def test_build_pipeline_returns_ordered_middlewares(self):
        pipeline = build_runtime_pipeline(
            session_id="s-1",
            agent_id="a-1",
            workspace_base="/sessions",
        )
        assert pipeline is not None
        # Should have at least: workspace, dangling_tool, clarification
        assert len(pipeline._middlewares) >= 3

    async def test_runtime_init_populates_workspace(self):
        runtime = LeadAgentRuntime(
            session_id="s-1",
            agent_id="a-1",
            workspace_base="/sessions",
        )
        ctx = await runtime.initialize()
        assert "workspace" in ctx.workspace
        assert ctx.workspace["task_state"].endswith("task_state.md")

    async def test_runtime_before_step_sanitizes_history(self):
        runtime = LeadAgentRuntime(
            session_id="s-1",
            agent_id="a-1",
        )
        ctx = await runtime.initialize()
        # Inject dangling tool call
        ctx.metadata["message_history"] = [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc-1", "function": {"name": "search", "arguments": "{}"}}
            ]},
        ]
        ctx = await runtime.before_step(ctx)
        history = ctx.metadata["message_history"]
        tool_msgs = [m for m in history if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert "[Interrupted]" in tool_msgs[0]["content"]

    async def test_runtime_exposes_workspace_contract(self):
        runtime = LeadAgentRuntime(
            session_id="s-1",
            agent_id="a-1",
            workspace_base="/sessions",
        )
        ctx = await runtime.initialize()
        contract = ctx.metadata.get("workspace_contract")
        assert contract is not None
        assert contract.session_id == "s-1"
        prompt_block = contract.to_prompt_block()
        assert "<workspace_contract>" in prompt_block
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_lead_agent_runtime.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# backend/app/domain/services/runtime/lead_agent_runtime.py
"""
LeadAgentRuntime — the ordered middleware facade for Pythinker's agent execution.

Borrows DeerFlow's agent.py:207 shape (ordered middleware pipeline) but preserves
Pythinker's full 31-collaborator PlanActFlow as the inner execution engine.

The runtime sits BETWEEN AgentTaskRunner and PlanActFlow:
  AgentTaskRunner → LeadAgentRuntime.initialize() → PlanActFlow(enhanced_context)
                  → LeadAgentRuntime.before_step() → PlanActFlow step execution
                  → LeadAgentRuntime.after_step()
                  → LeadAgentRuntime.finalize()

Middleware order (mirrors DeerFlow agent.py:198-206):
  1. WorkspaceMiddleware     — session-scoped paths (ThreadDataMiddleware equivalent)
  2. DanglingToolCallMiddleware — interrupt recovery
  3. ClarificationMiddleware — human-in-the-loop gate
"""
from __future__ import annotations

from app.domain.services.runtime.middleware import (
    RuntimeContext,
    RuntimeHook,
    RuntimePipeline,
)
from app.domain.services.runtime.workspace_middleware import WorkspaceMiddleware
from app.domain.services.runtime.dangling_tool_middleware import DanglingToolCallMiddleware
from app.domain.services.runtime.clarification_middleware import ClarificationMiddleware


def build_runtime_pipeline(
    session_id: str,
    agent_id: str,
    workspace_base: str = "/home/ubuntu",
) -> RuntimePipeline:
    """Construct the ordered middleware pipeline.

    Position order is the contract — do not reorder without understanding
    the dependency chain (workspace paths must exist before clarification
    can reference them, etc.).
    """
    return RuntimePipeline(middlewares=[
        WorkspaceMiddleware(base_dir=workspace_base),       # 1
        DanglingToolCallMiddleware(),                        # 2
        ClarificationMiddleware(),                           # 3
    ])


class LeadAgentRuntime:
    """Facade that wraps PlanActFlow with ordered middleware hooks."""

    __slots__ = ("_pipeline", "_ctx", "_session_id", "_agent_id")

    def __init__(
        self,
        session_id: str,
        agent_id: str,
        workspace_base: str = "/home/ubuntu",
    ) -> None:
        self._session_id = session_id
        self._agent_id = agent_id
        self._pipeline = build_runtime_pipeline(
            session_id=session_id,
            agent_id=agent_id,
            workspace_base=workspace_base,
        )
        self._ctx: RuntimeContext | None = None

    async def initialize(self) -> RuntimeContext:
        """Run BEFORE_RUN hooks. Call once at session start."""
        self._ctx = RuntimeContext(
            session_id=self._session_id,
            agent_id=self._agent_id,
        )
        self._ctx = await self._pipeline.run_hook(RuntimeHook.BEFORE_RUN, self._ctx)
        return self._ctx

    async def before_step(self, ctx: RuntimeContext | None = None) -> RuntimeContext:
        """Run BEFORE_STEP hooks. Call before each plan step."""
        target = ctx or self._ctx
        if target is None:
            raise RuntimeError("Runtime not initialized — call initialize() first")
        target = await self._pipeline.run_hook(RuntimeHook.BEFORE_STEP, target)
        self._ctx = target
        return target

    async def after_step(self, ctx: RuntimeContext | None = None) -> RuntimeContext:
        """Run AFTER_STEP hooks. Call after each plan step."""
        target = ctx or self._ctx
        if target is None:
            raise RuntimeError("Runtime not initialized")
        target = await self._pipeline.run_hook(RuntimeHook.AFTER_STEP, target)
        self._ctx = target
        return target

    async def finalize(self) -> RuntimeContext:
        """Run AFTER_RUN hooks. Call once at session end."""
        if self._ctx is None:
            raise RuntimeError("Runtime not initialized")
        self._ctx = await self._pipeline.run_hook(RuntimeHook.AFTER_RUN, self._ctx)
        return self._ctx

    @property
    def context(self) -> RuntimeContext | None:
        return self._ctx
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_lead_agent_runtime.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add backend/app/domain/services/runtime/lead_agent_runtime.py \
        backend/tests/domain/services/runtime/test_lead_agent_runtime.py
git commit -m "feat(runtime): assemble LeadAgentRuntime facade with ordered middleware pipeline"
```

---

## Phase 1 — P1: Intelligence Amplification

### Task 8: Insight Graph → Long-Term Memory Promotion

> Close the gap at context_manager.py:233 where InsightSynthesizer populates ContextGraph
> in-memory but never writes to MemoryService. Promote high-confidence insights automatically.

**Files:**
- Create: `backend/app/domain/services/runtime/insight_promotion_middleware.py`
- Test: `backend/tests/domain/services/runtime/test_insight_promotion.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/runtime/test_insight_promotion.py
"""Tests for insight-to-memory promotion middleware."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.services.runtime.insight_promotion_middleware import (
    InsightPromotionMiddleware,
)
from app.domain.services.runtime.middleware import RuntimeContext
from app.domain.services.agents.context_manager import StepInsight, InsightType


@pytest.mark.asyncio
class TestInsightPromotionMiddleware:
    async def test_high_confidence_insight_promoted(self):
        memory_service = AsyncMock()
        mw = InsightPromotionMiddleware(
            memory_service=memory_service,
            confidence_threshold=0.85,
        )
        insight = StepInsight(
            step_id="step-1",
            insight_type=InsightType.DISCOVERY,
            content="The API rate limit is 100 req/min",
            confidence=0.95,
            source_tool="info_search_web",
        )
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        ctx.metadata["new_insights"] = [insight]
        ctx.metadata["user_id"] = "user-1"

        await mw.after_step(ctx)

        memory_service.store_memory.assert_called_once()
        call_kwargs = memory_service.store_memory.call_args.kwargs
        assert "rate limit" in call_kwargs["content"].lower()

    async def test_low_confidence_insight_not_promoted(self):
        memory_service = AsyncMock()
        mw = InsightPromotionMiddleware(
            memory_service=memory_service,
            confidence_threshold=0.85,
        )
        insight = StepInsight(
            step_id="step-1",
            insight_type=InsightType.ASSUMPTION,
            content="Maybe the API uses OAuth",
            confidence=0.5,
        )
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        ctx.metadata["new_insights"] = [insight]
        ctx.metadata["user_id"] = "user-1"

        await mw.after_step(ctx)

        memory_service.store_memory.assert_not_called()

    async def test_error_learning_always_promoted(self):
        memory_service = AsyncMock()
        mw = InsightPromotionMiddleware(
            memory_service=memory_service,
            confidence_threshold=0.85,
        )
        insight = StepInsight(
            step_id="step-1",
            insight_type=InsightType.ERROR_LEARNING,
            content="Serper API rejects queries with special chars",
            confidence=0.7,  # below threshold but ERROR_LEARNING
        )
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        ctx.metadata["new_insights"] = [insight]
        ctx.metadata["user_id"] = "user-1"

        await mw.after_step(ctx)

        memory_service.store_memory.assert_called_once()

    async def test_no_insights_no_action(self):
        memory_service = AsyncMock()
        mw = InsightPromotionMiddleware(memory_service=memory_service)
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")

        await mw.after_step(ctx)

        memory_service.store_memory.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_insight_promotion.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# backend/app/domain/services/runtime/insight_promotion_middleware.py
"""
Insight-to-memory promotion middleware.

Closes the gap at context_manager.py:233 where InsightSynthesizer populates
ContextGraph in-memory but never writes to MemoryService. After each step,
this middleware checks for new high-confidence insights and promotes them
to long-term Qdrant storage.

Promotion rules:
- confidence >= threshold (default 0.85) → always promote
- InsightType.ERROR_LEARNING → always promote (regardless of confidence)
- InsightType.BLOCKER → always promote
- All others below threshold → skip
"""
from __future__ import annotations

import logging
from typing import Any

from app.domain.services.agents.context_manager import InsightType, StepInsight
from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware

logger = logging.getLogger(__name__)

# Insight types that are always promoted regardless of confidence
_ALWAYS_PROMOTE = {InsightType.ERROR_LEARNING, InsightType.BLOCKER}

# Map InsightType → MemoryType string
_INSIGHT_TO_MEMORY_TYPE = {
    InsightType.DISCOVERY: "FACT",
    InsightType.ERROR_LEARNING: "EXPERIENCE",
    InsightType.DECISION: "CONTEXT",
    InsightType.DEPENDENCY: "CONTEXT",
    InsightType.ASSUMPTION: "CONTEXT",
    InsightType.CONSTRAINT: "CONTEXT",
    InsightType.PROGRESS: "CONTEXT",
    InsightType.BLOCKER: "EXPERIENCE",
}


class InsightPromotionMiddleware(RuntimeMiddleware):
    """Promotes high-confidence insights from ContextGraph to long-term memory.

    Pipeline position: late in after_step (after execution, before checkpoint).
    """

    def __init__(
        self,
        memory_service: Any,  # MemoryService
        confidence_threshold: float = 0.85,
    ) -> None:
        self._memory_service = memory_service
        self._threshold = confidence_threshold

    async def after_step(self, ctx: RuntimeContext) -> RuntimeContext:
        insights: list[StepInsight] = ctx.metadata.get("new_insights", [])
        if not insights:
            return ctx

        user_id = ctx.metadata.get("user_id", "")
        if not user_id:
            return ctx

        promoted = 0
        for insight in insights:
            if not self._should_promote(insight):
                continue
            try:
                await self._memory_service.store_memory(
                    user_id=user_id,
                    content=insight.content,
                    memory_type=_INSIGHT_TO_MEMORY_TYPE.get(
                        insight.insight_type, "CONTEXT"
                    ),
                    importance=insight.confidence,
                    tags=[insight.insight_type.value],
                    session_id=ctx.session_id,
                    generate_embedding=True,
                )
                promoted += 1
            except Exception:
                logger.warning(
                    "Failed to promote insight to memory: %s",
                    insight.content[:80],
                    exc_info=True,
                )

        if promoted:
            logger.info("Promoted %d/%d insights to long-term memory", promoted, len(insights))

        # Clear processed insights
        ctx.metadata.pop("new_insights", None)
        return ctx

    def _should_promote(self, insight: StepInsight) -> bool:
        if insight.insight_type in _ALWAYS_PROMOTE:
            return True
        return insight.confidence >= self._threshold
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_insight_promotion.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add backend/app/domain/services/runtime/insight_promotion_middleware.py \
        backend/tests/domain/services/runtime/test_insight_promotion.py
git commit -m "feat(runtime): add insight-to-memory promotion middleware (ContextGraph → Qdrant)"
```

---

### Task 9: Runtime Capability Manifest

> Expose one per-session manifest covering active skills, MCP servers, tool categories,
> model capabilities, sandbox state, and child-task limits. Borrows DeerFlow's config-driven
> loading pattern (loader.py:22).

**Files:**
- Create: `backend/app/domain/models/capability_manifest.py`
- Create: `backend/app/domain/services/runtime/capability_middleware.py`
- Test: `backend/tests/domain/services/runtime/test_capability_manifest.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/runtime/test_capability_manifest.py
"""Tests for runtime capability manifest."""
import pytest

from app.domain.models.capability_manifest import (
    CapabilityManifest,
    ModelCapabilities,
    SandboxState,
)
from app.domain.services.runtime.capability_middleware import CapabilityMiddleware
from app.domain.services.runtime.middleware import RuntimeContext


@pytest.mark.asyncio
class TestCapabilityManifest:
    async def test_manifest_serializes(self):
        manifest = CapabilityManifest(
            session_id="s-1",
            active_skills=["deep-research", "chart-viz"],
            mcp_servers=["context7", "tavily"],
            tool_categories={"search", "browser", "file"},
            model=ModelCapabilities(
                name="kimi-for-coding",
                supports_vision=False,
                supports_thinking=False,
                max_tokens=8192,
            ),
            sandbox=SandboxState(active=True, sandbox_id="sb-123"),
            max_concurrent_delegates=3,
        )
        d = manifest.model_dump()
        assert d["active_skills"] == ["deep-research", "chart-viz"]
        assert d["model"]["name"] == "kimi-for-coding"
        assert d["sandbox"]["active"] is True

    async def test_manifest_to_prompt_block(self):
        manifest = CapabilityManifest(
            session_id="s-1",
            active_skills=["research"],
            mcp_servers=[],
            tool_categories={"search"},
            model=ModelCapabilities(name="test-model"),
            sandbox=SandboxState(active=False),
            max_concurrent_delegates=2,
        )
        block = manifest.to_prompt_block()
        assert "<capability_manifest>" in block
        assert "research" in block
        assert "max_concurrent_delegates: 2" in block

    async def test_middleware_populates_manifest(self):
        mw = CapabilityMiddleware(
            active_skills=["skill-a"],
            mcp_servers=["mcp-1"],
            tool_categories={"file", "search"},
            model_name="test",
            max_concurrent_delegates=3,
        )
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        result = await mw.before_run(ctx)
        assert "capability_manifest" in result.metadata
        manifest = result.metadata["capability_manifest"]
        assert manifest.session_id == "s-1"
        assert "skill-a" in manifest.active_skills
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_capability_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write domain model**

```python
# backend/app/domain/models/capability_manifest.py
"""
Runtime capability manifest — per-session inventory of active capabilities.

Borrows DeerFlow's config-driven loading pattern (loader.py:22) where the
prompt always reflects the current runtime state. The manifest is injected
once at session start and refreshed if capabilities change mid-session.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ModelCapabilities(BaseModel):
    name: str
    supports_vision: bool = False
    supports_thinking: bool = False
    max_tokens: int = 4096


class SandboxState(BaseModel):
    active: bool = False
    sandbox_id: str | None = None


class CapabilityManifest(BaseModel):
    """Per-session snapshot of what the agent can do right now."""
    session_id: str
    active_skills: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    tool_categories: set[str] = Field(default_factory=set)
    model: ModelCapabilities = Field(default_factory=lambda: ModelCapabilities(name="default"))
    sandbox: SandboxState = Field(default_factory=SandboxState)
    max_concurrent_delegates: int = 3

    def to_prompt_block(self) -> str:
        lines = ["<capability_manifest>"]
        lines.append(f"  model: {self.model.name}")
        if self.model.supports_vision:
            lines.append("  vision: enabled")
        if self.model.supports_thinking:
            lines.append("  thinking: enabled")
        if self.active_skills:
            lines.append(f"  skills: {', '.join(self.active_skills)}")
        if self.mcp_servers:
            lines.append(f"  mcp_servers: {', '.join(self.mcp_servers)}")
        if self.tool_categories:
            lines.append(f"  tool_categories: {', '.join(sorted(self.tool_categories))}")
        lines.append(f"  sandbox: {'active' if self.sandbox.active else 'inactive'}")
        lines.append(f"  max_concurrent_delegates: {self.max_concurrent_delegates}")
        lines.append("</capability_manifest>")
        return "\n".join(lines)
```

**Step 4: Write middleware**

```python
# backend/app/domain/services/runtime/capability_middleware.py
"""Capability manifest middleware — populates runtime capabilities at session start."""
from __future__ import annotations

from app.domain.models.capability_manifest import (
    CapabilityManifest,
    ModelCapabilities,
    SandboxState,
)
from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware


class CapabilityMiddleware(RuntimeMiddleware):
    """Assembles the capability manifest from injected config.

    Pipeline position: after workspace (needs session_id), before execution.
    """

    def __init__(
        self,
        active_skills: list[str] | None = None,
        mcp_servers: list[str] | None = None,
        tool_categories: set[str] | None = None,
        model_name: str = "default",
        supports_vision: bool = False,
        supports_thinking: bool = False,
        max_tokens: int = 4096,
        sandbox_active: bool = False,
        sandbox_id: str | None = None,
        max_concurrent_delegates: int = 3,
    ) -> None:
        self._skills = active_skills or []
        self._mcp = mcp_servers or []
        self._tools = tool_categories or set()
        self._model_name = model_name
        self._vision = supports_vision
        self._thinking = supports_thinking
        self._max_tokens = max_tokens
        self._sandbox_active = sandbox_active
        self._sandbox_id = sandbox_id
        self._max_delegates = max_concurrent_delegates

    async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
        manifest = CapabilityManifest(
            session_id=ctx.session_id,
            active_skills=list(self._skills),
            mcp_servers=list(self._mcp),
            tool_categories=set(self._tools),
            model=ModelCapabilities(
                name=self._model_name,
                supports_vision=self._vision,
                supports_thinking=self._thinking,
                max_tokens=self._max_tokens,
            ),
            sandbox=SandboxState(
                active=self._sandbox_active,
                sandbox_id=self._sandbox_id,
            ),
            max_concurrent_delegates=self._max_delegates,
        )
        ctx.metadata["capability_manifest"] = manifest
        return ctx
```

**Step 5: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_capability_manifest.py -v`
Expected: 3 PASSED

**Step 6: Commit**

```bash
git add backend/app/domain/models/capability_manifest.py \
        backend/app/domain/services/runtime/capability_middleware.py \
        backend/tests/domain/services/runtime/test_capability_manifest.py
git commit -m "feat(runtime): add capability manifest model and middleware"
```

---

### Task 10: Quality Gates as Runtime Defaults

> Wire grounding_validator, output_coverage_validator, and dynamic_toolset filtering into the
> runtime pipeline as BEFORE_STEP/AFTER_STEP hooks — always active, not optional late-stage
> helpers. Preserves existing implementations, just moves invocation earlier.

**Files:**
- Create: `backend/app/domain/services/runtime/quality_gate_middleware.py`
- Test: `backend/tests/domain/services/runtime/test_quality_gate_middleware.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/runtime/test_quality_gate_middleware.py
"""Tests for quality gate middleware."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.services.runtime.quality_gate_middleware import QualityGateMiddleware
from app.domain.services.runtime.middleware import RuntimeContext


@pytest.mark.asyncio
class TestQualityGateMiddleware:
    async def test_before_step_filters_tools(self):
        toolset_manager = MagicMock()
        toolset_manager.get_tools_for_task.return_value = ["search", "file_read"]
        mw = QualityGateMiddleware(toolset_manager=toolset_manager)
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        ctx.metadata["current_step_description"] = "Research competitors"

        result = await mw.before_step(ctx)

        toolset_manager.get_tools_for_task.assert_called_once()
        assert result.metadata.get("filtered_tools") == ["search", "file_read"]

    async def test_after_step_runs_coverage_check(self):
        coverage_validator = MagicMock()
        coverage_validator.validate.return_value = MagicMock(
            is_valid=True,
            quality_score=0.85,
            missing_requirements=[],
        )
        mw = QualityGateMiddleware(coverage_validator=coverage_validator)
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        ctx.metadata["step_output"] = "Here are the research results..."
        ctx.metadata["user_request"] = "Research AI trends"

        result = await mw.after_step(ctx)

        coverage_validator.validate.assert_called_once()
        assert result.metadata["coverage_score"] == 0.85

    async def test_no_validators_passes_through(self):
        mw = QualityGateMiddleware()
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        result = await mw.before_step(ctx)
        assert result is ctx

    async def test_grounding_check_on_after_step(self):
        grounding_validator = AsyncMock()
        grounding_validator.validate.return_value = MagicMock(
            is_acceptable=True,
            overall_score=0.92,
        )
        mw = QualityGateMiddleware(grounding_validator=grounding_validator)
        ctx = RuntimeContext(session_id="s-1", agent_id="a-1")
        ctx.metadata["step_output"] = "Some factual content"
        ctx.metadata["source_context"] = "Source material..."

        result = await mw.after_step(ctx)

        assert result.metadata.get("grounding_score") == 0.92
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_quality_gate_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# backend/app/domain/services/runtime/quality_gate_middleware.py
"""
Quality gate middleware — wires grounding, coverage, and tool filtering
into the runtime pipeline as always-on hooks.

These validators already exist in Pythinker (grounding_validator.py,
output_coverage_validator.py, dynamic_toolset.py). This middleware
moves their invocation from optional late-stage helpers to runtime defaults.
"""
from __future__ import annotations

import logging
from typing import Any

from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware

logger = logging.getLogger(__name__)


class QualityGateMiddleware(RuntimeMiddleware):
    """Applies quality gates as runtime defaults.

    before_step: dynamic tool filtering based on step description
    after_step: output coverage + grounding validation
    """

    def __init__(
        self,
        toolset_manager: Any | None = None,
        coverage_validator: Any | None = None,
        grounding_validator: Any | None = None,
    ) -> None:
        self._toolset = toolset_manager
        self._coverage = coverage_validator
        self._grounding = grounding_validator

    async def before_step(self, ctx: RuntimeContext) -> RuntimeContext:
        if not self._toolset:
            return ctx

        step_desc = ctx.metadata.get("current_step_description", "")
        if not step_desc:
            return ctx

        try:
            filtered = self._toolset.get_tools_for_task(step_desc)
            ctx.metadata["filtered_tools"] = filtered
        except Exception:
            logger.warning("Tool filtering failed, using full toolset", exc_info=True)

        return ctx

    async def after_step(self, ctx: RuntimeContext) -> RuntimeContext:
        step_output = ctx.metadata.get("step_output", "")
        if not step_output:
            return ctx

        # Coverage check
        if self._coverage:
            try:
                user_request = ctx.metadata.get("user_request", "")
                result = self._coverage.validate(
                    output=step_output,
                    user_request=user_request,
                )
                ctx.metadata["coverage_score"] = result.quality_score
                ctx.metadata["coverage_valid"] = result.is_valid
                if result.missing_requirements:
                    ctx.metadata["coverage_missing"] = result.missing_requirements
            except Exception:
                logger.warning("Coverage validation failed", exc_info=True)

        # Grounding check
        if self._grounding:
            try:
                source_context = ctx.metadata.get("source_context", "")
                if source_context:
                    result = await self._grounding.validate(
                        output=step_output,
                        source_context=source_context,
                    )
                    ctx.metadata["grounding_score"] = result.overall_score
                    ctx.metadata["grounding_acceptable"] = result.is_acceptable
            except Exception:
                logger.warning("Grounding validation failed", exc_info=True)

        return ctx
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_quality_gate_middleware.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add backend/app/domain/services/runtime/quality_gate_middleware.py \
        backend/tests/domain/services/runtime/test_quality_gate_middleware.py
git commit -m "feat(runtime): add quality gate middleware (grounding + coverage + tool filtering)"
```

---

## Phase 2 — P2: Platform Extensions

### Task 11: Channel/Session Config Overlay for Nanobot

> Add DeerFlow-style 3-layer config overlay (default → channel → user) to Pythinker's
> nanobot bridge. Borrows DeerFlow's service.py:29 and manager.py:165-198 pattern.

**Files:**
- Create: `backend/app/domain/models/channel_overlay.py`
- Modify: `backend/app/infrastructure/external/channels/nanobot_gateway.py` — add overlay resolution
- Test: `backend/tests/infrastructure/channels/test_channel_overlay.py`

**Step 1: Write the failing test**

```python
# backend/tests/infrastructure/channels/test_channel_overlay.py
"""Tests for channel/session config overlay."""
import pytest

from app.domain.models.channel_overlay import (
    ChannelSessionOverlay,
    resolve_session_config,
)


class TestChannelSessionOverlay:
    def test_default_only(self):
        default = ChannelSessionOverlay(model_name="kimi", thinking_enabled=False)
        result = resolve_session_config(default_config=default)
        assert result.model_name == "kimi"
        assert result.thinking_enabled is False

    def test_channel_overrides_default(self):
        default = ChannelSessionOverlay(model_name="kimi", thinking_enabled=False)
        channel = ChannelSessionOverlay(thinking_enabled=True)
        result = resolve_session_config(default_config=default, channel_config=channel)
        assert result.model_name == "kimi"  # inherited from default
        assert result.thinking_enabled is True  # overridden by channel

    def test_user_overrides_channel(self):
        default = ChannelSessionOverlay(model_name="kimi", max_delegates=3)
        channel = ChannelSessionOverlay(model_name="gpt-4o")
        user = ChannelSessionOverlay(model_name="claude-sonnet")
        result = resolve_session_config(
            default_config=default,
            channel_config=channel,
            user_config=user,
        )
        assert result.model_name == "claude-sonnet"  # user wins
        assert result.max_delegates == 3  # from default

    def test_none_fields_dont_override(self):
        default = ChannelSessionOverlay(model_name="kimi", max_delegates=3)
        channel = ChannelSessionOverlay(model_name=None)  # explicit None
        result = resolve_session_config(default_config=default, channel_config=channel)
        assert result.model_name == "kimi"  # None doesn't override
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/infrastructure/channels/test_channel_overlay.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# backend/app/domain/models/channel_overlay.py
"""
Channel/session config overlay model.

Borrows DeerFlow's 3-layer merge pattern (manager.py:165-198):
  DEFAULT_RUN_CONFIG → channel_layer → user_layer

Each layer can override: model_name, thinking_enabled, subagent_enabled,
max_delegates, tool_budget, clarification_policy.
None values mean "don't override — inherit from previous layer."
"""
from __future__ import annotations

from pydantic import BaseModel


class ChannelSessionOverlay(BaseModel):
    """One layer of session configuration. None = inherit from lower layer."""
    model_name: str | None = None
    thinking_enabled: bool | None = None
    subagent_enabled: bool | None = None
    max_delegates: int | None = None
    tool_budget: int | None = None
    clarification_enabled: bool | None = None


def resolve_session_config(
    default_config: ChannelSessionOverlay,
    channel_config: ChannelSessionOverlay | None = None,
    user_config: ChannelSessionOverlay | None = None,
) -> ChannelSessionOverlay:
    """Merge 3 layers: default → channel → user. Non-None values win."""
    layers = [default_config]
    if channel_config:
        layers.append(channel_config)
    if user_config:
        layers.append(user_config)

    merged: dict = {}
    for layer in layers:
        for field_name, value in layer.model_dump().items():
            if value is not None:
                merged[field_name] = value

    return ChannelSessionOverlay.model_validate(merged)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/infrastructure/channels/test_channel_overlay.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add backend/app/domain/models/channel_overlay.py \
        backend/tests/infrastructure/channels/test_channel_overlay.py
git commit -m "feat(channels): add 3-layer session config overlay for nanobot channels"
```

---

### Task 12: Skill System Filesystem Interop

> Add DeerFlow-style filesystem scanning (loader.py:57) alongside Pythinker's existing
> SkillLoader. Enable public/ and custom/ skill packs with SKILL.md frontmatter, while
> preserving Pythinker's 3-level progressive disclosure.

**Files:**
- Create: `backend/app/domain/services/runtime/skill_discovery_middleware.py`
- Modify: `backend/app/domain/services/skill_loader.py` — add `scan_directories()` method
- Test: `backend/tests/domain/services/runtime/test_skill_discovery.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/runtime/test_skill_discovery.py
"""Tests for skill discovery middleware."""
import pytest
from pathlib import Path

from app.domain.services.runtime.skill_discovery_middleware import (
    SkillDiscoveryMiddleware,
    scan_skill_directories,
    SkillSummary,
)


class TestScanSkillDirectories:
    def test_discovers_skills_with_skill_md(self, tmp_path: Path):
        # Create public/research/SKILL.md
        skill_dir = tmp_path / "public" / "research"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: research\ndescription: Deep research skill\n---\n# Research\n"
        )
        # Create custom/my-skill/SKILL.md
        custom_dir = tmp_path / "custom" / "my-skill"
        custom_dir.mkdir(parents=True)
        (custom_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Custom skill\n---\n# Custom\n"
        )
        # Create a decoy directory without SKILL.md
        (tmp_path / "public" / "not-a-skill").mkdir(parents=True)

        skills = scan_skill_directories(tmp_path)

        assert len(skills) == 2
        names = {s.name for s in skills}
        assert "research" in names
        assert "my-skill" in names

    def test_parses_frontmatter(self, tmp_path: Path):
        skill_dir = tmp_path / "public" / "test"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: A test\n---\n# Body\n"
        )
        skills = scan_skill_directories(tmp_path)
        assert skills[0].name == "test-skill"
        assert skills[0].description == "A test"
        assert skills[0].category == "public"

    def test_empty_directory_returns_empty(self, tmp_path: Path):
        assert scan_skill_directories(tmp_path) == []

    def test_skill_summary_to_prompt_entry(self, tmp_path: Path):
        s = SkillSummary(
            name="deep-research",
            description="Multi-phase research",
            category="public",
            path=str(tmp_path / "public" / "deep-research" / "SKILL.md"),
        )
        entry = s.to_prompt_entry()
        assert "deep-research" in entry
        assert "Multi-phase research" in entry
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_skill_discovery.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# backend/app/domain/services/runtime/skill_discovery_middleware.py
"""
Skill discovery middleware — filesystem scanning with frontmatter parsing.

Borrows DeerFlow's loader.py:57 pattern: scan public/ and custom/ directories
for SKILL.md files, parse YAML frontmatter, and inject a compact skill list
into the system prompt. Preserves Pythinker's existing SkillLoader for
full progressive-disclosure loading (levels 1-3).

This middleware handles DISCOVERY (level 0: name + description only).
The agent then uses ReadSkillTool to load full content on demand (level 2+).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_CATEGORIES = ("public", "custom")


@dataclass
class SkillSummary:
    """Compact skill entry for prompt injection (level 0 disclosure)."""
    name: str
    description: str
    category: str  # "public" or "custom"
    path: str

    def to_prompt_entry(self) -> str:
        return f"  - {self.name}: {self.description} [{self.category}]"


def scan_skill_directories(root: Path) -> list[SkillSummary]:
    """Scan root/{public,custom}/**/SKILL.md for skill metadata."""
    skills: list[SkillSummary] = []
    for category in _CATEGORIES:
        cat_dir = root / category
        if not cat_dir.is_dir():
            continue
        for child in sorted(cat_dir.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.is_file():
                continue
            meta = _parse_frontmatter(skill_md)
            if meta:
                skills.append(SkillSummary(
                    name=meta.get("name", child.name),
                    description=meta.get("description", ""),
                    category=category,
                    path=str(skill_md),
                ))
    return skills


def _parse_frontmatter(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(text)
        if not match:
            return None
        return yaml.safe_load(match.group(1)) or {}
    except Exception:
        return None


class SkillDiscoveryMiddleware(RuntimeMiddleware):
    """Discovers skills from filesystem and injects manifest into context.

    Pipeline position: during before_run, after workspace setup.
    """

    def __init__(self, skills_root: Path | str | None = None) -> None:
        self._root = Path(skills_root) if skills_root else None

    async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
        if not self._root or not self._root.is_dir():
            return ctx

        skills = scan_skill_directories(self._root)
        ctx.metadata["discovered_skills"] = skills
        ctx.metadata["skill_prompt_section"] = self._format_skill_section(skills)
        return ctx

    @staticmethod
    def _format_skill_section(skills: list[SkillSummary]) -> str:
        if not skills:
            return ""
        lines = ["<available_skills>"]
        for s in skills:
            lines.append(s.to_prompt_entry())
        lines.append("</available_skills>")
        return "\n".join(lines)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_skill_discovery.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add backend/app/domain/services/runtime/skill_discovery_middleware.py \
        backend/tests/domain/services/runtime/test_skill_discovery.py
git commit -m "feat(runtime): add skill discovery middleware with filesystem scanning"
```

---

## Phase 3 — Integration: Wire Runtime into AgentTaskRunner

### Task 13: Update LeadAgentRuntime with all middlewares

> Update the build_runtime_pipeline() factory to include all Phase 0-2 middlewares in
> correct order. Update AgentTaskRunner._init_plan_act_flow() to construct and use
> the runtime.

**Files:**
- Modify: `backend/app/domain/services/runtime/lead_agent_runtime.py` — add all middlewares
- Modify: `backend/app/domain/services/agent_task_runner.py:301` — construct runtime
- Test: `backend/tests/domain/services/runtime/test_full_pipeline.py`

**Step 1: Write the integration test**

```python
# backend/tests/domain/services/runtime/test_full_pipeline.py
"""Integration test for the full runtime pipeline."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.services.runtime.lead_agent_runtime import (
    LeadAgentRuntime,
    build_runtime_pipeline,
)
from app.domain.services.runtime.middleware import RuntimeContext, RuntimeHook


@pytest.mark.asyncio
class TestFullPipeline:
    async def test_full_pipeline_middleware_order(self):
        pipeline = build_runtime_pipeline(
            session_id="s-1",
            agent_id="a-1",
            workspace_base="/sessions",
            memory_service=AsyncMock(),
            toolset_manager=MagicMock(),
        )
        # Verify ordering: workspace → capability → dangling → quality → clarification → insight
        names = [type(m).__name__ for m in pipeline._middlewares]
        assert names.index("WorkspaceMiddleware") < names.index("DanglingToolCallMiddleware")
        assert names.index("DanglingToolCallMiddleware") < names.index("ClarificationMiddleware")

    async def test_full_lifecycle(self):
        runtime = LeadAgentRuntime(
            session_id="s-1",
            agent_id="a-1",
            workspace_base="/sessions",
        )
        # Initialize
        ctx = await runtime.initialize()
        assert ctx.workspace.get("workspace") is not None

        # Before step
        ctx.metadata["message_history"] = []
        ctx = await runtime.before_step(ctx)

        # After step
        ctx = await runtime.after_step(ctx)

        # Finalize
        ctx = await runtime.finalize()
        assert ctx.session_id == "s-1"

    async def test_workspace_contract_flows_to_capability_manifest(self):
        runtime = LeadAgentRuntime(
            session_id="s-1",
            agent_id="a-1",
            workspace_base="/sessions",
        )
        ctx = await runtime.initialize()
        assert "workspace_contract" in ctx.metadata
```

**Step 2: Update build_runtime_pipeline()**

Update `backend/app/domain/services/runtime/lead_agent_runtime.py`:

```python
def build_runtime_pipeline(
    session_id: str,
    agent_id: str,
    workspace_base: str = "/home/ubuntu",
    memory_service: Any | None = None,
    toolset_manager: Any | None = None,
    coverage_validator: Any | None = None,
    grounding_validator: Any | None = None,
    active_skills: list[str] | None = None,
    mcp_servers: list[str] | None = None,
    tool_categories: set[str] | None = None,
    model_name: str = "default",
    max_concurrent_delegates: int = 3,
    skills_root: Path | str | None = None,
) -> RuntimePipeline:
    middlewares = [
        WorkspaceMiddleware(base_dir=workspace_base),           # 1
        CapabilityMiddleware(                                    # 2
            active_skills=active_skills,
            mcp_servers=mcp_servers,
            tool_categories=tool_categories,
            model_name=model_name,
            max_concurrent_delegates=max_concurrent_delegates,
        ),
        DanglingToolCallMiddleware(),                            # 3
        QualityGateMiddleware(                                   # 4
            toolset_manager=toolset_manager,
            coverage_validator=coverage_validator,
            grounding_validator=grounding_validator,
        ),
        ClarificationMiddleware(),                               # 5
    ]
    if memory_service:
        middlewares.append(InsightPromotionMiddleware(            # 6
            memory_service=memory_service,
        ))
    if skills_root:
        middlewares.insert(2, SkillDiscoveryMiddleware(           # 2.5 (after capability)
            skills_root=skills_root,
        ))
    return RuntimePipeline(middlewares=middlewares)
```

**Step 3: Run integration test**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/test_full_pipeline.py -v`
Expected: 3 PASSED

**Step 4: Run all runtime tests**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/domain/services/runtime/ -v`
Expected: All PASSED (24+ tests across 8 test files)

**Step 5: Commit**

```bash
git add backend/app/domain/services/runtime/lead_agent_runtime.py \
        backend/tests/domain/services/runtime/test_full_pipeline.py
git commit -m "feat(runtime): wire all middlewares into full ordered pipeline with integration tests"
```

---

### Task 14: Feature Flags for Runtime

> Add feature flags so the runtime pipeline is opt-in during rollout.

**Files:**
- Modify: `backend/app/core/config_features.py` — add runtime feature flags
- Test: verify existing tests still pass

**Step 1: Add flags to config_features.py**

Add after the existing feature flags section (around line 444):

```python
# --- LeadAgentRuntime (DeerFlow convergence) ---
feature_lead_agent_runtime: bool = False  # Master switch for runtime pipeline
feature_runtime_workspace_contracts: bool = True  # Session-scoped workspace paths
feature_runtime_clarification_gate: bool = True  # Human-in-the-loop clarification
feature_runtime_dangling_recovery: bool = True  # Interrupted tool call sanitization
feature_runtime_quality_gates: bool = True  # Always-on grounding + coverage
feature_runtime_insight_promotion: bool = True  # ContextGraph → Qdrant bridge
feature_runtime_capability_manifest: bool = True  # Per-session capability inventory
feature_runtime_skill_discovery: bool = True  # Filesystem skill scanning
feature_runtime_research_trace: bool = True  # RESEARCH_TRACE memory tier
feature_runtime_delegate_tool: bool = True  # Unified delegation tool
feature_runtime_channel_overlay: bool = True  # 3-layer channel config
```

**Step 2: Run existing config tests**

Run: `cd backend && conda activate pythinker && pytest -p no:cov -o addopts= tests/ -k "config" -v --timeout=30`
Expected: All PASSED

**Step 3: Commit**

```bash
git add backend/app/core/config_features.py
git commit -m "feat(config): add feature flags for LeadAgentRuntime pipeline (all off by default)"
```

---

### Task 15: Wire Runtime into AgentTaskRunner

> The final integration step: construct LeadAgentRuntime in
> AgentTaskRunner._init_plan_act_flow() (line 301) and pass workspace contract
> and task_state_path to PlanActFlow.

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py:301-460`

**Step 1: Add runtime construction to _init_plan_act_flow()**

After the existing collaborator assembly (around line 420), before the `PlanActFlow(...)` construction:

```python
# --- LeadAgentRuntime (opt-in via feature flag) ---
from app.domain.services.runtime.lead_agent_runtime import LeadAgentRuntime
from app.core.config_features import get_feature_flags

flags = get_feature_flags()
self._lead_agent_runtime = None
if flags.get("feature_lead_agent_runtime", False):
    self._lead_agent_runtime = LeadAgentRuntime(
        session_id=self._session_id,
        agent_id=self._agent_id,
        workspace_base="/home/ubuntu",
        memory_service=self._memory_service,
    )
```

Then pass `task_state_path` from the runtime's workspace contract to `TaskStateManager` when constructing PlanActFlow.

**Step 2: Run full test suite**

Run: `cd backend && conda activate pythinker && pytest tests/ -x --timeout=60 -q`
Expected: All existing tests PASS (no regression)

**Step 3: Commit**

```bash
git add backend/app/domain/services/agent_task_runner.py
git commit -m "feat(runtime): wire LeadAgentRuntime into AgentTaskRunner behind feature flag"
```

---

## Summary

| Task | Priority | Component | New Files | Test Count |
|------|----------|-----------|-----------|------------|
| 1 | P0 | Middleware Protocol | 2 | 5 |
| 2 | P0 | Workspace Contract | 2 | 5 |
| 3 | P0 | Clarification Gate | 2 | 4 |
| 4 | P0 | Dangling Tool Recovery | 1 | 4 |
| 5 | P0 | Delegate Tool | 2 | 5 |
| 6 | P0 | RESEARCH_TRACE Tier | 2 | 5 |
| 7 | P0 | Runtime Facade Assembly | 1 | 4 |
| 8 | P1 | Insight Promotion | 1 | 4 |
| 9 | P1 | Capability Manifest | 2 | 3 |
| 10 | P1 | Quality Gates | 1 | 4 |
| 11 | P2 | Channel Overlay | 1 | 4 |
| 12 | P2 | Skill Discovery | 1 | 4 |
| 13 | — | Full Pipeline Integration | 1 | 3 |
| 14 | — | Feature Flags | 0 | 0 |
| 15 | — | AgentTaskRunner Wiring | 0 | 0 |
| **Total** | | | **19 new files** | **54 tests** |

**All new code is behind `feature_lead_agent_runtime: bool = False` master switch.**
**Existing PlanActFlow, BaseAgent, and ExecutionAgent remain unmodified.**
**The runtime wraps them — it does not replace them.**
