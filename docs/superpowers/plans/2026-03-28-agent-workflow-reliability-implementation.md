# Agent Workflow Reliability Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the known workflow reliability bug, consolidate lifecycle and timing policy ownership, add admission control and stream-pressure diagnostics, and surface a per-session reliability scorecard.

**Architecture:** Backend becomes authoritative for workflow timing and session reliability persistence, while the frontend stream controller becomes authoritative for reconnect policy execution and stream-pressure measurement. Session status polling remains the lightweight reconciliation path, but it gains a structured reliability payload fed by frontend summary telemetry and backend recovery counters.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, asyncio, Vue 3, Pinia, Vitest, pytest

---

## File Map

- Modify: `backend/app/domain/services/agent_domain_service.py`
- Modify: `backend/app/application/services/agent_service.py`
- Modify: `backend/app/application/services/session_lifecycle_service.py`
- Create: `backend/app/application/services/stale_session_cleanup_policy.py`
- Create: `backend/app/core/workflow_timing_contract.py`
- Modify: `backend/app/core/prometheus_metrics.py`
- Modify: `backend/app/domain/models/session.py`
- Modify: `backend/app/interfaces/schemas/session.py`
- Modify: `backend/app/interfaces/api/session_routes.py`
- Modify: `backend/app/interfaces/api/telemetry_routes.py`
- Modify: `backend/app/infrastructure/repositories/mongo_session_repository.py`
- Modify: `backend/tests/domain/services/test_agent_domain_service_chat_teardown.py`
- Modify: `backend/tests/application/services/test_agent_service_not_found.py`
- Modify: `backend/tests/application/services/test_agent_service_warmup_cancellation.py`
- Modify: `backend/tests/application/services/test_session_lifecycle_service.py`
- Create: `backend/tests/application/services/test_stale_session_cleanup_policy.py`
- Create: `backend/tests/interfaces/api/test_session_reliability_routes.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/agent.ts`
- Modify: `frontend/src/composables/useSessionStreamController.ts`
- Modify: `frontend/src/composables/__tests__/useSessionStreamController.test.ts`
- Modify: `frontend/src/stores/connectionStore.ts`
- Modify: `frontend/src/pages/ChatPage.vue`
- Create: `frontend/src/core/session/workflowTimingContract.ts`
- Create: `frontend/src/core/session/sessionReliability.ts`
- Create: `frontend/src/core/session/reconnectPolicy.ts`
- Update: `docs/reports/2026-03-28-agent-workflow-design-performance-scan.md`

## Chunk 1: Backend correctness and ownership

### Task 1: Fix execution-slot wait signaling with TDD

**Files:**
- Modify: `backend/tests/domain/services/test_agent_domain_service_chat_teardown.py`
- Modify: `backend/app/domain/services/agent_domain_service.py`

- [ ] Write a failing test that forces the execution semaphore wait path and expects a valid `ProgressEvent` with `phase=PlanningPhase.WAITING`, `message`, and `wait_stage`.
- [ ] Run: `cd backend && .venv/bin/pytest tests/domain/services/test_agent_domain_service_chat_teardown.py -q`
- [ ] Implement the minimal fix in `AgentDomainService.chat()` so the queued-slot notification uses the current `ProgressEvent` schema.
- [ ] Re-run: `cd backend && .venv/bin/pytest tests/domain/services/test_agent_domain_service_chat_teardown.py -q`

### Task 2: Extract stale-session cleanup policy

**Files:**
- Create: `backend/app/application/services/stale_session_cleanup_policy.py`
- Modify: `backend/app/application/services/agent_service.py`
- Create: `backend/tests/application/services/test_stale_session_cleanup_policy.py`

- [ ] Write failing tests for stale-session cleanup policy behavior: age cutoff, active-stream skip, per-session timeout, total timeout, and browser-close delegation.
- [ ] Run: `cd backend && .venv/bin/pytest tests/application/services/test_stale_session_cleanup_policy.py -q`
- [ ] Move `_cleanup_stale_sessions()` logic from `AgentService` into `StaleSessionCleanupPolicy`.
- [ ] Wire `AgentService.create_session()` to call the extracted policy.
- [ ] Re-run: `cd backend && .venv/bin/pytest tests/application/services/test_stale_session_cleanup_policy.py tests/application/services/test_agent_service_create_session.py -q`

### Task 3: Consolidate session lifecycle ownership

**Files:**
- Modify: `backend/app/application/services/session_lifecycle_service.py`
- Modify: `backend/app/application/services/agent_service.py`
- Modify: `backend/tests/application/services/test_session_lifecycle_service.py`
- Modify: `backend/tests/application/services/test_agent_service_not_found.py`
- Modify: `backend/tests/application/services/test_agent_service_warmup_cancellation.py`

- [ ] Write failing tests covering: idempotent stop/delete, warmup cancellation hook execution, and `AgentService` delegation to `SessionLifecycleService`.
- [ ] Run: `cd backend && .venv/bin/pytest tests/application/services/test_session_lifecycle_service.py tests/application/services/test_agent_service_not_found.py tests/application/services/test_agent_service_warmup_cancellation.py -q`
- [ ] Extend `SessionLifecycleService` to own stop/delete hooks needed by `AgentService` (warmup cancellation, login state cleanup if applicable).
- [ ] Replace direct stop/delete/pause/resume logic in `AgentService` with delegation.
- [ ] Re-run the same pytest command.

### Task 4: Add workload-class admission control

**Files:**
- Modify: `backend/app/domain/services/agent_domain_service.py`
- Modify: `backend/app/domain/models/session.py`
- Add tests in: `backend/tests/domain/services/test_agent_domain_service_chat_teardown.py` or a focused new test module if needed

- [ ] Write failing tests covering queue-class classification and fairness behavior between interactive and heavy sessions.
- [ ] Run the targeted backend pytest command for the new tests.
- [ ] Implement a minimal admission policy with explicit session workload classes and bounded fairness around execution-slot acquisition.
- [ ] Re-run the targeted backend pytest command.

## Chunk 2: Timing contract and backend scorecard plumbing

### Task 5: Create the workflow timing contract

**Files:**
- Create: `backend/app/core/workflow_timing_contract.py`
- Modify: `backend/app/application/services/agent_service.py`
- Modify: `backend/app/interfaces/api/session_routes.py`
- Create: `frontend/src/core/session/workflowTimingContract.ts`
- Modify: `frontend/src/stores/connectionStore.ts`

- [ ] Write backend tests proving the contract values are exposed through SSE protocol headers and used by `AgentService`/`session_routes`.
- [ ] Write frontend tests proving the contract values are the source of stale detection defaults.
- [ ] Implement the backend contract module and replace hardcoded timing constants where practical.
- [ ] Mirror the contract in the frontend timing module and route stale detection defaults through it.
- [ ] Re-run targeted backend and frontend tests.

### Task 6: Persist per-session reliability diagnostics

**Files:**
- Modify: `backend/app/domain/models/session.py`
- Modify: `backend/app/interfaces/schemas/session.py`
- Modify: `backend/app/interfaces/api/session_routes.py`
- Modify: `backend/app/interfaces/api/telemetry_routes.py`
- Modify: `backend/app/infrastructure/repositories/mongo_session_repository.py`
- Create: `backend/tests/interfaces/api/test_session_reliability_routes.py`
- Modify: `frontend/src/api/agent.ts`

- [ ] Write failing backend API tests for posting session reliability diagnostics and reading them back via session status.
- [ ] Run: `cd backend && .venv/bin/pytest tests/interfaces/api/test_session_reliability_routes.py -q`
- [ ] Add session reliability diagnostic models to the session domain/schema layer.
- [ ] Add an authenticated API surface to store per-session reliability diagnostics.
- [ ] Extend session status responses to include the structured reliability payload.
- [ ] Re-run the targeted backend pytest command.

### Task 7: Add Prometheus counters and histograms for scorecard signals

**Files:**
- Modify: `backend/app/core/prometheus_metrics.py`
- Modify: `backend/app/interfaces/api/telemetry_routes.py`
- Modify: `backend/app/interfaces/api/session_routes.py`
- Extend: `backend/tests/interfaces/api/test_session_reliability_routes.py`

- [ ] Write failing tests for duplicate-drop, stale-detection, auto-retry, fallback-poll, and stream-pressure metric recording.
- [ ] Run the targeted backend pytest command.
- [ ] Implement counters/histograms and record them from telemetry ingestion and existing SSE paths.
- [ ] Re-run the targeted backend pytest command.

## Chunk 3: Frontend controller ownership and reporting

### Task 8: Centralize reconnect policy ownership

**Files:**
- Create: `frontend/src/core/session/reconnectPolicy.ts`
- Modify: `frontend/src/composables/useSessionStreamController.ts`
- Modify: `frontend/src/stores/connectionStore.ts`
- Modify: `frontend/src/pages/ChatPage.vue`
- Modify: `frontend/src/composables/__tests__/useSessionStreamController.test.ts`

- [ ] Write failing frontend tests that assert reconnect delays, fallback poll limits, and stale-triggered reconnect entry all come from one policy source.
- [ ] Run: `cd frontend && pnpm test:run frontend/src/composables/__tests__/useSessionStreamController.test.ts`
- [ ] Move reconnect-policy defaults out of `ChatPage.vue` into a dedicated module consumed by the controller/store.
- [ ] Remove page-level policy constants that duplicate controller behavior.
- [ ] Re-run the targeted frontend test command.

### Task 9: Add stream-pressure instrumentation to the controller

**Files:**
- Modify: `frontend/src/composables/useSessionStreamController.ts`
- Modify: `frontend/src/composables/__tests__/useSessionStreamController.test.ts`
- Create: `frontend/src/core/session/sessionReliability.ts`

- [ ] Write failing tests for queue-depth tracking, flush batch size tracking, chunk duration tracking, duplicate-drop counting, and summary reset behavior.
- [ ] Run the targeted frontend test command.
- [ ] Add a session-scoped reliability accumulator to `useSessionStreamController`.
- [ ] Expose a structured summary API that `ChatPage.vue` can read.
- [ ] Re-run the targeted frontend test command.

### Task 10: Publish and submit the reliability scorecard from the frontend

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`
- Modify: `frontend/src/api/agent.ts`
- Extend: `frontend/src/composables/__tests__/useSessionStreamController.test.ts`

- [ ] Write failing tests for posting reliability diagnostics on terminal/reconcile paths and for consuming scorecard data from session status polling.
- [ ] Run targeted frontend tests.
- [ ] Submit the controller summary to the backend diagnostics API from `ChatPage.vue`.
- [ ] Update reconciliation/status polling to read the returned scorecard payload.
- [ ] Re-run targeted frontend tests.

## Chunk 4: Verification and docs

### Task 11: Refresh docs

**Files:**
- Modify: `docs/reports/2026-03-28-agent-workflow-design-performance-scan.md`

- [ ] Update the report if implementation details differ from the rewrite assumptions.

### Task 12: Full verification

- [ ] Run backend targeted verification:
  - `cd backend && .venv/bin/pytest tests/domain/services/test_agent_domain_service_chat_teardown.py tests/application/services/test_session_lifecycle_service.py tests/application/services/test_agent_service_not_found.py tests/application/services/test_agent_service_warmup_cancellation.py tests/application/services/test_stale_session_cleanup_policy.py tests/interfaces/api/test_session_reliability_routes.py -q`
- [ ] Run backend lint for touched Python files:
  - `cd backend && make lint`
- [ ] Run frontend targeted verification:
  - `cd frontend && pnpm test:run src/composables/__tests__/useSessionStreamController.test.ts`
- [ ] Run frontend static checks:
  - `cd frontend && pnpm lint:check`
  - `cd frontend && pnpm type-check`
