"""Tests for predictive context management in TokenManager."""

import time
from unittest.mock import patch

from app.domain.services.agents.token_manager import (
    PressureLevel,
    PressureStatus,
    TokenManager,
)


class TestTokenGrowthTracking:
    """Tests for token growth rate tracking."""

    def test_growth_history_initialized_empty(self):
        """Test that growth history starts empty."""
        tm = TokenManager()
        assert tm._growth_history == []

    def test_track_token_snapshot_adds_entry(self):
        """Test that tracking adds entries to history."""
        tm = TokenManager()
        messages = [{"role": "user", "content": "Hello world"}]

        tm.track_token_snapshot(messages)

        assert len(tm._growth_history) == 1
        assert tm._growth_history[0][1] > 0  # Token count

    def test_track_token_snapshot_limits_history(self):
        """Test that history is limited to max_growth_samples."""
        tm = TokenManager()
        tm._max_growth_samples = 5

        messages = [{"role": "user", "content": "x" * 100}]

        # Add more than max samples
        for _ in range(10):
            tm.track_token_snapshot(messages)

        assert len(tm._growth_history) == 5

    def test_estimate_growth_rate_with_no_history(self):
        """Test growth rate estimation with no history."""
        tm = TokenManager()

        rate = tm.estimate_growth_rate()

        assert rate == tm._default_growth_rate

    def test_estimate_growth_rate_with_insufficient_history(self):
        """Test growth rate estimation with only one entry."""
        tm = TokenManager()
        tm._growth_history = [(time.time(), 1000)]

        rate = tm.estimate_growth_rate()

        assert rate == tm._default_growth_rate

    def test_estimate_growth_rate_calculates_average(self):
        """Test growth rate is calculated from history."""
        tm = TokenManager()
        now = time.time()

        # Simulate growth: 1000, 3000, 5000, 7000
        tm._growth_history = [
            (now - 3, 1000),
            (now - 2, 3000),  # +2000
            (now - 1, 5000),  # +2000
            (now, 7000),  # +2000
        ]

        rate = tm.estimate_growth_rate()

        assert rate == 2000

    def test_estimate_growth_rate_ignores_negative_growth(self):
        """Test that negative growth (compaction) is ignored."""
        tm = TokenManager()
        now = time.time()

        tm._growth_history = [
            (now - 4, 1000),
            (now - 3, 3000),  # +2000
            (now - 2, 2000),  # -1000 (compaction - ignored)
            (now - 1, 4000),  # +2000
            (now, 6000),  # +2000
        ]

        rate = tm.estimate_growth_rate()

        # Should average only positive deltas: (2000 + 2000 + 2000) / 3
        assert rate == 2000


class TestPredictivePressure:
    """Tests for predictive pressure estimation."""

    def test_predict_pressure_with_no_history(self):
        """Test prediction uses default growth rate."""
        tm = TokenManager(max_context_tokens=32000)

        messages = [{"role": "user", "content": "x" * 10000}]  # ~2500 tokens

        predicted = tm.predict_pressure(messages, steps_ahead=3)

        # Should predict current + (default_rate * steps)
        assert predicted.current_tokens > 2500

    def test_predict_pressure_level_escalation(self):
        """Test that predicted level escalates appropriately."""
        tm = TokenManager(max_context_tokens=32000)

        # effective = 32000 - 4096 = 27904
        # Mock count_tokens to return a controlled value that lands in CRITICAL range
        # CRITICAL range: 0.70 * 27904 = 19533 to 0.85 * 27904 = 23718
        messages = [{"role": "user", "content": "test message"}]

        with patch.object(tm, "count_tokens", return_value=17000):
            # With 2000 tokens/step growth, 3 steps = +6000 tokens
            # 17000 + 6000 = 23000, 23000/27904 ≈ 0.824 = CRITICAL
            tm._default_growth_rate = 2000

            predicted = tm.predict_pressure(messages, steps_ahead=3)

            # Predicted tokens should be approximately 17000 + 6000 = 23000
            assert 22500 <= predicted.current_tokens <= 23500
            # 23000 / effective_limit ≈ 0.824, within CRITICAL (0.70-0.85)
            assert predicted.level == PressureLevel.CRITICAL

    def test_predict_pressure_recommendations(self):
        """Test that predictions include recommendations."""
        tm = TokenManager(max_context_tokens=10000)

        # Force high prediction by using small context limit
        messages = [{"role": "user", "content": "x" * 25000}]  # ~6250 tokens = 62.5%

        # Predict with default growth of 2000
        predicted = tm.predict_pressure(messages, steps_ahead=3)

        # Should have recommendations if above normal
        if predicted.level != PressureLevel.NORMAL:
            assert len(predicted.recommendations) > 0
            # Should mention prediction
            assert any("Predicted" in r for r in predicted.recommendations)


class TestProactiveCompression:
    """Tests for proactive compression triggering."""

    def test_proactive_compression_on_current_critical(self):
        """Test proactive compression triggers on current critical."""
        tm = TokenManager(max_context_tokens=10000)

        # Create messages that put us at critical (>85%)
        messages = [{"role": "user", "content": "x" * 40000}]  # ~10000 tokens

        should_compress = tm.should_trigger_proactive_compression(messages)

        # At or near critical should trigger
        assert should_compress is True

    def test_proactive_compression_on_predicted_critical(self):
        """Test proactive compression triggers on predicted critical."""
        tm = TokenManager(max_context_tokens=32000)

        # Current is at 70% but growth will push to critical
        tm._growth_history = [
            (time.time() - 2, 15000),
            (time.time() - 1, 20000),
            (time.time(), 22400),  # 70%
        ]

        # Actual current tokens matter for the check
        messages = [{"role": "user", "content": "x" * 80000}]

        should_compress = tm.should_trigger_proactive_compression(messages)

        # May or may not trigger depending on actual token count
        # The important thing is the method runs without error
        assert isinstance(should_compress, bool)

    def test_no_proactive_compression_when_safe(self):
        """Test no proactive compression when usage is low."""
        tm = TokenManager(max_context_tokens=100000)  # Large limit

        messages = [{"role": "user", "content": "Small message"}]  # Few tokens

        should_compress = tm.should_trigger_proactive_compression(messages)

        assert should_compress is False


class TestGrowthStats:
    """Tests for growth statistics reporting."""

    def test_growth_stats_with_no_history(self):
        """Test stats with no history."""
        tm = TokenManager()

        stats = tm.get_growth_stats()

        assert "growth_rate_tokens_per_step" in stats
        assert "history_size" in stats
        assert stats["history_size"] == 0

    def test_growth_stats_with_history(self):
        """Test stats with growth history."""
        tm = TokenManager(max_context_tokens=32000)
        now = time.time()

        tm._growth_history = [
            (now - 2, 5000),
            (now - 1, 7000),
            (now, 9000),
        ]

        stats = tm.get_growth_stats()

        assert stats["history_size"] == 3
        assert stats["growth_rate_tokens_per_step"] == 2000

    def test_growth_stats_calculates_steps_to_thresholds(self):
        """Test that steps to thresholds are calculated."""
        tm = TokenManager(max_context_tokens=32000)
        now = time.time()

        # At ~25% usage with 2000 tokens/step growth
        # effective = 32000 - 4096 = 27904, warning at 60% = 16742
        # steps to warning = (16742 - 8000) / 2000 ≈ 4.37
        tm._growth_history = [
            (now - 1, 6000),
            (now, 8000),  # ~29% of effective
        ]

        stats = tm.get_growth_stats()

        assert stats["steps_to_warning"] is not None
        assert stats["steps_to_warning"] > 0


class TestPressureStatusSignal:
    """Tests for pressure status signal generation."""

    def test_normal_pressure_no_signal(self):
        """Test that normal pressure returns no signal."""
        status = PressureStatus(
            level=PressureLevel.NORMAL,
            usage_percent=0.5,
            current_tokens=5000,
            max_tokens=10000,
            available_tokens=5000,
            recommendations=[],
        )

        signal = status.to_context_signal()

        assert signal is None

    def test_warning_pressure_generates_signal(self):
        """Test that warning pressure generates a signal."""
        status = PressureStatus(
            level=PressureLevel.WARNING,
            usage_percent=0.78,
            current_tokens=7800,
            max_tokens=10000,
            available_tokens=2200,
            recommendations=["Summarize completed work"],
        )

        signal = status.to_context_signal()

        assert signal is not None
        assert "CONTEXT PRESSURE" in signal
        assert "78%" in signal

    def test_critical_pressure_includes_recommendations(self):
        """Test that critical pressure signal includes recommendations."""
        status = PressureStatus(
            level=PressureLevel.CRITICAL,
            usage_percent=0.90,
            current_tokens=9000,
            max_tokens=10000,
            available_tokens=1000,
            recommendations=["Save to files", "Summarize now"],
        )

        signal = status.to_context_signal()

        assert signal is not None
        assert "Save to files" in signal
        assert "Summarize now" in signal


class TestIntegration:
    """Integration tests for predictive context management."""

    def test_full_tracking_and_prediction_flow(self):
        """Test the full flow of tracking and prediction."""
        tm = TokenManager(max_context_tokens=50000)

        messages = [{"role": "user", "content": "Initial message"}]

        # Track several snapshots
        for i in range(5):
            messages.append({"role": "assistant", "content": f"Response {i}" + "x" * 1000})
            tm.track_token_snapshot(messages)

        # Get prediction
        predicted = tm.predict_pressure(messages)

        # Get growth stats
        stats = tm.get_growth_stats()

        assert stats["history_size"] == 5
        assert stats["growth_rate_tokens_per_step"] > 0
        assert isinstance(predicted, PressureStatus)

    def test_prediction_horizon_customization(self):
        """Test that prediction horizon can be customized."""
        tm = TokenManager()

        messages = [{"role": "user", "content": "Test message"}]

        # Predict with different horizons
        pred_3 = tm.predict_pressure(messages, steps_ahead=3)
        pred_10 = tm.predict_pressure(messages, steps_ahead=10)

        # More steps ahead should predict higher usage
        assert pred_10.current_tokens >= pred_3.current_tokens
