# Live View Takeover and User Control Plan

**Created:** 2026-02-24  
**Updated:** 2026-02-24 (Status/gap audit synced to current repository implementation)  
**Scope:** Live browser view, user takeover control, captcha/login handoff, and login-state persistence  
**Status:** In Progress (Core implementation landed; security/affinity/test hardening still pending)

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
4. `message_ask_user` supports `suggest_user_takeover` in backend tool schema (`backend/app/domain/services/tools/message.py`).
5. `pauseSession()` and `resumeSession()` API calls exist in `frontend/src/api/agent.ts`.
6. `SandboxViewer.vue` provides a `<slot name="takeover">` for rendering takeover controls.
7. Phase 0 takeover primitives are now added:
   - `TakeoverState` domain model and persistence fields.
   - backend routes: `takeover/start`, `takeover/end`, `takeover/status`.
   - frontend API methods: `startTakeover`, `endTakeover`, `getTakeoverStatus`.
8. Takeover entry points now call `startTakeover(...)` before opening the takeover UI.
9. Onboarding copy in `TakeOverView.vue` now matches pause-first behavior.
10. Takeover navigation controls are wired end-to-end:
   - sandbox service/route: `cdp_navigation.py` + `api/v1/navigation.py`
   - backend proxy routes: takeover navigation action/history
   - frontend takeover UI buttons call the navigation APIs.
11. Login-state persistence now snapshots (`export_storage_state`) and restores (`import_storage_state`) Playwright storage state with file-backed retention (7-day TTL, max 5 states/user).
12. Websocket proxy logging now redacts sensitive query params (`secret`, `signature`, `uid`) in URL/error logging paths.

### 2.2 Gaps requiring implementation

1. Input target selection can diverge from screencast target in multi-page/tab conditions.
2. Pause-first arbitration is not fully enforced for all takeover entry paths: `TakeOverView.vue` can still render from route/query fallback (`preview=1`) without first calling `takeover/start`.
3. WebSocket origin allowlist enforcement is still pending at backend proxy entrypoints.
4. Test coverage for takeover lifecycle and new routes is still partial and needs expansion.
5. Persisted login-state implementation stores/restores snapshots, but cleanup on session delete is still missing and reconnect/crash-path end-to-end validation is still pending.

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

Add a backend-owned `takeover_state` field to the `Session` domain model and `SessionDocument` with transitions:

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

> [!IMPORTANT]
> The takeover endpoints **collectively wrap** legacy pause/resume logic:
> `takeover/start` drives pause + state transition, and `takeover/end` drives resume + state transition. The existing `/pause` and `/resume` endpoints remain for backward compatibility but should not be used by the new takeover UI flow.

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

> [!NOTE]
> Both `takeOver()` call sites are now migrated to the API-backed flow. Keep this as a regression checkpoint: if future refactors add new takeover entry points, they must call backend takeover APIs rather than dispatching UI-only events.

### 4.5 Login State Persistence

Implement actual auth state snapshot/restore:

1. On takeover end with `persist_login_state=true`, snapshot Playwright `storageState`.
2. Store state per `(user_id, session_id)` or `(user_id, profile_key)` under backend-managed storage.
3. On future browser context initialization, restore storage state before navigation.
4. Retention policy: **7-day TTL, max 5 stored states per user**, cleanup on session delete.
5. Secure file permissions: restrict to backend process owner, no world-readable paths.

### 4.6 Navigation Controls in Takeover

Implement real browser controls via backend/sandbox commands:

1. Back: `Page.getNavigationHistory` + `Page.navigateToHistoryEntry`.
2. Forward: same history navigation logic.
3. Reload: `Page.reload`.
4. Stop loading: `Page.stopLoading`.

> [!NOTE]
> `cdp_navigation.py` and `sandbox/app/api/v1/navigation.py` are now implemented and wired through backend takeover navigation proxy routes.

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
**Status:** In Progress

### Progress Snapshot (2026-02-24)

Completed:
1. `TakeoverState` model and persistence fields added.
2. Takeover API routes and request/response schemas added.
3. Service-layer takeover methods added (domain/application).
4. Frontend takeover API client methods added.
5. Frontend takeover entry points switched to `startTakeover(...)`.
6. Takeover onboarding copy updated to pause-first wording.
7. Takeover lifecycle semantics fixed for pause/resume false-return paths.
8. `resume_agent=false` takeover end now honors contract.
9. Wait metadata contract (`wait_reason`, `suggest_user_takeover`) is wired backend -> frontend CTA.
10. Takeover navigation controls are API-backed (`back`/`forward`/`reload`/`stop`).
11. `persist_login_state` now snapshots/restores Playwright storage state with file-backed retention.
12. Secret/query redaction added for websocket error/logging paths.

In Progress:
1. Dedicated takeover lifecycle and route test coverage expansion.
2. Ensuring all takeover entry paths are pause-first (including route/query fallback behavior).

Not Started:
1. Input/screencast target-affinity hardening for multi-tab scenarios.
2. WebSocket origin allowlist enforcement.
3. Session-delete cleanup hook for persisted login-state files.

### Backend

1. Add `TakeoverState` enum and `takeover_state` field to domain model:
   - `backend/app/domain/models/session.py` — add `TakeoverState` enum and field
   - `backend/app/infrastructure/models/documents.py` — add `takeover_state` to `SessionDocument`
2. Add takeover routes and schemas:
   - `backend/app/interfaces/api/session_routes.py` — add `takeover/start`, `takeover/end`, `takeover/status`
   - `backend/app/interfaces/schemas/session.py` — add `TakeoverStartRequest`, `TakeoverEndRequest`, `TakeoverStatusResponse`
3. Add lifecycle methods and state updates:
   - `backend/app/domain/services/agents/agent_session_lifecycle.py` — add `start_takeover()`, `end_takeover()` methods
   - `backend/app/application/services/session_lifecycle_service.py` — add takeover service methods with ownership checks
   - `backend/app/application/services/agent_service.py` — add takeover facade methods
4. Add optional wait/tool metadata mapping:
   - `backend/app/interfaces/schemas/event.py`
   - `backend/app/domain/models/event.py` (if needed for new fields)

### Frontend

1. Add takeover API calls:
   - `frontend/src/api/agent.ts` — add `startTakeover()`, `endTakeover()`, `getTakeoverStatus()`
2. Replace raw window takeover entry with API-backed orchestration:
   - `frontend/src/components/ToolPanelContent.vue` — update `takeOver()` (line 1246)
   - `frontend/src/components/toolViews/BrowserToolView.vue` — update `takeOver()` (line 330)
   - `frontend/src/components/TakeOverView.vue` — update `handleExitWithContext()`, fix onboarding copy (line 73)
   - `frontend/src/components/SandboxViewer.vue` — verify takeover slot compatibility
3. Consume enhanced wait/tool metadata and show CTA:
   - `frontend/src/pages/ChatPage.vue`
   - `frontend/src/types/event.ts`

### Acceptance Criteria

1. User cannot enter interactive takeover until pause succeeds.
2. Agent does not continue execution while takeover is active.
3. Exiting takeover reliably resumes agent when requested.
4. Existing chat/session flows remain backward compatible.
5. Onboarding tooltip accurately describes the pause-first behavior.

> [!NOTE]
> Criterion #1 is not fully satisfied yet due to the current route/query takeover fallback path (`preview=1`) that can render takeover UI without first calling `takeover/start`.

---

## Phase 1: Captcha/Login Handoff + Persisted Auth (P1)
**Status:** In Progress

### Progress Snapshot (2026-02-24)

Completed:
1. Wait metadata (`wait_reason`, `suggest_user_takeover`) is emitted and consumed.
2. Chat UI renders explicit takeover CTA for login/captcha/2FA/payment/verification waits.
3. `persist_login_state` end-to-end wiring exists for takeover exit -> snapshot -> later restore path.
4. File-backed retention policy exists (7-day TTL, max 5 states/user, restrictive file permissions).

In Progress:
1. Reconnect/crash-path validation for restored login state.

Not Started:
1. Cleanup of persisted login-state files on session delete.

### Backend

1. Validate and tighten challenge reason classifier behavior for tool outputs:
   - `backend/app/domain/services/agents/execution.py`
   - `backend/app/domain/services/tools/playwright_tool.py` (metadata enrichment)
2. Expand verification for existing storageState snapshot/restore implementation:
   - `backend/app/infrastructure/external/browser/playwright_browser.py`
   - relevant storage/service modules for persisted state files/records
3. Add cleanup-on-delete for persisted login state.

### Frontend

1. Show explicit "Take over to finish login/captcha" prompt on wait reasons.
2. Add/validate structured exit summary capture for handoff-sensitive reasons.

### Acceptance Criteria

1. Captcha/login/2FA waits present direct takeover CTA.
2. Persisted login option restores authenticated state on subsequent browser sessions.
3. Agent resumes with user context and fresh state awareness.

---

## Phase 2: Browser Controls + Target Affinity + Security Hardening (P1)
**Status:** In Progress

### Progress Snapshot (2026-02-24)

Completed:
1. `cdp_navigation.py` and sandbox navigation API routes are implemented.
2. Backend takeover navigation proxy routes are implemented.
3. Frontend takeover nav buttons call real navigation APIs (`back`/`forward`/`reload`/`stop`).
4. Sensitive query-value redaction is implemented in websocket proxy logging paths.

In Progress:
1. Input/screencast target-affinity hardening for multi-tab scenarios.
2. WebSocket origin allowlist enforcement.

### Sandbox/Backend

1. Introduce shared active-target registry for screencast/input alignment.
2. Add origin checks at websocket proxy entrypoints:
   - `backend/app/interfaces/api/session_routes.py`
   - supporting middleware/dependency if centralized.

### Frontend

1. Validate URL-bar/history sync behavior under reconnect and multi-tab transitions:
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
   - takeover start/end/status authorization, idempotency, state transitions.
2. `backend/tests/application/services/test_session_lifecycle_service.py`
   - pause/resume/takeover state transitions and context injection.
3. New tests for `AgentSessionLifecycle` takeover transitions + resume failure behavior.
4. New tests around event mapping metadata and login-state persistence path (including delete cleanup once added).

## Frontend

```bash
cd frontend && bun run lint && bun run type-check
```

Focused tests to add/update:

1. New tests for `TakeOverView` orchestration and `ChatPage` wait CTA behavior.
2. New tests to prevent route/query fallback takeover bypass of pause-first arbitration.

## Sandbox

1. Create `scripts/test_cdp_navigation.sh` for navigation control commands.
2. Add target-affinity tests for input + screencast alignment.

---

## 7. Risks and Mitigations

1. **Risk:** Pause latency causes poor takeover UX.  
Mitigation: optimistic loading UI with timeout and explicit error recovery path.

2. **Risk:** Persisted auth state leaks between users/sessions.  
Mitigation: strict namespace keys by user ownership; encrypted or locked-down storage location; 7-day TTL with max 5 states per user.

3. **Risk:** Event schema drift breaks older frontend assumptions.  
Mitigation: additive-only fields and contract tests for legacy payload compatibility.

4. **Risk:** Target affinity changes introduce new CDP complexity.  
Mitigation: single target-selection component with tests; fail-safe fallback to active page rediscovery.

---

## 8. Rollout Strategy

1. Current implementation is live-by-default; dedicated takeover feature flags (`takeover_v2_enabled`, `persist_login_state_enabled`, `ws_origin_enforcement`) are not currently defined in backend settings.
2. If staged rollout is required, add explicit feature flags before enabling origin enforcement/affinity changes in production-like environments.
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
8. Onboarding tooltip accurately reflects the pause-first behavior.

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
