"""Tests for the FastPathRouter module.

Tests query classification and URL resolution for fast-path routing.
"""

import pytest

from app.domain.services.flows.fast_path import (
    URL_KNOWLEDGE_BASE,
    FastPathRouter,
    QueryIntent,
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
        # Accept either Google or SearXNG search URLs depending on configuration
        assert "/search" in result, "Should fall back to search URL"
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
