"""Tests for user preference domain models."""

import pytest

from app.domain.models.user_preference import (
    CommunicationStyle,
    OutputFormat,
    PreferenceCategory,
    RiskTolerance,
    UserPreference,
    UserPreferenceProfile,
)


@pytest.mark.unit
class TestPreferenceCategoryEnum:
    def test_all_values(self) -> None:
        expected = {
            "communication", "tool_usage", "output_format",
            "risk_tolerance", "verbosity", "interaction_style",
        }
        assert {c.value for c in PreferenceCategory} == expected


@pytest.mark.unit
class TestCommunicationStyleEnum:
    def test_all_values(self) -> None:
        expected = {"concise", "detailed", "technical", "simple"}
        assert {s.value for s in CommunicationStyle} == expected


@pytest.mark.unit
class TestRiskToleranceEnum:
    def test_all_values(self) -> None:
        expected = {"conservative", "moderate", "aggressive"}
        assert {r.value for r in RiskTolerance} == expected


@pytest.mark.unit
class TestOutputFormatEnum:
    def test_all_values(self) -> None:
        expected = {"markdown", "plain_text", "structured", "code_focused"}
        assert {f.value for f in OutputFormat} == expected


@pytest.mark.unit
class TestUserPreference:
    def _make_pref(self, **kwargs) -> UserPreference:
        defaults = {
            "category": PreferenceCategory.COMMUNICATION,
            "name": "response_style",
            "value": "concise",
        }
        defaults.update(kwargs)
        return UserPreference(**defaults)

    def test_basic_construction(self) -> None:
        pref = self._make_pref()
        assert pref.name == "response_style"
        assert pref.value == "concise"
        assert pref.confidence == 0.5
        assert pref.source == "inferred"
        assert pref.usage_count == 0

    def test_update_value(self) -> None:
        pref = self._make_pref(confidence=0.5)
        pref.update_value("detailed", confidence_boost=0.2)
        assert pref.value == "detailed"
        assert pref.confidence == 0.7
        assert pref.usage_count == 1

    def test_update_value_caps_at_one(self) -> None:
        pref = self._make_pref(confidence=0.95)
        pref.update_value("new", confidence_boost=0.2)
        assert pref.confidence == 1.0


@pytest.mark.unit
class TestUserPreferenceProfile:
    def test_basic_construction(self) -> None:
        profile = UserPreferenceProfile(user_id="user1")
        assert profile.user_id == "user1"
        assert profile.preferences == []
        assert profile.communication_style == CommunicationStyle.DETAILED
