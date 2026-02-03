"""Tests for Browser Agent LangGraph Node

Phase 2 Enhancement: Tests for browser-use as first-class LangGraph node.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.services.langgraph.nodes.browser_agent_node import (
    BROWSER_USE_AVAILABLE,
    BrowserNodeConfig,
    BrowserNodeResult,
    BrowserStepEvent,
    BrowserStepStatus,
    browser_agent_node,
    should_use_browser_node,
)


class TestBrowserStepEvent:
    """Tests for BrowserStepEvent dataclass."""

    def test_default_values(self):
        """Test default values for browser step event."""
        event = BrowserStepEvent()
        assert event.type == "browser_step"
        assert event.step_number == 0
        assert event.status == BrowserStepStatus.STARTED
        assert event.action is None
        assert event.thought is None
        assert event.url is None
        assert event.screenshot_base64 is None
        assert event.error is None
        assert event.metadata == {}

    def test_custom_values(self):
        """Test browser step event with custom values."""
        event = BrowserStepEvent(
            step_number=5,
            status=BrowserStepStatus.ACTING,
            action="click button",
            thought="Need to submit form",
            url="https://example.com",
            metadata={"selector": "#submit"},
        )
        assert event.step_number == 5
        assert event.status == BrowserStepStatus.ACTING
        assert event.action == "click button"
        assert event.thought == "Need to submit form"
        assert event.url == "https://example.com"
        assert event.metadata == {"selector": "#submit"}


class TestBrowserNodeResult:
    """Tests for BrowserNodeResult dataclass."""

    def test_successful_result(self):
        """Test successful browser node result."""
        result = BrowserNodeResult(
            success=True,
            result="Task completed",
            steps_executed=10,
            final_url="https://example.com/result",
            execution_time_ms=5000.0,
        )
        assert result.success is True
        assert result.result == "Task completed"
        assert result.steps_executed == 10
        assert result.final_url == "https://example.com/result"
        assert result.errors == []
        assert result.interrupted is False

    def test_failed_result(self):
        """Test failed browser node result."""
        result = BrowserNodeResult(
            success=False,
            errors=["Timeout", "Element not found"],
            steps_executed=3,
        )
        assert result.success is False
        assert len(result.errors) == 2
        assert "Timeout" in result.errors

    def test_interrupted_result(self):
        """Test interrupted browser node result."""
        result = BrowserNodeResult(
            success=False,
            interrupted=True,
            steps_executed=5,
        )
        assert result.interrupted is True


class TestBrowserNodeConfig:
    """Tests for BrowserNodeConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BrowserNodeConfig()
        assert config.max_steps == 15
        assert config.timeout_seconds == 300
        assert config.use_vision is True
        assert config.capture_screenshots is True
        assert config.stream_events is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = BrowserNodeConfig(
            max_steps=5,
            timeout_seconds=60,
            use_vision=False,
            capture_screenshots=False,
            stream_events=False,
        )
        assert config.max_steps == 5
        assert config.timeout_seconds == 60
        assert config.use_vision is False


class TestShouldUseBrowserNode:
    """Tests for should_use_browser_node routing function."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.feature_browser_node = True
        return settings

    def test_feature_disabled(self, mock_settings):
        """Test routing when feature is disabled."""
        mock_settings.feature_browser_node = False
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            state = {"current_step": MagicMock(description="Navigate to website")}
            assert should_use_browser_node(state) is False

    def test_browser_use_unavailable(self, mock_settings):
        """Test routing when browser_use is not installed."""
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "app.domain.services.langgraph.nodes.browser_agent_node.BROWSER_USE_AVAILABLE",
                False,
            ):
                state = {"current_step": MagicMock(description="Navigate to website")}
                assert should_use_browser_node(state) is False

    def test_no_current_step(self, mock_settings):
        """Test routing when no current step."""
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            state = {}
            assert should_use_browser_node(state) is False

    def test_browser_keyword_browse(self, mock_settings):
        """Test routing for 'browse' keyword."""
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "app.domain.services.langgraph.nodes.browser_agent_node.BROWSER_USE_AVAILABLE",
                True,
            ):
                state = {"current_step": MagicMock(description="Browse to google.com")}
                assert should_use_browser_node(state) is True

    def test_browser_keyword_navigate(self, mock_settings):
        """Test routing for 'navigate' keyword."""
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "app.domain.services.langgraph.nodes.browser_agent_node.BROWSER_USE_AVAILABLE",
                True,
            ):
                state = {"current_step": MagicMock(description="Navigate to login page")}
                assert should_use_browser_node(state) is True

    def test_browser_keyword_fill_form(self, mock_settings):
        """Test routing for 'fill form' keyword."""
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "app.domain.services.langgraph.nodes.browser_agent_node.BROWSER_USE_AVAILABLE",
                True,
            ):
                state = {"current_step": MagicMock(description="Fill form with user data")}
                assert should_use_browser_node(state) is True

    def test_non_browser_task(self, mock_settings):
        """Test routing for non-browser task."""
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "app.domain.services.langgraph.nodes.browser_agent_node.BROWSER_USE_AVAILABLE",
                True,
            ):
                state = {"current_step": MagicMock(description="Calculate the sum of numbers")}
                assert should_use_browser_node(state) is False

    def test_explicit_browser_task_set(self, mock_settings):
        """Test routing when browser_task is explicitly set."""
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "app.domain.services.langgraph.nodes.browser_agent_node.BROWSER_USE_AVAILABLE",
                True,
            ):
                state = {
                    "current_step": MagicMock(description="Do something"),
                    "browser_task": "Navigate to example.com",
                }
                assert should_use_browser_node(state) is True


class TestBrowserAgentNode:
    """Tests for browser_agent_node function."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings with browser node enabled."""
        settings = MagicMock()
        settings.feature_browser_node = True
        settings.browser_agent_max_steps = 15
        settings.browser_agent_timeout = 300
        settings.browser_agent_use_vision = True
        return settings

    @pytest.mark.asyncio
    async def test_feature_disabled(self, mock_settings):
        """Test node returns empty result when feature disabled."""
        mock_settings.feature_browser_node = False
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            state = {"browser_task": "Navigate to google.com"}
            result = await browser_agent_node(state)
            assert result["browser_result"] is None
            assert result["pending_events"] == []

    @pytest.mark.asyncio
    async def test_no_browser_task(self, mock_settings):
        """Test node returns empty result when no browser task."""
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            state = {}
            result = await browser_agent_node(state)
            assert result["browser_result"] is None

    @pytest.mark.asyncio
    async def test_no_cdp_url(self, mock_settings):
        """Test node returns error when no CDP URL."""
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "app.domain.services.langgraph.nodes.browser_agent_node.BROWSER_USE_AVAILABLE",
                True,
            ):
                state = {"browser_task": "Navigate to google.com"}
                result = await browser_agent_node(state)
                assert result["browser_result"].success is False
                assert "No CDP URL" in result["browser_result"].errors[0]

    @pytest.mark.asyncio
    async def test_browser_use_not_available(self, mock_settings):
        """Test node returns error when browser_use not installed."""
        with patch(
            "app.domain.services.langgraph.nodes.browser_agent_node.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "app.domain.services.langgraph.nodes.browser_agent_node.BROWSER_USE_AVAILABLE",
                False,
            ):
                state = {
                    "browser_task": "Navigate to google.com",
                    "cdp_url": "ws://localhost:9222",
                }
                result = await browser_agent_node(state)
                assert result["browser_result"].success is False
                assert "not installed" in result["browser_result"].errors[0]


class TestBrowserStepStatus:
    """Tests for BrowserStepStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert BrowserStepStatus.STARTED.value == "started"
        assert BrowserStepStatus.THINKING.value == "thinking"
        assert BrowserStepStatus.ACTING.value == "acting"
        assert BrowserStepStatus.COMPLETED.value == "completed"
        assert BrowserStepStatus.FAILED.value == "failed"
        assert BrowserStepStatus.INTERRUPTED.value == "interrupted"

    def test_status_is_string_enum(self):
        """Test that status values are strings."""
        assert isinstance(BrowserStepStatus.STARTED, str)
        assert BrowserStepStatus.STARTED == "started"
