from app.application.services.agent_service import AgentService
from app.core.workflow_timing_contract import (
    CHAT_EVENT_HARD_TIMEOUT_SECONDS,
    CHAT_EVENT_TIMEOUT_SECONDS,
    CHAT_WAIT_BEACON_INTERVAL_SECONDS,
    MAX_CREATE_SESSION_WAIT_SECONDS,
    SSE_HEARTBEAT_INTERVAL_SECONDS,
    SSE_RETRY_BASE_DELAY_MS,
    SSE_RETRY_JITTER_RATIO,
    SSE_RETRY_MAX_ATTEMPTS,
    SSE_RETRY_MAX_DELAY_MS,
)
from app.interfaces.api.session_routes import _build_sse_protocol_headers


def test_agent_service_defaults_match_workflow_timing_contract() -> None:
    assert AgentService.MAX_CREATE_SESSION_WAIT_SECONDS == MAX_CREATE_SESSION_WAIT_SECONDS
    assert AgentService.CHAT_EVENT_TIMEOUT_SECONDS == CHAT_EVENT_TIMEOUT_SECONDS
    assert AgentService.CHAT_EVENT_HARD_TIMEOUT_SECONDS == CHAT_EVENT_HARD_TIMEOUT_SECONDS
    assert AgentService.CHAT_WAIT_BEACON_INTERVAL_SECONDS == CHAT_WAIT_BEACON_INTERVAL_SECONDS


def test_sse_protocol_headers_expose_workflow_timing_contract() -> None:
    headers = _build_sse_protocol_headers()

    assert headers["X-Pythinker-SSE-Heartbeat-Interval-Seconds"] == str(SSE_HEARTBEAT_INTERVAL_SECONDS)
    assert headers["X-Pythinker-SSE-Retry-Max-Attempts"] == str(SSE_RETRY_MAX_ATTEMPTS)
    assert headers["X-Pythinker-SSE-Retry-Base-Delay-Ms"] == str(SSE_RETRY_BASE_DELAY_MS)
    assert headers["X-Pythinker-SSE-Retry-Max-Delay-Ms"] == str(SSE_RETRY_MAX_DELAY_MS)
    assert headers["X-Pythinker-SSE-Retry-Jitter-Ratio"] == str(SSE_RETRY_JITTER_RATIO)
