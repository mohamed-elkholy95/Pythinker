from types import SimpleNamespace
from unittest.mock import patch

from app.infrastructure.external.llm.openai_llm import OpenAILLM


def _make_llm(*, api_base: str, is_glm: bool = False, is_deepseek: bool = False) -> OpenAILLM:
    llm = OpenAILLM.__new__(OpenAILLM)
    llm._api_base = api_base
    llm._is_glm_api = is_glm
    llm._is_deepseek = is_deepseek
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
