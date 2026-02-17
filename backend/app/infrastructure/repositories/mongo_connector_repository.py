"""MongoDB implementations of connector repositories."""

import re
from datetime import UTC, datetime

from app.domain.models.connector import (
    Connector,
    ConnectorStatus,
    ConnectorType,
    UserConnector,
)
from app.infrastructure.models.connector_documents import (
    ConnectorDocument,
    UserConnectorDocument,
)


class MongoConnectorRepository:
    """MongoDB implementation of ConnectorRepository."""

    async def get_all(self) -> list[Connector]:
        documents = await ConnectorDocument.find_all().to_list()
        return [doc.to_domain() for doc in documents]

    async def get_by_id(self, connector_id: str) -> Connector | None:
        document = await ConnectorDocument.find_one(ConnectorDocument.connector_id == connector_id)
        return document.to_domain() if document else None

    async def get_by_type(self, connector_type: ConnectorType) -> list[Connector]:
        documents = await ConnectorDocument.find(ConnectorDocument.connector_type == connector_type.value).to_list()
        return [doc.to_domain() for doc in documents]

    async def create(self, connector: Connector) -> Connector:
        document = ConnectorDocument.from_domain(connector)
        await document.save()
        return document.to_domain()

    async def upsert(self, connector: Connector) -> Connector:
        existing = await ConnectorDocument.find_one(ConnectorDocument.connector_id == connector.id)
        if existing:
            existing.update_from_domain(connector)
            existing.updated_at = datetime.now(UTC)
            await existing.save()
            return existing.to_domain()
        document = ConnectorDocument.from_domain(connector)
        await document.save()
        return document.to_domain()

    async def delete(self, connector_id: str) -> bool:
        document = await ConnectorDocument.find_one(ConnectorDocument.connector_id == connector_id)
        if not document:
            return False
        await document.delete()
        return True

    async def search(
        self,
        query: str | None = None,
        connector_type: ConnectorType | None = None,
    ) -> list[Connector]:
        filters: dict = {}
        if connector_type:
            filters["connector_type"] = connector_type.value
        if query:
            # Escape special regex characters to prevent regex injection
            escaped_query = re.escape(query)
            filters["$or"] = [
                {"name": {"$regex": escaped_query, "$options": "i"}},
                {"description": {"$regex": escaped_query, "$options": "i"}},
            ]
        documents = await ConnectorDocument.find(filters).to_list()
        return [doc.to_domain() for doc in documents]


class MongoUserConnectorRepository:
    """MongoDB implementation of UserConnectorRepository."""

    async def get_by_user(self, user_id: str) -> list[UserConnector]:
        documents = await UserConnectorDocument.find(UserConnectorDocument.user_id == user_id).to_list()
        return [doc.to_domain() for doc in documents]

    async def get_by_id(self, user_connector_id: str) -> UserConnector | None:
        document = await UserConnectorDocument.find_one(UserConnectorDocument.user_connector_id == user_connector_id)
        return document.to_domain() if document else None

    async def get_by_user_and_connector(self, user_id: str, connector_id: str) -> UserConnector | None:
        document = await UserConnectorDocument.find_one(
            UserConnectorDocument.user_id == user_id,
            UserConnectorDocument.connector_id == connector_id,
        )
        return document.to_domain() if document else None

    async def get_connected_by_user(self, user_id: str) -> list[UserConnector]:
        documents = await UserConnectorDocument.find(
            UserConnectorDocument.user_id == user_id,
            UserConnectorDocument.status == ConnectorStatus.CONNECTED.value,
            UserConnectorDocument.enabled == True,  # noqa: E712
        ).to_list()
        return [doc.to_domain() for doc in documents]

    async def get_mcp_connectors_by_user(self, user_id: str) -> list[UserConnector]:
        documents = await UserConnectorDocument.find(
            UserConnectorDocument.user_id == user_id,
            UserConnectorDocument.connector_type == ConnectorType.CUSTOM_MCP.value,
            UserConnectorDocument.status == ConnectorStatus.CONNECTED.value,
            UserConnectorDocument.enabled == True,  # noqa: E712
        ).to_list()
        return [doc.to_domain() for doc in documents]

    async def create(self, user_connector: UserConnector) -> UserConnector:
        document = UserConnectorDocument.from_domain(user_connector)
        await document.save()
        return document.to_domain()

    async def update(self, user_connector_id: str, user_connector: UserConnector) -> UserConnector | None:
        document = await UserConnectorDocument.find_one(UserConnectorDocument.user_connector_id == user_connector_id)
        if not document:
            return None
        document.update_from_domain(user_connector)
        document.updated_at = datetime.now(UTC)
        await document.save()
        return document.to_domain()

    async def delete(self, user_connector_id: str) -> bool:
        document = await UserConnectorDocument.find_one(UserConnectorDocument.user_connector_id == user_connector_id)
        if not document:
            return False
        await document.delete()
        return True

    async def delete_by_user_and_connector(self, user_id: str, connector_id: str) -> bool:
        document = await UserConnectorDocument.find_one(
            UserConnectorDocument.user_id == user_id,
            UserConnectorDocument.connector_id == connector_id,
        )
        if not document:
            return False
        await document.delete()
        return True
