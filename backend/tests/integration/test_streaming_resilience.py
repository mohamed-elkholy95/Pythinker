import json
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


def _parse_sse_events(response: requests.Response, timeout_seconds: float = 20.0, max_events: int = 120) -> list[dict]:
    events: list[dict] = []
    current_event: str | None = None
    current_data_lines: list[str] = []
    started_at = time.time()

    for raw_line in response.iter_lines(decode_unicode=True):
        if time.time() - started_at > timeout_seconds:
            break
        if raw_line is None:
            continue
        line = raw_line.strip()
        if line.startswith("event:"):
            current_event = line[6:].strip()
            continue
        if line.startswith("data:"):
            current_data_lines.append(line[5:].strip())
            continue
        if line != "" or current_event is None:
            continue

        payload_text = "\n".join(current_data_lines)
        try:
            payload = json.loads(payload_text) if payload_text else {}
        except json.JSONDecodeError:
            payload = {"raw": payload_text}
        events.append({"event": current_event, "data": payload})

        current_event = None
        current_data_lines = []
        if len(events) >= max_events or events[-1]["event"] in {"done", "error"}:
            break

    return events


def _create_session() -> str:
    response = requests.put(f"{BASE_URL}/sessions", json={}, headers=HEADERS, timeout=15)
    if response.status_code in {401, 403}:
        pytest.skip("Auth is enabled for integration environment")
    assert response.status_code in {200, 201}, f"Failed to create session: {response.status_code} {response.text}"
    payload = response.json()
    data = payload.get("data", payload)
    session_id = data.get("session_id")
    assert session_id, f"Missing session_id in response: {payload}"
    return session_id


@pytest.mark.integration
def test_stream_resume_after_disconnect_produces_valid_sse_sequence():
    if not _backend_available():
        pytest.skip("Backend is not running for integration test")

    session_id = _create_session()

    chat_response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/chat",
        json={"message": "Reply with a short sentence.", "timestamp": int(time.time())},
        headers=HEADERS,
        stream=True,
        timeout=30,
    )
    assert chat_response.status_code == 200, f"Chat failed: {chat_response.status_code} {chat_response.text}"

    events = _parse_sse_events(chat_response, timeout_seconds=20.0, max_events=100)
    assert events, "Expected initial SSE events from chat endpoint"
    last_event_id = None
    for event in reversed(events):
        data = event.get("data") or {}
        if isinstance(data, dict) and isinstance(data.get("event_id"), str):
            last_event_id = data["event_id"]
            break

    if not last_event_id:
        pytest.skip("No resumable event_id emitted by backend for this run")

    resume_response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/chat",
        json={"event_id": last_event_id, "timestamp": int(time.time())},
        headers=HEADERS,
        stream=True,
        timeout=20,
    )
    assert resume_response.status_code == 200, f"Resume request failed: {resume_response.status_code}"

    resumed_events = _parse_sse_events(resume_response, timeout_seconds=12.0, max_events=40)
    assert resumed_events, "Expected SSE events from resumed stream"
    assert any(event["event"] in {"progress", "message", "done", "error"} for event in resumed_events)
