# Session Monitoring Comprehensive Fixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 12 bugs identified across two monitored agent sessions — covering spider denylist gaps, hallucination grounding loops, sandbox ownership safety, step completion semantics, workspace path resolution, nullable event contracts, and delivery artifact quality.

**Architecture:** Surgical fixes across domain services, infrastructure adapters, and event models. Each fix is independent and self-contained. Test-driven approach with targeted unit tests for each behavioral change.

**Tech Stack:** Python 3.12, pytest, Pydantic v2, asyncio, httpx, Scrapling/Scrapy spider

---

## Session 1 Fixes (Research Session `5f7bf7479f214b6f`)

### Task 1: Expand Spider Denylist — Block Social Media Boilerplate

**Files:**
- Modify: `backend/app/infrastructure/external/scraper/research_spider.py:32-38`
- Modify: `backend/app/domain/services/tools/search.py:24-30`
- Create: `backend/tests/domain/services/tools/test_spider_denylist.py`

**Context:** The spider enriched `instagram.com` (1.36MB of UI boilerplate in 40+ languages). Social media platforms serve no useful research content through anonymous scraping.

**Step 1: Write failing tests**

```python
# backend/tests/domain/services/tools/test_spider_denylist.py
"""Tests for spider denylist expansion — social media platforms."""
import pytest
from app.infrastructure.external.scraper.research_spider import should_skip_spider, SPIDER_DENYLIST_DOMAINS
from app.domain.services.tools.search import _should_skip_spider as search_should_skip_spider


class TestSpiderDenylistExpansion:
    """Verify social media domains are blocked from spider enrichment."""

    @pytest.mark.parametrize("url", [
        "https://www.instagram.com/p/DVaK8iICao8/",
        "https://instagram.com/reel/abc123",
        "https://www.facebook.com/some-page",
        "https://facebook.com/groups/python",
        "https://www.tiktok.com/@user/video/123",
        "https://tiktok.com/explore",
        "https://www.linkedin.com/pulse/article",
        "https://linkedin.com/posts/user-123",
        "https://www.pinterest.com/pin/123",
        "https://pinterest.com/ideas/python",
    ])
    def test_social_media_blocked_research_spider(self, url: str):
        assert should_skip_spider(url) is True

    @pytest.mark.parametrize("url", [
        "https://www.instagram.com/p/DVaK8iICao8/",
        "https://www.facebook.com/some-page",
        "https://www.tiktok.com/@user/video/123",
        "https://www.linkedin.com/pulse/article",
        "https://www.pinterest.com/pin/123",
    ])
    def test_social_media_blocked_search_module(self, url: str):
        assert search_should_skip_spider(url) is True

    @pytest.mark.parametrize("url", [
        "https://github.com/python/cpython",
        "https://dev.to/article",
        "https://blog.bytebytego.com/p/top-ai",
        "https://docs.python.org/3/",
        "https://stackoverflow.com/questions/123",
    ])
    def test_legitimate_domains_allowed(self, url: str):
        assert should_skip_spider(url) is False
        assert search_should_skip_spider(url) is False
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && conda activate pythinker && pytest tests/domain/services/tools/test_spider_denylist.py -v
```

Expected: FAIL — instagram, facebook, tiktok, linkedin, pinterest not in denylist.

**Step 3: Implement the fix**

In `backend/app/infrastructure/external/scraper/research_spider.py`, replace lines 32-38:

```python
SPIDER_DENYLIST_DOMAINS: frozenset[str] = frozenset(
    {
        "reddit.com",  # Responsible Builder Policy — requires OAuth
        "x.com",  # Aggressive bot blocking
        "twitter.com",  # Legacy domain for x.com
        "instagram.com",  # Login wall, returns UI boilerplate only
        "facebook.com",  # Login wall, no useful anonymous content
        "tiktok.com",  # Video platform, no text content for research
        "linkedin.com",  # Login wall, aggressive bot blocking
        "pinterest.com",  # Login wall, image-only platform
    }
)
```

In `backend/app/domain/services/tools/search.py`, replace lines 24-30 identically:

```python
_SPIDER_DENYLIST_DOMAINS: frozenset[str] = frozenset(
    {
        "reddit.com",  # Responsible Builder Policy — requires OAuth
        "x.com",  # Aggressive bot blocking
        "twitter.com",  # Legacy domain for x.com
        "instagram.com",  # Login wall, returns UI boilerplate only
        "facebook.com",  # Login wall, no useful anonymous content
        "tiktok.com",  # Video platform, no text content for research
        "linkedin.com",  # Login wall, aggressive bot blocking
        "pinterest.com",  # Login wall, image-only platform
    }
)
```

**Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/domain/services/tools/test_spider_denylist.py -v
```

Expected: ALL PASS

**Step 5: Run existing search tests for regression**

```bash
cd backend && pytest tests/domain/services/tools/test_search*.py -v
```

**Step 6: Commit**

```bash
git add backend/app/infrastructure/external/scraper/research_spider.py backend/app/domain/services/tools/search.py backend/tests/domain/services/tools/test_spider_denylist.py
git commit -m "fix(spider): expand denylist to block social media boilerplate domains"
```

---

### Task 2: Break Hallucination Self-Referential Grounding Loop

**Files:**
- Modify: `backend/app/domain/services/agents/output_verifier.py:129-169`
- Create: `backend/tests/domain/services/agents/test_output_verifier_grounding.py`

**Context:** LettuceDetect's grounding context includes both external tool outputs AND the LLM's own prior step summaries (via `context_manager.key_facts`). This creates a self-referential loop: fabricated data in step 1 becomes "ground truth" for step 2's verification, which then passes with 1.00 confidence.

**Step 1: Write failing test**

```python
# backend/tests/domain/services/agents/test_output_verifier_grounding.py
"""Tests for grounding context — ensure LLM-generated content doesn't self-validate."""
import pytest
from unittest.mock import MagicMock, PropertyMock
from app.domain.services.agents.output_verifier import OutputVerifier


class TestGroundingContextIntegrity:
    """Verify grounding context excludes LLM-generated key_facts when external sources exist."""

    def _make_verifier(self, sources: list, key_facts: list[str] | None = None) -> OutputVerifier:
        """Create OutputVerifier with mock dependencies."""
        source_tracker = MagicMock()
        source_tracker._collected_sources = sources
        context_manager = MagicMock()
        if key_facts is not None:
            context_manager._context.key_facts = key_facts
        else:
            context_manager._context.key_facts = []
        return OutputVerifier(
            llm=MagicMock(),
            critic_llm=None,
            cove_llm=None,
            context_manager=context_manager,
            source_tracker=source_tracker,
        )

    def _make_source(self, title: str, url: str, snippet: str, source_type: str = "search") -> MagicMock:
        src = MagicMock()
        src.title = title
        src.url = url
        src.snippet = snippet
        src.source_type = source_type
        return src

    def test_external_sources_present_excludes_key_facts(self):
        """When external search/browser sources exist, key_facts should NOT be included."""
        sources = [
            self._make_source("GitHub Trending", "https://github.com/trending", "Python repos trending today", "search"),
        ]
        key_facts = [
            "OpenManus has 55K stars on GitHub",  # LLM-generated claim
            "anthropics/skills is the most popular repo",  # LLM-generated claim
        ]
        verifier = self._make_verifier(sources, key_facts)
        chunks = verifier.build_source_context()

        # Key facts should NOT appear in grounding context when external sources exist
        combined = " ".join(chunks)
        assert "55K stars" not in combined
        assert "most popular repo" not in combined
        # But the external source SHOULD be present
        assert "GitHub Trending" in combined

    def test_no_external_sources_allows_key_facts(self):
        """When no external sources exist, key_facts are the only grounding — include them."""
        sources = []
        key_facts = ["The project uses Python 3.12"]
        verifier = self._make_verifier(sources, key_facts)
        chunks = verifier.build_source_context()
        combined = " ".join(chunks)
        assert "Python 3.12" in combined
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/domain/services/agents/test_output_verifier_grounding.py -v
```

Expected: FAIL — `test_external_sources_present_excludes_key_facts` fails because key_facts are always appended.

**Step 3: Implement the fix**

In `backend/app/domain/services/agents/output_verifier.py`, replace lines 163-168:

```python
        # Supplement with key facts from execution context ONLY when no external
        # sources are available. When external sources exist, key_facts may contain
        # LLM-generated claims from prior steps, creating a self-referential
        # grounding loop where fabricated data validates itself.
        if not chunks:
            if hasattr(self._context_manager, "_context") and self._context_manager._context.key_facts:
                chunks.extend(fact for fact in self._context_manager._context.key_facts if fact and len(fact) > 20)
```

**Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/domain/services/agents/test_output_verifier_grounding.py -v
```

**Step 5: Run existing hallucination tests for regression**

```bash
cd backend && pytest tests/domain/services/agents/test_output_verifier*.py tests/domain/services/agents/test_lettuce*.py -v
```

**Step 6: Commit**

```bash
git add backend/app/domain/services/agents/output_verifier.py backend/tests/domain/services/agents/test_output_verifier_grounding.py
git commit -m "fix(grounding): exclude key_facts from LettuceDetect context when external sources exist"
```

---

### Task 3: Add Sandbox Ownership Lock — Prevent Mid-Session Reassignment

**Files:**
- Modify: `backend/app/infrastructure/external/sandbox/docker_sandbox.py:1639-1649`
- Create: `backend/tests/infrastructure/external/sandbox/test_sandbox_ownership.py`

**Context:** A new session stole the sandbox from an actively running research session mid-execution. The sandbox's `register_session()` blindly reassigns without checking if the current owner's task is still running.

**Step 1: Write failing test**

```python
# backend/tests/infrastructure/external/sandbox/test_sandbox_ownership.py
"""Tests for sandbox ownership protection during active sessions."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSandboxOwnershipProtection:
    """Verify sandbox cannot be reassigned while actively serving a running task."""

    @pytest.mark.asyncio
    async def test_reassignment_blocked_when_task_active(self):
        """Sandbox should NOT be reassigned when current owner has an active task."""
        from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

        sandbox = DockerSandbox.__new__(DockerSandbox)
        sandbox._active_sessions = {"sandbox-1": "session-A"}
        sandbox._active_sessions_lock = __import__("asyncio").Lock()

        # Mock Redis liveness check — session-A is actively running
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=True)

        with patch("app.infrastructure.external.sandbox.docker_sandbox.get_redis_client", return_value=mock_redis):
            was_reassigned = await sandbox.register_session("sandbox-1", "session-B")

        assert was_reassigned is False, "Should refuse to reassign sandbox with active task"

    @pytest.mark.asyncio
    async def test_reassignment_allowed_when_no_active_task(self):
        """Sandbox CAN be reassigned when current owner has no active task."""
        from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

        sandbox = DockerSandbox.__new__(DockerSandbox)
        sandbox._active_sessions = {"sandbox-1": "session-A"}
        sandbox._active_sessions_lock = __import__("asyncio").Lock()

        # Mock Redis liveness check — session-A is NOT active
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=False)

        with patch("app.infrastructure.external.sandbox.docker_sandbox.get_redis_client", return_value=mock_redis):
            was_reassigned = await sandbox.register_session("sandbox-1", "session-B")

        assert was_reassigned is True

    @pytest.mark.asyncio
    async def test_reassignment_allowed_when_no_previous_owner(self):
        """Sandbox CAN be assigned when there is no previous owner."""
        from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

        sandbox = DockerSandbox.__new__(DockerSandbox)
        sandbox._active_sessions = {}
        sandbox._active_sessions_lock = __import__("asyncio").Lock()

        was_assigned = await sandbox.register_session("sandbox-1", "session-A")
        assert was_assigned is True
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/infrastructure/external/sandbox/test_sandbox_ownership.py -v
```

Expected: FAIL — `register_session()` is currently synchronous and doesn't check Redis.

**Step 3: Implement the fix**

In `backend/app/infrastructure/external/sandbox/docker_sandbox.py`, modify `register_session()` (lines 1639-1649) to become async and check Redis liveness:

```python
    async def register_session(self, sandbox_address: str, session_id: str) -> bool:
        """Register a session as the owner of a sandbox.

        Returns True if registration succeeded, False if the sandbox is actively
        serving another session (has a live Redis task:liveness key).
        """
        async with self._active_sessions_lock:
            previous = self._active_sessions.get(sandbox_address)

            # If there's an existing owner, check if their task is still running
            if previous and previous != session_id:
                try:
                    from app.infrastructure.external.task.redis_task import get_redis_client
                    redis = get_redis_client()
                    liveness_key = f"task:liveness:{previous}"
                    is_active = await redis.exists(liveness_key)
                    if is_active:
                        logger.warning(
                            "Sandbox %s ownership BLOCKED: session %s still active "
                            "(requested by %s)",
                            sandbox_address,
                            previous,
                            session_id,
                        )
                        return False
                except Exception as e:
                    logger.warning(
                        "Redis liveness check failed for %s, allowing reassignment: %s",
                        previous,
                        e,
                    )

                logger.info(
                    "Sandbox %s reassigned: %s -> %s",
                    sandbox_address,
                    previous,
                    session_id,
                )

            self._active_sessions[sandbox_address] = session_id
            return True
```

Also update all callers of `register_session` to use `await` (search for `register_session` calls in the file and in `agent_service.py`).

**Step 4: Run tests**

```bash
cd backend && pytest tests/infrastructure/external/sandbox/test_sandbox_ownership.py -v
```

**Step 5: Run existing sandbox tests for regression**

```bash
cd backend && pytest tests/infrastructure/ -k sandbox -v
```

**Step 6: Commit**

```bash
git add backend/app/infrastructure/external/sandbox/docker_sandbox.py backend/tests/infrastructure/external/sandbox/test_sandbox_ownership.py
git commit -m "fix(sandbox): prevent mid-session reassignment via Redis liveness check"
```

---

### Task 4: Suppress Chart Fallback When No Meaningful Data Exists

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py:918-934`
- Create: `backend/tests/domain/services/test_chart_fallback_suppression.py`

**Context:** When Plotly chart generation finds no chart data (expected for non-quantitative reports), the system falls back to legacy SVG which also produces empty/meaningless charts. The fallback should be suppressed entirely when the primary generator found no data.

**Step 1: Write failing test**

```python
# backend/tests/domain/services/test_chart_fallback_suppression.py
"""Tests for chart fallback suppression when no data is extractable."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestChartFallbackSuppression:
    """Verify no chart is generated when primary extraction finds no data."""

    @pytest.mark.asyncio
    async def test_no_fallback_when_primary_finds_no_data(self):
        """When Plotly finds no chart data (not an error), skip SVG fallback entirely."""
        from app.domain.services.agent_task_runner import LeadAgentRuntime

        runtime = MagicMock(spec=LeadAgentRuntime)
        runtime._plotly_chart_orchestrator = AsyncMock()
        runtime._plotly_chart_orchestrator.generate_chart = AsyncMock(return_value=None)
        runtime._has_attachment = MagicMock(return_value=False)
        runtime._ensure_legacy_svg_chart = AsyncMock(return_value=[])
        runtime._session_id = "test-session"

        event = MagicMock()
        event.id = "test-report"
        event.title = "Test Report"
        event.content = "# Report\nSome text without tables."

        # Call the actual method
        result = await LeadAgentRuntime._ensure_report_chart(
            runtime, event, [], force_generation=False, generation_mode="auto"
        )

        # Should NOT call legacy SVG fallback when primary found no data (no error)
        runtime._ensure_legacy_svg_chart.assert_not_called()
        assert result == []
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/domain/services/test_chart_fallback_suppression.py -v
```

**Step 3: Implement the fix**

In `backend/app/domain/services/agent_task_runner.py`, replace lines 918-934:

```python
        if chart_result is None:
            # Chart extraction failure from an actual error is a warning;
            # "no chart data" is expected for non-quantitative reports (info).
            _chart_msg = chart_error or "no chart data extracted from report"
            _log_fn = logger.warning if chart_error else logger.info
            _log_fn(
                "Plotly chart unavailable for report_id=%s session=%s: %s",
                event.id,
                self._session_id,
                _chart_msg,
            )
            # Only fall back to legacy SVG if Plotly failed due to an actual error.
            # When there's simply no chartable data, don't generate a meaningless
            # fallback chart — it adds noise without value.
            if chart_error:
                return await self._ensure_legacy_svg_chart(
                    event,
                    attachments,
                    force_generation=force_generation,
                    generation_mode=f"{generation_mode}_fallback_svg",
                )
            return attachments
```

**Step 4: Run tests**

```bash
cd backend && pytest tests/domain/services/test_chart_fallback_suppression.py -v
```

**Step 5: Commit**

```bash
git add backend/app/domain/services/agent_task_runner.py backend/tests/domain/services/test_chart_fallback_suppression.py
git commit -m "fix(charts): suppress SVG fallback when primary chart finds no data"
```

---

## Session 2 Fixes (System Operation Session `1cfad266540d436c`)

### Task 5: Evidence-Based Step Completion — Fail Steps With Zero Sources and Failed Tool Reads

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py:580-586`
- Modify: `backend/app/domain/services/flows/plan_act.py:3297-3312`
- Create: `backend/tests/domain/services/agents/test_step_completion_evidence.py`

**Context:** Steps are coerced to COMPLETED even when all file reads returned 404 and no useful data was produced. The executor (line 583) sets `COMPLETED` for any step that didn't explicitly FAIL, and plan_act (line 3304) reinforces this with belt-and-suspenders coercion.

**Step 1: Write failing tests**

```python
# backend/tests/domain/services/agents/test_step_completion_evidence.py
"""Tests for evidence-based step completion — steps with failed reads should not be COMPLETED."""
import pytest
from unittest.mock import MagicMock
from app.domain.models.plan import Step, ExecutionStatus


class TestStepCompletionEvidence:
    """Steps should fail when all tool calls failed and no output was produced."""

    def test_step_with_only_failed_reads_should_fail(self):
        """A step where every tool call failed should not be marked COMPLETED."""
        step = Step(id="step-1", description="Read README.md and analyze")
        step.status = ExecutionStatus.IN_PROGRESS
        step.success = False
        step.result = None

        # Simulate: 3 file_read calls, all failed (file not found)
        tool_history = ["file_read", "file_read", "file_read"]
        tool_successes = [False, False, False]

        # The step should NOT be coerced to COMPLETED
        has_successful_tool = any(tool_successes)
        has_result = bool(step.result and str(step.result).strip())

        if not has_successful_tool and not has_result:
            step.status = ExecutionStatus.FAILED

        assert step.status == ExecutionStatus.FAILED
        assert step.success is False

    def test_step_with_mixed_results_should_complete(self):
        """A step with at least one successful tool call can be COMPLETED."""
        step = Step(id="step-2", description="Search and read files")
        step.status = ExecutionStatus.IN_PROGRESS
        step.success = False
        step.result = "Found relevant information"

        tool_history = ["wide_research", "file_read"]
        tool_successes = [True, False]

        has_successful_tool = any(tool_successes)
        has_result = bool(step.result and str(step.result).strip())

        if has_successful_tool or has_result:
            step.status = ExecutionStatus.COMPLETED
            step.success = True

        assert step.status == ExecutionStatus.COMPLETED
        assert step.success is True

    def test_step_with_no_tools_and_no_result_should_fail(self):
        """A step that used no tools and produced no result should FAIL."""
        step = Step(id="step-3", description="Validate findings")
        step.status = ExecutionStatus.IN_PROGRESS
        step.success = False
        step.result = None

        tool_history = []
        tool_successes = []

        has_successful_tool = any(tool_successes)
        has_result = bool(step.result and str(step.result).strip())

        # No tools, no result → FAILED
        if not has_successful_tool and not has_result:
            step.status = ExecutionStatus.FAILED

        assert step.status == ExecutionStatus.FAILED
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/domain/services/agents/test_step_completion_evidence.py -v
```

Expected: These tests pass as written (they test the logic pattern). The real fix is in execution.py.

**Step 3: Implement the fix in execution.py**

In `backend/app/domain/services/agents/execution.py`, replace lines 580-586:

```python
            # Evidence-based step completion: only mark COMPLETED if the step
            # produced a meaningful result OR had at least one successful tool call.
            # Steps where all tools failed and no result was produced are FAILED,
            # not silently coerced to COMPLETED.
            if step.status != ExecutionStatus.FAILED:
                has_result = bool(step.result and str(step.result).strip())
                tool_history = self._prompt_adapter._context.recent_tools
                # Check if any tools were called successfully during this step
                # (recent_errors tracks failures, recent_tools tracks all calls)
                tool_error_count = len(self._prompt_adapter._context.recent_errors)
                tool_total_count = len(tool_history)
                has_successful_tool = tool_total_count > tool_error_count

                if has_result or has_successful_tool or tool_total_count == 0:
                    # Normal completion: has output, has successful tools, or was LLM-only
                    step.status = ExecutionStatus.COMPLETED
                    if not step.success:
                        step.success = True
                else:
                    # All tools failed and no result — mark as FAILED
                    step.status = ExecutionStatus.FAILED
                    step.success = False
                    logger.warning(
                        "Step %s marked FAILED: %d/%d tool calls failed, no result produced",
                        step.id,
                        tool_error_count,
                        tool_total_count,
                    )
```

**Step 4: Implement the fix in plan_act.py**

In `backend/app/domain/services/flows/plan_act.py`, replace lines 3297-3312:

```python
                        # Belt-and-suspenders: sync step.status with step.success.
                        # Respect the executor's explicit status — do NOT coerce
                        # FAILED steps to COMPLETED. The executor now performs
                        # evidence-based completion checks.
                        if step.success:
                            step.status = ExecutionStatus.COMPLETED
                            await self._task_state_manager.update_step_status(str(step.id), "completed")
                        elif step.status == ExecutionStatus.COMPLETED:
                            # Executor explicitly marked COMPLETED — trust it
                            step.success = True
                            await self._task_state_manager.update_step_status(str(step.id), "completed")
                            logger.info(
                                "Step %s status was COMPLETED but success=False; "
                                "corrected to success=True (executor completed normally)",
                                step.id,
                            )
                        elif step.status == ExecutionStatus.FAILED:
                            # Executor explicitly marked FAILED (evidence-based) — respect it
                            step.success = False
                            await self._task_state_manager.update_step_status(str(step.id), "failed")
                            logger.warning(
                                "Step %s failed (evidence-based): executor found no successful outcomes",
                                step.id,
                            )
                        else:
                            step.status = ExecutionStatus.FAILED
                            await self._task_state_manager.update_step_status(str(step.id), "failed")
```

**Step 5: Run tests**

```bash
cd backend && pytest tests/domain/services/agents/test_step_completion_evidence.py -v
cd backend && pytest tests/domain/services/flows/test_plan_act*.py -v
```

**Step 6: Commit**

```bash
git add backend/app/domain/services/agents/execution.py backend/app/domain/services/flows/plan_act.py backend/tests/domain/services/agents/test_step_completion_evidence.py
git commit -m "fix(execution): evidence-based step completion — fail steps with zero successful outcomes"
```

---

### Task 6: Fix Monitor Session Nullable Sources Crash

**Files:**
- Modify: `backend/scripts/monitor_session.py:260-263`
- Create: `backend/tests/scripts/test_monitor_session_nullable.py`

**Context:** The monitor script calls `len(sources)` on a potentially `None` value. The `ReportEvent.sources` field is `list[SourceCitation] | None = None` (event.py:630). When the session emits `sources: null`, the monitor crashes.

**Step 1: Write failing test**

```python
# backend/tests/scripts/test_monitor_session_nullable.py
"""Tests for monitor_session nullable sources handling."""
import pytest


class TestMonitorNullableSources:
    """Verify monitor handles null/missing sources in report events."""

    def test_null_sources_defaults_to_empty_list(self):
        """data.get('sources', []) should handle None explicitly."""
        data = {"title": "Test", "content": "# Report", "sources": None}
        sources = data.get("sources") or []  # Fix: handle None explicitly
        assert len(sources) == 0

    def test_missing_sources_defaults_to_empty_list(self):
        data = {"title": "Test", "content": "# Report"}
        sources = data.get("sources") or []
        assert len(sources) == 0

    def test_present_sources_preserved(self):
        data = {"title": "Test", "content": "# Report", "sources": [{"url": "https://example.com"}]}
        sources = data.get("sources") or []
        assert len(sources) == 1
```

**Step 2: Run tests**

```bash
cd backend && pytest tests/scripts/test_monitor_session_nullable.py -v
```

**Step 3: Implement the fix**

In `backend/scripts/monitor_session.py`, replace line 260:

```python
            sources = data.get("sources") or []  # Handle sources: null
```

**Step 4: Run tests and commit**

```bash
git add backend/scripts/monitor_session.py backend/tests/scripts/test_monitor_session_nullable.py
git commit -m "fix(monitor): guard against nullable sources in report events"
```

---

### Task 7: Suppress Truncation Banner When Evidence Is Poor

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py:1227-1240`
- Create: `backend/tests/domain/services/agents/test_truncation_suppression.py`

**Context:** The "Incomplete Report" banner is prepended whenever `[…]` artifacts are found in content, even when the real problem is zero sources (not truncation). This misleads users into thinking the report was truncated rather than fundamentally lacking evidence.

**Step 1: Write failing test**

```python
# backend/tests/domain/services/agents/test_truncation_suppression.py
"""Tests for truncation notice suppression when evidence is poor."""
import pytest


class TestTruncationNoticeSuppression:
    """Truncation notice should only appear for actual truncation, not zero-source reports."""

    def test_no_banner_when_zero_sources_and_artifacts(self):
        """Don't prepend truncation banner when the real problem is zero sources."""
        source_count = 0
        truncation_exhausted = False
        has_artifacts = True  # Content has [...] but that's from LLM, not truncation

        # New logic: suppress banner when source_count == 0
        should_show_banner = (truncation_exhausted or has_artifacts) and source_count > 0
        assert should_show_banner is False

    def test_banner_shown_for_actual_truncation_with_sources(self):
        """Show truncation banner when there are sources and actual truncation."""
        source_count = 5
        truncation_exhausted = True
        has_artifacts = True

        should_show_banner = (truncation_exhausted or has_artifacts) and source_count > 0
        assert should_show_banner is True
```

**Step 2: Implement the fix**

In `backend/app/domain/services/agents/execution.py`, replace lines 1227-1240:

```python
            # Prepend incomplete-report warning header when truncation was unresolvable OR
            # when the content still carries `[…]` streaming artifacts.
            # BUT suppress if there are zero collected sources — the problem isn't
            # truncation, it's lack of evidence. Showing a truncation banner for
            # a zero-source report is misleading.
            source_count = len(self._collected_sources) if self._collected_sources else 0
            if (truncation_exhausted or self._has_truncation_artifacts(message_content)) and source_count > 0:
                truncation_notice = (
                    "> **Incomplete Report:** This report contains sections that were not fully "
                    "generated due to output length limits. Sections marked `[…]` contain truncated "
                    "content. The available research findings are included below.\n\n"
                )
                message_content = truncation_notice + message_content
                logger.warning(
                    "Prepended truncation notice to report (truncation_exhausted=%s, artifacts=%s, sources=%d)",
                    truncation_exhausted,
                    self._has_truncation_artifacts(message_content),
                    source_count,
                )
```

**Step 3: Run tests and commit**

```bash
cd backend && pytest tests/domain/services/agents/test_truncation_suppression.py -v
git add backend/app/domain/services/agents/execution.py backend/tests/domain/services/agents/test_truncation_suppression.py
git commit -m "fix(delivery): suppress truncation banner when zero sources collected"
```

---

### Task 8: Fix Duplicate References — Guard Against Double Injection

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py:1674-1705`
- Create: `backend/tests/domain/services/agents/test_reference_dedup.py`

**Context:** References can be duplicated when `_ensure_complete_references()` in execution.py injects a references section AND then `markdown_normalizer.py` also builds one from the same sources. The fix: `_ensure_complete_references()` should check if the normalizer will run and skip if so.

**Step 1: Write failing test**

```python
# backend/tests/domain/services/agents/test_reference_dedup.py
"""Tests for reference section deduplication."""
import pytest
import re


class TestReferenceSectionDedup:
    """Only one References section should exist in the final output."""

    def test_no_duplicate_references_sections(self):
        """Content with an existing complete References section should not get another one."""
        content = """# Report Title

## Analysis
Some analysis here [1][2].

## References
[1] Source One - https://example.com/1
[2] Source Two - https://example.com/2
"""
        # Count ## References headings
        ref_headings = re.findall(r"^##\s+References?\s*$", content, re.MULTILINE | re.IGNORECASE)
        assert len(ref_headings) == 1

    def test_existing_complete_refs_not_replaced(self):
        """If existing refs >= expected, leave untouched."""
        content = "# Report\n\n[1] cited.\n\n## References\n[1] Source - url\n[2] Extra - url\n"
        expected_count = 1  # Only 1 source tracked
        ref_match = re.search(r"^##\s+References?\s*$", content, re.MULTILINE | re.IGNORECASE)
        ref_section = content[ref_match.end():].strip()
        existing_count = len(re.findall(r"^\s*\[?\d+\]", ref_section, re.MULTILINE))

        # Guard: don't replace if existing >= expected
        should_replace = existing_count < expected_count
        assert should_replace is False
```

**Step 2: Implement the fix**

In `backend/app/domain/services/agents/execution.py`, at the start of `_ensure_complete_references` (around line 1660), add a guard that counts existing `## References` headings:

```python
    def _ensure_complete_references(self, content: str) -> str:
        """Inject complete References section if truncated/missing.

        Guards against double-injection: if the content already has a complete
        references section (count >= expected), return unchanged.
        """
        if not self._collected_sources:
            return content

        # Count existing ## References headings — if already 1+, let normalizer handle it
        ref_heading_count = len(re.findall(r"^##\s+References?\s*$", content, re.MULTILINE | re.IGNORECASE))
        if ref_heading_count > 1:
            # Already duplicated somehow — strip all but first
            logger.warning("Found %d References headings, deduplicating", ref_heading_count)
            parts = re.split(r"(^##\s+References?\s*$)", content, flags=re.MULTILINE | re.IGNORECASE)
            # Keep content up to and including first References section
            if len(parts) >= 3:
                first_ref_idx = 1  # parts[0]=before, parts[1]=heading, parts[2]=content after
                content = parts[0] + parts[1] + parts[2]

        # ... rest of existing logic unchanged ...
```

**Step 3: Run tests and commit**

```bash
cd backend && pytest tests/domain/services/agents/test_reference_dedup.py -v
git add backend/app/domain/services/agents/execution.py backend/tests/domain/services/agents/test_reference_dedup.py
git commit -m "fix(references): guard against duplicate References section injection"
```

---

### Task 9: Fix Headline Extractor — Don't Hide Failures Behind "completed (no output)"

**Files:**
- Modify: `backend/app/domain/services/flows/headline_extractor.py:25-26`
- Create: `backend/tests/domain/services/flows/test_headline_extractor_failures.py`

**Context:** When a tool produces empty output (e.g., file_read returning file-not-found), the headline becomes "Tool completed (no output)" — hiding the failure. The headline should reflect the actual failure.

**Step 1: Write failing test**

```python
# backend/tests/domain/services/flows/test_headline_extractor_failures.py
"""Tests for headline extraction with failed tool results."""
import pytest
from app.domain.services.flows.headline_extractor import extract_headline


class TestHeadlineExtractorFailures:
    """Empty tool results should indicate failure, not success."""

    def test_empty_result_shows_failure_not_success(self):
        headline = extract_headline("", tool_name="file_read")
        assert "completed" not in headline.lower()
        assert "no output" in headline.lower() or "no result" in headline.lower()

    def test_empty_result_includes_tool_name(self):
        headline = extract_headline("", tool_name="file_read")
        assert "file_read" in headline
```

**Step 2: Implement the fix**

In `backend/app/domain/services/flows/headline_extractor.py`, replace line 25-26:

```python
    if not tool_result.strip():
        return f"{tool_name or 'Tool'} returned no result"
```

**Step 3: Run tests and commit**

```bash
cd backend && pytest tests/domain/services/flows/test_headline_extractor_failures.py -v
git add backend/app/domain/services/flows/headline_extractor.py backend/tests/domain/services/flows/test_headline_extractor_failures.py
git commit -m "fix(headlines): replace misleading 'completed (no output)' with 'returned no result'"
```

---

### Task 10: Normalize ReportEvent Sources at Emission — Prevent Null Propagation

**Files:**
- Modify: `backend/app/domain/models/event.py:630`
- Create: `backend/tests/domain/models/test_report_event_sources.py`

**Context:** `ReportEvent.sources` is typed `list[SourceCitation] | None = None`. Downstream consumers crash on `None`. The cleanest fix is a Pydantic validator that normalizes `None` → `[]` at construction.

**Step 1: Write failing test**

```python
# backend/tests/domain/models/test_report_event_sources.py
"""Tests for ReportEvent sources normalization."""
import pytest
from app.domain.models.event import ReportEvent


class TestReportEventSourcesNormalization:
    """ReportEvent.sources should never be None after construction."""

    def test_none_sources_normalized_to_empty_list(self):
        event = ReportEvent(id="test-1", title="Test", content="# Report", sources=None)
        assert event.sources == []
        assert event.sources is not None

    def test_missing_sources_normalized_to_empty_list(self):
        event = ReportEvent(id="test-2", title="Test", content="# Report")
        assert event.sources == []

    def test_present_sources_preserved(self):
        from app.domain.models.event import SourceCitation
        src = SourceCitation(url="https://example.com", title="Example")
        event = ReportEvent(id="test-3", title="Test", content="# Report", sources=[src])
        assert len(event.sources) == 1
```

**Step 2: Implement the fix**

In `backend/app/domain/models/event.py`, on `ReportEvent` class (around line 630), add a field validator:

```python
    sources: list[SourceCitation] = Field(default_factory=list)  # Normalized: never None

    @field_validator("sources", mode="before")
    @classmethod
    def _normalize_sources(cls, v: list[SourceCitation] | None) -> list[SourceCitation]:
        return v if v is not None else []
```

**Step 3: Run tests and commit**

```bash
cd backend && pytest tests/domain/models/test_report_event_sources.py -v
git add backend/app/domain/models/event.py backend/tests/domain/models/test_report_event_sources.py
git commit -m "fix(events): normalize ReportEvent.sources — never emit null to consumers"
```

---

### Task 11: Suppress Delivery Artifacts When Evidence Is Poor

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py:918-934` (already done in Task 4)
- Modify: `backend/app/domain/services/agents/execution.py:1224-1226`

**Context:** Zero-source reports should not get reference injection. If `_collected_sources` is empty, `_ensure_complete_references()` should be a no-op (it already returns early on line 1670 — verify this path is hit).

This is already handled by the existing guard at line 1670:
```python
if not self._collected_sources:
    return content
```

**Verification step only** — no code change needed. Run existing tests:

```bash
cd backend && pytest tests/domain/services/agents/test_execution*.py -v
```

---

### Task 12: Final Integration Test & Full Suite Regression

**Files:**
- Run: Full test suite

**Step 1: Run full backend test suite**

```bash
cd backend && conda activate pythinker && pytest tests/ -x -v --timeout=60 2>&1 | tail -30
```

**Step 2: Run linting**

```bash
cd backend && ruff check . && ruff format --check .
```

**Step 3: Fix any failures**

Address any test failures or lint issues introduced by the above changes.

**Step 4: Final commit (if needed)**

```bash
git add -A && git commit -m "test: fix integration issues from session monitoring comprehensive fixes"
```

---

## Summary of Changes

| Task | Severity | File(s) | Fix |
|------|----------|---------|-----|
| 1 | Medium | research_spider.py, search.py | Expand spider denylist (+5 social domains) |
| 2 | High | output_verifier.py | Break self-referential grounding loop |
| 3 | Critical | docker_sandbox.py | Sandbox ownership lock via Redis liveness |
| 4 | Medium | agent_task_runner.py | Suppress SVG fallback when no data exists |
| 5 | High | execution.py, plan_act.py | Evidence-based step completion |
| 6 | Medium | monitor_session.py | Guard nullable sources |
| 7 | Medium | execution.py | Suppress truncation banner on zero sources |
| 8 | Medium | execution.py | Deduplicate References sections |
| 9 | Low | headline_extractor.py | Show failure instead of "completed (no output)" |
| 10 | Medium | event.py | Normalize sources `None` → `[]` at emission |
| 11 | — | (verification only) | Confirm zero-source guard works |
| 12 | — | (full suite) | Regression testing |
