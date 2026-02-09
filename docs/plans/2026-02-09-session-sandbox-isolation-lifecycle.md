# Session Sandbox Isolation Lifecycle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure every session gets its own sandbox at task start, shows explicit "Initializing my PC..." loading state, and always destroys the session sandbox when the session is ended.

**Architecture:** Keep session lifecycle ownership in backend services (`AgentService` and `AgentDomainService`) and make teardown idempotent. Preserve fast startup by keeping eager warm-up, but close race/leak paths when a warmed sandbox cannot be bound to the target session. Update frontend route/unload cleanup logic so session-end actions trigger teardown for all active startup/run states.

**Tech Stack:** FastAPI, Python (Pydantic v2), Vue 3 + TypeScript, Vitest, Pytest

---

**Execution skills to apply:** `@test-driven-development`, `@verification-before-completion`

### Task 1: Make Warm-Up Race-Safe and Session-Isolated

**Files:**
- Create: `backend/tests/application/services/test_agent_service_sandbox_lifecycle.py`
- Modify: `backend/app/application/services/agent_service.py:185-238`
- Test: `backend/tests/application/services/test_agent_service_sandbox_lifecycle.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_warm_sandbox_destroys_unbound_sandbox_when_session_already_has_sandbox_id(monkeypatch):
    service, repo = build_service_with_fake_repo(existing_sandbox_id="sandbox-existing")

    created_sandbox = AsyncMock()
    created_sandbox.id = "sandbox-new"
    created_sandbox.destroy = AsyncMock(return_value=True)
    created_sandbox.ensure_sandbox = AsyncMock()
    service._sandbox_cls.create = AsyncMock(return_value=created_sandbox)

    monkeypatch.setattr("app.application.services.agent_service.get_settings", lambda: SimpleNamespace(sandbox_pool_enabled=False))

    await service._warm_sandbox_for_session("session-1")

    assert created_sandbox.destroy.await_count == 1
    session = await repo.find_by_id("session-1")
    assert session.sandbox_id == "sandbox-existing"
```

**Step 2: Run test to verify it fails**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_agent_service_sandbox_lifecycle.py::test_warm_sandbox_destroys_unbound_sandbox_when_session_already_has_sandbox_id -v`
Expected: FAIL because warm-up currently leaves the newly created sandbox alive when `session.sandbox_id` is already set.

**Step 3: Write minimal implementation**

```python
# backend/app/application/services/agent_service.py (_warm_sandbox_for_session)
session = await self._session_repository.find_by_id(session_id)
if not session:
    await sandbox.destroy()
    return

if session.sandbox_id and session.sandbox_id != sandbox.id:
    logger.info("Session %s already bound to sandbox %s; destroying unbound sandbox %s", session_id, session.sandbox_id, sandbox.id)
    await sandbox.destroy()
    await self._session_repository.update_status(session_id, SessionStatus.PENDING)
    return

if not session.sandbox_id:
    session.sandbox_id = sandbox.id
    await self._session_repository.save(session)
```

**Step 4: Run test to verify it passes**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_agent_service_sandbox_lifecycle.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/tests/application/services/test_agent_service_sandbox_lifecycle.py backend/app/application/services/agent_service.py
git commit -m "test+fix: destroy unbound warm-up sandbox and enforce per-session binding"
```

### Task 2: Make Session Stop Teardown Deterministic

**Files:**
- Create: `backend/tests/domain/services/test_agent_domain_service_stop_session.py`
- Modify: `backend/app/domain/services/agent_domain_service.py:477-506`
- Test: `backend/tests/domain/services/test_agent_domain_service_stop_session.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_stop_session_destroys_sandbox_and_clears_references():
    session = Session(user_id="user-1", agent_id="agent-1", sandbox_id="sb-1", task_id="task-1")
    repo = AsyncMock()
    repo.find_by_id = AsyncMock(return_value=session)
    repo.save = AsyncMock()

    task = MagicMock()
    sandbox = AsyncMock()
    sandbox.destroy = AsyncMock(return_value=True)

    service = build_domain_service(repo=repo, task=task, sandbox=sandbox)

    await service.stop_session(session.id)

    task.cancel.assert_called_once()
    sandbox.destroy.assert_awaited_once()
    assert session.sandbox_id is None
    assert session.task_id is None
    assert session.status == SessionStatus.COMPLETED
    repo.save.assert_awaited_once_with(session)
```

**Step 2: Run test to verify it fails**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_domain_service_stop_session.py::test_stop_session_destroys_sandbox_and_clears_references -v`
Expected: FAIL because `stop_session()` currently does not clear `sandbox_id`/`task_id` in the session record.

**Step 3: Write minimal implementation**

```python
# backend/app/domain/services/agent_domain_service.py (stop_session)
if task:
    task.cancel()

if session.sandbox_id:
    ...  # existing destroy logic

session.sandbox_id = None
session.task_id = None
session.status = SessionStatus.COMPLETED
await self._session_repository.save(session)
self._task_creation_locks.pop(session_id, None)
```

**Step 4: Run test to verify it passes**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_domain_service_stop_session.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/tests/domain/services/test_agent_domain_service_stop_session.py backend/app/domain/services/agent_domain_service.py
git commit -m "test+fix: clear sandbox and task references on session stop"
```

### Task 3: Update Frontend Session-End Cleanup + Loading Text

**Files:**
- Create: `frontend/src/utils/sessionLifecycle.ts`
- Create: `frontend/tests/utils/sessionLifecycle.spec.ts`
- Modify: `frontend/src/pages/ChatPage.vue:102-105`
- Modify: `frontend/src/pages/ChatPage.vue:1594-1688`
- Test: `frontend/tests/utils/sessionLifecycle.spec.ts`

**Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest'
import { SessionStatus } from '@/types/response'
import { shouldStopSessionOnExit } from '@/utils/sessionLifecycle'

describe('shouldStopSessionOnExit', () => {
  it('returns true for initializing, pending, running, waiting', () => {
    expect(shouldStopSessionOnExit(SessionStatus.INITIALIZING)).toBe(true)
    expect(shouldStopSessionOnExit(SessionStatus.PENDING)).toBe(true)
    expect(shouldStopSessionOnExit(SessionStatus.RUNNING)).toBe(true)
    expect(shouldStopSessionOnExit(SessionStatus.WAITING)).toBe(true)
  })

  it('returns false for completed and failed', () => {
    expect(shouldStopSessionOnExit(SessionStatus.COMPLETED)).toBe(false)
    expect(shouldStopSessionOnExit(SessionStatus.FAILED)).toBe(false)
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test frontend/tests/utils/sessionLifecycle.spec.ts`
Expected: FAIL because `sessionLifecycle.ts` helper does not exist yet.

**Step 3: Write minimal implementation**

```ts
// frontend/src/utils/sessionLifecycle.ts
import { SessionStatus } from '@/types/response'

export function shouldStopSessionOnExit(status?: SessionStatus): boolean {
  return status === SessionStatus.INITIALIZING
    || status === SessionStatus.PENDING
    || status === SessionStatus.RUNNING
    || status === SessionStatus.WAITING
}
```

```vue
<!-- frontend/src/pages/ChatPage.vue -->
<span v-if="!sessionInitTimedOut" class="text-sm text-[var(--text-secondary)]">{{ $t('Initializing my PC...') }}</span>
```

```ts
// frontend/src/pages/ChatPage.vue (route leave/update + beforeunload)
if (prevSessionId && shouldStopSessionOnExit(sessionStatus.value)) {
  await agentApi.stopSession(prevSessionId)
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run test frontend/tests/utils/sessionLifecycle.spec.ts`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/utils/sessionLifecycle.ts frontend/tests/utils/sessionLifecycle.spec.ts frontend/src/pages/ChatPage.vue
git commit -m "feat: stop active session lifecycle states on exit and show initializing-my-pc banner"
```

### Task 4: Add Regression Coverage for Stop Endpoint Lifecycle Semantics

**Files:**
- Modify: `backend/tests/interfaces/api/test_session_routes.py`
- Test: `backend/tests/interfaces/api/test_session_routes.py`

**Step 1: Write the failing test**

```python
def test_stop_session_route_calls_service_with_current_user(client, mock_agent_service, auth_headers):
    response = client.post('/api/v1/sessions/session-123/stop', headers=auth_headers)
    assert response.status_code == 200
    mock_agent_service.stop_session.assert_awaited_once_with('session-123', 'test-user-id')
```

**Step 2: Run test to verify it fails**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_session_routes.py::test_stop_session_route_calls_service_with_current_user -v`
Expected: FAIL if current route fixture coverage does not assert stop lifecycle wiring.

**Step 3: Write minimal implementation**

```python
# If needed in test fixture setup only:
mock_agent_service.stop_session = AsyncMock(return_value=None)
```

**Step 4: Run test to verify it passes**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_session_routes.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/tests/interfaces/api/test_session_routes.py
git commit -m "test: lock stop-session api lifecycle behavior"
```

### Task 5: Full Verification and Final Hygiene

**Files:**
- Modify: none (verification only)

**Step 1: Backend lint/type/style checks**

Run: `conda activate pythinker && cd backend && ruff check . && ruff format --check .`
Expected: PASS.

**Step 2: Backend tests**

Run: `conda activate pythinker && cd backend && pytest tests/`
Expected: PASS.

**Step 3: Frontend checks**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: PASS.

**Step 4: Frontend tests for touched scope**

Run: `cd frontend && bun run test frontend/tests/utils/sessionReady.spec.ts frontend/tests/utils/sessionLifecycle.spec.ts`
Expected: PASS.

**Step 5: Commit verification artifact**

```bash
git status --short
git log --oneline -n 5
```

Expected: only planned commits are present; working tree is clean.
