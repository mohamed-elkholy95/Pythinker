from fastapi.routing import APIRoute

from app.interfaces.schemas.session import GetSessionResponse, ListSessionItem, SharedSessionResponse
from app.main import app


def test_openreplay_route_removed() -> None:
    session_route_paths = [
        route.path for route in app.routes if isinstance(route, APIRoute) and route.path.startswith("/api/v1/sessions")
    ]

    assert not any(path.endswith("/openreplay") for path in session_route_paths)


def test_openreplay_fields_removed_from_session_schemas() -> None:
    assert "openreplay_session_id" not in GetSessionResponse.model_fields
    assert "openreplay_session_url" not in GetSessionResponse.model_fields

    assert "openreplay_session_id" not in ListSessionItem.model_fields
    assert "openreplay_session_url" not in ListSessionItem.model_fields

    assert "openreplay_session_id" not in SharedSessionResponse.model_fields
    assert "openreplay_session_url" not in SharedSessionResponse.model_fields
