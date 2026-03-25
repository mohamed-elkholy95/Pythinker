"""Tests for PressureLevel enum."""

from app.domain.models.pressure import PressureLevel


class TestPressureLevel:
    def test_normal(self):
        assert PressureLevel.NORMAL == "normal"

    def test_early_warning(self):
        assert PressureLevel.EARLY_WARNING == "early_warning"

    def test_warning(self):
        assert PressureLevel.WARNING == "warning"

    def test_critical(self):
        assert PressureLevel.CRITICAL == "critical"

    def test_overflow(self):
        assert PressureLevel.OVERFLOW == "overflow"

    def test_member_count(self):
        assert len(PressureLevel) == 5

    def test_is_str_enum(self):
        assert isinstance(PressureLevel.NORMAL, str)
