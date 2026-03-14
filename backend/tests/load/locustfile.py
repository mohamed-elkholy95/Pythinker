"""Locust load testing scripts for Pythinker API.

Covers the primary API hot paths:
- Session creation and listing
- Chat message submission (SSE endpoint)
- Event pagination
- File upload (presigned URL)
- Health check

Usage:
    pip install locust
    locust -f backend/tests/load/locustfile.py --host http://localhost:8000

Web UI: http://localhost:8089
"""

import os
import random
import string

from locust import HttpUser, between, task


def _random_string(length: int = 12) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=length))  # noqa: S311


class PythinkerUser(HttpUser):
    """Simulates a typical Pythinker user session."""

    wait_time = between(1, 5)
    _session_ids: list[str] = []  # noqa: RUF012
    _auth_token: str | None = None

    def on_start(self) -> None:
        """Authenticate and create an initial session."""
        # Try local auth (dev mode)
        password = os.getenv("PYTHINKER_PASSWORD", os.getenv("LOCAL_AUTH_PASSWORD", "change-me-local-password"))
        resp = self.client.post(
            "/api/v1/auth/local",
            json={"password": password},
            name="/api/v1/auth/local",
        )
        if resp.status_code == 200:
            data = resp.json()
            self._auth_token = data.get("access_token")
            self.client.headers["Authorization"] = f"Bearer {self._auth_token}"

    @task(5)
    def health_check(self) -> None:
        """High-frequency health check (simulates load balancer probes)."""
        self.client.get("/api/v1/health", name="/api/v1/health")

    @task(3)
    def create_session(self) -> None:
        """Create a new chat session."""
        resp = self.client.post(
            "/api/v1/sessions",
            json={
                "title": f"Load test session {_random_string()}",
                "agent_mode": "plan_act",
            },
            name="/api/v1/sessions [create]",
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            session_id = data.get("session_id") or data.get("id")
            if session_id:
                self._session_ids.append(session_id)
                # Keep list bounded
                if len(self._session_ids) > 50:
                    self._session_ids = self._session_ids[-50:]

    @task(2)
    def list_sessions(self) -> None:
        """List user sessions."""
        self.client.get(
            "/api/v1/sessions",
            params={"limit": 20, "offset": 0},
            name="/api/v1/sessions [list]",
        )

    @task(4)
    def send_chat_message(self) -> None:
        """Send a chat message to a session (SSE endpoint)."""
        if not self._session_ids:
            return
        session_id = random.choice(self._session_ids)  # noqa: S311
        # Use non-streaming endpoint if available, or just POST the message
        self.client.post(
            f"/api/v1/sessions/{session_id}/chat",
            json={"message": f"Hello from load test {_random_string(6)}"},
            name="/api/v1/sessions/:id/chat",
            # SSE streams would hang; just check that the endpoint accepts the request
            timeout=10,
        )

    @task(3)
    def get_session_events(self) -> None:
        """Paginate through session events."""
        if not self._session_ids:
            return
        session_id = random.choice(self._session_ids)  # noqa: S311
        self.client.get(
            f"/api/v1/sessions/{session_id}/events",
            params={"offset": 0, "limit": 50},
            name="/api/v1/sessions/:id/events",
        )

    @task(1)
    def get_session_detail(self) -> None:
        """Get full session details."""
        if not self._session_ids:
            return
        session_id = random.choice(self._session_ids)  # noqa: S311
        self.client.get(
            f"/api/v1/sessions/{session_id}",
            name="/api/v1/sessions/:id",
        )

    @task(1)
    def generate_upload_url(self) -> None:
        """Request a presigned upload URL."""
        if not self._session_ids:
            return
        random.choice(self._session_ids)  # noqa: S311
        self.client.post(
            "/api/v1/files/upload-url",
            json={
                "filename": f"test_{_random_string(8)}.txt",
                "content_type": "text/plain",
            },
            name="/api/v1/files/upload-url",
        )


class HealthCheckUser(HttpUser):
    """Lightweight user that only hits health endpoints (simulates monitoring)."""

    wait_time = between(5, 15)

    @task
    def health(self) -> None:
        self.client.get("/api/v1/health", name="/api/v1/health [monitor]")
