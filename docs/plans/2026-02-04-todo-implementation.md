# TODO Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement all actionable TODO items scattered across the Pythinker codebase.

**Architecture:** Each TODO is addressed as an independent task, grouped by domain (frontend, backend infrastructure, backend domain). Tasks follow TDD where applicable.

**Tech Stack:** Python/FastAPI (backend), Vue 3/TypeScript (frontend), pytest (testing)

---

## Summary of TODOs

| # | Location | TODO Description | Priority |
|---|----------|------------------|----------|
| 1 | `frontend/src/pages/ChatPage.vue:1011` | Implement settings persistence for auto-run toggle | Medium |
| 2 | `frontend/src/pages/ChatPage.vue:1049` | Send rating to backend | Medium |
| 3 | `frontend/src/pages/SharePage.vue:410` | Handle wait event | Low |
| 4 | `backend/.../docker_sandbox.py:591` | Change file download to real stream | Low |
| 5 | `backend/.../flows/discuss.py:186` | Detect or configure language | Medium |
| 6 | `backend/.../flows/plan_act.py:113` | Refactor tracer to use domain port | High |
| 7 | `backend/.../flows/plan_act.py:1518` | Move session lookup to task runner | Medium |
| 8 | `backend/.../flows/plan_act_graph.py:69` | Refactor tracer to use domain port | High |
| 9 | `backend/.../flows/tree_of_thoughts_flow.py:55` | Refactor tracer to use domain port | High |
| 10 | `backend/.../langgraph/flow.py:58` | Refactor tracer to use domain port | High |
| 11 | `backend/.../agent_task_runner.py:676` | Refactor _handle_tool_event function | Medium |
| 12 | `backend/.../agent_task_runner.py:1009` | Move tool handling to tool function | Low |
| 13 | `backend/.../agent_domain_service.py:664` | Raise API exception instead of yield | Low |
| 14 | `backend/.../analyzers/security_analyzer.py:59` | Implement actual security scanning logic | High |

---

## Task 1: Create TracerPort Domain Abstraction

**Rationale:** Four TODOs (#6, #8, #9, #10) all request refactoring tracer imports to use a domain port. This consolidates all tracer abstraction work.

**Files:**
- Create: `backend/app/domain/external/tracing.py`
- Modify: `backend/app/domain/services/flows/plan_act.py:113`
- Modify: `backend/app/domain/services/flows/plan_act_graph.py:69`
- Modify: `backend/app/domain/services/flows/tree_of_thoughts_flow.py:55`
- Modify: `backend/app/domain/services/langgraph/flow.py:58`
- Test: `backend/tests/domain/external/test_tracing.py`

**Step 1: Write the failing test for TracerPort**

```python
# backend/tests/domain/external/test_tracing.py
"""Tests for tracing port abstraction."""
import pytest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

from app.domain.external.tracing import TracerPort, NullTracer, SpanKind


class TestTracerPort:
    """Test TracerPort interface and implementations."""

    def test_null_tracer_start_span_returns_context_manager(self) -> None:
        """NullTracer.start_span should return a working context manager."""
        tracer = NullTracer()

        with tracer.start_span("test_span", SpanKind.INTERNAL) as span:
            assert span is not None

    def test_null_tracer_span_set_attribute_no_op(self) -> None:
        """NullTracer span should accept attributes without error."""
        tracer = NullTracer()

        with tracer.start_span("test_span", SpanKind.INTERNAL) as span:
            span.set_attribute("key", "value")  # Should not raise

    def test_null_tracer_span_record_exception_no_op(self) -> None:
        """NullTracer span should accept exceptions without error."""
        tracer = NullTracer()

        with tracer.start_span("test_span", SpanKind.INTERNAL) as span:
            span.record_exception(ValueError("test"))  # Should not raise


class TestSpanKind:
    """Test SpanKind enum."""

    def test_span_kind_values(self) -> None:
        """SpanKind should have expected values."""
        assert SpanKind.INTERNAL is not None
        assert SpanKind.CLIENT is not None
        assert SpanKind.SERVER is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/external/test_tracing.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.domain.external.tracing'"

**Step 3: Write TracerPort abstraction**

```python
# backend/app/domain/external/tracing.py
"""Domain port for distributed tracing.

This module provides an abstraction layer for tracing, following DDD principles
by keeping infrastructure concerns (OpenTelemetry) out of the domain layer.
"""
from abc import ABC, abstractmethod
from contextlib import contextmanager
from enum import Enum
from typing import Any, Generator, Protocol


class SpanKind(Enum):
    """Type of span in distributed tracing."""
    INTERNAL = "internal"
    CLIENT = "client"
    SERVER = "server"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanProtocol(Protocol):
    """Protocol for span operations."""

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        ...

    def record_exception(self, exception: BaseException) -> None:
        """Record an exception on the span."""
        ...


class TracerPort(ABC):
    """Abstract port for tracing operations.

    Domain services depend on this abstraction rather than concrete
    infrastructure implementations like OpenTelemetry.
    """

    @abstractmethod
    @contextmanager
    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        **attributes: Any
    ) -> Generator[SpanProtocol, None, None]:
        """Start a new span.

        Args:
            name: Name of the span
            kind: Type of span
            **attributes: Initial attributes

        Yields:
            Span context for recording data
        """
        ...


class NullSpan:
    """No-op span implementation."""

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op."""
        pass

    def record_exception(self, exception: BaseException) -> None:
        """No-op."""
        pass


class NullTracer(TracerPort):
    """No-op tracer for testing and when tracing is disabled."""

    @contextmanager
    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        **attributes: Any
    ) -> Generator[SpanProtocol, None, None]:
        """Return a no-op span."""
        yield NullSpan()


# Module-level default instance
_tracer: TracerPort = NullTracer()


def get_tracer() -> TracerPort:
    """Get the current tracer instance."""
    return _tracer


def set_tracer(tracer: TracerPort) -> None:
    """Set the tracer instance (for dependency injection)."""
    global _tracer
    _tracer = tracer
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/domain/external/test_tracing.py -v`
Expected: PASS

**Step 5: Create OpenTelemetry adapter**

```python
# backend/app/infrastructure/observability/tracing_adapter.py
"""OpenTelemetry adapter implementing TracerPort."""
from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry import trace
from opentelemetry.trace import SpanKind as OTelSpanKind

from app.domain.external.tracing import TracerPort, SpanKind, SpanProtocol


class OTelSpanAdapter:
    """Adapter wrapping OpenTelemetry span."""

    def __init__(self, span: trace.Span) -> None:
        self._span = span

    def set_attribute(self, key: str, value: Any) -> None:
        self._span.set_attribute(key, value)

    def record_exception(self, exception: BaseException) -> None:
        self._span.record_exception(exception)


class OTelTracerAdapter(TracerPort):
    """OpenTelemetry implementation of TracerPort."""

    _KIND_MAP = {
        SpanKind.INTERNAL: OTelSpanKind.INTERNAL,
        SpanKind.CLIENT: OTelSpanKind.CLIENT,
        SpanKind.SERVER: OTelSpanKind.SERVER,
        SpanKind.PRODUCER: OTelSpanKind.PRODUCER,
        SpanKind.CONSUMER: OTelSpanKind.CONSUMER,
    }

    def __init__(self, service_name: str = "pythinker") -> None:
        self._tracer = trace.get_tracer(service_name)

    @contextmanager
    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        **attributes: Any
    ) -> Generator[SpanProtocol, None, None]:
        otel_kind = self._KIND_MAP.get(kind, OTelSpanKind.INTERNAL)
        with self._tracer.start_as_current_span(name, kind=otel_kind) as span:
            for key, value in attributes.items():
                span.set_attribute(key, value)
            yield OTelSpanAdapter(span)
```

**Step 6: Update flow imports to use domain port**

Replace in each file:
- `backend/app/domain/services/flows/plan_act.py:113`
- `backend/app/domain/services/flows/plan_act_graph.py:69`
- `backend/app/domain/services/flows/tree_of_thoughts_flow.py:55`
- `backend/app/domain/services/langgraph/flow.py:58`

Before:
```python
from app.infrastructure.observability import SpanKind, get_tracer
```

After:
```python
from app.domain.external.tracing import SpanKind, get_tracer
```

**Step 7: Run full test suite**

Run: `cd backend && pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 8: Commit**

```bash
git add backend/app/domain/external/tracing.py backend/app/infrastructure/observability/tracing_adapter.py backend/tests/domain/external/test_tracing.py
git add backend/app/domain/services/flows/plan_act.py backend/app/domain/services/flows/plan_act_graph.py
git add backend/app/domain/services/flows/tree_of_thoughts_flow.py backend/app/domain/services/langgraph/flow.py
git commit -m "refactor: extract TracerPort domain abstraction from infrastructure"
```

---

## Task 2: Implement Security Analyzer Scanning Logic

**Rationale:** The security analyzer currently returns an empty list. Implement basic regex-based pattern matching for common vulnerabilities.

**Files:**
- Modify: `backend/app/domain/services/analyzers/security_analyzer.py:59`
- Test: `backend/tests/domain/services/analyzers/test_security_analyzer.py`

**Step 1: Write failing tests for security patterns**

```python
# backend/tests/domain/services/analyzers/test_security_analyzer.py
"""Tests for security analyzer scanning logic."""
import pytest
from app.domain.services.analyzers.security_analyzer import SecurityAnalyzer
from app.domain.models.vulnerability import Vulnerability, VulnerabilitySeverity


class TestSecurityAnalyzerScan:
    """Test security scanning logic."""

    def test_detect_sql_injection_pattern(self) -> None:
        """Should detect SQL injection patterns."""
        analyzer = SecurityAnalyzer()
        code = '''
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
'''
        vulns = analyzer.scan_code(code, "test.py", "python")
        assert len(vulns) >= 1
        assert any(v.vulnerability_type == "SQL_INJECTION" for v in vulns)

    def test_detect_command_injection_pattern(self) -> None:
        """Should detect command injection patterns."""
        analyzer = SecurityAnalyzer()
        code = '''
import os
def run_cmd(user_input):
    os.system(f"echo {user_input}")
'''
        vulns = analyzer.scan_code(code, "test.py", "python")
        assert len(vulns) >= 1
        assert any(v.vulnerability_type == "COMMAND_INJECTION" for v in vulns)

    def test_detect_hardcoded_secret(self) -> None:
        """Should detect hardcoded secrets."""
        analyzer = SecurityAnalyzer()
        code = '''
API_KEY = "sk-1234567890abcdef"
PASSWORD = "supersecret123"
'''
        vulns = analyzer.scan_code(code, "config.py", "python")
        assert len(vulns) >= 1
        assert any(v.vulnerability_type == "HARDCODED_SECRET" for v in vulns)

    def test_safe_code_no_vulnerabilities(self) -> None:
        """Safe code should return no vulnerabilities."""
        analyzer = SecurityAnalyzer()
        code = '''
def add(a: int, b: int) -> int:
    return a + b
'''
        vulns = analyzer.scan_code(code, "math.py", "python")
        assert len(vulns) == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/services/analyzers/test_security_analyzer.py -v`
Expected: FAIL (scan_code returns empty list)

**Step 3: Implement security scanning with regex patterns**

```python
# Update backend/app/domain/services/analyzers/security_analyzer.py

import re
from typing import Any

from app.domain.models.vulnerability import Vulnerability, VulnerabilitySeverity


class SecurityAnalyzer:
    """Analyzer for detecting security vulnerabilities in code."""

    # Pattern definitions: (pattern, vuln_type, severity, description)
    PYTHON_PATTERNS = [
        # SQL Injection
        (
            r'(?:execute|cursor\.execute|query)\s*\(\s*[f"\'].*\{.*\}',
            "SQL_INJECTION",
            VulnerabilitySeverity.HIGH,
            "Potential SQL injection via string formatting"
        ),
        (
            r'(?:execute|cursor\.execute)\s*\(\s*["\'].*%s',
            "SQL_INJECTION",
            VulnerabilitySeverity.HIGH,
            "Potential SQL injection via % formatting"
        ),
        # Command Injection
        (
            r'os\.system\s*\(\s*[f"\'].*\{.*\}',
            "COMMAND_INJECTION",
            VulnerabilitySeverity.CRITICAL,
            "Command injection via os.system with f-string"
        ),
        (
            r'subprocess\.(?:call|run|Popen)\s*\([^)]*shell\s*=\s*True',
            "COMMAND_INJECTION",
            VulnerabilitySeverity.HIGH,
            "Shell=True with subprocess is dangerous"
        ),
        # Hardcoded Secrets
        (
            r'(?:api_key|apikey|secret|password|passwd|token)\s*=\s*["\'][a-zA-Z0-9_\-]{8,}["\']',
            "HARDCODED_SECRET",
            VulnerabilitySeverity.MEDIUM,
            "Potential hardcoded secret detected"
        ),
        # Path Traversal
        (
            r'open\s*\(\s*(?:request\.|user_|input)',
            "PATH_TRAVERSAL",
            VulnerabilitySeverity.HIGH,
            "Potential path traversal via user input in file open"
        ),
    ]

    def scan_code(
        self, code: str, file_path: str, language: str
    ) -> list[Vulnerability]:
        """
        Scan code for security vulnerabilities using regex patterns.

        Args:
            code: Source code to scan
            file_path: Path to the file
            language: Programming language

        Returns:
            List of vulnerabilities found
        """
        vulnerabilities: list[Vulnerability] = []

        if language.lower() not in ("python", "py"):
            # For now, only Python is supported
            return vulnerabilities

        lines = code.split("\n")

        for pattern, vuln_type, severity, description in self.PYTHON_PATTERNS:
            regex = re.compile(pattern, re.IGNORECASE)
            for line_num, line in enumerate(lines, start=1):
                if regex.search(line):
                    vulnerabilities.append(
                        Vulnerability(
                            vulnerability_type=vuln_type,
                            severity=severity,
                            file_path=file_path,
                            line_number=line_num,
                            description=description,
                            code_snippet=line.strip()[:100],
                        )
                    )

        return vulnerabilities

    def get_summary(self, vulnerabilities: list[Vulnerability]) -> dict[str, Any]:
        """Get summary of vulnerabilities by severity."""
        summary = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "total": len(vulnerabilities),
        }
        for vuln in vulnerabilities:
            if vuln.severity == VulnerabilitySeverity.CRITICAL:
                summary["critical"] += 1
            elif vuln.severity == VulnerabilitySeverity.HIGH:
                summary["high"] += 1
            elif vuln.severity == VulnerabilitySeverity.MEDIUM:
                summary["medium"] += 1
            else:
                summary["low"] += 1
        return summary
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/domain/services/analyzers/test_security_analyzer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/analyzers/security_analyzer.py backend/tests/domain/services/analyzers/test_security_analyzer.py
git commit -m "feat: implement regex-based security scanning in SecurityAnalyzer"
```

---

## Task 3: Implement Settings Persistence for Auto-Run Toggle

**Rationale:** The frontend has a TODO for persisting the auto-run toggle setting.

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue:1011`
- Modify: `frontend/src/stores/settings.ts` (or create if not exists)
- Test: Manual testing in browser

**Step 1: Check if settings store exists**

Run: `ls frontend/src/stores/`

**Step 2: Create or update settings store**

```typescript
// frontend/src/stores/settings.ts
import { defineStore } from 'pinia';
import { ref, watch } from 'vue';

const SETTINGS_KEY = 'pythinker_settings';

interface Settings {
  autoRunEnabled: boolean;
}

const defaultSettings: Settings = {
  autoRunEnabled: true,
};

function loadSettings(): Settings {
  try {
    const stored = localStorage.getItem(SETTINGS_KEY);
    if (stored) {
      return { ...defaultSettings, ...JSON.parse(stored) };
    }
  } catch (e) {
    console.warn('Failed to load settings:', e);
  }
  return defaultSettings;
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<Settings>(loadSettings());

  // Persist on change
  watch(
    settings,
    (newSettings) => {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(newSettings));
    },
    { deep: true }
  );

  const toggleAutoRun = () => {
    settings.value.autoRunEnabled = !settings.value.autoRunEnabled;
  };

  return {
    settings,
    toggleAutoRun,
  };
});
```

**Step 3: Update ChatPage.vue to use settings store**

Replace in `frontend/src/pages/ChatPage.vue:1009-1013`:

Before:
```typescript
const handleToggleAutoRun = () => {
  // TODO: Implement settings persistence
  console.log('Toggle auto-run preference');
};
```

After:
```typescript
import { useSettingsStore } from '@/stores/settings';

const settingsStore = useSettingsStore();

const handleToggleAutoRun = () => {
  settingsStore.toggleAutoRun();
};
```

**Step 4: Run linting and type-check**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: No errors

**Step 5: Commit**

```bash
git add frontend/src/stores/settings.ts frontend/src/pages/ChatPage.vue
git commit -m "feat(frontend): implement settings persistence for auto-run toggle"
```

---

## Task 4: Implement Report Rating Backend API

**Rationale:** Frontend has a TODO to send report ratings to the backend.

**Files:**
- Create: `backend/app/interfaces/api/rating_routes.py`
- Modify: `backend/app/main.py` (register routes)
- Modify: `frontend/src/pages/ChatPage.vue:1047-1050`
- Test: `backend/tests/interfaces/api/test_rating_routes.py`

**Step 1: Write failing test for rating endpoint**

```python
# backend/tests/interfaces/api/test_rating_routes.py
"""Tests for rating API endpoints."""
import pytest
from httpx import AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_submit_rating_success():
    """Should accept valid rating submission."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 4,
            },
        )
    assert response.status_code == 201
    assert response.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_submit_rating_invalid_value():
    """Should reject invalid rating values."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 6,  # Invalid: must be 1-5
            },
        )
    assert response.status_code == 422
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/interfaces/api/test_rating_routes.py -v`
Expected: FAIL (404 or module not found)

**Step 3: Implement rating endpoint**

```python
# backend/app/interfaces/api/rating_routes.py
"""Rating API endpoints."""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ratings", tags=["ratings"])


class RatingRequest(BaseModel):
    """Request body for submitting a rating."""
    session_id: str
    report_id: str
    rating: int = Field(ge=1, le=5, description="Rating from 1 to 5")
    feedback: str | None = None


class RatingResponse(BaseModel):
    """Response for rating submission."""
    status: str
    message: str


@router.post("", response_model=RatingResponse, status_code=201)
async def submit_rating(request: RatingRequest) -> RatingResponse:
    """Submit a rating for a report.

    For now, this logs the rating. Future: persist to database.
    """
    logger.info(
        "Rating received",
        extra={
            "session_id": request.session_id,
            "report_id": request.report_id,
            "rating": request.rating,
            "feedback": request.feedback,
        },
    )
    return RatingResponse(
        status="accepted",
        message=f"Rating of {request.rating}/5 recorded",
    )
```

**Step 4: Register routes in main.py**

Add to `backend/app/main.py`:

```python
from app.interfaces.api.rating_routes import router as rating_router

app.include_router(rating_router, prefix="/api/v1")
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/interfaces/api/test_rating_routes.py -v`
Expected: PASS

**Step 6: Update frontend to call API**

Replace in `frontend/src/pages/ChatPage.vue:1047-1050`:

```typescript
const handleReportRate = async (rating: number) => {
  if (!currentReport.value) return;

  try {
    await fetch('/api/v1/ratings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId.value,
        report_id: currentReport.value.id,
        rating,
      }),
    });
  } catch (error) {
    console.error('Failed to submit rating:', error);
  }
};
```

**Step 7: Commit**

```bash
git add backend/app/interfaces/api/rating_routes.py backend/app/main.py
git add backend/tests/interfaces/api/test_rating_routes.py frontend/src/pages/ChatPage.vue
git commit -m "feat: add report rating API and frontend integration"
```

---

## Task 5: Implement Language Detection/Configuration for Discuss Flow

**Rationale:** The discuss flow has hardcoded "English" language.

**Files:**
- Modify: `backend/app/domain/services/flows/discuss.py:186`
- Modify: `backend/app/core/config.py` (add setting)
- Test: `backend/tests/domain/services/flows/test_discuss.py`

**Step 1: Write failing test**

```python
# Add to backend/tests/domain/services/flows/test_discuss.py

@pytest.mark.asyncio
async def test_discuss_uses_configured_language(mock_llm, mock_agent_repo):
    """Discuss flow should use configured language from settings."""
    from app.core.config import get_settings

    settings = get_settings()
    settings.default_language = "Chinese"

    # ... setup flow and verify language is passed correctly
```

**Step 2: Add language configuration**

Add to `backend/app/core/config.py`:

```python
# In Settings class
default_language: str = "English"
```

**Step 3: Update discuss.py to use config**

Replace in `backend/app/domain/services/flows/discuss.py:186`:

Before:
```python
language="English",  # TODO: Detect or configure language
```

After:
```python
from app.core.config import get_settings

# In the method:
settings = get_settings()
language=settings.default_language,
```

**Step 4: Run tests**

Run: `cd backend && pytest tests/domain/services/flows/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/flows/discuss.py backend/app/core/config.py
git commit -m "feat: make discuss flow language configurable via settings"
```

---

## Task 6: Handle Wait Event in SharePage

**Rationale:** Low priority - the wait event handler is empty.

**Files:**
- Modify: `frontend/src/pages/SharePage.vue:410`

**Step 1: Implement wait event handler**

Replace in `frontend/src/pages/SharePage.vue:409-410`:

Before:
```typescript
} else if (event.event === 'wait') {
  // TODO: handle wait event
}
```

After:
```typescript
} else if (event.event === 'wait') {
  // Wait event indicates agent is paused awaiting user input
  // The UI already shows appropriate waiting states
  console.debug('Agent waiting for user input');
}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/SharePage.vue
git commit -m "fix(frontend): add wait event handler in SharePage"
```

---

## Task 7: Change File Download to Real Stream

**Rationale:** Low priority - currently buffering entire file into BytesIO.

**Files:**
- Modify: `backend/app/infrastructure/external/sandbox/docker_sandbox.py:591`

**Step 1: Update to streaming response**

Replace in `docker_sandbox.py:585-592`:

```python
async def download_file(self, path: str) -> BinaryIO:
    """Download a file from the sandbox.

    Args:
        path: File path in sandbox

    Returns:
        File content as binary stream
    """
    async with self.client.stream("GET", f"{self.base_url}/api/v1/file/download", params={"path": path}) as response:
        response.raise_for_status()
        # For now, still buffer for compatibility
        # True streaming would require API changes
        content = b""
        async for chunk in response.aiter_bytes():
            content += chunk
        return io.BytesIO(content)
```

**Step 2: Commit**

```bash
git add backend/app/infrastructure/external/sandbox/docker_sandbox.py
git commit -m "refactor: use streaming request for file download (still buffered)"
```

---

## Task 8: Refactor _handle_tool_event in Agent Task Runner

**Rationale:** The function is marked for refactoring - extract into separate tool event handlers.

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py:676-750` (approximate)
- Create: `backend/app/domain/services/tool_event_handler.py`
- Test: `backend/tests/domain/services/test_tool_event_handler.py`

**Step 1: Write failing test**

```python
# backend/tests/domain/services/test_tool_event_handler.py
"""Tests for tool event handler."""
import pytest
from app.domain.services.tool_event_handler import ToolEventHandler
from app.domain.models.event import ToolEvent


class TestToolEventHandler:
    """Test tool event handling logic."""

    def test_handle_shell_event(self) -> None:
        """Should extract command and cwd for shell events."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_name="shell",
            function_name="execute",
            function_args={"command": "ls -la", "exec_dir": "/home"},
            status="called",
        )

        handler.process(event)

        assert event.action_type == "run"
        assert event.command == "ls -la"
        assert event.cwd == "/home"

    def test_handle_file_event(self) -> None:
        """Should extract file path for file events."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_name="file",
            function_name="read",
            function_args={"file": "/path/to/file.txt"},
            status="called",
        )

        handler.process(event)

        assert event.file_path == "/path/to/file.txt"
```

**Step 2: Extract handler class**

```python
# backend/app/domain/services/tool_event_handler.py
"""Handler for enriching tool events with action metadata."""
from app.domain.models.event import ToolEvent


class ToolEventHandler:
    """Enriches ToolEvents with action-specific metadata."""

    def process(self, event: ToolEvent) -> None:
        """Process event and add action metadata in-place."""
        handler = getattr(self, f"_handle_{event.tool_name}", None)
        if handler:
            handler(event)

    def _handle_shell(self, event: ToolEvent) -> None:
        event.action_type = "run"
        event.command = event.function_args.get("command")
        event.cwd = event.function_args.get("exec_dir")

    def _handle_code_executor(self, event: ToolEvent) -> None:
        event.action_type = "run"
        event.command = event.function_args.get("code") or event.function_args.get("command")

    def _handle_file(self, event: ToolEvent) -> None:
        event.file_path = event.function_args.get("file")

    # Add more handlers as needed...
```

**Step 3: Update agent_task_runner to use handler**

Replace the inline logic with:

```python
from app.domain.services.tool_event_handler import ToolEventHandler

# In __init__:
self._tool_event_handler = ToolEventHandler()

# In _handle_tool_event:
async def _handle_tool_event(self, event: ToolEvent):
    """Generate tool content"""
    try:
        self._tool_event_handler.process(event)
        # ... rest of the method
```

**Step 4: Run tests**

Run: `cd backend && pytest tests/domain/services/test_tool_event_handler.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/tool_event_handler.py backend/tests/domain/services/test_tool_event_handler.py
git add backend/app/domain/services/agent_task_runner.py
git commit -m "refactor: extract ToolEventHandler from agent task runner"
```

---

## Remaining Low-Priority TODOs

The following TODOs are lower priority and can be addressed later:

1. **`agent_domain_service.py:664`** - "raise api exception": The current behavior (yielding error event) is acceptable for SSE streaming. A proper fix would require architectural changes to error handling.

2. **`plan_act.py:1518`** - "move to task runner": This requires significant refactoring of session handling. Document as technical debt.

3. **`agent_task_runner.py:1009`** - "move to tool function": Similar refactoring, lower impact.

These are tracked for future sprints but don't block current functionality.

---

## Execution Summary

| Task | Priority | Estimated Complexity |
|------|----------|---------------------|
| 1. TracerPort Abstraction | High | Medium |
| 2. Security Analyzer | High | Medium |
| 3. Settings Persistence | Medium | Low |
| 4. Report Rating API | Medium | Low |
| 5. Language Configuration | Medium | Low |
| 6. Wait Event Handler | Low | Trivial |
| 7. File Download Stream | Low | Trivial |
| 8. Tool Event Handler Refactor | Medium | Medium |

---

**Plan complete and saved to `docs/plans/2026-02-04-todo-implementation.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
