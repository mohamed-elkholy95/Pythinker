"""Seed data for pre-built connector catalog entries."""

import logging
from datetime import UTC, datetime

from app.domain.models.connector import Connector, ConnectorType

logger = logging.getLogger(__name__)

OFFICIAL_CONNECTORS: list[Connector] = [
    Connector(
        id="conn-browser",
        name="My Browser",
        description="Browse the web with a built-in browser in your sandbox",
        connector_type=ConnectorType.APP,
        icon="Globe",
        brand_color="#3b82f6",
        category="browsing",
        is_official=True,
    ),
    Connector(
        id="conn-gmail",
        name="Gmail",
        description="Read, send, and manage your Gmail messages",
        connector_type=ConnectorType.APP,
        icon="Mail",
        brand_color="#ea4335",
        category="communication",
        is_official=True,
    ),
    Connector(
        id="conn-google-calendar",
        name="Google Calendar",
        description="View and manage your Google Calendar events",
        connector_type=ConnectorType.APP,
        icon="Calendar",
        brand_color="#4285f4",
        category="productivity",
        is_official=True,
    ),
    Connector(
        id="conn-google-drive",
        name="Google Drive",
        description="Access and manage files in your Google Drive",
        connector_type=ConnectorType.APP,
        icon="HardDrive",
        brand_color="#34a853",
        category="storage",
        is_official=True,
    ),
    Connector(
        id="conn-outlook-mail",
        name="Outlook Mail",
        description="Read, send, and manage your Outlook email",
        connector_type=ConnectorType.APP,
        icon="Mail",
        brand_color="#0078d4",
        category="communication",
        is_official=True,
    ),
    Connector(
        id="conn-outlook-calendar",
        name="Outlook Calendar",
        description="View and manage your Outlook Calendar events",
        connector_type=ConnectorType.APP,
        icon="Calendar",
        brand_color="#0078d4",
        category="productivity",
        is_official=True,
    ),
    Connector(
        id="conn-github",
        name="GitHub",
        description="Access repositories, issues, and pull requests",
        connector_type=ConnectorType.APP,
        icon="Github",
        brand_color="#24292f",
        category="development",
        is_official=True,
    ),
    Connector(
        id="conn-slack",
        name="Slack",
        description="Send messages and interact with Slack workspaces",
        connector_type=ConnectorType.APP,
        icon="MessageSquare",
        brand_color="#4a154b",
        category="communication",
        is_official=True,
    ),
    Connector(
        id="conn-notion",
        name="Notion",
        description="Read and update your Notion pages and databases",
        connector_type=ConnectorType.APP,
        icon="BookOpen",
        brand_color="#000000",
        category="productivity",
        is_official=True,
    ),
    Connector(
        id="conn-zapier",
        name="Zapier",
        description="Trigger automations and connect to 5000+ apps",
        connector_type=ConnectorType.APP,
        icon="Zap",
        brand_color="#ff4a00",
        category="automation",
        is_official=True,
    ),
    Connector(
        id="conn-asana",
        name="Asana",
        description="Manage tasks and projects in Asana",
        connector_type=ConnectorType.APP,
        icon="CheckSquare",
        brand_color="#f06a6a",
        category="productivity",
        is_official=True,
    ),
    Connector(
        id="conn-monday",
        name="monday.com",
        description="Manage boards and items on monday.com",
        connector_type=ConnectorType.APP,
        icon="LayoutGrid",
        brand_color="#6161ff",
        category="productivity",
        is_official=True,
    ),
]


async def seed_connectors() -> int:
    """Seed official connectors into the database (upsert pattern).

    Returns:
        Number of connectors seeded/updated.
    """
    from app.infrastructure.repositories.mongo_connector_repository import (
        MongoConnectorRepository,
    )

    repo = MongoConnectorRepository()
    now = datetime.now(UTC)
    count = 0

    for connector in OFFICIAL_CONNECTORS:
        connector.updated_at = now
        await repo.upsert(connector)
        count += 1

    return count
