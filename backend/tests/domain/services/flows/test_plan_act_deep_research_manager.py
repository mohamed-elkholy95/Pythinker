"""Integration tests for PlanActFlow deep research manager orchestration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.flows.plan_act import PlanActFlow


@pytest.fixture
def mock_search_engine():
    engine = AsyncMock()
    engine.search = AsyncMock(
        return_value=ToolResult(
            success=True,
            data=SearchResults(
                query="test query",
                results=[SearchResultItem(title="Result 1", link="https://example.com", snippet="Snippet")],
            ),
        )
    )
    return engine


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.ask = AsyncMock(return_value={"content": "test response"})
    llm.model_name = "test-model"
    llm.count_tokens = MagicMock(return_value=100)
    return llm


@pytest.fixture
def mock_sandbox():
    sandbox = AsyncMock()
    sandbox.shell = AsyncMock()
    sandbox.file = AsyncMock()
    return sandbox


@pytest.fixture
def mock_browser():
    browser = AsyncMock()
    browser.navigate = AsyncMock(return_value=ToolResult(success=True, data={"content": "page"}))
    return browser


@pytest.fixture
def mock_json_parser():
    parser = MagicMock()
    parser.parse = MagicMock(return_value={})
    return parser


@pytest.fixture
def mock_mcp_tool():
    tool = MagicMock()
    tool.name = "mcp"
    tool.description = "MCP tool"
    return tool


@pytest.fixture
def flow(
    mock_search_engine,
    mock_llm,
    mock_sandbox,
    mock_browser,
    mock_json_parser,
    mock_mcp_tool,
):
    agent_repo = AsyncMock()
    session_repo = AsyncMock()
    return PlanActFlow(
        agent_id="test_agent",
        agent_repository=agent_repo,
        session_id="test_session",
        session_repository=session_repo,
        llm=mock_llm,
        sandbox=mock_sandbox,
        browser=mock_browser,
        json_parser=mock_json_parser,
        mcp_tool=mock_mcp_tool,
        search_engine=mock_search_engine,
    )


@pytest.mark.asyncio
async def test_execute_deep_research_uses_manager_lifecycle(flow):
    manager = AsyncMock()
    manager.register = AsyncMock()
    manager.unregister = AsyncMock()

    with patch("app.core.deep_research_manager.get_deep_research_manager", return_value=manager):
        events = [
            event async for event in flow._execute_deep_research("python testing", "research python testing", None)
        ]

    manager.register.assert_awaited_once()
    register_args = manager.register.await_args.args
    assert register_args[0] == "test_session"
    assert register_args[1].__class__.__name__ == "DeepResearchFlow"
    manager.unregister.assert_awaited_once_with("test_session")

    event_types = [event.type for event in events]
    assert "deep_research" in event_types
    assert "report" in event_types
    assert event_types[-1] == "done"


@pytest.mark.asyncio
async def test_execute_deep_research_without_search_engine_returns_message_and_done(
    mock_llm,
    mock_sandbox,
    mock_browser,
    mock_json_parser,
    mock_mcp_tool,
):
    agent_repo = AsyncMock()
    session_repo = AsyncMock()
    flow = PlanActFlow(
        agent_id="test_agent",
        agent_repository=agent_repo,
        session_id="test_session",
        session_repository=session_repo,
        llm=mock_llm,
        sandbox=mock_sandbox,
        browser=mock_browser,
        json_parser=mock_json_parser,
        mcp_tool=mock_mcp_tool,
        search_engine=None,
    )

    events = [event async for event in flow._execute_deep_research("python testing", "research python testing", None)]

    assert [event.type for event in events] == ["message", "done"]
    assert "not available" in events[0].message.lower()
