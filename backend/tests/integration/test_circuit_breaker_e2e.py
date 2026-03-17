import time

import pytest
import requests

BASE_URL = "http://localhost:8000/api/v1"
HEADERS = {"Content-Type": "application/json"}


def _backend_available() -> bool:
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=3)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _create_session() -> str:
    response = requests.put(f"{BASE_URL}/sessions", json={}, headers=HEADERS, timeout=15)
    if response.status_code in {401, 403}:
        pytest.skip("Auth is enabled for integration environment")
    assert response.status_code == 200, f"Failed to create session: {response.status_code} {response.text}"
    payload = response.json()
    data = payload.get("data", payload)
    session_id = data.get("session_id")
    assert session_id, f"Missing session_id in response: {payload}"
    return session_id


@pytest.mark.integration
def test_streaming_health_exposes_reconnect_and_latency_fields():
    if not _backend_available():
        pytest.skip("Backend is not running for integration test")

    session_id = _create_session()

    # Fire a resume-style call to generate reconnection telemetry.
    resume_response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/chat",
        json={"event_id": "synthetic-old-event", "timestamp": int(time.time())},
        headers=HEADERS,
        stream=True,
        timeout=15,
    )
    if resume_response.status_code in {401, 403}:
        pytest.skip("Auth is enabled for chat endpoint")
    assert resume_response.status_code == 200
    resume_response.close()

    health_response = requests.get(f"{BASE_URL}/health/streaming", timeout=10)
    if health_response.status_code in {401, 403}:
        pytest.skip("Auth is enabled for health endpoint")
    assert health_response.status_code == 200, health_response.text
    payload = health_response.json()

    assert payload["status"] in {"healthy", "degraded", "unhealthy"}
    assert isinstance(payload["health_score"], int)

    metrics = payload["metrics"]
    assert "active_connections" in metrics
    assert "latency_ms" in metrics
    assert "reconnections_last_5m" in metrics
    assert "reconnection_rate_per_min" in metrics
    assert "error_rate_by_category" in metrics
    assert "error_count_by_category" in metrics
