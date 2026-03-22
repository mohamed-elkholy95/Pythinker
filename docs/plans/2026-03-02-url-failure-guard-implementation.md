# URL Failure Guard — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a 3-tier session-scoped URL failure guard that prevents the LLM from repeatedly visiting hallucinated URLs, with automatic escalation from warning to hard-block.

**Architecture:** A new domain service `UrlFailureGuard` tracks failed URLs per session, collects known-good URLs from search results, and injects correction messages into the LLM context. Integrated at the `invoke_tool()` level in `BaseAgent` for pre-check/post-record. The root bug in `browser.py:451` (RuntimeError instead of ToolResult) is fixed first.

**Tech Stack:** Python 3.12 dataclasses, urllib.parse for URL normalization, Prometheus counters/gauge for observability. No new dependencies.

---

### Task 1: Create UrlFailureGuard Domain Service

**Files:**
- Create: `backend/app/domain/services/agents/url_failure_guard.py`
- Test: `backend/tests/domain/services/agents/test_url_failure_guard.py`

**Step 1: Write the failing tests**

Create the test file with comprehensive coverage:

```python
# backend/tests/domain/services/agents/test_url_failure_guard.py
"""Unit tests for UrlFailureGuard 3-tier escalation."""

import pytest

from app.domain.services.agents.url_failure_guard import (
    GuardDecision,
    UrlFailureGuard,
    UrlFailureRecord,
    normalize_url,
)


class TestUrlNormalization:
    """URL normalization catches near-duplicates."""

    def test_strips_trailing_slash(self):
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    def test_lowercases_scheme_and_host(self):
        assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"

    def test_sorts_query_parameters(self):
        assert normalize_url("https://example.com?b=2&a=1") == "https://example.com?a=1&b=2"

    def test_removes_fragments(self):
        assert normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_preserves_path_case(self):
        """Path is case-sensitive per RFC 3986."""
        assert normalize_url("https://example.com/Vue/Guide") == "https://example.com/Vue/Guide"

    def test_empty_url_returns_empty(self):
        assert normalize_url("") == ""

    def test_url_without_scheme(self):
        """URLs without scheme are returned as-is (normalized lowercase)."""
        result = normalize_url("example.com/path/")
        assert result == "example.com/path"


class TestTierEscalation:
    """3-tier escalation: allow → warn → block."""

    def setup_method(self):
        self.guard = UrlFailureGuard(max_failures_per_url=3)

    def test_tier1_first_attempt_allows(self):
        decision = self.guard.check_url("https://example.com/missing")
        assert decision.action == "allow"
        assert decision.tier == 1
        assert decision.message is None

    def test_tier2_second_attempt_warns(self):
        self.guard.record_failure("https://example.com/missing", "HTTP 404 Not Found", "browser_get_content")
        decision = self.guard.check_url("https://example.com/missing")
        assert decision.action == "warn"
        assert decision.tier == 2
        assert "already tried" in decision.message.lower() or "already failed" in decision.message.lower()

    def test_tier3_third_attempt_blocks(self):
        url = "https://example.com/missing"
        self.guard.record_failure(url, "HTTP 404 Not Found", "browser_get_content")
        self.guard.record_failure(url, "HTTP 404 Not Found", "browser_get_content")
        decision = self.guard.check_url(url)
        assert decision.action == "block"
        assert decision.tier == 3
        assert "BLOCKED" in decision.message

    def test_tier3_blocks_after_max_failures(self):
        url = "https://vuejs.org/guide/best-practices/"
        for _ in range(3):
            self.guard.record_failure(url, "HTTP 404", "browser_get_content")
        decision = self.guard.check_url(url)
        assert decision.action == "block"
        assert decision.tier == 3

    def test_different_urls_independent(self):
        """Failures on one URL don't affect another."""
        self.guard.record_failure("https://a.com/404", "404", "browser")
        self.guard.record_failure("https://a.com/404", "404", "browser")
        decision_a = self.guard.check_url("https://a.com/404")
        decision_b = self.guard.check_url("https://b.com/page")
        assert decision_a.action == "block"
        assert decision_b.action == "allow"


class TestAlternativeUrls:
    """Search result URLs suggested as alternatives."""

    def setup_method(self):
        self.guard = UrlFailureGuard()

    def test_alternatives_from_search_results(self):
        self.guard.record_search_results([
            "https://vuejs.org/guide/introduction.html",
            "https://coreui.io/vue/docs/",
        ])
        self.guard.record_failure("https://vuejs.org/guide/best-practices/", "404", "browser")
        decision = self.guard.check_url("https://vuejs.org/guide/best-practices/")
        assert decision.action == "warn"
        assert len(decision.alternative_urls) > 0
        assert "https://vuejs.org/guide/introduction.html" in decision.alternative_urls

    def test_failed_urls_excluded_from_alternatives(self):
        """URLs that have failed should not be suggested as alternatives."""
        self.guard.record_search_results([
            "https://a.com/good",
            "https://b.com/also-bad",
        ])
        self.guard.record_failure("https://b.com/also-bad", "404", "browser")
        self.guard.record_failure("https://example.com/bad", "404", "browser")
        decision = self.guard.check_url("https://example.com/bad")
        assert "https://a.com/good" in decision.alternative_urls
        assert "https://b.com/also-bad" not in decision.alternative_urls

    def test_alternatives_capped_at_five(self):
        urls = [f"https://example.com/page{i}" for i in range(10)]
        self.guard.record_search_results(urls)
        self.guard.record_failure("https://bad.com/404", "404", "browser")
        decision = self.guard.check_url("https://bad.com/404")
        assert len(decision.alternative_urls) <= 5


class TestUrlNormalizationInGuard:
    """Guard normalizes URLs before tracking."""

    def setup_method(self):
        self.guard = UrlFailureGuard()

    def test_trailing_slash_treated_as_same(self):
        self.guard.record_failure("https://example.com/path/", "404", "browser")
        decision = self.guard.check_url("https://example.com/path")
        assert decision.action == "warn"
        assert decision.tier == 2

    def test_case_insensitive_host(self):
        self.guard.record_failure("https://EXAMPLE.COM/path", "404", "browser")
        decision = self.guard.check_url("https://example.com/path")
        assert decision.action == "warn"


class TestMetrics:
    """Guard exposes metrics for Prometheus."""

    def test_metrics_initial(self):
        guard = UrlFailureGuard()
        metrics = guard.get_metrics()
        assert metrics["tracked_urls"] == 0
        assert metrics["total_failures"] == 0
        assert metrics["tier2_escalations"] == 0
        assert metrics["tier3_escalations"] == 0

    def test_metrics_after_escalation(self):
        guard = UrlFailureGuard()
        guard.record_failure("https://a.com/404", "404", "browser")
        guard.record_failure("https://a.com/404", "404", "browser")
        metrics = guard.get_metrics()
        assert metrics["tracked_urls"] == 1
        assert metrics["total_failures"] == 2

    def test_get_failed_urls_summary(self):
        guard = UrlFailureGuard()
        assert guard.get_failed_urls_summary() is None
        guard.record_failure("https://a.com/bad", "404", "browser")
        summary = guard.get_failed_urls_summary()
        assert "a.com/bad" in summary
        assert "404" in summary
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_url_failure_guard.py -v 2>&1 | head -30`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain.services.agents.url_failure_guard'`

**Step 3: Write minimal implementation**

```python
# backend/app/domain/services/agents/url_failure_guard.py
"""URL Failure Guard — 3-Tier Auto-Correction for LLM URL Hallucination.

Tracks failed URLs across all steps in a session and provides pre-execution
checks with escalating responses:
  Tier 1 (1st failure): Allow execution, return structured error
  Tier 2 (2nd attempt): Inject warning with alternative URLs, allow execution
  Tier 3 (3rd attempt): Hard-block tool call, return synthetic failure

Designed to prevent the LLM from retrying hallucinated URLs that return 404.

Root cause: Session 3fdec66859ff45b3 was cancelled after GLM-5 fabricated
https://vuejs.org/guide/best-practices/ (404). The agent retried the same
URL until StuckDetector killed the session.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

# Maximum alternative URLs to suggest
_MAX_ALTERNATIVES = 5


def normalize_url(url: str) -> str:
    """Normalize URL for comparison.

    - Strip trailing slashes
    - Lowercase scheme and host
    - Sort query parameters
    - Remove fragments (#anchors)
    """
    if not url:
        return ""

    parsed = urlparse(url)

    # If no scheme, urlparse puts everything in path — handle gracefully
    if not parsed.scheme:
        # Strip trailing slash from the raw URL
        return url.rstrip("/")

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or ""
    # Sort query parameters
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    sorted_query = urlencode(sorted(query_params.items()), doseq=True)
    # Remove fragment
    fragment = ""

    return urlunparse((scheme, netloc, path, parsed.params, sorted_query, fragment))


@dataclass
class UrlFailureRecord:
    """Tracks failure history for a single normalized URL."""

    url: str
    error: str
    attempts: int = 1
    first_failed: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_failed: datetime = field(default_factory=lambda: datetime.now(UTC))
    source_tool: str = ""


@dataclass
class GuardDecision:
    """Result of a pre-execution URL check."""

    action: str  # "allow", "warn", "block"
    tier: int  # 1, 2, 3
    message: str | None = None
    alternative_urls: list[str] = field(default_factory=list)


class UrlFailureGuard:
    """Session-scoped URL failure tracker with 3-tier escalation.

    Instantiated once per session in PlanActFlow, passed to BaseAgent.
    Persists across all steps in a session.
    """

    def __init__(self, max_failures_per_url: int = 3) -> None:
        self._max_failures = max_failures_per_url
        self._failures: dict[str, UrlFailureRecord] = {}
        self._known_good_urls: list[str] = []
        self._total_failures = 0
        self._tier2_escalations = 0
        self._tier3_escalations = 0

    def check_url(self, url: str) -> GuardDecision:
        """Pre-execution check for a URL.

        Returns:
            GuardDecision with action (allow/warn/block), tier, message,
            and alternative URLs from search results.
        """
        normalized = normalize_url(url)
        record = self._failures.get(normalized)

        if record is None:
            # Tier 1: First attempt — allow
            return GuardDecision(action="allow", tier=1)

        alternatives = self._get_alternatives(normalized)

        if record.attempts >= self._max_failures - 1:
            # Tier 3: 3rd+ attempt — hard block
            self._tier3_escalations += 1
            alt_text = self._format_alternatives(alternatives)
            return GuardDecision(
                action="block",
                tier=3,
                message=(
                    f"BLOCKED: {url} has failed {record.attempts} times "
                    f"({record.error}). Tool call was not executed. "
                    f"{alt_text}"
                    f"Pick one of these URLs instead."
                ),
                alternative_urls=alternatives,
            )

        # Tier 2: 2nd attempt — warn but allow
        self._tier2_escalations += 1
        alt_text = self._format_alternatives(alternatives)
        return GuardDecision(
            action="warn",
            tier=2,
            message=(
                f"WARNING: You already tried {url} and it failed "
                f"({record.error}). Do NOT retry this URL. "
                f"{alt_text}"
                f"Use a different URL from your search results."
            ),
            alternative_urls=alternatives,
        )

    def record_failure(self, url: str, error: str, tool: str) -> None:
        """Record a URL failure after tool execution.

        Args:
            url: The URL that failed
            error: Error description (e.g., "HTTP 404 Not Found")
            tool: Tool name that attempted the URL
        """
        normalized = normalize_url(url)
        self._total_failures += 1

        if normalized in self._failures:
            record = self._failures[normalized]
            record.attempts += 1
            record.last_failed = datetime.now(UTC)
            record.error = error
        else:
            self._failures[normalized] = UrlFailureRecord(
                url=normalized,
                error=error,
                source_tool=tool,
            )

        logger.info(
            "URL failure recorded: %s (attempts=%d, error=%s, tool=%s)",
            url,
            self._failures[normalized].attempts,
            error,
            tool,
        )

    def record_search_results(self, urls: list[str]) -> None:
        """Record known-good URLs from search results.

        These are used as alternative suggestions when the LLM
        tries a failed URL.

        Args:
            urls: List of URLs from search result items
        """
        for url in urls:
            normalized = normalize_url(url)
            if normalized and normalized not in self._known_good_urls:
                self._known_good_urls.append(normalized)

    def get_failed_urls_summary(self) -> str | None:
        """Human-readable summary of all failed URLs.

        Returns None if no failures recorded.
        """
        if not self._failures:
            return None

        lines = []
        for record in self._failures.values():
            lines.append(f"  - {record.url} ({record.error}, {record.attempts} attempts)")
        return "Failed URLs this session:\n" + "\n".join(lines)

    def get_metrics(self) -> dict[str, int]:
        """Metrics for Prometheus export."""
        return {
            "tracked_urls": len(self._failures),
            "total_failures": self._total_failures,
            "tier2_escalations": self._tier2_escalations,
            "tier3_escalations": self._tier3_escalations,
            "known_good_urls": len(self._known_good_urls),
        }

    def _get_alternatives(self, failed_normalized: str) -> list[str]:
        """Get known-good URLs excluding failed ones."""
        failed_set = set(self._failures.keys())
        alternatives = [
            url for url in self._known_good_urls
            if url not in failed_set
        ]
        return alternatives[:_MAX_ALTERNATIVES]

    def _format_alternatives(self, alternatives: list[str]) -> str:
        """Format alternative URLs for LLM context injection."""
        if not alternatives:
            return ""
        lines = "\n".join(f"  - {url}" for url in alternatives)
        return f"Available URLs:\n{lines}\n"
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_url_failure_guard.py -v`
Expected: All 17 tests PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/url_failure_guard.py backend/tests/domain/services/agents/test_url_failure_guard.py
git commit -m "feat(guard): add UrlFailureGuard domain service with 3-tier URL escalation

TDD: 17 unit tests covering tier escalation, URL normalization,
alternative suggestions, and metrics. Prevents LLM from retrying
hallucinated URLs that return 404."
```

---

### Task 2: Fix browser.py RuntimeError Bug

**Files:**
- Modify: `backend/app/domain/services/tools/browser.py:450-451`
- Test: `backend/tests/domain/services/tools/test_browser_scrapling_error.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/tools/test_browser_scrapling_error.py
"""Regression test: Scrapling 404 returns ToolResult(success=False), not RuntimeError."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.models.tool_result import ToolResult


@pytest.mark.asyncio
async def test_scrapling_404_returns_tool_result_not_exception():
    """browser.py:451 must return ToolResult(success=False), not raise RuntimeError."""
    from app.domain.services.tools.browser import BrowserTool

    # Create a mock browser with required attributes
    mock_browser = MagicMock()
    mock_browser.is_connected = MagicMock(return_value=True)
    mock_browser.navigate_for_display = AsyncMock()

    # Create a mock scraper that returns a 404 failure
    mock_scraper = MagicMock()
    mock_scraped = MagicMock()
    mock_scraped.success = False
    mock_scraped.error = "HTTP 404 Not Found"
    mock_scraped.text = ""
    mock_scraped.html = ""
    mock_scraped.url = "https://vuejs.org/guide/best-practices/"
    mock_scraped.tier_used = "http"
    mock_scraper.fetch_with_escalation = AsyncMock(return_value=mock_scraped)

    tool = BrowserTool(browser=mock_browser, scraper=mock_scraper)

    # Patch settings to enable enhanced fetch
    with patch("app.domain.services.tools.browser.get_settings") as mock_settings:
        settings = MagicMock()
        settings.scraping_enhanced_fetch = True
        mock_settings.return_value = settings

        # This MUST NOT raise RuntimeError — it must return ToolResult(success=False)
        result = await tool.browser_get_content("https://vuejs.org/guide/best-practices/")

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "404" in result.message or "failed" in result.message.lower()
```

**Step 2: Run test to verify it fails (RuntimeError raised)**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/tools/test_browser_scrapling_error.py -v 2>&1 | tail -10`
Expected: FAIL with `RuntimeError: HTTP 404 Not Found`

**Step 3: Fix browser.py line 451**

Replace line 451 in `backend/app/domain/services/tools/browser.py`:

```python
# BEFORE (line 450-451):
                else:
                    raise RuntimeError(_result.error or "Scrapling returned no usable content")

# AFTER (line 450-455):
                else:
                    return ToolResult(
                        success=False,
                        message=f"URL fetch failed: {_result.error or 'No usable content'}. "
                                "Try a different URL from your search results.",
                    )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/tools/test_browser_scrapling_error.py -v`
Expected: PASS

**Step 5: Run existing browser tests to ensure no regression**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/tools/test_browser*.py -v --timeout=30 2>&1 | tail -20`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add backend/app/domain/services/tools/browser.py backend/tests/domain/services/tools/test_browser_scrapling_error.py
git commit -m "fix(browser): return ToolResult(success=False) on Scrapling 404 instead of RuntimeError

Root cause of session 3fdec66859ff45b3 cancellation: browser.py:451
raised RuntimeError on Scrapling failure, breaking the tool error
contract. The LLM never saw a structured error and retried the same
hallucinated URL until StuckDetector killed the session."
```

---

### Task 3: Add Feature Flag

**Files:**
- Modify: `backend/app/core/config_features.py:286` (after DOM cursor line)

**Step 1: Add the feature flag**

Add after line 286 (`feature_dom_cursor_injection: bool = False`):

```python
    # URL Failure Guard — 3-tier auto-correction for LLM URL hallucination (2026-03-02)
    feature_url_failure_guard_enabled: bool = True
```

**Step 2: Run config tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/core/test_config*.py -v --timeout=30 2>&1 | tail -10`
Expected: All pass (the flag has a default, so no config tests break)

**Step 3: Commit**

```bash
git add backend/app/core/config_features.py
git commit -m "feat(config): add feature_url_failure_guard_enabled flag (default True)"
```

---

### Task 4: Integrate Guard into BaseAgent

**Files:**
- Modify: `backend/app/domain/services/agents/base.py:178` (init — add guard)
- Modify: `backend/app/domain/services/agents/base.py:797` (invoke_tool — pre-check)
- Modify: `backend/app/domain/services/agents/base.py:854` (invoke_tool — post-record)
- Test: `backend/tests/domain/services/agents/test_url_failure_guard_integration.py`

**Step 1: Write integration test**

```python
# backend/tests/domain/services/agents/test_url_failure_guard_integration.py
"""Integration: UrlFailureGuard wired into BaseAgent invoke_tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.agents.url_failure_guard import UrlFailureGuard


class TestGuardExtractsUrl:
    """Guard extracts URLs from tool arguments."""

    def test_extract_url_field(self):
        from app.domain.services.agents.base import _extract_url_from_args

        assert _extract_url_from_args({"url": "https://example.com"}) == "https://example.com"

    def test_extract_target_url_field(self):
        from app.domain.services.agents.base import _extract_url_from_args

        assert _extract_url_from_args({"target_url": "https://example.com"}) == "https://example.com"

    def test_extract_no_url(self):
        from app.domain.services.agents.base import _extract_url_from_args

        assert _extract_url_from_args({"query": "vue best practices"}) is None

    def test_extract_empty_args(self):
        from app.domain.services.agents.base import _extract_url_from_args

        assert _extract_url_from_args({}) is None


class TestGuardBlocksInInvokeTool:
    """Tier 3 blocks prevent tool execution."""

    @pytest.mark.asyncio
    async def test_tier3_returns_synthetic_failure(self):
        """When guard returns block, invoke_tool skips execution."""
        guard = UrlFailureGuard(max_failures_per_url=3)
        url = "https://vuejs.org/guide/best-practices/"
        # Simulate 2 prior failures → next check_url returns block
        guard.record_failure(url, "HTTP 404", "browser_get_content")
        guard.record_failure(url, "HTTP 404", "browser_get_content")

        decision = guard.check_url(url)
        assert decision.action == "block"
        assert "BLOCKED" in decision.message
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_url_failure_guard_integration.py -v 2>&1 | tail -10`
Expected: FAIL with `ImportError: cannot import name '_extract_url_from_args' from 'app.domain.services.agents.base'`

**Step 3: Add guard initialization to BaseAgent.__init__**

In `backend/app/domain/services/agents/base.py`, after line 178 (`self._efficiency_monitor = ...`):

```python
        # URL Failure Guard — session-scoped, set externally by PlanActFlow
        # When None, guard checks are skipped (backward compatible)
        self._url_failure_guard: "UrlFailureGuard | None" = None
```

**Step 4: Add URL extraction helper function**

In `backend/app/domain/services/agents/base.py`, add as a module-level function (before the `BaseAgent` class, after imports):

```python
def _extract_url_from_args(arguments: dict) -> str | None:
    """Extract URL from tool call arguments.

    Checks common URL parameter names used across tools.
    """
    for key in ("url", "target_url", "page_url"):
        val = arguments.get(key)
        if val and isinstance(val, str) and val.startswith("http"):
            return val
    return None
```

**Step 5: Add pre-check in invoke_tool before the retry loop**

In `backend/app/domain/services/agents/base.py`, before line 797 (`while retries <= self.max_retries:`), add:

```python
        # ── URL Failure Guard: pre-check ─────────────────────────────────────
        _guard_url: str | None = None
        if self._url_failure_guard is not None:
            _guard_url = _extract_url_from_args(arguments)
            if _guard_url:
                from app.domain.services.agents.url_failure_guard import GuardDecision

                _guard_decision = self._url_failure_guard.check_url(_guard_url)
                if _guard_decision.action == "block":
                    # Tier 3: Hard-block — skip execution entirely
                    logger.warning(
                        "URL guard BLOCKED %s (tier=%d): %s",
                        _guard_url,
                        _guard_decision.tier,
                        _guard_decision.message,
                    )
                    return ToolResult(success=False, message=_guard_decision.message)
                elif _guard_decision.action == "warn" and _guard_decision.message:
                    # Tier 2: Inject warning — execution still proceeds
                    logger.info(
                        "URL guard WARNING for %s (tier=%d)",
                        _guard_url,
                        _guard_decision.tier,
                    )
                    self._efficiency_nudges.append(
                        {
                            "message": _guard_decision.message,
                            "read_count": 0,
                            "action_count": 0,
                            "confidence": 0.90,
                            "hard_stop": False,
                        }
                    )
```

**Step 6: Add post-record after tool execution failure**

In `backend/app/domain/services/agents/base.py`, in the post-execution tracking block (around line 886, after the efficiency monitor section), add:

```python
                # URL Failure Guard: record failure on unsuccessful URL fetch
                if self._url_failure_guard and _guard_url and result and not result.success:
                    try:
                        self._url_failure_guard.record_failure(
                            _guard_url,
                            result.message[:200] if result.message else "Unknown error",
                            function_name,
                        )
                    except Exception as _guard_err:
                        logger.debug("URL failure guard recording failed: %s", _guard_err)
```

Also add the same recording in the retry-exhausted failure path (around line 979, after the efficiency monitor in the failure path):

```python
        # URL Failure Guard: record failure when retries exhausted
        if self._url_failure_guard and _guard_url:
            try:
                self._url_failure_guard.record_failure(_guard_url, last_error[:200], function_name)
            except Exception as _guard_err:
                logger.debug("URL failure guard recording failed (retry exhausted): %s", _guard_err)
```

**Step 7: Run integration tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_url_failure_guard_integration.py -v`
Expected: All PASS

**Step 8: Run full base agent tests to check regression**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_base*.py -v --timeout=60 2>&1 | tail -15`
Expected: All existing tests pass (guard is None by default → no behavior change)

**Step 9: Commit**

```bash
git add backend/app/domain/services/agents/base.py backend/tests/domain/services/agents/test_url_failure_guard_integration.py
git commit -m "feat(guard): integrate UrlFailureGuard into BaseAgent invoke_tool

Pre-check: extract URL from tool args, check guard tier.
  - Tier 2 (warn): inject warning into efficiency nudges
  - Tier 3 (block): skip execution, return synthetic failure
Post-record: track failures for URL-bearing tools.
Guard is None by default — zero behavior change without PlanActFlow."
```

---

### Task 5: Wire Guard into PlanActFlow (Session Scope)

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py:425` (after executor creation)

**Step 1: Add guard creation after executor init**

In `backend/app/domain/services/flows/plan_act.py`, after line 433 (`logger.debug(f"Created execution agent...")`), add:

```python
        # URL Failure Guard: session-scoped, shared across all steps
        self._url_failure_guard = None
        if flags.get("feature_url_failure_guard_enabled", True):
            from app.domain.services.agents.url_failure_guard import UrlFailureGuard

            self._url_failure_guard = UrlFailureGuard(max_failures_per_url=3)
            self.executor._url_failure_guard = self._url_failure_guard
            logger.info("UrlFailureGuard enabled for session %s", session_id)
```

**Step 2: Verify guard is passed to step executors in multi-agent dispatch**

Find where `_get_executor_for_step` creates specialized executors. Add guard propagation there.

Run: `grep -n "_get_executor_for_step\|step_executor\._url" backend/app/domain/services/flows/plan_act.py | head -10`

In the `_get_executor_for_step` method, after the executor is created/selected, ensure the guard is set:

```python
            # Propagate session-scoped URL failure guard to step executor
            if self._url_failure_guard and hasattr(step_executor, '_url_failure_guard'):
                step_executor._url_failure_guard = self._url_failure_guard
```

**Step 3: Run plan_act tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/flows/test_plan_act*.py -v --timeout=60 2>&1 | tail -15`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py
git commit -m "feat(guard): wire UrlFailureGuard into PlanActFlow with session scope

Guard created once per session, shared across default executor and
step executors. Controlled by feature_url_failure_guard_enabled flag."
```

---

### Task 6: Feed Search Result URLs to Guard

**Files:**
- Modify: `backend/app/domain/services/tools/search.py:775` (after successful search return)

**Step 1: Add search result URL collection**

In `backend/app/domain/services/tools/search.py`, in the `_execute_multi_variant_search` method, right before the final `return ToolResult(success=True, ...)` on line 775, add:

```python
        # Feed result URLs to URL failure guard for alternative suggestions
        if all_items:
            try:
                from app.domain.services.agents.url_failure_guard import UrlFailureGuard

                guard: UrlFailureGuard | None = getattr(self, "_url_failure_guard", None)
                if guard:
                    result_urls = [item.link for item in all_items if item.link]
                    guard.record_search_results(result_urls)
                    logger.debug("Fed %d search result URLs to URL failure guard", len(result_urls))
            except Exception as _guard_err:
                logger.debug("Failed to feed search URLs to guard: %s", _guard_err)
```

**Step 2: Set guard reference on SearchTool**

In `backend/app/domain/services/flows/plan_act.py`, after the guard is created (Task 5 insertion point), also set it on the search tool:

```python
            # Also wire guard into SearchTool for URL collection
            if self._search_tool:
                self._search_tool._url_failure_guard = self._url_failure_guard
```

If `_search_tool` is set later in the flow, find that location and add the wiring there too. Search for where `self._search_tool` is assigned.

**Step 3: Run search tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/tools/test_search*.py -v --timeout=60 2>&1 | tail -15`
Expected: All pass (guard is None by default on SearchTool)

**Step 4: Commit**

```bash
git add backend/app/domain/services/tools/search.py backend/app/domain/services/flows/plan_act.py
git commit -m "feat(guard): feed search result URLs to UrlFailureGuard

When search returns results, extract URLs and pass to guard via
record_search_results(). These are suggested as alternatives when
the LLM tries a failed URL."
```

---

### Task 7: Add Prometheus Metrics

**Files:**
- Modify: `backend/app/core/prometheus_metrics.py` (add 3 new metrics)
- Modify: `backend/app/domain/services/agents/base.py` (emit metrics on guard actions)

**Step 1: Add metrics definitions**

In `backend/app/core/prometheus_metrics.py`, add after the existing metric definitions:

```python
# URL Failure Guard metrics
url_guard_actions_total = Counter(
    name="pythinker_url_failure_guard_actions_total",
    help_text="Total URL guard actions by tier and action type",
    labels=["tier", "action"],
)

url_guard_escalations_total = Counter(
    name="pythinker_url_failure_guard_escalations_total",
    help_text="URLs that escalated to higher tiers",
    labels=["tier"],
)

url_guard_tracked_urls = Gauge(
    name="pythinker_url_failure_guard_tracked_urls",
    help_text="Current number of failed URLs tracked in session",
    labels=[],
)
```

**Step 2: Emit metrics in BaseAgent invoke_tool**

In the guard pre-check block added in Task 4, after the tier decision, add metric increments:

```python
                    try:
                        from app.core.prometheus_metrics import url_guard_actions_total

                        url_guard_actions_total.inc(
                            {"tier": str(_guard_decision.tier), "action": _guard_decision.action}
                        )
                    except Exception:
                        pass
```

**Step 3: Run metrics tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/core/test_prometheus*.py -v --timeout=30 2>&1 | tail -10`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/core/prometheus_metrics.py backend/app/domain/services/agents/base.py
git commit -m "feat(metrics): add Prometheus counters for URL failure guard actions

3 new metrics: actions_total (by tier/action), escalations_total (by tier),
tracked_urls (gauge). Emitted in invoke_tool guard pre-check."
```

---

### Task 8: Full Regression Test

**Files:** None (test-only)

**Step 1: Run all URL guard tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_url_failure_guard*.py tests/domain/services/tools/test_browser_scrapling_error.py -v`
Expected: All pass

**Step 2: Run full test suite**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/ -x --timeout=120 -q 2>&1 | tail -20`
Expected: All existing tests pass, plus new tests. Zero failures.

**Step 3: Run linting**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker ruff check . && conda run -n pythinker ruff format --check .`
Expected: Clean

---

## Summary

| Task | Files | Tests | Description |
|------|-------|-------|-------------|
| 1 | `url_failure_guard.py` (NEW) | 17 unit tests | Core domain service with 3-tier escalation |
| 2 | `browser.py:451` | 1 regression test | Fix RuntimeError → ToolResult(success=False) |
| 3 | `config_features.py` | — | `feature_url_failure_guard_enabled` flag |
| 4 | `base.py` | 5 integration tests | Guard in invoke_tool (pre-check + post-record) |
| 5 | `plan_act.py` | — | Session-scoped guard creation |
| 6 | `search.py`, `plan_act.py` | — | Feed search URLs to guard |
| 7 | `prometheus_metrics.py`, `base.py` | — | 3 Prometheus metrics |
| 8 | — | Full suite | Regression verification |

**Total: 8 tasks, 7 commits, ~23 tests added, 4 files modified, 2 files created.**
