# Pythinker Metrics + Quota + Token Calculator + Rate Limiter + Design System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a durable quota-aware usage platform for Pythinker with accurate token accounting, enforceable limits, low-cardinality observability, and a frontend design-system-backed quota UX.

**Architecture:** Keep business logic in domain/application layers and expose enforcement only through interfaces. Use a two-layer control model: (1) Manus-style credit/quota ledger for budget ownership (daily/monthly/session and credit-balance visibility), and (2) Redis-backed token bucket for short-window ingress throttling (`rate` + `burst`). Persist historical usage in MongoDB aggregates, and route both quota decisions and UI projections through one token-calculation domain service.

**Tech Stack:** FastAPI, Redis (Lua scripts), MongoDB/Beanie, Prometheus metrics, optional OpenTelemetry, Vue 3 + TypeScript + CSS custom properties.

---

## Related Plans

- **Search API Rate Limiting & IP Blocking Fix Plan** — `docs/plans/2026-03-02-search-api-rate-limiting-ip-blocking-fix-plan.md`
  - Coordinates with **Task 7** of this plan on Prometheus metric naming conventions and label cardinality rules.
  - New search metrics (`pythinker_search_429_total`, `pythinker_search_provider_health_score`) must follow the same low-cardinality label standards defined in this plan's Task 7.
  - Fix 7 of the search plan adds `pythinker_search_request_total{status}` and `pythinker_search_key_exhaustion_ratio` — wire these through the same `MetricsPortAdapter` path used here.

---

## Assumptions

1. We are enhancing the existing backend app (`backend/app/main.py`) rather than the placeholder gateway (`backend/app/gateway/main.py`).
2. Quota enforcement should prioritize authenticated user identity over raw IP, with IP fallback only when auth is unavailable.
3. This repository is development-only, so schema changes and breaking API adjustments are acceptable if fully implemented and tested.
4. Existing `UsageService` remains the aggregation backbone; we add quota state and estimator APIs around it.
5. We retain the current Redis availability model (fail closed for auth-critical checks, safe fallback behavior for non-auth paths).

---

## Algorithm Selection (Validated 2026-03-02)

1. **Token bucket (selected for ingress throttling):** best fit for interactive API traffic that must allow short bursts while maintaining a stable long-term rate. This is consistent with major gateway implementations that expose `rate` + `burst` controls.
2. **Leaky bucket (not selected as primary):** useful when strict output smoothing is required, but it introduces queueing/delay behavior that can degrade perceived latency for chat/agent requests.
3. **Sliding window (secondary/optional):** gives stricter boundary fairness than fixed windows, but typically requires more state and is better reserved for abuse-sensitive endpoints instead of all traffic.
4. **Manus-style credits (selected for spend control):** model credits as account budget state, separate from request-rate throttling. Credits are debited by weighted token cost and exposed as remaining balance/reset metadata in API/UI.

**Decision:** Use **credit ledger + token bucket** as default architecture. Keep sliding-window checks optional for specific abuse cases and avoid leaky-bucket queue semantics for normal interactive request handling.

---

## Evidence-Backed Standards To Apply

1. Prometheus: keep metric label cardinality low; avoid per-user/per-session labels in exported metrics. Use counters for totals and histograms for latency with SLO-aligned buckets.
2. FastAPI middleware: middleware order is stack-based (last added runs first on request), so rate-limiting/logging order must be explicit and tested.
3. Redis counters: execute `INCR`/`INCRBY` + conditional `EXPIRE` atomically in Lua to avoid race/leak windows.
4. Ingress limiter algorithm: use token bucket with explicit refill rate and burst capacity (`tokens_per_fill`, `fill_interval`, `max_tokens`) instead of fixed-window-only gating.
5. Credit system design: keep budget ledger independent from rate limiter; support deterministic debit order, expiry/reset semantics, and remaining-balance introspection.
6. HTTP 429 semantics: include `Retry-After` on throttled responses.
7. HTTP `RateLimit-*` fields: as of March 2, 2026, this remains IETF Internet-Draft work; keep these headers feature-flagged and avoid hard dependencies.
8. Token counting: use `tiktoken.encoding_for_model()` with safe fallback to known encoding.
9. OpenTelemetry semantic conventions: emit low-cardinality route templates (`http.route`), not raw dynamic URLs.
10. Design tokens (DTCG format): use a token file as source-of-truth (`$value`, `$type`), generate runtime CSS variables from it, and consume semantic tokens in components.

---

## Target Outcomes (Acceptance)

1. Accurate token usage for request/session/day/month from one shared token-calculation service.
2. Enforced Manus-style credit/quota policy (daily/monthly + optional per-session budget + remaining balance) with explicit API responses and UI visibility.
3. Rate limiting uses token bucket (`rate` + `burst`), returns standards-aligned metadata (`Retry-After` and optional `RateLimit-*` fields), and is tested for Redis primary + in-memory fallback paths.
4. Metrics dashboard can answer:
   - How many requests were limited and why?
   - How much token budget was consumed/blocked?
   - Where is latency introduced (queue vs model vs middleware)?
5. Frontend usage pages expose remaining quota, reset windows, and projected spend/tokens.
6. Usage/Quota UI styling is fully tokenized (no hard-coded colors in quota components).

---

## Delivery Sequence

### Task 1: Baseline + Contract Freeze

**Files:**
- Modify: `docs/architecture/ARCHITECTURE_ENHANCEMENT_PLAN.md`
- Create: `docs/plans/2026-03-02-metrics-quota-baseline.md`
- Test: `backend/tests/application/services/test_usage_service.py`

**Step 1: Write failing regression tests for current contract snapshots**

```python
# backend/tests/application/services/test_usage_service.py
async def test_usage_summary_contract_snapshot():
    summary = await service.get_usage_summary("user-1")
    assert set(summary.keys()) == {"today", "month"}
```

**Step 2: Run test to verify baseline behavior**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_usage_service.py -v`

Expected: PASS for current contract, used as freeze point before adding quota fields.

**Step 3: Document baseline metrics + route inventory**

Capture existing metric names in `backend/app/core/prometheus_metrics.py` and current middleware behavior in `backend/app/core/middleware.py`.

**Step 4: Commit baseline snapshot**

```bash
git add docs/plans/2026-03-02-metrics-quota-baseline.md backend/tests/application/services/test_usage_service.py
git commit -m "docs: capture metrics and usage baseline before quota refactor"
```

---

### Task 2: Introduce Domain Quota Model + Repository Port

**Files:**
- Create: `backend/app/domain/models/quota.py`
- Create: `backend/app/domain/repositories/quota_repository.py`
- Modify: `backend/app/domain/models/__init__.py`
- Test: `backend/tests/domain/models/test_quota_model.py`

**Step 1: Write failing domain tests**

```python
def test_quota_window_remaining_never_negative():
    window = QuotaWindow(limit_tokens=1000, used_tokens=1200)
    assert window.remaining_tokens == 0
```

**Step 2: Run test to verify fail**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/models/test_quota_model.py -v`

Expected: FAIL (missing model).

**Step 3: Implement minimal domain model + protocol**

Include:
- `QuotaWindow` (daily/monthly/session)
- `QuotaDecision` (`allow`, `warn`, `block`)
- `CreditGrant` / `CreditBalance` model primitives for prepaid budget semantics
- `QuotaRepository` port with atomic consume/check methods

**Step 4: Re-run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/domain/models/quota.py backend/app/domain/repositories/quota_repository.py backend/app/domain/models/__init__.py backend/tests/domain/models/test_quota_model.py
git commit -m "feat(domain): add quota model and repository port"
```

---

### Task 3: Token Calculator as Single Source of Truth

**Files:**
- Create: `backend/app/domain/services/usage/token_calculator.py`
- Modify: `backend/app/domain/services/agents/token_manager.py`
- Modify: `backend/app/application/services/usage_service.py`
- Test: `backend/tests/domain/services/usage/test_token_calculator.py`
- Test: `backend/tests/test_token_manager.py`

**Step 1: Write failing calculator tests**

```python
def test_token_calculator_uses_model_encoding_fallback():
    calc = TokenCalculator()
    result = calc.count_text("gpt-4o", "hello world")
    assert result.total_tokens > 0
```

**Step 2: Run tests to verify fail**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/usage/test_token_calculator.py -v`

Expected: FAIL (missing service).

**Step 3: Implement token calculator**

Rules:
- Use `tiktoken.encoding_for_model(model)` first.
- On unknown model, fallback to `get_encoding("cl100k_base")`.
- Expose deterministic methods for `count_text`, `count_messages`, and estimator metadata.

**Step 4: Integrate existing `TokenManager` to delegate counting to calculator**

Keep `TokenManager` pressure/trim logic; remove duplicated counting paths.

**Step 5: Re-run tests**

Run:
- `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/usage/test_token_calculator.py tests/test_token_manager.py -v`

Expected: PASS.

**Step 6: Commit**

```bash
git add backend/app/domain/services/usage/token_calculator.py backend/app/domain/services/agents/token_manager.py backend/app/application/services/usage_service.py backend/tests/domain/services/usage/test_token_calculator.py backend/tests/test_token_manager.py
git commit -m "feat(usage): centralize token accounting with token calculator"
```

---

### Task 4: Quota Service + Infrastructure Repository

**Files:**
- Create: `backend/app/application/services/quota_service.py`
- Create: `backend/app/infrastructure/repositories/redis_quota_repository.py`
- Modify: `backend/app/infrastructure/storage/redis.py`
- Modify: `backend/app/core/config_auth.py`
- Modify: `backend/app/core/config_features.py`
- Test: `backend/tests/application/services/test_quota_service.py`
- Test: `backend/tests/infrastructure/repositories/test_redis_quota_repository.py`

**Step 1: Write failing service tests**

```python
async def test_quota_blocks_when_daily_limit_exceeded():
    decision = await service.consume_tokens(user_id="u1", tokens=500)
    assert decision.allowed is False
    assert decision.reason == "daily_limit_exceeded"
```

Also add tests for:
- deterministic credit debit order across grants
- expired grant exclusion from available balance
- response metadata includes remaining credits + reset timestamps

**Step 2: Run tests to verify fail**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_quota_service.py -v`

Expected: FAIL.

**Step 3: Implement Redis-backed atomic quota ledger + counters**

Use Lua script per window:
- `INCRBY` token usage key
- initialize `EXPIRE` when first written
- return `{used, ttl, allowed}`

Support windows:
- daily
- monthly
- optional per-session budget gate

Add credit-ledger behavior:
- consume weighted usage from available balance atomically
- prevent negative balance
- return post-consume remaining credits for API/UI projection

**Step 4: Add config flags**

Add settings:
- `quota_enforcement_enabled`
- `quota_daily_tokens_default`
- `quota_monthly_tokens_default`
- `quota_warn_threshold`
- `quota_credit_grants_enabled`

**Step 5: Re-run tests**

Expected: PASS for both service and repository tests.

**Step 6: Commit**

```bash
git add backend/app/application/services/quota_service.py backend/app/infrastructure/repositories/redis_quota_repository.py backend/app/infrastructure/storage/redis.py backend/app/core/config_auth.py backend/app/core/config_features.py backend/tests/application/services/test_quota_service.py backend/tests/infrastructure/repositories/test_redis_quota_repository.py
git commit -m "feat(quota): add redis-backed quota service and config"
```

---

### Task 5: API Rate Limiter Hardening + Header Contract

**Files:**
- Modify: `backend/app/core/middleware.py`
- Modify: `backend/app/interfaces/errors/exception_handlers.py`
- Create: `backend/tests/core/test_rate_limit_middleware.py`
- Modify: `backend/app/main.py`

**Step 1: Write failing middleware tests**

```python
async def test_rate_limit_response_contains_retry_after_and_ratelimit_fields(client):
    response = await trigger_limit(client)
    assert response.status_code == 429
    assert "Retry-After" in response.headers
```

**Step 2: Run tests to verify fail**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/core/test_rate_limit_middleware.py -v`

Expected: FAIL.

**Step 3: Refactor keying + token bucket limiter**

- Prefer user key (`user_id`) when authenticated.
- Fallback to client IP.
- Use low-cardinality route group keys (method + route template group).
- Use token bucket semantics for ingress limiting:
  - `max_tokens` (burst capacity)
  - `tokens_per_fill`
  - `fill_interval`
- Add explicit config knobs for refill/burst so values can be tuned without code edits.
- Keep sliding-window checks optional and endpoint-specific (not global default).

**Step 4: Emit standards-friendly throttling metadata**

Always include:
- `Retry-After`

Feature-flag optional headers:
- `RateLimit-Limit`
- `RateLimit-Remaining`
- `RateLimit-Reset`
- `RateLimit-Policy`

**Step 5: Normalize 429 response body shape**

Use one API error structure for middleware and exception handler paths.

**Step 6: Re-run tests**

Expected: PASS.

**Step 7: Commit**

```bash
git add backend/app/core/middleware.py backend/app/interfaces/errors/exception_handlers.py backend/tests/core/test_rate_limit_middleware.py backend/app/main.py
git commit -m "feat(rate-limit): harden limiter keys and add throttle header contract"
```

---

### Task 6: Usage + Quota API Surface

**Files:**
- Modify: `backend/app/interfaces/schemas/usage.py`
- Modify: `backend/app/interfaces/api/usage_routes.py`
- Modify: `backend/app/application/services/usage_service.py`
- Modify: `backend/app/application/services/token_service.py`
- Create: `backend/tests/interfaces/api/test_usage_quota_routes.py`

**Step 1: Write failing API tests**

```python
async def test_usage_summary_returns_quota_block():
    response = client.get("/api/v1/usage/summary")
    assert response.json()["data"]["quota"]["daily"]["remaining_tokens"] >= 0
```

**Step 2: Run tests to verify fail**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_usage_quota_routes.py -v`

Expected: FAIL.

**Step 3: Add endpoints + schema extensions**

Add:
- `GET /usage/quota`
- `POST /usage/token-estimate`

Extend summary payload with:
- daily/monthly limits
- remaining tokens
- reset timestamps
- projected cost/tokens

**Step 4: Wire through quota + token calculator services**

No duplicated math in routes.

**Step 5: Re-run tests**

Expected: PASS.

**Step 6: Commit**

```bash
git add backend/app/interfaces/schemas/usage.py backend/app/interfaces/api/usage_routes.py backend/app/application/services/usage_service.py backend/app/application/services/token_service.py backend/tests/interfaces/api/test_usage_quota_routes.py
git commit -m "feat(api): expose quota and token estimation endpoints"
```

---

### Task 7: Metrics Expansion for Quota + Limiter + Estimator

**Files:**
- Modify: `backend/app/core/prometheus_metrics.py`
- Modify: `backend/app/domain/external/observability.py`
- Modify: `backend/app/infrastructure/observability/metrics_port_adapter.py`
- Test: `backend/tests/infrastructure/observability/test_robustness_metrics.py`
- Test: `backend/tests/infrastructure/observability/test_metrics_port_adapter.py`

**Step 1: Write failing metrics tests**

```python
def test_quota_block_counter_increments_without_user_labels():
    record_quota_decision("block", scope="daily")
    assert metric_value("pythinker_quota_decisions_total", {"decision": "block", "scope": "daily"}) == 1
```

**Step 2: Run tests to verify fail**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/observability/test_robustness_metrics.py tests/infrastructure/observability/test_metrics_port_adapter.py -v`

Expected: FAIL.

**Step 3: Add new metrics**

Counters:
- `pythinker_quota_decisions_total{scope,decision,reason}`
- `pythinker_rate_limit_events_total{bucket,decision,mode}`

Gauges:
- `pythinker_quota_utilization_ratio{scope}`

Histograms:
- `pythinker_rate_limit_check_latency_seconds{mode}`
- `pythinker_token_estimator_latency_seconds{model_group}`

**Step 4: Enforce low-cardinality labels only**

No `user_id`, no `session_id`, no raw path labels.

**Step 5: Re-run tests**

Expected: PASS.

**Step 6: Commit**

```bash
git add backend/app/core/prometheus_metrics.py backend/app/domain/external/observability.py backend/app/infrastructure/observability/metrics_port_adapter.py backend/tests/infrastructure/observability/test_robustness_metrics.py backend/tests/infrastructure/observability/test_metrics_port_adapter.py
git commit -m "feat(metrics): add quota and rate-limit observability with low-cardinality labels"
```

---

### Task 8: Frontend API Types + Quota Composable

**Files:**
- Modify: `frontend/src/api/usage.ts`
- Create: `frontend/src/composables/useQuota.ts`
- Create: `frontend/src/composables/useTokenEstimator.ts`
- Modify: `frontend/tests/composables/useReport.spec.ts` (or split new tests)
- Create: `frontend/tests/composables/useQuota.spec.ts`
- Create: `frontend/tests/composables/useTokenEstimator.spec.ts`

**Step 1: Write failing composable tests**

```ts
it('computes warning state at configured threshold', () => {
  const state = computeQuotaState({ used: 80, limit: 100, warnThreshold: 0.8 })
  expect(state.level).toBe('warning')
})
```

**Step 2: Run tests to verify fail**

Run: `cd frontend && bun run vitest tests/composables/useQuota.spec.ts tests/composables/useTokenEstimator.spec.ts`

Expected: FAIL.

**Step 3: Implement quota + estimator API client and composables**

- strict TypeScript interfaces
- no `any`
- predictable error-state mapping for 429 and quota-block responses

**Step 4: Re-run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/api/usage.ts frontend/src/composables/useQuota.ts frontend/src/composables/useTokenEstimator.ts frontend/tests/composables/useQuota.spec.ts frontend/tests/composables/useTokenEstimator.spec.ts
git commit -m "feat(frontend): add quota and token estimator composables"
```

---

### Task 9: Usage UI + Quota UX + Design Token Application

**Files:**
- Modify: `frontend/src/components/settings/UsageSettings.vue`
- Modify: `frontend/src/components/settings/ModelSettings.vue`
- Create: `frontend/src/components/settings/QuotaOverviewCard.vue`
- Create: `frontend/src/components/settings/TokenEstimatePanel.vue`
- Modify: `frontend/tests/components/DesignSurfaceTokens.spec.ts`
- Create: `frontend/tests/components/QuotaOverviewCard.spec.ts`

**Step 1: Write failing component tests**

```ts
it('renders remaining tokens and reset time', async () => {
  // mount with mocked quota data
  expect(screen.getByText(/remaining/i)).toBeInTheDocument()
})
```

**Step 2: Run tests to verify fail**

Run: `cd frontend && bun run vitest tests/components/QuotaOverviewCard.spec.ts`

Expected: FAIL.

**Step 3: Implement quota-centric UI states**

- normal/warning/blocked visuals
- explicit retry timing for rate-limited actions
- estimator preview before submit

**Step 4: Enforce tokenized styling only**

No hard-coded color literals in new quota components.

**Step 5: Re-run tests**

Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/src/components/settings/UsageSettings.vue frontend/src/components/settings/ModelSettings.vue frontend/src/components/settings/QuotaOverviewCard.vue frontend/src/components/settings/TokenEstimatePanel.vue frontend/tests/components/DesignSurfaceTokens.spec.ts frontend/tests/components/QuotaOverviewCard.spec.ts
git commit -m "feat(ui): add quota-aware usage panels with tokenized styling"
```

---

### Task 10: DTCG Token Source-of-Truth + Build Pipeline

**Files:**
- Create: `frontend/src/design/tokens/base.tokens.json`
- Create: `frontend/src/design/tokens/semantic.tokens.json`
- Create: `frontend/scripts/build-design-tokens.ts`
- Modify: `frontend/src/assets/theme.css`
- Modify: `frontend/src/assets/global.css`
- Create: `frontend/tests/utils/themeTokens.spec.ts` (extend if exists)

**Step 1: Write failing token build/test assertions**

```ts
it('generates css variables from semantic token files', () => {
  const css = buildTokens(mockTokens)
  expect(css).toContain('--color-surface-primary')
})
```

**Step 2: Run tests to verify fail**

Run: `cd frontend && bun run vitest tests/utils/themeTokens.spec.ts`

Expected: FAIL.

**Step 3: Implement local token build script**

- Parse DTCG-style JSON (`$value`, `$type`).
- Generate deterministic CSS vars file imported by `global.css`.
- Keep existing theme vars, alias gradually to semantic tokens.

**Step 4: Re-run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/design/tokens/base.tokens.json frontend/src/design/tokens/semantic.tokens.json frontend/scripts/build-design-tokens.ts frontend/src/assets/theme.css frontend/src/assets/global.css frontend/tests/utils/themeTokens.spec.ts
git commit -m "feat(design-system): add DTCG token source and css generation"
```

---

### Task 11: End-to-End Verification + Ops Docs

**Files:**
- Create: `docs/operations/QUOTA_AND_RATE_LIMIT_RUNBOOK.md`
- Modify: `backend/README.md`
- Modify: `frontend/README.md`
- Modify: `monitoring/grafana/README.md`

**Step 1: Add verification checklist tests and commands doc**

Include smoke sequence:
1. quota under limit
2. quota warning threshold
3. quota block
4. rate limit 429 with headers
5. Redis unavailable fallback path

**Step 2: Run full backend validation**

Run: `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`

Expected: PASS.

**Step 3: Run full frontend validation**

Run: `cd frontend && bun run lint && bun run type-check`

Expected: PASS.

**Step 4: Commit final docs + verifications**

```bash
git add docs/operations/QUOTA_AND_RATE_LIMIT_RUNBOOK.md backend/README.md frontend/README.md monitoring/grafana/README.md
git commit -m "docs: add quota/rate-limit runbook and verification guide"
```

---

## Concrete Implementation Notes (How To Apply In This Codebase)

1. Keep `RateLimitMiddleware` in `backend/app/core/middleware.py` as the single HTTP ingress limiter; do not split logic across gateway placeholder code.
2. Keep model/token accounting in domain/app services; avoid computing tokens directly in routes/components.
3. Keep Manus-style credit ledger logic in application/domain services and separate from short-window token bucket middleware logic.
4. Prefer extending `UsageService` and `/usage/*` routes over adding duplicate analytics endpoints.
5. Add new Prometheus metrics to `backend/app/core/prometheus_metrics.py` and expose through existing adapter paths used by domain services.
6. For UI, extend `UsageSettings.vue` first, then split into focused components once tests are green.
7. For design system migration, alias new semantic tokens into existing `theme.css` variables to avoid a big-bang rewrite.

---

## Risks and Mitigations

1. **Metric cardinality explosion**
   - Mitigation: enforce label allowlist in tests; reject `user_id/session_id/path` labels.
2. **Quota/rate-limit double blocking confusion**
   - Mitigation: distinct error codes and UI messaging (`RATE_LIMIT_EXCEEDED` vs `QUOTA_EXCEEDED`).
3. **Redis outage behavior drift**
   - Mitigation: explicit fallback tests; document allowed/blocked behavior per endpoint class.
4. **Inconsistent token estimates across models**
   - Mitigation: central token calculator and model-specific fallback tests.
5. **Design token drift**
   - Mitigation: generated CSS from DTCG source + snapshot tests on generated output.
6. **Credit ledger and rate-limiter state divergence**
   - Mitigation: enforce call order (`quota consume` before model execution, `token bucket check` at ingress), and add consistency assertions in integration tests.
7. **Token bucket misconfiguration (too small burst or too slow refill)**
   - Mitigation: externalize rate/burst config per endpoint class and run load-test calibration before enabling strict enforcement.

---

## Best-Practice Sources Used

- FastAPI middleware behavior and ordering: https://fastapi.tiangolo.com/tutorial/middleware/
- Redis atomic limiter pattern (`INCR` + conditional `EXPIRE` in Lua): https://redis.io/docs/latest/commands/incr/
- AWS API Gateway throttling model (`rate` + `burst` token bucket): https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html
- NGINX request limiting uses leaky bucket semantics: https://docs.nginx.com/nginx/admin-guide/security-controls/controlling-access-proxied-http/
- Cloudflare fixed vs sliding window explanation and boundary behavior: https://developers.cloudflare.com/ai-gateway/features/rate-limiting/
- Traefik rate limiting uses token bucket semantics (`average/period` + `burst`): https://doc.traefik.io/traefik/middlewares/http/ratelimit/
- Envoy local token bucket + optional global layered limiting: https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/other_features/global_rate_limiting
- Stripe billing credits (credit grants, expiry, priority, balance): https://docs.stripe.com/billing/subscriptions/usage-based/billing-credits
- Prometheus instrumentation/cardinality guidance: https://prometheus.io/docs/practices/instrumentation/
- Prometheus naming guidance: https://prometheus.io/docs/practices/naming/
- HTTP 429 (`Retry-After`) semantics: https://www.rfc-editor.org/rfc/rfc6585.html
- Current HTTP `RateLimit-*` work status (IETF HTTPAPI draft, checked March 2, 2026): https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/
- RFC 9457 Problem Details (`application/problem+json`): https://www.rfc-editor.org/rfc/rfc9457.html
- tiktoken model-aware encoding: https://github.com/openai/tiktoken
- OpenTelemetry HTTP semantic conventions (`http.route` low-cardinality template): https://opentelemetry.io/docs/specs/semconv/registry/attributes/http/
- DTCG design token format module (stable 2025.10 report): https://www.designtokens.org/tr/2025.10/format/

---

---

### Task 12: Coordinate Search API Metric Labels with Quota Plan

**Scope:** Ensures that search-infrastructure metrics added by the Search Rate Limiting Fix Plan use the same label conventions, adapter paths, and registry patterns established in Tasks 7 of this plan. This is a review+integration task, not a new implementation.

**Files to review:**
- `backend/app/core/prometheus_metrics.py` — verify `pythinker_search_429_total`, `pythinker_search_request_total`, `pythinker_search_provider_health_score`, and `pythinker_search_key_exhaustion_ratio` are registered here (not inline in infrastructure code)
- `backend/app/domain/external/observability.py` — add observer method stubs for search health metrics if not already present
- `backend/app/infrastructure/observability/metrics_port_adapter.py` — wire search health recording calls through the adapter

**Step 1: Verify label cardinality compliance**

All labels on new search metrics must be from this approved bounded set:

| Label | Allowed Values | Cardinality |
|---|---|---|
| `provider` | serper, tavily, brave, exa, duckduckgo, bing, google, searxng | ≤8 |
| `status` | success, rate_limited, error, circuit_open | 4 |
| `scope` | daily, monthly, session | 3 |
| `decision` | allow, warn, block | 3 |

**Prohibited labels** (same as Task 7): `user_id`, `session_id`, raw URL paths, key hashes.

**Step 2: Run unified metrics test**

```bash
conda activate pythinker && cd backend
pytest -p no:cov -o addopts= tests/infrastructure/observability/ -v
```

Expected: PASS for all existing + new search metric tests.

**Step 3: Commit coordination changes only**

```bash
git add backend/app/core/prometheus_metrics.py \
        backend/app/domain/external/observability.py \
        backend/app/infrastructure/observability/metrics_port_adapter.py
git commit -m "chore(metrics): align search health metrics with quota plan label conventions"
```

---

## Completion Gate

Do not mark this initiative complete until all are true:

1. Backend lint + format + full tests pass.
2. Frontend lint + type-check + relevant tests pass.
3. Quota and rate-limiting smoke scenarios verified manually.
4. Grafana queries for new metrics validated with non-zero sample data.
5. Runbook updated with rollback toggles and feature flags.
