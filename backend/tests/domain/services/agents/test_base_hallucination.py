# backend/tests/domain/services/agents/test_base_hallucination.py
"""Tests for BaseAgent hallucination detection in invoke_tool.

These tests verify that the hallucination detector is properly integrated
into the tool invocation flow, catching invalid tools and parameters
BEFORE execution.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base import BaseAgent
from app.domain.services.agents.hallucination_detector import ToolHallucinationDetector


@pytest.fixture
def mock_agent_repository():
    """Create a mock agent repository."""
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
    """Create a mock LLM."""
    llm = MagicMock()
    llm.model_name = "gpt-4"
    return llm


@pytest.fixture
def mock_json_parser():
    """Create a mock JSON parser."""
    parser = AsyncMock()
    parser.parse = AsyncMock(return_value={})
    return parser


@pytest.fixture
def mock_tool():
    """Create a mock tool with get_tools method."""
    tool = MagicMock()
    tool.name = "test_tool"
    tool.get_tools = MagicMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"},
                            "encoding": {"type": "string", "description": "File encoding"},
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "file_write",
                    "description": "Write to a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"},
                            "content": {"type": "string", "description": "File content"},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
        ]
    )
    tool.has_function = MagicMock(side_effect=lambda name: name in ["file_read", "file_write"])
    tool.invoke_function = AsyncMock(return_value=ToolResult.ok(message="Success"))
    return tool


@pytest.fixture
def base_agent(mock_agent_repository, mock_llm, mock_json_parser, mock_tool):
    """Create a BaseAgent with a mock tool."""
    return BaseAgent(
        agent_id="test-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        tools=[mock_tool],
    )


class TestHallucinationDetectorInitialization:
    """Tests for hallucination detector initialization with tool schemas."""

    def test_detector_initialized_with_tool_names(self, mock_agent_repository, mock_llm, mock_json_parser, mock_tool):
        """Detector should be initialized with available tool names."""
        agent = BaseAgent(
            agent_id="test",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            json_parser=mock_json_parser,
            tools=[mock_tool],
        )

        # Check that tool names are in the detector
        assert "file_read" in agent._hallucination_detector.available_tools
        assert "file_write" in agent._hallucination_detector.available_tools

    def test_detector_initialized_with_tool_schemas(self, mock_agent_repository, mock_llm, mock_json_parser, mock_tool):
        """Detector should be initialized with tool parameter schemas."""
        agent = BaseAgent(
            agent_id="test",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            json_parser=mock_json_parser,
            tools=[mock_tool],
        )

        # Check that schemas are loaded
        schemas = agent._hallucination_detector._tool_schemas
        assert "file_read" in schemas
        assert "file_write" in schemas

        # Verify schema structure
        file_read_schema = schemas["file_read"]
        assert "path" in file_read_schema["required"]
        assert "path" in file_read_schema["properties"]

    def test_refresh_hallucination_detector_updates_schemas(
        self, mock_agent_repository, mock_llm, mock_json_parser, mock_tool
    ):
        """refresh_hallucination_detector should update both names and schemas."""
        agent = BaseAgent(
            agent_id="test",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            json_parser=mock_json_parser,
            tools=[mock_tool],
        )

        # Add a new tool
        new_tool = MagicMock()
        new_tool.get_tools = MagicMock(
            return_value=[
                {
                    "type": "function",
                    "function": {
                        "name": "new_tool",
                        "description": "New tool",
                        "parameters": {
                            "type": "object",
                            "properties": {"arg": {"type": "string"}},
                            "required": ["arg"],
                        },
                    },
                }
            ]
        )
        agent.tools.append(new_tool)

        # Refresh the detector
        agent.refresh_hallucination_detector()

        # Check new tool is available
        assert "new_tool" in agent._hallucination_detector.available_tools
        assert "new_tool" in agent._hallucination_detector._tool_schemas


class TestPreExecutionHallucinationDetection:
    """Tests for hallucination detection in invoke_tool."""

    @pytest.mark.asyncio
    async def test_valid_tool_call_executes(self, base_agent, mock_tool):
        """Valid tool calls should execute normally."""
        result = await base_agent.invoke_tool(
            tool=mock_tool,
            function_name="file_read",
            arguments={"path": "/tmp/test.txt"},
        )

        assert result.success is True
        mock_tool.invoke_function.assert_called_once()

    @pytest.mark.asyncio
    async def test_hallucinated_tool_returns_error(self, base_agent, mock_tool):
        """Hallucinated tool names should return error without execution."""
        # Manually inject a hallucination check failure
        base_agent._hallucination_detector.available_tools = {"file_read", "file_write"}

        # Try to call a non-existent tool
        result = await base_agent.invoke_tool(
            tool=mock_tool,
            function_name="nonexistent_tool",
            arguments={"path": "/tmp/test.txt"},
        )

        assert result.success is False
        assert "does not exist" in result.message
        # Tool should NOT be executed
        mock_tool.invoke_function.assert_not_called()

    @pytest.mark.asyncio
    async def test_hallucinated_tool_includes_suggestions(self, base_agent, mock_tool):
        """Hallucinated tool errors should include similar tool suggestions."""
        # Try a tool name similar to an existing one
        result = await base_agent.invoke_tool(
            tool=mock_tool,
            function_name="file_reed",  # Typo of "file_read"
            arguments={"path": "/tmp/test.txt"},
        )

        assert result.success is False
        # Should suggest the similar tool
        assert "file_read" in result.message or "Suggestions" in result.message

    @pytest.mark.asyncio
    async def test_missing_required_params_returns_error(self, base_agent, mock_tool):
        """Missing required parameters should return error without execution."""
        result = await base_agent.invoke_tool(
            tool=mock_tool,
            function_name="file_write",
            arguments={"path": "/tmp/test.txt"},  # Missing required "content"
        )

        assert result.success is False
        assert "Missing required parameters" in result.message or "content" in result.message
        mock_tool.invoke_function.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_param_type_returns_error(self, base_agent, mock_tool):
        """Invalid parameter types should return error without execution."""
        result = await base_agent.invoke_tool(
            tool=mock_tool,
            function_name="file_read",
            arguments={"path": 12345},  # Should be string, not int
        )

        assert result.success is False
        assert "type" in result.message.lower() or "expected" in result.message.lower()
        mock_tool.invoke_function.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_params_with_optional_field(self, base_agent, mock_tool):
        """Tool calls with valid required params and optional params should execute."""
        result = await base_agent.invoke_tool(
            tool=mock_tool,
            function_name="file_read",
            arguments={
                "path": "/tmp/test.txt",
                "encoding": "utf-8",  # Optional param
            },
        )

        assert result.success is True
        mock_tool.invoke_function.assert_called_once()


class TestHallucinationDetectorIntegration:
    """Tests for hallucination detector integration with agent lifecycle."""

    def test_get_filtered_tools_updates_detector(self, mock_agent_repository, mock_llm, mock_json_parser, mock_tool):
        """get_filtered_tools should update hallucination detector with filtered tools."""
        agent = BaseAgent(
            agent_id="test",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            json_parser=mock_json_parser,
            tools=[mock_tool],
        )

        # This method updates the hallucination detector
        filtered_tools = agent.get_filtered_tools("read a file")

        # Verify detector was updated (indirectly through the method)
        assert len(filtered_tools) > 0

    def test_reliability_stats_includes_hallucination_info(self, base_agent):
        """get_reliability_stats should include hallucination detector info."""
        stats = base_agent.get_reliability_stats()

        assert "hallucination_detector" in stats
        assert "available_tools" in stats["hallucination_detector"]


class TestHallucinationDetectorUnit:
    """Unit tests for ToolHallucinationDetector validate_tool_call method."""

    def test_validate_valid_tool_call(self):
        """Valid tool call should pass validation."""
        detector = ToolHallucinationDetector(["file_read", "file_write"])
        detector.update_tool_schemas(
            {
                "file_read": {
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                }
            }
        )

        result = detector.validate_tool_call(
            tool_name="file_read",
            parameters={"path": "/tmp/test.txt"},
        )

        assert result.is_valid is True
        assert result.error_message is None

    def test_validate_nonexistent_tool(self):
        """Non-existent tool should fail validation."""
        detector = ToolHallucinationDetector(["file_read", "file_write"])

        result = detector.validate_tool_call(
            tool_name="nonexistent_tool",
            parameters={"path": "/tmp/test.txt"},
        )

        assert result.is_valid is False
        assert result.error_type == "tool_not_found"
        assert "does not exist" in result.error_message

    def test_validate_missing_required_param(self):
        """Missing required parameter should fail validation."""
        detector = ToolHallucinationDetector(["file_read"])
        detector.update_tool_schemas(
            {
                "file_read": {
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                }
            }
        )

        result = detector.validate_tool_call(
            tool_name="file_read",
            parameters={},  # Missing "path"
        )

        assert result.is_valid is False
        assert result.error_type == "missing_params"

    def test_validate_invalid_param_type(self):
        """Invalid parameter type should fail validation."""
        detector = ToolHallucinationDetector(["file_read"])
        detector.update_tool_schemas(
            {
                "file_read": {
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                }
            }
        )

        result = detector.validate_tool_call(
            tool_name="file_read",
            parameters={"path": 12345},  # Should be string
        )

        assert result.is_valid is False
        assert result.error_type == "invalid_type"

    def test_validate_without_schema(self):
        """Tools without schemas should pass validation (cannot validate params)."""
        detector = ToolHallucinationDetector(["custom_tool"])
        # No schema provided for custom_tool

        result = detector.validate_tool_call(
            tool_name="custom_tool",
            parameters={"any": "params"},
        )

        # Should pass because we can't validate without a schema
        assert result.is_valid is True

    def test_similar_tool_suggestions(self):
        """Hallucinated tools should get suggestions for similar tools."""
        detector = ToolHallucinationDetector(["file_read", "file_write", "file_delete"])

        result = detector.validate_tool_call(
            tool_name="file_reed",  # Typo
            parameters={},
        )

        assert result.is_valid is False
        assert "file_read" in result.suggestions
