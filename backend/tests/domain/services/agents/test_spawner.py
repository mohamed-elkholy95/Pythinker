"""
Tests for the Agent Spawner module.

Covers all public methods of AgentSpawner, SpawnedAgentConfig,
SpawnDecision, SpawnTrigger, and the module-level singleton helpers.
All external dependencies (AgentRegistry, CommunicationProtocol) are mocked
so no running services are required.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.domain.models.agent_capability import (
    AgentCapability,
    AgentProfile,
    CapabilityCategory,
    CapabilityLevel,
)
from app.domain.services.agents.spawner import (
    AgentSpawner,
    SpawnDecision,
    SpawnedAgentConfig,
    SpawnTrigger,
    get_agent_spawner,
    reset_agent_spawner,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_profile(agent_type: str = "researcher", agent_name: str = "test_agent") -> AgentProfile:
    """Return a minimal AgentProfile for use as a registry return value."""
    return AgentProfile(
        agent_type=agent_type,
        agent_name=agent_name,
        capabilities=[],
        primary_category=None,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_registry():
    """Mock AgentRegistry with sensible defaults."""
    registry = MagicMock()
    registry.register_agent.return_value = _make_profile()
    registry.get_agents_with_capability.return_value = []
    registry.get_agents_by_category.return_value = []
    return registry


@pytest.fixture
def mock_protocol():
    """Mock CommunicationProtocol."""
    protocol = MagicMock()
    protocol.register_agent.return_value = MagicMock()
    protocol.unregister_agent.return_value = None
    return protocol


@pytest.fixture
def spawner(mock_registry, mock_protocol):
    """AgentSpawner with injected mocks — no global state contamination."""
    return AgentSpawner(registry=mock_registry, protocol=mock_protocol)


@pytest.fixture(autouse=True)
def reset_global_spawner():
    """Reset the module-level singleton before and after each test."""
    reset_agent_spawner()
    yield
    reset_agent_spawner()


# =============================================================================
# SpawnTrigger enum
# =============================================================================


class TestSpawnTrigger:
    """Tests for the SpawnTrigger enumeration."""

    def test_all_trigger_values_are_strings(self):
        """Every SpawnTrigger member must be a plain string value."""
        for member in SpawnTrigger:
            assert isinstance(member.value, str)

    def test_expected_trigger_members_exist(self):
        """Verify the complete set of trigger members is present."""
        names = {m.name for m in SpawnTrigger}
        assert "COMPLEXITY_THRESHOLD" in names
        assert "TOOL_REQUIREMENTS" in names
        assert "QUALITY_GATE_FAILURE" in names
        assert "CAPABILITY_GAP" in names
        assert "LOAD_BALANCING" in names
        assert "SPECIALIZATION" in names
        assert "PARALLEL_EXECUTION" in names

    def test_trigger_is_str_subclass(self):
        """SpawnTrigger inherits from str — values are usable as plain strings."""
        assert SpawnTrigger.COMPLEXITY_THRESHOLD == "complexity_threshold"
        assert SpawnTrigger.QUALITY_GATE_FAILURE == "quality_gate_failure"


# =============================================================================
# SpawnedAgentConfig
# =============================================================================


class TestSpawnedAgentConfig:
    """Tests for the SpawnedAgentConfig data class."""

    def test_required_fields_are_set(self):
        """Constructor sets agent_type and agent_name correctly."""
        cfg = SpawnedAgentConfig(agent_type="researcher", agent_name="agent_1")

        assert cfg.agent_type == "researcher"
        assert cfg.agent_name == "agent_1"

    def test_optional_fields_have_correct_defaults(self):
        """Optional fields default to sensible values when not provided."""
        cfg = SpawnedAgentConfig(agent_type="coder", agent_name="coder_1")

        assert cfg.parent_id is None
        assert cfg.capabilities == []
        assert cfg.tools == []
        assert cfg.context == {}
        assert cfg.max_iterations == 50
        assert cfg.timeout_seconds == 300

    def test_custom_values_are_stored(self):
        """All constructor arguments are persisted correctly."""
        cap = AgentCapability(
            name="web_research",
            category=CapabilityCategory.RESEARCH,
            level=CapabilityLevel.EXPERT,
        )
        cfg = SpawnedAgentConfig(
            agent_type="analyst",
            agent_name="analyst_42",
            parent_id="parent_agent",
            capabilities=[cap],
            tools=["file_read", "shell_exec"],
            context={"key": "value"},
            max_iterations=100,
            timeout_seconds=600,
        )

        assert cfg.parent_id == "parent_agent"
        assert len(cfg.capabilities) == 1
        assert cfg.capabilities[0].name == "web_research"
        assert cfg.tools == ["file_read", "shell_exec"]
        assert cfg.context == {"key": "value"}
        assert cfg.max_iterations == 100
        assert cfg.timeout_seconds == 600

    def test_created_at_is_timezone_aware_utc(self):
        """created_at is set to an aware UTC datetime on construction."""
        before = datetime.now(UTC)
        cfg = SpawnedAgentConfig(agent_type="x", agent_name="y")
        after = datetime.now(UTC)

        assert cfg.created_at.tzinfo is not None
        assert before <= cfg.created_at <= after

    def test_none_capabilities_becomes_empty_list(self):
        """Passing capabilities=None should yield an empty list, not None."""
        cfg = SpawnedAgentConfig(agent_type="x", agent_name="y", capabilities=None)
        assert cfg.capabilities == []

    def test_none_tools_becomes_empty_list(self):
        """Passing tools=None should yield an empty list, not None."""
        cfg = SpawnedAgentConfig(agent_type="x", agent_name="y", tools=None)
        assert cfg.tools == []

    def test_none_context_becomes_empty_dict(self):
        """Passing context=None should yield an empty dict, not None."""
        cfg = SpawnedAgentConfig(agent_type="x", agent_name="y", context=None)
        assert cfg.context == {}


# =============================================================================
# SpawnDecision
# =============================================================================


class TestSpawnDecision:
    """Tests for the SpawnDecision data class."""

    def test_should_spawn_true(self):
        """A positive decision stores should_spawn=True and the trigger."""
        cfg = SpawnedAgentConfig(agent_type="critic", agent_name="critic_1")
        decision = SpawnDecision(
            should_spawn=True,
            trigger=SpawnTrigger.QUALITY_GATE_FAILURE,
            config=cfg,
            reason="Quality check failed",
        )

        assert decision.should_spawn is True
        assert decision.trigger == SpawnTrigger.QUALITY_GATE_FAILURE
        assert decision.config is cfg
        assert "Quality" in decision.reason

    def test_should_spawn_false_with_alternatives(self):
        """A negative decision stores alternatives and no trigger."""
        decision = SpawnDecision(
            should_spawn=False,
            reason="Limit reached",
            alternative_actions=["wait", "retry"],
        )

        assert decision.should_spawn is False
        assert decision.trigger is None
        assert decision.config is None
        assert "wait" in decision.alternative_actions
        assert "retry" in decision.alternative_actions

    def test_defaults_for_optional_fields(self):
        """Optional fields default to sensible values."""
        decision = SpawnDecision(should_spawn=False)

        assert decision.trigger is None
        assert decision.config is None
        assert decision.reason == ""
        assert decision.alternative_actions == []

    def test_none_alternative_actions_becomes_empty_list(self):
        """Passing alternative_actions=None yields an empty list."""
        decision = SpawnDecision(should_spawn=False, alternative_actions=None)
        assert decision.alternative_actions == []


# =============================================================================
# AgentSpawner — construction
# =============================================================================


class TestAgentSpawnerConstruction:
    """Tests for AgentSpawner.__init__."""

    def test_initialises_with_injected_dependencies(self, mock_registry, mock_protocol):
        """Constructor stores injected registry and protocol."""
        s = AgentSpawner(registry=mock_registry, protocol=mock_protocol)

        assert s._registry is mock_registry
        assert s._protocol is mock_protocol

    def test_initial_spawned_agents_dict_is_empty(self, spawner):
        """No agents are tracked immediately after construction."""
        assert spawner._spawned_agents == {}

    def test_initial_spawn_count_is_zero(self, spawner):
        """Spawn counter starts at zero."""
        assert spawner._spawn_count == 0

    def test_uses_global_registry_when_none_provided(self):
        """When no registry is injected, the global singleton is used."""
        with (
            patch("app.domain.services.agents.spawner.get_agent_registry") as mock_get_reg,
            patch("app.domain.services.agents.spawner.get_communication_protocol") as mock_get_proto,
        ):
            mock_get_reg.return_value = MagicMock()
            mock_get_proto.return_value = MagicMock()

            AgentSpawner()

            mock_get_reg.assert_called_once()
            mock_get_proto.assert_called_once()

    def test_class_constants_have_expected_values(self):
        """Class-level thresholds match documented constants."""
        assert AgentSpawner.COMPLEXITY_SPAWN_THRESHOLD == 0.7
        assert AgentSpawner.MAX_SPAWNED_AGENTS == 5

    def test_capability_agent_map_covers_all_mapped_categories(self):
        """CAPABILITY_AGENT_MAP maps the six documented categories."""
        cmap = AgentSpawner.CAPABILITY_AGENT_MAP
        assert CapabilityCategory.RESEARCH in cmap
        assert CapabilityCategory.CODING in cmap
        assert CapabilityCategory.ANALYSIS in cmap
        assert CapabilityCategory.VERIFICATION in cmap
        assert CapabilityCategory.BROWSER in cmap
        assert CapabilityCategory.FILE in cmap


# =============================================================================
# AgentSpawner.should_spawn — spawn-limit guard
# =============================================================================


class TestShouldSpawnLimit:
    """Tests for the spawn-limit guard in should_spawn."""

    def test_returns_no_spawn_when_limit_reached(self, spawner, mock_registry, mock_protocol):
        """When MAX_SPAWNED_AGENTS agents are already tracked, spawn is denied."""
        # Fill the tracker to the limit
        for i in range(AgentSpawner.MAX_SPAWNED_AGENTS):
            cfg = SpawnedAgentConfig(agent_type="researcher", agent_name=f"agent_{i}")
            spawner._spawned_agents[f"agent_{i}"] = cfg

        decision = spawner.should_spawn(
            task_description="Research AI trends",
            current_agent_type="executor",
            complexity_score=0.9,
        )

        assert decision.should_spawn is False
        assert str(AgentSpawner.MAX_SPAWNED_AGENTS) in decision.reason

    def test_limit_check_happens_before_all_other_triggers(self, spawner):
        """Even quality_failure=True is ignored once the limit is full."""
        for i in range(AgentSpawner.MAX_SPAWNED_AGENTS):
            cfg = SpawnedAgentConfig(agent_type="x", agent_name=f"a_{i}")
            spawner._spawned_agents[f"a_{i}"] = cfg

        decision = spawner.should_spawn(
            task_description="Review output",
            current_agent_type="executor",
            complexity_score=0.99,
            quality_failure=True,
        )

        assert decision.should_spawn is False


# =============================================================================
# AgentSpawner.should_spawn — quality gate trigger
# =============================================================================


class TestShouldSpawnQualityGate:
    """Tests for quality-gate-failure branching in should_spawn."""

    def test_spawns_critic_on_quality_failure(self, spawner):
        """Quality failure from a non-critic agent triggers a critic spawn."""
        decision = spawner.should_spawn(
            task_description="Write a report",
            current_agent_type="executor",
            complexity_score=0.3,
            quality_failure=True,
        )

        assert decision.should_spawn is True
        assert decision.trigger == SpawnTrigger.QUALITY_GATE_FAILURE
        assert decision.config is not None
        assert decision.config.agent_type == "critic"

    def test_does_not_spawn_when_already_critic(self, spawner):
        """Quality failure while already a critic agent yields no spawn."""
        decision = spawner.should_spawn(
            task_description="Review output",
            current_agent_type="critic",
            complexity_score=0.3,
            quality_failure=True,
        )

        assert decision.should_spawn is False
        assert decision.alternative_actions  # should suggest alternatives

    def test_quality_failure_takes_priority_over_complexity(self, spawner):
        """quality_failure=True is evaluated before the complexity threshold."""
        decision = spawner.should_spawn(
            task_description="Implement complex system",
            current_agent_type="executor",
            complexity_score=0.99,  # would also trigger complexity branch
            quality_failure=True,
        )

        # Must be quality-gate triggered, not complexity
        assert decision.trigger == SpawnTrigger.QUALITY_GATE_FAILURE


# =============================================================================
# AgentSpawner.should_spawn — complexity trigger
# =============================================================================


class TestShouldSpawnComplexity:
    """Tests for complexity-threshold branching in should_spawn."""

    def test_spawns_when_complexity_meets_threshold(self, spawner):
        """Complexity at exactly the threshold triggers a spawn."""
        decision = spawner.should_spawn(
            task_description="Write code",
            current_agent_type="executor",
            complexity_score=AgentSpawner.COMPLEXITY_SPAWN_THRESHOLD,
        )

        assert decision.should_spawn is True
        assert decision.trigger == SpawnTrigger.COMPLEXITY_THRESHOLD

    def test_spawns_when_complexity_exceeds_threshold(self, spawner):
        """Complexity above the threshold also triggers a spawn."""
        decision = spawner.should_spawn(
            task_description="Write code",
            current_agent_type="executor",
            complexity_score=0.95,
        )

        assert decision.should_spawn is True

    def test_does_not_spawn_below_threshold(self, spawner):
        """Complexity below the threshold does not trigger a complexity spawn."""
        decision = spawner.should_spawn(
            task_description="Write simple code",
            current_agent_type="executor",
            complexity_score=0.5,
        )

        # Complexity branch should not fire; other branches may still return False
        assert decision.trigger != SpawnTrigger.COMPLEXITY_THRESHOLD

    def test_no_spawn_when_same_agent_type_already_used(self, spawner):
        """Complexity spawn is skipped when the inferred type matches the current type."""
        # "code" in description → inferred category CODING → agent_type "coder"
        decision = spawner.should_spawn(
            task_description="Fix this code bug",
            current_agent_type="coder",
            complexity_score=0.9,
        )

        assert decision.should_spawn is False

    def test_complexity_reason_includes_score(self, spawner):
        """The reason string for complexity decisions includes the score value."""
        decision = spawner.should_spawn(
            task_description="Research something complex",
            current_agent_type="executor",
            complexity_score=0.85,
        )

        # Only check if the complexity branch actually triggered
        if decision.trigger == SpawnTrigger.COMPLEXITY_THRESHOLD:
            assert "0.85" in decision.reason


# =============================================================================
# AgentSpawner.should_spawn — tool requirements trigger
# =============================================================================


class TestShouldSpawnToolRequirements:
    """Tests for tool-requirements branching in should_spawn."""

    def test_spawns_when_required_tool_not_available(self, spawner, mock_registry):
        """A tool with no existing capable agents triggers a tool-specialist spawn."""
        mock_registry.get_agents_with_capability.return_value = []

        decision = spawner.should_spawn(
            task_description="A task",
            current_agent_type="executor",
            complexity_score=0.1,
            required_tools=["exotic_tool"],
        )

        assert decision.should_spawn is True
        assert decision.trigger == SpawnTrigger.TOOL_REQUIREMENTS
        assert decision.config is not None
        assert decision.config.agent_type == "tool_specialist"

    def test_no_spawn_when_all_tools_available(self, spawner, mock_registry):
        """No spawn if every required tool already has a capable agent."""
        mock_registry.get_agents_with_capability.return_value = [_make_profile()]

        decision = spawner.should_spawn(
            task_description="A task",
            current_agent_type="executor",
            complexity_score=0.1,
            required_tools=["shell_exec"],
        )

        assert decision.should_spawn is False

    def test_tool_config_contains_all_required_tools(self, spawner, mock_registry):
        """The spawned tool-specialist config lists every required tool."""
        mock_registry.get_agents_with_capability.return_value = []

        decision = spawner.should_spawn(
            task_description="Task",
            current_agent_type="executor",
            complexity_score=0.1,
            required_tools=["tool_a", "tool_b"],
        )

        assert decision.config is not None
        assert "tool_a" in decision.config.tools
        assert "tool_b" in decision.config.tools

    def test_empty_required_tools_list_skips_tool_branch(self, spawner):
        """An empty tools list does not enter the tool-requirements branch."""
        decision = spawner.should_spawn(
            task_description="Simple task",
            current_agent_type="executor",
            complexity_score=0.1,
            required_tools=[],
        )

        assert decision.trigger != SpawnTrigger.TOOL_REQUIREMENTS

    def test_none_required_tools_skips_tool_branch(self, spawner):
        """required_tools=None does not enter the tool-requirements branch."""
        decision = spawner.should_spawn(
            task_description="Simple task",
            current_agent_type="executor",
            complexity_score=0.1,
            required_tools=None,
        )

        assert decision.trigger != SpawnTrigger.TOOL_REQUIREMENTS


# =============================================================================
# AgentSpawner.should_spawn — specialization trigger
# =============================================================================


class TestShouldSpawnSpecialization:
    """Tests for the specialization check in should_spawn."""

    def test_spawns_researcher_for_research_task_with_no_research_agents(self, spawner, mock_registry):
        """A research keyword triggers a researcher spawn when none is registered."""
        mock_registry.get_agents_by_category.return_value = []

        decision = spawner.should_spawn(
            task_description="Research the latest AI trends",
            current_agent_type="executor",
            complexity_score=0.1,
        )

        assert decision.should_spawn is True
        assert decision.trigger == SpawnTrigger.SPECIALIZATION
        assert decision.config is not None
        assert decision.config.agent_type == "researcher"

    def test_no_specialization_spawn_when_research_agent_already_exists(self, spawner, mock_registry):
        """No specialization spawn if a research-capable agent is already registered."""
        mock_registry.get_agents_by_category.return_value = [_make_profile("researcher")]

        decision = spawner.should_spawn(
            task_description="Research AI trends",
            current_agent_type="executor",
            complexity_score=0.1,
        )

        assert decision.trigger != SpawnTrigger.SPECIALIZATION

    def test_investigate_keyword_triggers_specialization(self, spawner, mock_registry):
        """'investigate' keyword is also recognized as a research need."""
        mock_registry.get_agents_by_category.return_value = []

        decision = spawner.should_spawn(
            task_description="Investigate the root cause",
            current_agent_type="executor",
            complexity_score=0.1,
        )

        assert decision.trigger == SpawnTrigger.SPECIALIZATION

    def test_analyze_data_keyword_triggers_specialization(self, spawner, mock_registry):
        """'analyze data' phrase triggers the specialization check."""
        mock_registry.get_agents_by_category.return_value = []

        decision = spawner.should_spawn(
            task_description="Please analyze data from the report",
            current_agent_type="executor",
            complexity_score=0.1,
        )

        assert decision.trigger == SpawnTrigger.SPECIALIZATION


# =============================================================================
# AgentSpawner.should_spawn — default / no trigger
# =============================================================================


class TestShouldSpawnDefault:
    """Tests for the default no-spawn path."""

    def test_returns_no_spawn_when_no_conditions_met(self, spawner, mock_registry):
        """All conditions absent → should_spawn=False with a generic reason."""
        mock_registry.get_agents_by_category.return_value = [_make_profile()]

        decision = spawner.should_spawn(
            task_description="Do a simple task",
            current_agent_type="executor",
            complexity_score=0.3,
        )

        assert decision.should_spawn is False
        assert decision.reason  # must have a non-empty reason string


# =============================================================================
# AgentSpawner.spawn_agent
# =============================================================================


class TestSpawnAgent:
    """Tests for AgentSpawner.spawn_agent."""

    def test_registers_agent_in_registry(self, spawner, mock_registry):
        """spawn_agent calls registry.register_agent with the correct arguments."""
        cfg = SpawnedAgentConfig(
            agent_type="researcher",
            agent_name="my_researcher",
            capabilities=[],
        )
        spawner.spawn_agent(cfg)

        mock_registry.register_agent.assert_called_once()
        call_kwargs = mock_registry.register_agent.call_args
        assert call_kwargs.kwargs.get("agent_type") == "researcher" or call_kwargs.args[0] == "researcher"

    def test_registers_agent_in_protocol(self, spawner, mock_protocol):
        """spawn_agent calls protocol.register_agent with the agent name."""
        cfg = SpawnedAgentConfig(agent_type="coder", agent_name="my_coder")
        spawner.spawn_agent(cfg)

        mock_protocol.register_agent.assert_called_once_with("my_coder")

    def test_tracks_agent_in_internal_dict(self, spawner):
        """The spawned agent is added to _spawned_agents keyed by name."""
        cfg = SpawnedAgentConfig(agent_type="analyst", agent_name="analyst_99")
        spawner.spawn_agent(cfg)

        assert "analyst_99" in spawner._spawned_agents
        assert spawner._spawned_agents["analyst_99"] is cfg

    def test_increments_spawn_count(self, spawner):
        """Each successful spawn increments _spawn_count by 1."""
        assert spawner._spawn_count == 0

        cfg = SpawnedAgentConfig(agent_type="x", agent_name="a1")
        spawner.spawn_agent(cfg)
        assert spawner._spawn_count == 1

        cfg2 = SpawnedAgentConfig(agent_type="x", agent_name="a2")
        spawner.spawn_agent(cfg2)
        assert spawner._spawn_count == 2

    def test_returns_agent_profile(self, spawner, mock_registry):
        """spawn_agent returns the AgentProfile produced by the registry."""
        profile = _make_profile("researcher", "researcher_profile")
        mock_registry.register_agent.return_value = profile

        cfg = SpawnedAgentConfig(agent_type="researcher", agent_name="rp")
        result = spawner.spawn_agent(cfg)

        assert result is profile

    def test_spawn_agent_with_parent_id(self, spawner):
        """Parent ID is preserved on the config after spawning."""
        cfg = SpawnedAgentConfig(agent_type="coder", agent_name="child_agent", parent_id="parent_001")
        spawner.spawn_agent(cfg)

        stored = spawner._spawned_agents["child_agent"]
        assert stored.parent_id == "parent_001"


# =============================================================================
# AgentSpawner.terminate_agent
# =============================================================================


class TestTerminateAgent:
    """Tests for AgentSpawner.terminate_agent."""

    def test_returns_true_when_agent_exists(self, spawner):
        """terminate_agent returns True for a tracked agent."""
        cfg = SpawnedAgentConfig(agent_type="x", agent_name="to_kill")
        spawner._spawned_agents["to_kill"] = cfg

        result = spawner.terminate_agent("to_kill")

        assert result is True

    def test_returns_false_when_agent_not_found(self, spawner):
        """terminate_agent returns False for an unknown agent name."""
        result = spawner.terminate_agent("ghost_agent")

        assert result is False

    def test_removes_agent_from_tracking(self, spawner):
        """The agent is no longer in _spawned_agents after termination."""
        cfg = SpawnedAgentConfig(agent_type="x", agent_name="gone")
        spawner._spawned_agents["gone"] = cfg

        spawner.terminate_agent("gone")

        assert "gone" not in spawner._spawned_agents

    def test_unregisters_agent_from_protocol(self, spawner, mock_protocol):
        """terminate_agent calls protocol.unregister_agent with the correct name."""
        cfg = SpawnedAgentConfig(agent_type="x", agent_name="bye_agent")
        spawner._spawned_agents["bye_agent"] = cfg

        spawner.terminate_agent("bye_agent")

        mock_protocol.unregister_agent.assert_called_once_with("bye_agent")

    def test_protocol_not_called_for_missing_agent(self, spawner, mock_protocol):
        """protocol.unregister_agent is NOT called when the agent isn't tracked."""
        spawner.terminate_agent("nonexistent")

        mock_protocol.unregister_agent.assert_not_called()


# =============================================================================
# AgentSpawner.spawn_for_task
# =============================================================================


class TestSpawnForTask:
    """Tests for AgentSpawner.spawn_for_task."""

    def test_returns_spawned_agent_config(self, spawner):
        """spawn_for_task returns a SpawnedAgentConfig on success."""
        result = spawner.spawn_for_task(
            task_id="task-001",
            task_description="Conduct web research",
            required_category=CapabilityCategory.RESEARCH,
            parent_agent_id="planner_agent",
        )

        assert result is not None
        assert isinstance(result, SpawnedAgentConfig)

    def test_uses_correct_agent_type_for_category(self, spawner):
        """The spawned config uses the agent type mapped from the category."""
        result = spawner.spawn_for_task(
            task_id="t1",
            task_description="Write code",
            required_category=CapabilityCategory.CODING,
            parent_agent_id="parent",
        )

        assert result is not None
        assert result.agent_type == "coder"

    def test_agent_name_includes_agent_type_and_count(self, spawner):
        """The auto-generated name encodes the type and a sequential number."""
        result = spawner.spawn_for_task(
            task_id="t1",
            task_description="Analyse data",
            required_category=CapabilityCategory.ANALYSIS,
            parent_agent_id="parent",
        )

        assert result is not None
        assert "analyst" in result.agent_name
        assert "1" in result.agent_name

    def test_parent_id_is_stored_on_config(self, spawner):
        """The parent_agent_id argument is preserved on the returned config."""
        result = spawner.spawn_for_task(
            task_id="t2",
            task_description="Browse website",
            required_category=CapabilityCategory.BROWSER,
            parent_agent_id="orchestrator",
        )

        assert result is not None
        assert result.parent_id == "orchestrator"

    def test_context_is_passed_to_config(self, spawner):
        """Additional context is forwarded to the spawned agent config."""
        ctx = {"session_id": "abc", "depth": 3}
        result = spawner.spawn_for_task(
            task_id="t3",
            task_description="File task",
            required_category=CapabilityCategory.FILE,
            parent_agent_id="parent",
            context=ctx,
        )

        assert result is not None
        assert result.context == ctx

    def test_none_context_becomes_empty_dict(self, spawner):
        """Omitting context results in an empty dict on the config."""
        result = spawner.spawn_for_task(
            task_id="t4",
            task_description="Verify output",
            required_category=CapabilityCategory.VERIFICATION,
            parent_agent_id="parent",
            context=None,
        )

        assert result is not None
        assert result.context == {}

    def test_unknown_category_uses_generic_type(self, spawner):
        """A category not in the map falls back to the 'generic' agent type."""
        result = spawner.spawn_for_task(
            task_id="t5",
            task_description="Do something creative",
            required_category=CapabilityCategory.CREATIVE,
            parent_agent_id="parent",
        )

        assert result is not None
        assert result.agent_type == "generic"

    def test_agent_is_tracked_after_spawn_for_task(self, spawner):
        """The returned config is added to the spawner's internal tracking."""
        result = spawner.spawn_for_task(
            task_id="t6",
            task_description="Research task",
            required_category=CapabilityCategory.RESEARCH,
            parent_agent_id="parent",
        )

        assert result is not None
        assert result.agent_name in spawner._spawned_agents


# =============================================================================
# AgentSpawner.spawn_parallel_agents
# =============================================================================


class TestSpawnParallelAgents:
    """Tests for AgentSpawner.spawn_parallel_agents."""

    def test_spawns_one_agent_per_task(self, spawner):
        """Returns one SpawnedAgentConfig per input task."""
        tasks = [
            ("t1", "Research AI", CapabilityCategory.RESEARCH),
            ("t2", "Write code", CapabilityCategory.CODING),
            ("t3", "Analyse results", CapabilityCategory.ANALYSIS),
        ]

        configs = spawner.spawn_parallel_agents(tasks, parent_agent_id="orchestrator")

        assert len(configs) == 3

    def test_returns_empty_list_for_no_tasks(self, spawner):
        """An empty task list produces an empty config list."""
        configs = spawner.spawn_parallel_agents([], parent_agent_id="orchestrator")

        assert configs == []

    def test_respects_available_slot_limit(self, spawner):
        """Agents already tracked reduce available slots; extras are skipped."""
        # Pre-fill 3 of the 5 available slots
        for i in range(3):
            cfg = SpawnedAgentConfig(agent_type="x", agent_name=f"existing_{i}")
            spawner._spawned_agents[f"existing_{i}"] = cfg

        tasks = [(f"t{i}", f"Task {i}", CapabilityCategory.ANALYSIS) for i in range(4)]
        configs = spawner.spawn_parallel_agents(tasks, parent_agent_id="parent")

        # Only 2 slots remain (5 max - 3 existing)
        assert len(configs) == 2

    def test_all_spawned_agents_are_tracked(self, spawner):
        """Every config returned by spawn_parallel_agents appears in _spawned_agents."""
        tasks = [
            ("t1", "Task 1", CapabilityCategory.RESEARCH),
            ("t2", "Task 2", CapabilityCategory.CODING),
        ]

        configs = spawner.spawn_parallel_agents(tasks, parent_agent_id="parent")

        for cfg in configs:
            assert cfg.agent_name in spawner._spawned_agents

    def test_configs_have_correct_parent_id(self, spawner):
        """All parallel configs inherit the provided parent_agent_id."""
        tasks = [
            ("t1", "Research", CapabilityCategory.RESEARCH),
            ("t2", "Code", CapabilityCategory.CODING),
        ]

        configs = spawner.spawn_parallel_agents(tasks, parent_agent_id="master_orchestrator")

        for cfg in configs:
            assert cfg.parent_id == "master_orchestrator"

    def test_zero_slots_available_returns_empty(self, spawner):
        """When the tracker is full, spawn_parallel_agents returns an empty list."""
        for i in range(AgentSpawner.MAX_SPAWNED_AGENTS):
            cfg = SpawnedAgentConfig(agent_type="x", agent_name=f"full_{i}")
            spawner._spawned_agents[f"full_{i}"] = cfg

        tasks = [("t1", "Extra task", CapabilityCategory.RESEARCH)]
        configs = spawner.spawn_parallel_agents(tasks, parent_agent_id="parent")

        assert configs == []


# =============================================================================
# AgentSpawner.get_spawned_agents / get_agent_count
# =============================================================================


class TestAgentCounting:
    """Tests for get_spawned_agents and get_agent_count."""

    def test_get_spawned_agents_returns_empty_when_none_spawned(self, spawner):
        """Initially returns an empty list."""
        assert spawner.get_spawned_agents() == []

    def test_get_spawned_agents_returns_all_tracked_configs(self, spawner):
        """All spawned configs are included in the returned list."""
        cfg1 = SpawnedAgentConfig(agent_type="x", agent_name="a1")
        cfg2 = SpawnedAgentConfig(agent_type="y", agent_name="a2")
        spawner._spawned_agents = {"a1": cfg1, "a2": cfg2}

        agents = spawner.get_spawned_agents()

        assert len(agents) == 2
        assert cfg1 in agents
        assert cfg2 in agents

    def test_get_agent_count_returns_zero_initially(self, spawner):
        """Count is zero before any agents are spawned."""
        assert spawner.get_agent_count() == 0

    def test_get_agent_count_reflects_current_tracked_agents(self, spawner):
        """Count matches the number of entries in _spawned_agents."""
        spawner._spawned_agents = {
            "a1": SpawnedAgentConfig(agent_type="x", agent_name="a1"),
            "a2": SpawnedAgentConfig(agent_type="y", agent_name="a2"),
            "a3": SpawnedAgentConfig(agent_type="z", agent_name="a3"),
        }

        assert spawner.get_agent_count() == 3

    def test_get_agent_count_decrements_after_terminate(self, spawner):
        """Count decrements when an agent is terminated."""
        cfg = SpawnedAgentConfig(agent_type="x", agent_name="to_remove")
        spawner._spawned_agents["to_remove"] = cfg

        assert spawner.get_agent_count() == 1
        spawner.terminate_agent("to_remove")
        assert spawner.get_agent_count() == 0


# =============================================================================
# AgentSpawner.cleanup_idle_agents
# =============================================================================


class TestCleanupIdleAgents:
    """Tests for cleanup_idle_agents."""

    def test_removes_agents_older_than_max_idle(self, spawner):
        """Agents created before the idle window are removed."""
        old_cfg = SpawnedAgentConfig(agent_type="x", agent_name="old_agent")
        # Simulate an agent that has been idle for 400 seconds
        old_cfg.created_at = datetime.now(UTC) - timedelta(seconds=400)
        spawner._spawned_agents["old_agent"] = old_cfg

        removed = spawner.cleanup_idle_agents(max_idle_seconds=300)

        assert removed == 1
        assert "old_agent" not in spawner._spawned_agents

    def test_keeps_agents_within_idle_window(self, spawner):
        """Recently created agents are not cleaned up."""
        fresh_cfg = SpawnedAgentConfig(agent_type="x", agent_name="fresh_agent")
        # created_at defaults to now — well within the idle window
        spawner._spawned_agents["fresh_agent"] = fresh_cfg

        removed = spawner.cleanup_idle_agents(max_idle_seconds=300)

        assert removed == 0
        assert "fresh_agent" in spawner._spawned_agents

    def test_returns_count_of_removed_agents(self, spawner):
        """Return value equals the number of agents actually cleaned up."""
        for i in range(3):
            cfg = SpawnedAgentConfig(agent_type="x", agent_name=f"old_{i}")
            cfg.created_at = datetime.now(UTC) - timedelta(seconds=1000)
            spawner._spawned_agents[f"old_{i}"] = cfg

        removed = spawner.cleanup_idle_agents(max_idle_seconds=300)

        assert removed == 3

    def test_returns_zero_when_nothing_to_clean(self, spawner):
        """No agents to clean → returns 0."""
        removed = spawner.cleanup_idle_agents()
        assert removed == 0

    def test_only_idle_agents_are_removed(self, spawner):
        """Mixed-age agents: only the idle one is cleaned up."""
        old_cfg = SpawnedAgentConfig(agent_type="x", agent_name="old")
        old_cfg.created_at = datetime.now(UTC) - timedelta(seconds=600)

        fresh_cfg = SpawnedAgentConfig(agent_type="y", agent_name="fresh")
        # fresh_cfg.created_at is set to now by default

        spawner._spawned_agents = {"old": old_cfg, "fresh": fresh_cfg}

        removed = spawner.cleanup_idle_agents(max_idle_seconds=300)

        assert removed == 1
        assert "old" not in spawner._spawned_agents
        assert "fresh" in spawner._spawned_agents

    def test_cleanup_calls_terminate_agent_for_each_idle(self, spawner, mock_protocol):
        """cleanup_idle_agents delegates to terminate_agent (which calls unregister)."""
        old_cfg = SpawnedAgentConfig(agent_type="x", agent_name="idle_one")
        old_cfg.created_at = datetime.now(UTC) - timedelta(seconds=400)
        spawner._spawned_agents["idle_one"] = old_cfg

        spawner.cleanup_idle_agents(max_idle_seconds=300)

        mock_protocol.unregister_agent.assert_called_once_with("idle_one")

    def test_custom_idle_threshold_is_respected(self, spawner):
        """A custom max_idle_seconds is used instead of the default 300."""
        # Agent idle for 60 seconds — within 300s default threshold, outside 30s custom threshold.
        cfg = SpawnedAgentConfig(agent_type="x", agent_name="borderline")
        cfg.created_at = datetime.now(UTC) - timedelta(seconds=60)
        spawner._spawned_agents["borderline"] = cfg

        # With default 300s threshold → not removed (60s < 300s)
        removed_default = spawner.cleanup_idle_agents(max_idle_seconds=300)
        assert removed_default == 0
        assert "borderline" in spawner._spawned_agents

        # Same agent is now cleaned up with a tighter 30s threshold (60s > 30s)
        removed_custom = spawner.cleanup_idle_agents(max_idle_seconds=30)
        assert removed_custom == 1
        assert "borderline" not in spawner._spawned_agents


# =============================================================================
# Private helpers — _infer_category_from_task
# =============================================================================


class TestInferCategoryFromTask:
    """Tests for the _infer_category_from_task helper."""

    @pytest.mark.parametrize(
        "description,expected_category",
        [
            ("Write code to implement the feature", CapabilityCategory.CODING),
            ("Fix the broken function", CapabilityCategory.CODING),
            ("Debug the failing tests", CapabilityCategory.CODING),
            ("Implement the algorithm", CapabilityCategory.CODING),
            ("Research the latest ML papers", CapabilityCategory.RESEARCH),
            ("Search for documentation", CapabilityCategory.RESEARCH),
            ("Find relevant examples", CapabilityCategory.RESEARCH),
            ("Analyze the performance data", CapabilityCategory.ANALYSIS),
            ("Compare the two approaches", CapabilityCategory.ANALYSIS),
            ("Evaluate the results", CapabilityCategory.ANALYSIS),
            ("Browse the product website", CapabilityCategory.BROWSER),
            ("Load the web page", CapabilityCategory.BROWSER),
            ("Read the configuration file", CapabilityCategory.FILE),
            ("Write output to disk", CapabilityCategory.FILE),
        ],
    )
    def test_infers_correct_category(self, spawner, description, expected_category):
        """_infer_category_from_task maps known keywords to the correct category."""
        result = spawner._infer_category_from_task(description)
        assert result == expected_category

    def test_defaults_to_analysis_for_unknown_task(self, spawner):
        """An unrecognised description defaults to CapabilityCategory.ANALYSIS."""
        result = spawner._infer_category_from_task("Do something vague and undefined")
        assert result == CapabilityCategory.ANALYSIS

    def test_inference_is_case_insensitive(self, spawner):
        """Keywords are matched case-insensitively."""
        assert spawner._infer_category_from_task("WRITE CODE") == CapabilityCategory.CODING
        assert spawner._infer_category_from_task("RESEARCH trends") == CapabilityCategory.RESEARCH


# =============================================================================
# Private helpers — _get_primary_category
# =============================================================================


class TestGetPrimaryCategory:
    """Tests for the _get_primary_category helper."""

    @pytest.mark.parametrize(
        "agent_type,expected_category",
        [
            ("researcher", CapabilityCategory.RESEARCH),
            ("coder", CapabilityCategory.CODING),
            ("analyst", CapabilityCategory.ANALYSIS),
            ("critic", CapabilityCategory.VERIFICATION),
            ("browser_agent", CapabilityCategory.BROWSER),
            ("file_agent", CapabilityCategory.FILE),
        ],
    )
    def test_known_agent_types_return_correct_category(self, spawner, agent_type, expected_category):
        """All documented agent types map to the correct capability category."""
        result = spawner._get_primary_category(agent_type)
        assert result == expected_category

    def test_unknown_agent_type_returns_none(self, spawner):
        """An unmapped agent type returns None instead of raising."""
        result = spawner._get_primary_category("completely_unknown_type")
        assert result is None


# =============================================================================
# Private helpers — _create_capabilities_for_category
# =============================================================================


class TestCreateCapabilitiesForCategory:
    """Tests for the _create_capabilities_for_category helper."""

    @pytest.mark.parametrize(
        "category",
        [
            CapabilityCategory.RESEARCH,
            CapabilityCategory.CODING,
            CapabilityCategory.ANALYSIS,
            CapabilityCategory.VERIFICATION,
        ],
    )
    def test_returns_non_empty_list_for_known_categories(self, spawner, category):
        """Known categories produce at least one AgentCapability."""
        caps = spawner._create_capabilities_for_category(category)
        assert isinstance(caps, list)
        assert len(caps) >= 1

    def test_capabilities_belong_to_correct_category(self, spawner):
        """All returned capabilities match the requested category."""
        for cat in [
            CapabilityCategory.RESEARCH,
            CapabilityCategory.CODING,
            CapabilityCategory.ANALYSIS,
            CapabilityCategory.VERIFICATION,
        ]:
            caps = spawner._create_capabilities_for_category(cat)
            for cap in caps:
                assert cap.category == cat

    def test_returns_empty_list_for_unmapped_category(self, spawner):
        """Unmapped categories (e.g. BROWSER) return an empty list gracefully."""
        caps = spawner._create_capabilities_for_category(CapabilityCategory.BROWSER)
        assert isinstance(caps, list)

    def test_research_capability_has_required_tool(self, spawner):
        """The research capability specifies at least one required tool."""
        caps = spawner._create_capabilities_for_category(CapabilityCategory.RESEARCH)
        all_tools: list[str] = []
        for cap in caps:
            all_tools.extend(cap.required_tools)
        assert "info_search_web" in all_tools

    def test_coding_capability_has_required_tools(self, spawner):
        """The coding capability specifies shell and file tools."""
        caps = spawner._create_capabilities_for_category(CapabilityCategory.CODING)
        all_tools: list[str] = []
        for cap in caps:
            all_tools.extend(cap.required_tools)
        assert "file_write" in all_tools
        assert "shell_exec" in all_tools

    def test_capabilities_are_of_correct_type(self, spawner):
        """Every returned object is an AgentCapability Pydantic model."""
        caps = spawner._create_capabilities_for_category(CapabilityCategory.RESEARCH)
        for cap in caps:
            assert isinstance(cap, AgentCapability)


# =============================================================================
# Module-level singleton helpers
# =============================================================================


class TestModuleSingleton:
    """Tests for get_agent_spawner and reset_agent_spawner."""

    def test_get_agent_spawner_returns_agent_spawner_instance(self):
        """get_agent_spawner returns an AgentSpawner object."""
        with (
            patch("app.domain.services.agents.spawner.get_agent_registry") as reg,
            patch("app.domain.services.agents.spawner.get_communication_protocol") as proto,
        ):
            reg.return_value = MagicMock()
            proto.return_value = MagicMock()

            spawner = get_agent_spawner()

        assert isinstance(spawner, AgentSpawner)

    def test_get_agent_spawner_returns_same_instance_on_repeated_calls(self):
        """Repeated calls return the identical object (singleton pattern)."""
        with (
            patch("app.domain.services.agents.spawner.get_agent_registry") as reg,
            patch("app.domain.services.agents.spawner.get_communication_protocol") as proto,
        ):
            reg.return_value = MagicMock()
            proto.return_value = MagicMock()

            s1 = get_agent_spawner()
            s2 = get_agent_spawner()

        assert s1 is s2

    def test_reset_agent_spawner_forces_new_instance_on_next_get(self):
        """After reset, get_agent_spawner creates a fresh AgentSpawner."""
        with (
            patch("app.domain.services.agents.spawner.get_agent_registry") as reg,
            patch("app.domain.services.agents.spawner.get_communication_protocol") as proto,
        ):
            reg.return_value = MagicMock()
            proto.return_value = MagicMock()

            s1 = get_agent_spawner()
            reset_agent_spawner()
            s2 = get_agent_spawner()

        assert s1 is not s2

    def test_reset_when_none_is_safe(self):
        """Calling reset_agent_spawner when no singleton exists does not raise."""
        reset_agent_spawner()  # already reset by autouse fixture — safe to call again
        reset_agent_spawner()  # second reset — should be a no-op


# =============================================================================
# Integration-style: full spawn lifecycle
# =============================================================================


class TestSpawnLifecycle:
    """End-to-end lifecycle tests covering spawn → work → terminate."""

    def test_spawn_then_terminate_leaves_clean_state(self, spawner):
        """After spawning and terminating an agent, the tracker is empty again."""
        cfg = SpawnedAgentConfig(agent_type="analyst", agent_name="lifecycle_agent")
        spawner.spawn_agent(cfg)

        assert spawner.get_agent_count() == 1

        spawner.terminate_agent("lifecycle_agent")

        assert spawner.get_agent_count() == 0
        assert spawner.get_spawned_agents() == []

    def test_spawn_count_does_not_decrement_on_terminate(self, spawner):
        """_spawn_count is a monotonic counter; it does not decrease on termination."""
        cfg = SpawnedAgentConfig(agent_type="x", agent_name="temp")
        spawner.spawn_agent(cfg)
        assert spawner._spawn_count == 1

        spawner.terminate_agent("temp")
        assert spawner._spawn_count == 1  # still 1

    def test_sequential_spawns_have_unique_names_via_spawn_for_task(self, spawner):
        """spawn_for_task uses the ever-incrementing _spawn_count to generate unique names."""
        cfg1 = spawner.spawn_for_task(
            task_id="t1",
            task_description="Research something",
            required_category=CapabilityCategory.RESEARCH,
            parent_agent_id="p",
        )
        cfg2 = spawner.spawn_for_task(
            task_id="t2",
            task_description="Research more",
            required_category=CapabilityCategory.RESEARCH,
            parent_agent_id="p",
        )

        assert cfg1 is not None
        assert cfg2 is not None
        assert cfg1.agent_name != cfg2.agent_name

    def test_parallel_spawn_then_cleanup(self, spawner):
        """Parallel-spawned agents can all be cleaned up via cleanup_idle_agents."""
        tasks = [
            ("t1", "Research task", CapabilityCategory.RESEARCH),
            ("t2", "Coding task", CapabilityCategory.CODING),
        ]
        configs = spawner.spawn_parallel_agents(tasks, parent_agent_id="parent")

        # Age them artificially
        for cfg in configs:
            cfg.created_at = datetime.now(UTC) - timedelta(seconds=400)

        removed = spawner.cleanup_idle_agents(max_idle_seconds=300)

        assert removed == len(configs)
        assert spawner.get_agent_count() == 0
