# Session Reliability Fixes Design

**Date:** 2026-03-06
**Triggered by:** Live monitoring of Telegram research session (Codex 5.4 vs GLM-5)
**Session ID:** `71ff7c9e96f54eb2` (succeeded) / `763abbbfbacd400f` (crashed)

---

## Problem Statement

A live research session surfaced 9 issues, 6 requiring root-cause fixes. The session completed in 484s with 714 events, but wasted ~80s on truncation retries, showed 282s of silence to the user, and delivered a report with 7.9% unverified hallucination spans. One prior session crashed entirely due to a missing attribute.

## Issues and Root Causes

### Fix 1: Adaptive max_tokens for file_write tool calls

**Root cause:** `llm_tool_max_tokens=2048` blanket-caps ALL tool-enabled LLM calls. When the agent calls `file_write` with a full report (~6000+ tokens of markdown content), the response is always truncated at 2048 tokens, triggering a cascade: truncation detected -> retry with smaller output -> truncation again -> force text-only -> correction retry. This wastes 3 LLM calls (~80s).

**Fix:** Content-aware max_tokens selection. The 2048 cap exists to keep search/browse tool calls efficient, but `file_write` and `file_append` produce large content payloads that need the full budget.

**Implementation:**
- In `openai_llm.py` `_cap_tool_max_tokens()` (line ~1763): Check if the pending tool schema includes `file_write` or `file_append`. If so, skip the tool cap and use `config.max_tokens` (8192) or `summarization_max_tokens` (32000) for report-writing contexts.
- Add a new config field `llm_file_write_max_tokens: int = 16384` for explicit control.
- The LLM protocol already supports per-call `max_tokens` override — this just wires it up for content-heavy tools.

**Context7 validation:** OpenAI SDK's `.parse()` raises `LengthFinishReasonError` on `finish_reason=length`, confirming truncation is a first-class concern that should be prevented, not recovered from.

### Fix 2: Proactive schema sanitization

**Root cause:** The `_build_validation_recovery_messages()` cleanup (role normalization, tool message restructuring, field stripping) only runs AFTER the first API rejection. For providers like kimi-for-coding that don't support `role="developer"` or complex tool message schemas, the first attempt always fails, adding 1-7s per call.

**Fix:** Apply sanitization proactively for known-strict providers. The provider's capabilities are already detected (e.g., `"Provider doesn't support json_object format"` log). Use this same detection to pre-sanitize transcripts.

**Implementation:**
- Add `llm_proactive_schema_sanitization: bool = False` config field (opt-in, default off for OpenAI/Anthropic).
- In `openai_llm.py`: when `_provider_supports_json_object` is False (already tracked), run `_build_validation_recovery_messages()` before the first attempt in `ask()`, `ask_structured()`, and `ask_stream()`.
- This eliminates 100% of "API rejected message schema" retries for strict providers.

### Fix 3: Rebalance deep_research planning budget

**Root cause:** Deep research allocates only 10% (12,595 tokens) to planning, but each plan update after a step completion costs ~2000-3000 tokens. With 5 steps, the 4th update exceeds budget and triggers compression, losing context.

**Fix:** Increase planning allocation from 10% to 15% for deep_research, taking from memory_context (10% -> 5%) which is underutilized in research flows.

**Implementation:**
- In `token_budget_manager.py` `RESEARCH_ALLOCATIONS["deep_research"]`:
  ```python
  BudgetPhase.SYSTEM_PROMPT: 0.10,   # unchanged
  BudgetPhase.PLANNING: 0.15,        # was 0.10
  BudgetPhase.EXECUTION: 0.50,       # unchanged
  BudgetPhase.MEMORY_CONTEXT: 0.05,  # was 0.10
  BudgetPhase.SUMMARIZATION: 0.20,   # unchanged
  ```
- This gives planning 18,893 tokens (vs 12,595), enough for 6+ plan updates without compression.

### Fix 4: Structured data hallucination exemption

**Root cause:** LettuceDetect flags markdown tables containing cited data (e.g., pricing tables with `[19][22]` references) as "hallucinated" because it can't cross-reference structured tabular content against source text. This produces false positives on the most valuable parts of research reports.

**Fix:** Skip hallucination checking for content blocks that are markdown tables with inline citation markers.

**Implementation:**
- In `output_verifier.py` or `lettuce_verifier.py`: Before running LettuceDetect, split the text into segments. For segments matching the pattern `^\|.*\|$` (markdown table rows) that also contain citation markers (`\[\d+\]`), exclude them from the hallucination check.
- Report the exempted table row count in logs for transparency.
- This is industry-standard: RAG evaluation frameworks (RAGAS, TruLens) exempt structured outputs with explicit source attribution from hallucination scoring.

### Fix 5: Channel progress heartbeat

**Root cause:** The gateway's `MessageRouter._event_to_outbound()` only converts `message`, `report`, and `error` events to outbound messages. Internal events (progress, plan, step, tool) are silently dropped. During long LLM calls (30-40s), the gateway sees no activity and triggers stall warnings.

**Fix:** Forward `ProgressEvent` as lightweight channel heartbeat messages that reset the gateway's progress tracker without spamming the user.

**Implementation:**
- In `message_router.py`: Add `"progress"` to `_OUTBOUND_EVENT_TYPES`. Convert `ProgressEvent` to a minimal `OutboundMessage` with `type="progress"` (not rendered as text).
- In `nanobot_gateway.py`: Recognize `type="progress"` outbound messages and call `_mark_inbound_processing_progress()` without sending to Telegram.
- In `telegram_delivery_policy.py`: Filter out `type="progress"` messages (don't send to user).
- This provides sub-3s progress heartbeats (matching LLMHeartbeat's 2.5s interval) to the gateway without any user-visible messages.

### Fix 6: Artifact manifest injection

**Root cause:** The summarization prompt doesn't include the list of files uploaded to MinIO, so the LLM can't reference them. The "missing artifact references" warning fires because the summary has no file links.

**Implementation:**
- In `plan_act.py` or `execution.py`: Before calling the summarization LLM, collect all uploaded artifact paths from `file_sync_manager` and inject them as a system message:
  ```
  [ARTIFACTS] The following files were created during this session:
  - report-05666228.md (uploaded to storage)
  - gpt-5_4_vs_glm-5_perf.html (interactive chart)
  - gpt-5_4_vs_glm-5_perf.png (chart image)
  Reference these files in your summary where relevant.
  ```
- This gives the LLM the information it needs to include artifact references naturally.

---

## Out of Scope

- **Issue 1 (step.title):** Already fixed in this session.
- **Issue 3 (circuit breaker tripped):** Fix 1 eliminates the root cause (truncation cascade that causes slow calls). No separate circuit breaker change needed.
- **Issue 9 (empty scrape fallback):** System worked as designed — tiered fallback recovered correctly.

## Testing Strategy

- **Fix 1:** Unit test: mock file_write tool call, assert max_tokens > 2048.
- **Fix 2:** Unit test: mock strict provider, assert no schema rejection on first attempt.
- **Fix 3:** Unit test: verify deep_research budget allocations sum to 1.0 and planning >= 15%.
- **Fix 4:** Unit test: markdown table with citations excluded from LettuceDetect input.
- **Fix 5:** Integration test: emit ProgressEvent, assert gateway progress tracker updated.
- **Fix 6:** Unit test: verify artifact manifest injected into summarization messages.

## Files to Modify

| Fix | Files | Type |
|-----|-------|------|
| 1 | `config_llm.py`, `openai_llm.py` | Config + Logic |
| 2 | `config_llm.py`, `openai_llm.py` | Config + Logic |
| 3 | `token_budget_manager.py` | Config |
| 4 | `lettuce_verifier.py` or `output_verifier.py` | Logic |
| 5 | `message_router.py`, `nanobot_gateway.py`, `telegram_delivery_policy.py` | Logic |
| 6 | `plan_act.py` or `execution.py` | Logic |
