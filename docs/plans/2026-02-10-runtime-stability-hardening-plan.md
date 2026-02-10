# Runtime Stability Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate high-impact backend/runtime failures seen in production-like logs (WebSocket/ASGI failures, browser/CDP instability, Redis stream read faults, and severe session/chat latency spikes) while reducing recurrent quality regressions (token overflow churn, tool-sequence corruption, parser failures).

**Architecture:** We will stabilize the system in layers: transport/session lifecycle first, then browser and queue resilience, then LLM/message correctness, then performance. Every fix starts with a failing test and includes targeted instrumentation so regressions are detectable. Changes stay within existing boundaries (interfaces -> application -> domain -> infrastructure) and avoid broad refactors.

**Tech Stack:** FastAPI, WebSockets, asyncio, Playwright/CDP, Redis Streams, MongoDB, pytest, ruff.

---

## Scope and Priorities

P0:
- WebSocket no-sandbox failures and ASGI incomplete response errors.
- Browser/CDP crash and timeout cascades.
- Redis stream invalid ID / timeout read loops.

P1:
- Session creation and chat latency outliers.
- Token overflow churn and message trimming path quality.
- Incomplete tool sequence and JSON parse fallback reliability.

P2:
- Log-noise and environment hardening (auth-mode warnings, sandbox noise triage, optional frontend proxy resiliency).

---

### Task 0: Baseline and Guardrails

**Files:**
- Create: `docs/reports/2026-02-10-runtime-baseline.md`
- Modify: `docs/plans/2026-02-10-runtime-stability-hardening-plan.md`
- Test: `backend/tests/` (existing suites listed below)

**Step 1: Capture failing baseline evidence**

```bash
cd /Users/panda/Desktop/Projects/Pythinker

docker logs --since 2h pythinker-backend-1 2>&1 | tee /tmp/backend_2h.log

docker compose -f docker-compose-development.yml logs --since=2h 2>&1 | tee /tmp/stack_2h.log
```

**Step 2: Record error signatures and counts**

```bash
rg -i -c 'WebSocket error: Session has no sandbox environment|ASGI callable returned without completing response|tool_failed: browser_navigate|xread error|Invalid stream ID|Strategy _try_direct_parse failed|Incomplete tool sequence detected|Context \([0-9]+ tokens\) exceeds limit' /tmp/backend_2h.log
```

Expected: counts are non-zero for at least `ASGI`, `WebSocket no sandbox`, `xread`, and `browser_navigate timeout`.

**Step 3: Save baseline report**

- Write measured counts and top 20 latency endpoints into `docs/reports/2026-02-10-runtime-baseline.md`.

**Step 4: Verify no functional changes yet**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_session_routes.py -q
```

**Step 5: Commit baseline artifact**

```bash
git add docs/reports/2026-02-10-runtime-baseline.md docs/plans/2026-02-10-runtime-stability-hardening-plan.md
git commit -m "docs: add runtime stability baseline and implementation plan"
```

---

### Task 1: Fix VNC WebSocket Lifecycle and ASGI Incomplete Responses

**Files:**
- Modify: `backend/app/interfaces/api/session_routes.py`
- Modify: `backend/app/application/services/agent_service.py`
- Modify: `backend/tests/interfaces/api/test_session_routes.py`
- Create: `backend/tests/interfaces/api/test_session_vnc_websocket.py`

**Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_vnc_websocket_returns_policy_violation_when_session_has_no_sandbox(...):
    # assert close code 1008 and no ASGI incomplete response path

@pytest.mark.asyncio
async def test_vnc_websocket_closes_gracefully_when_client_disconnects(...):
    # assert no unhandled exception and no double-close
```

**Step 2: Run tests to verify failures**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_session_vnc_websocket.py -q
```

Expected: FAIL due to current mixed exception/close behavior.

**Step 3: Implement minimal fix**

```python
# session_routes.py (concept)
async def _safe_ws_close(ws: WebSocket, code: int, reason: str) -> None:
    with contextlib.suppress(Exception):
        await ws.close(code=code, reason=reason)

# vnc_websocket():
# - reject missing sandbox as NotFoundError/RuntimeError mapped to 1008
# - guard forwarding loops against expected close/disconnect exceptions
# - ensure pending tasks are cancelled and awaited exactly once
# - avoid raising after close to prevent ASGI incomplete response log
```

Also in `agent_service.get_vnc_url`, normalize missing sandbox to `NotFoundError("Session has no sandbox environment")`.

**Step 4: Run tests to verify pass**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_session_routes.py tests/interfaces/api/test_session_vnc_websocket.py -q
```

**Step 5: Commit**

```bash
git add backend/app/interfaces/api/session_routes.py backend/app/application/services/agent_service.py backend/tests/interfaces/api/test_session_routes.py backend/tests/interfaces/api/test_session_vnc_websocket.py
git commit -m "fix: harden vnc websocket lifecycle and close-path handling"
```

---

### Task 2: Fix Redis Stream Invalid-ID and Timeout Read Loops

**Files:**
- Modify: `backend/app/infrastructure/external/message_queue/redis_stream_queue.py`
- Create: `backend/tests/infrastructure/external/message_queue/test_redis_stream_queue.py`

**Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_get_normalizes_invalid_start_id_to_safe_cursor(...):
    # start_id invalid -> no warning spam, returns (None, None)

@pytest.mark.asyncio
async def test_get_caps_block_ms_below_socket_timeout(...):
    # large block_ms gets clamped

@pytest.mark.asyncio
async def test_get_handles_redis_timeout_without_exception(...):
    # TimeoutError returns (None, None)
```

**Step 2: Run tests to verify failures**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/message_queue/test_redis_stream_queue.py -q
```

**Step 3: Implement minimal fix**

```python
# redis_stream_queue.py (concept)
def _normalize_start_id(start_id: str | None) -> str:
    if not start_id or start_id == "0":
        return "0-0"
    if start_id == "$":
        return "$"
    return start_id if "-" in start_id else "0-0"

# get(): normalize ID before xread, keep timeout cap, demote repeated invalid-id log spam to debug after first warning
```

**Step 4: Run tests to verify pass**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/message_queue/test_redis_stream_queue.py -q
```

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/message_queue/redis_stream_queue.py backend/tests/infrastructure/external/message_queue/test_redis_stream_queue.py
git commit -m "fix: normalize redis stream cursor and harden xread error handling"
```

---

### Task 3: Harden Browser/CDP Crash Recovery and Pool Cleanup Behavior

**Files:**
- Modify: `backend/app/infrastructure/external/browser/playwright_browser.py`
- Modify: `backend/app/infrastructure/external/browser/connection_pool.py`
- Modify: `backend/tests/infrastructure/external/browser/test_connection_pool.py`
- Create: `backend/tests/infrastructure/external/browser/test_playwright_browser_recovery.py`

**Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_pool_force_release_logs_once_per_failure_window(...):
    # avoid repetitive force-release spam loops

@pytest.mark.asyncio
async def test_browser_reinitialize_after_target_crash(...):
    # target crash triggers bounded re-init and clean state
```

**Step 2: Run tests to verify failures**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/browser/test_connection_pool.py tests/infrastructure/external/browser/test_playwright_browser_recovery.py -q
```

**Step 3: Implement minimal fix**

```python
# connection_pool.py: add per-URL cooldown for force_release_all logging/action
# playwright_browser.py: centralize crash classification and reconnect path with bounded retries
# ensure failed background futures are observed/logged exactly once
```

**Step 4: Run tests to verify pass**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/browser/test_connection_pool.py tests/infrastructure/external/browser/test_playwright_browser_recovery.py -q
```

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/browser/playwright_browser.py backend/app/infrastructure/external/browser/connection_pool.py backend/tests/infrastructure/external/browser/test_connection_pool.py backend/tests/infrastructure/external/browser/test_playwright_browser_recovery.py
git commit -m "fix: improve browser crash recovery and pool cleanup stability"
```

---

### Task 4: Eliminate Fire-and-Forget Unretrieved Exceptions

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `backend/tests/domain/services/test_agent_task_runner_cleanup.py`

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_fire_and_forget_consumes_task_exception(...):
    # background task exception is captured/logged, not unretrieved
```

**Step 2: Run test to verify failure**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_task_runner_cleanup.py -q
```

**Step 3: Implement minimal fix**

```python
# agent_task_runner.py
# in _fire_and_forget: add done callback that calls task.exception() inside suppress
# and structured warning log when exception exists
```

**Step 4: Run test to verify pass**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_task_runner_cleanup.py -q
```

**Step 5: Commit**

```bash
git add backend/app/domain/services/agent_task_runner.py backend/tests/domain/services/test_agent_task_runner_cleanup.py
git commit -m "fix: consume background task exceptions in task runner"
```

---

### Task 5: Reduce Session Creation/Chat Latency Outliers

**Files:**
- Modify: `backend/app/application/services/agent_service.py`
- Modify: `backend/app/interfaces/api/session_routes.py`
- Modify: `backend/tests/application/services/test_agent_service_create_session.py`
- Create: `backend/tests/application/services/test_agent_service_latency_guards.py`

**Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_create_session_returns_quickly_when_warmup_exceeds_budget(...):
    # response should return within configured budget

@pytest.mark.asyncio
async def test_chat_timeout_path_emits_controlled_status_not_hang(...):
    # no multi-minute blocking for predictable timeout cases
```

**Step 2: Run tests to verify failure**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_agent_service_create_session.py tests/application/services/test_agent_service_latency_guards.py -q
```

**Step 3: Implement minimal fix**

```python
# agent_service.py
# enforce strict timeout budget around warm-up wait path and non-blocking fallback
# add explicit timing logs around create_session/chat critical sections
# keep session status transitions deterministic (INITIALIZING -> PENDING)
```

**Step 4: Run tests to verify pass**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_agent_service_create_session.py tests/application/services/test_agent_service_latency_guards.py -q
```

**Step 5: Commit**

```bash
git add backend/app/application/services/agent_service.py backend/app/interfaces/api/session_routes.py backend/tests/application/services/test_agent_service_create_session.py backend/tests/application/services/test_agent_service_latency_guards.py
git commit -m "fix: enforce session warm-up latency budgets and deterministic fallback"
```

---

### Task 6: Stabilize Tool-Sequence and JSON Parse Fallback Path

**Files:**
- Modify: `backend/app/infrastructure/external/llm/openai_llm.py`
- Modify: `backend/app/infrastructure/utils/llm_json_parser.py`
- Create: `backend/tests/infrastructure/external/llm/test_openai_llm_tool_sequence.py`
- Create: `backend/tests/infrastructure/utils/test_llm_json_parser.py`

**Step 1: Write failing tests**

```python
def test_validate_and_fix_messages_preserves_tool_call_contract(...):
    # no orphan tool_call/tool message pairs after normalization

@pytest.mark.asyncio
async def test_llm_json_parser_fallback_returns_structured_default_without_warning_storm(...):
    # repeated malformed payload should not generate repeated warning storm
```

**Step 2: Run tests to verify failure**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/llm/test_openai_llm_tool_sequence.py tests/infrastructure/utils/test_llm_json_parser.py -q
```

**Step 3: Implement minimal fix**

```python
# openai_llm.py: tighten _validate_and_fix_messages to preserve valid tool-call adjacency and drop invalid orphan states deterministically
# llm_json_parser.py: add bounded warning dedup for repeated strategy failures per request/session
```

**Step 4: Run tests to verify pass**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/llm/test_openai_llm_tool_sequence.py tests/infrastructure/utils/test_llm_json_parser.py -q
```

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/llm/openai_llm.py backend/app/infrastructure/utils/llm_json_parser.py backend/tests/infrastructure/external/llm/test_openai_llm_tool_sequence.py backend/tests/infrastructure/utils/test_llm_json_parser.py
git commit -m "fix: harden tool-sequence normalization and json parser fallback"
```

---

### Task 7: Reduce Token Overflow Churn and Preserve Response Quality

**Files:**
- Modify: `backend/app/domain/services/agents/token_manager.py`
- Modify: `backend/tests/test_token_manager.py`

**Step 1: Write failing tests**

```python
def test_trim_messages_limits_warning_churn_on_repeated_overflow(...):
    # overflow path should be bounded and deterministic

def test_trim_messages_preserves_recent_tool_pairs_when_compacting(...):
    # avoid creating orphan tool messages during trim
```

**Step 2: Run tests to verify failure**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/test_token_manager.py -q
```

**Step 3: Implement minimal fix**

```python
# token_manager.py: tighten preserve_recent backoff and pair-aware trimming
# emit one structured warning per compaction cycle, not per internal iteration
```

**Step 4: Run tests to verify pass**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/test_token_manager.py -q
```

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/token_manager.py backend/tests/test_token_manager.py
git commit -m "fix: make token compaction deterministic and pair-safe"
```

---

### Task 8: Session Not Found and No-Sandbox Error Contract Cleanup

**Files:**
- Modify: `backend/app/application/services/agent_service.py`
- Modify: `backend/app/interfaces/errors/exception_handlers.py`
- Modify: `backend/tests/application/services/test_agent_service_not_found.py`
- Modify: `backend/tests/test_error_handler.py`

**Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_get_vnc_url_missing_sandbox_raises_not_found(...):
    # normalize to domain/app-level error contract

def test_exception_handler_maps_not_found_without_error_log_pollution(...):
    # expected 404 paths should be warning/info level
```

**Step 2: Run tests to verify failure**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_agent_service_not_found.py tests/test_error_handler.py -q
```

**Step 3: Implement minimal fix**

```python
# agent_service.py: raise NotFoundError for known absent resources
# exception_handlers.py: maintain 404 semantics without escalating to error-level noise
```

**Step 4: Run tests to verify pass**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_agent_service_not_found.py tests/test_error_handler.py -q
```

**Step 5: Commit**

```bash
git add backend/app/application/services/agent_service.py backend/app/interfaces/errors/exception_handlers.py backend/tests/application/services/test_agent_service_not_found.py backend/tests/test_error_handler.py
git commit -m "fix: normalize not-found and no-sandbox error contracts"
```

---

### Task 9: Config and Operational Hardening

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `docker-compose-development.yml`
- Modify: `MONITORING.md`
- Create: `docs/reports/2026-02-10-runtime-hardening-checklist.md`

**Step 1: Write failing checks**

```bash
# static checks + config smoke
echo "AUTH_PROVIDER=$AUTH_PROVIDER"
```

Define test/check expectation: dev allows `none`, but startup emits single warning and explicit environment banner.

**Step 2: Implement minimal hardening**

```python
# config.py: reduce repeated auth warning emission (warn once per process)
```

```yaml
# docker-compose-development.yml:
# optional: set explicit redis config / tuned socket timeout values matching app expectations
```

**Step 3: Update monitoring docs with new alert signatures**

- Add counters and alert recommendations for:
  - `vnc_ws_rejected_no_sandbox`
  - `asgi_incomplete_response`
  - `redis_xread_invalid_id`
  - `browser_cdp_init_retry_exhausted`

**Step 4: Validate stack starts cleanly**

```bash
docker compose -f docker-compose-development.yml up -d

docker compose -f docker-compose-development.yml logs --tail=200 backend | rg -i "warning|error|ASGI callable|Session has no sandbox|xread error"
```

**Step 5: Commit**

```bash
git add backend/app/core/config.py docker-compose-development.yml MONITORING.md docs/reports/2026-02-10-runtime-hardening-checklist.md
git commit -m "chore: harden runtime config defaults and monitoring playbook"
```

---

## Final Verification Gate (Required)

Run all before claiming completion:

```bash
cd /Users/panda/Desktop/Projects/Pythinker

cd frontend && bun run lint && bun run type-check

conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
```

Then run runtime smoke:

```bash
docker compose -f docker-compose-development.yml logs --since=15m backend | rg -i "ASGI callable returned without completing response|WebSocket error: Session has no sandbox environment|tool_failed: browser_navigate|Invalid stream ID specified as stream command argument"
```

Expected: no new matches during smoke scenario.

---

## Rollout Strategy

1. Land P0 tasks first and deploy to dev stack.
2. Run 24-hour log watch with counters.
3. Land P1 quality/perf tasks.
4. Land P2 config/noise tasks.
5. Re-baseline with the same queries from Task 0 and compare deltas.

---

## Acceptance Criteria

1. `ASGI callable returned without completing response` occurrences are eliminated in normal VNC use.
2. `WebSocket error: Session has no sandbox environment` no longer appears as error-level runtime fault for expected reject paths.
3. Redis stream invalid ID warning loop does not recur.
4. Browser navigation timeout/crash retries are bounded and recover cleanly.
5. `POST /api/v1/sessions` and `/chat` tail latencies materially reduce (target p95 under 30s in dev load tests).
6. Token overflow and tool-sequence warnings are reduced without losing correctness.
