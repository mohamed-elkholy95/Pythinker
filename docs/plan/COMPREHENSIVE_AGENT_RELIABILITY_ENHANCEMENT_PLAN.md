# Comprehensive Agent Reliability Enhancement Plan

**Created:** 2026-02-23  
**Scope:** Session continuity, SSE reliability, long-running execution resiliency, and completion integrity  
**Status:** In Progress (planning started)

---

## 1. Context and Trigger

This plan is initiated from live production-like monitoring of session `c478f75a492d4114` on **2026-02-23**.

Observed sequence:
- Session progressed normally through planning and execution.
- Agent hit efficiency nudge (`STOP SEARCHING — START WRITING`) and then entered a long no-visible-progress period.
- Initial SSE stream closed with `completed_without_explicit_reason` while task execution was still active.
- Resume stream recovered execution and eventually completed all steps.
- Final summarization emitted a very high volume of `stream` events before final `done`.

Net result: **eventual completion succeeded**, but transport/continuity behavior is fragile and user-perceived reliability remains inconsistent.

---

## 2. Objectives

1. Ensure stream closure semantics are always aligned with task lifecycle state.
2. Make resume/replay deterministic and cursor-safe across reconnects and stale cursors.
3. Prevent heartbeat-only “apparent stalls” during long LLM/tool operations.
4. Reduce stream event flood while preserving perceived real-time UX.
5. Strengthen “search-to-write” transitions so nudges produce forward progress.
6. Improve completion integrity (artifact linkage + source coverage checks).

---

## 3. Reliability Targets (SLO-Style)

1. `resume_success_rate >= 99.5%` for interrupted sessions.
2. `mean_time_to_first_real_event_after_reconnect <= 5s` (excluding heartbeat).
3. No stream closes with `completed_without_explicit_reason` while session is still executing.
4. `max_silent_window_without_non_heartbeat_event <= 25s` for active runs.
5. Stream event rate cap during summarization: `<= 20 events/sec` sustained.
6. Completed report emits `report + done` with stable attachment references in one closure path.

---

## 4. Workstreams

### WS1. Resume Cursor and Replay Contract
**Goal:** Deterministic replay/skip semantics with explicit stale-cursor handling.

Target files:
- `backend/app/application/services/agent_service.py`
- `backend/app/interfaces/api/session_routes.py`
- `backend/tests/application/services/test_agent_service_latency_guards.py`
- `backend/tests/interfaces/api/test_session_routes.py`

Key actions:
- Formalize resume cursor states: `found`, `stale`, `format_mismatch`, `absent`.
- Emit explicit structured gap event when cursor is stale/missing in active stream mode.
- Ensure replay start-point behavior is consistent between completed and active sessions.
- Add metrics for stale-cursor frequency and replay success.

Acceptance:
- Reconnect with stale cursor always yields explicit gap signal and continues safely.
- No silent skip-mode disable without client-visible resume diagnostics.

---

### WS2. Stream Lifecycle Ownership
**Goal:** One authoritative source for stream close reason and cancellation policy.

Target files:
- `backend/app/interfaces/api/session_routes.py`
- `backend/app/domain/services/stream_guard.py`
- `backend/app/application/services/agent_service.py`

Key actions:
- Replace fallback close reason with explicit state machine transitions.
- Prevent “completed_without_explicit_reason” for active workloads.
- Align request cancellation timing with reconnect grace and task state.
- Add invariant checks: if stream closes as completed, task/session state must be terminal.

Acceptance:
- Every stream close has a deterministic reason from a bounded enum.
- No premature terminal close while task remains executing/updating/summarizing.

---

### WS3. Long-Op Progress Visibility
**Goal:** Eliminate user-perceived dead periods during long LLM calls.

Target files:
- `backend/app/application/services/agent_service.py`
- `backend/app/domain/services/agents/execution.py`
- `backend/app/interfaces/api/health_routes.py`

Key actions:
- Emit periodic progress beacons during long LLM/tool waits (non-heartbeat).
- Distinguish transport heartbeat from execution heartbeat in event payload.
- Add “active but waiting” status events with elapsed wait metadata.

Acceptance:
- During long calls, client receives non-heartbeat progress updates at bounded intervals.
- Health endpoint reflects waiting-state distributions.

---

### WS4. Stream Event Volume Control
**Goal:** Reduce token-by-token event flood while preserving real-time feel.

Target files:
- `backend/app/domain/services/agents/execution.py`
- `backend/app/infrastructure/external/llm/openai_llm.py`
- `frontend/src/composables/useSessionStreamController.ts`

Key actions:
- Add server-side chunk coalescing for `StreamEvent` (time/size threshold).
- Preserve semantic chunk boundaries on finalization and step transitions.
- Keep frontend batching but reduce upstream event count first.

Acceptance:
- Summarization stream event count reduced materially (>50% for long outputs) with no UX regressions.
- No missed final chunk or malformed markdown assembly.

---

### WS5. Efficiency Nudge to Action Enforcement
**Goal:** Convert nudge from advisory to reliable behavior change under repeated read loops.

Target files:
- `backend/app/domain/services/agents/tool_efficiency_monitor.py`
- `backend/app/domain/services/agents/base.py`
- `backend/tests/domain/services/agents/test_tool_efficiency_monitor.py`
- `backend/tests/domain/services/agents/test_base_efficiency_controls.py`

Key actions:
- Introduce step-level “must write before next read” gate after repeated nudges.
- Surface deterministic reason when read tools are blocked.
- Add one-shot auto-synthesis fallback when hard-stop threshold is reached repeatedly.

Acceptance:
- Repeated read-only loops are broken without manual intervention.
- Agent transitions to write/summarize path within bounded turns after hard-stop.

---

### WS6. Completion Integrity and Artifact Coverage
**Goal:** Ensure completed responses consistently include artifact references and source linkage.

Target files:
- `backend/app/domain/services/agents/execution.py`
- `backend/app/interfaces/schemas/event.py`
- `backend/tests/domain/services/agents/` (new/extended tests)

Key actions:
- Enforce report coverage checks before `done` emission (artifact refs + source citations policy).
- If coverage missing, trigger targeted completion patch pass instead of silent warning only.
- Stabilize attachment sync ordering and event payload guarantees.

Acceptance:
- Completion path emits validated report payload and stable artifact references.
- Coverage warnings become actionable correction flow, not just logs.

---

### WS7. Frontend Reconnect/Status Reconciliation Hardening
**Goal:** Keep UI state aligned with backend transitions under reconnect churn.

Target files:
- `frontend/src/api/client.ts`
- `frontend/src/pages/ChatPage.vue`
- `frontend/src/composables/useSessionStreamController.ts`
- `frontend/src/composables/useSSEConnection.ts`

Key actions:
- Tighten `no_events_after_message` handling versus active backend status checks.
- Improve stale/degraded logic to avoid false “stuck” with healthy execution.
- Preserve exactly-once event application across reconnect bursts.

Acceptance:
- UI does not show terminal failure while backend is still actively progressing.
- No duplicate visible tool/step/report entries after reconnect.

---

## 5. Phased Execution Plan

| Phase | Status | Outcome |
|---|---|---|
| Phase 0: Baseline + Incident Fixture Capture | In Progress | Metrics baseline, reproducible reconnect/stale-cursor fixture |
| Phase 1: Resume/Close Semantics | Not Started | Deterministic cursor and close-reason behavior |
| Phase 2: Progress Visibility + Event Rate Control | Not Started | No heartbeat-only stalls, reduced event flood |
| Phase 3: Efficiency Enforcement + Completion Integrity | Not Started | Reliable write transition and complete report delivery |
| Phase 4: Frontend Reconciliation + Rollout | Not Started | Stable user experience under reconnect/load |

---

## 6. Start-Now Tasks (Phase 0)

1. Add instrumentation counters/histograms for:
   - stale cursor fallback occurrences
   - stream close reasons
   - time from reconnect to first non-heartbeat event
   - stream event rate by phase
2. Build deterministic integration fixture simulating:
   - mid-run disconnect
   - stale resume cursor
   - long summarization stream
3. Add regression test to assert:
   - no premature terminal close while task state is non-terminal
   - explicit gap signal on stale resume cursor
4. Produce baseline dashboard snapshot from `/api/health/streaming` plus backend logs.

---

## 7. Verification Matrix

Backend checks:
```bash
cd backend
ruff check .
ruff format --check .
pytest tests/application/services/test_agent_service_latency_guards.py
pytest tests/interfaces/api/test_session_routes.py
pytest tests/domain/services/agents/test_tool_efficiency_monitor.py
pytest tests/domain/services/agents/test_base_efficiency_controls.py
```

Frontend checks:
```bash
cd frontend
bun run lint
bun run type-check
bun run test -- useSessionStreamController
```

Runtime validation:
1. Start a long-form deep-research session.
2. Force SSE reconnect mid-execution.
3. Verify replay behavior, step continuity, and final `report + done`.
4. Confirm session status transitions and close reason consistency.

---

## 8. Risks and Mitigations

1. **Risk:** Over-throttling stream chunks hurts perceived responsiveness.  
Mitigation: tune with dual thresholds (time + bytes) and keep immediate flush for phase/step boundaries.

2. **Risk:** Resume gap signaling introduces duplicate processing paths in frontend.  
Mitigation: keep event-id dedup as source of truth; add explicit tests for gap + replay scenarios.

3. **Risk:** Stronger efficiency gates may suppress necessary reads in edge cases.  
Mitigation: permit bounded exceptions for verifier/finalization phases with explicit logs.

4. **Risk:** Added integrity gates may increase completion latency.  
Mitigation: feature-flag rollout and latency SLO monitoring before default-on.

---

## 9. Definition of Done

All of the following must be true:
1. Stream and task lifecycle states remain consistent across disconnect/reconnect paths.
2. Stale cursor behavior is explicit, test-covered, and client-visible.
3. Long operations provide progress beyond transport heartbeats.
4. Stream event volume is controlled without losing content fidelity.
5. Efficiency controls reliably drive write/progress behavior.
6. Completion emits validated report and artifact references with consistent close semantics.

