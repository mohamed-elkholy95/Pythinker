# Search Orchestrator And Stability Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade multi-search architecture to a professional, resilient provider strategy with explicit priority `Tavily -> DuckDuckGo -> Serper`, while fixing the backend/sandbox/frontend reliability issues confirmed in live logs.

**Architecture:** Introduce a policy-driven search orchestration layer in the existing factory/fallback path. Keep provider adapters isolated, add provider-level cooldown/circuit behavior, and use typed settings for chain order, key-usage policy, and per-provider backoff. Apply targeted reliability fixes in auth refresh, delivery integrity gating, sandbox CDP/screencast recovery, and frontend startup/proxy resilience.

**Tech Stack:** Python (FastAPI, httpx, asyncio), Redis-backed key pool, Docker Compose, Vue + Vite, pytest + ruff.

---

## Scope, Constraints, Assumptions

ASSUMPTIONS I'M MAKING:
1. Required provider order is strictly `Tavily (primary) -> DuckDuckGo -> Serper` for default web search execution.
2. “Tavily 1 key first” means defaulting to primary Tavily key only, with multi-key failover optional via explicit setting.
3. `Serper` remains enabled as tertiary fallback, not removed entirely.
4. Current log issues (Serper exhaustion storms, local auth refresh failures, delivery-integrity gate blocks, sandbox pthread/fork bursts, transient frontend proxy failures) are all in-scope.

-> Correct these assumptions before implementation if any are wrong.

## Evidence Baseline (from live code + logs)

1. Search chain currently routes `tavily -> serper -> exa -> duckduckgo` when provider is `tavily` ([factory.py](backend/app/infrastructure/external/search/factory.py)).
2. Serper exhaustion repeats heavily in backend logs and triggers repeated fallback attempts.
3. Local auth refresh fails because `local_admin` is synthetic (not persisted) but refresh path requires DB lookup ([auth_service.py](backend/app/application/services/auth_service.py)).
4. Delivery integrity blocks report delivery on unresolved citation/truncation issues despite auto-repair attempts.
5. Sandbox experienced historical `pthread_create` / `fork` resource errors and one screencast recovery failure.
6. Frontend dev proxy showed transient `ECONNREFUSED` events (likely backend reload/startup windows).

---

### Task 1: Add Explicit Search Chain Policy (Tavily -> DuckDuckGo -> Serper)

**Files:**
- Modify: `backend/app/core/config_features.py`
- Modify: `backend/app/infrastructure/external/search/factory.py`
- Modify: `backend/app/interfaces/api/settings_routes.py`
- Modify: `backend/app/domain/models/user_settings.py`
- Test: `backend/tests/infrastructure/external/search/test_search_factory_chain_policy.py` (create)

**Step 1: Write failing tests for chain order and config parsing**

```python
def test_tavily_default_chain_prefers_duckduckgo_before_serper():
    ...
    assert resolved_chain == ["tavily", "duckduckgo", "serper"]
```

**Step 2: Run targeted tests (expect FAIL)**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/search/test_search_factory_chain_policy.py -v`
Expected: FAIL on missing policy fields / old chain order.

**Step 3: Implement new policy settings + chain builder**

- Add typed config fields:
  - `search_provider_chain: str = "tavily,duckduckgo,serper"`
  - `search_chain_enforce_order: bool = True`
- Update factory to build chain from policy first, then append selected provider if absent.

**Step 4: Re-run tests (expect PASS)**

Run same pytest command.

**Step 5: Commit**

```bash
git add backend/app/core/config_features.py backend/app/infrastructure/external/search/factory.py backend/app/interfaces/api/settings_routes.py backend/app/domain/models/user_settings.py backend/tests/infrastructure/external/search/test_search_factory_chain_policy.py
git commit -m "feat(search): enforce Tavily->DuckDuckGo->Serper chain policy"
```

---

### Task 2: Add Provider Cooldown To Stop Serper Exhaustion Storms

**Files:**
- Modify: `backend/app/infrastructure/external/search/factory.py`
- Test: `backend/tests/infrastructure/external/search/test_search_factory_fallback_cooldown.py` (create)

**Step 1: Write failing tests for provider-level cooldown skip**

```python
def test_exhausted_serper_is_temporarily_skipped_between_calls():
    ...
    assert serper_call_count == 1
```

**Step 2: Run test (expect FAIL)**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/search/test_search_factory_fallback_cooldown.py -v`

**Step 3: Implement cooldown memory in `FallbackSearchEngine`**

- Track last provider failure type per provider.
- If provider failed with quota-exhausted message, skip provider until cooldown expires.
- Log one warning per cooldown window (no spam).

**Step 4: Re-run tests (expect PASS)**

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/search/factory.py backend/tests/infrastructure/external/search/test_search_factory_fallback_cooldown.py
git commit -m "feat(search): add provider cooldown to suppress repeated exhausted fallbacks"
```

---

### Task 3: Implement Tavily Primary-Key-First Policy

**Files:**
- Modify: `backend/app/core/config_features.py`
- Modify: `backend/app/infrastructure/external/search/factory.py`
- Test: `backend/tests/infrastructure/external/search/test_tavily_primary_key_mode.py` (create)

**Step 1: Write failing tests for primary-only Tavily mode**

```python
def test_tavily_primary_only_ignores_fallback_keys_when_enabled():
    ...
    assert len(engine._key_pool.keys) == 1
```

**Step 2: Run test (expect FAIL)**

**Step 3: Add config + apply in provider kwargs**

- New setting: `tavily_primary_key_only: bool = True`
- In `_provider_kwargs("tavily")`, only include `fallback_api_keys` when the setting is `False`.

**Step 4: Re-run tests (expect PASS)**

**Step 5: Commit**

```bash
git add backend/app/core/config_features.py backend/app/infrastructure/external/search/factory.py backend/tests/infrastructure/external/search/test_tavily_primary_key_mode.py
git commit -m "feat(search): support Tavily primary-key-only mode"
```

---

### Task 4: Harden DuckDuckGo Adapter For Professional Fallback Quality

**Files:**
- Modify: `backend/app/infrastructure/external/search/duckduckgo_search.py`
- Modify: `backend/app/infrastructure/external/search/base.py` (if shared helpers needed)
- Test: `backend/tests/infrastructure/external/search/test_duckduckgo_search.py` (create)

**Step 1: Write failing parser/robustness tests**

```python
def test_duckduckgo_parses_alternate_snippet_container():
    ...

def test_duckduckgo_sets_stable_user_agent_and_timeout():
    ...
```

**Step 2: Run targeted tests (expect FAIL)**

**Step 3: Implement adapter hardening**

- Set explicit headers (`User-Agent`, `Accept-Language`).
- Add graceful parsing for selector variants.
- Add defensive handling for empty/partial markup.

**Step 4: Re-run tests (expect PASS)**

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/search/duckduckgo_search.py backend/app/infrastructure/external/search/base.py backend/tests/infrastructure/external/search/test_duckduckgo_search.py
git commit -m "feat(search): harden DuckDuckGo fallback adapter"
```

---

### Task 5: Reduce Search Burst Amplification In `wide_research`

**Files:**
- Modify: `backend/app/domain/services/tools/search.py`
- Modify: `backend/app/core/config_features.py`
- Test: `backend/tests/domain/services/tools/test_search_budget.py`
- Test: `backend/tests/domain/services/research/test_wide_research.py`

**Step 1: Add failing tests for burst control and fallback amplification**

```python
def test_wide_research_limits_parallel_calls_under_provider_stress():
    ...
```

**Step 2: Run tests (expect FAIL)**

**Step 3: Implement control knobs**

- Add setting `wide_research_parallelism_limit` (default 3).
- Bind semaphore to setting (currently hardcoded 5).
- Add per-invocation cap for repeated provider failures.

**Step 4: Re-run tests (expect PASS)**

**Step 5: Commit**

```bash
git add backend/app/domain/services/tools/search.py backend/app/core/config_features.py backend/tests/domain/services/tools/test_search_budget.py backend/tests/domain/services/research/test_wide_research.py
git commit -m "fix(search): reduce wide_research burst pressure and fallback amplification"
```

---

### Task 6: Fix Local Auth Refresh (Eliminate `local_admin not found`)

**Files:**
- Modify: `backend/app/application/services/auth_service.py`
- Modify: `backend/app/application/services/token_service.py`
- Test: `backend/tests/application/services/test_auth_service_refresh_local.py` (create)

**Step 1: Write failing tests for local-provider refresh flow**

```python
@pytest.mark.asyncio
async def test_refresh_token_local_provider_does_not_require_db_user():
    ...
```

**Step 2: Run tests (expect FAIL)**

**Step 3: Implement fix**

- In `refresh_access_token`, branch on `auth_provider == "local"`.
- Rehydrate local user from token payload (`sub`, `fullname`, `email`, `role`) instead of DB lookup.
- Ensure refresh token payload carries required local fields.

**Step 4: Re-run tests (expect PASS)**

**Step 5: Commit**

```bash
git add backend/app/application/services/auth_service.py backend/app/application/services/token_service.py backend/tests/application/services/test_auth_service_refresh_local.py
git commit -m "fix(auth): support refresh flow for local auth synthetic user"
```

---

### Task 7: Stabilize Delivery Integrity Gate (Citation/Truncation)

**Files:**
- Modify: `backend/app/domain/services/agents/response_generator.py`
- Modify: `backend/app/domain/services/agents/execution.py`
- Test: `backend/tests/integration/test_delivery_integrity_gate.py`
- Test: `backend/tests/domain/services/agents/test_citation_integrity.py`

**Step 1: Add failing tests for unresolved citation false-block and truncation-repair flow**

```python
def test_delivery_gate_does_not_block_when_citation_repair_succeeds():
    ...
```

**Step 2: Run tests (expect FAIL)**

**Step 3: Implement deterministic repair-before-block behavior**

- If `citation_integrity_unresolved` appears, perform one deterministic citation reconciliation pass using tracked sources.
- Only block when post-repair validation still fails.
- Keep strict mode for truly unresolved truncation.

**Step 4: Re-run tests (expect PASS)**

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/response_generator.py backend/app/domain/services/agents/execution.py backend/tests/integration/test_delivery_integrity_gate.py backend/tests/domain/services/agents/test_citation_integrity.py
git commit -m "fix(delivery): deterministic citation repair before strict gate blocking"
```

---

### Task 8: Fix Sandbox Thread/Fork Pressure And Screencast Recovery

**Files:**
- Modify: `docker-compose-development.yml`
- Modify: `sandbox/supervisord.conf`
- Modify: `sandbox/app/api/v1/screencast.py`
- Modify: `sandbox/app/services/cdp_screencast.py`
- Test: `sandbox/tests/test_screencast.py`
- Test: `sandbox/tests/test_screencast_recovery.py` (create)

**Step 1: Add failing tests around preemption + recovery from detached page**

```python
@pytest.mark.asyncio
async def test_stream_recovery_handles_not_attached_page_without_terminal_failure():
    ...
```

**Step 2: Run sandbox tests (expect FAIL)**

Run: `cd sandbox && pytest tests/test_screencast.py tests/test_screencast_recovery.py -v`

**Step 3: Implement runtime stability changes**

- Increase sandbox PID headroom in dev compose (e.g., `1024 -> 1536`) with explicit comment.
- Constrain `socat` child fan-out (`fork,max-children=<N>`) to avoid uncontrolled process bursts.
- Strengthen screencast recovery path for `Not attached to an active page` without terminal stream failure.

**Step 4: Re-run sandbox tests (expect PASS)**

**Step 5: Commit**

```bash
git add docker-compose-development.yml sandbox/supervisord.conf sandbox/app/api/v1/screencast.py sandbox/app/services/cdp_screencast.py sandbox/tests/test_screencast.py sandbox/tests/test_screencast_recovery.py
git commit -m "fix(sandbox): reduce thread/fork pressure and harden CDP screencast recovery"
```

---

### Task 9: Frontend Startup/Proxy Resilience Improvements

**Files:**
- Modify: `frontend/vite.config.ts`
- Modify: `docker-compose-development.yml`
- Test: `frontend/tests/api/client.sse-close.spec.ts`
- Test: `frontend/tests/composables/useCircuitBreaker.spec.ts`

**Step 1: Add failing tests for transient backend unavailability UX/retry behavior**

```ts
it('surfaces transient backend unavailability as retryable state', async () => {
  ...
})
```

**Step 2: Run frontend tests (expect FAIL)**

Run: `cd frontend && bun run test frontend/tests/api/client.sse-close.spec.ts frontend/tests/composables/useCircuitBreaker.spec.ts`

**Step 3: Implement improvements**

- Keep proxy error suppression, but add explicit dev-only backoff guidance message.
- Add startup dependency hardening (backend readiness wait before frontend dev server starts).

**Step 4: Re-run tests (expect PASS)**

**Step 5: Commit**

```bash
git add frontend/vite.config.ts docker-compose-development.yml frontend/tests/api/client.sse-close.spec.ts frontend/tests/composables/useCircuitBreaker.spec.ts
git commit -m "fix(frontend): improve startup/proxy resilience during backend restarts"
```

---

### Task 10: Full Verification + Regression Sweep

**Files:**
- Modify: `docs/DOCKER_LOG_DIAGNOSTIC_REPORT.md` (append post-fix verification evidence)

**Step 1: Run backend quality gates**

Run: `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`
Expected: PASS.

**Step 2: Run frontend quality gates**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: PASS.

**Step 3: Run sandbox tests**

Run: `cd sandbox && pytest`
Expected: PASS.

**Step 4: Run log regression check (4h window)**

Run:

```bash
docker logs --since 4h pythinker-main-backend-1 2>&1 | rg "All [0-9]+ Serper API keys exhausted|Refresh failed: user_id=local_admin|citation_integrity_unresolved|stream_truncation_unresolved"
docker logs --since 4h pythinker-main-sandbox-1 2>&1 | rg "pthread_create: Resource temporarily unavailable|fork\(\): Resource temporarily unavailable|Recovery failed — cannot restart screencast"
docker logs --since 4h pythinker-main-frontend-dev-1 2>&1 | rg "ECONNREFUSED|proxy error"
```

Expected: sharp reduction in repeated severe patterns; no `local_admin not found` refresh failures.

**Step 5: Commit verification evidence**

```bash
git add docs/DOCKER_LOG_DIAGNOSTIC_REPORT.md
git commit -m "docs: add post-remediation verification evidence"
```

---

## Exit Criteria

1. Default search chain executes in order: Tavily -> DuckDuckGo -> Serper.
2. Serper exhaustion no longer spams repeated warnings for the same cooldown window.
3. Local auth refresh no longer fails with `user_id=local_admin not found in database`.
4. Delivery integrity gate blocks only on true unresolved integrity failures after deterministic repair.
5. Sandbox no longer emits bursty `pthread_create/fork resource unavailable` under normal use.
6. Frontend degrades gracefully during backend restarts without noisy failure flood.

## Risk Controls

1. Keep all behavior toggled by settings where possible (`*_enabled`, `*_only`, cooldown durations).
2. Add targeted tests before implementation in every task.
3. Ship in small commits to allow quick rollback per subsystem.
4. Validate with 4-hour live log observation before calling complete.

## External References (validated during planning)

1. Tavily API docs (search/extract parameters, error codes incl. 429/432/433): https://docs.tavily.com/
2. Tavily SDK/API reference pages discovered via Ref MCP: https://docs.tavily.com/sdk/python/reference
3. DuckDuckGo Instant Answer API (officially documented API; not a full web-search SERP API): https://www.postman.com/api-evangelist/duckduckgo/documentation/i9r819s/duckduckgo-instant-answer-api
4. Serper endpoint/auth cross-check (OpenAPI mirror used because Ref-indexed official docs were unavailable in this environment): https://gist.github.com/timothymcmackin/29776d56a654e0a8cccda18a3213d774

