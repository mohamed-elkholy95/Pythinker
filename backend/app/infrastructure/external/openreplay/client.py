"""
OpenReplay Client

Provides server-side integration with OpenReplay for:
- Sending custom events from backend (for events not visible in frontend)
- Fetching session metadata and replay URLs
- Managing session associations
"""

import logging
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)


class OpenReplayEvent(BaseModel):
    """Custom event to send to OpenReplay"""

    name: str
    payload: dict[str, Any] = {}
    timestamp: datetime | None = None


class OpenReplaySessionInfo(BaseModel):
    """Session information from OpenReplay"""

    session_id: str
    project_id: int
    user_id: str | None = None
    start_ts: int
    duration: int | None = None
    pages_count: int = 0
    events_count: int = 0
    errors_count: int = 0
    viewed: bool = False


class OpenReplayClient:
    """Client for interacting with OpenReplay API"""

    def __init__(
        self,
        api_url: str | None = None,
        ingest_url: str | None = None,
        project_key: str | None = None,
    ):
        self.api_url = api_url or getattr(settings, "openreplay_api_url", "http://localhost:8090")
        self.ingest_url = ingest_url or getattr(settings, "openreplay_ingest_url", "http://localhost:9001")
        self.project_key = project_key or getattr(settings, "openreplay_project_key", "pythinker-dev")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send_event(
        self,
        session_id: str,
        event: OpenReplayEvent,
    ) -> bool:
        """
        Send a custom event to OpenReplay for a specific session.

        This can be used to track backend events that are not visible in the frontend,
        such as internal agent decisions, database queries, or external API calls.

        Args:
            session_id: The OpenReplay session ID
            event: The event to send

        Returns:
            True if successful, False otherwise
        """
        try:
            client = await self._get_client()
            timestamp = event.timestamp or datetime.utcnow()

            payload = {
                "projectKey": self.project_key,
                "sessionID": session_id,
                "messages": [
                    {
                        "type": "custom",
                        "name": event.name,
                        "payload": event.payload,
                        "timestamp": int(timestamp.timestamp() * 1000),
                    }
                ],
            }

            response = await client.post(
                f"{self.ingest_url}/v1/web/not-started",
                json=payload,
            )
            response.raise_for_status()
            logger.debug(f"Sent event '{event.name}' to OpenReplay session {session_id}")
            return True

        except httpx.HTTPError as e:
            logger.warning(f"Failed to send event to OpenReplay: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending event to OpenReplay: {e}")
            return False

    async def get_session(self, session_id: str) -> OpenReplaySessionInfo | None:
        """
        Get session information from OpenReplay.

        Args:
            session_id: The OpenReplay session ID

        Returns:
            Session info or None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get(f"{self.api_url}/api/sessions/{session_id}")

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()

            return OpenReplaySessionInfo(
                session_id=data.get("sessionID", session_id),
                project_id=data.get("projectId", 1),
                user_id=data.get("userID"),
                start_ts=data.get("startTs", 0),
                duration=data.get("duration"),
                pages_count=data.get("pagesCount", 0),
                events_count=data.get("eventsCount", 0),
                errors_count=data.get("errorsCount", 0),
                viewed=data.get("viewed", False),
            )

        except httpx.HTTPError as e:
            logger.warning(f"Failed to get session from OpenReplay: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting session from OpenReplay: {e}")
            return None

    def get_session_url(self, session_id: str) -> str:
        """
        Get the direct URL to view a session in OpenReplay.

        Args:
            session_id: The OpenReplay session ID

        Returns:
            URL to the session replay
        """
        return f"{self.api_url}/session/{session_id}"

    def get_session_embed_url(self, session_id: str) -> str:
        """
        Get an embeddable URL for the session replay.

        Args:
            session_id: The OpenReplay session ID

        Returns:
            Embeddable URL for iframe integration
        """
        return f"{self.api_url}/session/{session_id}?embed=true"

    async def track_agent_event(
        self,
        session_id: str,
        event_type: str,
        event_data: dict[str, Any],
    ) -> bool:
        """
        Track an agent event in OpenReplay.

        Convenience method for tracking agent-specific events.

        Args:
            session_id: OpenReplay session ID
            event_type: Type of agent event (e.g., 'agent_tool_execute', 'agent_plan_create')
            event_data: Event payload

        Returns:
            True if successful
        """
        event = OpenReplayEvent(
            name=f"backend_{event_type}",
            payload={
                "source": "backend",
                "type": event_type,
                **event_data,
            },
        )
        return await self.send_event(session_id, event)

    async def link_pythinker_session(
        self,
        openreplay_session_id: str,
        pythinker_session_id: str,
    ) -> bool:
        """
        Link a Pythinker session to an OpenReplay session.

        This sends a custom event that associates the two sessions for
        easier correlation in the OpenReplay dashboard.

        Args:
            openreplay_session_id: OpenReplay session ID
            pythinker_session_id: Pythinker session ID

        Returns:
            True if successful
        """
        event = OpenReplayEvent(
            name="pythinker_session_linked",
            payload={
                "pythinker_session_id": pythinker_session_id,
                "linked_at": datetime.utcnow().isoformat(),
            },
        )
        return await self.send_event(openreplay_session_id, event)


# Singleton instance
_client: OpenReplayClient | None = None


def get_openreplay_client() -> OpenReplayClient:
    """Get the singleton OpenReplay client instance"""
    global _client
    if _client is None:
        _client = OpenReplayClient()
    return _client
