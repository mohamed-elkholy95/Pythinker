# Frontend Stability, Resilience, and Sync Enhancement Plan (Vue 3 + FastAPI)

## Assumptions
1. Real-time transport remains SSE-first (not migrating to WebSockets as primary).
2. Stack remains Vue 3 + TypeScript frontend and FastAPI backend.
3. Authentication remains JWT-based and must work for both POST-stream and GET EventSource resume flows.
4. Goal is high reliability and smooth UX in development mode; breaking changes are acceptable if controlled by flags.

## Objectives
- Improve app design consistency and UX clarity during streaming states.
- Make frontend-backend sync robust under disconnects, retries, and partial failures.
- Standardize retry and error handling to reduce stuck sessions and duplicate events.
- Keep chat/task streams responsive, observable, and recoverable.

## Non-Goals
- Full protocol migration away from SSE.
- Large visual redesign unrelated to streaming UX and reliability.
- Rewriting all pages before stabilizing the core session/chat flows.

## Current Baseline (Status)
- `Completed`: SSE transport and retry logic exists in `frontend/src/api/client.ts`.
- `Completed`: Connection stale/degraded detection exists in `frontend/src/composables/useSSEConnection.ts`.
- `Completed`: Backend chat stream guards/heartbeats exist in `backend/app/interfaces/api/session_routes.py`.
- `Completed`: Native EventSource resume path exists (`GET /sessions/{session_id}/chat/eventsource`).
- `In Progress`: Unifying behavior across POST streaming and EventSource resume.
- `Not Started`: Formal error taxonomy harmonization and end-to-end chaos test suite.

## Workstream 1: UX and Design System Hardening
Status: `Not Started`

### Scope
- Define connection/streaming state UI standards for `connecting`, `streaming`, `reconnecting`, `degraded`, `timed_out`, `error`, `completed`.
- Improve visual hierarchy for streaming status and recovery actions.
- Reduce cognitive load in error states with precise, action-oriented messaging.

### Tasks
1. Create shared status token map in `frontend/src/constants/` for state labels, colors, and severity.
2. Standardize state banners/components used in `frontend/src/pages/ChatPage.vue` and related session views.
3. Add reusable “RecoveryActionRow” component for Retry, Resume, Stop, Refresh actions.
4. Add accessibility checks for status transitions and live-region updates.

### Acceptance Criteria
1. All stream states render with consistent design tokens and messages.
2. No ambiguous error text; every non-terminal state has an action.
3. Lighthouse accessibility score does not regress for chat page.

## Workstream 2: Frontend Sync Engine and State Consistency
Status: `Not Started`

### Scope
- Centralize stream lifecycle state transitions.
- Ensure idempotent event processing and deterministic resume behavior.

### Tasks
1. Extract stream session orchestration into a dedicated composable (for example `useSessionStreamController`).
2. Keep single source of truth for:
   - `lastEventId`
   - `receivedDoneEvent`
   - `connectionState`
   - `retryContext`
3. Enforce strict deduplication by `event_id` before UI mutation.
4. Persist and validate resume cursor in session storage with TTL guard.

### Acceptance Criteria
1. Refresh/reconnect does not duplicate tool/message/report blocks.
2. Cursor resume is monotonic and never regresses to earlier event ids.
3. No contradictory UI states (for example “completed” + “reconnecting”).

## Workstream 3: Transport Reliability (POST + EventSource GET)
Status: `In Progress`

### Scope
- Keep POST `fetch-event-source` for sending fresh messages.
- Use native EventSource GET for resume/reconnect where appropriate.

### Tasks
1. Unify close/retry semantics between `createSSEConnection` and `createEventSourceConnection` in `frontend/src/api/client.ts`.
2. Add explicit transport selection rules in `frontend/src/api/agent.ts`:
   - New user message -> POST stream
   - Resume without payload -> GET EventSource
3. Keep heartbeat and stream-gap behavior consistent across both transports.
4. Add kill-switch feature flag for EventSource resume path.

### Acceptance Criteria
1. Both transports report equivalent callback semantics to `ChatPage`.
2. Retry/backoff behavior is deterministic and observable.
3. Turning off EventSource flag safely falls back to POST stream resume.

## Workstream 4: Backend Stream Contract and Idempotency
Status: `Not Started`

### Scope
- Ensure stream contract is stable and explicit for clients.
- Prevent duplicate processing on reconnection edges.

### Tasks
1. Extract shared chat-stream generator logic to avoid route drift between POST and GET paths.
2. Add optional `request_id` idempotency key for message submissions.
3. Standardize SSE payload envelope fields (`event_id`, `timestamp`, `error_code`, `recoverable`, `checkpoint_event_id`).
4. Ensure disconnect cancellation logic is deterministic and race-safe.

### Acceptance Criteria
1. POST and GET stream paths emit the same event semantics.
2. Duplicate user-message processing is prevented when retries occur.
3. Stream gap errors always provide checkpoint metadata for resume.

## Workstream 5: Error Taxonomy and Recovery Logic
Status: `Not Started`

### Scope
- Make errors machine-actionable and user-actionable.

### Tasks
1. Define frontend/backend shared error categories:
   - `transport`
   - `timeout`
   - `auth`
   - `validation`
   - `domain`
   - `upstream`
2. Map each category to retry policy:
   - auto-retry
   - manual retry
   - terminal stop
3. Add a central error-to-UI mapper in frontend utilities.
4. Add structured logging fields for every error branch.

### Acceptance Criteria
1. Every emitted error has stable `error_code` and `error_category`.
2. Retry decisions are predictable and test-covered.
3. No silent terminal failures.

## Workstream 6: Testing Strategy (Unit + Integration + Chaos)
Status: `Not Started`

### Scope
- Validate reliability under real failure patterns.

### Tasks
1. Add unit tests for:
   - event parsing
   - dedup logic
   - retry delay computation
   - cursor persistence
2. Add integration tests for:
   - disconnect during stream
   - reconnection resume
   - heartbeat-only degraded mode
   - stream gap checkpoint recovery
3. Add E2E scenarios:
   - offline/online flaps
   - throttled network
   - backend restart during active stream

### Acceptance Criteria
1. Critical stream lifecycle tests pass in CI.
2. At least one chaos scenario exists per major failure type.
3. No regressions in existing chat lifecycle tests.

## Workstream 7: Observability and SLOs
Status: `Not Started`

### Scope
- Make stream reliability measurable and enforceable.

### Tasks
1. Add frontend diagnostics counters:
   - reconnect attempts
   - gap-detected count
   - heartbeat-only duration
2. Add backend metrics:
   - stream open/close reasons
   - send timeout count
   - recovery success rate
3. Establish SLO targets:
   - reconnect recovery success rate
   - time-to-first-event
   - stream completion rate

### Acceptance Criteria
1. Dashboards expose frontend and backend stream health together.
2. Alert rules exist for sustained degradation.
3. Root-cause data is available from logs/metrics without ad-hoc debugging.

## Rollout Plan
Status: `Not Started`

1. Phase A (Flagged internal):
   - Enable EventSource resume for dev users only.
   - Collect metrics and compare against current POST-only behavior.
2. Phase B (Wider internal):
   - Enable for all sessions with automatic fallback.
3. Phase C (Default on):
   - Keep fallback path for one release cycle, then simplify.

## Execution Sequence (Recommended)
1. Workstream 2 (state consistency) and Workstream 3 (transport parity)
2. Workstream 4 (backend contract/idempotency)
3. Workstream 5 (error taxonomy)
4. Workstream 6 (tests)
5. Workstream 1 (design polish) and Workstream 7 (dashboards/SLO)

## Definition of Done
1. No duplicate events in reconnect/resume flows across tested scenarios.
2. No stuck “connecting/reconnecting” states without user action path.
3. Stream interruptions recover automatically within retry budget or fail with clear terminal UX.
4. Logs/metrics can explain every stream closure and retry decision.
5. Lint/type-check/backend checks pass for all touched files.
