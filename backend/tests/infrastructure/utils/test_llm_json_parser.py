"""Tests for LLMJsonParser warning behavior and fallback handling."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.utils.llm_json_parser import LLMJsonParser


@pytest.mark.asyncio
async def test_llm_json_parser_fallback_returns_structured_default_without_warning_storm(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.setattr(
        "app.infrastructure.utils.llm_json_parser.get_llm",
        lambda: SimpleNamespace(ask=None),
    )
    parser = LLMJsonParser()

    with caplog.at_level(logging.WARNING):
        result1 = await parser.parse("not-json-at-all", default_value={"ok": False})
        result2 = await parser.parse("not-json-at-all", default_value={"ok": False})

    assert result1 == {"ok": False}
    assert result2 == {"ok": False}
    # _try_direct_parse failures are logged at debug (not warning) to avoid
    # noise on common non-raw-JSON responses.  The "All parsing strategies failed"
    # warning uses _warn_once so it should fire exactly once despite two calls.
    all_failed_warning_count = sum(
        1
        for record in caplog.records
        if record.levelno == logging.WARNING and "All parsing strategies failed" in record.message
    )
    assert all_failed_warning_count == 1


@pytest.mark.asyncio
async def test_parse_tier_a_disables_llm_extract_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.infrastructure.utils.llm_json_parser.get_llm",
        lambda: SimpleNamespace(ask=AsyncMock()),
    )
    parser = LLMJsonParser()
    parser._try_llm_extract_and_fix = AsyncMock(return_value={"ok": True})  # type: ignore[method-assign]

    result = await parser.parse("invalid json", default_value={"fallback": True}, tier="A")

    assert result == {"fallback": True}
    parser._try_llm_extract_and_fix.assert_not_awaited()


@pytest.mark.asyncio
async def test_parse_tier_c_allows_llm_extract_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.infrastructure.utils.llm_json_parser.get_llm",
        lambda: SimpleNamespace(ask=AsyncMock()),
    )
    parser = LLMJsonParser()
    parser._try_llm_extract_and_fix = AsyncMock(return_value={"ok": True})  # type: ignore[method-assign]

    result = await parser.parse("invalid json", default_value={"fallback": True}, tier="C")

    assert result == {"ok": True}
    parser._try_llm_extract_and_fix.assert_awaited()
