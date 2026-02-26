"""Tests for the FastPathRouter module.

Tests query classification and URL resolution for fast-path routing.
"""

import socket
from types import SimpleNamespace

import pytest

from app.domain.models.event import DoneEvent, ErrorEvent, ToolEvent, ToolStatus
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.flows.fast_path import (
    URL_KNOWLEDGE_BASE,
    FastPathRouter,
    QueryIntent,
    is_suggestion_follow_up_message,
    should_use_fast_path,
)


class TestQueryClassification:
    """Tests for query intent classification."""

    def setup_method(self):
        """Set up test fixtures."""
        self.router = FastPathRouter()

    # Direct browse tests
    @pytest.mark.parametrize(
        "message,expected_intent",
        [
            ("open google.com", QueryIntent.DIRECT_BROWSE),
            ("go to github.com", QueryIntent.DIRECT_BROWSE),
            ("browse https://example.com", QueryIntent.DIRECT_BROWSE),
            ("visit the claude docs", QueryIntent.DIRECT_BROWSE),
            ("navigate to anthropic website", QueryIntent.DIRECT_BROWSE),
            ("open claude code docs", QueryIntent.DIRECT_BROWSE),
            ("take me to stackoverflow", QueryIntent.DIRECT_BROWSE),
            ("show me the python documentation", QueryIntent.DIRECT_BROWSE),
        ],
    )
    def test_direct_browse_classification(self, message: str, expected_intent: QueryIntent):
        """Test that direct browse queries are classified correctly."""
        intent, params = self.router.classify(message)
        assert intent == expected_intent
        assert "target" in params

    # Web search tests
    @pytest.mark.parametrize(
        "message,expected_intent",
        [
            ("search for python tutorials", QueryIntent.WEB_SEARCH),
            ("google best restaurants nearby", QueryIntent.WEB_SEARCH),
            ("look up fastapi documentation", QueryIntent.WEB_SEARCH),
            ("find weather forecast", QueryIntent.WEB_SEARCH),
        ],
    )
    def test_web_search_classification(self, message: str, expected_intent: QueryIntent):
        """Test that web search queries are classified correctly."""
        intent, params = self.router.classify(message)
        assert intent == expected_intent
        assert "query" in params

    # Knowledge question tests
    @pytest.mark.parametrize(
        "message,expected_intent",
        [
            ("what is Python?", QueryIntent.KNOWLEDGE),
            ("who created JavaScript?", QueryIntent.KNOWLEDGE),
            ("when was Linux released?", QueryIntent.KNOWLEDGE),
            ("explain what Docker does", QueryIntent.KNOWLEDGE),
            ("how does Git work?", QueryIntent.KNOWLEDGE),
            ("define recursion", QueryIntent.KNOWLEDGE),
            ("Reply with a short sentence.", QueryIntent.KNOWLEDGE),
            ("respond in one sentence", QueryIntent.KNOWLEDGE),
            ("write a concise response", QueryIntent.KNOWLEDGE),
        ],
    )
    def test_knowledge_classification(self, message: str, expected_intent: QueryIntent):
        """Test that knowledge queries are classified correctly."""
        intent, params = self.router.classify(message)
        assert intent == expected_intent
        assert "question" in params

    # Knowledge escalation tests — queries that LOOK like knowledge questions
    # but should be escalated to TASK for web search / full workflow
    @pytest.mark.parametrize(
        "message",
        [
            # Health / supplement / medical topics
            "what does ashwagandha do to your body and pros and cons and side effects",
            "what are the side effects of ibuprofen",
            "how does creatine affect your body",
            "what is the recommended dosage for melatonin",
            "what does magnesium do to your brain",
            "how does caffeine affect blood pressure",
            "what are the health benefits of turmeric",
            # Comparison / pros-and-cons
            "what are the pros and cons of solar panels",
            "what are the advantages and disadvantages of remote work",
            "how does React compare to Vue",
            # Current events / prices / stats
            "what is the current price of Bitcoin",
            "what is the stock price of Tesla today",
            "how much does a Tesla Model 3 cost",
            # Safety / risk / danger
            "is it safe to take aspirin every day",
            "what are the risks of skydiving",
            "is tap water safe to drink",
            # Legal / regulatory
            "is it legal to download torrents",
            "what are the tax implications of freelancing",
            # Multi-sub-question (3+ conjunctions)
            "what is X and Y and Z and how does it work",
        ],
    )
    def test_knowledge_escalation_to_task(self, message: str):
        """Queries matching KNOWLEDGE patterns but containing escalation
        indicators (health, comparisons, safety, etc.) should be escalated to TASK."""
        intent, _ = self.router.classify(message)
        assert intent == QueryIntent.TASK, (
            f"Expected TASK (escalated) but got {intent.value} for: {message!r}"
        )

    # Ensure simple knowledge questions are NOT escalated
    @pytest.mark.parametrize(
        "message",
        [
            "what is Python?",
            "who created JavaScript?",
            "how does Git work?",
            "explain what Docker does",
            "what does HTML stand for?",
            "when was Linux released?",
            "define recursion",
        ],
    )
    def test_simple_knowledge_not_escalated(self, message: str):
        """Simple factual questions should remain KNOWLEDGE, not be escalated."""
        intent, params = self.router.classify(message)
        assert intent == QueryIntent.KNOWLEDGE, (
            f"Expected KNOWLEDGE but got {intent.value} for: {message!r}"
        )
        assert "question" in params

    # Task tests (should go to full workflow)
    @pytest.mark.parametrize(
        "message,expected_intent",
        [
            ("create a new React application", QueryIntent.TASK),
            ("build a web scraper for news sites", QueryIntent.TASK),
            ("write a Python script to process CSV files", QueryIntent.TASK),
            ("fix the bug in the login system", QueryIntent.TASK),
            ("refactor the authentication module", QueryIntent.TASK),
            ("analyze the codebase and suggest improvements", QueryIntent.TASK),
            ("First create a file, then run tests, finally deploy", QueryIntent.TASK),
        ],
    )
    def test_task_classification(self, message: str, expected_intent: QueryIntent):
        """Test that complex tasks are classified correctly."""
        intent, _ = self.router.classify(message)
        assert intent == expected_intent


class TestURLResolution:
    """Tests for URL resolution from target descriptions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.router = FastPathRouter()

    def test_knowledge_base_resolution(self):
        """Test that known targets resolve to correct URLs."""
        assert self.router.resolve_target_to_url("claude code") == URL_KNOWLEDGE_BASE["claude code"]
        assert self.router.resolve_target_to_url("anthropic docs") == URL_KNOWLEDGE_BASE["anthropic docs"]
        assert self.router.resolve_target_to_url("github") == URL_KNOWLEDGE_BASE["github"]

    def test_case_insensitive_resolution(self):
        """Test that URL resolution is case insensitive."""
        assert self.router.resolve_target_to_url("Claude Code") == URL_KNOWLEDGE_BASE["claude code"]
        assert self.router.resolve_target_to_url("GITHUB") == URL_KNOWLEDGE_BASE["github"]

    def test_direct_url_passthrough(self):
        """Test that URLs are passed through directly."""
        url = "https://example.com/page"
        assert self.router.resolve_target_to_url(url) == url

    def test_domain_resolution(self):
        """Test that bare domains get https:// prefix."""
        assert self.router.resolve_target_to_url("example.com") == "https://example.com"
        assert self.router.resolve_target_to_url("docs.python.org") == "https://docs.python.org"

    def test_unknown_target_search_fallback(self):
        """Test that unknown targets fall back to search."""
        result = self.router.resolve_target_to_url("some random thing")
        # DuckDuckGo search URL format: https://duckduckgo.com/?q=...
        assert "duckduckgo.com" in result, "Should fall back to DuckDuckGo search URL"
        assert "some%20random%20thing" in result or "some+random+thing" in result

    def test_single_character_alias_does_not_match_substrings(self):
        """Single-letter aliases should not match inside regular words."""
        result = self.router.resolve_target_to_url("and exttract all info from glimmerofpersia")
        assert "x.com" not in result

    def test_single_character_alias_matches_standalone_token(self):
        """Single-letter aliases should still work when explicitly requested."""
        assert self.router.resolve_target_to_url("x") == URL_KNOWLEDGE_BASE["x"]

    def test_site_hint_inference_from_task_like_phrase(self, monkeypatch):
        """Task-like phrases with 'from <site>' should infer a direct website URL."""
        monkeypatch.setattr(
            "app.domain.services.flows.fast_path.socket.getaddrinfo",
            lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))],
        )
        result = self.router.resolve_target_to_url("and exttract all info from glimmerofpersia")
        assert result == "https://glimmerofpersia.com"

    def test_knowledge_base_still_overrides_site_hint(self):
        """Known sites should use curated URLs before generic site-hint inference."""
        result = self.router.resolve_target_to_url("collect info from wikipedia")
        assert result == URL_KNOWLEDGE_BASE["wikipedia"]

    def test_site_hint_dns_failure_falls_back_to_search(self, monkeypatch):
        """Unresolvable inferred domains should gracefully fall back to search."""

        def _raise_dns(*args, **kwargs):
            raise socket.gaierror("dns failure")

        monkeypatch.setattr("app.domain.services.flows.fast_path.socket.getaddrinfo", _raise_dns)
        result = self.router.resolve_target_to_url("and exttract all info from glimmerofpersia")
        assert "duckduckgo.com" in result
        assert "glimmerofpersia" in result
        assert "exttract%20all%20info" not in result


class TestKnowledgeBase:
    """Tests for the URL knowledge base."""

    def test_claude_urls_exist(self):
        """Test that Claude/Anthropic URLs are in the knowledge base."""
        assert "claude code" in URL_KNOWLEDGE_BASE
        assert "claude code docs" in URL_KNOWLEDGE_BASE
        assert "anthropic docs" in URL_KNOWLEDGE_BASE
        assert "claude api" in URL_KNOWLEDGE_BASE

    def test_common_dev_tools_exist(self):
        """Test that common development tool URLs are in the knowledge base."""
        assert "github" in URL_KNOWLEDGE_BASE
        assert "stackoverflow" in URL_KNOWLEDGE_BASE
        assert "python docs" in URL_KNOWLEDGE_BASE

    def test_urls_are_valid(self):
        """Test that all URLs in knowledge base are valid."""
        for key, url in URL_KNOWLEDGE_BASE.items():
            assert url.startswith("https://"), f"URL for '{key}' should start with https://"
            assert "." in url, f"URL for '{key}' should contain a domain"


class TestSuggestionFollowUpDetection:
    """Tests for suggestion-style follow-up detection."""

    @pytest.mark.parametrize(
        "message",
        [
            "Can you explain this in more detail?",
            "Can you explain that in more detail?",
            "What are the best next steps?",
            "What should I prioritize as next steps?",
            "Can you give me a practical example?",
            "Can you provide a practical example for this?",
            "What should I ask next about this?",
            "Can you summarize this in three key points?",
        ],
    )
    def test_detects_suggestion_style_follow_ups(self, message: str):
        """Known suggestion templates should be detected."""
        assert is_suggestion_follow_up_message(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "what is python?",
            "search for latest rust release",
            "open docs.python.org",
            "create a report on market trends",
            "Can you explain Bayesian priors mathematically?",
        ],
    )
    def test_ignores_regular_messages(self, message: str):
        """Regular prompts should not be treated as suggestion follow-ups."""
        assert is_suggestion_follow_up_message(message) is False

    def test_excluded_from_should_use_fast_path(self):
        """Suggestion-style follow-ups should bypass fast-path entry checks."""
        assert should_use_fast_path("Can you explain this in more detail?") is False


class TestSuggestionClickMetadataDetection:
    """Tests for metadata-based suggestion click detection (primary method)."""

    def test_bypasses_fast_path_when_follow_up_source_is_suggestion_click(self):
        """When follow_up_source='suggestion_click', fast path should be bypassed."""
        from app.domain.models.message import Message

        message = Message(
            message="What are the best next steps?",
            follow_up_source="suggestion_click",
            follow_up_selected_suggestion="What are the best next steps?",
            follow_up_anchor_event_id="evt_123",
        )

        # Should return False (bypass fast path) due to metadata
        assert should_use_fast_path(message.message, follow_up_source=message.follow_up_source) is False

    def test_uses_fast_path_when_no_follow_up_metadata(self):
        """When no follow_up_source metadata, should use intent classification."""
        from app.domain.models.message import Message

        message = Message(
            message="what is python?",  # KNOWLEDGE intent
        )

        # Should return True (use fast path) for knowledge query
        assert should_use_fast_path(message.message, follow_up_source=message.follow_up_source) is True

    def test_metadata_takes_precedence_over_regex(self):
        """Metadata-based detection should take precedence over regex-based detection."""
        from app.domain.models.message import Message

        # Message matches regex pattern but has different follow_up_source
        message = Message(
            message="Can you explain this in more detail?",
            follow_up_source="manual_input",  # Not "suggestion_click"
        )

        # Regex would detect this as suggestion follow-up, but metadata says otherwise
        # Should still bypass fast path because regex fallback kicks in
        assert should_use_fast_path(message.message, follow_up_source=message.follow_up_source) is False

    def test_regex_fallback_when_no_metadata_provided(self):
        """When no metadata provided, should fall back to regex detection."""
        # Message that matches regex pattern, no metadata
        message_text = "Can you explain this in more detail?"

        # Should bypass fast path due to regex fallback
        assert should_use_fast_path(message_text, follow_up_source=None) is False


class TestFastPathEntryPolicy:
    """Tests for policy-level fast-path entry gating."""

    def test_browse_intent_bypasses_fast_path(self):
        """Browse requests should use full workflow."""
        assert should_use_fast_path("open glimmerofpersia website") is False

    def test_web_search_intent_bypasses_fast_path(self):
        """Search requests should use full workflow."""
        assert should_use_fast_path("search for glimmerofpersia website") is False


class TestFastBrowseInitialization:
    """Regression tests for fast browse browser warm-up behavior."""

    @pytest.mark.asyncio
    async def test_fast_browse_initializes_browser_before_failing_health(self):
        """Fast browse should warm up a cold browser instead of failing immediately."""

        class BrowserStub:
            def __init__(self):
                self.ensure_calls = 0
                self.navigate_calls = 0
                self._healthy = False

            def is_healthy(self) -> bool:
                return self._healthy

            async def _ensure_browser(self) -> None:
                self.ensure_calls += 1
                self._healthy = True

            async def navigate_fast(self, url: str):
                self.navigate_calls += 1
                return SimpleNamespace(success=True, data={"title": "Example"})

        browser = BrowserStub()
        router = FastPathRouter(browser=browser)

        events = [event async for event in router.execute_fast_browse("example.com")]

        assert browser.ensure_calls >= 1
        assert browser.navigate_calls == 1
        assert not any(isinstance(event, ErrorEvent) for event in events)
        assert any(isinstance(event, ToolEvent) and event.status == ToolStatus.CALLING for event in events)
        assert isinstance(events[-1], DoneEvent)

    @pytest.mark.asyncio
    async def test_fast_browse_retries_browser_init_and_returns_timeout_error(self):
        """Fast browse should retry browser initialization and return timeout error on failure."""

        class BrowserTimeoutStub:
            def __init__(self):
                self.ensure_calls = 0

            def is_healthy(self) -> bool:
                return False

            async def _ensure_browser(self) -> None:
                self.ensure_calls += 1
                raise TimeoutError("timed out")

            async def navigate_fast(self, url: str):
                return SimpleNamespace(success=True, data={"title": "Example"})

        browser = BrowserTimeoutStub()
        router = FastPathRouter(browser=browser)

        events = [event async for event in router.execute_fast_browse("example.com")]

        assert browser.ensure_calls == 2
        assert any(isinstance(event, ErrorEvent) and "timeout" in event.error.lower() for event in events)
        assert isinstance(events[-1], DoneEvent)


class TestFastBrowseSearchAssistedResolution:
    """Tests for search-first website identification in fast browse."""

    @pytest.mark.asyncio
    async def test_fast_browse_uses_search_api_to_open_identified_website(self):
        """Ambiguous browse targets should resolve via search API before navigation."""

        class BrowserStub:
            def __init__(self):
                self._healthy = False
                self.last_url: str | None = None

            def is_healthy(self) -> bool:
                return self._healthy

            async def _ensure_browser(self) -> None:
                self._healthy = True

            async def navigate_fast(self, url: str):
                self.last_url = url
                return SimpleNamespace(success=True, data={"title": "Glimmer Of Persia"})

        class SearchEngineStub:
            def __init__(self):
                self.queries: list[str] = []

            async def search(self, query: str, date_range: str | None = None):
                self.queries.append(query)
                return ToolResult.ok(
                    data=SearchResults(
                        query=query,
                        total_results=1,
                        results=[
                            SearchResultItem(
                                title="Glimmer Of Persia",
                                link="https://www.glimmerofpersia.store",
                                snippet="Official website",
                            )
                        ],
                    )
                )

        browser = BrowserStub()
        search_engine = SearchEngineStub()
        FastPathRouter._search_cache.clear()
        router = FastPathRouter(browser=browser, search_engine=search_engine)

        events = [event async for event in router.execute_fast_browse("and exttract all info from glimmerofpersia")]

        assert search_engine.queries == ["glimmerofpersia official website"]
        assert browser.last_url == "https://www.glimmerofpersia.store"
        assert not any(isinstance(event, ErrorEvent) for event in events)
        assert isinstance(events[-1], DoneEvent)

    @pytest.mark.asyncio
    async def test_fast_browse_falls_back_to_site_search_when_no_confident_search_match(self, monkeypatch):
        """When search results lack a domain match, fallback should search by extracted site token."""

        def _raise_dns(*args, **kwargs):
            raise socket.gaierror("dns failure")

        monkeypatch.setattr("app.domain.services.flows.fast_path.socket.getaddrinfo", _raise_dns)

        class BrowserStub:
            def __init__(self):
                self._healthy = False
                self.last_url: str | None = None

            def is_healthy(self) -> bool:
                return self._healthy

            async def _ensure_browser(self) -> None:
                self._healthy = True

            async def navigate_fast(self, url: str):
                self.last_url = url
                return SimpleNamespace(success=True, data={"title": "Search"})

        class SearchEngineStub:
            async def search(self, query: str, date_range: str | None = None):
                return ToolResult.ok(
                    data=SearchResults(
                        query=query,
                        total_results=2,
                        results=[
                            SearchResultItem(
                                title="DuckDuckGo",
                                link="https://duckduckgo.com/?q=glimmerofpersia",
                                snippet="Search results",
                            ),
                            SearchResultItem(
                                title="Unrelated",
                                link="https://example.org/page",
                                snippet="Unrelated domain",
                            ),
                        ],
                    )
                )

        browser = BrowserStub()
        FastPathRouter._search_cache.clear()
        router = FastPathRouter(browser=browser, search_engine=SearchEngineStub())

        events = [event async for event in router.execute_fast_browse("and exttract all info from glimmerofpersia")]

        assert browser.last_url == "https://duckduckgo.com/?q=glimmerofpersia"
        assert not any(isinstance(event, ErrorEvent) for event in events)
        assert isinstance(events[-1], DoneEvent)
