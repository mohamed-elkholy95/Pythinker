# Production Bug Fix Plan

**Generated:** 2026-02-24
**Source:** Deep-scan code review (68 files, full backend + frontend composables)
**Total findings:** 19 (4 Critical · 8 High · 7 Important)

---

## Fix Priority Matrix

| Priority | Tracking | Fixes | Rationale |
|----------|----------|-------|-----------|
| **P0 — Do immediately** | CRITICAL-3, CRITICAL-4 | Event loop blockers | Affect ALL users under any load |
| **P0 — Do immediately** | CRITICAL-1, CRITICAL-2, IMPORTANT-4 | Auth security chain | Enum → spam → account takeover |
| **P1 — This week** | HIGH-4, HIGH-6 | Race conditions | Exploitable under concurrent load |
| **P1 — This week** | HIGH-1, HIGH-3, HIGH-5 | Stability / resource leaks | Crash risk in production |
| **P2 — Next sprint** | HIGH-2, HIGH-7, HIGH-8, IMPORTANT-2, IMPORTANT-5, IMPORTANT-6 | Reliability cleanup | Non-crash but degrades over time |
| **P3 — Backlog** | IMPORTANT-1, IMPORTANT-3, IMPORTANT-7 | Polish | Low risk, clean-up |

---

## P0 — Immediate Fixes

---

### CRITICAL-3 · Synchronous SMTP Blocks the Async Event Loop

**File:** `backend/app/application/services/email_service.py:155–173`
**Category:** Reliability / Concurrency
**Impact:** Stalls the entire asyncio event loop during SMTP handshake (seconds), dropping all SSE streams and agent tasks system-wide.

**Root cause:** `async def _send_smtp_email()` calls `smtplib.SMTP_SSL()` directly — a blocking TCP + TLS call — with no `asyncio.to_thread()` wrapper. The docstring claims "runs in thread pool" but the implementation does not.

**Fix:**
```python
async def _send_smtp_email(self, msg: MIMEMultipart, email: str) -> None:
    def _blocking_send() -> None:
        server = smtplib.SMTP_SSL(
            self.settings.email_host,
            self.settings.email_port,
            timeout=30,  # also fixes HIGH-5
        )
        try:
            server.login(self.settings.email_user, self.settings.email_password)
            server.sendmail(self.settings.email_from, [email], msg.as_string())
        finally:
            server.quit()

    await asyncio.to_thread(_blocking_send)
```

**Covers:** Also resolves **HIGH-5** (missing socket timeout on SMTP).

---

### CRITICAL-4 · docker-py Calls Block the Async Event Loop

**Files:** `backend/app/core/sandbox_manager.py:265, 271, 274, 428, 462–463`
**Category:** Reliability / Concurrency
**Impact:** Container create/stop/restart blocks the event loop for 10–30 seconds, dropping SSE keepalives across all active sessions.

**Root cause:** All docker-py SDK calls are synchronous but called directly from `async` methods. `sandbox_pool.py` already wraps docker-py calls in `asyncio.to_thread()` for image pulls — the same pattern must be applied to the sandbox lifecycle methods.

**Fix pattern (apply to all docker-py calls):**
```python
# Container creation
self.container = await asyncio.to_thread(
    docker_client.containers.run, **container_config
)

# Container reload
await asyncio.to_thread(self.container.reload)

# Container restart
await asyncio.to_thread(self.container.restart)

# Container stop + remove
await asyncio.to_thread(self.container.stop, timeout=10)
await asyncio.to_thread(self.container.remove, force=True)
```

**Affected methods:** `_create_task()`, `_restart_services()`, `_cleanup()`, `docker_sandbox.py` equivalents.

---

### CRITICAL-1 · OTP Leaked to Logs

**File:** `backend/app/application/services/email_service.py:141`
**Category:** Security
**Impact:** Raw 6-digit OTP written to stdout, Loki, and any log drain. Any engineer or tool with log read access can use codes to take over accounts.

**Fix:**
```python
# Remove this line entirely, or replace with:
logger.debug("Verification code generated for %s (redacted)", email)
```

---

### CRITICAL-2 · User Enumeration via Password Reset Endpoint

**File:** `backend/app/interfaces/api/auth_routes.py:206–208`
**Category:** Security
**Impact:** HTTP 404 on unknown email lets attackers enumerate all registered accounts. Compounded by IMPORTANT-4 (wrong rate limit).

**Fix:**
```python
user = await auth_service.user_repository.get_user_by_email(request.email)
if not user or not user.is_active:
    # Always return 200 — never disclose whether email is registered
    return APIResponse.success({})
```

---

### IMPORTANT-4 · `send-verification-code` Not in Auth Rate-Limit Path

**File:** `backend/app/core/middleware.py:215–224`
**Category:** Security
**Impact:** The endpoint falls through to the general 300 req/min limit instead of the 10 req/min auth limit. Combined with CRITICAL-2, enables high-speed enumeration and email spam.

**Fix:**
```python
AUTH_PATHS: ClassVar[set[str]] = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/auth/send-verification-code",   # ← ADD
    "/api/v1/auth/reset-password",           # ← ADD
}
```

---

## P1 — This Week

---

### HIGH-4 · Race Condition: Duplicate Docker Containers for Same Session

**File:** `backend/app/core/sandbox_manager.py:81–137`
**Category:** Concurrency
**Impact:** Two concurrent `get_sandbox(session_id)` calls can both observe `None` and each spawn a container. The second overwrites `_sandboxes[session_id]`, permanently leaking the first container.

**Fix:** Apply a per-session asyncio lock (same pattern as `HTTPClientPool._get_lock()`):
```python
_session_locks: dict[str, asyncio.Lock] = {}
_session_locks_lock: asyncio.Lock = asyncio.Lock()

async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
    async with self._session_locks_lock:
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

async def get_sandbox(self, session_id: str) -> ManagedSandbox:
    lock = await self._get_session_lock(session_id)
    async with lock:
        sandbox = self._sandboxes.get(session_id)
        if sandbox and sandbox.is_healthy():
            return sandbox
        return await self.create_sandbox(session_id)
```

---

### HIGH-6 · OTP Verification Not Atomic — Brute-Force Limit Bypassable

**File:** `backend/app/application/services/email_service.py:61–78`
**Category:** Security / Concurrency
**Impact:** Concurrent parallel requests can each read `attempts=0`, both increment to `1`, doubling the effective brute-force budget (3 → 6+ per concurrent pair).

**Fix:** Use a Redis Lua script for atomic get-increment-check:
```lua
-- atomic_verify.lua
local key = KEYS[1]
local submitted = ARGV[1]
local max_attempts = tonumber(ARGV[2])

local data = redis.call('HGETALL', key)
if #data == 0 then return {0, 'expired'} end

local attempts = tonumber(redis.call('HGET', key, 'attempts') or 0)
if attempts >= max_attempts then
    redis.call('DEL', key)
    return {0, 'exceeded'}
end

redis.call('HINCRBY', key, 'attempts', 1)
local stored_code = redis.call('HGET', key, 'code')
if stored_code == submitted then
    redis.call('DEL', key)
    return {1, 'ok'}
end
return {0, 'invalid'}
```

---

### HIGH-1 · `SandboxHealth.last_check` Type Mismatch → TypeError Crash

**File:** `backend/app/core/sandbox_manager.py:50`
**Category:** Reliability / Bug
**Impact:** Any timestamp arithmetic before first health check raises `TypeError`, silently killing the background health monitor task.

**Fix:**
```python
@dataclass
class SandboxHealth:
    last_check: datetime | None = None   # was: datetime = None
    is_healthy: bool = False
    last_error: str | None = None
```

---

### HIGH-3 · Health Monitor Busy-Loops at Full CPU on Repeated Errors

**File:** `backend/app/core/sandbox_manager.py:155–184`
**Category:** Reliability / Resource Leak
**Impact:** On repeated health check failures the task spins at CPU max with no backoff. No `CancelledError` handler exits cleanly. Background tasks not awaited on shutdown.

**Fix:** Add exponential backoff on consecutive errors, clean `CancelledError` exit, and a `shutdown()` method:
```python
async def _monitor_sandbox_health(self, sandbox: ManagedSandbox) -> None:
    consecutive_errors = 0
    while sandbox.state not in (SandboxState.DESTROYED, SandboxState.FAILED):
        try:
            await self._run_health_check(sandbox)
            consecutive_errors = 0
            await asyncio.sleep(self._health_check_interval)
        except asyncio.CancelledError:
            return  # clean shutdown — do not swallow
        except Exception as e:
            consecutive_errors += 1
            backoff = min(2 ** consecutive_errors, 60)  # max 60s
            logger.error(
                "sandbox_health_check_failed",
                session_id=sandbox.session_id,
                consecutive_errors=consecutive_errors,
                backoff_seconds=backoff,
                error=str(e),
            )
            await asyncio.sleep(backoff)

async def shutdown(self) -> None:
    """Cancel and await all background monitoring tasks."""
    for task in list(self._background_tasks):
        task.cancel()
    await asyncio.gather(*self._background_tasks, return_exceptions=True)
    self._background_tasks.clear()
```

---

### HIGH-5 · SMTP Has No Socket Timeout

**File:** `backend/app/application/services/email_service.py:162`
**Category:** Reliability
**Impact:** Unreachable SMTP host hangs the event loop thread indefinitely (compounds CRITICAL-3).
**Fix:** Covered by the CRITICAL-3 fix above (`timeout=30` parameter added).

---

## P2 — Next Sprint

---

### HIGH-2 · Module-Level `_pending_disconnect_cancellations` Dict Never Evicted

**File:** `backend/app/interfaces/api/session_routes.py:112–148`
**Category:** Memory Leak
**Impact:** Stale session IDs accumulate in a module-level dict over time. In multi-worker deployments, cross-process disconnect events silently fail.

**Fix:** Replace with `WeakValueDictionary` or cap size via LRU eviction. For multi-worker correctness, use Redis-backed coordination consistent with the existing stream guard pattern.

---

### HIGH-7 · `_restart_services` Blocks Event Loop Then Sleeps 10s

**File:** `backend/app/core/sandbox_manager.py:428–429`
**Category:** Reliability
**Impact:** `container.restart()` is synchronous (blocks up to 30s) + then `asyncio.sleep(10)` = potential 40s event loop block per recovery cycle.
**Fix:** Covered by CRITICAL-4 fix (wrap in `asyncio.to_thread`).

---

### HIGH-8 · `aclose()` Suppresses All Exceptions — Agent May Not Be Cancelled

**File:** `backend/app/interfaces/api/session_routes.py:910–911, 923–924`
**Category:** Reliability
**Impact:** Exceptions during generator cleanup are silently swallowed. Agent coroutine may continue running against a completed session.

**Fix:**
```python
try:
    await stream_iter.aclose()
except Exception as e:
    logger.warning(
        "chat_stream_close_error",
        session_id=session_id,
        error=str(e),
    )
```

---

### IMPORTANT-2 · `HTTPClientPool._get_lock()` Has Race at Initialization

**File:** `backend/app/infrastructure/external/http_pool.py:224–229`
**Category:** Concurrency
**Impact:** Two startup coroutines can create separate `asyncio.Lock` instances, breaking mutual exclusion on the pool.

**Fix:**
```python
# Eager class-level initialization instead of lazy check
_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
```

---

### IMPORTANT-5 · `useSSEConnection` Window Listener Leaks Outside Components

**File:** `frontend/src/composables/useSSEConnection.ts:180–185, 295–299`
**Category:** Memory Leak
**Impact:** `window.addEventListener('sse:heartbeat', ...)` is never removed when the composable is used outside a component (Pinia store, router guard). Listeners accumulate per chat session.

**Fix:**
```typescript
// Replace onUnmounted (component-only) with onScopeDispose (always runs)
import { onScopeDispose } from 'vue'
onScopeDispose(() => stopStaleDetection())
```

---

### IMPORTANT-6 · `ensure_sandbox` Has No Wall-Clock Timeout

**File:** `backend/app/infrastructure/external/sandbox/docker_sandbox.py:421–548`
**Category:** Reliability
**Impact:** `max_retries=30` with configurable delays but no hard wall-clock limit. Slow Docker daemon can keep a session stuck in init indefinitely.

**Fix:**
```python
async def ensure_sandbox(self) -> None:
    async with asyncio.timeout(settings.sandbox_ensure_timeout_seconds):
        # ... existing retry loop unchanged ...
```

Add `sandbox_ensure_timeout_seconds: int = 120` to `config_sandbox.py`.

---

## P3 — Backlog

---

### IMPORTANT-1 · `SecurityHeadersMiddleware` Captures Settings at Import Time

**File:** `backend/app/infrastructure/middleware/security_headers.py:27`
**Category:** Reliability
**Impact:** Module-level `get_settings()` call bakes stale settings. Test fixtures patching `get_settings` have no effect.

**Fix:** Move `get_settings()` call inside `__init__()` rather than module scope.

---

### IMPORTANT-3 · `RateLimitMiddleware._fallback_storage` Mutated Without Lock

**File:** `backend/app/core/middleware.py:98–192`
**Category:** Concurrency
**Impact:** Read-modify-write on shared class dict without `asyncio.Lock`. Counters can be off under concurrency.

**Fix:** Either protect with `asyncio.Lock`, or route all fallback counting through the existing Redis atomic counter path exclusively.

---

### IMPORTANT-7 · OTP Compared with `==` Not `secrets.compare_digest`

**File:** `backend/app/application/services/email_service.py:70`
**Category:** Security
**Impact:** Timing side-channel on OTP comparison. Low practical risk given the 3-attempt limit, but OWASP recommends constant-time comparison for all auth tokens.

**Fix:**
```python
import secrets

if secrets.compare_digest(stored_data["code"], code):
```

---

## What Passed Review (Do Not Regress)

| Area | File(s) | Status |
|------|---------|--------|
| Retry framework | `core/retry.py` | ✅ Exponential backoff + jitter, scoped decorators |
| HTTP connection pooling | `infrastructure/external/http_pool.py` | ✅ LRU eviction, stats tracking, used correctly |
| NoSQL injection prevention | `mongo_session_repository.py` | ✅ `ALLOWED_SESSION_UPDATE_FIELDS` allowlist enforced |
| SSE protocol robustness | `interfaces/api/session_routes.py` | ✅ Heartbeat, cursor resume, `CancelledError` propagation |
| JWT revocation | `middleware.py`, `token_service.py` | ✅ Token blacklist with TTL recovery |
| Docker security hardening | `docker_sandbox.py` | ✅ `no-new-privileges`, cap drops, `tmpfs`, `pids_limit` |
| Circuit breaker | `circuit_breaker.py` | ✅ Non-blocking lock, state normalization, Prometheus |

---

## Implementation Notes

- **CRITICAL-3 and CRITICAL-4** should be fixed in a single commit — they share the same root pattern (sync calls in async context) and fixing one without the other leaves the event loop still blocked.
- **CRITICAL-1 + CRITICAL-2 + IMPORTANT-4** form a security chain — fix together and test as a group.
- **HIGH-4** requires careful testing: the per-session lock must be evicted after sandbox destroy to prevent unbounded lock accumulation.
- **IMPORTANT-5** fix is a 1-line change but requires a Vitest regression test to prevent reintroduction.
- All Python fixes require: `conda activate pythinker && ruff check . && pytest tests/` before committing.
- All frontend fixes require: `bun run lint && bun run type-check` before committing.
