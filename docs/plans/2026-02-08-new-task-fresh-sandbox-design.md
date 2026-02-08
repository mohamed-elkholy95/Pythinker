# New Task Fresh Sandbox Design

**Goal:** Ensure every new task starts from a clean sandbox while keeping the New Task UX fast and predictable (max 3s wait before showing an initializing state).

## User Flow
- Clicking **New Task** immediately cancels any running task, stops the current session, destroys its sandbox, and routes the user to Home.
- No new session is created on New Task. The user types a new prompt on Home and submits to start a new session.
- On submit, the app creates a new session and attempts to attach a **fresh sandbox**. If a clean sandbox cannot be confirmed within 3 seconds, the session is returned as `INITIALIZING` and the UI shows a clear “Preparing clean sandbox…” state until ready.

## Backend Design
- Add explicit freshness and timeout controls to session creation:
  - `CreateSessionRequest.require_fresh_sandbox: bool = True`
  - `CreateSessionRequest.sandbox_wait_seconds: float = 3.0`
- `AgentService.create_session()` attempts to acquire a fresh sandbox (prefer pool; fallback to on-demand) and verify it within `sandbox_wait_seconds`.
  - If ready within time: set `session.sandbox_id`, return `PENDING`.
  - If not ready: return `INITIALIZING` and continue warming in a background task that sets `sandbox_id` and flips to `PENDING` when complete.
- Cleanup path updates:
  - Treat `INITIALIZING` sessions as stale in `_cleanup_stale_sessions`.
  - `stop_session` should be callable for `INITIALIZING` sessions to destroy partially warmed sandboxes.

## Frontend UX
- `New Task` stop logic includes `INITIALIZING` as stoppable.
- In the chat view, if the session status is `INITIALIZING`, show a blocking banner/spinner and disable sending until `PENDING`.
- Use SSE/polling to refresh status and transition UI when the sandbox becomes ready.

## Data Flow (Happy Path)
1. User clicks New Task → current session stopped + sandbox destroyed → Home.
2. User submits prompt → `createSession(require_fresh_sandbox=true, sandbox_wait_seconds=3.0)`.
3. Backend returns `PENDING` (sandbox ready) or `INITIALIZING` (still warming).
4. UI renders chat; if `INITIALIZING`, show “Preparing clean sandbox…” until ready.

## Error Handling
- If sandbox creation fails: keep session in `PENDING` and allow normal task creation (existing fallback behavior), but surface a toast/log for diagnostics.
- If pool is exhausted: on-demand creation proceeds; if it exceeds 3 seconds, UI remains in initializing state until ready.

## Testing
- Backend unit tests:
  - `create_session` returns `INITIALIZING` when sandbox warm-up exceeds timeout.
  - `_cleanup_stale_sessions` stops `INITIALIZING` sessions.
  - `stop_session` destroys sandbox for `INITIALIZING` sessions.
- Frontend tests:
  - `New Task` stops `INITIALIZING` sessions.
  - Chat view shows initializing banner and blocks send while `INITIALIZING`.

