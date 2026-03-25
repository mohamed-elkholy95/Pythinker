"""Tests for agent capability domain models."""

import pytest

from app.domain.models.agent_capability import (
    AgentCapability,
    AgentProfile,
    CapabilityCategory,
    CapabilityLevel,
)


@pytest.mark.unit
class TestCapabilityCategoryEnum:
    def test_all_values(self) -> None:
        expected = {
            "research", "coding", "analysis", "creative", "browser",
            "file", "shell", "planning", "verification", "communication",
        }
        assert {c.value for c in CapabilityCategory} == expected


@pytest.mark.unit
class TestCapabilityLevelEnum:
    def test_all_values(self) -> None:
        expected = {"expert", "proficient", "basic", "limited", "none"}
        assert {lv.value for lv in CapabilityLevel} == expected


@pytest.mark.unit
class TestAgentCapability:
    def _make_cap(self, **kwargs) -> AgentCapability:
        defaults = {
            "name": "web_research",
            "category": CapabilityCategory.RESEARCH,
        }
        defaults.update(kwargs)
        return AgentCapability(**defaults)

    def test_basic_construction(self) -> None:
        cap = self._make_cap()
        assert cap.name == "web_research"
        assert cap.category == CapabilityCategory.RESEARCH
        assert cap.level == CapabilityLevel.PROFICIENT
        assert cap.performance_score == 0.5
        assert cap.usage_count == 0

    def test_is_suitable_for_matching_category(self) -> None:
        cap = self._make_cap(level=CapabilityLevel.EXPERT)
        assert cap.is_suitable_for(CapabilityCategory.RESEARCH) is True

    def test_is_not_suitable_for_wrong_category(self) -> None:
        cap = self._make_cap()
        assert cap.is_suitable_for(CapabilityCategory.CODING) is False

    def test_is_not_suitable_for_low_level(self) -> None:
        cap = self._make_cap(level=CapabilityLevel.BASIC)
        assert cap.is_suitable_for(CapabilityCategory.RESEARCH) is False

    def test_update_performance_success(self) -> None:
        cap = self._make_cap(success_rate=0.5)
        cap.update_performance(success=True, duration_ms=1000)
        assert cap.usage_count == 1
        assert cap.success_rate > 0.5

    def test_update_performance_failure(self) -> None:
        cap = self._make_cap(success_rate=0.5)
        cap.update_performance(success=False, duration_ms=10000)
        assert cap.usage_count == 1
        assert cap.success_rate < 0.5


@pytest.mark.unit
class TestAgentProfile:
    def _make_profile(self, **kwargs) -> AgentProfile:
        defaults = {
            "agent_type": "researcher",
            "agent_name": "research_agent_1",
        }
        defaults.update(kwargs)
        return AgentProfile(**defaults)

    def test_basic_construction(self) -> None:
        profile = self._make_profile()
        assert profile.agent_type == "researcher"
        assert profile.is_available is True
        assert profile.current_load == 0

    def test_get_capability_found(self) -> None:
        cap = AgentCapability(name="web_search", category=CapabilityCategory.RESEARCH)
        profile = self._make_profile(capabilities=[cap])
        assert profile.get_capability("web_search") is cap

    def test_get_capability_not_found(self) -> None:
        profile = self._make_profile()
        assert profile.get_capability("nonexistent") is None

    def test_get_capabilities_by_category(self) -> None:
        caps = [
            AgentCapability(name="search", category=CapabilityCategory.RESEARCH),
            AgentCapability(name="code", category=CapabilityCategory.CODING),
            AgentCapability(name="analyze", category=CapabilityCategory.RESEARCH),
        ]
        profile = self._make_profile(capabilities=caps)
        research_caps = profile.get_capabilities_by_category(CapabilityCategory.RESEARCH)
        assert len(research_caps) == 2

    def test_has_capability_true(self) -> None:
        cap = AgentCapability(name="search", category=CapabilityCategory.RESEARCH, level=CapabilityLevel.EXPERT)
        profile = self._make_profile(capabilities=[cap])
        assert profile.has_capability("search", min_level=CapabilityLevel.PROFICIENT) is True

    def test_has_capability_false_low_level(self) -> None:
        cap = AgentCapability(name="search", category=CapabilityCategory.RESEARCH, level=CapabilityLevel.LIMITED)
        profile = self._make_profile(capabilities=[cap])
        assert profile.has_capability("search", min_level=CapabilityLevel.PROFICIENT) is False

    def test_has_capability_false_missing(self) -> None:
        profile = self._make_profile()
        assert profile.has_capability("nonexistent") is False

    def test_can_take_task(self) -> None:
        profile = self._make_profile(max_concurrent_tasks=2, current_load=1)
        assert profile.can_take_task() is True

    def test_cannot_take_task_at_capacity(self) -> None:
        profile = self._make_profile(max_concurrent_tasks=1, current_load=1)
        assert profile.can_take_task() is False

    def test_cannot_take_task_unavailable(self) -> None:
        profile = self._make_profile(is_available=False)
        assert profile.can_take_task() is False

    def test_get_best_capability_for_category(self) -> None:
        caps = [
            AgentCapability(name="search1", category=CapabilityCategory.RESEARCH, performance_score=0.3),
            AgentCapability(name="search2", category=CapabilityCategory.RESEARCH, performance_score=0.9),
        ]
        profile = self._make_profile(capabilities=caps)
        best = profile.get_best_capability_for_category(CapabilityCategory.RESEARCH)
        assert best is not None
        assert best.name == "search2"

    def test_get_best_capability_empty_category(self) -> None:
        profile = self._make_profile()
        assert profile.get_best_capability_for_category(CapabilityCategory.RESEARCH) is None
