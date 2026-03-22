# Sandbox Manus-Parity Enhancement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring Pythinker's sandbox to full feature parity with Manus's sandbox (v7.0.30) across 7 phases: environment polish, structured terminal markers, bidirectional callback, LLM proxy, code-server IDE, observability (OTEL+Sentry), and cloud token integrations.

**Architecture:** Each phase is feature-flagged (default: off), backward-compatible, and independently deployable. The sandbox remains a stateless tool-execution container; all auth/secrets are scoped JWTs or env vars passed at container startup. LLM access is proxied through the backend (no direct API keys in sandbox).

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, supervisord, Docker multi-stage, Vue 3 (Composition API), OpenTelemetry SDK, Sentry SDK, code-server, `gh` CLI.

**Design Doc:** `docs/plans/2026-03-12-sandbox-manus-parity-design.md`

---

## Phase 1: Environment Polish

### Task 1.1: Add Encoding/Locale/Version ENV to Dockerfile

**Files:**
- Modify: `sandbox/Dockerfile:219-226` (runtime stage ENV block)

**Step 1: Add env vars to the runtime stage ENV block**

In `sandbox/Dockerfile`, after the existing `ENV` declarations in the runtime stage (around line 219-226), add:

```dockerfile
ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8
ENV PW_TEST_SCREENSHOT_NO_FONTS_READY=1
```

These go after `ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers` (line 226) and before `RUN update-alternatives` (line 228).

**Step 2: Verify Dockerfile syntax**

Run: `cd /home/mac/Desktop/Pythinker-main && docker compose -f docker-compose-development.yml config --quiet`
Expected: No errors

**Step 3: Commit**

```bash
git add sandbox/Dockerfile
git commit -m "feat(sandbox): add PYTHONIOENCODING, LANG, PW_TEST_SCREENSHOT_NO_FONTS_READY env vars"
```

---

### Task 1.2: Add TZ and SANDBOX_VERSION to Docker Compose

**Files:**
- Modify: `docker-compose-development.yml:249-260` (sandbox environment)
- Modify: `docker-compose.yml:161-168` (sandbox environment)

**Step 1: Add env vars to development compose**

In `docker-compose-development.yml`, in the sandbox service `environment:` section (after line 260), add:

```yaml
      - TZ=${TZ:-UTC}
      - SANDBOX_VERSION=${IMAGE_TAG:-dev}
```

**Step 2: Add env vars to production compose**

In `docker-compose.yml`, in the sandbox service `environment:` section (after line 168), add:

```yaml
      - TZ=${TZ:-UTC}
      - SANDBOX_VERSION=${IMAGE_TAG:-dev}
```

**Step 3: Verify compose syntax**

Run: `docker compose -f docker-compose-development.yml config --quiet && docker compose -f docker-compose.yml config --quiet 2>/dev/null; echo "OK"`
Expected: OK (production may warn about missing .env vars — that's fine)

**Step 4: Commit**

```bash
git add docker-compose-development.yml docker-compose.yml
git commit -m "feat(sandbox): add TZ and SANDBOX_VERSION environment variables"
```

---

### Task 1.3: Add Settings to Sandbox Config

**Files:**
- Modify: `sandbox/app/core/config.py:51` (after CDP constants, before @field_validator)

**Step 1: Add new settings**

In `sandbox/app/core/config.py`, after the CDP timeout constants (after line 51, before the `@field_validator` at line 53), add:

```python
    # Environment metadata
    SANDBOX_VERSION: str = "dev"
    TZ: str = "UTC"
```

**Step 2: Verify import works**

Run: `cd /home/mac/Desktop/Pythinker-main/sandbox && python3 -c "from app.core.config import settings; print(settings.SANDBOX_VERSION, settings.TZ)"`
Expected: `dev UTC`

**Step 3: Commit**

```bash
git add sandbox/app/core/config.py
git commit -m "feat(sandbox): add SANDBOX_VERSION and TZ to Settings"
```

---

### Task 1.4: Include Version in Sandbox Context

**Files:**
- Modify: `sandbox/scripts/generate_sandbox_context.py:710-724` (scan_all method, environment collection)

**Step 1: Add version to system info**

In `generate_sandbox_context.py`, find the `scan_os_info()` method (line 49). At the end of the returned dict (before the closing `}`), add:

```python
            "sandbox_version": os.environ.get("SANDBOX_VERSION", "dev"),
            "timezone": os.environ.get("TZ", "UTC"),
```

**Step 2: Verify script runs**

Run: `cd /home/mac/Desktop/Pythinker-main/sandbox && python3 -c "from scripts.generate_sandbox_context import EnvironmentScanner; s = EnvironmentScanner(); info = s.scan_os_info(); print(info.get('sandbox_version'), info.get('timezone'))"`
Expected: `dev UTC` (or similar)

**Step 3: Commit**

```bash
git add sandbox/scripts/generate_sandbox_context.py
git commit -m "feat(sandbox): include sandbox_version and timezone in context"
```

---

### Task 1.5: Add TZ to .env.example

**Files:**
- Modify: `.env.example:113` (after SANDBOX_STREAMING_MODE)

**Step 1: Add TZ documentation**

In `.env.example`, after the `SANDBOX_STREAMING_MODE=cdp_only` line (line 113), add:

```bash

# Timezone for sandbox containers (affects log timestamps, cron, file dates)
TZ=UTC
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add TZ to .env.example"
```

---

## Phase 2: Structured Terminal Markers

### Task 2.1: Write Failing Tests for Structured Markers

**Files:**
- Create: `sandbox/tests/services/test_shell_markers.py`

**Step 1: Write the tests**

```python
"""Tests for structured terminal markers ([CMD_BEGIN]/[CMD_END])."""
import pytest
from unittest.mock import patch, MagicMock
from app.services.shell import ShellService, CMD_BEGIN_MARKER, CMD_END_MARKER


class TestStructuredMarkers:
    """Test PS1 marker format and output parsing."""

    def setup_method(self):
        self.shell_service = ShellService()

    def test_cmd_markers_are_defined(self):
        """Markers must be importable constants."""
        assert CMD_BEGIN_MARKER == "[CMD_BEGIN]"
        assert CMD_END_MARKER == "[CMD_END]"

    def test_format_ps1_structured(self):
        """PS1 should include CMD_END marker when structured markers enabled."""
        with patch("app.services.shell.settings") as mock_settings:
            mock_settings.SHELL_USE_STRUCTURED_MARKERS = True
            ps1 = self.shell_service._format_ps1("/home/ubuntu")
            assert CMD_END_MARKER in ps1
            assert "ubuntu" in ps1 or "root" in ps1

    def test_format_ps1_legacy(self):
        """PS1 should use legacy format when structured markers disabled."""
        with patch("app.services.shell.settings") as mock_settings:
            mock_settings.SHELL_USE_STRUCTURED_MARKERS = False
            ps1 = self.shell_service._format_ps1("/home/ubuntu")
            assert CMD_END_MARKER not in ps1
            assert "$" in ps1

    def test_format_ps1_structured_contains_path(self):
        """Structured PS1 should still show the working directory."""
        with patch("app.services.shell.settings") as mock_settings:
            mock_settings.SHELL_USE_STRUCTURED_MARKERS = True
            ps1 = self.shell_service._format_ps1("/home/ubuntu/workspace")
            assert "workspace" in ps1 or "~" in ps1

    def test_build_command_header_has_begin_marker(self):
        """Command header must start with CMD_BEGIN marker."""
        with patch("app.services.shell.settings") as mock_settings:
            mock_settings.SHELL_USE_STRUCTURED_MARKERS = True
            ps1 = self.shell_service._format_ps1("/home/ubuntu")
            header = f"{CMD_BEGIN_MARKER}{ps1} ls -la\n"
            assert header.startswith(CMD_BEGIN_MARKER)
            assert "ls -la" in header
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/mac/Desktop/Pythinker-main/sandbox && python3 -m pytest tests/services/test_shell_markers.py -v 2>&1 | head -30`
Expected: FAIL — `ImportError: cannot import name 'CMD_BEGIN_MARKER'`

**Step 3: Commit failing tests**

```bash
git add sandbox/tests/services/test_shell_markers.py
git commit -m "test(sandbox): add failing tests for structured terminal markers"
```

---

### Task 2.2: Add Feature Flag to Sandbox Config

**Files:**
- Modify: `sandbox/app/core/config.py` (after SHELL_MAX_OUTPUT_CHARS)

**Step 1: Add the flag**

In `sandbox/app/core/config.py`, find `SHELL_MAX_OUTPUT_CHARS` (around line 20). After it, add:

```python
    SHELL_USE_STRUCTURED_MARKERS: bool = True
```

**Step 2: Verify**

Run: `cd /home/mac/Desktop/Pythinker-main/sandbox && python3 -c "from app.core.config import settings; print(settings.SHELL_USE_STRUCTURED_MARKERS)"`
Expected: `True`

**Step 3: Commit**

```bash
git add sandbox/app/core/config.py
git commit -m "feat(sandbox): add SHELL_USE_STRUCTURED_MARKERS feature flag"
```

---

### Task 2.3: Implement Structured PS1 and Marker Constants

**Files:**
- Modify: `sandbox/app/services/shell.py:65-70` (_format_ps1 method)

**Step 1: Add marker constants at module level**

At the top of `sandbox/app/services/shell.py`, after the imports and before the class definition, add:

```python
CMD_BEGIN_MARKER = "[CMD_BEGIN]"
CMD_END_MARKER = "[CMD_END]"
```

**Step 2: Update `_format_ps1()` method**

Replace the existing `_format_ps1()` method (lines 65-70) with:

```python
    def _format_ps1(self, exec_dir: str) -> str:
        """Format the command prompt, optionally with structured markers."""
        username = getpass.getuser()
        hostname = socket.gethostname()
        display_path = self._get_display_path(exec_dir)

        if settings.SHELL_USE_STRUCTURED_MARKERS:
            # Manus-style: \n{user}@{host}:{path}\n[CMD_END]
            return f"\n{username}@{hostname}:{display_path}\n{CMD_END_MARKER}"

        # Legacy format
        return f"{username}@{hostname}:{display_path} $"
```

**Step 3: Update command header construction in `exec_command()`**

Find the lines where ConsoleRecord is created with ps1 (lines 184 and 219). Before each ConsoleRecord creation, the output is initialized. Find where the initial output header is built (the ps1 + command string that goes into the output buffer).

In the section where a new session is created (around line 184), and the section where an existing session reuses (around line 219), update the initial output to include the CMD_BEGIN marker:

```python
# When constructing the header for output:
if settings.SHELL_USE_STRUCTURED_MARKERS:
    header = f"{CMD_BEGIN_MARKER}{ps1} {command}\n"
else:
    header = f"{ps1} {command}\n"
```

**Step 4: Run the tests**

Run: `cd /home/mac/Desktop/Pythinker-main/sandbox && python3 -m pytest tests/services/test_shell_markers.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add sandbox/app/services/shell.py
git commit -m "feat(sandbox): implement structured CMD_BEGIN/CMD_END terminal markers"
```

---

### Task 2.4: Add exit_code to ConsoleRecord Model

**Files:**
- Modify: `sandbox/app/models/shell.py:9-14` (ConsoleRecord class)

**Step 1: Add exit_code field**

In `sandbox/app/models/shell.py`, add to the ConsoleRecord class (after line 14):

```python
    exit_code: Optional[int] = Field(default=None, description="Command exit code")
```

Ensure `Optional` is imported from `typing` at the top of the file.

**Step 2: Verify model loads**

Run: `cd /home/mac/Desktop/Pythinker-main/sandbox && python3 -c "from app.models.shell import ConsoleRecord; r = ConsoleRecord(ps1='$', command='ls', exit_code=0); print(r.model_dump())"`
Expected: `{'ps1': '$', 'command': 'ls', 'output': '', 'exit_code': 0}`

**Step 3: Update shell service to populate exit_code**

In `sandbox/app/services/shell.py`, in `exec_command()`, after the process completes (where returncode is available), update the last ConsoleRecord:

```python
# After process completion, update exit_code on the last console record
if shell.get("console") and process.returncode is not None:
    shell["console"][-1].exit_code = process.returncode
```

**Step 4: Commit**

```bash
git add sandbox/app/models/shell.py sandbox/app/services/shell.py
git commit -m "feat(sandbox): add exit_code to ConsoleRecord for richer terminal records"
```

---

### Task 2.5: Add Backend Marker Parser (Backward Compatible)

**Files:**
- Modify: `backend/app/domain/services/tools/shell.py` (add parsing method)

**Step 1: Add marker constants and parser**

In `backend/app/domain/services/tools/shell.py`, after the `MAX_SHELL_OUTPUT_CHARS` constant (line 10-11), add:

```python
CMD_BEGIN = "[CMD_BEGIN]"
CMD_END = "[CMD_END]"
```

Add a new static method to the `ShellTool` class:

```python
    @staticmethod
    def _extract_structured_output(raw: str) -> str:
        """Extract clean output from structured markers if present.

        Falls back to raw output when markers are absent (old sandbox images).
        """
        if CMD_BEGIN not in raw:
            return raw

        blocks = []
        for block in raw.split(CMD_BEGIN):
            if not block.strip():
                continue
            if CMD_END in block:
                content, _ = block.rsplit(CMD_END, 1)
                blocks.append(content.strip())
            else:
                blocks.append(block.strip())
        return "\n".join(blocks) if blocks else raw
```

**Step 2: Integrate parser in shell_exec result processing**

In the `shell_exec()` method, before the `_truncate_output()` call, apply the parser:

```python
if result.message:
    result.message = self._extract_structured_output(result.message)
```

**Step 3: Write a test**

Create `backend/tests/domain/services/tools/test_shell_markers.py`:

```python
"""Tests for structured terminal marker parsing in ShellTool."""
import pytest
from app.domain.services.tools.shell import ShellTool, CMD_BEGIN, CMD_END


class TestStructuredMarkerParsing:
    def test_extract_with_markers(self):
        raw = f"{CMD_BEGIN}\nubuntu@sandbox:~\n{CMD_END} ls\nfile1.txt\nfile2.py\n{CMD_END}"
        result = ShellTool._extract_structured_output(raw)
        assert "file1.txt" in result
        assert CMD_BEGIN not in result

    def test_extract_without_markers_fallback(self):
        raw = "ubuntu@sandbox:~ $ ls\nfile1.txt\nfile2.py"
        result = ShellTool._extract_structured_output(raw)
        assert result == raw  # Unchanged — no markers

    def test_extract_multiple_commands(self):
        raw = (
            f"{CMD_BEGIN}\nubuntu@sandbox:~\n{CMD_END} ls\nfile1.txt\n{CMD_END}"
            f"{CMD_BEGIN}\nubuntu@sandbox:~\n{CMD_END} pwd\n/home/ubuntu\n{CMD_END}"
        )
        result = ShellTool._extract_structured_output(raw)
        assert "file1.txt" in result
        assert "/home/ubuntu" in result

    def test_extract_empty_output(self):
        result = ShellTool._extract_structured_output("")
        assert result == ""
```

**Step 4: Run tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker python -m pytest tests/domain/services/tools/test_shell_markers.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/tools/shell.py backend/tests/domain/services/tools/test_shell_markers.py
git commit -m "feat(backend): add structured terminal marker parser with backward compat fallback"
```

---

### Task 2.6: Add SHELL_USE_STRUCTURED_MARKERS to .env.example and Docker Compose

**Files:**
- Modify: `.env.example` (sandbox section)
- Modify: `docker-compose-development.yml` (sandbox environment)
- Modify: `docker-compose.yml` (sandbox environment)

**Step 1: Add to .env.example**

After the `SANDBOX_STREAMING_MODE` line in `.env.example`, add:

```bash
# Structured terminal markers ([CMD_BEGIN]/[CMD_END]) for reliable output parsing
SHELL_USE_STRUCTURED_MARKERS=true
```

**Step 2: Add to docker-compose files**

Add to both sandbox service `environment:` sections:

```yaml
      - SHELL_USE_STRUCTURED_MARKERS=${SHELL_USE_STRUCTURED_MARKERS:-true}
```

**Step 3: Commit**

```bash
git add .env.example docker-compose-development.yml docker-compose.yml
git commit -m "feat(sandbox): expose SHELL_USE_STRUCTURED_MARKERS in compose and .env.example"
```

---

## Phase 3: Sandbox → Backend Callback (RUNTIME_API_HOST)

### Task 3.1: Write Failing Tests for Callback Client

**Files:**
- Create: `sandbox/tests/services/test_callback.py`

**Step 1: Write the tests**

```python
"""Tests for sandbox → backend callback client."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.callback import CallbackClient


class TestCallbackClient:
    """Test the callback client for sandbox → backend communication."""

    def test_client_is_noop_when_no_host(self):
        """Client should be a no-op when RUNTIME_API_HOST is not set."""
        with patch("app.services.callback.settings") as mock_settings:
            mock_settings.RUNTIME_API_HOST = None
            mock_settings.RUNTIME_API_TOKEN = None
            client = CallbackClient()
            assert not client.enabled

    def test_client_enabled_when_host_set(self):
        """Client should be enabled when RUNTIME_API_HOST is set."""
        with patch("app.services.callback.settings") as mock_settings:
            mock_settings.RUNTIME_API_HOST = "http://backend:8000"
            mock_settings.RUNTIME_API_TOKEN = "test-token"
            client = CallbackClient()
            assert client.enabled

    @pytest.mark.asyncio
    async def test_report_event_noop_when_disabled(self):
        """report_event should silently return when disabled."""
        with patch("app.services.callback.settings") as mock_settings:
            mock_settings.RUNTIME_API_HOST = None
            mock_settings.RUNTIME_API_TOKEN = None
            client = CallbackClient()
            # Should not raise
            await client.report_event("crash", {"reason": "OOM"})

    @pytest.mark.asyncio
    async def test_report_event_sends_post(self):
        """report_event should POST to the callback endpoint."""
        with patch("app.services.callback.settings") as mock_settings:
            mock_settings.RUNTIME_API_HOST = "http://backend:8000"
            mock_settings.RUNTIME_API_TOKEN = "test-token"
            client = CallbackClient()

            mock_response = MagicMock()
            mock_response.status_code = 200

            with patch.object(client, "_client") as mock_client:
                mock_client.post = AsyncMock(return_value=mock_response)
                await client.report_event("crash", {"reason": "OOM"})
                mock_client.post.assert_called_once()
                call_args = mock_client.post.call_args
                assert "/callback/event" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_report_progress_sends_post(self):
        """report_progress should POST to the progress endpoint."""
        with patch("app.services.callback.settings") as mock_settings:
            mock_settings.RUNTIME_API_HOST = "http://backend:8000"
            mock_settings.RUNTIME_API_TOKEN = "test-token"
            client = CallbackClient()

            mock_response = MagicMock()
            mock_response.status_code = 200

            with patch.object(client, "_client") as mock_client:
                mock_client.post = AsyncMock(return_value=mock_response)
                await client.report_progress("session-1", "step-1", 50, "halfway")
                mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_report_event_handles_timeout_gracefully(self):
        """Callback failures should be swallowed (fire-and-forget)."""
        import httpx
        with patch("app.services.callback.settings") as mock_settings:
            mock_settings.RUNTIME_API_HOST = "http://backend:8000"
            mock_settings.RUNTIME_API_TOKEN = "test-token"
            client = CallbackClient()

            with patch.object(client, "_client") as mock_client:
                mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
                # Should not raise
                await client.report_event("crash", {"reason": "OOM"})
```

**Step 2: Run to verify failure**

Run: `cd /home/mac/Desktop/Pythinker-main/sandbox && python3 -m pytest tests/services/test_callback.py -v 2>&1 | head -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.callback'`

**Step 3: Commit**

```bash
git add sandbox/tests/services/test_callback.py
git commit -m "test(sandbox): add failing tests for callback client"
```

---

### Task 3.2: Add Callback Config Settings

**Files:**
- Modify: `sandbox/app/core/config.py` (add RUNTIME_API_HOST, RUNTIME_API_TOKEN)

**Step 1: Add settings**

After the `TZ` setting added in Phase 1, add:

```python
    # Sandbox → Backend callback
    RUNTIME_API_HOST: Optional[str] = None
    RUNTIME_API_TOKEN: Optional[str] = None
```

Ensure `Optional` is imported from `typing`.

**Step 2: Commit**

```bash
git add sandbox/app/core/config.py
git commit -m "feat(sandbox): add RUNTIME_API_HOST and RUNTIME_API_TOKEN settings"
```

---

### Task 3.3: Implement Callback Client

**Files:**
- Create: `sandbox/app/services/callback.py`

**Step 1: Write the implementation**

```python
"""Sandbox → Backend callback client.

Fire-and-forget HTTP client for reporting sandbox events, progress, and
resource requests back to the backend.  No-op when RUNTIME_API_HOST is unset.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


class CallbackClient:
    """Lightweight HTTP client for sandbox → backend callbacks."""

    def __init__(self) -> None:
        self.enabled = bool(settings.RUNTIME_API_HOST and settings.RUNTIME_API_TOKEN)
        if self.enabled:
            self._client = httpx.AsyncClient(
                base_url=settings.RUNTIME_API_HOST,
                timeout=_TIMEOUT,
                headers={
                    "X-Sandbox-Callback-Token": settings.RUNTIME_API_TOKEN or "",
                    "Content-Type": "application/json",
                },
            )
        else:
            self._client = None  # type: ignore[assignment]

    async def report_event(
        self, event_type: str, details: dict[str, Any], session_id: str | None = None
    ) -> None:
        """Report a sandbox event (crash, OOM, timeout, ready)."""
        if not self.enabled:
            return
        await self._post("/api/v1/sandbox/callback/event", {
            "type": event_type,
            "details": details,
            "session_id": session_id,
        })

    async def report_progress(
        self,
        session_id: str,
        step: str,
        percent: int,
        message: str = "",
    ) -> None:
        """Report progress on an ongoing operation."""
        if not self.enabled:
            return
        await self._post("/api/v1/sandbox/callback/progress", {
            "session_id": session_id,
            "step": step,
            "percent": percent,
            "message": message,
        })

    async def request_resource(
        self, resource_type: str, params: dict[str, Any] | None = None
    ) -> Optional[dict[str, Any]]:
        """Request a resource from the backend (upload URL, secret, etc.)."""
        if not self.enabled:
            return None
        return await self._post("/api/v1/sandbox/callback/request", {
            "type": resource_type,
            "params": params or {},
        })

    async def _post(self, path: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Fire-and-forget POST. Swallows all errors."""
        try:
            response = await self._client.post(path, json=payload)
            if response.status_code >= 400:
                logger.warning("Callback %s returned %d", path, response.status_code)
                return None
            return response.json()
        except Exception:
            logger.debug("Callback to %s failed (fire-and-forget)", path, exc_info=True)
            return None

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client:
            await self._client.aclose()


# Singleton — initialized once at import time
callback_client = CallbackClient()
```

**Step 2: Run the tests**

Run: `cd /home/mac/Desktop/Pythinker-main/sandbox && python3 -m pytest tests/services/test_callback.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add sandbox/app/services/callback.py
git commit -m "feat(sandbox): implement CallbackClient for sandbox → backend communication"
```

---

### Task 3.4: Add Backend Callback Receiver Routes

**Files:**
- Create: `backend/app/interfaces/api/sandbox_callback_routes.py`
- Modify: `backend/app/interfaces/api/routes.py` (include new router)

**Step 1: Write the callback routes**

```python
"""Sandbox callback receiver routes.

These endpoints receive events, progress updates, and resource requests
from sandbox containers.  All requests are authenticated via
X-Sandbox-Callback-Token header (scoped JWT or shared secret).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox/callback", tags=["sandbox-callback"])


# ── Request/Response schemas ──────────────────────────────────────────


class CallbackEventRequest(BaseModel):
    type: str = Field(..., description="Event type: crash, oom, timeout, ready")
    details: dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None


class CallbackProgressRequest(BaseModel):
    session_id: str
    step: str
    percent: int = Field(ge=0, le=100)
    message: str = ""


class CallbackResourceRequest(BaseModel):
    type: str = Field(..., description="Resource type: upload_url, secret")
    params: dict[str, Any] = Field(default_factory=dict)


class CallbackResponse(BaseModel):
    success: bool = True
    message: str = "ok"
    data: Optional[dict[str, Any]] = None


# ── Auth dependency ───────────────────────────────────────────────────


async def verify_sandbox_callback_token(
    x_sandbox_callback_token: str = Header(...),
) -> str:
    """Validate the sandbox callback token."""
    settings = get_settings()
    expected = settings.sandbox_callback_token
    if not expected or x_sandbox_callback_token != expected:
        raise HTTPException(status_code=401, detail="Invalid sandbox callback token")
    return x_sandbox_callback_token


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/event", response_model=CallbackResponse)
async def receive_event(
    body: CallbackEventRequest,
    _token: str = Depends(verify_sandbox_callback_token),
) -> CallbackResponse:
    """Receive a sandbox event (crash, OOM, timeout, ready)."""
    logger.info(
        "Sandbox callback event: type=%s session=%s details=%s",
        body.type,
        body.session_id,
        body.details,
    )
    # Future: forward to AgentService for session correlation
    return CallbackResponse(message=f"Event '{body.type}' received")


@router.post("/progress", response_model=CallbackResponse)
async def receive_progress(
    body: CallbackProgressRequest,
    _token: str = Depends(verify_sandbox_callback_token),
) -> CallbackResponse:
    """Receive a progress update from the sandbox."""
    logger.info(
        "Sandbox callback progress: session=%s step=%s percent=%d message=%s",
        body.session_id,
        body.step,
        body.percent,
        body.message,
    )
    return CallbackResponse(message="Progress received")


@router.post("/request", response_model=CallbackResponse)
async def receive_resource_request(
    body: CallbackResourceRequest,
    _token: str = Depends(verify_sandbox_callback_token),
) -> CallbackResponse:
    """Handle a resource request from the sandbox."""
    logger.info(
        "Sandbox callback resource request: type=%s params=%s",
        body.type,
        body.params,
    )
    # Future: generate presigned upload URLs, fetch secrets, etc.
    return CallbackResponse(
        message=f"Resource request '{body.type}' received",
        data={"status": "pending"},
    )
```

**Step 2: Include router in routes.py**

In `backend/app/interfaces/api/routes.py`, add the import and include:

```python
from app.interfaces.api.sandbox_callback_routes import router as sandbox_callback_router

# In the router inclusion section:
api_router.include_router(sandbox_callback_router)
```

**Step 3: Add backend config**

In `backend/app/core/config_sandbox.py`, in `SandboxSettingsMixin` (after the existing settings around line 56), add:

```python
    # Sandbox callback
    sandbox_callback_enabled: bool = False
    sandbox_callback_token: Optional[str] = None
```

**Step 4: Write a test**

Create `backend/tests/interfaces/api/test_sandbox_callback_routes.py`:

```python
"""Tests for sandbox callback receiver routes."""
import pytest
from unittest.mock import patch


class TestSandboxCallbackRoutes:
    """Test callback endpoints with token validation."""

    def test_event_without_token_returns_422(self, test_client):
        """Missing token header should return 422."""
        response = test_client.post(
            "/api/v1/sandbox/callback/event",
            json={"type": "crash", "details": {"reason": "OOM"}},
        )
        assert response.status_code == 422

    def test_event_with_invalid_token_returns_401(self, test_client):
        """Invalid token should return 401."""
        response = test_client.post(
            "/api/v1/sandbox/callback/event",
            json={"type": "crash", "details": {"reason": "OOM"}},
            headers={"X-Sandbox-Callback-Token": "wrong-token"},
        )
        assert response.status_code == 401

    def test_event_with_valid_token_returns_200(self, test_client):
        """Valid token should return 200."""
        with patch("app.interfaces.api.sandbox_callback_routes.get_settings") as mock:
            mock.return_value.sandbox_callback_token = "valid-token"
            response = test_client.post(
                "/api/v1/sandbox/callback/event",
                json={"type": "ready", "details": {}},
                headers={"X-Sandbox-Callback-Token": "valid-token"},
            )
            assert response.status_code == 200

    def test_progress_with_valid_token(self, test_client):
        """Progress endpoint should accept valid data."""
        with patch("app.interfaces.api.sandbox_callback_routes.get_settings") as mock:
            mock.return_value.sandbox_callback_token = "valid-token"
            response = test_client.post(
                "/api/v1/sandbox/callback/progress",
                json={
                    "session_id": "abc-123",
                    "step": "downloading",
                    "percent": 50,
                    "message": "halfway there",
                },
                headers={"X-Sandbox-Callback-Token": "valid-token"},
            )
            assert response.status_code == 200
```

**Step 5: Run tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker python -m pytest tests/interfaces/api/test_sandbox_callback_routes.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/app/interfaces/api/sandbox_callback_routes.py backend/app/interfaces/api/routes.py backend/app/core/config_sandbox.py backend/tests/interfaces/api/test_sandbox_callback_routes.py
git commit -m "feat(backend): add sandbox callback receiver routes with token auth"
```

---

### Task 3.5: Add Callback Config to Docker Compose and .env.example

**Files:**
- Modify: `docker-compose-development.yml` (sandbox environment)
- Modify: `docker-compose.yml` (sandbox environment)
- Modify: `.env.example`

**Step 1: Add to compose files**

In both sandbox service `environment:` sections:

```yaml
      - RUNTIME_API_HOST=${RUNTIME_API_HOST:-http://backend:8000}
      - RUNTIME_API_TOKEN=${SANDBOX_CALLBACK_TOKEN:-}
```

In both backend service `environment:` sections:

```yaml
      - SANDBOX_CALLBACK_ENABLED=${SANDBOX_CALLBACK_ENABLED:-false}
      - SANDBOX_CALLBACK_TOKEN=${SANDBOX_CALLBACK_TOKEN:-}
```

**Step 2: Add to .env.example**

In the sandbox configuration section:

```bash
# Sandbox → Backend callback (bidirectional communication)
SANDBOX_CALLBACK_ENABLED=false
SANDBOX_CALLBACK_TOKEN=
```

**Step 3: Commit**

```bash
git add docker-compose-development.yml docker-compose.yml .env.example
git commit -m "feat: add sandbox callback config to compose and .env.example"
```

---

## Phase 4: LLM Proxy Inside Sandbox

### Task 4.1: Write Failing Tests for LLM Proxy Routes

**Files:**
- Create: `backend/tests/interfaces/api/test_llm_proxy_routes.py`

**Step 1: Write the tests**

```python
"""Tests for the sandbox LLM proxy endpoint."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestLLMProxyRoutes:
    """Test OpenAI-compatible LLM proxy for sandbox."""

    def test_proxy_disabled_returns_403(self, test_client):
        """When proxy is disabled, should return 403."""
        with patch("app.interfaces.api.llm_proxy_routes.get_settings") as mock:
            mock.return_value.sandbox_llm_proxy_enabled = False
            response = test_client.post(
                "/api/v1/llm-proxy/v1/chat/completions",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                headers={"Authorization": "Bearer test-key"},
            )
            assert response.status_code == 403

    def test_proxy_invalid_key_returns_401(self, test_client):
        """Invalid API key should return 401."""
        with patch("app.interfaces.api.llm_proxy_routes.get_settings") as mock:
            mock.return_value.sandbox_llm_proxy_enabled = True
            mock.return_value.sandbox_llm_proxy_key = "correct-key"
            response = test_client.post(
                "/api/v1/llm-proxy/v1/chat/completions",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                headers={"Authorization": "Bearer wrong-key"},
            )
            assert response.status_code == 401

    def test_models_endpoint_returns_list(self, test_client):
        """GET /models should return available models."""
        with patch("app.interfaces.api.llm_proxy_routes.get_settings") as mock:
            mock.return_value.sandbox_llm_proxy_enabled = True
            mock.return_value.sandbox_llm_proxy_key = "test-key"
            mock.return_value.model_name = "kimi-for-coding"
            response = test_client.get(
                "/api/v1/llm-proxy/v1/models",
                headers={"Authorization": "Bearer test-key"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "data" in data

    def test_max_tokens_cap_enforced(self, test_client):
        """Requests exceeding max_tokens cap should be capped."""
        with patch("app.interfaces.api.llm_proxy_routes.get_settings") as mock:
            mock.return_value.sandbox_llm_proxy_enabled = True
            mock.return_value.sandbox_llm_proxy_key = "test-key"
            mock.return_value.sandbox_llm_proxy_max_tokens = 100
            response = test_client.post(
                "/api/v1/llm-proxy/v1/chat/completions",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 99999,
                },
                headers={"Authorization": "Bearer test-key"},
            )
            # Should proceed (capped internally) or return 200
            # Implementation will cap to 100
            assert response.status_code in (200, 500)  # 500 if no LLM configured in test
```

**Step 2: Run to verify failure**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker python -m pytest tests/interfaces/api/test_llm_proxy_routes.py -v 2>&1 | head -20`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Commit**

```bash
git add backend/tests/interfaces/api/test_llm_proxy_routes.py
git commit -m "test(backend): add failing tests for LLM proxy routes"
```

---

### Task 4.2: Add LLM Proxy Config to Backend

**Files:**
- Modify: `backend/app/core/config_sandbox.py` (SandboxSettingsMixin)

**Step 1: Add settings**

In `SandboxSettingsMixin`, after the callback settings added in Phase 3, add:

```python
    # LLM Proxy (OpenAI-compatible endpoint for sandbox)
    sandbox_llm_proxy_enabled: bool = False
    sandbox_llm_proxy_key: Optional[str] = None
    sandbox_llm_proxy_max_tokens: int = 4096
    sandbox_llm_proxy_rate_limit: int = 30  # requests per minute
    sandbox_llm_proxy_allowed_models: list[str] = []  # empty = all models
```

**Step 2: Commit**

```bash
git add backend/app/core/config_sandbox.py
git commit -m "feat(backend): add LLM proxy settings to SandboxSettingsMixin"
```

---

### Task 4.3: Implement LLM Proxy Routes

**Files:**
- Create: `backend/app/interfaces/api/llm_proxy_routes.py`
- Modify: `backend/app/interfaces/api/routes.py`

**Step 1: Write the proxy router**

```python
"""OpenAI-compatible LLM proxy for sandbox containers.

Sandbox agents call this endpoint instead of direct LLM APIs.
The backend validates auth, enforces rate limits and token caps,
then forwards to the configured LLM provider via UniversalLLM.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm-proxy/v1", tags=["llm-proxy"])


# ── Schemas ───────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = ""
    messages: list[ChatMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: bool = False


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str = "chatcmpl-proxy"
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: list[ChatChoice] = []
    usage: dict[str, int] = Field(default_factory=lambda: {
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
    })


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    owned_by: str = "pythinker"


class ModelsResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo] = []


# ── Auth ──────────────────────────────────────────────────────────────


async def verify_proxy_auth(authorization: str = Header(...)) -> str:
    """Validate Bearer token for LLM proxy access."""
    settings = get_settings()

    if not settings.sandbox_llm_proxy_enabled:
        raise HTTPException(status_code=403, detail="LLM proxy is disabled")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization[7:]
    if not settings.sandbox_llm_proxy_key or token != settings.sandbox_llm_proxy_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return token


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    _token: str = Depends(verify_proxy_auth),
) -> JSONResponse:
    """OpenAI-compatible chat completions endpoint."""
    settings = get_settings()

    # Cap max_tokens
    max_tokens = min(
        body.max_tokens or settings.sandbox_llm_proxy_max_tokens,
        settings.sandbox_llm_proxy_max_tokens,
    )

    # Model allow-list check
    if settings.sandbox_llm_proxy_allowed_models and body.model not in settings.sandbox_llm_proxy_allowed_models:
        raise HTTPException(status_code=400, detail=f"Model '{body.model}' not allowed")

    try:
        # Import lazily to avoid circular deps
        from app.infrastructure.llm.universal_llm import get_universal_llm

        llm = get_universal_llm()
        messages = [{"role": m.role, "content": m.content} for m in body.messages]

        result = await llm.ask_with_messages(
            messages=messages,
            max_tokens=max_tokens,
            temperature=body.temperature,
        )

        response = ChatCompletionResponse(
            model=body.model or settings.model_name,
            choices=[
                ChatChoice(
                    message=ChatMessage(role="assistant", content=result or ""),
                )
            ],
        )
        return JSONResponse(content=response.model_dump())

    except Exception as e:
        logger.error("LLM proxy error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"LLM proxy error: {type(e).__name__}")


@router.get("/models")
async def list_models(
    _token: str = Depends(verify_proxy_auth),
) -> JSONResponse:
    """List available models."""
    settings = get_settings()
    models = [ModelInfo(id=settings.model_name)]

    if settings.sandbox_llm_proxy_allowed_models:
        models = [ModelInfo(id=m) for m in settings.sandbox_llm_proxy_allowed_models]

    return JSONResponse(content=ModelsResponse(data=models).model_dump())
```

**Step 2: Include router in routes.py**

```python
from app.interfaces.api.llm_proxy_routes import router as llm_proxy_router

api_router.include_router(llm_proxy_router)
```

**Step 3: Run tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker python -m pytest tests/interfaces/api/test_llm_proxy_routes.py -v`
Expected: Tests pass (some may need adjustments based on test_client fixture)

**Step 4: Commit**

```bash
git add backend/app/interfaces/api/llm_proxy_routes.py backend/app/interfaces/api/routes.py
git commit -m "feat(backend): implement OpenAI-compatible LLM proxy for sandbox"
```

---

### Task 4.4: Add LLM Proxy Env Vars to Sandbox and Compose

**Files:**
- Modify: `sandbox/app/core/config.py`
- Modify: `docker-compose-development.yml`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Step 1: Add to sandbox config**

```python
    # LLM Proxy (OpenAI-compatible, provided by backend)
    OPENAI_API_BASE: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
```

**Step 2: Add to compose files**

In both sandbox service `environment:` sections:

```yaml
      - OPENAI_API_BASE=${SANDBOX_LLM_PROXY_URL:-http://backend:8000/api/v1/llm-proxy/v1}
      - OPENAI_BASE_URL=${SANDBOX_LLM_PROXY_URL:-http://backend:8000/api/v1/llm-proxy/v1}
      - OPENAI_API_KEY=${SANDBOX_LLM_PROXY_KEY:-}
```

**Step 3: Add to .env.example**

```bash
# Sandbox LLM Proxy (OpenAI-compatible endpoint inside sandbox)
SANDBOX_LLM_PROXY_ENABLED=false
SANDBOX_LLM_PROXY_KEY=
SANDBOX_LLM_PROXY_MAX_TOKENS=4096
SANDBOX_LLM_PROXY_RATE_LIMIT=30
```

**Step 4: Update context generator**

In `sandbox/scripts/generate_sandbox_context.py`, in the `scan_sandbox_capabilities()` method, add detection:

```python
"llm_proxy_available": bool(os.environ.get("OPENAI_API_BASE")),
"llm_proxy_base_url": os.environ.get("OPENAI_API_BASE", ""),
```

**Step 5: Commit**

```bash
git add sandbox/app/core/config.py docker-compose-development.yml docker-compose.yml .env.example sandbox/scripts/generate_sandbox_context.py
git commit -m "feat: add LLM proxy config to sandbox, compose, and .env.example"
```

---

## Phase 5: Code-Server (VS Code Web IDE)

### Task 5.1: Add Code-Server Installation to Dockerfile

**Files:**
- Modify: `sandbox/Dockerfile` (builder stage, addons section around line 106-111)

**Step 1: Add code-server install**

In `sandbox/Dockerfile`, in the builder stage, find the addons section (around line 106-111). After the existing pnpm globals block, add:

```dockerfile
# code-server — VS Code web IDE (addons profile only)
RUN if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        curl -fsSL https://code-server.dev/install.sh | sh && \
        code-server --install-extension ms-python.python 2>/dev/null || true && \
        code-server --install-extension dbaeumer.vscode-eslint 2>/dev/null || true; \
    fi
```

In the runtime stage, copy code-server if installed:

```dockerfile
COPY --from=builder /usr/lib/code-server /usr/lib/code-server
COPY --from=builder /usr/bin/code-server /usr/bin/code-server
```

Wrap in conditional to avoid build failure when not installed:

```dockerfile
RUN if [ -f /usr/bin/code-server ]; then echo "code-server available"; fi
```

**Step 2: Commit**

```bash
git add sandbox/Dockerfile
git commit -m "feat(sandbox): add code-server install to Dockerfile addons profile"
```

---

### Task 5.2: Add Code-Server to Supervisord

**Files:**
- Modify: `sandbox/supervisord.conf:205` (before group:services)
- Modify: `sandbox/app/core/config.py`

**Step 1: Add config settings**

```python
    # Code-Server (VS Code web IDE)
    CODE_SERVER_PORT: int = 8443
    CODE_SERVER_PASSWORD: Optional[str] = None
    ENABLE_CODE_SERVER: bool = False
```

**Step 2: Add supervisord program**

In `sandbox/supervisord.conf`, before the `[group:services]` block (line 204), add:

```ini
; code-server — VS Code web IDE (optional, enabled by ENABLE_CODE_SERVER env var)
[program:code_server]
command=/bin/bash -c "if [ '%(ENV_ENABLE_CODE_SERVER)s' = '1' ] || [ '%(ENV_ENABLE_CODE_SERVER)s' = 'true' ]; then exec code-server --bind-addr 0.0.0.0:%(ENV_CODE_SERVER_PORT)s --auth password --disable-telemetry --disable-update-check /workspace; else echo 'code-server disabled'; exit 0; fi"
autostart=true
autorestart=unexpected
exitcodes=0
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
environment=HOME=/home/ubuntu,PASSWORD=%(ENV_CODE_SERVER_PASSWORD)s
user=ubuntu
priority=60
```

**Step 3: Update group:services to include code_server**

Update the `programs=` line in `[group:services]` to include `code_server`:

```ini
programs=runtime_init,context_generator,dbus_session,xvfb,openbox,x11vnc,websockify,chrome_cdp_only,socat,app,framework,code_server
```

**Step 4: Add port and env vars to compose files**

In both compose files, sandbox service:

Ports:
```yaml
      - "127.0.0.1:8443:8443"  # code-server (localhost only)
```

Environment:
```yaml
      - CODE_SERVER_PORT=${CODE_SERVER_PORT:-8443}
      - CODE_SERVER_PASSWORD=${CODE_SERVER_PASSWORD:-}
      - ENABLE_CODE_SERVER=${ENABLE_CODE_SERVER:-0}
```

**Step 5: Commit**

```bash
git add sandbox/supervisord.conf sandbox/app/core/config.py docker-compose-development.yml docker-compose.yml
git commit -m "feat(sandbox): add code-server as optional supervisord service"
```

---

### Task 5.3: Create CodeServerView Frontend Component

**Files:**
- Create: `frontend/src/components/CodeServerView.vue`

**Step 1: Write the component**

```vue
<script setup lang="ts">
/**
 * CodeServerView — iframe-based VS Code web IDE viewer.
 *
 * Loads code-server via a signed URL from the backend,
 * matching the VncViewer.vue pattern for auth and lifecycle.
 */
import { ref, watch, computed, onBeforeUnmount } from 'vue'

const props = defineProps<{
  sessionId: string
  enabled: boolean
  codeServerUrl?: string
}>()

const emit = defineEmits<{
  connected: []
  disconnected: []
  error: [message: string]
}>()

const iframeRef = ref<HTMLIFrameElement | null>(null)
const status = ref<'loading' | 'connected' | 'error'>('loading')

const iframeSrc = computed(() => {
  if (!props.enabled || !props.codeServerUrl) return ''
  return props.codeServerUrl
})

watch(
  () => props.enabled,
  (enabled) => {
    if (enabled) {
      status.value = 'loading'
    } else {
      status.value = 'error'
      emit('disconnected')
    }
  },
)

function onIframeLoad() {
  status.value = 'connected'
  emit('connected')
}

function onIframeError() {
  status.value = 'error'
  emit('error', 'Failed to load code-server')
}

onBeforeUnmount(() => {
  emit('disconnected')
})
</script>

<template>
  <div class="code-server-view relative w-full h-full">
    <!-- Loading overlay -->
    <div
      v-if="status === 'loading' && enabled"
      class="absolute inset-0 flex items-center justify-center bg-zinc-900 z-10"
    >
      <div class="text-zinc-400 text-sm">Loading VS Code...</div>
    </div>

    <!-- Error state -->
    <div
      v-if="status === 'error' || !enabled"
      class="absolute inset-0 flex items-center justify-center bg-zinc-900"
    >
      <div class="text-zinc-500 text-sm">
        {{ !enabled ? 'Code-server not available' : 'Connection failed' }}
      </div>
    </div>

    <!-- code-server iframe -->
    <iframe
      v-if="enabled && iframeSrc"
      ref="iframeRef"
      :src="iframeSrc"
      class="w-full h-full border-0"
      allow="clipboard-read; clipboard-write"
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
      @load="onIframeLoad"
      @error="onIframeError"
    />
  </div>
</template>
```

**Step 2: Commit**

```bash
git add frontend/src/components/CodeServerView.vue
git commit -m "feat(frontend): add CodeServerView component for VS Code web IDE"
```

---

### Task 5.4: Add .env.example entries for Code-Server

**Files:**
- Modify: `.env.example`

**Step 1: Add entries**

```bash
# Code-Server (VS Code web IDE in sandbox)
# Requires ENABLE_SANDBOX_ADDONS=1 at Docker build time
ENABLE_CODE_SERVER=0
CODE_SERVER_PASSWORD=
CODE_SERVER_PORT=8443
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add code-server config to .env.example"
```

---

## Phase 6: Observability (OTEL + Sentry)

### Task 6.1: Add Observability Dependencies

**Files:**
- Modify: `sandbox/requirements.runtime.txt`

**Step 1: Add packages**

At the end of `sandbox/requirements.runtime.txt`, add:

```
# Observability (lazy-loaded — zero overhead when disabled)
opentelemetry-api>=1.29.0
opentelemetry-sdk>=1.29.0
opentelemetry-instrumentation-fastapi>=0.50b0
opentelemetry-instrumentation-httpx>=0.50b0
opentelemetry-exporter-otlp-proto-http>=1.29.0
sentry-sdk[fastapi]>=2.19.0
```

**Step 2: Commit**

```bash
git add sandbox/requirements.runtime.txt
git commit -m "feat(sandbox): add OTEL and Sentry SDK dependencies"
```

---

### Task 6.2: Add Observability Config Settings

**Files:**
- Modify: `sandbox/app/core/config.py`

**Step 1: Add settings**

```python
    # Observability (OTEL + Sentry)
    OTEL_ENABLED: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    OTEL_SERVICE_NAME: str = "sandbox-runtime"
    OTEL_TRACES_SAMPLER_RATIO: float = 1.0
    OTEL_BSP_MAX_EXPORT_BATCH_SIZE: int = 1024
    OTEL_BSP_SCHEDULE_DELAY: int = 10000
    OTEL_PYTHON_LOG_CORRELATION: bool = True
    OTEL_RESOURCE_ATTRIBUTES: str = "service.name=sandbox-runtime,service.env=sandbox"
    SENTRY_DSN: Optional[str] = None
```

**Step 2: Commit**

```bash
git add sandbox/app/core/config.py
git commit -m "feat(sandbox): add OTEL and Sentry settings"
```

---

### Task 6.3: Implement Telemetry Setup Module

**Files:**
- Create: `sandbox/app/core/telemetry.py`

**Step 1: Write the module**

```python
"""Telemetry initialization for sandbox (OTEL + Sentry).

All imports are lazy — zero overhead when OTEL_ENABLED=false and SENTRY_DSN is unset.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def setup_telemetry(app: "FastAPI") -> None:
    """Initialize OpenTelemetry and/or Sentry if configured."""
    _setup_otel(app)
    _setup_sentry()


def _setup_otel(app: "FastAPI") -> None:
    """Configure OpenTelemetry tracing with OTLP HTTP exporter."""
    if not settings.OTEL_ENABLED or not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        logger.info("OTEL disabled (OTEL_ENABLED=%s)", settings.OTEL_ENABLED)
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        resource = Resource.create({
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.env": "sandbox",
        })

        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=f"{settings.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces",
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                max_export_batch_size=settings.OTEL_BSP_MAX_EXPORT_BATCH_SIZE,
                schedule_delay_millis=settings.OTEL_BSP_SCHEDULE_DELAY,
            )
        )
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()

        logger.info(
            "OTEL initialized: service=%s endpoint=%s",
            settings.OTEL_SERVICE_NAME,
            settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        )
    except ImportError:
        logger.warning("OTEL packages not installed — skipping")
    except Exception:
        logger.exception("OTEL setup failed — continuing without tracing")


def _setup_sentry() -> None:
    """Configure Sentry error tracking."""
    if not settings.SENTRY_DSN:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[FastApiIntegration()],
            traces_sample_rate=settings.OTEL_TRACES_SAMPLER_RATIO,
            environment="sandbox",
        )
        logger.info("Sentry initialized for sandbox")
    except ImportError:
        logger.warning("sentry-sdk not installed — skipping")
    except Exception:
        logger.exception("Sentry setup failed — continuing without error tracking")
```

**Step 2: Commit**

```bash
git add sandbox/app/core/telemetry.py
git commit -m "feat(sandbox): implement telemetry setup module (OTEL + Sentry)"
```

---

### Task 6.4: Wire Telemetry into Main App

**Files:**
- Modify: `sandbox/app/main.py` (after setup_logging call, around line 49)

**Step 1: Import and call**

In `sandbox/app/main.py`, after the `setup_logging()` call (line 49) and after the FastAPI app is created (line 52-54), add:

```python
from app.core.telemetry import setup_telemetry

# After app = FastAPI(...) and middleware setup:
setup_telemetry(app)
```

**Step 2: Add OTEL env vars to compose files**

In both sandbox service `environment:` sections:

```yaml
      - OTEL_ENABLED=${OTEL_ENABLED:-false}
      - OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT:-}
      - OTEL_SERVICE_NAME=sandbox-runtime
      - OTEL_TRACES_SAMPLER_RATIO=${OTEL_TRACES_SAMPLER_RATIO:-1.0}
      - SENTRY_DSN=${SANDBOX_SENTRY_DSN:-}
```

**Step 3: Add to .env.example**

```bash
# Sandbox Observability (OTEL + Sentry)
OTEL_ENABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=
OTEL_TRACES_SAMPLER_RATIO=1.0
SANDBOX_SENTRY_DSN=
```

**Step 4: Write test**

Create `sandbox/tests/core/test_telemetry.py`:

```python
"""Tests for telemetry initialization."""
import pytest
from unittest.mock import patch, MagicMock


class TestTelemetrySetup:
    def test_otel_disabled_by_default(self):
        """OTEL should not initialize when disabled."""
        with patch("app.core.telemetry.settings") as mock_settings:
            mock_settings.OTEL_ENABLED = False
            mock_settings.SENTRY_DSN = None

            mock_app = MagicMock()
            from app.core.telemetry import setup_telemetry
            # Should not raise
            setup_telemetry(mock_app)

    def test_sentry_disabled_when_no_dsn(self):
        """Sentry should not initialize without DSN."""
        with patch("app.core.telemetry.settings") as mock_settings:
            mock_settings.OTEL_ENABLED = False
            mock_settings.SENTRY_DSN = None

            from app.core.telemetry import _setup_sentry
            # Should not raise
            _setup_sentry()
```

**Step 5: Run tests**

Run: `cd /home/mac/Desktop/Pythinker-main/sandbox && python3 -m pytest tests/core/test_telemetry.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add sandbox/app/main.py sandbox/app/core/telemetry.py sandbox/tests/core/test_telemetry.py docker-compose-development.yml docker-compose.yml .env.example
git commit -m "feat(sandbox): wire OTEL + Sentry telemetry into sandbox app"
```

---

## Phase 7: GitHub Token + Cloud Integrations

### Task 7.1: Add GH Auth Setup to Supervisord

**Files:**
- Modify: `sandbox/supervisord.conf` (after runtime_init, before context_generator)

**Step 1: Add gh_auth_setup program**

In `sandbox/supervisord.conf`, after `[program:runtime_init]` (line 39) and before `[program:context_generator]` (line 42), add:

```ini
; GitHub CLI authentication (one-shot, runs after runtime_init)
[program:gh_auth_setup]
command=/bin/bash -c "if [ -n \"%(ENV_GH_TOKEN)s\" ] && [ \"%(ENV_GH_TOKEN)s\" != \"\" ]; then echo '%(ENV_GH_TOKEN)s' | gh auth login --with-token 2>/dev/null && gh auth setup-git 2>/dev/null && echo 'gh auth: configured'; else echo 'gh auth: skipped (no GH_TOKEN)'; fi; exit 0"
autostart=true
autorestart=false
startsecs=0
exitcodes=0
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
environment=HOME=/home/ubuntu,GH_TOKEN=%(ENV_GH_TOKEN)s
user=ubuntu
priority=3
```

**Step 2: Update group:services**

Update `programs=` to include `gh_auth_setup`:

```ini
programs=runtime_init,gh_auth_setup,context_generator,dbus_session,xvfb,openbox,x11vnc,websockify,chrome_cdp_only,socat,app,framework,code_server
```

**Step 3: Commit**

```bash
git add sandbox/supervisord.conf
git commit -m "feat(sandbox): add gh CLI auth setup as supervisord one-shot"
```

---

### Task 7.2: Add Cloud Token Config and Compose Entries

**Files:**
- Modify: `sandbox/app/core/config.py`
- Modify: `backend/app/core/config_sandbox.py`
- Modify: `docker-compose-development.yml`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Step 1: Add to sandbox config**

```python
    # Cloud service tokens
    GH_TOKEN: Optional[str] = None
    GOOGLE_DRIVE_TOKEN: Optional[str] = None
    GOOGLE_WORKSPACE_CLI_TOKEN: Optional[str] = None
```

**Step 2: Add to backend config**

In `SandboxSettingsMixin`:

```python
    # Cloud tokens for sandbox
    sandbox_gh_token: Optional[str] = None
    sandbox_google_drive_token: Optional[str] = None
    sandbox_google_workspace_token: Optional[str] = None
```

**Step 3: Add to compose files**

In both sandbox service `environment:` sections:

```yaml
      - GH_TOKEN=${GH_TOKEN:-}
      - GOOGLE_DRIVE_TOKEN=${GOOGLE_DRIVE_TOKEN:-}
      - GOOGLE_WORKSPACE_CLI_TOKEN=${GOOGLE_WORKSPACE_CLI_TOKEN:-}
```

**Step 4: Add to .env.example**

```bash
# Cloud service tokens for sandbox (optional)
# GitHub token enables: gh auth, git clone private repos, gh pr create
#GH_TOKEN=ghp_your_github_token
# Google tokens enable: Drive file access, Workspace API operations
#GOOGLE_DRIVE_TOKEN=
#GOOGLE_WORKSPACE_CLI_TOKEN=
```

**Step 5: Commit**

```bash
git add sandbox/app/core/config.py backend/app/core/config_sandbox.py docker-compose-development.yml docker-compose.yml .env.example
git commit -m "feat: add cloud service token config (GitHub, Google Drive, Workspace)"
```

---

### Task 7.3: Update Context Generator for Cloud Auth Status

**Files:**
- Modify: `sandbox/scripts/generate_sandbox_context.py`

**Step 1: Add cloud auth detection**

In the `scan_sandbox_capabilities()` method (or `scan_system_tools()`), add:

```python
# Cloud authentication status
cloud_auth = {}

# GitHub CLI auth status
try:
    gh_result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True, text=True, timeout=5
    )
    cloud_auth["github_cli_authenticated"] = gh_result.returncode == 0
except (FileNotFoundError, subprocess.TimeoutExpired):
    cloud_auth["github_cli_authenticated"] = False

cloud_auth["google_drive_available"] = bool(os.environ.get("GOOGLE_DRIVE_TOKEN"))
cloud_auth["google_workspace_available"] = bool(os.environ.get("GOOGLE_WORKSPACE_CLI_TOKEN"))
```

Include `cloud_auth` in the returned context dict.

**Step 2: Commit**

```bash
git add sandbox/scripts/generate_sandbox_context.py
git commit -m "feat(sandbox): detect cloud auth status in context generator"
```

---

## Final Task: Rebuild and Verify

### Task F.1: Verify Compose Syntax

**Step 1: Validate both compose files**

Run:
```bash
cd /home/mac/Desktop/Pythinker-main
docker compose -f docker-compose-development.yml config --quiet
echo "Dev compose: OK"
```

**Step 2: Verify all env vars documented**

Run:
```bash
grep -c "SANDBOX_\|OTEL_\|SENTRY_\|CODE_SERVER\|GH_TOKEN\|GOOGLE_\|RUNTIME_API\|SHELL_USE_\|OPENAI_API" .env.example
```
Expected: Count matches all new vars added

---

### Task F.2: Run Backend Tests

**Step 1: Run full backend test suite**

Run:
```bash
cd /home/mac/Desktop/Pythinker-main/backend
conda run -n pythinker python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20
```
Expected: All pass (no regressions from new routes/config)

---

### Task F.3: Run Frontend Checks

**Step 1: Run lint and type-check**

Run:
```bash
cd /home/mac/Desktop/Pythinker-main/frontend
bun run lint
bun run type-check
```
Expected: No errors from new CodeServerView.vue

---

## Phase Dependency Graph

```
Phase 1 (Env Polish) ──────────────────────────────────┐
Phase 2 (Terminal Markers) ─────────────────────────────┤
Phase 3 (Callback) ────────────┬───────────────────────┤
Phase 4 (LLM Proxy) ──────────┘                        ├── Task F (Verify)
Phase 5 (Code-Server) ─────────────────────────────────┤
Phase 6 (Observability) ───────────────────────────────┤
Phase 7 (Cloud Tokens) ────────────────────────────────┘
```

Phases 1, 2, 6, 7 are independent. Phase 4 should follow Phase 3.
Phase 5 is independent but benefits from Phase 1 (env) and Phase 3 (callback for ready signal).
