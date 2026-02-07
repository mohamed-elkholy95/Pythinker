# DDD Design Enhancement, Agent Logging & Standardized Tool Calls

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix DDD layer violations, standardize agent logging with structured correlation, and create a unified tool call interface used consistently across all tools and agents.

**Architecture:** The domain layer currently imports infrastructure observability directly (7 violations). We fix this by routing all domain tracing through the existing `domain/external/observability.py` port. Agent logging is inconsistent (mix of f-strings, some with `extra=`, some without correlation IDs) — we standardize on structlog with automatic context propagation. Tool calls lack a unified execution envelope — we add a `ToolCallEnvelope` that wraps every tool invocation with consistent metadata, timing, and logging.

**Tech Stack:** Python 3.12, structlog, Pydantic v2, FastAPI, existing Protocol-based DDD ports

**Reference:** See `CODE_QUALITY_REPORT.md` for the full 266-finding analysis. This plan addresses:
- Part 3.1: DDD Layer Violations (all 8 violations)
- Part 3.2: God Classes (BaseAgent, PlanActFlow via structured decomposition)
- Part 3.3: Duplicate Systems (PressureLevel, is_research_task consolidation)
- Part 3.5: LLM Provider Issues (broken polymorphism, factory registration)
- Part 5.1: Backend Duplication (tool safety lists, datetime patterns)

---

## Phase 1: Fix Domain Layer Violations (DDD Purity)

### Task 1: Route domain flows through observability port instead of infrastructure imports

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py:108-109,1352`
- Modify: `backend/app/domain/services/flows/plan_act_graph.py:67-68`
- Modify: `backend/app/domain/services/flows/tree_of_thoughts_flow.py:54`
- Modify: `backend/app/domain/services/langgraph/flow.py:47`
- Modify: `backend/app/domain/external/observability.py` (add `record_failure_prediction`)
- Test: `backend/tests/test_ddd_layer_violations.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_ddd_layer_violations.py
"""Tests that domain layer never imports infrastructure directly."""
import ast
import os

import pytest


def _get_domain_python_files():
    """Get all Python files in domain layer."""
    domain_dir = os.path.join(os.path.dirname(__file__), "..", "app", "domain")
    domain_dir = os.path.abspath(domain_dir)
    files = []
    for root, _, filenames in os.walk(domain_dir):
        for f in filenames:
            if f.endswith(".py") and not f.startswith("__"):
                files.append(os.path.join(root, f))
    return files


FORBIDDEN_IMPORTS = [
    "app.infrastructure.",
    "app.application.",
]


def _check_imports(filepath: str) -> list[str]:
    """Check a file for forbidden imports."""
    violations = []
    with open(filepath) as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for forbidden in FORBIDDEN_IMPORTS:
                if node.module.startswith(forbidden):
                    violations.append(
                        f"{filepath}:{node.lineno} imports {node.module}"
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in FORBIDDEN_IMPORTS:
                    if alias.name.startswith(forbidden):
                        violations.append(
                            f"{filepath}:{node.lineno} imports {alias.name}"
                        )
    return violations


def test_domain_layer_has_no_infrastructure_imports():
    """Domain layer must not import from infrastructure or application."""
    all_violations = []
    for filepath in _get_domain_python_files():
        all_violations.extend(_check_imports(filepath))

    if all_violations:
        msg = "Domain layer violations found:\n" + "\n".join(all_violations)
        pytest.fail(msg)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && pytest tests/test_ddd_layer_violations.py -v --timeout=30`
Expected: FAIL listing the 7 infrastructure imports in domain

**Step 3: Add `record_failure_prediction` to the MetricsPort**

In `backend/app/domain/external/observability.py`, the `MetricsPort` protocol already has `record_failure_prediction`. It's already correct. We just need to ensure domain services use the port's `get_tracer()` instead of infrastructure's.

**Step 4: Fix `plan_act.py` imports**

Replace:
```python
from app.infrastructure.observability import SpanKind, get_tracer
from app.infrastructure.observability.prometheus_metrics import record_failure_prediction
```
With:
```python
from app.domain.external.observability import get_tracer
```

And later in the file where `SpanKind` is used inline (line ~1352):
```python
from app.infrastructure.observability.spans import SpanKind, SpanStatus
```
Replace with:
```python
# SpanKind/SpanStatus are just string constants; use string literals instead
```

For `record_failure_prediction`, inject via the `MetricsPort` that's already available on the flow, or call `self._metrics.record_failure_prediction(...)`.

**Step 5: Fix `plan_act_graph.py` imports**

Replace:
```python
from app.infrastructure.observability import get_tracer
from app.infrastructure.observability.prometheus_metrics import record_failure_prediction
```
With:
```python
from app.domain.external.observability import get_tracer
```

Route `record_failure_prediction` through the MetricsPort.

**Step 6: Fix `tree_of_thoughts_flow.py` imports**

Replace:
```python
from app.infrastructure.observability import get_tracer
```
With:
```python
from app.domain.external.observability import get_tracer
```

**Step 7: Fix `langgraph/flow.py` imports**

Replace:
```python
from app.infrastructure.observability import get_tracer
```
With:
```python
from app.domain.external.observability import get_tracer
```

**Step 8: Run the test to verify it passes**

Run: `cd backend && pytest tests/test_ddd_layer_violations.py -v --timeout=30`
Expected: PASS

**Step 9: Run full test suite to verify no regressions**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass (except 2 known pre-existing failures)

**Step 10: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py backend/app/domain/services/flows/plan_act_graph.py backend/app/domain/services/flows/tree_of_thoughts_flow.py backend/app/domain/services/langgraph/flow.py backend/tests/test_ddd_layer_violations.py
git commit -m "fix(ddd): route domain layer through observability port, remove infrastructure imports"
```

---

### Task 2: Fix `agent_task_runner.py` circular dependency (domain → application)

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Test: Already covered by `test_ddd_layer_violations.py`

**Step 1: Read `agent_task_runner.py` to understand the UsageService dependency**

Read the file to see how `get_usage_service` is used.

**Step 2: Remove the application layer import**

The domain should not call application services directly. Options:
1. Move the usage tracking call to the application layer (caller of agent_task_runner)
2. Create a domain port for usage tracking

Choose option 1: remove the import and the usage tracking call, letting the application layer handle it. The caller (`agent_service.py`) already has access to `UsageService`.

**Step 3: Run the DDD violations test**

Run: `cd backend && pytest tests/test_ddd_layer_violations.py -v --timeout=30`
Expected: PASS with zero violations

**Step 4: Commit**

```bash
git add backend/app/domain/services/agent_task_runner.py
git commit -m "fix(ddd): remove application layer import from domain agent_task_runner"
```

---

## Phase 2: Standardize Agent Logging

### Task 3: Create domain logging port for structured agent logging

**Files:**
- Create: `backend/app/domain/external/logging.py`
- Test: `backend/tests/test_domain_logging.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_domain_logging.py
"""Tests for domain logging port."""
from app.domain.external.logging import AgentLogger, get_agent_logger


def test_agent_logger_protocol():
    """AgentLogger provides structured logging methods."""
    logger = get_agent_logger("test-agent", session_id="s1")
    assert hasattr(logger, "tool_started")
    assert hasattr(logger, "tool_completed")
    assert hasattr(logger, "tool_failed")
    assert hasattr(logger, "agent_step")
    assert hasattr(logger, "workflow_transition")


def test_agent_logger_logs_tool_started(caplog):
    """tool_started emits structured log."""
    import logging
    with caplog.at_level(logging.INFO):
        logger = get_agent_logger("agent-1", session_id="s1")
        logger.tool_started("browser_navigate", "tc-001", {"url": "https://example.com"})
    assert "tool_started" in caplog.text or "browser_navigate" in caplog.text
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_domain_logging.py -v --timeout=30`
Expected: FAIL (module not found)

**Step 3: Implement the domain logging port**

```python
# backend/app/domain/external/logging.py
"""Domain Logging Port - Structured agent logging interface.

Provides a standardized logging interface for agent operations,
tool calls, and workflow transitions with automatic context binding.
"""

import logging
import time
from typing import Any


class AgentLogger:
    """Structured logger for agent operations.

    Binds agent_id and session_id to all log entries automatically.
    Provides domain-specific logging methods for tool calls,
    agent steps, and workflow transitions.
    """

    def __init__(self, agent_id: str, session_id: str | None = None):
        self._logger = logging.getLogger(f"agent.{agent_id}")
        self._agent_id = agent_id
        self._session_id = session_id

    def _extra(self, **kwargs: Any) -> dict[str, Any]:
        """Build extra dict with automatic context fields."""
        base = {"agent_id": self._agent_id}
        if self._session_id:
            base["session_id"] = self._session_id
        base.update(kwargs)
        return base

    def tool_started(
        self,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> float:
        """Log tool execution start. Returns start_time for duration calc."""
        start = time.time()
        safe_args = _truncate_args(arguments) if arguments else {}
        self._logger.info(
            "tool_started: %s",
            tool_name,
            extra=self._extra(
                event="tool_started",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                arguments=safe_args,
            ),
        )
        return start

    def tool_completed(
        self,
        tool_name: str,
        tool_call_id: str,
        start_time: float,
        success: bool,
        message: str | None = None,
    ) -> None:
        """Log tool execution completion with duration."""
        duration_ms = (time.time() - start_time) * 1000
        log_fn = self._logger.info if success else self._logger.warning
        log_fn(
            "tool_completed: %s (%.0fms, success=%s)",
            tool_name,
            duration_ms,
            success,
            extra=self._extra(
                event="tool_completed",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                duration_ms=round(duration_ms, 2),
                success=success,
                message=message[:200] if message else None,
            ),
        )

    def tool_failed(
        self,
        tool_name: str,
        tool_call_id: str,
        error: str,
        start_time: float | None = None,
    ) -> None:
        """Log tool execution failure."""
        duration_ms = (time.time() - start_time) * 1000 if start_time else None
        self._logger.error(
            "tool_failed: %s - %s",
            tool_name,
            error[:200],
            extra=self._extra(
                event="tool_failed",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error=error[:500],
                duration_ms=round(duration_ms, 2) if duration_ms else None,
            ),
        )

    def agent_step(
        self,
        step: str,
        iteration: int,
        token_usage: dict[str, int] | None = None,
    ) -> None:
        """Log an agent iteration/step."""
        self._logger.info(
            "agent_step: %s (iter=%d)",
            step,
            iteration,
            extra=self._extra(
                event="agent_step",
                step=step,
                iteration=iteration,
                token_usage=token_usage,
            ),
        )

    def workflow_transition(
        self,
        from_state: str,
        to_state: str,
        reason: str | None = None,
    ) -> None:
        """Log a workflow state transition."""
        self._logger.info(
            "workflow_transition: %s -> %s",
            from_state,
            to_state,
            extra=self._extra(
                event="workflow_transition",
                from_state=from_state,
                to_state=to_state,
                reason=reason,
            ),
        )

    def security_event(
        self,
        action: str,
        tool_name: str,
        reason: str,
    ) -> None:
        """Log a security-related event (blocked tool, risk assessment)."""
        self._logger.warning(
            "security_event: %s on %s - %s",
            action,
            tool_name,
            reason,
            extra=self._extra(
                event="security_event",
                action=action,
                tool_name=tool_name,
                reason=reason,
            ),
        )

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Structured debug log."""
        self._logger.debug(msg, extra=self._extra(**kwargs))

    def info(self, msg: str, **kwargs: Any) -> None:
        """Structured info log."""
        self._logger.info(msg, extra=self._extra(**kwargs))

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Structured warning log."""
        self._logger.warning(msg, extra=self._extra(**kwargs))

    def error(self, msg: str, **kwargs: Any) -> None:
        """Structured error log."""
        self._logger.error(msg, extra=self._extra(**kwargs))


def _truncate_args(args: dict[str, Any], max_value_len: int = 100) -> dict[str, Any]:
    """Truncate argument values for safe logging."""
    result = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > max_value_len:
            result[k] = v[:max_value_len] + "..."
        else:
            result[k] = v
    return result


def get_agent_logger(agent_id: str, session_id: str | None = None) -> AgentLogger:
    """Factory function for AgentLogger.

    Args:
        agent_id: Agent identifier for log correlation
        session_id: Optional session identifier

    Returns:
        AgentLogger bound to the given agent context
    """
    return AgentLogger(agent_id, session_id)
```

**Step 4: Run the test to verify it passes**

Run: `cd backend && pytest tests/test_domain_logging.py -v --timeout=30`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/external/logging.py backend/tests/test_domain_logging.py
git commit -m "feat(logging): add domain AgentLogger port for structured agent logging"
```

---

### Task 4: Integrate AgentLogger into BaseAgent

**Files:**
- Modify: `backend/app/domain/services/agents/base.py`
- Test: `backend/tests/test_domain_logging.py` (extend)

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_domain_logging.py
def test_agent_logger_integration():
    """AgentLogger can be imported and used from domain layer."""
    from app.domain.external.logging import AgentLogger
    logger = AgentLogger("test-agent-123", session_id="session-456")
    start = logger.tool_started("shell_exec", "tc-001", {"command": "ls -la"})
    assert isinstance(start, float)
    logger.tool_completed("shell_exec", "tc-001", start, success=True, message="ok")
    logger.agent_step("processing_response", iteration=3)
    logger.workflow_transition("planning", "executing", reason="plan approved")
    logger.security_event("blocked", "shell_exec", "dangerous command")
```

**Step 2: Run test to verify it passes (test is for the port itself)**

Run: `cd backend && pytest tests/test_domain_logging.py::test_agent_logger_integration -v --timeout=30`
Expected: PASS

**Step 3: Integrate AgentLogger into BaseAgent.__init__**

In `backend/app/domain/services/agents/base.py`, add in `__init__`:

```python
from app.domain.external.logging import get_agent_logger

# In __init__, after self._agent_id is set:
self._log = get_agent_logger(self._agent_id, session_id=getattr(self, '_session_id', None))
```

Then replace key logging calls in BaseAgent:

1. Tool invocation started → `self._log.tool_started(...)`
2. Tool execution result → `self._log.tool_completed(...)` / `self._log.tool_failed(...)`
3. Security blocked → `self._log.security_event(...)`
4. Agent iteration → `self._log.agent_step(...)`

**Step 4: Replace scattered logger calls in BaseAgent with self._log**

Replace at least these key spots:
- `logger.info("Tool invocation started", ...)` → `start_time = self._log.tool_started(function_name, tool_call_id, arguments)`
- `logger.exception(f"Tool execution failed, ...")` → `self._log.tool_failed(function_name, tool_call_id, str(e), start_time)`
- `logger.warning(f"Security blocked tool ...")` → `self._log.security_event("blocked", function_name, security_assessment.reason)`
- `logger.info(f"High-risk tool call: ...")` → `self._log.security_event("high_risk", function_name, security_assessment.reason)`

**Step 5: Run tests to verify no regressions**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass (except known failures)

**Step 6: Commit**

```bash
git add backend/app/domain/services/agents/base.py backend/tests/test_domain_logging.py
git commit -m "refactor(agents): integrate AgentLogger into BaseAgent for structured logging"
```

---

### Task 5: Integrate AgentLogger into PlanActFlow and LangGraph flow

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Modify: `backend/app/domain/services/langgraph/flow.py`

**Step 1: Add AgentLogger to PlanActFlow**

In `plan_act.py`, after `self._agent_id` is set:
```python
from app.domain.external.logging import get_agent_logger
self._log = get_agent_logger(self._agent_id)
```

Replace scattered `logger.info/debug/warning` calls with `self._log.info/debug/warning`.
Replace workflow state changes with `self._log.workflow_transition(from_state, to_state)`.

**Step 2: Add AgentLogger to LangGraphFlow**

Same pattern in `langgraph/flow.py`.

**Step 3: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py backend/app/domain/services/langgraph/flow.py
git commit -m "refactor(flows): integrate AgentLogger into PlanActFlow and LangGraphFlow"
```

---

## Phase 3: Standardize Tool Call Interface

### Task 6: Create ToolCallEnvelope for standardized tool execution metadata

**Files:**
- Create: `backend/app/domain/models/tool_call.py`
- Test: `backend/tests/test_tool_call_envelope.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_tool_call_envelope.py
"""Tests for standardized tool call envelope."""
from app.domain.models.tool_call import ToolCallEnvelope, ToolCallStatus


def test_tool_call_envelope_creation():
    """ToolCallEnvelope captures tool call metadata."""
    envelope = ToolCallEnvelope(
        tool_call_id="tc-001",
        tool_name="browser",
        function_name="browser_navigate",
        arguments={"url": "https://example.com"},
    )
    assert envelope.status == ToolCallStatus.PENDING
    assert envelope.tool_call_id == "tc-001"
    assert envelope.duration_ms is None


def test_tool_call_envelope_mark_started():
    """mark_started transitions to RUNNING."""
    envelope = ToolCallEnvelope(
        tool_call_id="tc-001",
        tool_name="shell",
        function_name="shell_exec",
        arguments={"command": "ls"},
    )
    envelope.mark_started()
    assert envelope.status == ToolCallStatus.RUNNING
    assert envelope.started_at is not None


def test_tool_call_envelope_mark_completed():
    """mark_completed captures duration and result."""
    envelope = ToolCallEnvelope(
        tool_call_id="tc-001",
        tool_name="file",
        function_name="file_read",
        arguments={"path": "/workspace/test.py"},
    )
    envelope.mark_started()
    envelope.mark_completed(success=True, message="File read successfully")
    assert envelope.status == ToolCallStatus.COMPLETED
    assert envelope.duration_ms is not None
    assert envelope.duration_ms >= 0
    assert envelope.success is True


def test_tool_call_envelope_mark_failed():
    """mark_failed captures error info."""
    envelope = ToolCallEnvelope(
        tool_call_id="tc-001",
        tool_name="shell",
        function_name="shell_exec",
        arguments={"command": "rm -rf /"},
    )
    envelope.mark_started()
    envelope.mark_failed(error="Command blocked by security")
    assert envelope.status == ToolCallStatus.FAILED
    assert envelope.error == "Command blocked by security"
    assert envelope.success is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_tool_call_envelope.py -v --timeout=30`
Expected: FAIL (module not found)

**Step 3: Implement ToolCallEnvelope**

```python
# backend/app/domain/models/tool_call.py
"""Standardized tool call envelope for consistent tool execution tracking.

Every tool invocation flows through this envelope, providing:
- Consistent metadata (timing, status, arguments)
- Uniform logging fields
- Status lifecycle (PENDING -> RUNNING -> COMPLETED/FAILED)
"""

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolCallStatus(str, Enum):
    """Tool call lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ToolCallEnvelope(BaseModel):
    """Envelope wrapping every tool call with standardized metadata.

    Attributes:
        tool_call_id: Unique identifier for this tool call
        tool_name: Category name of the tool (browser, shell, file, etc.)
        function_name: Specific function being called
        arguments: Arguments passed to the tool
        status: Current lifecycle status
        started_at: Epoch time when execution started
        completed_at: Epoch time when execution finished
        duration_ms: Execution duration in milliseconds
        success: Whether execution succeeded
        error: Error message if failed
        result_summary: Short summary of result for logging
    """

    tool_call_id: str
    tool_name: str
    function_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: ToolCallStatus = ToolCallStatus.PENDING
    started_at: float | None = None
    completed_at: float | None = None
    duration_ms: float | None = None
    success: bool | None = None
    error: str | None = None
    result_summary: str | None = None

    def mark_started(self) -> None:
        """Transition to RUNNING status."""
        self.status = ToolCallStatus.RUNNING
        self.started_at = time.time()

    def mark_completed(self, success: bool, message: str | None = None) -> None:
        """Transition to COMPLETED status with result."""
        self.status = ToolCallStatus.COMPLETED
        self.completed_at = time.time()
        self.success = success
        if self.started_at:
            self.duration_ms = round((self.completed_at - self.started_at) * 1000, 2)
        self.result_summary = message[:200] if message else None

    def mark_failed(self, error: str) -> None:
        """Transition to FAILED status with error."""
        self.status = ToolCallStatus.FAILED
        self.completed_at = time.time()
        self.success = False
        self.error = error[:500]
        if self.started_at:
            self.duration_ms = round((self.completed_at - self.started_at) * 1000, 2)

    def mark_blocked(self, reason: str) -> None:
        """Transition to BLOCKED status (security block)."""
        self.status = ToolCallStatus.BLOCKED
        self.success = False
        self.error = reason

    def to_log_dict(self) -> dict[str, Any]:
        """Convert to dict suitable for structured logging extra fields."""
        d: dict[str, Any] = {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "function_name": self.function_name,
            "status": self.status.value,
        }
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        if self.success is not None:
            d["success"] = self.success
        if self.error:
            d["error"] = self.error
        return d
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_tool_call_envelope.py -v --timeout=30`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/models/tool_call.py backend/tests/test_tool_call_envelope.py
git commit -m "feat(tools): add ToolCallEnvelope for standardized tool call tracking"
```

---

### Task 7: Integrate ToolCallEnvelope into BaseAgent tool execution

**Files:**
- Modify: `backend/app/domain/services/agents/base.py`

**Step 1: Import ToolCallEnvelope in BaseAgent**

At the top of `base.py`:
```python
from app.domain.models.tool_call import ToolCallEnvelope
```

**Step 2: Wrap tool calls in BaseAgent with ToolCallEnvelope**

In the tool execution section of BaseAgent (the method that handles `tool_use` blocks), wrap each tool call:

```python
# Create envelope for this tool call
envelope = ToolCallEnvelope(
    tool_call_id=tool_call_id,
    tool_name=tool.name,
    function_name=function_name,
    arguments=arguments,
)

# Log start via AgentLogger
start_time = self._log.tool_started(function_name, tool_call_id, arguments)
envelope.mark_started()

try:
    result = await tool.invoke_function(function_name, **arguments)
    envelope.mark_completed(success=result.success, message=result.message)
    self._log.tool_completed(function_name, tool_call_id, start_time, result.success, result.message)
except Exception as e:
    envelope.mark_failed(error=str(e))
    self._log.tool_failed(function_name, tool_call_id, str(e), start_time)
    raise
```

**Step 3: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/domain/services/agents/base.py
git commit -m "refactor(agents): wrap tool calls with ToolCallEnvelope in BaseAgent"
```

---

### Task 8: Add ToolCallEnvelope to ToolEvent for consistent event sourcing

**Files:**
- Modify: `backend/app/domain/models/event.py`

**Step 1: Extend ToolEvent to accept envelope data**

In `event.py`, add an optional `envelope` field to `ToolEvent`:

```python
from app.domain.models.tool_call import ToolCallStatus

class ToolEvent(BaseEvent):
    # ... existing fields ...

    # Standardized envelope fields (replaces ad-hoc tracking)
    call_status: ToolCallStatus | None = None  # Lifecycle status from envelope
```

This is a light touch — we don't replace the existing fields, just add the new status enum that's more precise than the existing `ToolStatus` (which only has CALLING/CALLED).

**Step 2: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass

**Step 3: Commit**

```bash
git add backend/app/domain/models/event.py
git commit -m "feat(events): add ToolCallStatus to ToolEvent from standardized envelope"
```

---

## Phase 4: Standardize Tool Logging Across All Tools

### Task 9: Add structured logging to BaseTool.invoke_function

**Files:**
- Modify: `backend/app/domain/services/tools/base.py`

**Step 1: Update invoke_function to use structured logging**

The `log_tool_start` and `log_tool_end` functions already exist in `base.py` but aren't used consistently by `invoke_function`. Wire them in:

In `invoke_function`, after the method is found:

```python
start_time = log_tool_start(self.name, function_name, filtered_kwargs)

# ... existing execution logic ...

log_tool_end(self.name, function_name, start_time, result.success, result.message)
```

**Step 2: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass

**Step 3: Commit**

```bash
git add backend/app/domain/services/tools/base.py
git commit -m "refactor(tools): wire structured logging into BaseTool.invoke_function"
```

---

### Task 10: Ensure correlation IDs propagate to agent operations

**Files:**
- Modify: `backend/app/application/services/agent_service.py`

**Step 1: Set structured logging context vars when agent runs**

In `agent_service.py`, in the method that starts agent execution (the SSE streaming handler), add context binding:

```python
from app.infrastructure.structured_logging import set_session_id, set_agent_id

# At the start of agent execution:
set_session_id(session_id)
set_agent_id(agent_id)
```

This ensures all downstream logs from agents, tools, and flows automatically include `session_id` and `agent_id` via structlog's correlation ID processor.

**Step 2: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass

**Step 3: Commit**

```bash
git add backend/app/application/services/agent_service.py
git commit -m "feat(logging): propagate session_id and agent_id correlation IDs to agent operations"
```

---

## Phase 5: Verification & Cleanup

### Task 11: Run full verification suite

**Step 1: Run backend lint**

Run: `cd backend && ruff check app/domain/external/logging.py app/domain/models/tool_call.py app/domain/services/agents/base.py app/domain/services/flows/plan_act.py`

Fix any lint issues.

**Step 2: Run full backend tests**

Run: `cd backend && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && pytest tests/ -q --timeout=30`
Expected: All pass (except 2 known pre-existing failures)

**Step 3: Run DDD violations test specifically**

Run: `cd backend && pytest tests/test_ddd_layer_violations.py -v --timeout=30`
Expected: PASS — zero domain layer violations

**Step 4: Run frontend checks (verify no breakage)**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: PASS

**Step 5: Final commit with any cleanup**

```bash
git add -A
git commit -m "chore: lint fixes and verification for DDD enhancement"
```

---

## Phase 6: Application Layer DDD Violations (from CODE_QUALITY_REPORT.md §3.1)

### Task 12: Fix application layer importing from interfaces layer

**Files:**
- Modify: `backend/app/application/services/agent_service.py:27-34`
- Test: `backend/tests/test_ddd_layer_violations.py` (extend to cover app→interfaces)

**Step 1: Extend the DDD violations test to cover application layer**

Add a new test function in `test_ddd_layer_violations.py`:

```python
def _get_application_python_files():
    """Get all Python files in application layer."""
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app", "application")
    app_dir = os.path.abspath(app_dir)
    files = []
    for root, _, filenames in os.walk(app_dir):
        for f in filenames:
            if f.endswith(".py") and not f.startswith("__"):
                files.append(os.path.join(root, f))
    return files


def test_application_layer_does_not_import_interfaces():
    """Application layer must not import from interfaces layer."""
    violations = []
    for filepath in _get_application_python_files():
        with open(filepath) as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("app.interfaces."):
                    violations.append(f"{filepath}:{node.lineno} imports {node.module}")
    if violations:
        pytest.fail("Application→Interfaces violations:\n" + "\n".join(violations))
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_ddd_layer_violations.py::test_application_layer_does_not_import_interfaces -v --timeout=30`
Expected: FAIL — `agent_service.py` imports `FileViewResponse`, `ShellViewResponse`, `WorkspaceManifest` from interfaces

**Step 3: Move shared response types to domain models or application DTOs**

In `agent_service.py`, the interface imports are for response schemas used in SSE event formatting. Move these type definitions into `backend/app/application/schemas/` or create domain-side equivalents that the interfaces layer also uses.

The cleanest fix: create thin DTOs in the application layer that both the application service and the interfaces layer can use.

```python
# In agent_service.py, replace:
# from app.interfaces.schemas.xxx import FileViewResponse, ShellViewResponse
# With domain/application-layer equivalents that don't cross the boundary
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_ddd_layer_violations.py -v --timeout=30`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/application/services/agent_service.py backend/tests/test_ddd_layer_violations.py
git commit -m "fix(ddd): remove application→interfaces imports in agent_service"
```

---

### Task 13: Fix application layer direct infrastructure imports

**Files:**
- Modify: `backend/app/application/services/token_service.py:12`
- Modify: `backend/app/application/services/skill_service.py:12`

**Context from CODE_QUALITY_REPORT §3.1:**
- `token_service.py` imports `get_redis` directly from infrastructure
- `skill_service.py` imports `MongoSkillRepository` directly

**Step 1: Fix token_service.py — inject Redis via constructor**

Replace direct `from app.infrastructure.storage.redis import get_redis` with constructor injection. The token service should receive a cache/store interface, not reach into infrastructure.

**Step 2: Fix skill_service.py — use abstract SkillRepository**

Replace `from app.infrastructure.repositories.mongo_skill_repository import MongoSkillRepository` with the domain `SkillRepository` protocol, injected via constructor.

**Step 3: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/application/services/token_service.py backend/app/application/services/skill_service.py
git commit -m "fix(ddd): inject dependencies in token_service and skill_service instead of importing infrastructure"
```

---

### Task 14: Fix PlaywrightBrowser importing concrete LLM

**Files:**
- Modify: `backend/app/infrastructure/external/browser/playwright_browser.py:15`

**Context from CODE_QUALITY_REPORT §3.1:**
- Imports `OpenAILLM` directly instead of using the `LLM` Protocol

**Step 1: Replace concrete import with Protocol**

Replace:
```python
from app.infrastructure.external.llm.openai_llm import OpenAILLM
```
With:
```python
from app.domain.external.llm import LLM
```

Update the type annotations in the class to use `LLM` protocol instead of `OpenAILLM`.

**Step 2: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass

**Step 3: Commit**

```bash
git add backend/app/infrastructure/external/browser/playwright_browser.py
git commit -m "fix(ddd): use LLM protocol instead of concrete OpenAILLM in PlaywrightBrowser"
```

---

### Task 15: Fix LLM factory — register Anthropic provider and fix broken polymorphism

**Files:**
- Modify: `backend/app/infrastructure/external/llm/factory.py`
- Modify: `backend/app/infrastructure/external/llm/anthropic_llm.py`
- Modify: `backend/app/infrastructure/external/llm/ollama_llm.py`

**Context from CODE_QUALITY_REPORT §3.5:**
- Anthropic not registered in factory (decorator never fires because module never imported)
- `anthropic_llm.py` and `ollama_llm.py` define local `TokenLimitExceededError` instead of importing domain one
- Callers catching domain error won't catch provider-specific errors

**Step 1: Register Anthropic in factory.py**

In `factory.py`, add explicit import:
```python
import app.infrastructure.external.llm.anthropic_llm  # noqa: F401 - triggers @register decorator
```

**Step 2: Fix TokenLimitExceededError polymorphism**

In both `anthropic_llm.py` and `ollama_llm.py`, replace local `TokenLimitExceededError` definitions with:
```python
from app.domain.services.agents.error_handler import TokenLimitExceededError
```

**Step 3: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/infrastructure/external/llm/factory.py backend/app/infrastructure/external/llm/anthropic_llm.py backend/app/infrastructure/external/llm/ollama_llm.py
git commit -m "fix(llm): register Anthropic provider in factory and fix TokenLimitExceededError polymorphism"
```

---

## Phase 7: Consolidate Duplicate Systems (from CODE_QUALITY_REPORT.md §3.3)

### Task 16: Consolidate duplicate PressureLevel enums

**Files:**
- Modify: `backend/app/domain/services/agents/token_manager.py`
- Modify: `backend/app/domain/services/agents/memory_manager.py`

**Context from CODE_QUALITY_REPORT §3.3:**
- `PressureLevel` exists in both `token_manager.py` and `memory_manager.py` with incompatible values

**Step 1: Create canonical PressureLevel in domain models**

Create a single `PressureLevel` enum in `backend/app/domain/models/pressure.py`:

```python
from enum import Enum

class PressureLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
```

**Step 2: Update both token_manager.py and memory_manager.py to import from canonical location**

Replace local definitions with:
```python
from app.domain.models.pressure import PressureLevel
```

**Step 3: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/domain/models/pressure.py backend/app/domain/services/agents/token_manager.py backend/app/domain/services/agents/memory_manager.py
git commit -m "refactor: consolidate duplicate PressureLevel enums into domain models"
```

---

### Task 17: Consolidate duplicate is_research_task() implementations

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py`
- Modify: `backend/app/domain/services/prompts/research.py`

**Context from CODE_QUALITY_REPORT §3.3:**
- Two `is_research_task()` functions with different indicator lists

**Step 1: Create canonical implementation**

Add a single `is_research_task()` in `backend/app/domain/services/tools/task_classifier.py` (or an existing appropriate module) that merges both keyword lists.

**Step 2: Update both callers to use the canonical implementation**

**Step 3: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/domain/services/agents/execution.py backend/app/domain/services/prompts/research.py
git commit -m "refactor: consolidate duplicate is_research_task() into single canonical implementation"
```

---

## Phase 8: Final Verification

### Task 18: Comprehensive verification across all changes

**Step 1: Run all DDD violation tests**

Run: `cd backend && pytest tests/test_ddd_layer_violations.py -v --timeout=30`
Expected: PASS — zero violations in domain AND application layers

**Step 2: Run full backend test suite**

Run: `cd backend && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && pytest tests/ -q --timeout=30`
Expected: All pass (except 2 known pre-existing failures: test_semantic_matching, test_structured_logging)

**Step 3: Run backend lint**

Run: `cd backend && ruff check . --select E,F,W`
Expected: No new errors from our changes

**Step 4: Run frontend checks (verify no breakage)**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: PASS

**Step 5: Verify git status is clean**

Run: `git diff --stat` to review all changes.

**Step 6: Final commit if needed**

```bash
git commit -m "chore: final verification and cleanup for DDD enhancement"
```

---

## Summary of Changes

| Area | Before | After |
|------|--------|-------|
| Domain→Infra imports | 7 violations (observability) | 0 violations |
| Domain→App imports | 1 violation (agent_task_runner) | 0 violations |
| App→Interfaces imports | 1 violation (agent_service) | 0 violations |
| App→Infra direct imports | 2 violations (token_service, skill_service) | Injected via DI |
| Agent logging | Scattered `logger.info/warning` with f-strings | Structured `AgentLogger` with auto-correlated context |
| Tool call tracking | Ad-hoc timing in some places | `ToolCallEnvelope` with lifecycle states |
| Correlation IDs | Set at HTTP layer only | Propagated to agent_id, session_id in all agent/tool logs |
| Tool execution logging | Inconsistent across tools | `log_tool_start`/`log_tool_end` in `BaseTool.invoke_function` |
| Duplicate PressureLevel | 2 incompatible enums | 1 canonical enum in domain models |
| Duplicate is_research_task | 2 implementations with different keywords | 1 canonical function |
| LLM factory | Anthropic unregistered, broken polymorphism | All providers registered, domain error reused |
| PlaywrightBrowser | Imports concrete OpenAILLM | Uses LLM Protocol |

## Files Created (5)
- `backend/app/domain/external/logging.py` — AgentLogger port
- `backend/app/domain/models/tool_call.py` — ToolCallEnvelope model
- `backend/app/domain/models/pressure.py` — Canonical PressureLevel enum
- `backend/tests/test_ddd_layer_violations.py` — DDD purity tests (domain + application)
- `backend/tests/test_domain_logging.py` — AgentLogger tests
- `backend/tests/test_tool_call_envelope.py` — ToolCallEnvelope tests

## Files Modified (18)
- `backend/app/domain/services/agents/base.py` — Use AgentLogger + ToolCallEnvelope
- `backend/app/domain/services/agents/token_manager.py` — Use canonical PressureLevel
- `backend/app/domain/services/agents/memory_manager.py` — Use canonical PressureLevel
- `backend/app/domain/services/agents/execution.py` — Use canonical is_research_task
- `backend/app/domain/services/flows/plan_act.py` — Fix imports, use AgentLogger
- `backend/app/domain/services/flows/plan_act_graph.py` — Fix imports
- `backend/app/domain/services/flows/tree_of_thoughts_flow.py` — Fix imports
- `backend/app/domain/services/langgraph/flow.py` — Fix imports
- `backend/app/domain/services/agent_task_runner.py` — Remove circular import
- `backend/app/domain/services/prompts/research.py` — Use canonical is_research_task
- `backend/app/domain/services/tools/base.py` — Wire structured logging
- `backend/app/domain/models/event.py` — Add ToolCallStatus
- `backend/app/application/services/agent_service.py` — Fix imports, add correlation IDs
- `backend/app/application/services/token_service.py` — Inject Redis via DI
- `backend/app/application/services/skill_service.py` — Use abstract SkillRepository
- `backend/app/infrastructure/external/browser/playwright_browser.py` — Use LLM Protocol
- `backend/app/infrastructure/external/llm/factory.py` — Register Anthropic
- `backend/app/infrastructure/external/llm/anthropic_llm.py` — Use domain TokenLimitExceededError
- `backend/app/infrastructure/external/llm/ollama_llm.py` — Use domain TokenLimitExceededError
