from types import SimpleNamespace
from unittest.mock import patch

from app.infrastructure.external.llm.openai_llm import OpenAILLM
from app.infrastructure.external.llm.provider_profile import get_provider_profile


def _make_llm(*, api_base: str, is_glm: bool = False, is_deepseek: bool = False) -> OpenAILLM:
    llm = OpenAILLM.__new__(OpenAILLM)
    llm._api_base = api_base
    llm._is_glm_api = is_glm
    llm._is_deepseek = is_deepseek
    llm._provider_profile = get_provider_profile(api_base, "")
    # Slow circuit-breaker instance attributes (set in __init__ by Task 5)
    llm._slow_tool_threshold = OpenAILLM._SLOW_TOOL_CALL_THRESHOLD_SECONDS
    llm._slow_tool_trip_count = OpenAILLM._SLOW_TOOL_CALL_TRIP_COUNT
    llm._slow_tool_cooldown = OpenAILLM._SLOW_TOOL_CALL_COOLDOWN_SECONDS
    llm._slow_breaker_max_tokens = OpenAILLM._SLOW_TOOL_BREAKER_DEGRADED_MAX_TOKENS
    llm._slow_breaker_timeout = OpenAILLM._SLOW_TOOL_BREAKER_DEGRADED_TIMEOUT_SECONDS
    return llm


def test_create_timeout_uses_streaming_read_timeout_cap() -> None:
    llm = _make_llm(api_base="https://api.z.ai/api/paas/v4", is_glm=True)

    with patch(
        "app.infrastructure.external.llm.openai_llm.get_settings",
        return_value=SimpleNamespace(llm_request_timeout=45.0),
    ):
        timeout = llm._create_timeout(is_streaming=True)

    assert timeout.connect == 10.0
    assert timeout.read == 30.0
    assert timeout.write == 30.0
    assert timeout.pool == 30.0


def test_create_timeout_caps_tool_read_timeout_by_global_budget() -> None:
    llm = _make_llm(api_base="https://api.openai.com/v1", is_glm=False)

    with patch(
        "app.infrastructure.external.llm.openai_llm.get_settings",
        return_value=SimpleNamespace(llm_request_timeout=45.0),
    ):
        timeout = llm._create_timeout(is_tool_call=True)

    assert timeout.connect == 5.0
    assert timeout.read == 45.0
    assert timeout.write == 30.0
    assert timeout.pool == 30.0


def test_slow_tool_call_breaker_trips_after_three_slow_calls() -> None:
    llm = _make_llm(api_base="https://api.z.ai/api/paas/v4", is_glm=True)
    llm._slow_tool_call_streak = 2
    llm._slow_tool_call_breaker_until = 0.0

    llm._record_tool_call_latency(
        duration_seconds=61.0,
        has_tools=True,
        fast_model="claude-haiku-4-5-20251001",
        now_monotonic=100.0,
    )

    assert llm._slow_tool_call_streak == 3
    assert llm._slow_tool_call_breaker_until == 400.0
    assert llm._is_slow_tool_breaker_active(now_monotonic=250.0) is True
    assert llm._is_slow_tool_breaker_active(now_monotonic=401.0) is False


def test_slow_tool_call_streak_resets_on_fast_response() -> None:
    llm = _make_llm(api_base="https://api.openai.com/v1")
    llm._slow_tool_call_streak = 2
    llm._slow_tool_call_breaker_until = 0.0

    llm._record_tool_call_latency(
        duration_seconds=5.0,
        has_tools=True,
        fast_model="claude-haiku-4-5-20251001",
        now_monotonic=100.0,
    )

    assert llm._slow_tool_call_streak == 0


def test_slow_tool_breaker_missing_fast_model_logs_once(caplog) -> None:
    llm = _make_llm(api_base="https://api.openai.com/v1")
    llm._model_name = "gpt-4.1"
    llm._slow_tool_call_streak = 2
    llm._slow_tool_call_breaker_until = 0.0
    llm._slow_breaker_missing_fast_model_warned = False

    llm._record_tool_call_latency(
        duration_seconds=61.0,
        has_tools=True,
        fast_model="",
        now_monotonic=100.0,
    )
    assert llm._is_slow_tool_breaker_active(now_monotonic=250.0) is True

    with (
        caplog.at_level("ERROR"),
        patch("app.infrastructure.external.llm.openai_llm.time.monotonic", return_value=250.0),
    ):
        resolved1 = llm._resolve_slow_tool_breaker_model(
            request_tools=[{"type": "function"}],
            model_override_for_attempt=None,
            timeout_fallback_fast_model="",
        )
        resolved2 = llm._resolve_slow_tool_breaker_model(
            request_tools=[{"type": "function"}],
            model_override_for_attempt=None,
            timeout_fallback_fast_model="",
        )

    assert resolved1 is None
    assert resolved2 is None
    assert llm._slow_breaker_missing_fast_model_warned is True
    assert sum("FAST_MODEL is not configured" in rec.message for rec in caplog.records) == 1


def test_slow_tool_breaker_resets_streak_after_cooldown_expiry() -> None:
    llm = _make_llm(api_base="https://api.openai.com/v1")
    llm._slow_tool_call_streak = 2
    llm._slow_tool_call_breaker_until = 100.0

    llm._record_tool_call_latency(
        duration_seconds=61.0,
        has_tools=True,
        fast_model="claude-haiku-4-5-20251001",
        now_monotonic=120.0,
    )

    # After cooldown expiry, streak should restart from 1, not re-trip immediately.
    assert llm._slow_tool_call_streak == 1
    assert llm._slow_tool_call_breaker_until == 100.0


def test_slow_tool_breaker_ignores_noop_fast_model_override() -> None:
    llm = _make_llm(api_base="https://api.openai.com/v1")
    llm._model_name = "glm-5"
    llm._slow_breaker_missing_fast_model_warned = False
    llm._slow_breaker_invalid_fast_model_warned = False
    llm._slow_tool_call_breaker_until = 500.0

    with patch("app.infrastructure.external.llm.openai_llm.time.monotonic", return_value=250.0):
        resolved = llm._resolve_slow_tool_breaker_model(
            request_tools=[{"type": "function"}],
            model_override_for_attempt=None,
            timeout_fallback_fast_model="claude-haiku-4-5-20251001",
        )

    assert resolved is None


def test_slow_tool_breaker_degraded_mode_enabled_when_fast_model_missing() -> None:
    llm = _make_llm(api_base="https://api.openai.com/v1")
    llm._slow_tool_call_breaker_until = 300.0

    degraded = llm._should_use_slow_tool_breaker_degraded_mode(
        request_tools=[{"type": "function"}],
        model_override_for_attempt=None,
        timeout_fallback_fast_model="",
        now_monotonic=150.0,
    )

    assert degraded is True


def test_slow_tool_breaker_degraded_mode_disabled_when_fast_model_available() -> None:
    llm = _make_llm(api_base="https://api.openai.com/v1")
    llm._slow_tool_call_breaker_until = 300.0

    degraded = llm._should_use_slow_tool_breaker_degraded_mode(
        request_tools=[{"type": "function"}],
        model_override_for_attempt=None,
        timeout_fallback_fast_model="claude-haiku-4-5-20251001",
        now_monotonic=150.0,
    )

    assert degraded is False


def test_slow_tool_breaker_degraded_timeout_cap() -> None:
    llm = _make_llm(api_base="https://api.openai.com/v1")

    capped_timeout = llm._cap_tool_timeout_for_slow_breaker(
        120.0,
        degraded_mode=True,
    )
    uncapped_timeout = llm._cap_tool_timeout_for_slow_breaker(
        120.0,
        degraded_mode=False,
    )

    assert capped_timeout == llm._SLOW_TOOL_BREAKER_DEGRADED_TIMEOUT_SECONDS
    assert uncapped_timeout == 120.0


def test_slow_tool_breaker_degraded_token_cap() -> None:
    llm = _make_llm(api_base="https://api.openai.com/v1")

    capped_tokens = llm._cap_tool_max_tokens_for_slow_breaker(
        4096,
        degraded_mode=True,
    )
    uncapped_tokens = llm._cap_tool_max_tokens_for_slow_breaker(
        4096,
        degraded_mode=False,
    )

    assert capped_tokens == llm._SLOW_TOOL_BREAKER_DEGRADED_MAX_TOKENS
    assert uncapped_tokens == 4096
