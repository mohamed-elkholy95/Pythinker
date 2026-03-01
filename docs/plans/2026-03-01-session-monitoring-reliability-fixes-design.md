# Session Monitoring Reliability Fixes — Design Document

**Date**: 2026-03-01
**Status**: Approved
**Scope**: 5 production issues observed during GLM-5 agent session monitoring (session `94376a220a5b43d6`)

---

## Context

During live monitoring of a GLM-5 research session ("Best AI Coding Agents 2026"), 5 reliability issues were identified:

1. **GLM-5 tool hallucination** — missing required params (`shell_exec` without `id`, `exec_dir`) at high budget usage
2. **Python script execution loop** — 50 consecutive `code_execute_python` calls not caught by tool efficiency monitor
3. **Tool efficiency monitor gap** — only detects read-without-write imbalance, not repetitive same-tool loops
4. **Post-compression context loss** — agent forgets why scripts failed after token budget compression drops error messages
5. **structlog formatting error** — `AttributeError: 'str' object has no attribute 'copy'` from f-string logging in middleware

Issues 2 and 3 share the same root cause and are addressed by a single fix.

---

## Fix 1: Repetitive Same-Tool Loop Detection (Issues 2 & 3)

### Root Cause

`ToolEfficiencyMonitor.record()` tracks a binary `_consecutive_reads` counter. It increments on read tools and **resets to 0** when any ACTION tool is called. Since `code_execute_python` is classified as ACTION (`ToolName._ACTION`), calling it 50 times in a row resets the counter every time — the monitor thinks the agent is being productive.

### Design

Add a **repetitive same-tool tracker** alongside the existing read/action balance detector.

**State additions to `ToolEfficiencyMonitor`**:
- `_consecutive_same_tool: int = 0` — consecutive calls to the same tool
- `_last_tool_name: str | None = None` — last tool called

**`record()` changes**:
```python
def record(self, tool_name: str) -> None:
    self._recent_tools.append(tool_name)

    # Track consecutive same-tool usage
    if tool_name == self._last_tool_name:
        self._consecutive_same_tool += 1
    else:
        self._consecutive_same_tool = 1
        self._last_tool_name = tool_name

    # Existing read/action tracking (unchanged)
    if self._is_read_tool(tool_name):
        self._consecutive_reads += 1
    elif self._is_action_tool(tool_name):
        self._consecutive_reads = 0
```

**`check_efficiency()` changes** — check repetitive tool FIRST, before read/action balance:
```python
# Check for repetitive same-tool usage (skip exempt tools)
if (
    self._consecutive_same_tool >= self.same_tool_threshold
    and self._last_tool_name not in self.LOOP_EXEMPT_TOOLS
):
    hard_stop = self._consecutive_same_tool >= self.same_tool_strong_threshold
    return EfficiencySignal(
        is_balanced=False,
        read_count=read_count,
        action_count=action_count,
        nudge_message=f"... {self._consecutive_same_tool} consecutive calls to {self._last_tool_name} ...",
        confidence=0.90,
        hard_stop=hard_stop,
        signal_type="repetitive_tool",
    )
```

**Thresholds**:
- `same_tool_threshold: int = 4` — nudge (2-3 retries is legitimate; 4+ is suspicious)
- `same_tool_strong_threshold: int = 6` — hard stop
- Research mode relaxation: `same_tool_threshold=8`, `same_tool_strong_threshold=10`

**Exempt tools** (`LOOP_EXEMPT_TOOLS`):
- `file_write` — multi-file implementations legitimately write many files
- `file_read` — already covered by existing read detection

**`EfficiencySignal` changes**:
- Add `signal_type: str = "balance"` field (values: `"balance"`, `"repetitive_tool"`)

**`base.py` tool filtering changes**:
- When `signal_type == "repetitive_tool"` and `hard_stop=True`: filter out the specific repeated tool (not all read tools)
- This allows the agent to use different tools to solve the problem

### Files Modified

- `backend/app/domain/services/agents/tool_efficiency_monitor.py`
- `backend/app/domain/services/agents/base.py`

### Feature Flag

`feature_repetitive_tool_detection_enabled: bool = False` (in `config_features.py`)

### Metrics

`pythinker_repetitive_tool_stops_total{tool_name, threshold}`

---

## Fix 2: Post-Compression Context Preservation (Issue 4)

### Root Cause

`TokenBudgetManager.compress_to_fit()` runs three compression stages:
1. `_summarize_tool_outputs()` — truncates older tool results to 500 chars
2. `_truncate_long_content()` — caps all non-system messages at 2000 chars
3. `trim_messages()` — drops low-priority messages (preserves last 4)

Error messages from failed tool executions (e.g., `ModuleNotFoundError: No module named 'plotly'`) get truncated or dropped entirely. The agent then retries the same failing approach because it has no memory of why it failed.

### Design

Add a **failure lesson extractor** that runs before compression and injects a compact context note.

**New method `_extract_failure_lessons(messages) -> str | None`**:
- Scans all tool result messages (`role == "tool"`) for error patterns:
  - `ModuleNotFoundError`, `ImportError`, `FileNotFoundError`
  - `Error:`, `Exception:`, `Traceback`
  - `exit code` non-zero, `Permission denied`
- Extracts the error type and key detail (module name, file path, etc.)
- Deduplicates (same error type + same target = one entry)
- Returns a compact string (~100-200 tokens) or `None` if no errors found

**Integration in `compress_to_fit()`**:
```python
def compress_to_fit(self, budget, phase, messages, target_tokens=None):
    # ... existing budget calculation ...

    # Extract failure lessons BEFORE any truncation
    lessons = self._extract_failure_lessons(messages)

    # Stage 1-3: existing compression (unchanged)
    compressed = self._summarize_tool_outputs(messages, target_tokens)
    # ...

    # Inject lessons as a protected system message
    if lessons:
        lesson_msg = {
            "role": "system",
            "content": lessons,
        }
        # Insert after the first system message
        insert_idx = next(
            (i + 1 for i, m in enumerate(compressed) if m.get("role") == "system"),
            0,
        )
        compressed.insert(insert_idx, lesson_msg)

    return compressed
```

**Example injected message**:
```
[COMPRESSION_CONTEXT] Previous tool errors — do NOT retry these approaches:
- code_execute_python: ModuleNotFoundError 'plotly' (not installed in sandbox)
- code_execute_python: ModuleNotFoundError 'seaborn' (not installed in sandbox)
Use only pre-installed packages or find alternative approaches.
```

**Why system message**: The existing compression logic on lines 422-424 of `_truncate_long_content()` never truncates system messages. By injecting as `role=system`, the lessons survive all three compression stages.

**Deduplication**: Uses `(error_type, target)` tuple as key. `ModuleNotFoundError: plotly` appearing in 5 different tool results produces only one lesson entry.

**Size guard**: Cap the lessons string at 300 chars to avoid bloating the context.

### Files Modified

- `backend/app/domain/services/agents/token_budget_manager.py`

### Feature Flag

`feature_compression_context_preservation_enabled: bool = False`

### Metrics

`pythinker_compression_lessons_injected_total`

---

## Fix 3: GLM-5 Tool Hallucination Escalation (Issue 1)

### Root Cause

GLM-5 generates tool calls with missing required parameters when operating under token budget pressure. The `ToolHallucinationDetector` catches these (max 3 corrections per step), then force-advances. But the pattern repeats in subsequent steps because the underlying cause (model confusion at high budget) persists.

### Design

Add a **per-session hallucination rate tracker** that triggers model tier escalation.

**State additions to agent `BaseAgent.__init__()`**:
- `_total_hallucinations: int = 0`
- `_total_tool_calls: int = 0`

**Tracking** (in the tool call processing loop):
```python
self._total_tool_calls += 1
# After hallucination detection:
if hallucination_detected:
    self._total_hallucinations += 1
```

**Escalation check** (after hallucination correction):
```python
rate = self._total_hallucinations / max(1, self._total_tool_calls)
if (
    rate >= settings.hallucination_escalation_threshold  # default 0.15
    and self._total_tool_calls >= 10  # minimum sample size
    and not self._hallucination_escalated  # only escalate once
):
    self._hallucination_escalated = True
    if settings.adaptive_model_selection_enabled:
        # Escalate model tier (fast → balanced → powerful)
        self._escalate_model_tier()
    else:
        # Inject meta-prompt with explicit param reminders
        self._inject_hallucination_meta_prompt()
```

**`_escalate_model_tier()`**: Sets `self._model_override` to the next tier up. The existing `model_router.py` adaptive selection already supports per-call model overrides.

**`_inject_hallucination_meta_prompt()`**: Adds a system message: "CRITICAL: Include ALL required parameters for every tool call. Recent errors: missing `id`, `exec_dir` for shell_exec."

### Files Modified

- `backend/app/domain/services/agents/base.py`
- `backend/app/core/config_features.py`

### Feature Flag

`feature_hallucination_escalation_enabled: bool = False`

### Config

`hallucination_escalation_threshold: float = 0.15` (in `config_features.py`)

### Metrics

`pythinker_hallucination_escalations_total{from_tier, to_tier}`

---

## Fix 4: structlog Middleware Formatting (Issue 5)

### Root Cause

`middleware.py` uses f-string formatting with structlog's `BoundLogger`:
```python
logger.info(f"[{request_id}] {request.method} {path} - Client: {client_ip}")
```

This defeats structured logging:
- Correlation IDs are duplicated (embedded in f-string AND injected by `add_correlation_ids` processor)
- JSON output contains an unparseable `event` string instead of discrete queryable fields
- The `AttributeError: 'str' object has no attribute 'copy'` error can occur when `ProcessorFormatter` processes stdlib `LogRecord` objects with pre-formatted string messages

### Design

Convert all 4 logging calls in `RequestLoggingMiddleware` to structured kwargs:

```python
# Line 54: Request start
logger.info("request_started", method=request.method, path=path, client_ip=client_ip)

# Line 72: Exception
logger.error("request_failed", exc_info=True)

# Lines 76-80: Request completion
log_kw = dict(method=request.method, path=path, status=response_status, duration_ms=round(duration_ms, 2))
if response_status < 400:
    logger.info("request_completed", **log_kw)
else:
    logger.warning("request_completed", **log_kw)
```

The `request_id` is automatically injected by the `add_correlation_ids` processor via the `request_id_var` ContextVar (set on line 50), so it should NOT be in the log message.

### Files Modified

- `backend/app/core/middleware.py` (4 logging call sites)

### Feature Flag

None — this is a correctness fix, not a behavioral change.

---

## Cross-Cutting: Feature Flags and Config

All new feature flags in `backend/app/core/config_features.py`:

```python
# Fix 1: Repetitive same-tool loop detection
feature_repetitive_tool_detection_enabled: bool = False

# Fix 2: Compression context preservation
feature_compression_context_preservation_enabled: bool = False

# Fix 3: Hallucination rate escalation
feature_hallucination_escalation_enabled: bool = False
hallucination_escalation_threshold: float = 0.15
```

Fix 4 (structlog) has no feature flag — it's a correctness fix.

---

## Implementation Order

1. **Fix 4** (structlog) — Zero risk, immediate correctness improvement
2. **Fix 1** (repetitive tool detection) — Highest impact, addresses the most visible failure mode
3. **Fix 2** (compression context) — Second highest impact, prevents post-compression loops
4. **Fix 3** (hallucination escalation) — Provider-specific, lower priority
5. **Tests** — Unit tests for all new behaviors

---

## Testing Strategy

| Fix | Test Approach |
|-----|--------------|
| 1. Repetitive tool | Unit test: 6 consecutive `code_execute_python` → hard stop signal |
| 1. Repetitive tool | Unit test: exempt tools don't trigger |
| 1. Repetitive tool | Unit test: different tools reset counter |
| 2. Compression context | Unit test: messages with errors → lessons extracted |
| 2. Compression context | Unit test: lessons survive 3-stage compression |
| 2. Compression context | Unit test: deduplication works |
| 3. Hallucination escalation | Unit test: rate below threshold → no escalation |
| 3. Hallucination escalation | Unit test: rate above threshold with min samples → escalation |
| 4. structlog | Existing test coverage sufficient (format change only) |
