# New Task Fresh Sandbox Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Guarantee a clean sandbox for every new task while keeping the New Task UX fast, showing an initializing state if a fresh sandbox isn’t ready within 3 seconds.

**Architecture:** Session creation explicitly requests a fresh sandbox with a bounded wait. The backend returns `INITIALIZING` if the sandbox isn’t ready within the timeout and continues warm-up in the background. The frontend recognizes `INITIALIZING`, blocks send, and shows a clear “Preparing clean sandbox…” banner until the session becomes `PENDING`.

**Tech Stack:** FastAPI + Pydantic v2 backend, Vue 3 frontend, Docker sandbox pool.

---

### Task 1: Add Backend Tests for Fresh Sandbox Session Creation

**Files:**
- Create: `backend/tests/application/services/test_agent_service_create_session.py`

**Step 1: Write the failing test for timeout behavior**

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.agent_service import AgentService
from app.domain.models.session import SessionStatus
from app.domain.models.agent import Agent

class DummyLLM:
    model_name = "test"
    temperature = 0.0
    max_tokens = 100

class DummyTask:
    @classmethod
    def create(cls, *_args, **_kwargs):
        raise AssertionError("Task creation should not be invoked in create_session tests")

@pytest.mark.asyncio
async def test_create_session_returns_initializing_on_timeout(monkeypatch):
    agent_repo = AsyncMock()
    session_repo = AsyncMock()
    session_repo.find_by_user_id = AsyncMock(return_value=[])
    session_repo.save = AsyncMock()
    session_repo.update_status = AsyncMock()

    # Build service with minimal dependencies
    service = AgentService(
        llm=DummyLLM(),
        agent_repository=agent_repo,
        session_repository=session_repo,
        sandbox_cls=MagicMock(),
        task_cls=DummyTask,
        json_parser=MagicMock(),
        file_storage=MagicMock(),
        mcp_repository=MagicMock(),
        search_engine=None,
        memory_service=None,
        mongodb_db=None,
    )

    # Slow warm-up to force timeout
    warm_started = asyncio.Event()

    async def slow_warm(session_id: str) -> None:
        warm_started.set()
        await asyncio.sleep(0.2)

    monkeypatch.setattr(service, "_warm_sandbox_for_session", slow_warm)

    session = await service.create_session(
        user_id="user-1",
        require_fresh_sandbox=True,
        sandbox_wait_seconds=0.05,
    )

    assert session.status == SessionStatus.INITIALIZING
    assert warm_started.is_set()
```

**Step 2: Run test to verify it fails**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_agent_service_create_session.py::test_create_session_returns_initializing_on_timeout -v`
Expected: FAIL with missing `require_fresh_sandbox` or logic not implemented.

**Step 3: Add test for fast success path**

```python
@pytest.mark.asyncio
async def test_create_session_returns_pending_when_warm_completes(monkeypatch):
    agent_repo = AsyncMock()
    session_repo = AsyncMock()
    session_repo.find_by_user_id = AsyncMock(return_value=[])
    session_repo.save = AsyncMock()
    session_repo.update_status = AsyncMock()

    service = AgentService(
        llm=DummyLLM(),
        agent_repository=agent_repo,
        session_repository=session_repo,
        sandbox_cls=MagicMock(),
        task_cls=DummyTask,
        json_parser=MagicMock(),
        file_storage=MagicMock(),
        mcp_repository=MagicMock(),
        search_engine=None,
        memory_service=None,
        mongodb_db=None,
    )

    async def fast_warm(session_id: str) -> None:
        return None

    monkeypatch.setattr(service, "_warm_sandbox_for_session", fast_warm)

    session = await service.create_session(
        user_id="user-1",
        require_fresh_sandbox=True,
        sandbox_wait_seconds=1.0,
    )

    assert session.status == SessionStatus.PENDING
```

**Step 4: Run tests to verify both fail**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_agent_service_create_session.py -v`
Expected: FAIL

**Step 5: Commit**

```bash
git add backend/tests/application/services/test_agent_service_create_session.py
git commit -m "test: cover fresh sandbox session creation"
```

---

### Task 2: Implement Fresh Sandbox Controls in Session Creation

**Files:**
- Modify: `backend/app/interfaces/schemas/session.py`
- Modify: `backend/app/interfaces/api/session_routes.py`
- Modify: `backend/app/application/services/agent_service.py`

**Step 1: Update request schema to accept freshness options**

```python
class CreateSessionRequest(BaseModel):
    mode: AgentMode | None = AgentMode.AGENT
    message: str | None = None
    require_fresh_sandbox: bool = True
    sandbox_wait_seconds: float = 3.0
```

**Step 2: Pass new fields into AgentService.create_session**

```python
session = await agent_service.create_session(
    current_user.id,
    mode=request.mode,
    initial_message=request.message,
    require_fresh_sandbox=request.require_fresh_sandbox,
    sandbox_wait_seconds=request.sandbox_wait_seconds,
)
```

**Step 3: Implement fresh sandbox logic in AgentService.create_session**

```python
async def create_session(..., require_fresh_sandbox: bool = True, sandbox_wait_seconds: float = 3.0) -> Session:
    ...
    session = Session(...)
    if require_fresh_sandbox:
        session.status = SessionStatus.INITIALIZING
    await self._session_repository.save(session)

    if require_fresh_sandbox:
        task = asyncio.create_task(self._warm_sandbox_for_session(session.id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=sandbox_wait_seconds)
        except TimeoutError:
            pass
        # Re-fetch status to return accurate view
        updated = await self._session_repository.find_by_id(session.id)
        return updated or session

    # Existing sandbox_eager_init path for non-fresh sessions
```

**Step 4: Run tests to verify they pass**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_agent_service_create_session.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/interfaces/schemas/session.py backend/app/interfaces/api/session_routes.py backend/app/application/services/agent_service.py
git commit -m "feat: support fresh sandbox session creation"
```

---

### Task 3: Frontend API + New Task Stop Logic

**Files:**
- Modify: `frontend/src/api/agent.ts`
- Modify: `frontend/src/components/LeftPanel.vue`

**Step 1: Add optional createSession options (fresh sandbox defaults)**

```ts
export interface CreateSessionOptions {
  require_fresh_sandbox?: boolean;
  sandbox_wait_seconds?: number;
}

export async function createSession(
  mode: AgentMode = 'agent',
  options?: CreateSessionOptions
): Promise<CreateSessionResponse> {
  const response = await apiClient.put<ApiResponse<CreateSessionResponse>>('/sessions', {
    mode,
    ...(options || {})
  });
  return response.data.data;
}
```

**Step 2: Stop INITIALIZING sessions on New Task**

```ts
if (currentSession && [SessionStatus.RUNNING, SessionStatus.PENDING, SessionStatus.INITIALIZING].includes(currentSession.status)) {
  await stopSession(currentSessionId);
}
```

**Step 3: Manual check**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/api/agent.ts frontend/src/components/LeftPanel.vue
git commit -m "feat: stop initializing sessions on new task"
```

---

### Task 4: Frontend Initializing UX + Message Gate

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`
- Modify: `frontend/src/components/ChatBox.vue`

**Step 1: Add UI banner and block sending while session is INITIALIZING**

```vue
<div v-if="sessionStatus === SessionStatus.INITIALIZING" class="init-banner">
  Preparing clean sandbox…
</div>

<ChatBox
  ...
  :isBlocked="sessionStatus === SessionStatus.INITIALIZING"
/>
```

```ts
const props = defineProps<{ ...; isBlocked?: boolean }>();
const sendEnabled = computed(() => {
  return !props.isBlocked && chatBoxFileListRef.value?.isAllUploaded && hasTextInput.value;
});
```

**Step 2: Delay initial message until session becomes PENDING**

```ts
const pendingInitialMessage = ref<{ message: string; files: FileInfo[] } | null>(null);

const awaitSessionReady = async () => {
  if (!sessionId.value) return;
  while (true) {
    const session = await agentApi.getSession(sessionId.value);
    sessionStatus.value = session.status as SessionStatus;
    if (session.status !== SessionStatus.INITIALIZING) return;
    await new Promise((r) => setTimeout(r, 500));
  }
};
```

**Step 3: Manual check**

- Create a new session with backend returning `INITIALIZING`.
- Confirm banner shows, send button disabled, and initial message is sent automatically once status flips to `PENDING`.

**Step 4: Commit**

```bash
git add frontend/src/pages/ChatPage.vue frontend/src/components/ChatBox.vue
git commit -m "feat: block chat while sandbox initializes"
```

---

### Task 5: Full Verification

**Files:**
- None

**Step 1: Backend test suite (targeted)**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_agent_service_create_session.py -v`
Expected: PASS

**Step 2: Frontend checks**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: PASS

**Step 3: Commit verification notes**

```bash
git status --short
```
Expected: clean or only intentional changes.

---

## Notes
- Use `@superpowers:verification-before-completion` after Task 5 before reporting completion.
- If `sandbox_eager_init` behavior conflicts, keep it for non-fresh sessions only; fresh sessions should always warm immediately.
