"""Tests for Token Budget Tracker.

Tests the TokenBudget class including:
- Token tracking and limits
- Reservation pattern
- Warning thresholds
- Session management
- Statistics and status
"""

from unittest.mock import MagicMock, patch

import pytest

from app.domain.services.concurrency.token_budget import (
    TokenBudget,
    TokenBudgetExceededError,
    TokenUsage,
    clear_all_budgets,
    get_all_budgets,
    get_token_budget,
    remove_token_budget,
)


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = MagicMock()
    settings.max_tokens_per_run = 10000
    return settings


@pytest.fixture(autouse=True)
def clear_budgets():
    """Clear budgets before and after each test."""
    clear_all_budgets()
    yield
    clear_all_budgets()


@pytest.fixture
def budget(mock_settings):
    """Create a token budget for testing."""
    with patch("app.core.config.get_settings", return_value=mock_settings):
        return TokenBudget("test-session", max_tokens=10000)


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_default_values(self):
        """Test default usage values."""
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.cached_tokens == 0
        assert usage.total_tokens == 0
        assert usage.llm_calls == 0

    def test_add_tokens(self):
        """Test adding token usage."""
        usage = TokenUsage()
        usage.add(prompt=100, completion=50, cached=20)

        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.cached_tokens == 20
        assert usage.total_tokens == 150  # prompt + completion
        assert usage.llm_calls == 1

    def test_add_multiple_times(self):
        """Test adding usage multiple times."""
        usage = TokenUsage()
        usage.add(prompt=100, completion=50)
        usage.add(prompt=200, completion=100)

        assert usage.prompt_tokens == 300
        assert usage.completion_tokens == 150
        assert usage.total_tokens == 450
        assert usage.llm_calls == 2


class TestTokenBudget:
    """Tests for TokenBudget class."""

    def test_initialization(self, budget):
        """Test budget initialization."""
        assert budget.session_id == "test-session"
        assert budget.max_tokens == 10000
        assert budget.used == 0
        assert budget.reserved == 0
        assert budget.remaining == 10000
        assert budget.utilization == 0.0

    def test_can_use_within_limit(self, budget):
        """Test can_use returns True when within budget."""
        assert budget.can_use(5000) is True
        assert budget.can_use(10000) is True

    def test_can_use_exceeds_limit(self, budget):
        """Test can_use returns False when exceeding budget."""
        assert budget.can_use(10001) is False
        assert budget.can_use(20000) is False

    def test_reserve_success(self, budget):
        """Test successful token reservation."""
        result = budget.reserve(1000)
        assert result is True
        assert budget.reserved == 1000
        assert budget.remaining == 9000

    def test_reserve_exceeds_budget_strict(self, budget):
        """Test reservation fails when exceeding budget in strict mode."""
        with pytest.raises(TokenBudgetExceededError) as exc_info:
            budget.reserve(15000, strict=True)

        assert exc_info.value.used == 0
        assert exc_info.value.limit == 10000
        assert exc_info.value.requested == 15000

    def test_reserve_exceeds_budget_non_strict(self, budget):
        """Test reservation returns False when non-strict."""
        result = budget.reserve(15000, strict=False)
        assert result is False
        assert budget.reserved == 0

    def test_release_reservation(self, budget):
        """Test releasing reservations."""
        budget.reserve(1000)
        budget.release_reservation(500)

        assert budget.reserved == 500

    def test_release_all_reservations(self, budget):
        """Test releasing all reservations."""
        budget.reserve(1000)
        budget.release_reservation()

        assert budget.reserved == 0

    def test_consume_tokens(self, budget):
        """Test consuming tokens."""
        budget.consume(prompt_tokens=500, completion_tokens=200, cached_tokens=100)

        assert budget.used == 700
        assert budget.remaining == 9300
        assert budget.usage.prompt_tokens == 500
        assert budget.usage.completion_tokens == 200
        assert budget.usage.cached_tokens == 100
        assert budget.usage.llm_calls == 1

    def test_consume_releases_reservation(self, budget):
        """Test that consume releases reservation by default."""
        budget.reserve(1000)
        budget.consume(prompt_tokens=300, completion_tokens=200)

        assert budget.reserved == 500  # 1000 - 500 (300 + 200)

    def test_consume_keeps_reservation(self, budget):
        """Test consume can keep reservation."""
        budget.reserve(1000)
        budget.consume(prompt_tokens=300, completion_tokens=200, release_reservation=False)

        assert budget.reserved == 1000

    def test_utilization_calculation(self, budget):
        """Test utilization is calculated correctly."""
        budget.consume(prompt_tokens=2500, completion_tokens=2500)
        assert budget.utilization == 0.5

        budget.reserve(2500)
        assert budget.utilization == 0.75

    def test_utilization_with_zero_max(self, mock_settings):
        """Test utilization when max_tokens is 0."""
        with patch("app.core.config.get_settings", return_value=mock_settings):
            budget = TokenBudget("test", max_tokens=0)
            assert budget.utilization == 0.0

    def test_reset(self, budget):
        """Test budget reset."""
        budget.consume(prompt_tokens=500, completion_tokens=500)
        budget.reserve(1000)

        budget.reset()

        assert budget.used == 0
        assert budget.reserved == 0
        assert budget.remaining == 10000

    def test_get_status(self, budget):
        """Test get_status returns correct information."""
        budget.consume(prompt_tokens=100, completion_tokens=50)
        budget.reserve(200)

        status = budget.get_status()

        assert status["session_id"] == "test-session"
        assert status["max_tokens"] == 10000
        assert status["used_tokens"] == 150
        assert status["reserved_tokens"] == 200  # Reservation is separate from consumption
        assert status["remaining_tokens"] == 9650  # 10000 - 150 - 200
        assert "usage" in status
        assert status["usage"]["llm_calls"] == 1

    def test_warning_threshold(self, mock_settings, caplog):
        """Test warning is logged when threshold exceeded."""
        with patch("app.core.config.get_settings", return_value=mock_settings):
            budget = TokenBudget("test-session", max_tokens=1000, warn_threshold=0.8)
            # Consume 80% of budget
            budget.consume(prompt_tokens=400, completion_tokens=400)

            # Check that warning was logged
            assert budget._warned is True


class TestSessionBudgetManagement:
    """Tests for session-based budget management functions."""

    def test_get_token_budget_creates_new(self, mock_settings):
        """Test get_token_budget creates new budget for unknown session."""
        with patch("app.core.config.get_settings", return_value=mock_settings):
            budget = get_token_budget("new-session")
            assert budget.session_id == "new-session"

    def test_get_token_budget_returns_existing(self, mock_settings):
        """Test get_token_budget returns existing budget."""
        with patch("app.core.config.get_settings", return_value=mock_settings):
            budget1 = get_token_budget("test-session")
            budget1.consume(prompt_tokens=100, completion_tokens=100)

            budget2 = get_token_budget("test-session")

            assert budget1 is budget2
            assert budget2.used == 200

    def test_remove_token_budget(self, mock_settings):
        """Test removing a token budget."""
        with patch("app.core.config.get_settings", return_value=mock_settings):
            get_token_budget("test-session")

            result = remove_token_budget("test-session")
            assert result is True

            # Budget should be removed
            result = remove_token_budget("test-session")
            assert result is False

    def test_get_all_budgets(self, mock_settings):
        """Test getting all active budgets."""
        with patch("app.core.config.get_settings", return_value=mock_settings):
            get_token_budget("session-1")
            get_token_budget("session-2")

            all_budgets = get_all_budgets()

            assert len(all_budgets) == 2
            assert "session-1" in all_budgets
            assert "session-2" in all_budgets

    def test_clear_all_budgets(self, mock_settings):
        """Test clearing all budgets."""
        with patch("app.core.config.get_settings", return_value=mock_settings):
            get_token_budget("session-1")
            get_token_budget("session-2")

            clear_all_budgets()

            assert len(get_all_budgets()) == 0


class TestTokenBudgetExceededError:
    """Tests for TokenBudgetExceededError exception."""

    def test_error_attributes(self):
        """Test error has correct attributes."""
        error = TokenBudgetExceededError(
            "Budget exceeded",
            used=5000,
            limit=10000,
            requested=6000,
        )

        assert error.used == 5000
        assert error.limit == 10000
        assert error.requested == 6000
        assert str(error) == "Budget exceeded"

    def test_error_default_requested(self):
        """Test error with default requested value."""
        error = TokenBudgetExceededError("Error", used=100, limit=100)
        assert error.requested == 0
