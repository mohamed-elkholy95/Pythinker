"""Tests for search engine retry discipline — Fix 3.

Verifies that permanent errors (400/401/403) are not retried while
transient errors (429/502-504) are retried with backoff.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType


class _MinimalEngine(SearchEngineBase):
    """Minimal concrete engine for testing base class behavior."""

    provider_name = "TestProvider"
    engine_type = SearchEngineType.API

    def __init__(self) -> None:
        super().__init__()
        self.attempt_count = 0
        self._responses: list = []

    def set_responses(self, responses: list) -> None:
        self._responses = responses

    def _get_date_range_mapping(self) -> dict[str, str]:
        return {}

    def _build_request_params(self, query: str, date_range: str | None) -> dict:
        return {"q": query}

    async def _execute_request(self, client, params):
        self.attempt_count += 1
        resp = self._responses.pop(0) if self._responses else 200
        if isinstance(resp, Exception):
            raise resp
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = resp
        if resp >= 400:
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"HTTP {resp}", request=MagicMock(), response=mock_response
            )
        else:
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {}
        return mock_response

    def _parse_response(self, response):
        return [], 0


@pytest.mark.asyncio
async def test_401_does_not_retry():
    """401 auth error: fail immediately without retry."""
    engine = _MinimalEngine()
    engine.set_responses([401])
    result = await engine.search("test query")
    assert result.success is False
    assert engine.attempt_count == 1  # only 1 attempt


@pytest.mark.asyncio
async def test_403_does_not_retry():
    """403 policy error: fail immediately without retry."""
    engine = _MinimalEngine()
    engine.set_responses([403])
    result = await engine.search("test query")
    assert result.success is False
    assert engine.attempt_count == 1


@pytest.mark.asyncio
async def test_400_permanent_fail_no_retry():
    """400 client error: fail immediately, do not retry."""
    engine = _MinimalEngine()
    engine.set_responses([400])
    result = await engine.search("test query")
    assert result.success is False
    assert engine.attempt_count == 1


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_429_retries_once(mock_sleep):
    """429 rate limit: retry once with backoff."""
    engine = _MinimalEngine()
    engine.set_responses([429, 200])
    await engine.search("test query")
    assert engine.attempt_count == 2
    assert mock_sleep.called


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_502_retries_once(mock_sleep):
    """502 upstream error: retry once."""
    engine = _MinimalEngine()
    engine.set_responses([502, 200])
    await engine.search("test query")
    assert engine.attempt_count == 2


@pytest.mark.asyncio
async def test_rotate_no_retry_codes_set():
    """ROTATE_NO_RETRY_CODES must contain 401 and 403."""
    assert 401 in SearchEngineBase.ROTATE_NO_RETRY_CODES
    assert 403 in SearchEngineBase.ROTATE_NO_RETRY_CODES


@pytest.mark.asyncio
async def test_permanent_fail_codes_set():
    """PERMANENT_FAIL_CODES must contain 400."""
    assert 400 in SearchEngineBase.PERMANENT_FAIL_CODES


@pytest.mark.asyncio
async def test_retryable_status_codes_unchanged():
    """RETRYABLE_STATUS_CODES must include 429, 502, 503, 504."""
    assert {429, 502, 503, 504} <= SearchEngineBase.RETRYABLE_STATUS_CODES
