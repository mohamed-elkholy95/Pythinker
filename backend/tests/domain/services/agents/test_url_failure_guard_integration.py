"""Integration tests for URL failure guard wiring in BaseAgent."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base import BaseAgent, _extract_url_from_args
from app.domain.services.agents.url_failure_guard import UrlFailureGuard


@pytest.fixture
def mock_agent_repository():
    repo = AsyncMock()
    repo.get_memory = AsyncMock(
        return_value=MagicMock(
            empty=True,
            get_messages=MagicMock(return_value=[]),
            add_message=MagicMock(),
            add_messages=MagicMock(),
        )
    )
    return repo


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.model_name = "gpt-4"
    return llm


@pytest.fixture
def mock_json_parser():
    parser = AsyncMock()
    parser.parse = AsyncMock(return_value={})
    return parser


@pytest.fixture
def mock_tool():
    tool = MagicMock()
    tool.name = "test_tool"
    tool.get_tools = MagicMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "browser_get_content",
                    "description": "Fetch URL content",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "info_search_web",
                    "description": "Search web",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            },
        ]
    )
    tool.has_function = MagicMock(side_effect=lambda name: name in {"browser_get_content", "info_search_web"})
    tool.invoke_function = AsyncMock(return_value=ToolResult.ok(message="Success"))
    return tool


@pytest.fixture
def base_agent(mock_agent_repository, mock_llm, mock_json_parser, mock_tool):
    return BaseAgent(
        agent_id="test-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        tools=[mock_tool],
    )


class TestExtractUrlFromArgs:
    def test_extract_url_key(self):
        assert _extract_url_from_args({"url": "https://example.com"}) == "https://example.com"

    def test_extract_target_url_key(self):
        assert _extract_url_from_args({"target_url": "https://example.com"}) == "https://example.com"

    def test_extract_page_url_key(self):
        assert _extract_url_from_args({"page_url": "https://example.com"}) == "https://example.com"

    def test_non_http_urls_ignored(self):
        assert _extract_url_from_args({"url": "file:///tmp/x"}) is None

    def test_missing_url(self):
        assert _extract_url_from_args({"query": "test"}) is None


class TestInvokeToolGuardIntegration:
    @pytest.mark.asyncio
    async def test_tier3_block_skips_tool_execution(self, base_agent, mock_tool):
        guard = UrlFailureGuard(max_failures_per_url=3)
        blocked_url = "https://vuejs.org/guide/best-practices/"
        guard.record_failure(blocked_url, "HTTP 404 Not Found", "browser_get_content")
        guard.record_failure(blocked_url, "HTTP 404 Not Found", "browser_get_content")
        base_agent._url_failure_guard = guard

        result = await base_agent.invoke_tool(
            tool=mock_tool,
            function_name="browser_get_content",
            arguments={"url": blocked_url},
        )

        assert result.success is False
        assert "BLOCKED" in (result.message or "")
        mock_tool.invoke_function.assert_not_called()

    @pytest.mark.asyncio
    async def test_tier2_warn_allows_execution_and_injects_nudge(self, base_agent, mock_tool):
        guard = UrlFailureGuard(max_failures_per_url=3)
        warned_url = "https://example.com/missing"
        guard.record_failure(warned_url, "HTTP 404 Not Found", "browser_get_content")
        base_agent._url_failure_guard = guard

        result = await base_agent.invoke_tool(
            tool=mock_tool,
            function_name="browser_get_content",
            arguments={"url": warned_url},
        )

        assert result.success is True
        mock_tool.invoke_function.assert_called_once()
        assert base_agent._efficiency_nudges
        assert "do NOT retry".lower() in base_agent._efficiency_nudges[-1]["message"].lower()

    @pytest.mark.asyncio
    async def test_failed_url_call_is_recorded(self, base_agent, mock_tool):
        failed_url = "https://example.com/404"
        base_agent._url_failure_guard = UrlFailureGuard(max_failures_per_url=3)
        mock_tool.invoke_function = AsyncMock(return_value=ToolResult(success=False, message="HTTP 404 Not Found"))

        result = await base_agent.invoke_tool(
            tool=mock_tool,
            function_name="browser_get_content",
            arguments={"url": failed_url},
        )

        assert result.success is False
        decision = base_agent._url_failure_guard.check_url(failed_url)
        assert decision.action == "warn"
        assert decision.tier == 2

    @pytest.mark.skip(reason="Task 6: search result URL feeding to guard not yet implemented in invoke_tool")
    @pytest.mark.asyncio
    async def test_search_results_feed_guard_alternatives(self, base_agent, mock_tool):
        failed_url = "https://bad.example/404"
        base_agent._url_failure_guard = UrlFailureGuard(max_failures_per_url=3)

        mock_tool.invoke_function = AsyncMock(
            return_value=ToolResult(
                success=True,
                message="search done",
                data=SimpleNamespace(
                    results=[
                        SimpleNamespace(link="https://docs.example/guide"),
                        SimpleNamespace(link="https://docs.example/api"),
                    ]
                ),
            )
        )

        search_result = await base_agent.invoke_tool(
            tool=mock_tool,
            function_name="info_search_web",
            arguments={"query": "example docs"},
        )

        assert search_result.success is True

        base_agent._url_failure_guard.record_failure(failed_url, "HTTP 404", "browser_get_content")
        decision = base_agent._url_failure_guard.check_url(failed_url)

        assert decision.action == "warn"
        assert decision.alternative_urls
        assert "https://docs.example/guide" in decision.alternative_urls
