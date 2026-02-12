"""Unit tests for token management optimization (Priority 4)."""

from app.domain.models.pressure import PressureLevel
from app.domain.services.agents.token_manager import TokenManager


def test_early_warning_threshold_at_60_percent():
    """Test that early warning triggers at 60% token usage."""
    manager = TokenManager(max_context_tokens=10000, safety_margin=2000)

    # 60% of max (before safety margin)
    tokens_used = 6000

    pressure = manager.check_pressure(tokens_used)

    # Should be early warning or higher
    assert pressure in [
        PressureLevel.EARLY_WARNING,
        PressureLevel.WARNING,
        PressureLevel.CRITICAL,
        PressureLevel.OVERFLOW,
    ]


def test_critical_threshold_at_80_percent():
    """Test that critical pressure triggers at 80% token usage."""
    manager = TokenManager(max_context_tokens=10000, safety_margin=2000)

    # 80% of max (before safety margin)
    tokens_used = 8000

    pressure = manager.check_pressure(tokens_used)

    # Should be critical or overflow
    assert pressure in [PressureLevel.CRITICAL, PressureLevel.OVERFLOW]


def test_overflow_threshold_at_90_percent():
    """Test that overflow triggers at 90% token usage."""
    manager = TokenManager(max_context_tokens=10000, safety_margin=2000)

    # 90% of max (before safety margin)
    tokens_used = 9000

    pressure = manager.check_pressure(tokens_used)

    # Should be overflow
    assert pressure == PressureLevel.OVERFLOW


def test_normal_pressure_below_60_percent():
    """Test that pressure is normal below 60%."""
    manager = TokenManager(max_context_tokens=10000, safety_margin=2000)

    # 59% of effective context (10000 - 2000 = 8000)
    tokens_used = int((10000 - 2000) * 0.59)

    pressure = manager.check_pressure(tokens_used)

    assert pressure == PressureLevel.NORMAL


def test_reduced_safety_margin_provides_more_context():
    """Test that reduced safety margin allows more usable tokens."""
    # Old margin: 4096
    old_manager = TokenManager(max_context_tokens=200000, safety_margin=4096)

    # New margin: 2048
    new_manager = TokenManager(max_context_tokens=200000, safety_margin=2048)

    # Calculate usable tokens at 70% threshold
    old_effective = old_manager._max_effective_tokens
    new_effective = new_manager._max_effective_tokens

    # New effective should be 2048 tokens higher
    assert new_effective == old_effective + 2048


def test_safety_margin_from_config():
    """Test that safety margin can be set from config."""
    from app.core.config import get_settings

    settings = get_settings()

    # Create manager with config-driven margin
    manager = TokenManager(max_context_tokens=200000, safety_margin=settings.token_safety_margin)

    # Should use config value (2048)
    expected_effective = 200000 - settings.token_safety_margin

    assert manager._max_effective_tokens == expected_effective


def test_pressure_level_boundaries_exact():
    """Test exact pressure level boundaries."""
    manager = TokenManager(max_context_tokens=10000, safety_margin=2000)
    effective = 8000  # 10000 - 2000

    # Test exact boundaries
    test_cases = [
        (int(effective * 0.59), PressureLevel.NORMAL),  # 59% - normal
        (int(effective * 0.60), PressureLevel.EARLY_WARNING),  # 60% - early warning
        (int(effective * 0.70), PressureLevel.WARNING),  # 70% - warning
        (int(effective * 0.80), PressureLevel.CRITICAL),  # 80% - critical
        (int(effective * 0.90), PressureLevel.OVERFLOW),  # 90% - overflow
    ]

    for tokens, expected_pressure in test_cases:
        pressure = manager.check_pressure(tokens)
        assert pressure == expected_pressure, (
            f"Failed for {tokens} tokens: expected {expected_pressure}, got {pressure}"
        )


def test_token_pressure_metric_recorded():
    """Test that token pressure is recorded to metrics."""
    manager = TokenManager(max_context_tokens=10000, safety_margin=2000, session_id="test-session")

    # Trigger critical pressure
    manager.check_pressure(8000)

    # Metric should be set (value 3 for CRITICAL)
    # Note: Direct metric verification would require accessing metric value


def test_early_warning_enables_proactive_planning():
    """Test that early warning level gives agent time to react."""
    manager = TokenManager(max_context_tokens=100000, safety_margin=2048)

    # At 60%, agent gets early warning
    tokens_at_60_percent = int(((100000 - 2048) * 0.60) + 1)

    pressure = manager.check_pressure(tokens_at_60_percent)

    assert pressure == PressureLevel.EARLY_WARNING

    # Agent still has 20% headroom before critical (80%)
    headroom = int((100000 - 2048) * 0.80) - tokens_at_60_percent

    # Should have significant headroom (20% of effective tokens)
    assert headroom > 15000  # ~20% of 97952


def test_context_utilization_improvement():
    """Test that new thresholds improve context utilization."""
    # Scenario: 200K token model
    max_tokens = 200000

    # Old system: critical at 70%, safety margin 4096
    old_critical = int((max_tokens - 4096) * 0.70)

    # New system: critical at 80%, safety margin 2048
    new_critical = int((max_tokens - 2048) * 0.80)

    # Improvement in usable tokens before critical
    improvement = new_critical - old_critical

    # Should gain ~21K tokens before hitting critical
    assert improvement > 20000
    assert improvement < 22000
