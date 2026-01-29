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
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

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
    session = requests.Session()
    # Don't set default Content-Type to allow multipart/form-data for file uploads
    return session


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
        "tool_calls": [{
            "id": "call_123",
            "function": {
                "name": "file_read",
                "arguments": json.dumps({"path": "/test/file.txt"})
            }
        }]
    }
    mock_llm.ask.return_value = tool_call_response
    return mock_llm


@pytest.fixture
def mock_llm_json_response(mock_llm):
    """Mock LLM that returns valid JSON responses."""
    json_response = {
        "role": "assistant",
        "content": json.dumps({
            "action": "complete",
            "result": "Task completed successfully",
            "confidence": 0.95
        })
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
    tool.get_tools = MagicMock(return_value=[
        {"function": {"name": "file_read"}},
        {"function": {"name": "file_write"}},
        {"function": {"name": "file_search"}},
    ])
    tool.has_function = MagicMock(return_value=True)
    tool.invoke_function = AsyncMock(
        return_value=mock_tool_result(message="File operation successful")
    )
    return tool


@pytest.fixture
def mock_shell_tool(mock_tool_result):
    """Mock shell tool for testing."""
    tool = AsyncMock()
    tool.name = "shell"
    tool.get_tools = MagicMock(return_value=[
        {"function": {"name": "shell_execute"}},
    ])
    tool.has_function = MagicMock(return_value=True)
    tool.invoke_function = AsyncMock(
        return_value=mock_tool_result(message="Command executed: exit code 0")
    )
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
