"""Application service for connector management."""

import logging
import uuid
from datetime import UTC, datetime

from app.domain.models.connector import (
    Connector,
    ConnectorStatus,
    ConnectorType,
    CustomApiConfig,
    CustomMcpConfig,
    UserConnector,
)
from app.domain.models.mcp_config import MCPServerConfig, MCPTransport
from app.domain.repositories.connector_repository import (
    ConnectorRepository,
    UserConnectorRepository,
)

logger = logging.getLogger(__name__)


class ConnectorService:
    """Service for managing connectors and user connector instances."""

    def __init__(
        self,
        connector_repo: ConnectorRepository | None = None,
        user_connector_repo: UserConnectorRepository | None = None,
    ) -> None:
        if connector_repo is None or user_connector_repo is None:
            from app.infrastructure.repositories.mongo_connector_repository import (
                MongoConnectorRepository,
                MongoUserConnectorRepository,
            )

            connector_repo = connector_repo or MongoConnectorRepository()
            user_connector_repo = user_connector_repo or MongoUserConnectorRepository()
        self._connector_repo = connector_repo
        self._user_connector_repo = user_connector_repo

    # --- Catalog ---

    async def get_available_connectors(
        self,
        connector_type: ConnectorType | None = None,
        search: str | None = None,
    ) -> list[Connector]:
        return await self._connector_repo.search(query=search, connector_type=connector_type)

    async def get_connector_by_id(self, connector_id: str) -> Connector | None:
        return await self._connector_repo.get_by_id(connector_id)

    # --- User CRUD ---

    async def get_user_connectors(self, user_id: str) -> list[UserConnector]:
        return await self._user_connector_repo.get_by_user(user_id)

    async def get_connected_connectors(self, user_id: str) -> list[UserConnector]:
        return await self._user_connector_repo.get_connected_by_user(user_id)

    async def connect_app(self, user_id: str, connector_id: str) -> UserConnector:
        """Connect a pre-built app connector for a user."""
        # Check for existing connection
        existing = await self._user_connector_repo.get_by_user_and_connector(user_id, connector_id)
        if existing:
            if existing.status == ConnectorStatus.CONNECTED:
                return existing
            # Re-connect
            existing.status = ConnectorStatus.CONNECTED
            existing.enabled = True
            existing.last_connected_at = datetime.now(UTC)
            existing.error_message = None
            existing.updated_at = datetime.now(UTC)
            updated = await self._user_connector_repo.update(existing.id, existing)
            return updated or existing

        # Look up catalog entry
        connector = await self._connector_repo.get_by_id(connector_id)
        if not connector:
            raise ValueError(f"Connector '{connector_id}' not found in catalog")

        user_connector = UserConnector(
            id=str(uuid.uuid4()),
            user_id=user_id,
            connector_id=connector_id,
            connector_type=ConnectorType.APP,
            name=connector.name,
            description=connector.description,
            icon=connector.icon,
            status=ConnectorStatus.CONNECTED,
            enabled=True,
            last_connected_at=datetime.now(UTC),
        )
        return await self._user_connector_repo.create(user_connector)

    async def disconnect(self, user_id: str, user_connector_id: str) -> bool:
        """Disconnect a user connector."""
        uc = await self._user_connector_repo.get_by_id(user_connector_id)
        if not uc or uc.user_id != user_id:
            return False
        uc.status = ConnectorStatus.DISCONNECTED
        uc.enabled = False
        uc.updated_at = datetime.now(UTC)
        await self._user_connector_repo.update(user_connector_id, uc)
        return True

    async def create_custom_api(
        self,
        user_id: str,
        name: str,
        config: CustomApiConfig,
        description: str = "",
    ) -> UserConnector:
        user_connector = UserConnector(
            id=str(uuid.uuid4()),
            user_id=user_id,
            connector_type=ConnectorType.CUSTOM_API,
            name=name,
            description=description,
            icon="Globe",
            status=ConnectorStatus.CONNECTED,
            enabled=True,
            api_config=config,
            last_connected_at=datetime.now(UTC),
        )
        return await self._user_connector_repo.create(user_connector)

    async def create_custom_mcp(
        self,
        user_id: str,
        name: str,
        config: CustomMcpConfig,
        description: str = "",
    ) -> UserConnector:
        user_connector = UserConnector(
            id=str(uuid.uuid4()),
            user_id=user_id,
            connector_type=ConnectorType.CUSTOM_MCP,
            name=name,
            description=description,
            icon="Server",
            status=ConnectorStatus.CONNECTED,
            enabled=True,
            mcp_config=config,
            last_connected_at=datetime.now(UTC),
        )
        return await self._user_connector_repo.create(user_connector)

    async def update_custom_connector(
        self,
        user_id: str,
        user_connector_id: str,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
        api_config: CustomApiConfig | None = None,
        mcp_config: CustomMcpConfig | None = None,
    ) -> UserConnector | None:
        uc = await self._user_connector_repo.get_by_id(user_connector_id)
        if not uc or uc.user_id != user_id:
            return None
        if name is not None:
            uc.name = name
        if description is not None:
            uc.description = description
        if enabled is not None:
            uc.enabled = enabled
        if api_config is not None:
            uc.api_config = api_config
        if mcp_config is not None:
            uc.mcp_config = mcp_config
        uc.updated_at = datetime.now(UTC)
        return await self._user_connector_repo.update(user_connector_id, uc)

    async def delete_custom_connector(self, user_id: str, user_connector_id: str) -> bool:
        uc = await self._user_connector_repo.get_by_id(user_connector_id)
        if not uc or uc.user_id != user_id:
            return False
        return await self._user_connector_repo.delete(user_connector_id)

    async def test_connection(self, user_id: str, user_connector_id: str) -> dict[str, bool | str | float | None]:
        """Test a user connector's connection. Returns {ok, message, latency_ms}."""
        uc = await self._user_connector_repo.get_by_id(user_connector_id)
        if not uc or uc.user_id != user_id:
            return {"ok": False, "message": "Connector not found", "latency_ms": None}

        start = datetime.now(UTC)
        try:
            if uc.connector_type == ConnectorType.CUSTOM_API and uc.api_config:
                from app.infrastructure.external.http_pool import HTTPClientPool

                client = await HTTPClientPool.get_client(
                    name="connector-test",
                    timeout=10.0,
                )
                headers = dict(uc.api_config.headers)
                if uc.api_config.auth_type.value == "bearer" and uc.api_config.api_key:
                    headers["Authorization"] = f"Bearer {uc.api_config.api_key}"
                elif uc.api_config.auth_type.value == "api_key" and uc.api_config.api_key:
                    headers["X-API-Key"] = uc.api_config.api_key
                resp = await client.get(uc.api_config.base_url, headers=headers)
                latency = (datetime.now(UTC) - start).total_seconds() * 1000
                if resp.status_code < 500:
                    uc.status = ConnectorStatus.CONNECTED
                    uc.error_message = None
                    await self._user_connector_repo.update(user_connector_id, uc)
                    return {"ok": True, "message": f"HTTP {resp.status_code}", "latency_ms": round(latency, 1)}
                uc.status = ConnectorStatus.ERROR
                uc.error_message = f"HTTP {resp.status_code}"
                await self._user_connector_repo.update(user_connector_id, uc)
                return {"ok": False, "message": f"HTTP {resp.status_code}", "latency_ms": round(latency, 1)}

            if uc.connector_type == ConnectorType.CUSTOM_MCP and uc.mcp_config:
                if uc.mcp_config.transport in ("sse", "streamable-http") and uc.mcp_config.url:
                    from app.infrastructure.external.http_pool import HTTPClientPool

                    client = await HTTPClientPool.get_client(
                        name="connector-mcp-test",
                        timeout=10.0,
                    )
                    resp = await client.get(uc.mcp_config.url, headers=dict(uc.mcp_config.headers))
                    latency = (datetime.now(UTC) - start).total_seconds() * 1000
                    uc.status = ConnectorStatus.CONNECTED
                    uc.error_message = None
                    await self._user_connector_repo.update(user_connector_id, uc)
                    return {
                        "ok": True,
                        "message": f"MCP server reachable (HTTP {resp.status_code})",
                        "latency_ms": round(latency, 1),
                    }
                # stdio transport — just mark as connected (can't easily test)
                uc.status = ConnectorStatus.CONNECTED
                uc.error_message = None
                await self._user_connector_repo.update(user_connector_id, uc)
                return {"ok": True, "message": "stdio transport (not testable remotely)", "latency_ms": None}

            # App connectors — just mark as connected
            uc.status = ConnectorStatus.CONNECTED
            uc.error_message = None
            await self._user_connector_repo.update(user_connector_id, uc)
            return {"ok": True, "message": "Connected", "latency_ms": None}

        except Exception as e:
            latency = (datetime.now(UTC) - start).total_seconds() * 1000
            uc.status = ConnectorStatus.ERROR
            uc.error_message = str(e)[:500]
            await self._user_connector_repo.update(user_connector_id, uc)
            return {"ok": False, "message": str(e)[:500], "latency_ms": round(latency, 1)}

    # --- MCP integration ---

    async def get_user_mcp_configs(self, user_id: str) -> list[tuple[str, MCPServerConfig]]:
        """Get MCPServerConfig objects for user's connected MCP connectors.

        Returns list of (server_name, MCPServerConfig) tuples.
        """
        mcp_connectors = await self._user_connector_repo.get_mcp_connectors_by_user(user_id)
        configs: list[tuple[str, MCPServerConfig]] = []

        for uc in mcp_connectors:
            if not uc.mcp_config:
                continue
            server_name = f"user-mcp-{uc.id[:8]}-{uc.name.lower().replace(' ', '-')[:20]}"
            transport_map = {
                "stdio": MCPTransport.STDIO,
                "sse": MCPTransport.SSE,
                "streamable-http": MCPTransport.STREAMABLE_HTTP,
            }
            transport = transport_map.get(uc.mcp_config.transport, MCPTransport.STDIO)

            server_config = MCPServerConfig(
                command=uc.mcp_config.command,
                args=uc.mcp_config.args or None,
                url=uc.mcp_config.url,
                headers=uc.mcp_config.headers or None,
                transport=transport,
                enabled=True,
                env=uc.mcp_config.env or None,
            )
            configs.append((server_name, server_config))

        return configs


# Global singleton
_connector_service: ConnectorService | None = None


def get_connector_service() -> ConnectorService:
    global _connector_service
    if _connector_service is None:
        _connector_service = ConnectorService()
    return _connector_service
