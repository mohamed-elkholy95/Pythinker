"""Beanie documents for connector persistence."""

from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.domain.models.connector import (
    Connector,
    ConnectorStatus,
    ConnectorType,
    CustomApiConfig,
    CustomMcpConfig,
    UserConnector,
)
from app.infrastructure.models.documents import BaseDocument


class ConnectorDocument(
    BaseDocument[Connector],
    id_field="connector_id",
    domain_model_class=Connector,
):
    """MongoDB document for the connector catalog."""

    connector_id: str
    name: str
    description: str = ""
    connector_type: str = ConnectorType.APP.value
    icon: str = ""
    brand_color: str = "#6366f1"
    category: str = "general"
    app_config: dict[str, str] | None = None
    api_config: dict[str, Any] | None = None
    mcp_config: dict[str, Any] | None = None
    is_official: bool = False
    version: str = "1.0.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "connectors"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("connector_id", ASCENDING)], unique=True),
            "connector_type",
            "is_official",
            IndexModel([("connector_type", ASCENDING), ("is_official", ASCENDING)]),
        ]

    def to_domain(self) -> Connector:
        data = self.model_dump(exclude={"id"})
        data["id"] = data.pop("connector_id")
        if data.get("connector_type"):
            data["connector_type"] = ConnectorType(data["connector_type"])
        if data.get("api_config"):
            data["api_config"] = CustomApiConfig.model_validate(data["api_config"])
        if data.get("mcp_config"):
            data["mcp_config"] = CustomMcpConfig.model_validate(data["mcp_config"])
        return Connector.model_validate(data)

    @classmethod
    def from_domain(cls, domain_obj: Connector) -> "ConnectorDocument":
        data = domain_obj.model_dump()
        data["connector_id"] = data.pop("id")
        if isinstance(data.get("connector_type"), ConnectorType):
            data["connector_type"] = data["connector_type"].value
        return cls.model_validate(data)


class UserConnectorDocument(
    BaseDocument[UserConnector],
    id_field="user_connector_id",
    domain_model_class=UserConnector,
):
    """MongoDB document for per-user connector instances."""

    user_connector_id: str
    user_id: str
    connector_id: str | None = None
    connector_type: str = ConnectorType.APP.value
    name: str = ""
    description: str = ""
    icon: str = ""
    status: str = ConnectorStatus.PENDING.value
    enabled: bool = True
    api_config: dict[str, Any] | None = None
    mcp_config: dict[str, Any] | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
    last_connected_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "user_connectors"
        indexes: ClassVar[list[Any]] = [
            IndexModel(
                [("user_id", ASCENDING), ("connector_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"connector_id": {"$exists": True, "$type": "string"}},
            ),
            IndexModel([("user_id", ASCENDING), ("status", ASCENDING)]),
            "user_id",
        ]

    def to_domain(self) -> UserConnector:
        data = self.model_dump(exclude={"id"})
        data["id"] = data.pop("user_connector_id")
        if data.get("connector_type"):
            data["connector_type"] = ConnectorType(data["connector_type"])
        if data.get("status"):
            data["status"] = ConnectorStatus(data["status"])
        if data.get("api_config"):
            data["api_config"] = CustomApiConfig.model_validate(data["api_config"])
        if data.get("mcp_config"):
            data["mcp_config"] = CustomMcpConfig.model_validate(data["mcp_config"])
        return UserConnector.model_validate(data)

    @classmethod
    def from_domain(cls, domain_obj: UserConnector) -> "UserConnectorDocument":
        data = domain_obj.model_dump()
        data["user_connector_id"] = data.pop("id")
        if isinstance(data.get("connector_type"), ConnectorType):
            data["connector_type"] = data["connector_type"].value
        if isinstance(data.get("status"), ConnectorStatus):
            data["status"] = data["status"].value
        if isinstance(data.get("api_config"), CustomApiConfig):
            data["api_config"] = data["api_config"].model_dump()
        if isinstance(data.get("mcp_config"), CustomMcpConfig):
            data["mcp_config"] = data["mcp_config"].model_dump()
        return cls.model_validate(data)
