# Live View Takeover and User Control Plan

**Created:** 2026-02-24  
**Scope:** Live browser view, user takeover control, captcha/login handoff, and login-state persistence  
**Status:** Completed (planning and validation), Not Started (implementation)

---

## 1. Executive Summary

This plan defines a robust, end-to-end design for:

1. Deterministic user takeover of the Pythinker browser session.
2. Correct agent pause/resume arbitration when user control is active.
3. Reliable handoff for captcha/login/2FA steps.
4. Practical "persist login state" behavior that actually restores auth context.
5. Security hardening for screencast/input websocket flows.

The implementation is grounded in current code behavior and validated against:

1. Chrome DevTools Protocol (Page/Input domains).
2. Playwright authentication/context state patterns.
3. OWASP WebSocket security guidance.

---

## 2. Validated Current State (Codebase Facts)

### 2.1 What already exists

1. Live browser stream (CDP screencast) exists and is proxied via backend.
2. Interactive input websocket exists for user control.
3. Session pause/resume APIs exist and task runner already respects paused tasks.
4. `message_ask_user` supports `suggest_user_takeover` in backend tool schema.

### 2.2 Gaps requiring implementation

1. Takeover entry from UI currently does not pause agent first.
2. Takeover exits call `resume` as optional context injection, even when no prior pause happened.
3. `persist_login_state` is stored on session metadata but not used for auth snapshot/restore.
4. Takeover navigation controls (`back`/`forward`) are placeholders.
5. Frontend does not consume `suggest_user_takeover` for explicit CTA/handoff UX.
6. Input target selection can diverge from screencast target in multi-page/tab conditions.
7. WebSocket proxy logging still exposes full target URL (including secret query param).

---

## 3. Design Principles

1. **User control must be explicit and conflict-free**: user takeover is a controlled mode, not just an overlay.
2. **State machine over ad hoc events**: takeover lifecycle transitions must be first-class backend state.
3. **Backward-compatible contracts**: existing clients keep working while new fields remain optional.
4. **Security-by-default**: origin checks, secret redaction, and no sensitive query logging.
5. **Durability and maintainability**: clear ownership boundaries across frontend/backend/sandbox.

---

## 4. Target Architecture

### 4.1 Takeover Lifecycle State Machine

Add a backend-owned takeover state with transitions:

1. `idle` -> `takeover_requested`
2. `takeover_requested` -> `takeover_active` (after pause succeeds)
3. `takeover_active` -> `resuming` (exit requested)
4. `resuming` -> `idle` (resume succeeded)

Failure transitions:

1. Pause failure: return to `idle` with actionable error.
2. Resume failure: remain `takeover_active`, surface retry action.

### 4.2 API Contract Additions

Add explicit takeover endpoints (idempotent):

1. `POST /sessions/{session_id}/takeover/start`
2. `POST /sessions/{session_id}/takeover/end`
3. `GET /sessions/{session_id}/takeover/status` (optional but recommended)

Payload examples:

1. `start`: `{ "reason": "manual|captcha|login|2fa|payment|verification" }`
2. `end`: `{ "context": "...", "persist_login_state": true, "resume_agent": true }`

### 4.3 Event Contract Enhancements

Extend SSE payloads in a backward-compatible way:

1. `wait` event data:
   - `wait_reason`: `user_input|captcha|login|2fa|payment|verification|other`
   - `suggest_user_takeover`: `none|browser`
2. `tool` event data:
   - Keep existing `args`; frontend must read `args.suggest_user_takeover` safely.

### 4.4 Frontend Control Arbitration

Create a single takeover orchestration flow:

1. User clicks takeover -> call `takeover/start` -> show loading gate.
2. Enter fullscreen takeover only after backend confirms paused state.
3. On exit, call `takeover/end`; if `resume_agent=true`, backend resumes.
4. If `wait_reason` indicates captcha/login and `suggest_user_takeover=browser`, show one-click CTA.

### 4.5 Login State Persistence

Implement actual auth state snapshot/restore:

1. On takeover end with `persist_login_state=true`, snapshot Playwright `storageState`.
2. Store state per `(user_id, session_id)` or `(user_id, profile_key)` under backend-managed storage.
3. On future browser context initialization, restore storage state before navigation.
4. Add retention policy and secure file permissions.

### 4.6 Navigation Controls in Takeover

Implement real browser controls via backend/sandbox commands:

1. Back: `Page.getNavigationHistory` + `Page.navigateToHistoryEntry`.
2. Forward: same history navigation logic.
3. Reload: `Page.reload`.
4. Stop loading: `Page.stopLoading`.

### 4.7 Screencast/Input Target Affinity

Guarantee both streams address the same active page target:

1. Introduce shared target selection service in sandbox.
2. Bind screencast and input to tracked active page target id.
3. Reconcile target on tab creation/navigation and during reconnects.

### 4.8 WebSocket Security Hardening

1. Enforce websocket origin allowlist at backend proxy entrypoints.
2. Redact sensitive query keys from all logs (`secret`, `signature`, `uid` as needed).
3. Prefer header auth to sandbox where possible; keep query fallback behind controlled path.

---

## 5. Detailed Implementation Phases

## Phase 0: Contract and Control Foundations (P0)
**Status:** Not Started

### Backend

1. Add takeover routes and schemas in:
   - `backend/app/interfaces/api/session_routes.py`
   - `backend/app/interfaces/schemas/session.py`
2. Add lifecycle methods and state updates in:
   - `backend/app/domain/services/agents/agent_session_lifecycle.py`
   - `backend/app/application/services/session_lifecycle_service.py`
   - `backend/app/application/services/agent_service.py`
3. Add optional wait/tool metadata mapping in:
   - `backend/app/interfaces/schemas/event.py`
   - `backend/app/domain/models/event.py` (if needed for new fields)

### Frontend

1. Add takeover API calls in:
   - `frontend/src/api/agent.ts`
2. Replace raw window takeover entry with API-backed orchestration:
   - `frontend/src/components/ToolPanelContent.vue`
   - `frontend/src/components/toolViews/BrowserToolView.vue`
   - `frontend/src/components/TakeOverView.vue`
3. Consume enhanced wait/tool metadata and show CTA:
   - `frontend/src/pages/ChatPage.vue`
   - `frontend/src/types/event.ts`

### Acceptance Criteria

1. User cannot enter interactive takeover until pause succeeds.
2. Agent does not continue execution while takeover is active.
3. Exiting takeover reliably resumes agent when requested.
4. Existing chat/session flows remain backward compatible.

---

## Phase 1: Captcha/Login Handoff + Persisted Auth (P1)
**Status:** Not Started

### Backend

1. Add challenge reason classifier for tool outputs:
   - `backend/app/domain/services/agents/execution.py`
   - `backend/app/domain/services/tools/playwright_tool.py` (metadata enrichment)
2. Implement storageState snapshot/restore:
   - `backend/app/infrastructure/external/browser/playwright_browser.py`
   - relevant storage/service modules for persisted state files/records
3. Wire `persist_login_state` from takeover end into restore path.

### Frontend

1. Show explicit "Take over to finish login/captcha" prompt on wait reasons.
2. Collect structured exit summary for handoff-sensitive reasons.

### Acceptance Criteria

1. Captcha/login/2FA waits present direct takeover CTA.
2. Persisted login option restores authenticated state on subsequent browser sessions.
3. Agent resumes with user context and fresh state awareness.

---

## Phase 2: Browser Controls + Target Affinity + Security Hardening (P1)
**Status:** Not Started

### Sandbox/Backend

1. Implement navigation commands for takeover controls:
   - `sandbox/app/api/v1/...` (new control route if needed)
   - `sandbox/app/services/cdp_screencast.py`
   - `sandbox/app/services/cdp_input.py`
2. Introduce shared active-target registry for screencast/input alignment.
3. Add origin checks and sensitive log redaction:
   - `backend/app/interfaces/api/session_routes.py`
   - supporting middleware/dependency if centralized.

### Frontend

1. Wire takeover nav buttons to real control APIs in:
   - `frontend/src/components/TakeOverView.vue`

### Acceptance Criteria

1. Back/forward/reload/stop controls work reliably in takeover mode.
2. Input and screencast operate on the same page target in multi-tab scenarios.
3. Sensitive tokens are not logged.
4. Disallowed websocket origins are rejected.

---

## Phase 3: Reliability and Regression Hardening (P2)
**Status:** Not Started

1. Add integration and reconnect tests for takeover lifecycle.
2. Add regression tests for event schema compatibility.
3. Add observability counters for takeover starts/ends/failures and reason distribution.

Acceptance:

1. No known regressions in live view, chat streaming, or session state transitions.
2. Deterministic behavior under reconnect/disconnect conditions.

---

## 6. Testing and Verification Matrix

## Backend

```bash
conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
```

Focused tests to add/update:

1. `backend/tests/interfaces/api/test_session_routes.py`
   - takeover start/end authorization, idempotency, websocket origin checks.
2. `backend/tests/application/services/test_session_lifecycle_service.py`
   - pause/resume/takeover state transitions and context injection.
3. New tests around event mapping metadata and login-state persistence path.

## Frontend

```bash
cd frontend && bun run lint && bun run type-check
```

Focused tests to add/update:

1. `frontend/tests/components/LiveViewer.spec.ts`
2. New tests for `TakeOverView` orchestration and `ChatPage` wait CTA behavior.

## Sandbox

1. Extend `scripts/test_cdp_integration.sh` coverage for control commands.
2. Add target-affinity tests for input + screencast alignment.

---

## 7. Risks and Mitigations

1. **Risk:** Pause latency causes poor takeover UX.  
Mitigation: optimistic loading UI with timeout and explicit error recovery path.

2. **Risk:** Persisted auth state leaks between users/sessions.  
Mitigation: strict namespace keys by user ownership; encrypted or locked-down storage location.

3. **Risk:** Event schema drift breaks older frontend assumptions.  
Mitigation: additive-only fields and contract tests for legacy payload compatibility.

4. **Risk:** Target affinity changes introduce new CDP complexity.  
Mitigation: single target-selection component with tests; fail-safe fallback to active page rediscovery.

---

## 8. Rollout Strategy

1. Gate major behavior behind feature flags:
   - `takeover_requires_pause`
   - `takeover_wait_reason_cta`
   - `persist_login_state_enabled`
   - `ws_origin_enforcement`
2. Roll out in sequence:
   - Phase 0 flags on in development.
   - Phase 1/2 behind opt-in until integration tests stabilize.
3. Monitor:
   - takeover success rate
   - pause/resume failure rate
   - wait reason distribution
   - websocket rejection metrics by reason

---

## 9. Definition of Done

This initiative is complete when all are true:

1. Takeover always pauses agent first and resumes deterministically on exit.
2. Captcha/login/2FA waits produce actionable takeover guidance in UI.
3. Persist login state reliably restores auth context when requested.
4. Takeover navigation controls function using real browser history/reload commands.
5. Screencast and input target alignment is validated in multi-page scenarios.
6. Websocket origin and logging hardening are enforced and tested.
7. Backend/frontend/sandbox verification suites pass with no critical regressions.

---

## 10. External Validation Sources

1. CDP Page domain: `startScreencast`, `screencastFrameAck`, `getNavigationHistory`, `navigateToHistoryEntry`, `reload`, `stopLoading`  
   https://chromedevtools.github.io/devtools-protocol/tot/Page/
2. CDP Input domain: mouse/keyboard/wheel dispatch semantics  
   https://chromedevtools.github.io/devtools-protocol/tot/Input/
3. Playwright BrowserContext auth/session state (`storageState`, permissions)  
   https://playwright.dev/docs/api/class-browsercontext
4. OWASP WebSocket Security guidance  
   https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html

