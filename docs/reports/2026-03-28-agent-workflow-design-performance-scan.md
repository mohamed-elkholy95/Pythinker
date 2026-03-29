# Agent Workflow Design & Performance Scan (2026-03-28)

**Status:** Implemented and re-verified against the current checkout  
**Method:** The original scan was reconciled against live code, then the reliability plan was executed and this report was refreshed to match the implemented state.  
**Scope:** Agent workflow design, session lifecycle orchestration, SSE transport resilience, reconnect behavior, and frontend stream processing.

## Scope

This report is a static codebase scan focused on:

- backend orchestration and session lifecycle
- SSE contract and client transport handling
- frontend stream batching, reconnect behavior, and stale detection
- architecture and policy ownership across the current repository

## Current-State Snapshot

### Completed

- **Backend session orchestration now has explicit latency guardrails and extracted stale-session policy ownership.**
  - `AgentService` sources session-create wait, idle timeout, hard timeout, and wait-beacon values from `backend/app/core/workflow_timing_contract.py`.
  - stale-session cleanup now lives in a dedicated `StaleSessionCleanupPolicy` with bounded per-session and total cleanup caps.

- **Lifecycle ownership is consolidated through `SessionLifecycleService`.**
  - stop, delete, pause, and resume paths delegate through the lifecycle service.
  - `AgentService` now hooks in warmup cancellation and login-state cleanup instead of owning parallel lifecycle logic.

- **Execution concurrency now includes workload-class admission control.**
  - `AgentDomainService` keeps separate sandbox-init and execution semaphores.
  - execution-slot acquisition classifies sessions as interactive vs heavy and enforces bounded fairness after interactive bursts.
  - the execution-slot wait path now emits a valid queue-pressure `ProgressEvent` instead of failing on schema mismatch.

- **Backend and frontend now share explicit workflow timing and reconnect policy modules.**
  - backend timing values live in `backend/app/core/workflow_timing_contract.py`.
  - frontend stale-detection thresholds mirror that contract in `frontend/src/core/session/workflowTimingContract.ts`.
  - reconnect defaults now live in `frontend/src/core/session/reconnectPolicy.ts` and are consumed by the stream controller and page-level coordinator setup.

- **Frontend stream processing now exposes structured stream-pressure diagnostics.**
  - `useSessionStreamController` still frame-batches and chunk-yields event bursts.
  - it now records max queue depth, average flush batch size, max chunk processing duration, duplicate-drop counts, stale detections, auto-retries, and fallback poll attempts.

- **Per-session reliability scorecard plumbing is implemented end-to-end.**
  - backend persists `SessionReliabilityDiagnostics` on the session model and exposes it via session status responses.
  - frontend submits controller summaries to `/telemetry/sessions/{session_id}/reliability`.
  - Prometheus now records the submitted recovery counters and stream-pressure signals.

### Remaining Risks

- **Transport behavior is more centralized, but not fully isolated from page flow.**
  - reconnect defaults are centralized, but `ChatPage.vue` still decides when to trigger stale reconnect attempts and when to publish the final scorecard.
  - that split is smaller and clearer than before, but page-level orchestration still exists.

- **The timing contract is mirrored rather than generated from one source artifact.**
  - backend and frontend constants now match by explicit module design.
  - they are still maintained in two languages, so future drift remains possible without generation or automated parity checks.

## Design Risks Found

1. **Frontend reconnect execution still depends on page orchestration**
   - `useSessionStreamController` owns policy and instrumentation, but `ChatPage.vue` still triggers stale reconnect actions and terminal scorecard submission.
   - further extraction would reduce coupling between UI flow and transport recovery.

2. **Cross-language timing drift is reduced, not eliminated**
   - matching backend/frontend timing modules are now in place.
   - without automated parity enforcement, these mirrored constants can still drift over time.

3. **Operator visibility is better, but product surfacing is still thin**
   - Prometheus counters and persisted session diagnostics now exist.
   - UI/operator presentation of that scorecard remains limited to status polling and backend metrics rather than a dedicated diagnostics surface.

## Priority Enhancement Plan

### P1

1. **Reduce remaining page-level reconnect orchestration.**
   - Move stale-triggered reconnect decisions and reliability-submission triggers behind a thinner composable or controller boundary.

2. **Add parity checks for the mirrored timing contract.**
   - Introduce automated tests or generated artifacts so backend/frontend timing values cannot silently diverge.

### P2

3. **Promote the reliability scorecard into a first-class operator or support surface.**
   - Persisted diagnostics and Prometheus signals now exist.
   - the next step is trend views, correlation tooling, and support-facing inspection rather than more raw counters.

## Suggested Success Metrics

- **Latency:** p95 time to first non-heartbeat event after user send
- **Reconnect recovery:** p95 reconnect-to-first-non-heartbeat latency
- **Stability:** percentage of sessions reaching a terminal event without manual refresh
- **Queue resilience:** percentage of execution-slot waits that surface a valid progress event instead of failing
- **UI smoothness proxy:** median and p95 stream-controller queue depth and flush duration

## Evidence Sources (Scanned)

- `backend/app/application/services/agent_service.py`
- `backend/app/application/services/session_lifecycle_service.py`
- `backend/app/domain/services/agent_domain_service.py`
- `backend/app/domain/models/event.py`
- `backend/app/interfaces/api/session_routes.py`
- `backend/app/interfaces/schemas/event.py`
- `backend/app/core/prometheus_metrics.py`
- `frontend/src/api/client.ts`
- `frontend/src/composables/useSessionStreamController.ts`
- `frontend/src/stores/connectionStore.ts`
- `frontend/src/pages/ChatPage.vue`
