# Sandbox Daytona API Enhancement Report

**Report Date:** 2026-02-11  
**Status:** Research & Recommendations  
**Scope:** Pythinker sandbox enhancement using Daytona API as alternative or complementary provider

---

## Executive Summary

This report analyzes the Pythinker sandbox architecture, researches the Daytona API via Context7 documentation, and provides a comprehensive plan to enhance the sandbox by integrating Daytona. Daytona offers **cloud-hosted, elastic sandbox infrastructure** with Python/TypeScript SDKs, while Pythinker currently uses **self-hosted Docker containers** via `DockerSandbox`. The integration paths range from a **unified adapter** (supporting both Docker and Daytona) to a **full Daytona-only** mode for serverless/cloud deployment.

---

## 1. Current Pythinker Sandbox Architecture

### 1.1 Overview

| Component | Description |
|-----------|-------------|
| **Interface** | `Sandbox` Protocol (`backend/app/domain/external/sandbox.py`) |
| **Implementation** | `DockerSandbox` (`backend/app/infrastructure/external/sandbox/docker_sandbox.py`) |
| **Sandbox Service** | FastAPI app in `sandbox/` — Shell, File, Framework, Supervisor APIs on port 8080 |
| **Lifecycle** | `SandboxPool` with pre-warming, pause/unpause, idle TTL, circuit breaker |
| **Browser** | Chrome CDP (9222), Playwright, CDP screencast for live view, VNC fallback |

### 1.2 Sandbox Protocol Surface

The `Sandbox` Protocol defines these operations:

- **Lifecycle:** `ensure_sandbox`, `ensure_framework`, `destroy`, `pause`, `unpause`
- **Shell:** `exec_command`, `view_shell`, `wait_for_process`, `write_to_process`, `kill_process`
- **File:** `file_write`, `file_read`, `file_exists`, `file_delete`, `file_list`, `file_replace`, `file_search`, `file_find`, `file_upload`, `file_download`
- **Workspace:** `workspace_init`, `workspace_info`, `workspace_tree`, `workspace_clean`, `workspace_exists`
- **Git:** `git_clone`, `git_status`, `git_diff`, `git_log`, `git_branches`
- **Code:** `file_*`, `code_format`, `code_lint`, `code_analyze`, `code_search`
- **Test:** `test_run`, `test_list`, `test_coverage`
- **Export:** `export_organize`, `export_archive`, `export_report`, `export_list`
- **Browser:** `get_browser`, `get_screenshot`, `cdp_url`, `vnc_url`

### 1.3 Docker Flow

1. `DockerSandbox.create()` → `docker_client.containers.run()` with pythinker-sandbox image  
2. Container gets IP from Docker network; backend talks to `http://{ip}:8080/api/v1/*`  
3. CDP at `http://{ip}:9222`, VNC at `ws://{ip}:5901`  
4. SandboxPool pre-warms containers, optionally pauses idle ones

### 1.4 Existing Daytona Usage (system/pyth-open)

The `system/pyth-open` subproject already uses Daytona:

- **Config:** `config/config.example-daytona.toml` — `daytona_api_key`, `sandbox_image_name`, `daytona_target`, etc.
- **Sandbox:** `app/daytona/sandbox.py` — `create_sandbox()`, `get_or_start_sandbox()`, `delete_sandbox()`
- **Tools:** `sb_shell_tool.py`, `sb_files_tool.py`, `sb_browser_tool.py` via `SandboxToolsBase`

Daytona integration there is synchronous and separate from the main Pythinker backend.

---

## 2. Daytona API (Context7 Research Summary)

### 2.1 Overview

- **Library:** `daytona` (Python), `@daytonaio/sdk` (TypeScript)
- **Install:** `pip install daytona`
- **Docs:** [Daytona Python SDK](https://www.daytona.io/docs/)

Daytona provides:

- Secure, elastic sandbox infrastructure (cloud-hosted)
- Fast sandbox creation from snapshot or custom image
- Programmatic lifecycle (create, start, stop, archive, delete)
- File system APIs (upload, download, find)
- Process/session management (create session, execute command)

### 2.2 Creation Options

| Method | Use Case |
|--------|----------|
| `CreateSandboxFromSnapshotParams` | Pre-built Python/TypeScript/JS runtimes |
| `CreateSandboxFromImageParams` | Custom Docker images (e.g. browser-use) |

**From image example (Context7):**

```python
from daytona import Daytona, CreateSandboxFromImageParams, Resources

params = CreateSandboxFromImageParams(
    image="debian:12.9",
    env_vars={"DEBUG": "true"},
    resources=Resources(cpu=2, memory=4),
    auto_stop_interval=60,
    auto_archive_interval=60,
    auto_delete_interval=120,
)
sandbox = daytona.create(params)
```

**From custom image (pyth-open pattern):**

```python
params = CreateSandboxFromImageParams(
    image="whitezxj/sandbox:0.1.0",
    public=True,
    env_vars={
        "CHROME_PERSISTENT_SESSION": "true",
        "CHROME_DEBUGGING_PORT": "9222",
        "VNC_PASSWORD": password,
        ...
    },
    resources=Resources(cpu=2, memory=4, disk=5),
    auto_stop_interval=15,
    auto_archive_interval=24 * 60,
)
sandbox = daytona.create(params)
```

### 2.3 Async Python SDK

```python
from daytona import AsyncDaytona

async with AsyncDaytona() as daytona:
    sandbox = await daytona.create()
    response = await sandbox.process.exec("echo 'Hello, World!'")
    print(response.result)
```

### 2.4 File System

```python
# Upload
sandbox.fs.upload_file(b'Hello, World!', 'path/to/file.txt')

# Download
content = sandbox.fs.download_file('path/to/file.txt')

# Search
matches = sandbox.fs.find_files(root_dir, 'search_pattern')
```

### 2.5 Process & Sessions

```python
# Create session (maintains state)
session_id = "my-session"
sandbox.process.create_session(session_id)

# Execute command (sync or async)
req = SessionExecuteRequest(command="cd /workspace", run_async=False)
result = sandbox.process.execute_session_command(session_id, req)
# result.stdout, result.stderr, result.exit_code
```

### 2.6 Preview Link (VNC/Browser Access)

```python
preview_link = sandbox.get_preview_link(3000)  # or 6080 for VNC, 8080 for app
print(preview_link.url)
print(preview_link.token)  # for private sandboxes
```

### 2.7 Lifecycle

```python
sandbox.stop()
sandbox.start()
sandbox.archive()
daytona.delete(sandbox)

# Auto-lifecycle
sandbox.set_autostop_interval(0)
sandbox.set_auto_archive_interval(60)
sandbox.set_auto_delete_interval(120)
```

---

## 3. Gap Analysis: Pythinker vs Daytona

### 3.1 API Mapping

| Pythinker Sandbox | Daytona Equivalent | Notes |
|-------------------|-------------------|-------|
| `ensure_sandbox` | Poll `sandbox.state` / CDP health | Daytona has no supervisor; need custom health logic |
| `exec_command` | `sandbox.process.execute_session_command()` | Direct mapping |
| `view_shell` | Session output / stdout from last command | Different model; may need session logs |
| `file_write` | `sandbox.fs.upload_file()` | Bytes vs string; trivial conversion |
| `file_read` | `sandbox.fs.download_file()` | Direct mapping |
| `file_exists`, `file_list`, `file_find` | `sandbox.fs.find_files()` | Partial; may need custom logic |
| `get_browser` | CDP via `get_preview_link(9222)` or internal CDP URL | Daytona exposes ports via preview links |
| `get_screenshot` | CDP screencast or VNC | Same as Docker if image has Chrome+VNC |
| `cdp_url`, `vnc_url` | `get_preview_link(9222)`, `get_preview_link(6080)` | URLs are public/preview-style |
| `destroy` | `daytona.delete(sandbox)` | Direct mapping |
| `pause` / `unpause` | `sandbox.stop()` / `sandbox.start()` | Conceptual match; archive for long-term pause |

### 3.2 Missing or Different

| Capability | Issue |
|------------|-------|
| **Sandbox API (8080)** | Pythinker expects a FastAPI service (shell, file, framework) in the container. Daytona sandboxes run arbitrary images; if the image has that API, it works. Otherwise, we must use Daytona’s `fs` and `process` APIs. |
| **Framework bootstrap** | `ensure_framework` posts to `/api/v1/framework/bootstrap`. Requires the sandbox image to run this service. |
| **Workspace / Git / Code / Test / Export** | Implemented via sandbox HTTP API. Must be reimplemented using Daytona `fs` + `process` or by ensuring the Daytona image runs the same services. |
| **Pooling** | Daytona is cloud-based; no local Docker to pause. Use `stop`/`start` and consider `archive` for cost savings. |
| **HTTP Client Pooling** | Daytona preview URLs are external; reuse HTTP clients by base URL (same as current pool). |
| **Circuit Breaker** | Still applicable for Daytona API failures. |
| **Orphan Reaper** | Daytona-managed; list/delete via SDK instead of Docker API. |

### 3.3 CDP / VNC / Screencast

If the Daytona image (e.g. `whitezxj/sandbox:0.1.0`) includes:

- Chrome with CDP on 9222
- VNC/WebSocket on 5901 or 6080
- The same supervisor + FastAPI stack as `pythinker-sandbox`

then CDP, VNC, and screencast can work through Daytona’s `get_preview_link()` URLs. The main difference is that URLs are public/daytona.io domains instead of container IPs.

---

## 4. Recommended Architecture

### 4.1 Strategy: Adapter Pattern

Introduce a `DaytonaSandbox` implementation of the `Sandbox` protocol that:

1. Uses `AsyncDaytona` for create/destroy/lifecycle  
2. Maps Pythinker calls to Daytona `fs` and `process` APIs where possible  
3. For capabilities not in Daytona (e.g. framework bootstrap, workspace), either:
   - Use a compatible image that runs the same FastAPI services and call them via `get_preview_link(8080)`, or  
   - Implement a compatibility layer in `DaytonaSandbox` using `fs` + `process`

### 4.2 Configuration

Add to `backend/app/core/config.py`:

```python
# Sandbox provider: "docker" | "daytona"
sandbox_provider: str = "docker"

# Daytona (when sandbox_provider="daytona")
daytona_api_key: str | None = None
daytona_server_url: str = "https://app.daytona.io/api"
daytona_target: str = "us"
daytona_sandbox_image: str = "whitezxj/sandbox:0.1.0"  # or pythinker-compatible image
daytona_vnc_password: str = "123456"
```

### 4.3 Class Diagram

```
Sandbox (Protocol)
       ^
       |
   +---+---+
   |       |
DockerSandbox   DaytonaSandbox
   |               |
   +-------+-------+
           |
   SandboxPool / AgentService
   (inject Sandbox implementation)
```

### 4.4 DaytonaSandbox Implementation Outline

```python
# backend/app/infrastructure/external/sandbox/daytona_sandbox.py

from daytona import (
    AsyncDaytona,
    DaytonaConfig,
    CreateSandboxFromImageParams,
    Resources,
    SessionExecuteRequest,
)

class DaytonaSandbox(Sandbox):
    def __init__(self, daytona_sandbox, daytona_client: AsyncDaytona):
        self._sandbox = daytona_sandbox
        self._daytona = daytona_client
        self._base_url = None  # Resolved from get_preview_link(8080) when image has API
        self._cdp_url = None   # get_preview_link(9222)
        self._vnc_url = None   # get_preview_link(6080)
        self._session_id: str | None = None

    @property
    def id(self) -> str:
        return self._sandbox.id

    @property
    def cdp_url(self) -> str:
        return self._cdp_url or self._resolve_preview_url(9222)

    @property
    def vnc_url(self) -> str:
        return self._vnc_url or self._resolve_preview_url(6080)

    async def ensure_sandbox(self) -> None:
        # Check sandbox.state, optionally start if STOPPED/ARCHIVED
        # If image has API: GET base_url/health and retry
        # Verify CDP if browser needed
        ...

    async def exec_command(self, session_id: str, exec_dir: str, command: str) -> ToolResult:
        if not self._session_id:
            self._sandbox.process.create_session(session_id)
            self._session_id = session_id
        cmd = f"cd {exec_dir} && {command}" if exec_dir else command
        result = self._sandbox.process.execute_session_command(
            session_id, SessionExecuteRequest(command=cmd, run_async=False)
        )
        return ToolResult(success=result.exit_code == 0, data={"output": result.stdout, ...})

    async def file_write(self, file: str, content: str, ...) -> ToolResult:
        self._sandbox.fs.upload_file(content.encode("utf-8"), file)
        return ToolResult(success=True, ...)

    async def file_read(self, file: str, ...) -> ToolResult:
        data = self._sandbox.fs.download_file(file)
        return ToolResult(success=True, data={"content": data.decode("utf-8")})

    async def destroy(self) -> bool:
        self._daytona.delete(self._sandbox)
        return True

    @classmethod
    async def create(cls) -> Sandbox:
        config = get_daytona_config()
        async with AsyncDaytona(config) as daytona:
            params = CreateSandboxFromImageParams(
                image=config.sandbox_image,
                env_vars={"VNC_PASSWORD": config.vnc_password, "CHROME_DEBUGGING_PORT": "9222", ...},
                resources=Resources(cpu=2, memory=4, disk=5),
                auto_stop_interval=15,
                auto_archive_interval=24 * 60,
            )
            sandbox = await daytona.create(params)
            # Keep daytona client in sandbox for later operations (or use global client)
            return cls(sandbox, daytona)
```

### 4.5 Dependency Injection

In `dependencies.py` or similar:

```python
def get_sandbox_cls() -> type[Sandbox]:
    settings = get_settings()
    if settings.sandbox_provider == "daytona":
        return DaytonaSandbox
    return DockerSandbox
```

`AgentService` and `SandboxPool` use `get_sandbox_cls()` instead of hardcoding `DockerSandbox`.

### 4.6 SandboxPool and Daytona

For Daytona:

- **Pre-warming:** Create sandboxes via API and keep them running (avoid `stop` if latency matters)
- **Pause:** Use `sandbox.stop()`; `unpause` = `sandbox.start()`
- **Eviction:** Call `daytona.delete(sandbox)` for evicted instances
- **Orphan reaper:** Query Daytona for sandboxes by label (e.g. `pythinker`) and delete those not in pool or active sessions
- **Image pre-pull:** N/A (cloud images)
- **Circuit breaker:** Same pattern for API failures

---

## 5. Implementation Phases

### Phase 1: Config & Daytona Client (1–2 days)

- Add `sandbox_provider`, `daytona_api_key`, `daytona_server_url`, `daytona_target`, `daytona_sandbox_image`, `daytona_vnc_password` to config  
- Add `daytona` to `pyproject.toml`  
- Create `get_daytona_config()` and a shared `AsyncDaytona` client (or context manager)

### Phase 2: DaytonaSandbox Skeleton (2–3 days)

- Implement `DaytonaSandbox` with `create`, `destroy`, `id`, `cdp_url`, `vnc_url`  
- Implement `ensure_sandbox` (state + optional health check)  
- Implement `exec_command`, `file_write`, `file_read` using Daytona APIs

### Phase 3: Full Protocol Coverage (3–5 days)

- Implement remaining file operations (`file_exists`, `file_list`, `file_find`, etc.) via `fs` or shell commands  
- Implement workspace/git/code/test/export using either:
  - HTTP to sandbox API if image has it, or  
  - `process` + `fs`  
- Implement `get_browser` using CDP URL from `get_preview_link(9222)`  
- Implement `get_screenshot`, `pause`, `unpause`

### Phase 4: Pool & Lifecycle (1–2 days)

- Adapt `SandboxPool` for Daytona (create, stop, start, delete, eviction, circuit breaker)  
- Implement Daytona-specific orphan reaper (list by label, compare with pool + active sessions)

### Phase 5: Testing & Docs (2–3 days)

- Unit tests for `DaytonaSandbox` (mocked Daytona client)  
- Integration tests with real Daytona account (optional, CI with credentials)  
- Update `AGENTS.md`, `CLAUDE.md`, architecture docs

---

## 6. Migration Path

| Mode | Use Case |
|------|----------|
| `sandbox_provider=docker` | Current behavior (local Docker) |
| `sandbox_provider=daytona` | Cloud sandboxes (e.g. serverless, no Docker) |
| Future: `sandbox_provider=auto` | Prefer Daytona when Docker unavailable |

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Daytona API rate limits | Circuit breaker, backoff, consider premium plan |
| Preview URL latency | Cache preview URLs; use same base URL for HTTP pool |
| Image compatibility | Pin a pythinker-compatible image; document env vars |
| Cost | Use `auto_stop_interval`, `auto_archive_interval`; monitor usage |
| Async client lifecycle | Use context manager or singleton; ensure cleanup on shutdown |

---

## 8. References

- **Pythinker Sandbox Protocol:** `backend/app/domain/external/sandbox.py`
- **DockerSandbox:** `backend/app/infrastructure/external/sandbox/docker_sandbox.py`
- **SandboxPool:** `backend/app/core/sandbox_pool.py`
- **pyth-open Daytona:** `system/pyth-open/app/daytona/`, `config/config.example-daytona.toml`
- **Daytona Docs:** [https://www.daytona.io/docs/](https://www.daytona.io/docs/)
- **Context7 Library:** `/daytonaio/daytona`

---

## 9. Appendix: Daytona SDK Quick Reference

```python
# Install
# pip install daytona

# Sync
from daytona import Daytona, CreateSandboxFromImageParams, Resources
daytona = Daytona()
sandbox = daytona.create(CreateSandboxFromImageParams(image="debian:12.9"))

# Async
from daytona import AsyncDaytona
async with AsyncDaytona() as daytona:
    sandbox = await daytona.create()

# File ops
sandbox.fs.upload_file(b"content", "path.txt")
content = sandbox.fs.download_file("path.txt")
matches = sandbox.fs.find_files("/", "*.py")

# Process
sandbox.process.create_session("sid")
sandbox.process.execute_session_command("sid", SessionExecuteRequest(command="ls", run_async=False))

# Preview
link = sandbox.get_preview_link(8080)

# Lifecycle
sandbox.stop()
sandbox.start()
sandbox.archive()
daytona.delete(sandbox)
```
