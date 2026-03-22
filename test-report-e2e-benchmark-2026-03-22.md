# Pythinker E2E Verification & Benchmark Report

**Date:** 2026-03-22 07:17 EDT
**Environment:** Docker containers running (backend :8000, frontend :5174, sandbox :8082, redis, mongodb, qdrant, minio)
**Python env:** `/home/mac/miniconda3/envs/pythinker`
**Test runner:** pytest

---

## Phase 1: Health & Connectivity

| Endpoint | Status | Response Time (avg) |
|---|---|---|
| Backend `/health` | ✅ 200 OK | **0.79ms** |
| Frontend `/` | ✅ 200 OK | **1.48ms** |
| Sandbox `/` | ✅ 200 OK | **0.67ms** |

**Docker Containers:** All 6 containers healthy and running.
**Connectivity Script:** Not found at `scripts/test_connectivity.sh`.

---

## Phase 2: Backend Unit Tests

**Command:** `pytest tests/unit/ -v --tb=short` (with `JWT_SECRET_KEY` and `AUTH_PROVIDER=none`)

| Metric | Value |
|---|---|
| Passed | **182** |
| Failed | 0 |
| Skipped | 0 |
| Duration | 30.28s |
| Coverage | 19.41% |

**Status:** ✅ ALL PASSED

---

## Phase 3: Backend Integration Tests

**Command:** `pytest tests/integration/ -v --tb=short` (with `JWT_SECRET_KEY` and `AUTH_PROVIDER=none`)

| Metric | Value |
|---|---|
| Passed | **160** |
| Failed | 0 |
| Skipped | **60** |
| Duration | 123.52s |
| Coverage | 46.13% |

**Status:** ✅ ALL PASSED (with skips)

**Skip Reasons:**
- 38 skipped: `AUTH_PROVIDER` not set to `none` for auth-gated agent e2e tests
- 12 skipped: Redis unavailable via container hostname (`redis:6379`)
- 5 skipped: Sandbox API secret not configured for seccomp runtime tests
- 1 skipped: Local browser CDP endpoint unavailable
- 4 skipped: Various auth/browser requirements

---

## Phase 4: Backend E2E Tests

**Command:** `pytest tests/e2e/ -v --tb=short` (with `JWT_SECRET_KEY` and `AUTH_PROVIDER=none`)

| Metric | Value |
|---|---|
| Passed | **9** |
| Failed | 0 |
| Skipped | 0 |
| Duration | 4.72s |
| Coverage | 0.00% (no coverage for non-domain code) |

**Status:** ✅ ALL PASSED

---

## Phase 5: Backend Load/Benchmark Tests

**Command:** `pytest tests/load/ -v --tb=short`

| Metric | Value |
|---|---|
| Passed | **0** |
| Failed | 0 |
| Skipped | **0** |
| Duration | 4.52s |

**Status:** ⚠️ NO TESTS RAN — `tests/load/` directory exists but contains no runnable tests (all likely require specific infrastructure or configuration).

---

## Phase 6: Backend Domain Tests

**Command:** `pytest tests/domain/ -v --tb=short`

| Metric | Value |
|---|---|
| Passed | **3185** |
| Failed | **36** |
| Skipped | 19 |
| XFailed | 2 |
| Duration | 69.99s |
| Coverage | 44.97% |

**Status:** ⚠️ 36 FAILURES (98.88% pass rate on executed tests)

**Root Cause of All 36 Failures:** `RuntimeError: No embedding API key configured. Set EMBEDDING_API_KEY or API_KEY.`

These tests import modules that trigger embedding client initialization. Tests needing a running Qdrant/embedding endpoint:
- `test_agent_domain_service_browse_release.py` (1 test)
- `test_agent_domain_service_browser_timeout.py` (4 tests)
- `test_agent_domain_service_chat_teardown.py` (9 tests)
- `test_agent_domain_service_reactivation_context.py` (2 tests)
- `test_agent_domain_service_session_sandbox_teardown.py` (8 tests)
- `test_agent_domain_service_skill_activation_policy.py` (1 test)
- `test_agent_domain_service_stop_session.py` (6 tests)
- `test_reconnect_liveness.py` (6 tests)

**XFail (expected failures):**
- `test_base_wall_clock.py::test_wall_clock_warning_skips_current_tool_calls`
- `test_base_wall_clock.py::test_wall_clock_fallback_message_is_structured_json`

---

## Phase 7: Backend Core Tests

**Command:** `pytest tests/core/ -v --tb=short`

| Metric | Value |
|---|---|
| Passed | **188** |
| Failed | **3** |
| Skipped | 0 |
| Duration | 19.81s |
| Coverage | 12.96% |

**Status:** ⚠️ 3 FAILURES (98.43% pass rate)

**Root Cause:** Tests in `test_config_channels.py` assert that Telegram/Slack bot tokens default to empty strings, but the local `.env` file provides actual values. These are test-environment isolation issues:

| Test | Expected | Got |
|---|---|---|
| `TestTelegramDefaults::test_bot_token_empty` | `''` | `'8284742282:AAH...'` |
| `TestSlackDefaults::test_bot_token_empty` | `''` | `'xoxb-10753...'` |
| `TestSlackDefaults::test_app_token_empty` | `''` | `'xapp-1-A0AM...'` |

---

## Phase 8: Remaining Backend Tests (root test_*.py)

**Command:** `pytest tests/test_*.py -v --tb=short`

| Metric | Value |
|---|---|
| Passed | **858** |
| Failed | **2** |
| Skipped | 37 |
| Duration | 68.61s |
| Coverage | 44.30% |

**Status:** ⚠️ 2 FAILURES (99.77% pass rate)

**Failures** (`test_wide_research_fix.py`):
- Same root cause as domain tests: `RuntimeError: No embedding API key configured`

**Skips (37):**
- 11 skipped: Backend API registration not supported by auth provider
- 13 skipped: Sandbox container not reachable from test runner (hostname resolution)
- 13 skipped: Various auth provider constraints

---

## Phase 9: Frontend Lint & Type Check

| Check | Status | Details |
|---|---|---|
| ESLint (`lint:check`) | ✅ PASSED | No errors or warnings |
| TypeScript (`type-check`) | ✅ PASSED | No type errors |

---

## Response Time Benchmarks

| Endpoint | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Avg |
|---|---|---|---|---|---|---|
| Backend `/health` | 1.20ms | 0.76ms | 0.72ms | 0.71ms | 0.55ms | **0.79ms** |
| Frontend `/` | 2.03ms | 1.52ms | 1.34ms | 1.19ms | 1.31ms | **1.48ms** |
| Sandbox `/` | 0.80ms | 0.69ms | 0.52ms | — | — | **0.67ms** |
| Backend `/api/v1/sessions` (POST) | 2.86ms | — | — | — | — | **2.86ms** |

All response times are well within acceptable thresholds (< 5ms local).

---

## Overall Summary

| Phase | Run | Passed | Failed | Skipped | XFail | Duration | Status |
|---|---|---|---|---|---|---|---|
| 1. Health & Connectivity | — | — | — | — | — | <1s | ✅ |
| 2. Unit Tests | 182 | 182 | 0 | 0 | — | 30.3s | ✅ |
| 3. Integration Tests | 220 | 160 | 0 | 60 | — | 123.5s | ✅ |
| 4. E2E Tests | 9 | 9 | 0 | 0 | — | 4.7s | ✅ |
| 5. Load/Benchmark Tests | 0 | 0 | 0 | 0 | — | 4.5s | ⚠️ Empty |
| 6. Domain Tests | 3242 | 3185 | 36 | 19 | 2 | 70.0s | ⚠️ |
| 7. Core Tests | 191 | 188 | 3 | 0 | — | 19.8s | ⚠️ |
| 8. Root test_*.py | 897 | 858 | 2 | 37 | — | 68.6s | ⚠️ |
| 9. Frontend Lint/Type | — | — | 0 | — | — | <30s | ✅ |
| **TOTAL** | **4741** | **4582** | **41** | **116** | **2** | **~352s** | |

### Overall Health Score

- **Tests passed:** 4,582 out of 4,625 executed (non-skipped) = **99.07% pass rate**
- **Tests with issues:** 41 failures (all from 2 known root causes)
- **Coverage:** ~44% overall (target: 53%)

### Root Cause Analysis

| Issue | Count | Severity | Fix |
|---|---|---|---|
| Missing `EMBEDDING_API_KEY` env var | 38 | Medium | Set `EMBEDDING_API_KEY` or `API_KEY` in test env |
| `.env` leaking into config tests | 3 | Low | Mock/unset env vars in test setup for channel config tests |
| Redis hostname resolution | 12 skips | Low | Use `localhost:6379` mapping or Docker network config |
| Missing `SANDBOX_TEST_SECRET` | 5 skips | Low | Set `SANDBOX_API_SECRET` for seccomp tests |
| Empty load test suite | 0 | Info | Add load tests or document requirements |

### Recommendations

1. **Set `EMBEDDING_API_KEY`** in the test environment to unblock 38 domain/root test failures (or mock the embedding client in those test modules)
2. **Isolate `tests/core/test_config_channels.py`** from `.env` leakage — mock env vars explicitly
3. **Add `tests/load/` test implementations** — the directory exists but has no runnable tests
4. **Configure Redis hostname** for test runner access or add `localhost:6379` fallback
5. **Set `SANDBOX_API_SECRET`** to enable seccomp runtime integration tests
6. **Improve test coverage** from 44% to the 53% target — focus on domain services and infrastructure layers

---

*Report generated by OpenClaw subagent | pythinker-e2e-tests*
