"""Seed data for pre-built connector catalog entries."""

import logging
from datetime import UTC, datetime

from app.domain.models.connector import (
    Connector,
    ConnectorType,
    CredentialField,
    McpTemplate,
)

logger = logging.getLogger(__name__)

OFFICIAL_CONNECTORS: list[Connector] = [
    # --- Built-in ---
    Connector(
        id="conn-browser",
        name="My Browser",
        description="Browse the web with a built-in browser in your sandbox",
        connector_type=ConnectorType.APP,
        icon="Globe",
        brand_color="#3b82f6",
        category="browsing",
        availability="built_in",
        is_official=True,
    ),
    # --- Available (MCP-backed, token-based) ---
    Connector(
        id="conn-github",
        name="GitHub",
        description="Access repositories, issues, pull requests, and code",
        connector_type=ConnectorType.APP,
        icon="Github",
        brand_color="#24292f",
        category="development",
        availability="available",
        is_official=True,
        mcp_template=McpTemplate(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            transport="stdio",
            credential_fields=[
                CredentialField(
                    key="GITHUB_PERSONAL_ACCESS_TOKEN",
                    label="Personal Access Token",
                    description="Create a token at GitHub → Settings → Developer settings → Personal access tokens",
                    placeholder="ghp_xxxxxxxxxxxxxxxxxxxx",
                    required=True,
                    secret=True,
                ),
            ],
        ),
    ),
    Connector(
        id="conn-notion",
        name="Notion",
        description="Read and update your Notion pages and databases",
        connector_type=ConnectorType.APP,
        icon="BookOpen",
        brand_color="#000000",
        category="productivity",
        availability="available",
        is_official=True,
        mcp_template=McpTemplate(
            command="npx",
            args=["-y", "@notionhq/notion-mcp-server"],
            transport="stdio",
            credential_fields=[
                CredentialField(
                    key="NOTION_TOKEN",
                    label="Integration Token",
                    description="Create an integration at notion.so/my-integrations and copy the Internal Integration Secret",
                    placeholder="ntn_xxxxxxxxxxxxxxxxxxxx",
                    required=True,
                    secret=True,
                ),
            ],
        ),
    ),
    Connector(
        id="conn-slack",
        name="Slack",
        description="Read messages, channels, and interact with Slack workspaces",
        connector_type=ConnectorType.APP,
        icon="MessageSquare",
        brand_color="#4a154b",
        category="communication",
        availability="available",
        is_official=True,
        mcp_template=McpTemplate(
            command="npx",
            args=["-y", "slack-mcp-server@latest", "--transport", "stdio"],
            transport="stdio",
            credential_fields=[
                CredentialField(
                    key="SLACK_MCP_XOXC_TOKEN",
                    label="XOXC Token",
                    description="Browser session token: open Slack in browser → DevTools → Application → Cookies → find 'd' cookie value",
                    placeholder="xoxc-...",
                    required=True,
                    secret=True,
                ),
                CredentialField(
                    key="SLACK_MCP_XOXD_TOKEN",
                    label="XOXD Token",
                    description="Browser session token: open Slack in browser → DevTools → Application → Cookies → find 'd' cookie value starting with xoxd",
                    placeholder="xoxd-...",
                    required=True,
                    secret=True,
                ),
            ],
        ),
    ),
    Connector(
        id="conn-google-maps",
        name="Google Maps",
        description="Geocoding, directions, places search, and elevation data",
        connector_type=ConnectorType.APP,
        icon="MapPin",
        brand_color="#4285f4",
        category="productivity",
        availability="available",
        is_official=True,
        mcp_template=McpTemplate(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-google-maps"],
            transport="stdio",
            credential_fields=[
                CredentialField(
                    key="GOOGLE_MAPS_API_KEY",
                    label="Google Maps API Key",
                    description="Get an API key from Google Cloud Console → APIs & Services → Credentials",
                    placeholder="AIza...",
                    required=True,
                    secret=True,
                ),
            ],
        ),
    ),
    # --- Coming Soon (require OAuth) ---
    Connector(
        id="conn-gmail",
        name="Gmail",
        description="Read, send, and manage your Gmail messages",
        connector_type=ConnectorType.APP,
        icon="Mail",
        brand_color="#ea4335",
        category="communication",
        availability="coming_soon",
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
        availability="coming_soon",
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
        availability="coming_soon",
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
        availability="coming_soon",
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
        availability="coming_soon",
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
