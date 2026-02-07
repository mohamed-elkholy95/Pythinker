# Agent Enhancement Plan — Deep Scan Results

**Date:** 2026-02-07
**Scope:** Agent logic, reasoning, workflow, tool execution, LLM integration, memory management, sandbox lifecycle
**Total Issues Found:** 108 across 6 subsystems

---

## Executive Summary

Deep scan of the entire agent system revealed **108 issues** across 6 subsystems. The most critical problems are:

1. **Workflow can loop infinitely** — no outer iteration limit or timeout on `plan_act.py` main loop
2. **Parallel tool execution silently drops results** — `zip(strict=False)` hides misalignment
3. **Background memory save races with retry logic** — can cause infinite token-limit retry loops
4. **CancelledError treated as normal exception** in parallel gather — blocks graceful shutdown
5. **Streaming LLM calls miss cache savings** — Anthropic `ask_stream()` skips cache control
6. **Browser content extraction has no enforced size limit** — can return 100KB+ to agent

---

## Phase 1: CRITICAL Fixes (14 issues) — Do First

### P1.1 — Workflow Loop Safety (plan_act.py)

| # | Issue | File:Line | Impact |
|---|-------|-----------|--------|
| 1 | **No outer iteration limit** on `while True` loop | plan_act.py:1666 | Infinite workflow cycles |
| 2 | **No workflow-level timeout** — entire `run()` can hang | plan_act.py:1442 | Session hangs forever |
| 3 | **Verification loop can exceed max** then fall back to PLANNING creating infinite cycle | plan_act.py:1745-1799 | Planning↔Verification loop |
| 4 | **Reflection has no "abort" decision** — stuck patterns don't escalate | reflection.py:149-292 | Never breaks out of loop |

**Fix:** Add `max_workflow_transitions = 100` counter to outer loop + `asyncio.timeout(600)` wrapper on `run()` + add `"abort"` route from reflection to summarize + track plan-update attempts with max=3.

### P1.2 — Parallel Execution Safety (base.py)

| # | Issue | File:Line | Impact |
|---|-------|-----------|--------|
| 5 | **`zip(strict=False)` silently drops misaligned results** | base.py:826-828 | Orphaned tool responses, memory corruption |
| 6 | **CancelledError/KeyboardInterrupt caught as normal exception** in `asyncio.gather` results | base.py:823-831 | Blocks shutdown, treats cancellation as tool failure |
| 7 | **Background memory save race condition** — fire-and-forget save before retry | base.py:1178-1188 | Infinite token-limit retry loops |

**Fix:** Change to `strict=True` + add pre-check `if isinstance(result, (CancelledError, KeyboardInterrupt)): raise result` before line 830 + make memory save synchronous (`await` instead of `create_task`).

### P1.3 — LLM Token Waste (anthropic_llm.py, openai_llm.py)

| # | Issue | File:Line | Impact |
|---|-------|-----------|--------|
| 8 | **Streaming skips cache control** — `ask_stream()` doesn't call `_prepare_system_with_caching()` | anthropic_llm.py:479-510 | Repeated streaming pays full token cost |
| 9 | **MLX tool call parsing fragile** — regex fails on nested braces | openai_llm.py:354-382 | Tool calls silently dropped |

**Fix:** Call `_prepare_system_with_caching()` in `ask_stream()` + add JSON validation fallback in MLX parser.

### P1.4 — Tool Content Safety

| # | Issue | File:Line | Impact |
|---|-------|-----------|--------|
| 10 | **Browser content extraction no enforced size limit** — focus extraction falls back to full 100KB text | browser.py:143-201 | Massive tool results consume context |
| 11 | **Search deduplication too late** — expanded_search runs all variants before dedup | search.py:539-598 | Wasted API calls, duplicate results |
| 12 | **MCP initialization race** — multiple concurrent calls trigger duplicate init | mcp.py:1325-1329 | Multiple server connections |

**Fix:** Enforce `max_length` strictly (never return > limit) + deduplicate during variant execution + add `asyncio.Lock` for MCP initialization.

### P1.5 — Sandbox Cleanup

| # | Issue | File:Line | Impact |
|---|-------|-----------|--------|
| 13 | **Browser context not closed in sandbox pool** — only sets to None | sandbox_pool.py:275-287 | Connection leaks |
| 14 | **MCP cleanup timeout insufficient** — blocks agent shutdown | agent_task_runner.py:1093 | Hung shutdown |

**Fix:** Call `browser.context.close()` and `browser.browser.close()` before setting to None + implement non-blocking cleanup with fallback kill.

---

## Phase 2: HIGH Severity Fixes (25 issues)

### P2.1 — Stuck Detection Accuracy

| # | Issue | File:Line | Fix |
|---|-------|-----------|-----|
| 15 | Confidence score can exceed 1.0 before clamping | stuck_detector.py:282-296 | Normalize weights to sum ≤1.0 |
| 16 | False positive on tool argument changes | stuck_detector.py:327-365 | Exclude search query args from hash |
| 17 | Cache key uses truncated MD5 (collision risk) | stuck_detector.py:450 | Use full 32-char hex |

### P2.2 — Token & Memory Management

| # | Issue | File:Line | Fix |
|---|-------|-----------|-----|
| 18 | Token cache eviction too aggressive (10% batch) | token_manager.py:230-235 | Use LRU eviction (single oldest) |
| 19 | Memory trimming creates orphaned tool responses | token_manager.py:450-497 | Validate all tool_call_ids have matching responses |
| 20 | Usage not recorded on error paths | anthropic/openai_llm.py | Record usage even on failures |

### P2.3 — Workflow Robustness

| # | Issue | File:Line | Fix |
|---|-------|-----------|-----|
| 21 | Plan validation failure creates loop (no counter) | plan_act.py:1721-1724 | Add `_plan_validation_failures` counter, max=3 |
| 22 | Step dependencies can deadlock (all blocked) | plan_act.py:1822-1826 | Track consecutive blocked steps, escalate |
| 23 | No recovery from failed verification (immediate escalation) | plan_act.py:1764-1791 | Try replan before giving up |
| 24 | Error state recovery can loop infinitely | plan_act.py:1671-1685 | Add `_error_recovery_attempts` counter, max=3 |
| 25 | Iteration budget is per-step, not per-workflow | base.py:716-721 | Implement workflow-level token budget |

### P2.4 — Tool Reliability

| # | Issue | File:Line | Fix |
|---|-------|-----------|-----|
| 26 | Shell tool no output size limiting | shell.py:34-45 | Add `max_output_bytes` parameter |
| 27 | File read missing encoding spec | file.py:49-64 | Add encoding param, fallback to latin-1 |
| 28 | Browser page load race condition | playwright_browser.py:1201-1242 | Atomic wait-then-extract |
| 29 | Wide research no failure distinction | search.py:779-897 | Distinguish "no results" vs "search failed" |
| 30 | Browser fallback chain unbounded recursion | browser.py:238-302 | Add depth param, max 2 fallbacks |

### P2.5 — Concurrency & Sandbox

| # | Issue | File:Line | Fix |
|---|-------|-----------|-----|
| 31 | Semaphore per-batch not global | base.py:815-821 | Use class-level semaphore |
| 32 | Sandbox pool circuit breaker never exponentially backs off | sandbox_pool.py:197-233 | Add exponential backoff to reset time |
| 33 | LLM concurrency limiter semaphore leak on cancellation | llm_limiter.py:215-220 | Track acquisition state explicitly |
| 34 | Tool call JSON args silently set to {} on parse failure | openai/anthropic/ollama_llm.py | Log malformed JSON before fallback |
| 35 | OpenAI structured output truncation not detected | openai_llm.py:889-896 | Check `finish_reason` before JSON parse |

### P2.6 — LLM Integration

| # | Issue | File:Line | Fix |
|---|-------|-----------|-----|
| 36 | Anthropic system prompt cache control applied twice | anthropic_llm.py:183-247, 357 | Apply caching during conversion, not after |
| 37 | Response format silently dropped for OpenAI default endpoint | openai_llm.py:957-972 | Fix condition to include default OpenAI |
| 38 | Temperature silently dropped for o1/o3 models (no warning) | openai_llm.py:626-641 | Log when temperature is ignored |
| 39 | Hallucination detector not updated when MCP tools fail to load | base.py:156-185 | Validate tools exist before returning |

---

## Phase 3: MEDIUM Severity Fixes (35 issues)

### P3.1 — Execution & Planning

| # | Issue | Fix |
|---|-------|-----|
| 40 | Skip plan update decision unvalidated | Track last skipped update, check retroactively |
| 41 | Reflection trigger conditions not comprehensive | Add mandatory triggers for errors and low confidence |
| 42 | Parallel step failure cascade too aggressive | Distinguish "failed dependency" vs "unmet dependency" |
| 43 | Memory compaction timing assumes no stalls | Make compaction synchronous or add timeout |
| 44 | Verification loop counter semantics unclear | Rename to `_verification_revision_attempts` |
| 45 | No validation failure metrics/observability | Add span attributes and metrics |
| 46 | LangGraph routing doesn't validate state keys | Add required key validation before routing |
| 47 | Compliance check happens too late (post-execution) | Check after planning, before execution |
| 48 | Task state manager unsynchronized with plan state | Add explicit sync method |

### P3.2 — Tool Quality

| # | Issue | Fix |
|---|-------|-----|
| 49 | PDF extraction assumes pdftotext installed | Check availability, return informative error |
| 50 | HTTP session reuse without health validation | Add ping/health check, configurable TTL |
| 51 | MCP tool schema cache served stale on refresh failure | Return error instead of old cache |
| 52 | Search query expansion creates duplicates | Add similarity check before adding variant |
| 53 | Browser element extraction limits arbitrary | Make limits adaptive to page complexity |
| 54 | File write tool no atomic write support | Implement write-to-temp-then-rename |
| 55 | Tool profiler stats accumulate without cleanup | Keep last 1000 calls, implement rotation |
| 56 | MCP resource template matching uses naive regex | Use proper URI template library (RFC 6570) |

### P3.3 — LLM Efficiency

| # | Issue | Fix |
|---|-------|-----|
| 57 | Message sanitization O(3n) — 3 sequential passes | Combine into single pass with early returns |
| 58 | Structured output caching not effective | Factor out schema instruction, mark cacheable |
| 59 | No JSON repair logic before retry | Add regex-based JSON repair before re-calling LLM |
| 60 | Anthropic tool conversion runs every call (no caching) | Cache converted tools with hash key |
| 61 | MLX tool injection adds 370 tokens of boilerplate per call | Move to system prompt or compress |
| 62 | TOOL_SECTION_MAP duplicates tool-to-section mapping | Use single source of truth |
| 63 | Prompt cache manager hash-based detection too strict | Use fuzzy matching for cache stability |

### P3.4 — Sandbox & Concurrency

| # | Issue | Fix |
|---|-------|-----|
| 64 | Docker sandbox HTTP timeout 600s for all operations | Use per-operation timeouts (5s/30s/60s) |
| 65 | Browser pre-warm leaves browser in inconsistent state on failure | Explicit shutdown on initialize failure |
| 66 | Parallel executor dependencies incomplete (shell, git) | Add comprehensive dependency graph |
| 67 | MCP init failure silently suppressed in gather | Only suppress specific exceptions |
| 68 | Browser not released before sandbox destroy | Release browser before destroy |
| 69 | Health check can cause exponential task spawning | Add exponential backoff between retries |

### P3.5 — Agent Core

| # | Issue | Fix |
|---|-------|-----|
| 70 | Parallel execution ignores tool data dependencies | Check file path conflicts in args |
| 71 | Memory compaction during execution causes context loss | Track tool use before execution |
| 72 | Background task cleanup doesn't wait for cancellation | Wait for cancel with timeout |
| 73 | Model name matching too broad ("gpt" in "deepseek-gpt") | Use exact match or startswith |
| 74 | Iteration budget ignores tool complexity weighting | Add tool-specific cost weights |

---

## Phase 4: LOW Severity & Optimizations (34 issues)

| # | Issue | Fix |
|---|-------|-----|
| 75 | System prompt build uses naive string concatenation | Use list + join |
| 76 | Token manager cache miss on first request | Pre-warm cache with common prompts |
| 77 | Prompt compressor list truncation not format-aware | Detect format (JSON, YAML) before truncate |
| 78 | OpenAI message validation no cross-reference check | Add tool_call_id ↔ tool_call validation |
| 79 | Token manager pressure thresholds hardcoded | Make configurable per instance |
| 80 | Context pressure thresholds not per-session | Allow override per agent type |
| 81 | Error pattern analyzer init fails at DEBUG level | Log at WARNING for init failures |
| 82 | Tool result truncation doesn't show what was removed | Add content type indicator |
| 83 | Search cache eviction uses timestamp not access frequency | Consider LFU |
| 84 | File preview truncation inconsistent (5000 stored vs 500 shown) | Standardize |
| 85 | Browser focus extraction scores all paragraphs | Early exit when sufficient content found |
| 86 | Parallel tool exception loses stack trace | Log exception before converting |
| 87 | Sandbox pool warmup size mismatch causes thrashing | Track target size carefully |
| 88 | Stuck detector accepts empty tool_name | Add validation |
| 89 | DNS resolution in sandbox creation is blocking | Use asyncio.to_thread() |
| 90 | Tool event handler missing error context | Add tool_name/call_id to log |
| 91-108 | Various minor logging, naming, documentation issues | Individual fixes |

---

## Implementation Priority Matrix

```
                    HIGH IMPACT
                        │
         Phase 1        │        Phase 2
     (CRITICAL, 14)     │     (HIGH, 25)
     ─ Workflow loops    │  ─ Stuck detection
     ─ Parallel safety   │  ─ Token management
     ─ LLM cache         │  ─ Tool reliability
     ─ Content limits    │  ─ Concurrency fixes
                        │
  ──────────────────────┼────────────────────── URGENCY
                        │
         Phase 4        │        Phase 3
      (LOW, 34)         │     (MEDIUM, 35)
     ─ Optimizations    │  ─ Execution quality
     ─ Naming/logging   │  ─ LLM efficiency
     ─ Minor fixes      │  ─ Sandbox lifecycle
                        │
                    LOW IMPACT
```

---

## Expected Outcomes

| Phase | Issues | Agent Impact |
|-------|--------|-------------|
| **Phase 1** | 14 | Eliminates infinite loops, prevents silent data loss, saves ~40% token cost on streaming, prevents 100KB tool results |
| **Phase 2** | 25 | Better stuck detection accuracy, proper error recovery, reliable tool execution, safe concurrency |
| **Phase 3** | 35 | Smarter planning, faster execution, efficient LLM usage, clean sandbox lifecycle |
| **Phase 4** | 34 | Polish, observability, minor perf gains |

---

## Files Most Affected

| File | Issues | Priority |
|------|--------|----------|
| `agents/base.py` | 15 | Phase 1-3 |
| `flows/plan_act.py` | 12 | Phase 1-2 |
| `tools/search.py` | 5 | Phase 1-2 |
| `tools/browser.py` | 5 | Phase 1-2 |
| `agents/stuck_detector.py` | 4 | Phase 2 |
| `agents/token_manager.py` | 4 | Phase 2-3 |
| `llm/anthropic_llm.py` | 4 | Phase 1-3 |
| `llm/openai_llm.py` | 5 | Phase 2-3 |
| `tools/mcp.py` | 3 | Phase 1-2 |
| `langgraph/nodes/reflection.py` | 2 | Phase 1-2 |
| `core/sandbox_pool.py` | 3 | Phase 1-2 |
| `agent_task_runner.py` | 3 | Phase 1-2 |

---

## Testing Strategy

1. **Phase 1 tests:** Workflow timeout integration test, parallel execution with cancellation, streaming cache verification
2. **Phase 2 tests:** Stuck detection accuracy suite, memory trimming validation, tool failure recovery
3. **Phase 3 tests:** End-to-end plan→execute→verify cycle, LLM mock with cache hit verification
4. **Phase 4 tests:** Performance benchmarks before/after
