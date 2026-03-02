"""Chaos test suite for search resilience mechanisms.

Tests all resilience patterns without real API calls:
- 429 circuit breaker behavior (trips after 5 consecutive 429s, 45 s window)
- 429 vs 5xx window duration comparison (Fix 5 key invariant)
- Retry discipline (retries on 429, not on 400/401/403)
- Provider health ranking and demotion after 429 storm
- Rate governor in-memory fallback (Redis=None path)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.infrastructure.external.key_pool import CircuitBreaker, CircuitState, ErrorType
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.provider_health_ranker import ProviderHealthRanker
from app.infrastructure.external.search.rate_governor import SearchRateGovernor

# ---------------------------------------------------------------------------
# Minimal concrete SearchEngineBase for scenarios 3-5
# ---------------------------------------------------------------------------


class _ChaosEngine(SearchEngineBase):
    """Minimal concrete engine that lets tests inject response sequences."""

    provider_name = "chaos"
    engine_type = SearchEngineType.API

    def __init__(self) -> None:
        super().__init__()
        self.attempt_count: int = 0
        self._responses: list = []

    def queue_responses(self, responses: list) -> None:
        """Set the ordered sequence of status codes (or Exceptions) to return."""
        self._responses = list(responses)

    def _get_date_range_mapping(self) -> dict[str, str]:
        return {}

    def _build_request_params(self, query: str, date_range: str | None) -> dict:
        return {"q": query}

    async def _execute_request(self, client: httpx.AsyncClient, params: dict) -> httpx.Response:
        self.attempt_count += 1
        item = self._responses.pop(0) if self._responses else 200
        if isinstance(item, Exception):
            raise item
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = item
        if item >= 400:
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"HTTP {item}",
                request=MagicMock(),
                response=mock_resp,
            )
        else:
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {}
        return mock_resp

    def _parse_response(self, response: httpx.Response) -> tuple:
        return [], 0


# ---------------------------------------------------------------------------
# Scenario 1: 429 circuit trips after 5 consecutive 429s
# ---------------------------------------------------------------------------


def test_circuit_trips_after_five_consecutive_429s() -> None:
    """CircuitBreaker opens after 5 RATE_LIMITED failures with a 45 s window.

    Verifies Fix 5: consecutive 429 storm trips the circuit in the short
    45 s transient window (not the 300 s 5xx infrastructure window).
    """
    cb = CircuitBreaker(threshold=5, reset_timeout=300.0)

    # Circuit starts closed
    assert cb.state == CircuitState.CLOSED

    # Record 4 rate-limit failures — circuit must stay closed
    for i in range(4):
        cb.record_failure(ErrorType.RATE_LIMITED)
        assert cb.state == CircuitState.CLOSED, f"Circuit opened prematurely on failure {i + 1}"

    # 5th failure — circuit must open
    cb.record_failure(ErrorType.RATE_LIMITED)
    assert cb.state == CircuitState.OPEN, "Circuit must be OPEN after 5 consecutive 429s"
    assert cb.open_seconds == 45.0, (
        f"429 storm must use 45 s open window, got {cb.open_seconds}"
    )


# ---------------------------------------------------------------------------
# Scenario 2: 429 storm uses shorter window than 5xx storm
# ---------------------------------------------------------------------------


def test_429_storm_window_shorter_than_5xx_storm_window() -> None:
    """Fix 5 key invariant: 429 open window (45 s) < 5xx open window (300 s).

    Verifies that the two independent failure counters use different open
    durations so a transient rate-limit burst recovers faster than a 5xx
    infrastructure outage.
    """
    # --- 429 storm ---
    cb_429 = CircuitBreaker(threshold=5, reset_timeout=300.0)
    for _ in range(5):
        cb_429.record_failure(ErrorType.RATE_LIMITED)
    assert cb_429.state == CircuitState.OPEN
    open_seconds_429 = cb_429.open_seconds

    # --- 5xx storm ---
    cb_5xx = CircuitBreaker(threshold=5, reset_timeout=300.0)
    for _ in range(5):
        cb_5xx.record_failure(ErrorType.UPSTREAM_5XX)
    assert cb_5xx.state == CircuitState.OPEN
    open_seconds_5xx = cb_5xx.open_seconds

    assert open_seconds_429 < open_seconds_5xx, (
        f"429 storm window ({open_seconds_429} s) must be shorter than "
        f"5xx storm window ({open_seconds_5xx} s)"
    )
    assert open_seconds_429 == 45.0
    assert open_seconds_5xx == 300.0


# ---------------------------------------------------------------------------
# Scenario 3: SearchEngineBase retries on 429 (makes 2 HTTP calls)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_base_retries_once_on_429(mock_sleep: AsyncMock) -> None:
    """SearchEngineBase._do_search retries exactly once after a 429 response.

    Verifies Fix 3 / base retry discipline: the first 429 triggers a backoff
    sleep and a second attempt; the second attempt (200) succeeds.
    """
    engine = _ChaosEngine()
    engine.queue_responses([429, 200])

    result = await engine.search("resilience test")

    assert engine.attempt_count == 2, (
        f"Expected 2 HTTP attempts (1 retry after 429), got {engine.attempt_count}"
    )
    # The backoff sleep must have been called between the two attempts
    assert mock_sleep.called, "Expected asyncio.sleep() backoff call between retry attempts"
    assert result.success is True, f"Expected success on second attempt, got: {result.message}"


# ---------------------------------------------------------------------------
# Scenario 4: SearchEngineBase does NOT retry on 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_does_not_retry_on_400() -> None:
    """SearchEngineBase treats 400 as a permanent client error — no retry.

    400 is in PERMANENT_FAIL_CODES: the request is immediately failed without
    consuming the retry budget or rotating the API key.
    """
    engine = _ChaosEngine()
    engine.queue_responses([400])

    result = await engine.search("bad query")

    assert engine.attempt_count == 1, (
        f"Expected exactly 1 HTTP attempt for 400 (no retry), got {engine.attempt_count}"
    )
    assert result.success is False
    assert "400" in str(result.message) or "bad request" in str(result.message).lower()


# ---------------------------------------------------------------------------
# Scenario 5: SearchEngineBase does NOT retry on 401/403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_does_not_retry_on_401() -> None:
    """SearchEngineBase treats 401 as an auth error — fails without retry.

    401 is in ROTATE_NO_RETRY_CODES: this attempt fails immediately so the
    key pool above can rotate to the next key.
    """
    engine = _ChaosEngine()
    engine.queue_responses([401])

    result = await engine.search("auth fail test")

    assert engine.attempt_count == 1, (
        f"Expected 1 HTTP attempt for 401 (no retry), got {engine.attempt_count}"
    )
    assert result.success is False
    assert "auth" in str(result.message).lower() or "401" in str(result.message)


@pytest.mark.asyncio
async def test_base_does_not_retry_on_403() -> None:
    """SearchEngineBase treats 403 as a policy/auth error — fails without retry.

    403 is in ROTATE_NO_RETRY_CODES: this attempt fails immediately so the
    key pool above can rotate to the next key.
    """
    engine = _ChaosEngine()
    engine.queue_responses([403])

    result = await engine.search("forbidden test")

    assert engine.attempt_count == 1, (
        f"Expected 1 HTTP attempt for 403 (no retry), got {engine.attempt_count}"
    )
    assert result.success is False


# ---------------------------------------------------------------------------
# Scenario 6: ProviderHealthRanker demotes unhealthy provider
# ---------------------------------------------------------------------------


def test_health_ranker_demotes_429_heavy_provider() -> None:
    """ProviderHealthRanker sorts providers by health score (healthiest first).

    After 10 successes for 'brave' and 10 rate-limit responses for 'serper',
    brave should rank first because serper's 429 ratio is high (1.0 after
    pruning older events) driving its health score below brave's perfect 1.0.
    """
    ranker = ProviderHealthRanker()

    # 'brave' gets 10 clean successes — health score stays at 1.0
    for _ in range(10):
        ranker.record_success("brave")

    # 'serper' gets 10 rate-limit hits — health score drops substantially
    for _ in range(10):
        ranker.record_429("serper")

    brave_score = ranker.health_score("brave")
    serper_score = ranker.health_score("serper")

    assert brave_score > serper_score, (
        f"brave health score ({brave_score:.3f}) must exceed "
        f"serper score ({serper_score:.3f}) after serper 429 storm"
    )
    # Serper's score with 100 % 429s: 0.0 * 0.30 + 1.0 * 0.70 penalty = 0.30 health
    assert serper_score < 0.35, (
        f"serper score ({serper_score:.3f}) should be near 0.30 with 100% 429 rate"
    )

    ordered = ranker.rank(["serper", "brave"])
    assert ordered[0] == "brave", (
        f"Expected 'brave' first after ranking, got {ordered}"
    )
    assert ordered[1] == "serper"


# ---------------------------------------------------------------------------
# Scenario 7: SearchRateGovernor in-memory fallback (Redis=None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_governor_in_memory_fallback_limits_burst() -> None:
    """SearchRateGovernor falls back to in-memory token bucket when Redis is None.

    With burst=2.0 and rps=1.0 the bucket starts full at 2 tokens:
    - acquire() #1 → True  (1 token remaining)
    - acquire() #2 → True  (0 tokens remaining)
    - acquire() #3 → False (burst exhausted, no time has passed)

    Verifies that Redis=None does not crash and correctly throttles traffic.
    """
    governor = SearchRateGovernor(redis=None, provider="tavily", rps=1.0, burst=2.0)

    first = await governor.acquire()
    second = await governor.acquire()
    third = await governor.acquire()

    assert first is True, "First acquire should succeed (1 token consumed of burst=2)"
    assert second is True, "Second acquire should succeed (2 tokens consumed of burst=2)"
    assert third is False, (
        "Third acquire should fail — burst budget exhausted immediately "
        "(no time elapsed for token refill at rps=1.0)"
    )
