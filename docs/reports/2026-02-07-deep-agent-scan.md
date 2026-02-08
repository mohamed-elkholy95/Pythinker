# Deep Agent Code Scan Report
**Date:** 2026-02-07
**Scope:** Agent logic, retry mechanisms, error handling, workflow flow control
**Files Scanned:** 35+ files across 5 parallel analysis streams
**Total Issues Found:** 163 (9 CRITICAL, 43 HIGH, 67 MEDIUM, 44 LOW)

---

## CRITICAL Issues (9) — Fix Immediately

### C1. Fast Path Code Is Dead/Unreachable Due to Indentation Bug
**File:** `flows/plan_act.py:1551-1577`
The entire fast path execution block is nested inside the `else` branch for `QueryIntent.TASK`. When intent is GREETING/KNOWLEDGE/BROWSE/SEARCH, `use_fast_path=True` is set but execution falls past the `else` — the fast path code is never reached. For TASK intent, `use_fast_path` is always False. **The fast path feature is completely non-functional.** All queries fall through to the full planning workflow.
**Fix:** Dedent lines 1554-1577 by one level so they execute after the classification chain.

### C2. `store_observation` Method Does Not Exist on MemoryService
**File:** `agents/execution.py:966`
`self._memory_service.store_observation(...)` will raise `AttributeError` at runtime whenever the multimodal findings persistence path is hit (every 2 view operations).
**Fix:** Add `store_observation` to MemoryService or remove the call.

### C3. `format_memories_for_context` Is Async but Called Without `await`
**File:** `agents/execution.py:203`
The missing `await` means `memory_context` is a coroutine object, not a string. When injected into the prompt, it appears as `<coroutine object ...>`, polluting the LLM prompt.
**Fix:** Add `await` before the call.

### C4. Race Condition on `self.memory` Between Background Save and Main Loop
**File:** `agents/base.py:1170-1185`
In `_handle_token_limit_exceeded()`, a background task references `self.memory`. Between task creation and execution, `self.memory` is mutated by the main loop. The background save captures whatever state messages are in when `await` runs.
**Fix:** Snapshot trimmed messages before creating background task: `snapshot = Memory(messages=list(self.memory.messages))`.

### C5. `ask_streaming` Fallback Duplicates User Message in Memory
**File:** `agents/base.py:1318-1320`
The request is added to memory on line 1313. The fallback calls `self.ask(request)` which calls `ask_with_messages([{"role":"user","content":request}])`, adding the user message a second time.
**Fix:** Use `ask_with_messages([])` in the fallback path.

### C6. Stale `event` Variable Referenced After Planning Loop
**File:** `flows/plan_act.py:1806`
After `async for event in self.planner.create_plan(...)`, the code references `event.plan.steps` but `event` may not be a PlanEvent (last event type), or may be undefined.
**Fix:** Replace `event.plan.steps` with `self.plan.steps` (already set on line 1763).

### C7. `ensure_sandbox()` Silent Failure on Connection Error
**File:** `docker_sandbox.py:78-88`
After 5 `ConnectError` attempts, `ensure_sandbox()` returns silently without raising. Callers assume sandbox is ready. All subsequent operations fail with confusing errors.
**Fix:** Raise an explicit error after max connection attempts.

### C8. MCP `cleanup()` Leaves Zombie Processes on Failure
**File:** `tools/mcp.py:1005-1015`
When `_exit_stack.aclose()` fails, exception is caught but `_clients` is cleared and `_initialized=False`. Underlying stdio subprocess transports remain running. Subsequent init creates new subprocesses without cleaning up old ones.
**Fix:** Attempt individual client session cleanup on failure. Add subprocess kill fallback.

### C9. `ask_stream()` in Anthropic LLM Has Zero Retry Logic
**File:** `anthropic_llm.py:459-518`
`ask()` has retry with backoff; `ask_stream()` has none. Transient `APIConnectionError`, `InternalServerError`, `RateLimitError` all propagate immediately.
**Fix:** Add at minimum a connection-level retry wrapper around the streaming call.

---

## HIGH Issues (43)

### Agent Base & Execution (13 HIGH)

| # | File | Lines | Issue |
|---|------|-------|-------|
| H1 | `base.py` | 778, 879 | `tool_call["id"]` — KeyError if "id" key missing. Use `.get("id")` |
| H2 | `base.py` | 956-979 | Budget exhaustion yields ErrorEvent AND stale MessageEvent |
| H3 | `base.py` | 648-649 | MCP `_can_parallelize_tools` substring matching too broad — destructive MCP tools could be parallelized |
| H4 | `base.py` | 915 | Redundant security assessment AFTER tool already executed |
| H5 | `base.py` | 728-955 | `execute()` never yields assistant reasoning text during tool-calling iterations |
| H6 | `execution.py` | 164-171 | `execute_step` permanently mutates `self.tools` — skill tool restrictions leak across steps |
| H7 | `execution.py` | 152 | `execute_step` permanently mutates `self.system_prompt` for skill context |
| H8 | `execution.py` | 179-180 | All skill loading exceptions silently caught as warning |
| H9 | `execution.py` | 282-283 | Step JSON parsing failure is unhandled — step stays RUNNING forever |
| H10 | `execution.py` | 365 | `step.status = COMPLETED` unconditionally overrides FAILED status set on error |
| H11 | `error_handler.py` | 489, 521 | Retry counter set inconsistently — backoff exponent always one step behind |
| H12 | `error_handler.py` | 572-634 | `can_retry()` initially False causes unreachable RuntimeError |
| H13 | `error_handler.py` | 174-251 | Error type classification has false positives (keyword collisions) |

### Plan-Act Workflow (5 HIGH)

| # | File | Lines | Issue |
|---|------|-------|-------|
| H14 | `plan_act.py` | 196, 1786+ | `_plan_validation_failures` never reset — monotonically increases, becomes trigger-happy over session lifetime |
| H15 | `plan_act.py` | 185, 1452 | `_error_recovery_attempts` never reset — after 3 successful recoveries, all future errors are unrecoverable |
| H16 | `state_model.py` | 22 | REFLECTING state defined but never used — reflection feature is completely inert |
| H17 | `plan_act.py` | 283, 662 | Background tasks never awaited/canceled on workflow exit |
| H18 | `plan_act.py` | 1806+ | No guard against `self.plan` being None in multiple places |

### LLM Retry & Error (5 HIGH)

| # | File | Lines | Issue |
|---|------|-------|-------|
| H19 | `anthropic_llm.py` | 337-386 | Double-sleep on RateLimitError (backoff + loop-top retry delay) |
| H20 | `openai_llm.py` | 1189-1201 | Stream rate limit handler sleeps then re-raises — wasted delay if caller doesn't retry |
| H21 | `llm_limiter.py` | all | LLM concurrency limiter is dead code — never invoked anywhere |
| H22 | `anthropic_llm.py` | 335-518 | No CancelledError handling in ask/ask_stream |
| H23 | `openai_llm.py` | 540-558 | `_sanitize_messages` mutates tool_calls dicts in-place via shallow copy |

### Parallel Executor & Tools (8 HIGH)

| # | File | Lines | Issue |
|---|------|-------|-------|
| H24 | `search.py` | 566-577 | Race condition in expanded_search — concurrent tasks mutate shared `seen_urls` without lock |
| H25 | `parallel_executor.py` | 356-400 | `CancelledError` (BaseException) in gather `return_exceptions=True` treated as successful ToolResult |
| H26 | `parallel_executor.py` | 228-231 | Circular dependency fallback runs ALL remaining calls in parallel — defeats safety |
| H27 | `search.py` | 279-282 | Class-level mutable cache shared across all instances without thread safety |
| H28 | `search.py` | 606-647 | `_browse_top_results` is blocking (adds 7.5s+), not "non-blocking" as documented |
| H29 | `browser.py` | 71-84 | HTTP session singleton race condition — two coroutines can create leaked sessions |
| H30 | `file.py` | 352-364 | Shell injection in `_view_pdf` via unsanitized file path in f-string |
| H31 | `base.py` + `parallel_executor.py` | multiple | Two conflicting parallel execution systems with incompatible safe-tool lists |

### Sandbox & Infrastructure (12 HIGH)

| # | File | Lines | Issue |
|---|------|-------|-------|
| H32 | `docker_sandbox.py` | 42-47 | Auto-healing client race: two coroutines can create + leak clients simultaneously |
| H33 | `docker_sandbox.py` | 836 | `_resolve_hostname_to_ip` returns None → sandbox URLs become `http://None:8080` |
| H34 | `sandbox_pool.py` | 278-299 | `_prewarm_browser` closes browser context, defeating pre-warming purpose |
| H35 | `sandbox_pool.py` + `agent_service.py` | 251, 209 | Browser pre-warming uses `sandbox.ip_address` but DockerSandbox uses `self.ip` — always silently skipped |
| H36 | `agent_task_runner.py` | 1040 | Exception handler sets status to COMPLETED instead of FAILED |
| H37 | `agent_task_runner.py` | 351, 983 | `_pop_event` returns None but callers don't check — AttributeError on `.attachments` |
| H38 | `agent_task_runner.py` | 145 | Background tasks not cancelled in `destroy()` — reference destroyed sandbox |
| H39 | `agent_domain_service.py` | 66 | `_task_creation_locks` dict grows unboundedly, never cleaned |
| H40 | `agent_service.py` | 334-365 | Double sandbox destroy in `delete_session` and `stop_session` |
| H41 | `mcp.py` | 1345-1359 | `get_tools()` is sync — returns empty list during lazy init, LLM gets incomplete tool list |
| H42 | `mcp.py` | 459-570 | No timeout on MCP server connection or tool calls — hung server blocks forever |
| H43 | `token_manager.py` | 195-199 | Token cache hash truncated to 64 bits — collision can cause incorrect trim decisions |

---

## MEDIUM Issues (67) — Summary by Area

### Agent Base & Execution (16)
- Retry loop shares single `max_retries` budget across 4 different failure modes (base.py:1042)
- System prompt only injected once on first call, changes ignored (base.py:1017)
- `cleanup_background_tasks` not called on normal exit (base.py:1206)
- `_is_read_only_tool` substring matching has false positives (base.py:668)
- Parallel tool execution silently drops calls beyond MAX_CONCURRENT_TOOLS (base.py:774)
- `_execute_parallel_tool` duplicates `_invoke_tool_with_semaphore` — dead code (base.py:658)
- `func_name` variable shadowed (execution.py:297,326)
- `_persist_key_findings` calls sync method on async service (execution.py:966)
- `step.status = COMPLETED` overrides FAILED (execution.py:365)
- CoVe verification + critic revision add 30-60s latency without timeout (execution.py)
- `_collected_sources` list grows unbounded (execution.py:1075)
- `_error_history` holds exception objects with full tracebacks (error_handler.py:293)
- `datetime.now` without timezone (error_handler.py:70)
- `get_recovery_stats` double-counts failures (error_handler.py:547)
- Stuck detector `_stuck_analysis` not cleared on pattern break (stuck_detector.py:309)
- Stuck detector `compute_trigram_embedding` uses `hash()` non-deterministic across processes (stuck_detector.py:65)

### Plan-Act Workflow (7)
- EXECUTING→EXECUTING self-transition works only due to hidden guard (state_model.py:40)
- PLANNING/VERIFYING can loop ~100 times via validation failures (plan_act.py:1786-1893)
- `_verification_loops` incremented only on REVISE, not full cycles (plan_act.py:1838)
- Streaming verification short-circuit can return false positives (verifier.py:510)
- Reflection fail-open doesn't increment counter → reflection storm under LLM failure (reflection.py:232)
- `_should_skip_step()` always returns False — dead code (plan_act.py:1149)
- PLANNING→COMPLETED skips SUMMARIZING — no compliance gates run (plan_act.py:1806)

### LLM Retry & Error (11)
- Multiple system messages: only last one kept by Anthropic converter (anthropic_llm.py:193)
- Stream usage estimated, not actual API-reported (anthropic_llm.py:128)
- OpenAI `ask_stream` silently drops tool call chunks (openai_llm.py:1159)
- LLM limiter singleton not event-loop-safe (llm_limiter.py:80)
- Tool responses with unknown IDs kept when pending IDs exist (openai_llm.py:600)
- MLX mode switch `continue` may double-inject tool instructions (openai_llm.py:779)
- `@lru_cache` permanently caches None from failed LLM init (llm/__init__.py:23)
- Tool result content None/multimodal not handled (anthropic_llm.py:233)
- `api_base=None` disables features for default OpenAI endpoint (openai_llm.py:1027)
- PromptCacheManager singleton ignores provider changes (prompt_cache_manager.py:615)
- `ask_structured` records usage on non-error path but not on fallback error (anthropic_llm.py:401)

### Parallel Executor & Tools (16)
- Read-after-write file dependency not detected (parallel_executor.py:174)
- `detect_dependencies` mutates original ToolCall objects (parallel_executor.py:162)
- `info_search_web` bypasses `search_prefer_browser` setting (search.py:707)
- Query normalization removes meaningful search terms like "best", "top" (search.py:397)
- `expanded_search` silently drops exceptions from gather (search.py:579)
- Browser tool SSRF potential — no URL validation on `search` method (browser.py:239)
- `html_to_text` regex-based HTML stripping is fragile (browser.py:95)
- `shell_wait` has no upper bound on `seconds` parameter (shell.py:86)
- Shell injection in `_view_pdf` — use `shlex.quote()` (file.py:352)
- `sandbox.shell_exec()` doesn't exist in Sandbox Protocol (file.py:358)
- `file_read_binary` and `file_stat` not in Sandbox Protocol (file.py:247, 300)
- `_parse_page_range` no bounds validation — "1-1000000" creates huge list (file.py:504)
- No path validation on file tool inputs (file.py:49-194)
- Tool name "search" overloaded between browser and search tools
- `_browse_top_results` causes browser contention during search (search.py:636)
- Two different ToolResult classes with same name (parallel_executor.py:44 vs tool_result.py)

### Sandbox & Infrastructure (17)
- `destroy()` blocks event loop with synchronous Docker API call (docker_sandbox.py:856)
- Cached sandbox may have destroyed/closed client (docker_sandbox.py:1064)
- Circuit breaker `_circuit_open_count` never fully resets (sandbox_pool.py:204)
- `stop()` destroys sandboxes sequentially without timeout (sandbox_pool.py:122)
- Global `_sandbox_pool` singleton not thread-safe (sandbox_pool.py:321)
- `_warm_pool` busy-waits when circuit breaker is open (sandbox_pool.py:171)
- `_tool_start_times` and `_file_before_cache` grow unboundedly (agent_task_runner.py:151)
- `_pending_tool_calls` never cleaned up on timeout (agent_task_runner.py:153)
- `init_mcp()` silently succeeds even if config loading raises (agent_task_runner.py:952)
- SSE event loop busy-waits with 50ms polling (agent_domain_service.py:766)
- `enqueue_user_message` doesn't load extra_mcp_configs (agent_domain_service.py:531)
- `_classify_intent_with_context` may trigger lazy load of all session events (agent_domain_service.py:332)
- `_warm_sandbox_for_session` can leak sandbox on race (agent_service.py:174)
- `_get_or_create_sandbox` doesn't save session after assigning sandbox_id (agent_service.py:751)
- MCP `_exit_stack` accumulates old connection contexts on reconnect (mcp.py:472)
- `record_tool_usage` missing params in failure path (mcp.py:992)
- `_store_memory_parallel` is actually sequential — dead parallel code (memory_service.py:247)

---

## Priority Fix Recommendations

### Immediate (Blocks functionality)
1. **C1** — Fast path indentation bug (feature completely broken)
2. **C2+C3** — MemoryService missing method + missing await (runtime crashes + LLM prompt pollution)
3. **C6** — Stale event variable (potential crash in PLANNING)
4. **H14+H15** — Never-reset counters (agent degrades over session lifetime)
5. **H35** — `ip_address` vs `ip` attribute (browser pre-warming never works)
6. **H36** — Task runner sets COMPLETED on exception (masks failures)

### High Priority (Reliability)
7. **C4+C5** — Memory race condition + message duplication
8. **C7+C8** — Sandbox silent failure + MCP zombie processes
9. **C9** — Stream retry logic missing
10. **H6+H7** — execute_step permanently mutates tools/prompt
11. **H24** — Search race condition (duplicate results)
12. **H25+H26** — Parallel executor CancelledError + circular dep fallback
13. **H37** — _pop_event None check missing

### Medium Priority (Robustness)
14. **H21** — Wire up LLM concurrency limiter
15. **H30** — Shell injection in PDF viewer (shlex.quote)
16. **H31** — Unify two parallel execution systems
17. **H34** — Fix sandbox pool browser pre-warming
18. **H42** — Add MCP connection/call timeouts

---

## Metrics Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 9 |
| HIGH | 43 |
| MEDIUM | 67 |
| LOW | 44 |
| **Total** | **163** |

| Scan Area | CRIT | HIGH | MED | LOW | Total |
|-----------|------|------|-----|-----|-------|
| Agent Base & Execution | 4 | 13 | 16 | 16 | 49 |
| Plan-Act Workflow | 2 | 5 | 7 | 6 | 20 |
| LLM Retry & Error | 1 | 5 | 11 | 8 | 25 |
| Parallel Executor & Tools | 0 | 8 | 16 | 9 | 33 |
| Sandbox & Infrastructure | 2 | 12 | 17 | 5 | 36 |
