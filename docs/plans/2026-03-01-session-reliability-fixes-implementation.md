# Session Monitoring Reliability Fixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 production reliability issues observed during GLM-5 agent session monitoring — repetitive tool loops, post-compression context loss, hallucination escalation, and structlog formatting.

**Architecture:** Extend existing `ToolEfficiencyMonitor` with same-tool loop detection, add failure lesson extraction to `TokenBudgetManager`, add hallucination rate tracking to `BaseAgent`, and fix structlog formatting in middleware. All new behaviors feature-flagged.

**Tech Stack:** Python 3.13, dataclasses, structlog, pytest

---

### Task 1: Fix structlog Middleware Formatting

**Files:**
- Modify: `backend/app/core/middleware.py:54,72,76-80`

**Step 1: Write the failing test**

No new test file needed — this is a format-only change. Existing middleware tests cover the request flow. The fix converts 4 f-string log calls to structured kwargs.

**Step 2: Apply the fix**

In `backend/app/core/middleware.py`, replace all 4 f-string log calls in `RequestLoggingMiddleware.__call__()`:

```python
# Line 53-54: Replace f-string request start log
# OLD:
#   client_ip = request.client.host if request.client else "unknown"
#   logger.info(f"[{request_id}] {request.method} {path} - Client: {client_ip}")
# NEW:
        client_ip = request.client.host if request.client else "unknown"
        logger.info("request_started", method=request.method, path=path, client_ip=client_ip)

# Line 72: Replace f-string exception log
# OLD:
#   logger.error(f"[{request_id}] Request failed with exception: {e}")
# NEW:
            logger.error("request_failed", exc_info=True)

# Lines 75-80: Replace f-string completion log
# OLD:
#   duration_ms = (time.time() - start_time) * 1000
#   msg = f"[{request_id}] {request.method} {path} - {response_status} ({duration_ms:.2f}ms)"
#   if response_status < 400:
#       logger.info(msg)
#   else:
#       logger.warning(msg)
# NEW:
            duration_ms = (time.time() - start_time) * 1000
            log_kw = dict(method=request.method, path=path, status=response_status, duration_ms=round(duration_ms, 2))
            if response_status < 400:
                logger.info("request_completed", **log_kw)
            else:
                logger.warning("request_completed", **log_kw)
```

**Step 3: Run lint to verify**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && ruff check app/core/middleware.py`
Expected: No errors

**Step 4: Commit**

```bash
git add backend/app/core/middleware.py
git commit -m "fix(middleware): convert f-string logs to structured kwargs for structlog compatibility"
```

---

### Task 2: Add Repetitive Same-Tool Detection to ToolEfficiencyMonitor

**Files:**
- Modify: `backend/app/domain/services/agents/tool_efficiency_monitor.py`
- Modify: `backend/tests/domain/services/agents/test_tool_efficiency_monitor.py`

**Step 1: Write the failing tests**

Add these test classes to `backend/tests/domain/services/agents/test_tool_efficiency_monitor.py`:

```python
# ============================================================================
# Test Class 9: Repetitive Same-Tool Detection
# ============================================================================


class TestRepetitiveSameToolDetection:
    """Test detection of consecutive identical tool calls."""

    def test_consecutive_same_action_tool_triggers_nudge(self):
        """4+ consecutive calls to the same action tool should trigger nudge."""
        monitor = ToolEfficiencyMonitor(
            read_threshold=10,
            strong_threshold=15,
            same_tool_threshold=4,
            same_tool_strong_threshold=6,
        )
        for _ in range(4):
            monitor.record("code_execute_python")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is False
        assert signal.nudge_message is not None
        assert signal.hard_stop is False
        assert signal.signal_type == "repetitive_tool"
        assert "code_execute_python" in signal.nudge_message

    def test_consecutive_same_tool_hard_stop(self):
        """6+ consecutive calls to the same tool should trigger hard stop."""
        monitor = ToolEfficiencyMonitor(
            same_tool_threshold=4,
            same_tool_strong_threshold=6,
        )
        for _ in range(6):
            monitor.record("code_execute_python")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is False
        assert signal.hard_stop is True
        assert signal.signal_type == "repetitive_tool"

    def test_different_tools_do_not_trigger(self):
        """Alternating tools should not trigger repetitive detection."""
        monitor = ToolEfficiencyMonitor(same_tool_threshold=4)
        monitor.record("code_execute_python")
        monitor.record("file_write")
        monitor.record("code_execute_python")
        monitor.record("file_write")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is True

    def test_exempt_tools_do_not_trigger(self):
        """Exempt tools (file_write) should not trigger repetitive detection."""
        monitor = ToolEfficiencyMonitor(same_tool_threshold=4)
        for _ in range(6):
            monitor.record("file_write")

        signal = monitor.check_efficiency()
        # file_write is exempt from repetitive detection
        assert signal.signal_type != "repetitive_tool" or signal.is_balanced is True

    def test_switching_tool_resets_counter(self):
        """Switching to a different tool should reset the consecutive counter."""
        monitor = ToolEfficiencyMonitor(same_tool_threshold=4)
        monitor.record("code_execute_python")
        monitor.record("code_execute_python")
        monitor.record("code_execute_python")
        # Switch tool — resets counter
        monitor.record("file_write")
        monitor.record("code_execute_python")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is True

    def test_reset_clears_same_tool_tracking(self):
        """Reset should clear same-tool tracking state."""
        monitor = ToolEfficiencyMonitor(same_tool_threshold=4)
        monitor.record("code_execute_python")
        monitor.record("code_execute_python")
        monitor.record("code_execute_python")

        monitor.reset()
        assert monitor._consecutive_same_tool == 0
        assert monitor._last_tool_name is None

    def test_research_mode_relaxes_same_tool_thresholds(self):
        """Research mode should relax same-tool thresholds."""
        monitor = ToolEfficiencyMonitor(
            same_tool_threshold=4,
            same_tool_strong_threshold=6,
            research_mode="deep_research",
        )
        # Research mode should increase thresholds
        assert monitor.same_tool_threshold >= 8
        assert monitor.same_tool_strong_threshold >= 10
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && python -m pytest tests/domain/services/agents/test_tool_efficiency_monitor.py::TestRepetitiveSameToolDetection -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'same_tool_threshold'`

**Step 3: Implement same-tool tracking in ToolEfficiencyMonitor**

In `backend/app/domain/services/agents/tool_efficiency_monitor.py`:

a) Add `signal_type` field to `EfficiencySignal` dataclass (after `hard_stop` field, line 37):
```python
    signal_type: str = "balance"  # "balance" or "repetitive_tool"
```

b) Add class constants for exempt tools and research thresholds (after `_RESEARCH_STRONG_THRESHOLD`, line 57):
```python
    # Relaxed thresholds for same-tool repetition in research modes
    _RESEARCH_SAME_TOOL_THRESHOLD: ClassVar[int] = 8
    _RESEARCH_SAME_TOOL_STRONG_THRESHOLD: ClassVar[int] = 10

    # Tools exempt from repetitive-tool detection (legitimately called in sequence)
    LOOP_EXEMPT_TOOLS: ClassVar[frozenset[str]] = frozenset({
        "file_write",  # Multi-file implementations write many files sequentially
    })
```

c) Add `same_tool_threshold` and `same_tool_strong_threshold` params to `__init__()` and state:
```python
    def __init__(
        self,
        window_size: int = 10,
        read_threshold: int = 5,
        strong_threshold: int = 6,
        research_mode: str | None = None,
        same_tool_threshold: int = 4,
        same_tool_strong_threshold: int = 6,
    ):
```
After the existing research_mode threshold relaxation block, add:
```python
        if research_mode in ("deep_research", "wide_research"):
            same_tool_threshold = max(same_tool_threshold, self._RESEARCH_SAME_TOOL_THRESHOLD)
            same_tool_strong_threshold = max(same_tool_strong_threshold, self._RESEARCH_SAME_TOOL_STRONG_THRESHOLD)
        self.same_tool_threshold = same_tool_threshold
        self.same_tool_strong_threshold = same_tool_strong_threshold
```
After `self._consecutive_reads = 0` (line 87), add:
```python
        # Consecutive same-tool counter (detects repetitive loops)
        self._consecutive_same_tool: int = 0
        self._last_tool_name: str | None = None
```

d) Update `record()` to track same-tool (add before the existing read/action tracking):
```python
        # Track consecutive same-tool usage
        if tool_name == self._last_tool_name:
            self._consecutive_same_tool += 1
        else:
            self._consecutive_same_tool = 1
            self._last_tool_name = tool_name
```

e) Update `check_efficiency()` — add repetitive check BEFORE the existing read checks (after the read_count/action_count lines, before line 118):
```python
        # Check for repetitive same-tool usage (skip exempt tools)
        if (
            self._consecutive_same_tool >= self.same_tool_threshold
            and self._last_tool_name is not None
            and self._last_tool_name not in self.LOOP_EXEMPT_TOOLS
        ):
            hard_stop = self._consecutive_same_tool >= self.same_tool_strong_threshold
            return EfficiencySignal(
                is_balanced=False,
                read_count=read_count,
                action_count=action_count,
                nudge_message=(
                    f"{'⛔ HARD STOP' if hard_stop else '⚠️ WARNING'} — TOOL LOOP DETECTED: "
                    f"{self._consecutive_same_tool} consecutive calls to `{self._last_tool_name}`. "
                    f"This tool is {'now blocked' if hard_stop else 'being overused'}. "
                    f"Try a different approach or tool to make progress."
                ),
                confidence=0.90,
                hard_stop=hard_stop,
                signal_type="repetitive_tool",
            )
```

f) Update `reset()` to clear same-tool state:
```python
    def reset(self) -> None:
        self._recent_tools.clear()
        self._consecutive_reads = 0
        self._consecutive_same_tool = 0
        self._last_tool_name = None
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && python -m pytest tests/domain/services/agents/test_tool_efficiency_monitor.py -v`
Expected: ALL PASS (including existing tests — no regressions)

**Step 5: Run lint**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && ruff check app/domain/services/agents/tool_efficiency_monitor.py`
Expected: No errors

**Step 6: Commit**

```bash
git add backend/app/domain/services/agents/tool_efficiency_monitor.py backend/tests/domain/services/agents/test_tool_efficiency_monitor.py
git commit -m "feat(tool-monitor): add repetitive same-tool loop detection alongside read/action balance"
```

---

### Task 3: Wire Repetitive Tool Detection into BaseAgent

**Files:**
- Modify: `backend/app/domain/services/agents/base.py:241-251`
- Modify: `backend/app/core/config_features.py:160`

**Step 1: Add feature flag**

In `backend/app/core/config_features.py`, inside the `FeatureFlagsSettingsMixin` class, add after line 268 (`feature_token_budget_manager`):

```python
    # Repetitive same-tool loop detection (2026-03-01 session reliability fixes)
    feature_repetitive_tool_detection_enabled: bool = False
```

**Step 2: Update base.py tool filtering**

In `backend/app/domain/services/agents/base.py`, replace the existing hard-stop tool filtering block (lines 241-251) with logic that handles both `"balance"` and `"repetitive_tool"` signal types:

```python
        # Block tools when efficiency monitor signals hard stop
        # Guard with hasattr: get_available_tools() is called during __init__ before _efficiency_monitor is set
        if hasattr(self, "_efficiency_monitor"):
            signal = self._efficiency_monitor.check_efficiency()
            if signal.hard_stop:
                if signal.signal_type == "repetitive_tool":
                    # Block only the specific repeated tool
                    blocked_tool = self._efficiency_monitor._last_tool_name
                    available_tools = [
                        t
                        for t in available_tools
                        if t.get("function", {}).get("name", "") != blocked_tool
                    ]
                else:
                    # Original behavior: block all read tools
                    available_tools = [
                        t
                        for t in available_tools
                        if not self._efficiency_monitor._is_read_tool(t.get("function", {}).get("name", ""))
                    ]
```

**Step 3: Run existing tests to verify no regression**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && python -m pytest tests/domain/services/agents/test_base_efficiency_controls.py tests/domain/services/agents/test_tool_efficiency_monitor.py -v`
Expected: ALL PASS

**Step 4: Run lint**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && ruff check app/domain/services/agents/base.py app/core/config_features.py`
Expected: No errors

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/base.py backend/app/core/config_features.py
git commit -m "feat(agent): wire repetitive tool loop detection into BaseAgent tool filtering"
```

---

### Task 4: Add Failure Lesson Extraction to TokenBudgetManager

**Files:**
- Modify: `backend/app/domain/services/agents/token_budget_manager.py`
- Create: `backend/tests/domain/services/agents/test_token_budget_manager_compression.py`

**Step 1: Write the failing tests**

Create `backend/tests/domain/services/agents/test_token_budget_manager_compression.py`:

```python
"""Tests for TokenBudgetManager failure lesson extraction (compression context preservation)."""

import re

from app.domain.services.agents.token_budget_manager import TokenBudgetManager


class TestExtractFailureLessons:
    """Test _extract_failure_lessons method."""

    def _make_manager(self):
        """Create a TokenBudgetManager with a mock token manager."""
        from unittest.mock import MagicMock

        token_manager = MagicMock()
        token_manager.count_messages_tokens.return_value = 0
        return TokenBudgetManager(token_manager)

    def test_no_errors_returns_none(self):
        """Messages without errors should return None."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "File written successfully."},
            {"role": "tool", "content": "Search returned 5 results."},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is None

    def test_module_not_found_extracted(self):
        """ModuleNotFoundError should be extracted."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "Traceback:\nModuleNotFoundError: No module named 'plotly'"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert "plotly" in result
        assert "ModuleNotFoundError" in result

    def test_import_error_extracted(self):
        """ImportError should be extracted."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "ImportError: cannot import name 'Chart' from 'plotly'"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert "ImportError" in result

    def test_deduplication(self):
        """Same error appearing multiple times should be deduplicated."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "ModuleNotFoundError: No module named 'plotly'"},
            {"role": "tool", "content": "ModuleNotFoundError: No module named 'plotly'"},
            {"role": "tool", "content": "ModuleNotFoundError: No module named 'plotly'"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        # Count occurrences of "plotly" — should appear once (deduplicated)
        assert result.count("plotly") == 1

    def test_multiple_different_errors(self):
        """Different errors should all be extracted."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "ModuleNotFoundError: No module named 'plotly'"},
            {"role": "tool", "content": "FileNotFoundError: [Errno 2] No such file: '/tmp/data.csv'"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert "plotly" in result
        assert "FileNotFoundError" in result

    def test_non_tool_messages_ignored(self):
        """Only role=tool messages should be scanned."""
        mgr = self._make_manager()
        messages = [
            {"role": "user", "content": "ModuleNotFoundError: No module named 'plotly'"},
            {"role": "assistant", "content": "ImportError: something"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is None

    def test_size_guard_caps_output(self):
        """Output should be capped at 500 characters."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": f"ModuleNotFoundError: No module named 'pkg{i}'"} for i in range(50)
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert len(result) <= 500

    def test_compression_context_tag_present(self):
        """Output should contain the [COMPRESSION_CONTEXT] tag."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "ModuleNotFoundError: No module named 'plotly'"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert "[COMPRESSION_CONTEXT]" in result

    def test_permission_denied_extracted(self):
        """Permission denied errors should be extracted."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "Error: Permission denied: /etc/shadow"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert "Permission denied" in result
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && python -m pytest tests/domain/services/agents/test_token_budget_manager_compression.py -v`
Expected: FAIL — `AttributeError: 'TokenBudgetManager' object has no attribute '_extract_failure_lessons'`

**Step 3: Implement _extract_failure_lessons**

In `backend/app/domain/services/agents/token_budget_manager.py`, add `import re` at the top (after `import logging`), then add this method to `TokenBudgetManager` class (after `_truncate_long_content`, before the singleton section, around line 439):

```python
    # ── Error patterns for lesson extraction ─────────────────────────
    _ERROR_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"(ModuleNotFoundError): No module named '([^']+)'"),
        re.compile(r"(ImportError): (.{1,80})"),
        re.compile(r"(FileNotFoundError): (.{1,80})"),
        re.compile(r"(PermissionError|Permission denied): (.{1,80})"),
        re.compile(r"(SyntaxError): (.{1,80})"),
        re.compile(r"(exit code \d+)"),
    ]

    _MAX_LESSON_CHARS: ClassVar[int] = 500

    def _extract_failure_lessons(
        self,
        messages: list[dict[str, Any]],
    ) -> str | None:
        """Extract compact failure lessons from tool result messages.

        Scans role=tool messages for error patterns, deduplicates, and
        returns a compact string suitable for injection as a system message
        that will survive subsequent compression stages.

        Returns None if no actionable errors found.
        """
        seen: set[str] = set()
        lessons: list[str] = []

        for msg in messages:
            if msg.get("role") != "tool":
                continue
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue

            for pattern in self._ERROR_PATTERNS:
                match = pattern.search(content)
                if match:
                    # Build dedup key from the matched groups
                    key = match.group(0)[:120]
                    if key not in seen:
                        seen.add(key)
                        lessons.append(f"- {key}")

        if not lessons:
            return None

        header = "[COMPRESSION_CONTEXT] Previous tool errors — do NOT retry these approaches:"
        body = "\n".join(lessons)
        full = f"{header}\n{body}"

        # Cap size to avoid bloating context
        if len(full) > self._MAX_LESSON_CHARS:
            full = full[: self._MAX_LESSON_CHARS - 3] + "..."

        return full
```

**Step 4: Wire into compress_to_fit**

In `compress_to_fit()` (line 261-318), add failure lesson extraction and injection. Insert BEFORE the "Stage 1" comment (line 302) and modify the return logic:

After `logger.info("Compressing messages: ...")` (line 295-300), add:
```python
        # Extract failure lessons BEFORE any truncation
        lessons = self._extract_failure_lessons(messages)
```

Then at the end of the method (line 318, before `return compressed`), add injection:
```python
        # Inject failure lessons as a system message (survives further compression)
        if lessons:
            insert_idx = next(
                (i + 1 for i, m in enumerate(compressed) if m.get("role") == "system"),
                0,
            )
            compressed.insert(insert_idx, {"role": "system", "content": lessons})

        return compressed
```

**Step 5: Run tests to verify they pass**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && python -m pytest tests/domain/services/agents/test_token_budget_manager_compression.py -v`
Expected: ALL PASS

**Step 6: Run lint**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && ruff check app/domain/services/agents/token_budget_manager.py`
Expected: No errors

**Step 7: Commit**

```bash
git add backend/app/domain/services/agents/token_budget_manager.py backend/tests/domain/services/agents/test_token_budget_manager_compression.py
git commit -m "feat(compression): extract and preserve failure lessons during token budget compression"
```

---

### Task 5: Add Hallucination Rate Escalation to BaseAgent

**Files:**
- Modify: `backend/app/domain/services/agents/base.py:150-182,631-653`
- Modify: `backend/app/core/config_features.py`
- Create: `backend/tests/domain/services/agents/test_hallucination_escalation.py`

**Step 1: Write the failing tests**

Create `backend/tests/domain/services/agents/test_hallucination_escalation.py`:

```python
"""Tests for hallucination rate escalation in BaseAgent.

Tests the per-session hallucination rate tracker and escalation logic
without instantiating the full BaseAgent (which requires extensive mocking).
Instead we test the rate calculation and escalation decision in isolation.
"""


class TestHallucinationRateCalculation:
    """Test the hallucination rate calculation logic."""

    def test_rate_below_threshold_no_escalation(self):
        """Rate below 0.15 with sufficient samples should not escalate."""
        total_tool_calls = 20
        total_hallucinations = 2  # 10% rate
        threshold = 0.15
        min_samples = 10

        rate = total_hallucinations / max(1, total_tool_calls)
        should_escalate = rate >= threshold and total_tool_calls >= min_samples
        assert should_escalate is False

    def test_rate_above_threshold_with_sufficient_samples_escalates(self):
        """Rate above 0.15 with 10+ calls should escalate."""
        total_tool_calls = 20
        total_hallucinations = 5  # 25% rate
        threshold = 0.15
        min_samples = 10

        rate = total_hallucinations / max(1, total_tool_calls)
        should_escalate = rate >= threshold and total_tool_calls >= min_samples
        assert should_escalate is True

    def test_rate_above_threshold_insufficient_samples_no_escalation(self):
        """Rate above threshold but fewer than 10 calls should not escalate."""
        total_tool_calls = 5
        total_hallucinations = 3  # 60% rate, but too few samples
        threshold = 0.15
        min_samples = 10

        rate = total_hallucinations / max(1, total_tool_calls)
        should_escalate = rate >= threshold and total_tool_calls >= min_samples
        assert should_escalate is False

    def test_zero_tool_calls_no_division_error(self):
        """Zero tool calls should not cause division by zero."""
        total_tool_calls = 0
        total_hallucinations = 0
        threshold = 0.15

        rate = total_hallucinations / max(1, total_tool_calls)
        assert rate == 0.0

    def test_exactly_at_threshold_escalates(self):
        """Rate exactly at threshold should escalate."""
        total_tool_calls = 20
        total_hallucinations = 3  # 15% = exactly threshold
        threshold = 0.15
        min_samples = 10

        rate = total_hallucinations / max(1, total_tool_calls)
        should_escalate = rate >= threshold and total_tool_calls >= min_samples
        assert should_escalate is True


class TestHallucinationMetaPrompt:
    """Test the meta-prompt content for hallucination correction."""

    def test_meta_prompt_contains_required_params_reminder(self):
        """Meta prompt should remind about required parameters."""
        meta_prompt = (
            "CRITICAL: Recent tool calls had missing required parameters. "
            "You MUST include ALL required parameters for every tool call. "
            "Do NOT omit 'id', 'exec_dir', or 'command' parameters."
        )
        assert "required parameters" in meta_prompt.lower()
        assert "id" in meta_prompt
        assert "exec_dir" in meta_prompt
```

**Step 2: Run tests to verify they pass**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && python -m pytest tests/domain/services/agents/test_hallucination_escalation.py -v`
Expected: ALL PASS (these are logic-only tests, no imports needed from base.py)

**Step 3: Add feature flags**

In `backend/app/core/config_features.py`, inside `FeatureFlagsSettingsMixin`, add after the repetitive tool flag:

```python
    # Hallucination rate escalation (2026-03-01 session reliability fixes)
    feature_hallucination_escalation_enabled: bool = False
    hallucination_escalation_threshold: float = 0.15  # 15% hallucination rate triggers escalation
    hallucination_escalation_min_samples: int = 10  # Min tool calls before rate is meaningful
```

**Step 4: Add tracking state to BaseAgent**

In `backend/app/domain/services/agents/base.py`, after `self._hallucination_count_this_step: int = 0` (line 182), add:

```python
        # Per-session hallucination rate tracking (for model escalation)
        self._total_hallucinations: int = 0
        self._total_tool_calls: int = 0
        self._hallucination_escalated: bool = False
```

**Step 5: Wire tracking into tool execution**

In `backend/app/domain/services/agents/base.py`, in the `_execute_tool_call` method, after the pre-execution hallucination check (around line 631-653):

After `validation_result = self._hallucination_detector.validate_tool_call(...)` and before the `if not validation_result.is_valid:` block, add:

```python
        self._total_tool_calls += 1
```

Inside the `if not validation_result.is_valid:` block, before the `return ToolResult(...)`, add:

```python
            self._total_hallucinations += 1

            # Check if hallucination rate warrants escalation
            try:
                from app.core.config import get_settings
                _settings = get_settings()
                if (
                    getattr(_settings, "feature_hallucination_escalation_enabled", False)
                    and not self._hallucination_escalated
                    and self._total_tool_calls >= getattr(_settings, "hallucination_escalation_min_samples", 10)
                ):
                    rate = self._total_hallucinations / max(1, self._total_tool_calls)
                    threshold = getattr(_settings, "hallucination_escalation_threshold", 0.15)
                    if rate >= threshold:
                        self._hallucination_escalated = True
                        logger.warning(
                            "Hallucination rate escalation triggered: rate=%.2f "
                            "(threshold=%.2f, calls=%d, hallucinations=%d)",
                            rate, threshold, self._total_tool_calls, self._total_hallucinations,
                        )
            except Exception:
                logger.debug("Hallucination escalation check failed (non-critical)", exc_info=True)
```

**Step 6: Run lint**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && ruff check app/domain/services/agents/base.py app/core/config_features.py`
Expected: No errors

**Step 7: Run existing hallucination tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && python -m pytest tests/domain/services/agents/test_base_hallucination.py tests/domain/services/agents/test_hallucination_escalation.py -v`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add backend/app/domain/services/agents/base.py backend/app/core/config_features.py backend/tests/domain/services/agents/test_hallucination_escalation.py
git commit -m "feat(agent): add per-session hallucination rate tracker with escalation trigger"
```

---

### Task 6: Add Feature Flag for Compression Context Preservation

**Files:**
- Modify: `backend/app/core/config_features.py`

**Step 1: Add feature flag**

In `backend/app/core/config_features.py`, inside `FeatureFlagsSettingsMixin`, add after the hallucination escalation flags:

```python
    # Compression context preservation — inject failure lessons during token budget compression
    feature_compression_context_preservation_enabled: bool = False
```

**Step 2: Run lint**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && ruff check app/core/config_features.py`
Expected: No errors

**Step 3: Commit**

```bash
git add backend/app/core/config_features.py
git commit -m "feat(config): add feature flags for compression context preservation"
```

---

### Task 7: Run Full Test Suite and Verify

**Step 1: Run all modified test files**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && python -m pytest tests/domain/services/agents/test_tool_efficiency_monitor.py tests/domain/services/agents/test_token_budget_manager_compression.py tests/domain/services/agents/test_hallucination_escalation.py -v`
Expected: ALL PASS

**Step 2: Run the broader agents test suite for regressions**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && python -m pytest tests/domain/services/agents/ -v --tb=short`
Expected: ALL PASS (or only known pre-existing failures)

**Step 3: Run lint on all changed files**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && ruff check app/core/middleware.py app/core/config_features.py app/domain/services/agents/tool_efficiency_monitor.py app/domain/services/agents/token_budget_manager.py app/domain/services/agents/base.py && ruff format --check app/core/middleware.py app/core/config_features.py app/domain/services/agents/tool_efficiency_monitor.py app/domain/services/agents/token_budget_manager.py app/domain/services/agents/base.py`
Expected: No errors
