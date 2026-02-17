"""Tests for the FastPathRouter module.

Tests query classification and URL resolution for fast-path routing.
"""

import pytest

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
