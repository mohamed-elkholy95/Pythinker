"""Tests for ConnectorService.

Tests the application-layer connector management service covering:
- Catalog browsing (search, filter, get by ID)
- User connector CRUD (list, connect, disconnect, create, update, delete)
- Connection testing (not found, app connector)
- MCP config generation for agent integration
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.application.services.connector_service import ConnectorService
from app.domain.models.connector import (
    Connector,
    ConnectorAuthType,
    ConnectorStatus,
    ConnectorType,
    CustomApiConfig,
    CustomMcpConfig,
    UserConnector,
)
from app.domain.models.mcp_config import MCPServerConfig, MCPTransport

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_connector(
    connector_id: str = "cat-1",
    name: str = "Test App",
    connector_type: ConnectorType = ConnectorType.APP,
    description: str = "A test connector",
    icon: str = "Plug",
    is_official: bool = True,
) -> Connector:
    """Factory helper for Connector catalog entries."""
    return Connector(
        id=connector_id,
        name=name,
        connector_type=connector_type,
        description=description,
        icon=icon,
        is_official=is_official,
    )


def _make_user_connector(
    uc_id: str = "uc-1",
    user_id: str = "user-1",
    connector_id: str | None = "cat-1",
    connector_type: ConnectorType = ConnectorType.APP,
    name: str = "Test App",
    status: ConnectorStatus = ConnectorStatus.CONNECTED,
    enabled: bool = True,
    api_config: CustomApiConfig | None = None,
    mcp_config: CustomMcpConfig | None = None,
) -> UserConnector:
    """Factory helper for UserConnector instances."""
    return UserConnector(
        id=uc_id,
        user_id=user_id,
        connector_id=connector_id,
        connector_type=connector_type,
        name=name,
        status=status,
        enabled=enabled,
        api_config=api_config,
        mcp_config=mcp_config,
    )


@pytest.fixture
def connector_repo() -> AsyncMock:
    """Mock catalog connector repository."""
    repo = AsyncMock()
    repo.search = AsyncMock(return_value=[])
    repo.get_by_id = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def user_connector_repo() -> AsyncMock:
    """Mock user connector repository."""
    repo = AsyncMock()
    repo.get_by_user = AsyncMock(return_value=[])
    repo.get_connected_by_user = AsyncMock(return_value=[])
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_user_and_connector = AsyncMock(return_value=None)
    repo.create = AsyncMock(side_effect=lambda uc: uc)
    repo.update = AsyncMock(side_effect=lambda _id, uc: uc)
    repo.delete = AsyncMock(return_value=True)
    repo.get_mcp_connectors_by_user = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(connector_repo: AsyncMock, user_connector_repo: AsyncMock) -> ConnectorService:
    """ConnectorService wired with mock repositories."""
    return ConnectorService(
        connector_repo=connector_repo,
        user_connector_repo=user_connector_repo,
    )


# ===========================================================================
# 1. get_available_connectors
# ===========================================================================


class TestGetAvailableConnectors:
    """Tests for catalog browsing via get_available_connectors."""

    @pytest.mark.asyncio
    async def test_returns_all_when_no_filters(self, service: ConnectorService, connector_repo: AsyncMock) -> None:
        connectors = [_make_connector("c1", "Alpha"), _make_connector("c2", "Beta")]
        connector_repo.search.return_value = connectors

        result = await service.get_available_connectors()

        connector_repo.search.assert_awaited_once_with(query=None, connector_type=None)
        assert result == connectors
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filters_by_connector_type(self, service: ConnectorService, connector_repo: AsyncMock) -> None:
        app_connector = _make_connector("c1", "App Only", ConnectorType.APP)
        connector_repo.search.return_value = [app_connector]

        result = await service.get_available_connectors(connector_type=ConnectorType.APP)

        connector_repo.search.assert_awaited_once_with(query=None, connector_type=ConnectorType.APP)
        assert len(result) == 1
        assert result[0].connector_type == ConnectorType.APP

    @pytest.mark.asyncio
    async def test_filters_by_search_query(self, service: ConnectorService, connector_repo: AsyncMock) -> None:
        connector_repo.search.return_value = [_make_connector("c1", "GitHub")]

        result = await service.get_available_connectors(search="git")

        connector_repo.search.assert_awaited_once_with(query="git", connector_type=None)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_matches(
        self, service: ConnectorService, connector_repo: AsyncMock
    ) -> None:
        connector_repo.search.return_value = []

        result = await service.get_available_connectors(search="nonexistent")

        assert result == []


# ===========================================================================
# 2. get_connector_by_id
# ===========================================================================


class TestGetConnectorById:
    """Tests for get_connector_by_id."""

    @pytest.mark.asyncio
    async def test_returns_connector_when_found(self, service: ConnectorService, connector_repo: AsyncMock) -> None:
        connector = _make_connector("c1", "Found App")
        connector_repo.get_by_id.return_value = connector

        result = await service.get_connector_by_id("c1")

        connector_repo.get_by_id.assert_awaited_once_with("c1")
        assert result is not None
        assert result.id == "c1"
        assert result.name == "Found App"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, service: ConnectorService, connector_repo: AsyncMock) -> None:
        connector_repo.get_by_id.return_value = None

        result = await service.get_connector_by_id("nonexistent")

        assert result is None


# ===========================================================================
# 3. get_user_connectors
# ===========================================================================


class TestGetUserConnectors:
    """Tests for get_user_connectors."""

    @pytest.mark.asyncio
    async def test_returns_user_connectors(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        ucs = [
            _make_user_connector("uc-1", "user-1"),
            _make_user_connector("uc-2", "user-1", name="Second App"),
        ]
        user_connector_repo.get_by_user.return_value = ucs

        result = await service.get_user_connectors("user-1")

        user_connector_repo.get_by_user.assert_awaited_once_with("user-1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_for_user_with_no_connectors(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        user_connector_repo.get_by_user.return_value = []

        result = await service.get_user_connectors("user-no-connectors")

        assert result == []


# ===========================================================================
# 4. connect_app
# ===========================================================================


class TestConnectApp:
    """Tests for connect_app — new, reconnect, already-connected, not-found."""

    @pytest.mark.asyncio
    async def test_creates_new_connection(
        self,
        service: ConnectorService,
        connector_repo: AsyncMock,
        user_connector_repo: AsyncMock,
    ) -> None:
        catalog = _make_connector("cat-1", "Slack", icon="MessageSquare")
        connector_repo.get_by_id.return_value = catalog
        user_connector_repo.get_by_user_and_connector.return_value = None

        result = await service.connect_app("user-1", "cat-1")

        user_connector_repo.create.assert_awaited_once()
        assert result.user_id == "user-1"
        assert result.connector_id == "cat-1"
        assert result.connector_type == ConnectorType.APP
        assert result.name == "Slack"
        assert result.icon == "MessageSquare"
        assert result.status == ConnectorStatus.CONNECTED
        assert result.enabled is True
        assert result.last_connected_at is not None

    @pytest.mark.asyncio
    async def test_reconnects_disconnected_connector(
        self,
        service: ConnectorService,
        user_connector_repo: AsyncMock,
    ) -> None:
        existing = _make_user_connector("uc-1", "user-1", status=ConnectorStatus.DISCONNECTED, enabled=False)
        user_connector_repo.get_by_user_and_connector.return_value = existing

        result = await service.connect_app("user-1", "cat-1")

        user_connector_repo.update.assert_awaited_once()
        assert result.status == ConnectorStatus.CONNECTED
        assert result.enabled is True
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_returns_existing_if_already_connected(
        self,
        service: ConnectorService,
        user_connector_repo: AsyncMock,
    ) -> None:
        existing = _make_user_connector("uc-1", "user-1", status=ConnectorStatus.CONNECTED)
        user_connector_repo.get_by_user_and_connector.return_value = existing

        result = await service.connect_app("user-1", "cat-1")

        # Should NOT call update or create
        user_connector_repo.update.assert_not_awaited()
        user_connector_repo.create.assert_not_awaited()
        assert result is existing

    @pytest.mark.asyncio
    async def test_raises_when_catalog_connector_not_found(
        self,
        service: ConnectorService,
        connector_repo: AsyncMock,
        user_connector_repo: AsyncMock,
    ) -> None:
        user_connector_repo.get_by_user_and_connector.return_value = None
        connector_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found in catalog"):
            await service.connect_app("user-1", "missing-id")

    @pytest.mark.asyncio
    async def test_reconnect_clears_error_message(
        self,
        service: ConnectorService,
        user_connector_repo: AsyncMock,
    ) -> None:
        existing = _make_user_connector("uc-1", "user-1", status=ConnectorStatus.ERROR, enabled=False)
        existing.error_message = "Previous error"
        user_connector_repo.get_by_user_and_connector.return_value = existing

        result = await service.connect_app("user-1", "cat-1")

        assert result.error_message is None
        assert result.status == ConnectorStatus.CONNECTED


# ===========================================================================
# 5. disconnect
# ===========================================================================


class TestDisconnect:
    """Tests for disconnect."""

    @pytest.mark.asyncio
    async def test_disconnects_successfully(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        uc = _make_user_connector("uc-1", "user-1", status=ConnectorStatus.CONNECTED)
        user_connector_repo.get_by_id.return_value = uc

        result = await service.disconnect("user-1", "uc-1")

        assert result is True
        user_connector_repo.update.assert_awaited_once()
        # Verify the connector was mutated before update
        assert uc.status == ConnectorStatus.DISCONNECTED
        assert uc.enabled is False

    @pytest.mark.asyncio
    async def test_returns_false_for_wrong_user(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        uc = _make_user_connector("uc-1", "user-1")
        user_connector_repo.get_by_id.return_value = uc

        result = await service.disconnect("user-OTHER", "uc-1")

        assert result is False
        user_connector_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        user_connector_repo.get_by_id.return_value = None

        result = await service.disconnect("user-1", "nonexistent")

        assert result is False


# ===========================================================================
# 6. create_custom_api
# ===========================================================================


class TestCreateCustomApi:
    """Tests for create_custom_api."""

    @pytest.mark.asyncio
    async def test_creates_api_connector(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        api_config = CustomApiConfig(
            base_url="https://api.example.com",
            auth_type=ConnectorAuthType.BEARER,
            api_key="sk-secret",
            headers={"X-Custom": "value"},
        )

        result = await service.create_custom_api(
            user_id="user-1",
            name="My API",
            config=api_config,
            description="My custom API",
        )

        user_connector_repo.create.assert_awaited_once()
        assert result.user_id == "user-1"
        assert result.connector_type == ConnectorType.CUSTOM_API
        assert result.name == "My API"
        assert result.description == "My custom API"
        assert result.icon == "Globe"
        assert result.status == ConnectorStatus.CONNECTED
        assert result.enabled is True
        assert result.api_config is not None
        assert result.api_config.base_url == "https://api.example.com"
        assert result.api_config.auth_type == ConnectorAuthType.BEARER
        assert result.last_connected_at is not None

    @pytest.mark.asyncio
    async def test_creates_api_connector_with_default_description(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        api_config = CustomApiConfig(base_url="https://api.example.com")

        result = await service.create_custom_api(
            user_id="user-1",
            name="Minimal API",
            config=api_config,
        )

        assert result.description == ""


# ===========================================================================
# 7. create_custom_mcp
# ===========================================================================


class TestCreateCustomMcp:
    """Tests for create_custom_mcp."""

    @pytest.mark.asyncio
    async def test_creates_mcp_connector_stdio(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        mcp_config = CustomMcpConfig(
            transport="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        )

        result = await service.create_custom_mcp(
            user_id="user-1",
            name="Filesystem MCP",
            config=mcp_config,
            description="Local filesystem access",
        )

        user_connector_repo.create.assert_awaited_once()
        assert result.user_id == "user-1"
        assert result.connector_type == ConnectorType.CUSTOM_MCP
        assert result.name == "Filesystem MCP"
        assert result.icon == "Server"
        assert result.status == ConnectorStatus.CONNECTED
        assert result.enabled is True
        assert result.mcp_config is not None
        assert result.mcp_config.transport == "stdio"
        assert result.mcp_config.command == "npx"

    @pytest.mark.asyncio
    async def test_creates_mcp_connector_sse(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        mcp_config = CustomMcpConfig(
            transport="sse",
            url="https://mcp.example.com/sse",
            headers={"Authorization": "Bearer tok"},
        )

        result = await service.create_custom_mcp(
            user_id="user-1",
            name="Remote MCP",
            config=mcp_config,
        )

        assert result.mcp_config is not None
        assert result.mcp_config.transport == "sse"
        assert result.mcp_config.url == "https://mcp.example.com/sse"


# ===========================================================================
# 8. update_custom_connector
# ===========================================================================


class TestUpdateCustomConnector:
    """Tests for update_custom_connector."""

    @pytest.mark.asyncio
    async def test_updates_all_fields(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        existing = _make_user_connector(
            "uc-1",
            "user-1",
            connector_type=ConnectorType.CUSTOM_API,
            name="Old Name",
        )
        existing.api_config = CustomApiConfig(base_url="https://old.example.com")
        user_connector_repo.get_by_id.return_value = existing

        new_api_config = CustomApiConfig(base_url="https://new.example.com")
        result = await service.update_custom_connector(
            user_id="user-1",
            user_connector_id="uc-1",
            name="New Name",
            description="Updated desc",
            enabled=False,
            api_config=new_api_config,
        )

        assert result is not None
        assert result.name == "New Name"
        assert result.description == "Updated desc"
        assert result.enabled is False
        assert result.api_config is not None
        assert result.api_config.base_url == "https://new.example.com"
        user_connector_repo.update.assert_awaited_once_with("uc-1", existing)

    @pytest.mark.asyncio
    async def test_partial_update_name_only(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        existing = _make_user_connector("uc-1", "user-1", name="Original")
        user_connector_repo.get_by_id.return_value = existing

        result = await service.update_custom_connector(
            user_id="user-1",
            user_connector_id="uc-1",
            name="Renamed",
        )

        assert result is not None
        assert result.name == "Renamed"
        # Other fields unchanged
        assert result.enabled is True

    @pytest.mark.asyncio
    async def test_partial_update_enabled_only(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        existing = _make_user_connector("uc-1", "user-1", name="Keep Name")
        user_connector_repo.get_by_id.return_value = existing

        result = await service.update_custom_connector(
            user_id="user-1",
            user_connector_id="uc-1",
            enabled=False,
        )

        assert result is not None
        assert result.name == "Keep Name"
        assert result.enabled is False

    @pytest.mark.asyncio
    async def test_update_mcp_config(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        existing = _make_user_connector("uc-1", "user-1", connector_type=ConnectorType.CUSTOM_MCP)
        existing.mcp_config = CustomMcpConfig(transport="stdio", command="npx")
        user_connector_repo.get_by_id.return_value = existing

        new_mcp = CustomMcpConfig(transport="sse", url="https://mcp.example.com/sse")
        result = await service.update_custom_connector(
            user_id="user-1",
            user_connector_id="uc-1",
            mcp_config=new_mcp,
        )

        assert result is not None
        assert result.mcp_config is not None
        assert result.mcp_config.transport == "sse"

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_user(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        existing = _make_user_connector("uc-1", "user-1")
        user_connector_repo.get_by_id.return_value = existing

        result = await service.update_custom_connector(
            user_id="user-WRONG",
            user_connector_id="uc-1",
            name="Hijack",
        )

        assert result is None
        user_connector_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        user_connector_repo.get_by_id.return_value = None

        result = await service.update_custom_connector(
            user_id="user-1",
            user_connector_id="missing",
            name="Ghost",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_sets_updated_at_timestamp(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        old_time = datetime(2024, 1, 1, tzinfo=UTC)
        existing = _make_user_connector("uc-1", "user-1")
        existing.updated_at = old_time
        user_connector_repo.get_by_id.return_value = existing

        result = await service.update_custom_connector(
            user_id="user-1",
            user_connector_id="uc-1",
            name="Newer",
        )

        assert result is not None
        assert result.updated_at > old_time


# ===========================================================================
# 9. delete_custom_connector
# ===========================================================================


class TestDeleteCustomConnector:
    """Tests for delete_custom_connector."""

    @pytest.mark.asyncio
    async def test_deletes_successfully(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        uc = _make_user_connector("uc-1", "user-1", connector_type=ConnectorType.CUSTOM_API)
        user_connector_repo.get_by_id.return_value = uc
        user_connector_repo.delete.return_value = True

        result = await service.delete_custom_connector("user-1", "uc-1")

        assert result is True
        user_connector_repo.delete.assert_awaited_once_with("uc-1")

    @pytest.mark.asyncio
    async def test_returns_false_for_wrong_user(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        uc = _make_user_connector("uc-1", "user-1")
        user_connector_repo.get_by_id.return_value = uc

        result = await service.delete_custom_connector("user-OTHER", "uc-1")

        assert result is False
        user_connector_repo.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        user_connector_repo.get_by_id.return_value = None

        result = await service.delete_custom_connector("user-1", "ghost")

        assert result is False
        user_connector_repo.delete.assert_not_awaited()


# ===========================================================================
# 10. test_connection
# ===========================================================================


class TestTestConnection:
    """Tests for test_connection."""

    @pytest.mark.asyncio
    async def test_returns_not_found_when_connector_missing(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        user_connector_repo.get_by_id.return_value = None

        result = await service.test_connection("user-1", "missing")

        assert result["ok"] is False
        assert result["message"] == "Connector not found"
        assert result["latency_ms"] is None

    @pytest.mark.asyncio
    async def test_returns_not_found_for_wrong_user(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        uc = _make_user_connector("uc-1", "user-1")
        user_connector_repo.get_by_id.return_value = uc

        result = await service.test_connection("user-OTHER", "uc-1")

        assert result["ok"] is False
        assert result["message"] == "Connector not found"

    @pytest.mark.asyncio
    async def test_app_connector_marks_connected(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        uc = _make_user_connector("uc-1", "user-1", connector_type=ConnectorType.APP)
        user_connector_repo.get_by_id.return_value = uc

        result = await service.test_connection("user-1", "uc-1")

        assert result["ok"] is True
        assert result["message"] == "Connected"
        assert result["latency_ms"] is None
        user_connector_repo.update.assert_awaited_once()
        assert uc.status == ConnectorStatus.CONNECTED
        assert uc.error_message is None

    @pytest.mark.asyncio
    async def test_custom_api_success(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        api_config = CustomApiConfig(
            base_url="https://api.example.com",
            auth_type=ConnectorAuthType.BEARER,
            api_key="tok-123",
        )
        uc = _make_user_connector(
            "uc-1",
            "user-1",
            connector_type=ConnectorType.CUSTOM_API,
            api_config=api_config,
        )
        user_connector_repo.get_by_id.return_value = uc

        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_managed_client = AsyncMock()
        mock_managed_client.get.return_value = mock_response

        with patch(
            "app.infrastructure.external.http_pool.HTTPClientPool.get_client",
            return_value=mock_managed_client,
        ):
            result = await service.test_connection("user-1", "uc-1")

        assert result["ok"] is True
        assert "200" in result["message"]
        assert result["latency_ms"] is not None

    @pytest.mark.asyncio
    async def test_mcp_stdio_connector(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        mcp_config = CustomMcpConfig(
            transport="stdio",
            command="npx",
            args=["-y", "test-server"],
        )
        uc = _make_user_connector(
            "uc-1",
            "user-1",
            connector_type=ConnectorType.CUSTOM_MCP,
            mcp_config=mcp_config,
        )
        user_connector_repo.get_by_id.return_value = uc

        result = await service.test_connection("user-1", "uc-1")

        assert result["ok"] is True
        assert "stdio" in result["message"]
        assert result["latency_ms"] is None
        assert uc.status == ConnectorStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        api_config = CustomApiConfig(
            base_url="https://broken.example.com",
            auth_type=ConnectorAuthType.NONE,
        )
        uc = _make_user_connector(
            "uc-1",
            "user-1",
            connector_type=ConnectorType.CUSTOM_API,
            api_config=api_config,
        )
        user_connector_repo.get_by_id.return_value = uc

        with patch(
            "app.infrastructure.external.http_pool.HTTPClientPool.get_client",
            side_effect=ConnectionError("Connection refused"),
        ):
            result = await service.test_connection("user-1", "uc-1")

        assert result["ok"] is False
        assert result["latency_ms"] is not None
        assert uc.status == ConnectorStatus.ERROR


# ===========================================================================
# 11. get_user_mcp_configs
# ===========================================================================


class TestGetUserMcpConfigs:
    """Tests for get_user_mcp_configs — MCPServerConfig generation."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_mcp_connectors(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        user_connector_repo.get_mcp_connectors_by_user.return_value = []

        result = await service.get_user_mcp_configs("user-1")

        assert result == []

    @pytest.mark.asyncio
    async def test_generates_stdio_config(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        mcp_config = CustomMcpConfig(
            transport="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            env={"MY_VAR": "value"},
        )
        uc = _make_user_connector(
            "abcdef12-rest",
            "user-1",
            connector_type=ConnectorType.CUSTOM_MCP,
            name="FS Server",
            mcp_config=mcp_config,
        )
        user_connector_repo.get_mcp_connectors_by_user.return_value = [uc]

        result = await service.get_user_mcp_configs("user-1")

        assert len(result) == 1
        server_name, server_config = result[0]

        # Server name format: user-mcp-{id[:8]}-{name_slug[:20]}
        assert server_name.startswith("user-mcp-abcdef12")
        assert "fs-server" in server_name

        assert isinstance(server_config, MCPServerConfig)
        assert server_config.transport == MCPTransport.STDIO
        assert server_config.command == "npx"
        assert server_config.args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        assert server_config.enabled is True
        assert server_config.env == {"MY_VAR": "value"}

    @pytest.mark.asyncio
    async def test_generates_sse_config(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        mcp_config = CustomMcpConfig(
            transport="sse",
            url="https://mcp.example.com/sse",
            headers={"Authorization": "Bearer tok"},
        )
        uc = _make_user_connector(
            "12345678-rest",
            "user-1",
            connector_type=ConnectorType.CUSTOM_MCP,
            name="Remote SSE",
            mcp_config=mcp_config,
        )
        user_connector_repo.get_mcp_connectors_by_user.return_value = [uc]

        result = await service.get_user_mcp_configs("user-1")

        assert len(result) == 1
        _server_name, server_config = result[0]

        assert server_config.transport == MCPTransport.SSE
        assert server_config.url == "https://mcp.example.com/sse"
        assert server_config.headers == {"Authorization": "Bearer tok"}

    @pytest.mark.asyncio
    async def test_generates_streamable_http_config(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        mcp_config = CustomMcpConfig(
            transport="streamable-http",
            url="https://mcp.example.com/stream",
        )
        uc = _make_user_connector(
            "aabbccdd-rest",
            "user-1",
            connector_type=ConnectorType.CUSTOM_MCP,
            name="Streamable",
            mcp_config=mcp_config,
        )
        user_connector_repo.get_mcp_connectors_by_user.return_value = [uc]

        result = await service.get_user_mcp_configs("user-1")

        assert len(result) == 1
        _, server_config = result[0]
        assert server_config.transport == MCPTransport.STREAMABLE_HTTP

    @pytest.mark.asyncio
    async def test_skips_connectors_without_mcp_config(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        uc_no_config = _make_user_connector(
            "uc-no-cfg",
            "user-1",
            connector_type=ConnectorType.CUSTOM_MCP,
            name="No Config",
        )
        # mcp_config is None by default
        assert uc_no_config.mcp_config is None

        uc_with_config = _make_user_connector(
            "uc-cfg-ok",
            "user-1",
            connector_type=ConnectorType.CUSTOM_MCP,
            name="Has Config",
            mcp_config=CustomMcpConfig(transport="stdio", command="npx"),
        )
        user_connector_repo.get_mcp_connectors_by_user.return_value = [
            uc_no_config,
            uc_with_config,
        ]

        result = await service.get_user_mcp_configs("user-1")

        assert len(result) == 1
        server_name, _ = result[0]
        assert "has-config" in server_name

    @pytest.mark.asyncio
    async def test_multiple_mcp_connectors(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        configs = [
            _make_user_connector(
                f"uc-{i}xxxxx",
                "user-1",
                connector_type=ConnectorType.CUSTOM_MCP,
                name=f"Server {i}",
                mcp_config=CustomMcpConfig(transport="stdio", command="npx"),
            )
            for i in range(3)
        ]
        user_connector_repo.get_mcp_connectors_by_user.return_value = configs

        result = await service.get_user_mcp_configs("user-1")

        assert len(result) == 3
        names = [name for name, _ in result]
        assert len(set(names)) == 3  # All server names are unique

    @pytest.mark.asyncio
    async def test_empty_args_and_env_become_none(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        mcp_config = CustomMcpConfig(
            transport="stdio",
            command="npx",
            args=[],
            env={},
        )
        uc = _make_user_connector(
            "uc-empty0",
            "user-1",
            connector_type=ConnectorType.CUSTOM_MCP,
            name="Empty Lists",
            mcp_config=mcp_config,
        )
        user_connector_repo.get_mcp_connectors_by_user.return_value = [uc]

        result = await service.get_user_mcp_configs("user-1")

        assert len(result) == 1
        _, server_config = result[0]
        # Empty lists/dicts are falsy, so `or None` converts them to None
        assert server_config.args is None
        assert server_config.env is None

    @pytest.mark.asyncio
    async def test_unknown_transport_defaults_to_stdio(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        # Construct with a valid transport first, then override to test fallback
        mcp_config = CustomMcpConfig(transport="stdio", command="npx")
        # Manually override to simulate a bad stored value
        object.__setattr__(mcp_config, "transport", "unknown-transport")

        uc = _make_user_connector(
            "uc-unk00",
            "user-1",
            connector_type=ConnectorType.CUSTOM_MCP,
            name="Unknown Transport",
            mcp_config=mcp_config,
        )
        user_connector_repo.get_mcp_connectors_by_user.return_value = [uc]

        result = await service.get_user_mcp_configs("user-1")

        assert len(result) == 1
        _, server_config = result[0]
        assert server_config.transport == MCPTransport.STDIO


# ===========================================================================
# get_connected_connectors tests
# ===========================================================================


class TestGetConnectedConnectors:
    """Tests for get_connected_connectors."""

    @pytest.mark.asyncio
    async def test_returns_only_connected(self, service: ConnectorService, user_connector_repo: AsyncMock) -> None:
        connected = [_make_user_connector("uc-1", "user-1", status=ConnectorStatus.CONNECTED)]
        user_connector_repo.get_connected_by_user.return_value = connected

        result = await service.get_connected_connectors("user-1")

        user_connector_repo.get_connected_by_user.assert_awaited_once_with("user-1")
        assert len(result) == 1
        assert result[0].status == ConnectorStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_returns_empty_when_none_connected(
        self, service: ConnectorService, user_connector_repo: AsyncMock
    ) -> None:
        user_connector_repo.get_connected_by_user.return_value = []

        result = await service.get_connected_connectors("user-1")

        assert result == []
