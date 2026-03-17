from fastapi.testclient import TestClient

from app.main import app


def test_api_health_alias_matches_root_health() -> None:
    """Compatibility alias /api/health should mirror /health for old clients."""
    client = TestClient(app)

    root_response = client.get("/health")
    alias_response = client.get("/api/health")

    assert root_response.status_code == 200
    assert alias_response.status_code == 200
    assert alias_response.json() == root_response.json()
