"""
Pytest configuration and fixtures for Pythinker backend testing.

Provides comprehensive fixtures for:
- Mock LLM clients for testing without API calls
- Mock sandbox environments
- Test sessions with mocked dependencies
- Database and cache mocking
- HTTP client mocking
"""

import asyncio
import importlib.util
import json
import site
import sys
import tempfile

# Increase recursion limit for test collection with many test files
# The default 1000 can be exceeded during deep import chains when running full suite
sys.setrecursionlimit(10000)
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Fix langgraph import shadowing issue BEFORE any app imports
# The local app/domain/services/langgraph module shadows the installed langgraph package
def _preload_langgraph():
    """Preload the langgraph package from site-packages to prevent shadowing."""
    # Get site-packages directories
    site_packages = site.getsitepackages()
    if hasattr(site, 'getusersitepackages'):
        user_site = site.getusersitepackages()
        if user_site:
            site_packages.append(user_site)

    for sp in site_packages:
        pkg_path = Path(sp) / 'langgraph'
        if pkg_path.exists():
            # Load the checkpoint module directly from site-packages
            checkpoint_init = pkg_path / 'checkpoint' / 'base' / '__init__.py'
            if checkpoint_init.exists():
                spec = importlib.util.spec_from_file_location(
                    'langgraph.checkpoint.base',
                    checkpoint_init,
                    submodule_search_locations=[str(pkg_path / 'checkpoint' / 'base')]
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules['langgraph.checkpoint.base'] = module
                    spec.loader.exec_module(module)
                    return True
    return False

# Preload langgraph before any app imports
_preload_langgraph()

# Add the parent directory to Python path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

# Base URL for API testing
BASE_URL = "http://localhost:8000/api/v1"


# =============================================================================
# HTTP Client Fixtures
# =============================================================================


@pytest.fixture
def client():
    """Create requests session for synchronous API testing."""
    return requests.Session()
    # Don't set default Content-Type to allow multipart/form-data for file uploads


@pytest.fixture
def auth_headers():
    """Headers with mock authentication token."""
    return {
        "Authorization": "Bearer test-token-12345",
        "Content-Type": "application/json",
    }


# =============================================================================
# Mock LLM Fixtures
# =============================================================================


@pytest.fixture
def mock_llm_response():
    """Factory for creating mock LLM responses."""

    def _create_response(
        content: str = "Test response",
        tool_calls: list[dict] | None = None,
        role: str = "assistant",
    ) -> dict[str, Any]:
        response = {
            "role": role,
            "content": content,
        }
        if tool_calls:
            response["tool_calls"] = tool_calls
        return response

    return _create_response


@pytest.fixture
def mock_llm(mock_llm_response):
    """Mock LLM client for testing without API calls.

    Returns an AsyncMock configured to return standard responses.
    Can be customized by setting return_value on the ask method.
    """
    llm = AsyncMock()

    # Default response
    llm.ask.return_value = mock_llm_response(content="This is a test response from the mock LLM.")

    # Model info
    llm.model_name = "test-model"
    llm.provider = "test"

    # Token counting (mock)
    llm.count_tokens.return_value = 100

    # Streaming support
    async def mock_stream(*args, **kwargs):
        yield "This is "
        yield "a streaming "
        yield "response."

    llm.ask_stream = mock_stream

    return llm


@pytest.fixture
def mock_llm_with_tool_call(mock_llm):
    """Mock LLM that returns a tool call response."""
    tool_call_response = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call_123", "function": {"name": "file_read", "arguments": json.dumps({"path": "/test/file.txt"})}}
        ],
    }
    mock_llm.ask.return_value = tool_call_response
    return mock_llm


@pytest.fixture
def mock_llm_json_response(mock_llm):
    """Mock LLM that returns valid JSON responses."""
    json_response = {
        "role": "assistant",
        "content": json.dumps({"action": "complete", "result": "Task completed successfully", "confidence": 0.95}),
    }
    mock_llm.ask.return_value = json_response
    return mock_llm


# =============================================================================
# Mock Sandbox Fixtures
# =============================================================================


@pytest.fixture
def mock_sandbox():
    """Mock sandbox for testing without Docker.

    Provides a mock sandbox environment that simulates:
    - Shell command execution
    - File operations
    - Browser interactions
    """
    sandbox = AsyncMock()

    # Basic properties
    sandbox.session_id = "test-session-123"
    sandbox.workspace = "/workspace"
    sandbox.is_running = True

    # Shell execution
    async def mock_shell_execute(command: str, **kwargs):
        return {
            "stdout": f"Mock output for: {command}",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 100,
        }

    sandbox.shell_execute = AsyncMock(side_effect=mock_shell_execute)

    # File operations
    async def mock_file_read(path: str, **kwargs):
        return {
            "content": f"Mock content of {path}",
            "encoding": "utf-8",
            "size": 100,
        }

    sandbox.file_read = AsyncMock(side_effect=mock_file_read)

    async def mock_file_write(path: str, content: str, **kwargs):
        return {"success": True, "path": path}

    sandbox.file_write = AsyncMock(side_effect=mock_file_write)

    # Browser mock
    sandbox.browser = AsyncMock()
    sandbox.browser.navigate = AsyncMock(return_value={"url": "https://example.com"})
    sandbox.browser.get_content = AsyncMock(return_value={"content": "<html>Mock</html>"})

    # Lifecycle
    sandbox.start = AsyncMock()
    sandbox.stop = AsyncMock()
    sandbox.cleanup = AsyncMock()

    return sandbox


@pytest.fixture
def mock_sandbox_manager(mock_sandbox):
    """Mock sandbox manager for session tests."""
    manager = AsyncMock()
    manager.create_sandbox = AsyncMock(return_value=mock_sandbox)
    manager.get_sandbox = AsyncMock(return_value=mock_sandbox)
    manager.destroy_sandbox = AsyncMock()
    return manager


# =============================================================================
# Mock Database Fixtures
# =============================================================================


@pytest.fixture
def mock_mongodb():
    """Mock MongoDB client for testing."""
    mongo = AsyncMock()
    mongo.client = MagicMock()
    mongo.initialize = AsyncMock()
    mongo.shutdown = AsyncMock()

    # Collection mocks
    mongo.client.__getitem__ = MagicMock(return_value=MagicMock())

    return mongo


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis = AsyncMock()
    redis.client = AsyncMock()
    redis.initialize = AsyncMock()
    redis.shutdown = AsyncMock()

    # Basic operations
    redis.client.get = AsyncMock(return_value=None)
    redis.client.set = AsyncMock(return_value=True)
    redis.client.delete = AsyncMock(return_value=1)
    redis.client.exists = AsyncMock(return_value=False)
    redis.client.incr = AsyncMock(return_value=1)
    redis.client.expire = AsyncMock(return_value=True)

    return redis


@pytest.fixture
def mock_qdrant():
    """Mock Qdrant client for testing."""
    qdrant = AsyncMock()
    qdrant.client = AsyncMock()
    qdrant.initialize = AsyncMock()
    qdrant.shutdown = AsyncMock()

    # Search mock
    qdrant.client.search = AsyncMock(return_value=[])
    qdrant.client.upsert = AsyncMock()
    qdrant.client.delete = AsyncMock()

    return qdrant


# =============================================================================
# Session Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def test_session(mock_llm, mock_sandbox):
    """Create a test session with mocked dependencies.

    This fixture provides a complete test session that can be used
    for integration-style tests without external dependencies.
    """
    from app.domain.models.session import Session, SessionStatus

    session = Session(
        id="test-session-123",
        user_id="test-user-456",
        status=SessionStatus.ACTIVE,
        agent_id="test-agent-789",
    )

    # Attach mocks for easy access in tests
    session._mock_llm = mock_llm
    session._mock_sandbox = mock_sandbox

    yield session


@pytest.fixture
def mock_session_repository():
    """Mock session repository for testing."""
    repo = AsyncMock()

    repo.save = AsyncMock(return_value=True)
    repo.get = AsyncMock(return_value=None)
    repo.delete = AsyncMock(return_value=True)
    repo.list_by_user = AsyncMock(return_value=[])

    return repo


# =============================================================================
# Agent Fixtures
# =============================================================================


@pytest.fixture
def mock_agent_repository():
    """Mock agent repository for testing."""
    repo = AsyncMock()

    repo.save = AsyncMock(return_value=True)
    repo.get = AsyncMock(return_value=None)
    repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
    repo.save_memory = AsyncMock()

    return repo


@pytest.fixture
def mock_json_parser():
    """Mock JSON parser for testing."""
    parser = AsyncMock()

    async def parse(json_str):
        if isinstance(json_str, dict):
            return json_str
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return {}

    parser.parse = AsyncMock(side_effect=parse)
    return parser


# =============================================================================
# Tool Fixtures
# =============================================================================


@pytest.fixture
def mock_tool_result():
    """Factory for creating mock tool results."""
    from app.domain.models.tool_result import ToolResult

    def _create_result(
        success: bool = True,
        message: str = "Operation completed",
        data: Any | None = None,
    ) -> ToolResult:
        return ToolResult(
            success=success,
            message=message,
            data=data,
        )

    return _create_result


@pytest.fixture
def mock_file_tool(mock_tool_result):
    """Mock file tool for testing."""
    tool = AsyncMock()
    tool.name = "file"
    tool.get_tools = MagicMock(
        return_value=[
            {"function": {"name": "file_read"}},
            {"function": {"name": "file_write"}},
            {"function": {"name": "file_search"}},
        ]
    )
    tool.has_function = MagicMock(return_value=True)
    tool.invoke_function = AsyncMock(return_value=mock_tool_result(message="File operation successful"))
    return tool


@pytest.fixture
def mock_shell_tool(mock_tool_result):
    """Mock shell tool for testing."""
    tool = AsyncMock()
    tool.name = "shell"
    tool.get_tools = MagicMock(
        return_value=[
            {"function": {"name": "shell_execute"}},
        ]
    )
    tool.has_function = MagicMock(return_value=True)
    tool.invoke_function = AsyncMock(return_value=mock_tool_result(message="Command executed: exit code 0"))
    return tool


# =============================================================================
# Configuration Fixtures
# =============================================================================


@pytest.fixture
def mock_settings():
    """Mock application settings for testing."""
    settings = MagicMock()

    # Basic settings
    settings.environment = "test"
    settings.debug = True
    settings.is_development = True
    settings.is_production = False

    # LLM settings
    settings.llm_provider = "test"
    settings.model_name = "test-model"
    settings.api_key = "test-api-key"

    # Database settings
    settings.mongodb_uri = "mongodb://localhost:27017"
    settings.mongodb_database = "test_db"
    settings.redis_host = "localhost"
    settings.redis_port = 6379

    # Auth settings
    settings.auth_provider = "none"
    settings.jwt_secret_key = "test-secret-key"

    # Rate limits
    settings.rate_limit_enabled = False

    return settings


# =============================================================================
# Event Loop Configuration
# =============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Temporary File Fixtures
# =============================================================================


@pytest.fixture
def temp_directory():
    """Create a temporary directory for test files."""
    import shutil

    temp_dir = tempfile.mkdtemp(prefix="pythinker_test_")
    yield Path(temp_dir)

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_file(temp_directory):
    """Create a temporary file for testing."""
    file_path = temp_directory / "test_file.txt"
    file_path.write_text("Test content for testing purposes.")
    return file_path


# =============================================================================
# HTTP Mocking Fixtures
# =============================================================================


@pytest.fixture
def mock_httpx():
    """Mock httpx for external API testing."""
    with patch("httpx.AsyncClient") as mock_client:
        instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = instance

        # Default response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.text = '{"success": true}'

        instance.get.return_value = mock_response
        instance.post.return_value = mock_response
        instance.put.return_value = mock_response
        instance.delete.return_value = mock_response

        yield instance


# =============================================================================
# LLM Response Factories (Agent Testing)
# =============================================================================


@pytest.fixture
def mock_llm_plan_response():
    """Factory for creating mock planning responses.

    Returns a factory function that creates PlanResponse-like dicts.
    """

    def _create(
        steps: list[dict] | None = None,
        complexity: str = "medium",
        goal: str = "Test goal",
        title: str = "Test Plan",
    ) -> dict[str, Any]:
        if steps is None:
            steps = [{"step": 1, "description": "Default step"}]

        return {
            "title": title,
            "goal": goal,
            "language": "en",
            "message": "Planning complete",
            "steps": steps,
            "complexity": complexity,
            "estimated_iterations": len(steps),
        }

    return _create


@pytest.fixture
def mock_llm_execution_response():
    """Factory for creating mock execution responses.

    Returns a factory function that creates ExecutionResponse-like dicts.
    """

    def _create(
        tool_calls: list[dict] | None = None,
        final_answer: str | None = None,
        reasoning: str = "Test reasoning",
    ) -> dict[str, Any]:
        response = {
            "reasoning": reasoning,
            "tool_calls": tool_calls or [],
        }
        if final_answer:
            response["final_answer"] = final_answer
        return response

    return _create


@pytest.fixture
def mock_llm_reflection_response():
    """Factory for creating mock reflection responses.

    Returns a factory function that creates ReflectionResponse-like dicts.
    """

    def _create(
        decision: str = "continue",
        feedback: str = "",
        confidence: float = 0.85,
    ) -> dict[str, Any]:
        return {
            "decision": decision,  # continue, adjust, replan, escalate
            "feedback": feedback,
            "confidence": confidence,
            "reasoning": "Test reflection reasoning",
        }

    return _create


# =============================================================================
# LangGraph State Fixtures
# =============================================================================


@pytest.fixture
def initial_plan_act_state():
    """Base state for LangGraph workflow tests.

    Provides a minimal valid state for starting Plan-Act workflows.
    """
    return {
        "user_message": "test message",
        "plan": None,
        "current_step": 0,
        "iteration_count": 0,
        "verification_loops": 0,
        "error_count": 0,
        "pending_events": [],
        "recent_tools": [],
        "plan_created": False,
        "all_steps_done": False,
        "max_iterations": 400,
        "error": None,
        "recovery_attempts": 0,
    }


@pytest.fixture
def state_with_plan(initial_plan_act_state, mock_llm_plan_response):
    """State with an existing plan for mid-workflow tests."""
    from app.domain.models.plan import Plan, Step

    state = initial_plan_act_state.copy()

    # Create a proper Plan object
    plan = Plan(
        title="Test Plan",
        goal="Test goal",
        steps=[
            Step(id="1", description="Search for info"),
            Step(id="2", description="Analyze results"),
        ],
    )

    state["plan"] = plan
    state["plan_created"] = True
    return state


# =============================================================================
# Tool Mock Registry
# =============================================================================


@pytest.fixture
def mock_tool_registry():
    """Registry of mock tools with configurable responses and call tracking.

    Useful for testing tool execution, retry logic, and tool selection.
    """

    class MockToolRegistry:
        def __init__(self):
            self.tools: dict[str, dict[str, Any]] = {}
            self.call_history: list[dict[str, Any]] = []

        def register(
            self,
            name: str,
            response: Any = None,
            error: Exception | None = None,
        ) -> None:
            """Register a mock tool with optional response or error."""
            self.tools[name] = {"response": response or {"success": True}, "error": error}

        async def execute(self, name: str, args: dict) -> Any:
            """Execute a mock tool and record the call."""
            self.call_history.append({"tool": name, "args": args, "timestamp": None})

            tool = self.tools.get(name)
            if not tool:
                # Return default response for unregistered tools
                return {"success": True, "message": f"Mock response for {name}"}

            if tool.get("error"):
                raise tool["error"]

            return tool["response"]

        def get_call_count(self, name: str | None = None) -> int:
            """Get number of calls, optionally filtered by tool name."""
            if name:
                return sum(1 for c in self.call_history if c["tool"] == name)
            return len(self.call_history)

        def reset(self) -> None:
            """Reset call history for clean test isolation."""
            self.call_history = []

    return MockToolRegistry()


# =============================================================================
# Agent Instance Factories
# =============================================================================


@pytest.fixture
def mock_tools():
    """List of mock tools for agent initialization."""
    from unittest.mock import MagicMock

    mock_tool = MagicMock()
    mock_tool.name = "mock_tool"
    mock_tool.get_tools = MagicMock(
        return_value=[
            {"function": {"name": "web_search"}},
            {"function": {"name": "file_read"}},
            {"function": {"name": "file_write"}},
        ]
    )
    mock_tool.has_function = MagicMock(return_value=True)
    mock_tool.invoke_function = AsyncMock(return_value=MagicMock(success=True, message="Success"))

    return [mock_tool]


@pytest.fixture
def mock_message():
    """Factory for creating test Message objects."""
    from app.domain.models.message import Message

    def _create(
        message: str = "Test message",
        attachments: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> Message:
        return Message(
            message=message,
            attachments=attachments or [],
            skills=skills or [],
        )

    return _create


# =============================================================================
# Plan & Step Factories
# =============================================================================


@pytest.fixture
def plan_factory():
    """Factory for creating test Plan objects."""
    from app.domain.models.plan import ExecutionStatus, Plan, Step

    def _create(
        steps: list[dict] | None = None,
        title: str = "Test Plan",
        goal: str = "Test goal",
        status: ExecutionStatus = ExecutionStatus.PENDING,
    ) -> Plan:
        if steps is None:
            steps = [{"id": "1", "description": "Default step"}]

        plan_steps = []
        for i, step_data in enumerate(steps):
            step = Step(
                id=step_data.get("id", str(i + 1)),
                description=step_data.get("description", f"Step {i + 1}"),
                status=step_data.get("status", ExecutionStatus.PENDING),
            )
            plan_steps.append(step)

        return Plan(title=title, goal=goal, steps=plan_steps, status=status)

    return _create


@pytest.fixture
def step_factory():
    """Factory for creating test Step objects."""
    from app.domain.models.plan import ExecutionStatus, Step

    def _create(
        step_id: str = "1",
        description: str = "Test step",
        status: ExecutionStatus = ExecutionStatus.PENDING,
        result: str | None = None,
        error: str | None = None,
    ) -> Step:
        return Step(
            id=step_id,
            description=description,
            status=status,
            result=result,
            error=error,
            success=status == ExecutionStatus.COMPLETED,
        )

    return _create
