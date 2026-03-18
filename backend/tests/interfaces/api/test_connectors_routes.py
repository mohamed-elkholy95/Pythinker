"""Tests for connector API endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.exceptions.base import ConnectorNotFoundException
from app.domain.models.connector import (
    Connector,
    ConnectorAuthType,
    ConnectorStatus,
    ConnectorType,
    CustomApiConfig,
    CustomMcpConfig,
    UserConnector,
)
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user
from app.main import app

BASE_URL = "http://test"
CATALOG_URL = "/api/v1/connectors/catalog"
USER_URL = "/api/v1/connectors/user"


def _make_test_user() -> User:
    return User(id="test-user-id", email="test@example.com", fullname="Test User")


def _make_connector(
    connector_id: str = "conn-1",
    name: str = "Test Connector",
    connector_type: ConnectorType = ConnectorType.APP,
    **kwargs: object,
) -> Connector:
    return Connector(
        id=connector_id,
        name=name,
        description=kwargs.get("description", "A test connector"),
        connector_type=connector_type,
        icon=kwargs.get("icon", "Plug"),
        brand_color=kwargs.get("brand_color", "#6366f1"),
        category=kwargs.get("category", "general"),
        is_official=kwargs.get("is_official", True),
    )


def _make_user_connector(
    uc_id: str = "uc-1",
    user_id: str = "test-user-id",
    connector_type: ConnectorType = ConnectorType.APP,
    status: ConnectorStatus = ConnectorStatus.CONNECTED,
    enabled: bool = True,
    api_config: CustomApiConfig | None = None,
    mcp_config: CustomMcpConfig | None = None,
    **kwargs: object,
) -> UserConnector:
    return UserConnector(
        id=uc_id,
        user_id=user_id,
        connector_id=kwargs.get("connector_id", "conn-1"),
        connector_type=connector_type,
        name=kwargs.get("name", "My Connector"),
        description=kwargs.get("description", "User connector"),
        icon=kwargs.get("icon", "Plug"),
        status=status,
        enabled=enabled,
        api_config=api_config,
        mcp_config=mcp_config,
        last_connected_at=datetime.now(UTC),
    )


def _mock_service() -> MagicMock:
    """Create a mock ConnectorService with all async methods pre-configured."""
    svc = MagicMock()
    svc.get_available_connectors = AsyncMock(return_value=[])
    svc.get_connector_by_id = AsyncMock(return_value=None)
    svc.get_user_connectors = AsyncMock(return_value=[])
    svc.connect_app = AsyncMock()
    svc.create_custom_api = AsyncMock()
    svc.create_custom_mcp = AsyncMock()
    svc.update_custom_connector = AsyncMock(return_value=None)
    svc.delete_custom_connector = AsyncMock(return_value=False)
    svc.test_connection = AsyncMock(return_value={"ok": True, "message": "OK", "latency_ms": None})
    # The get_user_connector route accesses _user_connector_repo directly
    svc._user_connector_repo = MagicMock()
    svc._user_connector_repo.get_by_id = AsyncMock(return_value=None)
    return svc


@pytest.fixture()
def _override_deps():
    """Override auth dependency for connector tests."""
    user = _make_test_user()
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# GET /catalog — list catalog connectors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_catalog_returns_list():
    """Should return a list of catalog connectors."""
    connectors = [
        _make_connector("conn-1", "GitHub"),
        _make_connector("conn-2", "Slack"),
    ]
    svc = _mock_service()
    svc.get_available_connectors = AsyncMock(return_value=connectors)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(CATALOG_URL)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert len(data["connectors"]) == 2
    assert data["connectors"][0]["name"] == "GitHub"
    assert data["connectors"][1]["name"] == "Slack"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_catalog_empty():
    """Should return empty list when no connectors exist."""
    svc = _mock_service()

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(CATALOG_URL)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 0
    assert data["connectors"] == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_catalog_filters_by_type():
    """Should pass connector_type filter to the service."""
    svc = _mock_service()
    svc.get_available_connectors = AsyncMock(return_value=[])

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(CATALOG_URL, params={"type": "app"})

    assert response.status_code == 200
    svc.get_available_connectors.assert_awaited_once_with(connector_type=ConnectorType.APP, search=None)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_catalog_filters_by_search():
    """Should pass search query to the service."""
    svc = _mock_service()
    svc.get_available_connectors = AsyncMock(return_value=[])

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(CATALOG_URL, params={"search": "git"})

    assert response.status_code == 200
    svc.get_available_connectors.assert_awaited_once_with(connector_type=None, search="git")


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_catalog_invalid_type():
    """Should return 400 for an invalid connector type."""
    svc = _mock_service()

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(CATALOG_URL, params={"type": "invalid_type"})

    assert response.status_code == 400
    assert "Invalid connector type" in response.json()["msg"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_catalog_combined_filters():
    """Should pass both type and search filters to the service."""
    svc = _mock_service()
    svc.get_available_connectors = AsyncMock(return_value=[])

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(CATALOG_URL, params={"type": "custom_api", "search": "weather"})

    assert response.status_code == 200
    svc.get_available_connectors.assert_awaited_once_with(connector_type=ConnectorType.CUSTOM_API, search="weather")


# ---------------------------------------------------------------------------
# GET /catalog/{connector_id} — get specific catalog connector
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_catalog_connector_found():
    """Should return a single catalog connector."""
    connector = _make_connector("conn-42", "Jira", is_official=True)
    svc = _mock_service()
    svc.get_connector_by_id = AsyncMock(return_value=connector)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(f"{CATALOG_URL}/conn-42")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == "conn-42"
    assert data["name"] == "Jira"
    assert data["is_official"] is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_catalog_connector_not_found():
    """Should return 404 when connector does not exist."""
    svc = _mock_service()
    svc.get_connector_by_id = AsyncMock(return_value=None)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(f"{CATALOG_URL}/nonexistent")

    assert response.status_code == 404
    assert response.json()["msg"] == "Connector not found"


# ---------------------------------------------------------------------------
# GET /user — list user connectors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_user_connectors_returns_list_with_connected_count():
    """Should return user connectors with correct connected count."""
    user_connectors = [
        _make_user_connector("uc-1", status=ConnectorStatus.CONNECTED, enabled=True),
        _make_user_connector("uc-2", status=ConnectorStatus.CONNECTED, enabled=True),
        _make_user_connector("uc-3", status=ConnectorStatus.DISCONNECTED, enabled=False),
    ]
    svc = _mock_service()
    svc.get_user_connectors = AsyncMock(return_value=user_connectors)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(USER_URL)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 3
    assert data["connected_count"] == 2
    assert len(data["connectors"]) == 3


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_user_connectors_empty():
    """Should return empty list when user has no connectors."""
    svc = _mock_service()
    svc.get_user_connectors = AsyncMock(return_value=[])

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(USER_URL)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 0
    assert data["connected_count"] == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_user_connectors_disabled_not_counted():
    """Connected but disabled connectors should not be counted as connected."""
    user_connectors = [
        _make_user_connector("uc-1", status=ConnectorStatus.CONNECTED, enabled=False),
    ]
    svc = _mock_service()
    svc.get_user_connectors = AsyncMock(return_value=user_connectors)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(USER_URL)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["connected_count"] == 0


# ---------------------------------------------------------------------------
# GET /user/{user_connector_id} — get specific user connector
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_user_connector_found():
    """Should return a specific user connector."""
    uc = _make_user_connector("uc-99", user_id="test-user-id", name="My GitHub")
    svc = _mock_service()
    svc._user_connector_repo.get_by_id = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(f"{USER_URL}/uc-99")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == "uc-99"
    assert data["name"] == "My GitHub"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_user_connector_not_found():
    """Should return 404 when user connector does not exist."""
    svc = _mock_service()
    svc._user_connector_repo.get_by_id = AsyncMock(return_value=None)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(f"{USER_URL}/nonexistent")

    assert response.status_code == 404
    assert response.json()["msg"] == "Connector not found"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_get_user_connector_wrong_user():
    """Should return 404 when connector belongs to a different user."""
    uc = _make_user_connector("uc-99", user_id="other-user-id")
    svc = _mock_service()
    svc._user_connector_repo.get_by_id = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(f"{USER_URL}/uc-99")

    assert response.status_code == 404
    assert response.json()["msg"] == "Connector not found"


# ---------------------------------------------------------------------------
# POST /user/connect/{connector_id} — connect app connector
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_connect_app_success():
    """Should connect a pre-built app connector."""
    uc = _make_user_connector("uc-new", name="GitHub")
    svc = _mock_service()
    svc.connect_app = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(f"{USER_URL}/connect/conn-1")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == "uc-new"
    assert data["name"] == "GitHub"
    svc.connect_app.assert_awaited_once_with("test-user-id", "conn-1", credentials=None)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_connect_app_not_found():
    """Should return 404 when catalog connector does not exist."""
    svc = _mock_service()
    svc.connect_app = AsyncMock(side_effect=ConnectorNotFoundException("bad-id"))

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(f"{USER_URL}/connect/bad-id")

    assert response.status_code == 404
    assert "not found" in response.json()["msg"]


# ---------------------------------------------------------------------------
# POST /user/custom-api — create custom API connector
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_create_custom_api_success():
    """Should create a custom API connector with valid data."""
    uc = _make_user_connector(
        "uc-api-1",
        connector_type=ConnectorType.CUSTOM_API,
        name="Weather API",
        api_config=CustomApiConfig(
            base_url="https://api.weather.com",
            auth_type=ConnectorAuthType.BEARER,
            api_key="sk-test1234",
        ),
    )
    svc = _mock_service()
    svc.create_custom_api = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(
                f"{USER_URL}/custom-api",
                json={
                    "name": "Weather API",
                    "base_url": "https://api.weather.com",
                    "auth_type": "bearer",
                    "api_key": "sk-test1234",
                },
            )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "Weather API"
    assert data["connector_type"] == "custom_api"
    # API key should be masked in response
    assert data["api_config"]["api_key"] == "****1234"
    svc.create_custom_api.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_create_custom_api_with_headers():
    """Should accept custom headers."""
    uc = _make_user_connector(
        "uc-api-2",
        connector_type=ConnectorType.CUSTOM_API,
        name="Internal API",
        api_config=CustomApiConfig(
            base_url="https://internal.example.com",
            headers={"X-Custom": "value"},
        ),
    )
    svc = _mock_service()
    svc.create_custom_api = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(
                f"{USER_URL}/custom-api",
                json={
                    "name": "Internal API",
                    "base_url": "https://internal.example.com",
                    "headers": {"X-Custom": "value"},
                },
            )

    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_create_custom_api_invalid_url():
    """Should return 422 when URL does not start with http(s)."""
    svc = _mock_service()

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(
                f"{USER_URL}/custom-api",
                json={
                    "name": "Bad API",
                    "base_url": "ftp://not-http.com",
                },
            )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_create_custom_api_missing_name():
    """Should return 422 when name is missing."""
    svc = _mock_service()

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(
                f"{USER_URL}/custom-api",
                json={
                    "base_url": "https://api.example.com",
                },
            )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_create_custom_api_missing_url():
    """Should return 422 when base_url is missing."""
    svc = _mock_service()

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(
                f"{USER_URL}/custom-api",
                json={
                    "name": "No URL API",
                },
            )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /user/custom-mcp — create custom MCP connector
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_create_custom_mcp_stdio_success():
    """Should create a custom MCP connector with stdio transport."""
    uc = _make_user_connector(
        "uc-mcp-1",
        connector_type=ConnectorType.CUSTOM_MCP,
        name="My MCP Server",
        mcp_config=CustomMcpConfig(
            transport="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
        ),
    )
    svc = _mock_service()
    svc.create_custom_mcp = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(
                f"{USER_URL}/custom-mcp",
                json={
                    "name": "My MCP Server",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                },
            )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "My MCP Server"
    assert data["connector_type"] == "custom_mcp"
    assert data["mcp_config"]["transport"] == "stdio"
    svc.create_custom_mcp.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_create_custom_mcp_sse_success():
    """Should create a custom MCP connector with SSE transport."""
    uc = _make_user_connector(
        "uc-mcp-2",
        connector_type=ConnectorType.CUSTOM_MCP,
        name="Remote MCP",
        mcp_config=CustomMcpConfig(
            transport="sse",
            url="https://mcp.example.com/sse",
        ),
    )
    svc = _mock_service()
    svc.create_custom_mcp = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(
                f"{USER_URL}/custom-mcp",
                json={
                    "name": "Remote MCP",
                    "transport": "sse",
                    "url": "https://mcp.example.com/sse",
                },
            )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mcp_config"]["transport"] == "sse"
    assert data["mcp_config"]["url"] == "https://mcp.example.com/sse"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_create_custom_mcp_invalid_transport():
    """Should return 422 for invalid transport value."""
    svc = _mock_service()

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(
                f"{USER_URL}/custom-mcp",
                json={
                    "name": "Bad MCP",
                    "transport": "websocket",  # Invalid transport
                },
            )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_create_custom_mcp_missing_name():
    """Should return 422 when name is missing."""
    svc = _mock_service()

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(
                f"{USER_URL}/custom-mcp",
                json={
                    "transport": "stdio",
                    "command": "npx",
                },
            )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# PUT /user/{user_connector_id} — update user connector
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_update_user_connector_success():
    """Should update a user connector."""
    uc = _make_user_connector("uc-update", name="Updated Name")
    svc = _mock_service()
    svc.update_custom_connector = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.put(
                f"{USER_URL}/uc-update",
                json={"name": "Updated Name"},
            )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "Updated Name"
    svc.update_custom_connector.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_update_user_connector_enable_disable():
    """Should toggle the enabled field."""
    uc = _make_user_connector("uc-toggle", enabled=False)
    svc = _mock_service()
    svc.update_custom_connector = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.put(
                f"{USER_URL}/uc-toggle",
                json={"enabled": False},
            )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["enabled"] is False


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_update_user_connector_not_found():
    """Should return 404 when connector does not exist or belongs to another user."""
    svc = _mock_service()
    svc.update_custom_connector = AsyncMock(return_value=None)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.put(
                f"{USER_URL}/nonexistent",
                json={"name": "Doesn't matter"},
            )

    assert response.status_code == 404
    assert response.json()["msg"] == "Connector not found"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_update_user_connector_with_api_config():
    """Should update API config on an existing connector."""
    uc = _make_user_connector(
        "uc-api-upd",
        connector_type=ConnectorType.CUSTOM_API,
        api_config=CustomApiConfig(
            base_url="https://api.new.com",
            auth_type=ConnectorAuthType.API_KEY,
            api_key="new-key-5678",
        ),
    )
    svc = _mock_service()
    svc.update_custom_connector = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.put(
                f"{USER_URL}/uc-api-upd",
                json={
                    "api_config": {
                        "base_url": "https://api.new.com",
                        "auth_type": "api_key",
                        "api_key": "new-key-5678",
                    },
                },
            )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["api_config"]["base_url"] == "https://api.new.com"
    # API key should be masked
    assert data["api_config"]["api_key"] == "****5678"


# ---------------------------------------------------------------------------
# DELETE /user/{user_connector_id} — delete user connector
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_delete_user_connector_success():
    """Should delete a user connector."""
    svc = _mock_service()
    svc.delete_custom_connector = AsyncMock(return_value=True)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.delete(f"{USER_URL}/uc-delete-me")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["deleted"] is True
    svc.delete_custom_connector.assert_awaited_once_with("test-user-id", "uc-delete-me")


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_delete_user_connector_not_found():
    """Should return 404 when connector does not exist or belongs to another user."""
    svc = _mock_service()
    svc.delete_custom_connector = AsyncMock(return_value=False)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.delete(f"{USER_URL}/nonexistent")

    assert response.status_code == 404
    assert response.json()["msg"] == "Connector not found"


# ---------------------------------------------------------------------------
# POST /user/{user_connector_id}/test — test connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_test_connection_ok():
    """Should return successful test result."""
    svc = _mock_service()
    svc.test_connection = AsyncMock(return_value={"ok": True, "message": "HTTP 200", "latency_ms": 42.5})

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(f"{USER_URL}/uc-test/test")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ok"] is True
    assert data["message"] == "HTTP 200"
    assert data["latency_ms"] == 42.5
    svc.test_connection.assert_awaited_once_with("test-user-id", "uc-test")


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_test_connection_failure():
    """Should return failed test result."""
    svc = _mock_service()
    svc.test_connection = AsyncMock(return_value={"ok": False, "message": "Connection refused", "latency_ms": 1500.0})

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(f"{USER_URL}/uc-fail/test")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ok"] is False
    assert data["message"] == "Connection refused"
    assert data["latency_ms"] == 1500.0


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_test_connection_no_latency():
    """Should handle test result with no latency (e.g. stdio transport)."""
    svc = _mock_service()
    svc.test_connection = AsyncMock(
        return_value={"ok": True, "message": "stdio transport (not testable remotely)", "latency_ms": None}
    )

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(f"{USER_URL}/uc-stdio/test")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ok"] is True
    assert data["latency_ms"] is None


# ---------------------------------------------------------------------------
# Response format — API key masking and connector type serialization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_api_key_masked_in_user_connector_response():
    """Should mask the API key in user connector list responses."""
    uc = _make_user_connector(
        "uc-masked",
        connector_type=ConnectorType.CUSTOM_API,
        api_config=CustomApiConfig(
            base_url="https://api.example.com",
            auth_type=ConnectorAuthType.BEARER,
            api_key="super-secret-key-9999",
        ),
    )
    svc = _mock_service()
    svc.get_user_connectors = AsyncMock(return_value=[uc])

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(USER_URL)

    assert response.status_code == 200
    connector_data = response.json()["data"]["connectors"][0]
    assert connector_data["api_config"]["api_key"] == "****9999"
    # Original key should NOT appear in the response
    assert "super-secret-key-9999" not in response.text


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_short_api_key_fully_masked():
    """Should fully mask short API keys (4 chars or fewer)."""
    uc = _make_user_connector(
        "uc-short",
        connector_type=ConnectorType.CUSTOM_API,
        api_config=CustomApiConfig(
            base_url="https://api.example.com",
            api_key="abcd",
        ),
    )
    svc = _mock_service()
    svc._user_connector_repo.get_by_id = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(f"{USER_URL}/uc-short")

    assert response.status_code == 200
    assert response.json()["data"]["api_config"]["api_key"] == "****"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_connector_type_serialized_as_string():
    """Connector type enum should be serialized as its string value."""
    connectors = [
        _make_connector("c-1", "App C", connector_type=ConnectorType.APP),
        _make_connector("c-2", "API C", connector_type=ConnectorType.CUSTOM_API),
        _make_connector("c-3", "MCP C", connector_type=ConnectorType.CUSTOM_MCP),
    ]
    svc = _mock_service()
    svc.get_available_connectors = AsyncMock(return_value=connectors)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(CATALOG_URL)

    assert response.status_code == 200
    types = [c["connector_type"] for c in response.json()["data"]["connectors"]]
    assert types == ["app", "custom_api", "custom_mcp"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_mcp_config_in_user_connector_response():
    """Should include MCP config details in user connector response."""
    uc = _make_user_connector(
        "uc-mcp-resp",
        connector_type=ConnectorType.CUSTOM_MCP,
        mcp_config=CustomMcpConfig(
            transport="sse",
            url="https://mcp.example.com/sse",
            headers={"Authorization": "Bearer tok"},
            env={"API_TOKEN": "secret"},
        ),
    )
    svc = _mock_service()
    svc._user_connector_repo.get_by_id = AsyncMock(return_value=uc)

    with patch("app.interfaces.api.connectors_routes.get_connector_service", return_value=svc):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(f"{USER_URL}/uc-mcp-resp")

    assert response.status_code == 200
    mcp = response.json()["data"]["mcp_config"]
    assert mcp["transport"] == "sse"
    assert mcp["url"] == "https://mcp.example.com/sse"
    assert mcp["headers"] == {"Authorization": "Bearer tok"}
    assert mcp["env"] == {"API_TOKEN": "****cret"}  # env values are masked
