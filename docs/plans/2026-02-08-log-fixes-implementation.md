# Log Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate the logged errors and reduce noisy warnings across frontend, backend, sandbox, and Redis without changing core behavior.

**Architecture:** Introduce a JSON schema sanitizer for non-OpenAI endpoints, move sandbox progress artifacts to a writable path, and tune sandbox/Redis configs to prevent runtime warnings. Add focused regression tests where code changes occur.

**Tech Stack:** Python 3.11/3.12, FastAPI, Pydantic v2, pytest, Vite/Vitest, Docker Compose, Redis, Chromium in sandbox.

---

### Task 1: Add JSON Schema Sanitizer (Moonshot Compatibility)

**Files:**
- Create: `backend/app/domain/models/json_schema.py`
- Create: `backend/tests/domain/models/test_json_schema.py`
- Modify: `backend/app/infrastructure/external/llm/openai_llm.py`

**Step 1: Write the failing test**

```python
from app.domain.models.json_schema import sanitize_json_schema

def test_sanitize_removes_default_with_anyof():
    schema = {
        "type": "object",
        "properties": {
            "foo": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
            },
            "bar": {"type": "string", "default": "ok"},
        },
    }

    sanitized = sanitize_json_schema(schema)

    assert "default" not in sanitized["properties"]["foo"]
    assert sanitized["properties"]["bar"]["default"] == "ok"
```

**Step 2: Run test to verify it fails**

Run: `set -a && source .env && set +a && cd backend && pytest -p no:cov -o addopts= tests/domain/models/test_json_schema.py -q`  
Expected: FAIL (module/function missing).

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

from typing import Any


def sanitize_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove invalid 'default' when combined with anyOf/oneOf at same level."""
    def _sanitize(node: Any) -> Any:
        if isinstance(node, dict):
            sanitized = {k: _sanitize(v) for k, v in node.items()}
            if ("anyOf" in sanitized or "oneOf" in sanitized) and "default" in sanitized:
                sanitized.pop("default", None)
            return sanitized
        if isinstance(node, list):
            return [_sanitize(item) for item in node]
        return node

    return _sanitize(schema)
```

Update `backend/app/infrastructure/external/llm/openai_llm.py` to apply sanitizer before setting `response_format` when using non-OpenAI base URLs:

```python
from app.domain.models.json_schema import sanitize_json_schema

# ...
schema = response_model.model_json_schema()
if self._api_base and not self._is_official_openai_base():
    schema = sanitize_json_schema(schema)
```

**Step 4: Run test to verify it passes**

Run: `set -a && source .env && set +a && cd backend && pytest -p no:cov -o addopts= tests/domain/models/test_json_schema.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/domain/models/json_schema.py backend/tests/domain/models/test_json_schema.py backend/app/infrastructure/external/llm/openai_llm.py
git commit -m "fix: sanitize json schema for non-openai endpoints"
```

---

### Task 2: Fix PlanAct Progress Artifact Path

**Files:**
- Create: `backend/tests/domain/services/flows/test_plan_act_progress_artifact.py`
- Modify: `backend/app/domain/services/flows/plan_act.py`

**Step 1: Write the failing test**

```python
import pytest
from app.domain.models.plan import Plan, Step
from app.domain.models.event import ExecutionStatus


@pytest.mark.asyncio
async def test_progress_artifact_path_uses_home_ubuntu(
    mock_llm,
    mock_sandbox,
    mock_browser,
    mock_json_parser,
    mock_mcp_tool,
    mock_repositories,
    monkeypatch,
):
    monkeypatch.setenv("API_KEY", "test-key")
    from app.domain.services.flows.plan_act import PlanActFlow

    agent_repo, session_repo = mock_repositories
    flow = PlanActFlow(
        agent_id="test_agent",
        agent_repository=agent_repo,
        session_id="test_session",
        session_repository=session_repo,
        llm=mock_llm,
        sandbox=mock_sandbox,
        browser=mock_browser,
        json_parser=mock_json_parser,
        mcp_tool=mock_mcp_tool,
    )

    flow.plan = Plan(
        steps=[Step(description="done", status=ExecutionStatus.COMPLETED, result="ok")]
    )

    await flow._save_progress_artifact()

    mock_sandbox.file_write.assert_called_once()
    args, kwargs = mock_sandbox.file_write.call_args
    assert kwargs["file"] == "/home/ubuntu/.agent_progress.json"
```

**Step 2: Run test to verify it fails**

Run: `set -a && source .env && set +a && cd backend && pytest -p no:cov -o addopts= tests/domain/services/flows/test_plan_act_progress_artifact.py -q`  
Expected: FAIL (path currently `/home/user/...`).

**Step 3: Write minimal implementation**

Change both save and read paths in `backend/app/domain/services/flows/plan_act.py`:

```python
file="/home/ubuntu/.agent_progress.json"
```

**Step 4: Run test to verify it passes**

Run: `set -a && source .env && set +a && cd backend && pytest -p no:cov -o addopts= tests/domain/services/flows/test_plan_act_progress_artifact.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py backend/tests/domain/services/flows/test_plan_act_progress_artifact.py
git commit -m "fix: write progress artifact to /home/ubuntu"
```

---

### Task 3: Reduce Sandbox Runtime Warnings

**Files:**
- Modify: `sandbox/fix-permissions.sh`
- Modify: `sandbox/supervisord.conf`
- Modify: `sandbox/requirements.txt`

**Step 1: Implement config changes**

Update `sandbox/fix-permissions.sh` to create `/tmp/.X11-unix` and `/run/dbus` with correct permissions.

Add a new `[program:dbus]` section in `sandbox/supervisord.conf`:

```ini
[program:dbus]
command=/usr/bin/dbus-daemon --system --nofork --nopidfile
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stderr_logfile=/dev/stderr
user=root
priority=2
```

Update the Chrome command to include:
- `--disable-vulkan`
- `--disable-features=GCMChannelStatusRequest,UseGCMChannel,OnDeviceModelService,OnDeviceModelDownload`

And set env on the chrome program:

```ini
environment=DISPLAY=:1,HOME=/home/ubuntu,DBUS_SESSION_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket,DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket
```

Add numpy to `sandbox/requirements.txt`:

```
numpy>=1.26
```

**Step 2: Verify locally (manual)**

Rebuild/restart sandbox containers and confirm logs no longer show DBus/X11/Vulkan/numpy warnings:

```bash
docker compose -f docker-compose-development.yml up -d --build sandbox sandbox2
docker logs --tail 200 pyth-main-sandbox-1 | rg -i "dbus|vulkan|on_device_model|numpy|X11"
```

**Step 3: Commit**

```bash
git add sandbox/fix-permissions.sh sandbox/supervisord.conf sandbox/requirements.txt
git commit -m "chore: reduce sandbox chrome/dbus noise"
```

---

### Task 4: Add Redis Config to Silence Warning

**Files:**
- Create: `redis/redis.conf`
- Modify: `docker-compose.yml`
- Modify: `docker-compose-development.yml`

**Step 1: Implement config**

Create `redis/redis.conf`:

```
bind 0.0.0.0 ::
protected-mode no
```

Update both compose files to mount the config and use it:

```yaml
redis:
  image: redis:7.0
  command: ["redis-server", "/usr/local/etc/redis/redis.conf"]
  volumes:
    - ./redis/redis.conf:/usr/local/etc/redis/redis.conf:ro
```

**Step 2: Verify locally (manual)**

```bash
docker compose -f docker-compose-development.yml up -d --build redis
docker logs --tail 100 pyth-main-redis-1 | rg -i "config file"
```

**Step 3: Commit**

```bash
git add redis/redis.conf docker-compose.yml docker-compose-development.yml
git commit -m "chore: add redis config file"
```

---

### Task 5: Frontend Regression Guard (Optional if build already clean)

**Files:**
- Create: `frontend/tests/pages/CanvasPage.spec.ts`

**Step 1: Add guard test**

```ts
import { describe, it, expect } from 'vitest';
import CanvasPage from '@/pages/CanvasPage.vue';

describe('CanvasPage', () => {
  it('imports successfully', () => {
    expect(CanvasPage).toBeTruthy();
  });
});
```

**Step 2: Run test**

Run: `cd frontend && bun run test:run -- tests/pages/CanvasPage.spec.ts`  
Expected: PASS.

**Step 3: Commit**

```bash
git add frontend/tests/pages/CanvasPage.spec.ts
git commit -m "test: add CanvasPage import guard"
```

---

### Task 6: Final Verification

**Step 1: Backend tests**

Run:

```bash
set -a && source .env && set +a
cd backend
pytest -p no:cov -o addopts= tests/domain/models/test_json_schema.py tests/domain/services/flows/test_plan_act_progress_artifact.py -q
```

**Step 2: Frontend tests (if added)**

Run: `cd frontend && bun run test:run -- tests/pages/CanvasPage.spec.ts`

**Step 3: Container log check**

```bash
docker logs --tail 200 pyth-main-backend-1 | rg -i "response_format|json_schema|moonshot"
docker logs --tail 200 pyth-main-sandbox-1 | rg -i "dbus|vulkan|on_device_model|numpy|X11"
docker logs --tail 200 pyth-main-redis-1 | rg -i "config file"
```

---

Plan complete and saved to `docs/plans/2026-02-08-log-fixes-implementation.md`.

Two execution options:

1. Subagent-Driven (this session) — I dispatch a fresh subagent per task, review between tasks.
2. Parallel Session (separate) — Open a new session using `executing-plans`, batch execution with checkpoints.

Which approach do you want?
