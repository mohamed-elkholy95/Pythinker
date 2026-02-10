# Ephemeral Session Sandbox Lifecycle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make sandbox runtime ownership explicit so each session in dev/testing gets a temporary sandbox that is auto-created and auto-destroyed when that session ends.

**Architecture:** Introduce an explicit lifecycle mode (`ephemeral` vs `static`) and keep sandbox ownership rules inside backend services, not routes. In `ephemeral` mode, session lifecycle owns sandbox creation and teardown end-to-end; in `static` mode, pre-provisioned sandboxes are reused without container removal. Use one teardown path for all terminal states (done/error/stop/delete/disconnect) to prevent leaks and double-destroy races.

**Tech Stack:** FastAPI, Python, Docker SDK, MongoDB (Beanie), Pytest, Docker Compose

---

**Execution skills to apply:** `@systematic-debugging`, `@test-driven-development`, `@verification-before-completion`

## Confirmed Root-Cause Signals (from current repo + logs)

1. Backend logs show repeated CDP connect timeouts on static dev sandboxes (`BrowserType.connect_over_cdp: Timeout 30000ms exceeded`) and session failures after sandbox recycle attempts.
2. Current dev mode sets `SANDBOX_ADDRESS=sandbox,sandbox2`, so sessions share long-lived sandbox hosts.
3. Current lifecycle logic mixes shared-static behavior with per-session teardown calls, and sandbox destruction is not unified under a single ownership rule.

---

### Task 1: Add Explicit Sandbox Lifecycle Mode

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `docker-compose-development.yml`
- Create: `backend/tests/core/test_sandbox_lifecycle_mode.py`

**Step 1: Write the failing test**

```python
from app.core.config import Settings


def test_sandbox_lifecycle_mode_defaults_to_static():
    settings = Settings.model_construct()
    assert settings.sandbox_lifecycle_mode == "static"


def test_uses_static_sandbox_addresses_disabled_in_ephemeral_mode():
    settings = Settings.model_construct(
        sandbox_lifecycle_mode="ephemeral",
        sandbox_address="sandbox,sandbox2",
    )
    assert settings.uses_static_sandbox_addresses is False
```

**Step 2: Run test to verify it fails**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/core/test_sandbox_lifecycle_mode.py -v`
Expected: FAIL because lifecycle mode does not exist yet and `uses_static_sandbox_addresses` still depends only on `sandbox_address`.

**Step 3: Write minimal implementation**

```python
# backend/app/core/config.py
sandbox_lifecycle_mode: str = "static"  # "static" | "ephemeral"

@property
def uses_static_sandbox_addresses(self) -> bool:
    if self.sandbox_lifecycle_mode == "ephemeral":
        return False
    return bool(self.sandbox_address and self.sandbox_address.strip())
```

```yaml
# docker-compose-development.yml (backend env)
- SANDBOX_LIFECYCLE_MODE=ephemeral
- SANDBOX_ADDRESS=
- SANDBOX_IMAGE=pythinker-sandbox
```

**Step 4: Run test to verify it passes**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/core/test_sandbox_lifecycle_mode.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/tests/core/test_sandbox_lifecycle_mode.py backend/app/core/config.py .env.example docker-compose-development.yml
git commit -m "feat: add explicit sandbox lifecycle mode for static vs ephemeral behavior"
```

---

### Task 2: Make DockerSandbox Lifecycle-Mode Aware

**Files:**
- Modify: `backend/app/infrastructure/external/sandbox/docker_sandbox.py`
- Create: `backend/tests/infrastructure/external/sandbox/test_docker_sandbox_lifecycle_mode.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_create_ignores_static_addresses_when_ephemeral_mode():
    with patch("app.infrastructure.external.sandbox.docker_sandbox.get_settings") as gs:
        gs.return_value = SimpleNamespace(
            sandbox_lifecycle_mode="ephemeral",
            sandbox_address="sandbox,sandbox2",
            sandbox_image="pythinker-sandbox",
            sandbox_name_prefix="sandbox",
        )
        with patch.object(DockerSandbox, "_create_task", return_value=DockerSandbox("127.0.0.1", "sandbox-abc")) as ct:
            sb = await DockerSandbox.create()
    ct.assert_called_once()
    assert sb.id == "sandbox-abc"


@pytest.mark.asyncio
async def test_destroy_skips_container_remove_for_static_mode():
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="dev-sandbox-sandbox")
    with patch("app.infrastructure.external.sandbox.docker_sandbox.get_settings") as gs:
        gs.return_value = SimpleNamespace(sandbox_lifecycle_mode="static")
        with patch("app.infrastructure.external.sandbox.docker_sandbox.docker.from_env") as docker_env:
            ok = await sandbox.destroy()
    assert ok is True
    docker_env.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/sandbox/test_docker_sandbox_lifecycle_mode.py -v`
Expected: FAIL because `create()` still prioritizes `SANDBOX_ADDRESS` and `destroy()` does not branch on lifecycle mode.

**Step 3: Write minimal implementation**

```python
# docker_sandbox.py
if settings.sandbox_lifecycle_mode == "ephemeral":
    return await asyncio.to_thread(DockerSandbox._create_task)

if settings.sandbox_address:
    ...
```

```python
async def destroy(self) -> bool:
    settings = get_settings()
    is_static = settings.sandbox_lifecycle_mode == "static"
    ...
    if is_static:
        return True  # release local clients/pool only; no container remove
    ...
```

**Step 4: Run test to verify it passes**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/sandbox/test_docker_sandbox_lifecycle_mode.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/sandbox/docker_sandbox.py backend/tests/infrastructure/external/sandbox/test_docker_sandbox_lifecycle_mode.py
git commit -m "feat: make docker sandbox create/destroy lifecycle-mode aware"
```

---

### Task 3: Track Sandbox Ownership on Session and Centralize Teardown

**Files:**
- Modify: `backend/app/domain/models/session.py`
- Modify: `backend/app/infrastructure/models/documents.py`
- Modify: `backend/app/domain/services/agent_domain_service.py`
- Modify: `backend/app/application/services/agent_service.py`
- Create: `backend/tests/domain/services/test_agent_domain_service_session_sandbox_teardown.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_teardown_session_runtime_is_idempotent_and_clears_references():
    session = Session(id="s1", user_id="u1", agent_id="a1", sandbox_id="sb-1", sandbox_owned=True, task_id="t1")
    repo = AsyncMock()
    repo.find_by_id = AsyncMock(return_value=session)
    repo.save = AsyncMock()
    sandbox = AsyncMock()
    sandbox_cls = MagicMock(get=AsyncMock(return_value=sandbox))

    service = build_domain_service(repo=repo, sandbox_cls=sandbox_cls)

    await service._teardown_session_runtime("s1")
    await service._teardown_session_runtime("s1")

    sandbox.destroy.assert_awaited_once()
    assert session.sandbox_id is None
    assert session.task_id is None
```

**Step 2: Run test to verify it fails**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_domain_service_session_sandbox_teardown.py -v`
Expected: FAIL because no centralized `_teardown_session_runtime()` exists and ownership fields are missing.

**Step 3: Write minimal implementation**

```python
# session.py
sandbox_owned: bool = False
sandbox_lifecycle_mode: str | None = None
sandbox_created_at: datetime | None = None
```

```python
# agent_domain_service.py
async def _teardown_session_runtime(self, session_id: str) -> None:
    session = await self._session_repository.find_by_id(session_id)
    if not session:
        return
    if session.sandbox_id and session.sandbox_owned:
        sandbox = await self._sandbox_cls.get(session.sandbox_id)
        if sandbox:
            await asyncio.wait_for(sandbox.destroy(), timeout=15.0)
    session.task_id = None
    session.sandbox_id = None
    session.sandbox_owned = False
    await self._session_repository.save(session)
```

```python
# create/bind points set ownership
session.sandbox_owned = settings.sandbox_lifecycle_mode == "ephemeral"
session.sandbox_lifecycle_mode = settings.sandbox_lifecycle_mode
```

**Step 4: Run test to verify it passes**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_domain_service_session_sandbox_teardown.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/domain/models/session.py backend/app/infrastructure/models/documents.py backend/app/domain/services/agent_domain_service.py backend/app/application/services/agent_service.py backend/tests/domain/services/test_agent_domain_service_session_sandbox_teardown.py
git commit -m "feat: add session sandbox ownership metadata and centralized runtime teardown"
```

---

### Task 4: Auto-Teardown on All Session Terminal Paths

**Files:**
- Modify: `backend/app/domain/services/agent_domain_service.py`
- Modify: `backend/app/application/services/agent_service.py`
- Modify: `backend/app/interfaces/api/session_routes.py`
- Create: `backend/tests/domain/services/test_agent_domain_service_chat_teardown.py`
- Modify: `backend/tests/domain/services/test_agent_domain_service_stop_session.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_chat_done_event_triggers_runtime_teardown_for_ephemeral_session():
    session = Session(id="s1", user_id="u1", agent_id="a1", status=SessionStatus.RUNNING, sandbox_id="sb-1", sandbox_owned=True)
    service = build_service_with_done_event(session)

    events = [event async for event in service.chat("s1", "u1", "hello")]
    assert any(e.type == "done" for e in events)
    service._teardown_session_runtime.assert_awaited_once_with("s1")
```

**Step 2: Run test to verify it fails**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_domain_service_chat_teardown.py -v`
Expected: FAIL because done/error/stop/delete/disconnect do not all route through one teardown helper.

**Step 3: Write minimal implementation**

```python
# agent_domain_service.py
# After DoneEvent/ErrorEvent or terminal status:
await self._teardown_session_runtime(session_id)
```

```python
# stop_session/delete_session
await self._teardown_session_runtime(session_id)
session.status = SessionStatus.COMPLETED
await self._session_repository.save(session)
```

```python
# session_routes.py disconnect handler
await agent_service.stop_session(session_id, current_user.id)
```

**Step 4: Run test to verify it passes**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_domain_service_chat_teardown.py tests/domain/services/test_agent_domain_service_stop_session.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/domain/services/agent_domain_service.py backend/app/application/services/agent_service.py backend/app/interfaces/api/session_routes.py backend/tests/domain/services/test_agent_domain_service_chat_teardown.py backend/tests/domain/services/test_agent_domain_service_stop_session.py
git commit -m "feat: route all session terminal paths through unified sandbox teardown"
```

---

### Task 5: Add Orphan Sandbox Cleanup and Dev Verification

**Files:**
- Modify: `backend/app/application/services/maintenance_service.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/application/services/test_maintenance_service_sandbox_cleanup.py`
- Modify: `MONITORING.md`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_cleanup_stale_running_sessions_destroys_ephemeral_sandbox_only():
    # stale session has sandbox_owned=True
    # static/shared session has sandbox_owned=False
    # expect only owned sandbox destroy call
```

**Step 2: Run test to verify it fails**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_maintenance_service_sandbox_cleanup.py -v`
Expected: FAIL because stale cleanup currently destroys by `sandbox_id` without ownership gating.

**Step 3: Write minimal implementation**

```python
# maintenance_service.py
if sandbox_id and session.get("sandbox_owned"):
    sandbox = await DockerSandbox.get(sandbox_id)
    await asyncio.wait_for(sandbox.destroy(), timeout=15.0)
```

```python
# main.py startup logs
logger.info("Sandbox lifecycle mode: %s", settings.sandbox_lifecycle_mode)
```

```md
# MONITORING.md add runbook
- verify ephemeral container appears when session starts
- verify container disappears on done/stop/delete
```

**Step 4: Run test to verify it passes**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_maintenance_service_sandbox_cleanup.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/application/services/maintenance_service.py backend/app/main.py backend/tests/application/services/test_maintenance_service_sandbox_cleanup.py MONITORING.md
git commit -m "feat: cleanup only owned ephemeral sandboxes and document monitoring checks"
```

---

### Task 6: End-to-End Dev Validation (No Coverage, Focus on Lifecycle)

**Files:**
- Modify: `docs/plans/2026-02-10-ephemeral-session-sandbox-lifecycle.md` (record validation evidence)

**Step 1: Run backend targeted tests**

Run:
`conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/core/test_sandbox_lifecycle_mode.py tests/infrastructure/external/sandbox/test_docker_sandbox_lifecycle_mode.py tests/domain/services/test_agent_domain_service_session_sandbox_teardown.py tests/domain/services/test_agent_domain_service_chat_teardown.py tests/application/services/test_maintenance_service_sandbox_cleanup.py -v`

Expected: PASS all.

**Step 2: Run backend quality checks**

Run:
`conda activate pythinker && cd backend && ruff check . && ruff format --check .`

Expected: PASS.

**Step 3: Start compose stack and run lifecycle smoke**

Run:
`docker compose -f docker-compose-development.yml up -d --build`

Then:
1. Create session via API/UI.
2. Send one message and wait for completion.
3. Confirm sandbox container count returns to baseline.

Expected: each session gets a new container and it is removed after terminal state.

**Step 4: Capture logs for evidence**

Run:
`docker compose -f docker-compose-development.yml logs --tail=300 backend | rg "sandbox lifecycle mode|Created sandbox|Destroyed sandbox|teardown"`

Expected: explicit create/bind/teardown lines per session id.

**Step 5: Commit validation notes**

```bash
git add docs/plans/2026-02-10-ephemeral-session-sandbox-lifecycle.md
git commit -m "docs: add validation evidence for ephemeral session sandbox lifecycle"
```

---

## Non-Goals (for this plan)

1. Re-architecting browser automation flows unrelated to sandbox ownership.
2. Removing static sandbox mode entirely.
3. Changing frontend UX beyond what is needed to surface session terminal state behavior.

