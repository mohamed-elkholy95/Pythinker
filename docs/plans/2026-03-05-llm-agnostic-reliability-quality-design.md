# LLM-Agnostic Reliability & Report Quality Enhancement Design

**Date**: 2026-03-05
**Status**: Approved
**Scope**: 20 changes across ~15 files, 1 new file
**Trigger**: Monitoring session f5e12c8eae1b4758 revealed 23 findings across LLM adapter, agent execution, prompt engineering, and report quality layers

---

## Context

A deep research session using GLM-5 exposed systemic reliability and quality issues that are not GLM-specific but affect any LLM API. Key findings:
- Step 1 timed out (1004s > 900s wall-clock limit)
- All 6 Serper API keys exhausted in ~10s
- Slow tool-call circuit breaker tripped 3x with no FAST_MODEL fallback
- 3 tool hallucinations (missing required params)
- LLM response truncation with malformed tool args
- 9 report files created instead of 1 (3 overwrite loops)
- code_execute_python misused for markdown text
- 53 of 75 citation numbers had no References entry
- 12 hallucinated spans detected (4.3% ratio)
- Delivery integrity gate flagged 3 issues but report shipped anyway

---

## Section 1: LLM Adapter Hardening (Model-Agnostic)

### 1A. Provider Capability Profiles

**Files**: new `backend/app/infrastructure/external/llm/provider_profile.py`, `openai_llm.py`

Create a `ProviderProfile` frozen dataclass consolidating all provider-specific behavior:

```python
@dataclass(frozen=True)
class ProviderProfile:
    name: str
    connect_timeout: float = 5.0
    read_timeout: float = 120.0
    tool_read_timeout: float = 90.0
    stream_read_timeout: float = 30.0
    supports_json_mode: bool = True
    supports_tool_choice: bool = True
    supports_system_role: bool = True
    max_tool_calls_per_response: int = 20
    needs_message_merging: bool = False       # GLM error 1214
    needs_thinking_suppression: bool = False   # GLM thinking mode
    tool_arg_truncation_prone: bool = False    # GLM/small models
    requires_orphan_cleanup: bool = False       # GLM/Qwen
    slow_tool_threshold: float = 30.0
    slow_tool_trip_count: int = 2
```

Registry maps `(api_base, model_name)` to profile via pattern matching. Unknown providers get conservative defaults. Replaces scattered `_is_glm_api`, `_is_deepseek`, etc. booleans.

### 1B. Slow Tool-Call Circuit Breaker Enhancement

**Files**: `config_llm.py`, `openai_llm.py`

New settings:
- `llm_slow_breaker_degraded_max_tokens: int = 4096` (was hardcoded 1024)
- `llm_slow_breaker_degraded_timeout: float = 90.0` (was hardcoded 60.0)
- `llm_slow_tool_threshold: float = 30.0`
- `llm_slow_tool_trip_count: int = 2`
- `llm_slow_tool_cooldown: float = 300.0`

When breaker active with no FAST_MODEL: log error once (not every call) with "Set FAST_MODEL to improve recovery".

### 1C. Tool Argument Pre-Validation

**Files**: `openai_llm.py`

Add `_validate_tool_args()` to tool call parsing:
1. Validate each tool call's arguments against JSON schema before returning
2. On failure: inject synthetic tool response with schema correction
3. Count failures per-call; if all fail: append schemas as system message
4. Provider-profile-driven: only when `tool_arg_truncation_prone=True`

### 1D. Response Finish Reason Propagation

**Files**: `openai_llm.py`

When `finish_reason == "length"` with tools provided:
1. Automatically reduce `max_tokens` for retry
2. Add "Previous response was truncated. Produce a shorter response." instruction
3. Make `max_consecutive_truncations` configurable via settings

---

## Section 2: Agent Execution Fixes

### 2A. Graduated Step Wall-Clock Pressure

**Files**: `base.py`, `config_features.py`

Replace single 65% warning with 3 graduated thresholds:
- **50%**: `STEP_TIME_ADVISORY` — advisory message with remaining time
- **75%**: `STEP_TIME_URGENT` — block read-only tools, demand finalization
- **90%**: `STEP_TIME_CRITICAL` — block ALL tools except file_write/code_save_artifact

After 50% mark: append `[Step time: {elapsed}s/{budget}s]` to every tool result.

Per-depth budgets: QUICK=300s, STANDARD=600s, DEEP=900s (new settings).

### 2B. File Management Enforcement

**Files**: `file.py`, `prompts/execution.py`

1. Single report file instruction in execution prompt
2. After 3rd overwrite: block file_write for that path for 120s, force file_str_replace
3. Content regression >50%: return error instead of warning
4. Inject workspace file listing at summarization time

### 2C. Tool Efficiency Monitor Settings

**Files**: `config_features.py`, `tool_efficiency_monitor.py`, `plan_act.py`

New settings:
- `tool_efficiency_read_threshold: int = 5`
- `tool_efficiency_strong_threshold: int = 6`
- `tool_efficiency_same_tool_threshold: int = 4`
- `tool_efficiency_same_tool_strong_threshold: int = 6`

Per-session instances (not singleton). Step-scoped reset.

### 2D. Rich Stuck Recovery

**Files**: `step_failure.py`

Before injecting placeholder: collect files written during step, build richer placeholder with file list and last tool result summary.

---

## Section 3: Prompt Engineering

### 3A. Report Construction Protocol

**Files**: `prompts/execution.py`

New `REPORT_CONSTRUCTION_PROTOCOL` signal for research steps:
1. Single report file
2. Outline first, fill incrementally
3. Use file_str_replace, not file_write for edits
4. Never use code_execute_python for text
5. Never create duplicate files

### 3B. Citation Numbering Discipline

**Files**: `prompts/execution.py`, `execution.py`

1. Inject numbered source list into summarize prompt
2. Add citation cap instruction: "Citation numbers MUST be in range [1]-[{N}]"
3. Re-summarize if orphan citations exceed 50%
4. Pre-populate References section template

### 3C. Anti-Tool-Misuse Instructions

**Files**: `prompts/system.py`

Explicit negative examples:
- NEVER use code_execute_python to save text
- NEVER use shell_exec to write files
- code_execute_python ONLY for: data analysis, calculations, charts

### 3D. Comprehensiveness Signal

**Files**: `prompts/execution.py`

For DEEP research: inject signal requesting comparisons, real-world examples, limitations, and actionable recommendations.

---

## Section 4: Report Quality Pipeline

### 4A. Citation Integrity Overhaul

**Files**: `citation_integrity.py`, `execution.py`

1. Pre-generation `SourceRegistry` with stable numbered IDs
2. Two-pass citation repair: fuzzy match orphans, then remove/mark remaining
3. `citation_coverage_ratio` in delivery gate; re-summarize if below 0.6
4. Auto-dedup references with same URL

### 4B. Hallucination Mitigation

**Files**: `output_verifier.py`, `config_features.py`

New settings:
- `hallucination_warn_threshold: float = 0.05`
- `hallucination_block_threshold: float = 0.15`
- `hallucination_annotate_spans: bool = False`

Actions: annotate spans, remove high-confidence (>=0.95) hallucinations, expand grounding context to 8K for DEEP research.

### 4C. Delivery Gate Hardening

**Files**: `response_generator.py`

Graduated response: Green (0 issues), Yellow (1-2 non-critical), Red (3+).
Quality metadata in ReportEvent. Auto-inject `## Supplementary Files` section.

### 4D. Plotly Chart Logging

**Files**: `agent_task_runner.py`

Log actual failure reason. Add `chart_generation_enabled` feature flag.

---

## Section 5: Search & Infrastructure

### 5A. Key Pool Configurability

**Files**: `config_features.py`, `key_pool.py`

New settings:
- `key_pool_cb_threshold: int = 5`
- `key_pool_cb_reset_timeout_5xx: int = 300`
- `key_pool_cb_reset_timeout_429: int = 45`
- `key_pool_exhaustion_recovery_ttl: int = 1800`

### 5B. Search Provider Health Visibility

**Files**: `plan_act.py`, `search/factory.py`

1. Pre-search health check before research tasks
2. Provider health in search result metadata
3. Proactive switching when >50% keys exhausted

### 5C. Model Router Tier Settings

**Files**: `config_llm.py`, `model_router.py`

New settings:
- `fast_model_max_tokens: int = 4096`
- `fast_model_temperature: float = 0.2`
- `balanced_model_max_tokens: int = 8192`

### 5D. LLM Retry Budget Middleware

**Files**: new `backend/app/infrastructure/external/llm/middleware.py`, `openai_llm.py`

Phase 1 only: `RetryBudgetMiddleware` wrapping LLM adapter.
- Track retries per-task with asyncio.Lock
- Raise `RetryBudgetExhaustedError` at limit
- 5s cooldown when per-minute budget exceeded

---

## Implementation Priority

| Priority | Items | Impact |
|----------|-------|--------|
| **HIGH** | 1A, 1B, 2A, 2B, 3A, 3B, 4A | Prevents timeouts, file chaos, citation gaps |
| **MEDIUM** | 1C, 1D, 2C, 3C, 4B, 4C, 5A, 5B, 5D | Improves resilience and observability |
| **LOW** | 2D, 3D, 4D, 5C | Polish and configurability |

## Testing Strategy

- Unit tests for each new/modified component
- Integration test: run a research session with mock LLM returning truncated/malformed responses
- Regression: existing 4979 tests must pass
- Manual: run a real deep research session and compare quality metrics before/after
