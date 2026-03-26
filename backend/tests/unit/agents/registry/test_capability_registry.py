"""Tests for AgentRegistry capability routing and lifecycle.

Note on key design: _initialize_default_profiles stores each profile under its
agent_type string (e.g. "planner"), not its agent_name ("planner_default").
register_agent stores profiles under agent_name. Tests reflect this asymmetry.
"""

from __future__ import annotations

from app.domain.models.agent_capability import (
    AgentCapability,
    AgentProfile,
    CapabilityCategory,
    CapabilityLevel,
    TaskRequirement,
)
from app.domain.services.agents.registry.capability_registry import (
    DEFAULT_AGENT_PROFILES,
    AgentRegistry,
    get_agent_registry,
    reset_agent_registry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_capability(
    name: str,
    category: CapabilityCategory = CapabilityCategory.CODING,
    level: CapabilityLevel = CapabilityLevel.PROFICIENT,
    required_tools: list[str] | None = None,
) -> AgentCapability:
    return AgentCapability(
        name=name,
        category=category,
        level=level,
        description=f"Test capability: {name}",
        required_tools=required_tools or [],
    )


def _make_registry() -> AgentRegistry:
    """Return a fresh registry with no cross-test pollution."""
    return AgentRegistry()


def _register_named_agent(
    registry: AgentRegistry,
    agent_name: str = "named_executor",
    category: CapabilityCategory = CapabilityCategory.CODING,
    level: CapabilityLevel = CapabilityLevel.EXPERT,
    tools: list[str] | None = None,
    max_concurrent: int = 5,
) -> AgentProfile:
    """Register an agent whose registry key equals its agent_name."""
    caps = [_make_capability("primary_cap", category, level, required_tools=tools or [])]
    return registry.register_agent(
        agent_type="worker",
        agent_name=agent_name,
        capabilities=caps,
        primary_category=category,
        max_concurrent=max_concurrent,
    )


# ---------------------------------------------------------------------------
# __init__ / default profiles
# ---------------------------------------------------------------------------


class TestAgentRegistryInit:
    def test_default_profiles_loaded(self):
        registry = _make_registry()
        for agent_type in ("planner", "executor", "critic", "verifier", "reflection"):
            assert agent_type in registry._profiles

    def test_default_profiles_count_matches_config(self):
        registry = _make_registry()
        assert len(registry._profiles) == len(DEFAULT_AGENT_PROFILES)

    def test_assignments_list_starts_empty(self):
        registry = _make_registry()
        assert registry._assignments == []

    def test_profiles_are_agent_profile_instances(self):
        registry = _make_registry()
        for profile in registry._profiles.values():
            assert isinstance(profile, AgentProfile)


# ---------------------------------------------------------------------------
# _initialize_default_profiles — capability counts
# ---------------------------------------------------------------------------


class TestInitializeDefaultProfiles:
    def test_planner_has_three_capabilities(self):
        registry = _make_registry()
        assert len(registry._profiles["planner"].capabilities) == 3

    def test_executor_has_four_capabilities(self):
        registry = _make_registry()
        assert len(registry._profiles["executor"].capabilities) == 4

    def test_critic_has_three_capabilities(self):
        registry = _make_registry()
        assert len(registry._profiles["critic"].capabilities) == 3

    def test_verifier_has_two_capabilities(self):
        registry = _make_registry()
        assert len(registry._profiles["verifier"].capabilities) == 2

    def test_reflection_has_two_capabilities(self):
        registry = _make_registry()
        assert len(registry._profiles["reflection"].capabilities) == 2

    def test_planner_primary_category_is_planning(self):
        registry = _make_registry()
        assert registry._profiles["planner"].primary_category == CapabilityCategory.PLANNING

    def test_executor_primary_category_is_coding(self):
        registry = _make_registry()
        assert registry._profiles["executor"].primary_category == CapabilityCategory.CODING

    def test_default_profile_agent_name_uses_type_suffix(self):
        registry = _make_registry()
        for agent_type, profile in registry._profiles.items():
            assert profile.agent_name == f"{agent_type}_default"

    def test_default_profiles_keyed_by_agent_type(self):
        # The registry key is agent_type, not agent_name.
        registry = _make_registry()
        for agent_type in DEFAULT_AGENT_PROFILES:
            assert registry._profiles[agent_type].agent_type == agent_type

    def test_executor_code_execution_has_required_tools(self):
        registry = _make_registry()
        cap = registry._profiles["executor"].get_capability("code_execution")
        assert cap is not None
        assert "shell_exec" in cap.required_tools


# ---------------------------------------------------------------------------
# register_agent
# ---------------------------------------------------------------------------


class TestRegisterAgent:
    def test_register_adds_profile_by_name(self):
        registry = _make_registry()
        caps = [_make_capability("data_analysis", CapabilityCategory.ANALYSIS)]
        profile = registry.register_agent(
            agent_type="analyst",
            agent_name="analyst_v1",
            capabilities=caps,
        )
        assert registry._profiles["analyst_v1"] is profile

    def test_register_returns_agent_profile(self):
        registry = _make_registry()
        caps = [_make_capability("file_read", CapabilityCategory.FILE)]
        result = registry.register_agent(
            agent_type="file_agent",
            agent_name="file_agent_1",
            capabilities=caps,
        )
        assert isinstance(result, AgentProfile)
        assert result.agent_name == "file_agent_1"
        assert result.agent_type == "file_agent"

    def test_register_stores_capabilities(self):
        registry = _make_registry()
        caps = [
            _make_capability("cap_a", CapabilityCategory.RESEARCH),
            _make_capability("cap_b", CapabilityCategory.ANALYSIS),
        ]
        profile = registry.register_agent("researcher", "researcher_1", caps)
        assert len(profile.capabilities) == 2

    def test_register_sets_primary_category(self):
        registry = _make_registry()
        caps = [_make_capability("browse", CapabilityCategory.BROWSER)]
        profile = registry.register_agent(
            "browser_agent",
            "browser_1",
            caps,
            primary_category=CapabilityCategory.BROWSER,
        )
        assert profile.primary_category == CapabilityCategory.BROWSER

    def test_register_sets_max_concurrent(self):
        registry = _make_registry()
        caps = [_make_capability("shell_run", CapabilityCategory.SHELL)]
        profile = registry.register_agent("shell_agent", "shell_1", caps, max_concurrent=3)
        assert profile.max_concurrent_tasks == 3

    def test_register_overwrites_existing_name(self):
        registry = _make_registry()
        caps_v1 = [_make_capability("old_cap", CapabilityCategory.FILE)]
        caps_v2 = [_make_capability("new_cap", CapabilityCategory.CODING)]
        registry.register_agent("agent_type", "overwrite_me", caps_v1)
        registry.register_agent("agent_type", "overwrite_me", caps_v2)
        profile = registry._profiles["overwrite_me"]
        assert profile.capabilities[0].name == "new_cap"


# ---------------------------------------------------------------------------
# get_agent
# ---------------------------------------------------------------------------


class TestGetAgent:
    def test_get_default_agent_by_type_key(self):
        # Default profiles are stored under agent_type as the dict key.
        registry = _make_registry()
        profile = registry.get_agent("planner")
        assert profile is not None
        assert profile.agent_type == "planner"

    def test_get_registered_agent_by_name(self):
        registry = _make_registry()
        _register_named_agent(registry, "custom_agent")
        assert registry.get_agent("custom_agent") is not None

    def test_get_unknown_agent_returns_none(self):
        registry = _make_registry()
        assert registry.get_agent("does_not_exist") is None

    def test_get_agent_returns_same_object(self):
        registry = _make_registry()
        first = registry.get_agent("executor")
        second = registry.get_agent("executor")
        assert first is second

    def test_default_agent_name_attribute_vs_key(self):
        # The stored profile's agent_name attribute is "{type}_default",
        # but the key used to look it up is just the agent_type.
        registry = _make_registry()
        profile = registry.get_agent("executor")
        assert profile is not None
        assert profile.agent_name == "executor_default"


# ---------------------------------------------------------------------------
# get_agents_by_type
# ---------------------------------------------------------------------------


class TestGetAgentsByType:
    def test_returns_default_profile_by_type(self):
        registry = _make_registry()
        results = registry.get_agents_by_type("planner")
        assert len(results) == 1
        assert results[0].agent_type == "planner"

    def test_returns_multiple_agents_of_same_type(self):
        registry = _make_registry()
        caps = [_make_capability("cap", CapabilityCategory.CODING)]
        registry.register_agent("executor", "executor_extra", caps)
        results = registry.get_agents_by_type("executor")
        names = {p.agent_name for p in results}
        assert "executor_default" in names
        assert "executor_extra" in names

    def test_returns_empty_for_unknown_type(self):
        registry = _make_registry()
        assert registry.get_agents_by_type("nonexistent_type") == []


# ---------------------------------------------------------------------------
# get_agents_with_capability
# ---------------------------------------------------------------------------


class TestGetAgentsWithCapability:
    def test_finds_agent_with_exact_capability_name(self):
        registry = _make_registry()
        results = registry.get_agents_with_capability("task_decomposition")
        assert any(p.agent_name == "planner_default" for p in results)

    def test_min_level_filters_out_lower_levels(self):
        registry = _make_registry()
        caps = [_make_capability("quality_review", CapabilityCategory.VERIFICATION, CapabilityLevel.BASIC)]
        registry.register_agent("weak_critic", "weak_critic_1", caps)
        # Min level EXPERT should exclude the BASIC-level agent
        results = registry.get_agents_with_capability("quality_review", min_level=CapabilityLevel.EXPERT)
        names = {p.agent_name for p in results}
        assert "weak_critic_1" not in names
        assert "critic_default" in names  # critic default has EXPERT quality_review

    def test_returns_empty_for_nonexistent_capability(self):
        registry = _make_registry()
        assert registry.get_agents_with_capability("this_cap_does_not_exist") == []

    def test_limited_level_excluded_at_default_basic_threshold(self):
        registry = _make_registry()
        caps = [_make_capability("fact_checking", CapabilityCategory.VERIFICATION, CapabilityLevel.LIMITED)]
        registry.register_agent("limited_agent", "limited_1", caps)
        results = registry.get_agents_with_capability("fact_checking")
        assert not any(p.agent_name == "limited_1" for p in results)


# ---------------------------------------------------------------------------
# get_agents_by_category
# ---------------------------------------------------------------------------


class TestGetAgentsByCategory:
    def test_returns_agents_with_any_capability_in_category(self):
        registry = _make_registry()
        results = registry.get_agents_by_category(CapabilityCategory.PLANNING)
        names = {p.agent_name for p in results}
        # planner has PLANNING caps; reflection also has adaptive_replanning (PLANNING)
        assert "planner_default" in names
        assert "reflection_default" in names

    def test_returns_empty_for_category_with_no_agents(self):
        registry = _make_registry()
        results = registry.get_agents_by_category(CapabilityCategory.COMMUNICATION)
        assert results == []

    def test_newly_registered_agent_appears_by_category(self):
        registry = _make_registry()
        caps = [_make_capability("send_message", CapabilityCategory.COMMUNICATION)]
        registry.register_agent("comm_agent", "comm_1", caps)
        results = registry.get_agents_by_category(CapabilityCategory.COMMUNICATION)
        assert any(p.agent_name == "comm_1" for p in results)


# ---------------------------------------------------------------------------
# find_best_agent
# ---------------------------------------------------------------------------


class TestFindBestAgent:
    def _planning_requirement(self, task_id: str = "t1") -> TaskRequirement:
        return TaskRequirement(
            task_id=task_id,
            task_description="Plan a set of steps",
            required_category=CapabilityCategory.PLANNING,
        )

    def test_returns_tuple_of_profile_and_score(self):
        registry = _make_registry()
        req = self._planning_requirement()
        agent, score = registry.find_best_agent(req)
        assert agent is not None
        assert isinstance(score, float)

    def test_score_capped_at_one(self):
        registry = _make_registry()
        req = self._planning_requirement()
        _, score = registry.find_best_agent(req)
        assert 0.0 <= score <= 1.0

    def test_returns_none_and_zero_when_no_candidates(self):
        registry = AgentRegistry.__new__(AgentRegistry)
        registry._profiles = {}
        registry._assignments = []
        req = self._planning_requirement()
        agent, score = registry.find_best_agent(req)
        assert agent is None
        assert score == 0.0

    def test_unavailable_agent_not_selected(self):
        registry = _make_registry()
        registry._profiles["planner"].is_available = False
        req = self._planning_requirement()
        agent, _ = registry.find_best_agent(req)
        if agent is not None:
            assert agent.agent_name != "planner_default"

    def test_overloaded_agent_not_selected_when_only_candidate(self):
        registry = AgentRegistry.__new__(AgentRegistry)
        registry._profiles = {}
        registry._assignments = []
        caps = [_make_capability("task_decomposition", CapabilityCategory.PLANNING, CapabilityLevel.EXPERT)]
        profile = AgentProfile(
            agent_type="planner",
            agent_name="only_planner",
            capabilities=caps,
            primary_category=CapabilityCategory.PLANNING,
            max_concurrent_tasks=1,
            current_load=1,  # already at limit
        )
        registry._profiles["only_planner"] = profile
        req = self._planning_requirement()
        agent, score = registry.find_best_agent(req)
        assert agent is None
        assert score == 0.0


# ---------------------------------------------------------------------------
# route_task
# ---------------------------------------------------------------------------


class TestRouteTask:
    def test_route_returns_assignment_for_known_category(self):
        registry = _make_registry()
        assignment = registry.route_task(
            task_id="task-001",
            task_description="Write a Python script",
            required_category=CapabilityCategory.CODING,
        )
        assert assignment is not None
        assert assignment.task_id == "task-001"

    def test_route_assignment_fields_populated(self):
        registry = _make_registry()
        assignment = registry.route_task(
            task_id="task-002",
            task_description="Execute code",
            required_category=CapabilityCategory.CODING,
        )
        assert assignment is not None
        assert assignment.agent_name != ""
        assert assignment.agent_type != ""
        assert assignment.suitability_score > 0.0

    def test_route_increments_agent_load(self):
        registry = _make_registry()
        # Use a registered agent so the profile object can be tracked directly.
        agent = _register_named_agent(registry, "load_tracker", CapabilityCategory.CODING)
        initial_load = agent.current_load
        # Force all default profiles off so our agent wins
        for key, profile in registry._profiles.items():
            if key != "load_tracker":
                profile.is_available = False
        registry.route_task(
            task_id="task-003",
            task_description="File write",
            required_category=CapabilityCategory.CODING,
        )
        assert agent.current_load == initial_load + 1

    def test_route_appends_to_assignments_list(self):
        registry = _make_registry()
        before = len(registry._assignments)
        registry.route_task(
            task_id="task-004",
            task_description="Research query",
            required_category=CapabilityCategory.RESEARCH,
        )
        assert len(registry._assignments) == before + 1

    def test_route_returns_none_when_no_agent_available(self):
        registry = _make_registry()
        for profile in registry._profiles.values():
            profile.is_available = False
        result = registry.route_task(
            task_id="task-999",
            task_description="Impossible task",
            required_category=CapabilityCategory.CODING,
        )
        assert result is None

    def test_route_with_required_tools_reflected_in_assignment(self):
        registry = _make_registry()
        assignment = registry.route_task(
            task_id="task-005",
            task_description="Browse site",
            required_category=CapabilityCategory.BROWSER,
            required_tools=["browser_navigate"],
        )
        assert assignment is not None

    def test_route_assignment_completed_at_is_none(self):
        registry = _make_registry()
        assignment = registry.route_task(
            task_id="task-006",
            task_description="Plan steps",
            required_category=CapabilityCategory.PLANNING,
        )
        assert assignment is not None
        assert assignment.completed_at is None


# ---------------------------------------------------------------------------
# Assignment eviction — _MAX_ASSIGNMENTS
# ---------------------------------------------------------------------------


class TestAssignmentEviction:
    def test_assignments_capped_at_max(self):
        registry = _make_registry()
        caps = [_make_capability("work", CapabilityCategory.CODING, CapabilityLevel.EXPERT)]
        registry.register_agent("worker", "worker_unlimited", caps, max_concurrent=10_000)
        limit = AgentRegistry._MAX_ASSIGNMENTS
        for i in range(limit + 10):
            registry.route_task(
                task_id=f"evict-task-{i}",
                task_description="workload",
                required_category=CapabilityCategory.CODING,
            )
        assert len(registry._assignments) <= limit

    def test_oldest_assignments_are_evicted_first(self):
        registry = _make_registry()
        caps = [_make_capability("work", CapabilityCategory.CODING, CapabilityLevel.EXPERT)]
        registry.register_agent("worker", "worker_unlimited", caps, max_concurrent=10_000)
        limit = AgentRegistry._MAX_ASSIGNMENTS
        for i in range(limit + 5):
            registry.route_task(
                task_id=f"order-task-{i}",
                task_description="workload",
                required_category=CapabilityCategory.CODING,
            )
        remaining_ids = {a.task_id for a in registry._assignments}
        assert "order-task-0" not in remaining_ids
        assert f"order-task-{limit + 4}" in remaining_ids


# ---------------------------------------------------------------------------
# complete_assignment
# ---------------------------------------------------------------------------


class TestCompleteAssignment:
    """Use registered agents (key == agent_name) so complete_assignment can find them."""

    def _setup_registry_with_named_agent(self, agent_name: str = "comp_worker") -> tuple[AgentRegistry, AgentProfile]:
        registry = _make_registry()
        # Disable defaults so our named agent wins routing
        for profile in registry._profiles.values():
            profile.is_available = False
        agent = _register_named_agent(registry, agent_name, CapabilityCategory.CODING)
        return registry, agent

    def test_complete_sets_completed_at(self):
        registry, _ = self._setup_registry_with_named_agent("w1")
        registry.route_task("comp-1", "Code task", CapabilityCategory.CODING)
        registry.complete_assignment("comp-1", success=True, duration_ms=500.0)
        assignment = next(a for a in registry._assignments if a.task_id == "comp-1")
        assert assignment.completed_at is not None

    def test_complete_sets_success_flag(self):
        registry, _ = self._setup_registry_with_named_agent("w2")
        registry.route_task("comp-2", "Code task", CapabilityCategory.CODING)
        registry.complete_assignment("comp-2", success=False, duration_ms=200.0)
        assignment = next(a for a in registry._assignments if a.task_id == "comp-2")
        assert assignment.success is False

    def test_complete_sets_result_summary(self):
        registry, _ = self._setup_registry_with_named_agent("w3")
        registry.route_task("comp-3", "Code task", CapabilityCategory.CODING)
        registry.complete_assignment("comp-3", success=True, duration_ms=100.0, result_summary="Done")
        assignment = next(a for a in registry._assignments if a.task_id == "comp-3")
        assert assignment.result_summary == "Done"

    def test_complete_decrements_agent_load(self):
        registry, agent = self._setup_registry_with_named_agent("w4")
        registry.route_task("comp-4", "Code task", CapabilityCategory.CODING)
        load_after_route = agent.current_load
        registry.complete_assignment("comp-4", success=True, duration_ms=300.0)
        assert agent.current_load == load_after_route - 1

    def test_complete_increments_total_tasks_completed(self):
        registry, agent = self._setup_registry_with_named_agent("w5")
        before = agent.total_tasks_completed
        registry.route_task("comp-5", "Code task", CapabilityCategory.CODING)
        registry.complete_assignment("comp-5", success=True, duration_ms=300.0)
        assert agent.total_tasks_completed == before + 1

    def test_complete_updates_capability_usage_count(self):
        registry, agent = self._setup_registry_with_named_agent("w6")
        registry.route_task("comp-6", "Code task", CapabilityCategory.CODING)
        assignment = next(a for a in registry._assignments if a.task_id == "comp-6")
        cap = agent.get_capability(assignment.capability_used)
        initial_usage = cap.usage_count if cap else -1
        registry.complete_assignment("comp-6", success=True, duration_ms=100.0)
        if cap:
            assert cap.usage_count == initial_usage + 1

    def test_complete_updates_success_rate_on_success(self):
        registry, agent = self._setup_registry_with_named_agent("w7")
        registry.route_task("comp-7", "Code task", CapabilityCategory.CODING)
        registry.complete_assignment("comp-7", success=True, duration_ms=100.0)
        assert agent.overall_success_rate > 0.0

    def test_complete_missing_task_does_not_raise(self):
        registry = _make_registry()
        registry.complete_assignment("nonexistent-task", success=True, duration_ms=0.0)

    def test_complete_does_not_double_complete(self):
        registry, agent = self._setup_registry_with_named_agent("w8")
        registry.route_task("comp-8", "Code task", CapabilityCategory.CODING)
        registry.complete_assignment("comp-8", success=True, duration_ms=100.0)
        load_after_first = agent.current_load
        # Second call — no active (completed_at=None) assignment remains
        registry.complete_assignment("comp-8", success=True, duration_ms=100.0)
        assert agent.current_load == load_after_first


# ---------------------------------------------------------------------------
# get_agent_statistics
# ---------------------------------------------------------------------------


class TestGetAgentStatistics:
    def test_returns_dict_for_known_agent(self):
        registry = _make_registry()
        stats = registry.get_agent_statistics("executor")
        assert isinstance(stats, dict)

    def test_stats_contain_expected_keys(self):
        registry = _make_registry()
        stats = registry.get_agent_statistics("planner")
        for key in (
            "agent_name",
            "agent_type",
            "total_tasks",
            "success_rate",
            "current_load",
            "is_available",
            "capabilities",
            "recent_assignments",
        ):
            assert key in stats

    def test_returns_empty_dict_for_unknown_agent(self):
        registry = _make_registry()
        assert registry.get_agent_statistics("ghost_agent") == {}

    def test_capabilities_count_matches_profile(self):
        registry = _make_registry()
        stats = registry.get_agent_statistics("executor")
        executor = registry._profiles["executor"]
        assert stats["capabilities"] == len(executor.capabilities)

    def test_recent_assignments_reflects_completed_tasks(self):
        registry = _make_registry()
        # Disable defaults; register named agent whose key == agent_name
        for profile in registry._profiles.values():
            profile.is_available = False
        _register_named_agent(registry, "stat_worker", CapabilityCategory.CODING)
        registry.route_task("stat-1", "Code task", CapabilityCategory.CODING)
        registry.complete_assignment("stat-1", success=True, duration_ms=50.0)
        stats = registry.get_agent_statistics("stat_worker")
        assert stats["recent_assignments"] >= 1


# ---------------------------------------------------------------------------
# get_capability_coverage
# ---------------------------------------------------------------------------


class TestGetCapabilityCoverage:
    def test_returns_dict_with_all_categories(self):
        registry = _make_registry()
        coverage = registry.get_capability_coverage()
        for category in CapabilityCategory:
            assert category in coverage

    def test_planning_category_has_positive_count(self):
        registry = _make_registry()
        coverage = registry.get_capability_coverage()
        assert coverage[CapabilityCategory.PLANNING] > 0

    def test_communication_category_zero_by_default(self):
        registry = _make_registry()
        coverage = registry.get_capability_coverage()
        assert coverage[CapabilityCategory.COMMUNICATION] == 0

    def test_count_increases_when_new_agent_registered(self):
        registry = _make_registry()
        before = registry.get_capability_coverage()[CapabilityCategory.COMMUNICATION]
        caps = [_make_capability("notify", CapabilityCategory.COMMUNICATION)]
        registry.register_agent("comm", "comm_agent", caps)
        after = registry.get_capability_coverage()[CapabilityCategory.COMMUNICATION]
        assert after == before + 1


# ---------------------------------------------------------------------------
# list_all_agents
# ---------------------------------------------------------------------------


class TestListAllAgents:
    def test_returns_list_of_dicts(self):
        registry = _make_registry()
        result = registry.list_all_agents()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, dict)

    def test_length_matches_profiles_count(self):
        registry = _make_registry()
        assert len(registry.list_all_agents()) == len(registry._profiles)

    def test_each_entry_has_required_keys(self):
        registry = _make_registry()
        for entry in registry.list_all_agents():
            for key in ("name", "type", "primary_category", "capabilities", "available", "success_rate"):
                assert key in entry

    def test_entry_capabilities_field_is_int(self):
        registry = _make_registry()
        for entry in registry.list_all_agents():
            assert isinstance(entry["capabilities"], int)

    def test_primary_category_is_string_or_none(self):
        registry = _make_registry()
        for entry in registry.list_all_agents():
            assert entry["primary_category"] is None or isinstance(entry["primary_category"], str)

    def test_registered_agent_appears_in_list(self):
        registry = _make_registry()
        caps = [_make_capability("custom_cap", CapabilityCategory.ANALYSIS)]
        registry.register_agent("analyst", "analyst_listed", caps)
        names = {e["name"] for e in registry.list_all_agents()}
        assert "analyst_listed" in names


# ---------------------------------------------------------------------------
# get_agent_registry / reset_agent_registry — singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def setup_method(self):
        reset_agent_registry()

    def teardown_method(self):
        reset_agent_registry()

    def test_get_returns_agent_registry_instance(self):
        registry = get_agent_registry()
        assert isinstance(registry, AgentRegistry)

    def test_get_returns_same_instance_on_second_call(self):
        first = get_agent_registry()
        second = get_agent_registry()
        assert first is second

    def test_reset_causes_new_instance_on_next_get(self):
        first = get_agent_registry()
        reset_agent_registry()
        second = get_agent_registry()
        assert first is not second

    def test_reset_clears_global_state(self):
        registry = get_agent_registry()
        caps = [_make_capability("temp_cap", CapabilityCategory.FILE)]
        registry.register_agent("temp", "temp_agent", caps)
        reset_agent_registry()
        fresh = get_agent_registry()
        assert fresh.get_agent("temp_agent") is None

    def test_registry_after_reset_has_default_profiles(self):
        reset_agent_registry()
        fresh = get_agent_registry()
        for agent_type in ("planner", "executor", "critic", "verifier", "reflection"):
            assert agent_type in fresh._profiles
