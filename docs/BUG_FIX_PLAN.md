# Validated Bug Fix Plan

**Validated:** 2026-02-24
**Validation method:** Direct code verification against current repository state (backend + frontend)
**Original findings reviewed:** 19
**Validation result:** 13 confirmed, 4 reframed, 2 not reproducible
**Additional findings added:** 3
**Actionable findings total:** 20

---

## Fix Priority Matrix

| Priority | Tracking | Fixes | Rationale |
|----------|----------|-------|-----------|
| **P0 — Do immediately** | CRITICAL-3, HIGH-5 | SMTP event loop blockers | Blocks async loop during email send and can stall requests |
| **P0 — Do immediately** | CRITICAL-4, CRITICAL-5, HIGH-7 | Docker SDK event loop blockers | Sync Docker SDK calls inside async paths can stall SSE and API handlers |
| **P0 — Do immediately** | CRITICAL-1, CRITICAL-1B, CRITICAL-2, IMPORTANT-4 | Auth/OTP security chain | OTP disclosure + user/account-state enumeration + weak endpoint limits |
| **P1 — This week** | HIGH-4, HIGH-6, HIGH-8, HIGH-9 | Concurrency + cleanup correctness | Duplicate resources, bypassable OTP limits, cleanup reliability, health-state bug |
| **P2 — Next sprint** | HIGH-2, HIGH-3, IMPORTANT-5, IMPORTANT-6 | Reliability hardening | Multi-worker coordination and lifecycle robustness |
| **P3 — Backlog** | IMPORTANT-1, IMPORTANT-7, HIGH-1 (reframed) | Hygiene and defense-in-depth | Lower immediate risk but worth addressing |

---

## P0 — Immediate Fixes

### CRITICAL-3 · Synchronous SMTP Blocks Async Event Loop

**File:** `backend/app/application/services/email_service.py:155-173`
**Category:** Reliability / Concurrency
**Validated:** Confirmed

`_send_smtp_email()` is `async` but directly calls `smtplib.SMTP_SSL()` + `login()` + `sendmail()` without `asyncio.to_thread()`.

**Fix:** move SMTP session work into a blocking helper and call via `await asyncio.to_thread(...)`.

---

### HIGH-5 · SMTP Socket Timeout Missing

**File:** `backend/app/application/services/email_service.py:162`
**Category:** Reliability
**Validated:** Confirmed

SMTP client is created without explicit timeout. Add `timeout=30` (or configurable setting) when constructing `SMTP_SSL`.

---

### CRITICAL-4 · Sync docker-py Calls in `sandbox_manager.py`

**File:** `backend/app/core/sandbox_manager.py:265, 271, 274, 428, 462-463`
**Category:** Reliability / Concurrency
**Validated:** Confirmed

Sync Docker SDK calls are made in async methods (`create`, `_restart_services`, `destroy`).

**Fix:** wrap blocking Docker calls with `asyncio.to_thread`.

---

### CRITICAL-5 · Additional Sync Docker SDK Calls in `docker_sandbox.py`

**Files:**
- `backend/app/infrastructure/external/sandbox/docker_sandbox.py:570`
- `backend/app/infrastructure/external/sandbox/docker_sandbox.py:643-645`
- `backend/app/infrastructure/external/sandbox/docker_sandbox.py:1672-1674`

**Category:** Reliability / Concurrency
**Validated:** New finding

`ensure_sandbox()` invokes `_container_exists_and_running()` from async flow, and that helper performs sync `docker.from_env()`, `containers.get()`, and `reload()`. `DockerSandbox.get()` also performs sync Docker calls.

**Fix:**
- run `_container_exists_and_running` via `await asyncio.to_thread(...)` from async callers
- or make Docker operations in these paths explicitly thread-wrapped

---

### CRITICAL-1 · OTP Explicitly Logged

**File:** `backend/app/application/services/email_service.py:141`
**Category:** Security
**Validated:** Confirmed

Raw verification code is logged directly.

**Fix:** remove log or redact.

---

### CRITICAL-1B · OTP Also Leaked via MIME Message Logging

**File:** `backend/app/application/services/email_service.py:145`
**Category:** Security
**Validated:** New finding

Logging `Created email message: {msg}` can serialize message body content and expose OTP in logs.

**Fix:** remove message-object logging or log metadata only (recipient/domain, message type) with no body content.

---

### CRITICAL-2 · User and Account-State Enumeration in Password Reset Flow

**File:** `backend/app/interfaces/api/auth_routes.py:206-211`
**Category:** Security
**Validated:** Confirmed (expanded)

Current response behavior discloses both:
- unknown email (`404 User not found`)
- inactive account (`400 User account is inactive`)

**Fix:** always return success for `send-verification-code` regardless of existence/state; do not disclose account status.

---

### IMPORTANT-4 · Auth Rate-Limit Path Missing Password Reset Endpoints

**File:** `backend/app/core/middleware.py:92, 220-224`
**Category:** Security
**Validated:** Confirmed

`AUTH_PATHS` lacks `/api/v1/auth/send-verification-code` and `/api/v1/auth/reset-password`, so they use general limit instead of strict auth limit.

**Fix:** add both endpoints to `AUTH_PATHS`.

---

## P1 — This Week

### HIGH-4 · Race Condition Creates Duplicate Sandboxes Per Session

**File:** `backend/app/core/sandbox_manager.py:123-137`
**Category:** Concurrency
**Validated:** Confirmed

Concurrent `get_sandbox(session_id)` calls can both create sandbox instances before `_sandboxes` map settles.

**Fix:** per-session lock around read/create/destroy logic; evict lock on sandbox final teardown.

---

### HIGH-6 · OTP Verification Attempt Counter Is Non-Atomic

**File:** `backend/app/application/services/email_service.py:61-78`
**Category:** Security / Concurrency
**Validated:** Confirmed

Read-modify-write on `attempts` is vulnerable to concurrent bypass.

**Fix:** atomic Redis operation (Lua script or transaction) to check+increment+compare in one step.

---

### HIGH-8 · Stream Cleanup Swallows `aclose()` Errors

**File:** `backend/app/interfaces/api/session_routes.py:1130-1131, 1143-1144`
**Category:** Reliability
**Validated:** Confirmed

`stream_iter.aclose()` exceptions are suppressed, reducing observability and possibly masking leaked work.

**Fix:** log warning/error on cleanup failures (with session_id), avoid silent suppression.

---

### HIGH-9 · Health Failure Counter Uses Wrong Dataclass (`health` vs `metrics`)

**Files:**
- `backend/app/core/sandbox_manager.py:64`
- `backend/app/core/sandbox_manager.py:168`
- `backend/app/core/sandbox_manager.py:178`

**Category:** Reliability / Bug
**Validated:** New finding

`health_check_failures` is declared on `SandboxMetrics` but increment/reset is done on `sandbox.health.health_check_failures`.

**Fix:** consistently update `sandbox.metrics.health_check_failures`.

---

## P2 — Next Sprint

### HIGH-2 · Reframed: Cross-Worker Disconnect-Cancellation Coordination Gap

**File:** `backend/app/interfaces/api/session_routes.py:154-191`
**Category:** Reliability / Distributed correctness
**Validated:** Reframed

Original claim of local memory leak is not accurate: entries are cleaned via pop and done callbacks. The actual risk is multi-worker behavior because cancellation state is process-local.

**Fix:** move deferred-cancellation coordination to shared store (Redis) or route through distributed stream registry.

---

### HIGH-3 · Reframed: Health Monitor Lifecycle Needs Explicit Shutdown Management

**File:** `backend/app/core/sandbox_manager.py:155-184`
**Category:** Reliability
**Validated:** Reframed

Original claim of CPU busy-loop is overstated because loop sleeps each cycle. Main gap is task lifecycle: background monitor tasks are tracked but no explicit manager shutdown drains/cancels them.

**Fix:** add explicit `shutdown()` to cancel+await `_background_tasks` and wire it into app lifecycle.

---

### IMPORTANT-5 · `useSSEConnection` Listener Cleanup Depends on Component Instance

**File:** `frontend/src/composables/useSSEConnection.ts:1, 295-299`
**Category:** Reliability / Leak risk
**Validated:** Confirmed

Cleanup uses `onUnmounted` only when `getCurrentInstance()` exists. Usage from store/non-component scopes can leak heartbeat listeners.

**Fix:** use `onScopeDispose` for composable-scope cleanup.

---

### IMPORTANT-6 · Reframed: No Explicit Wall-Clock Budget for `ensure_sandbox`

**File:** `backend/app/infrastructure/external/sandbox/docker_sandbox.py:421-633`
**Category:** Reliability
**Validated:** Reframed

The loop is retry-bounded (`max_retries=30`), so “indefinite” is inaccurate. However, no global wall-clock budget exists, so total wait can still be longer than desired under repeated timeout paths.

**Fix:** optional hard wall-clock timeout wrapper (configurable) around full warmup flow.

---

## P3 — Backlog

### IMPORTANT-1 · `SecurityHeadersMiddleware` Captures Settings at Import Time

**File:** `backend/app/infrastructure/middleware/security_headers.py:27, 48, 57`
**Category:** Reliability / Testability
**Validated:** Confirmed

Module-level `settings = get_settings()` can freeze configuration assumptions for tests/runtime changes.

**Fix:** resolve settings in `__init__` and use instance field.

---

### IMPORTANT-7 · OTP Comparison Uses `==` Instead of Constant-Time Compare

**File:** `backend/app/application/services/email_service.py:70`
**Category:** Security (defense-in-depth)
**Validated:** Confirmed

Use `secrets.compare_digest(...)` for token/code comparison.

---

### HIGH-1 (Reframed to Important) · Typing Hygiene for `last_check`

**File:** `backend/app/core/sandbox_manager.py:50`
**Category:** Type correctness
**Validated:** Reframed

Current annotation is `datetime = None`; should be `datetime | None`. Original “TypeError crash” claim is not currently demonstrated by this file alone.

**Fix:** change type annotation to optional for correctness and static analysis quality.

---

## Validation of Original 19 Findings

| ID | Validation Status | Notes |
|----|-------------------|-------|
| CRITICAL-1 | Confirmed | Valid and high impact |
| CRITICAL-2 | Confirmed (expanded) | Also leaks inactive-account state |
| CRITICAL-3 | Confirmed | Valid |
| CRITICAL-4 | Confirmed | Valid |
| HIGH-1 | Reframed | Typing issue confirmed; crash claim not proven |
| HIGH-2 | Reframed | Cleanup exists; real issue is multi-worker coordination |
| HIGH-3 | Reframed | No tight busy-loop shown; shutdown lifecycle gap remains |
| HIGH-4 | Confirmed | Valid |
| HIGH-5 | Confirmed | Valid |
| HIGH-6 | Confirmed | Valid |
| HIGH-7 | Confirmed | Covered by Docker sync-call fixes |
| HIGH-8 | Confirmed | Valid |
| IMPORTANT-1 | Confirmed | Valid |
| IMPORTANT-2 | Not reproducible | `_get_lock()` race not demonstrated in current async model |
| IMPORTANT-3 | Not reproducible | Claimed dict race not demonstrated in current synchronous block |
| IMPORTANT-4 | Confirmed | Valid |
| IMPORTANT-5 | Confirmed | Valid |
| IMPORTANT-6 | Reframed | Long-tail latency risk; not strictly indefinite |
| IMPORTANT-7 | Confirmed | Valid |

---

## Additional Findings Added in This Validation

1. `CRITICAL-1B` OTP leak via message-object logging (`email_service.py:145`).
2. `CRITICAL-5` additional sync Docker SDK calls in async flow (`docker_sandbox.py`).
3. `HIGH-9` health-failure counter updated on wrong object (`sandbox_manager.py`).

---

## Implementation Notes

- Fix security chain together: `CRITICAL-1`, `CRITICAL-1B`, `CRITICAL-2`, `IMPORTANT-4`.
- Fix async-blocking chain together: `CRITICAL-3`, `HIGH-5`, `CRITICAL-4`, `CRITICAL-5`, `HIGH-7`.
- For sandbox locking (`HIGH-4`), include lock eviction strategy to avoid lock-map growth.
- For OTP atomic verification (`HIGH-6`), add concurrent verification tests.
- For frontend composable cleanup (`IMPORTANT-5`), add regression tests for store/non-component usage.
- Backend verification command: `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`
- Frontend verification command: `cd frontend && bun run lint && bun run type-check`
