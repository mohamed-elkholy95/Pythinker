"""Tests for data models, enums, and pure functions in swarm.py.

Covers:
- AgentStatus enum
- SwarmTask dataclass (defaults, field types, mutation)
- SwarmResult dataclass (defaults, field types)
- AgentInstance dataclass (defaults, field types)
- SwarmConfig Pydantic model (validation, constraints)
- Swarm._AGENT_TYPE_MAP class variable
- Swarm._build_agent_prompt (pure string construction)
- Swarm._detect_handoff_request (JSON and regex paths)
- Swarm.get_stats (pure dictionary computation over internal state)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.domain.services.orchestration.agent_types import (
    AgentCapability,
    AgentSpec,
    AgentType,
)
from app.domain.services.orchestration.handoff import HandoffContext
from app.domain.services.orchestration.swarm import (
    AgentInstance,
    AgentStatus,
    Swarm,
    SwarmConfig,
    SwarmResult,
    SwarmTask,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_factory() -> MagicMock:
    factory = MagicMock()
    factory.create_agent = AsyncMock(return_value=MagicMock())
    factory.execute_agent = AsyncMock(return_value=iter([]))
    return factory


def _make_swarm(**kwargs: Any) -> Swarm:
    return Swarm(agent_factory=_make_factory(), session_id="test-session", **kwargs)


def _make_minimal_spec() -> AgentSpec:
    return AgentSpec(
        agent_type=AgentType.RESEARCHER,
        name="Researcher",
        description="Research agent",
        capabilities={AgentCapability.RESEARCH},
        tools=["info_search_web"],
        system_prompt_template="You are a researcher.",
    )


# ---------------------------------------------------------------------------
# AgentStatus enum
# ---------------------------------------------------------------------------


class TestAgentStatus:
    def test_all_members_present(self) -> None:
        members = {s.value for s in AgentStatus}
        assert members == {"idle", "working", "waiting", "completed", "failed"}

    def test_is_str_subclass(self) -> None:
        for status in AgentStatus:
            assert isinstance(status, str)

    def test_equality_with_string(self) -> None:
        assert AgentStatus.IDLE == "idle"
        assert AgentStatus.WORKING == "working"
        assert AgentStatus.WAITING == "waiting"
        assert AgentStatus.COMPLETED == "completed"
        assert AgentStatus.FAILED == "failed"

    def test_from_string_value(self) -> None:
        assert AgentStatus("idle") is AgentStatus.IDLE
        assert AgentStatus("working") is AgentStatus.WORKING
        assert AgentStatus("failed") is AgentStatus.FAILED

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            AgentStatus("unknown")

    def test_repr_contains_value(self) -> None:
        assert "idle" in repr(AgentStatus.IDLE)


# ---------------------------------------------------------------------------
# SwarmTask dataclass
# ---------------------------------------------------------------------------


class TestSwarmTask:
    def test_default_id_is_uuid(self) -> None:
        task = SwarmTask()
        parsed = uuid.UUID(task.id)
        assert str(parsed) == task.id

    def test_each_instance_gets_unique_id(self) -> None:
        ids = {SwarmTask().id for _ in range(20)}
        assert len(ids) == 20

    def test_default_status_is_idle(self) -> None:
        task = SwarmTask()
        assert task.status is AgentStatus.IDLE

    def test_default_priority_is_zero(self) -> None:
        assert SwarmTask().priority == 0

    def test_default_timeout_is_300(self) -> None:
        assert SwarmTask().timeout_seconds == 300

    def test_default_result_is_none(self) -> None:
        task = SwarmTask()
        assert task.result is None
        assert task.error is None

    def test_default_assigned_agent_is_none(self) -> None:
        task = SwarmTask()
        assert task.assigned_agent is None

    def test_default_timestamps(self) -> None:
        task = SwarmTask()
        assert isinstance(task.created_at, datetime)
        assert task.started_at is None
        assert task.completed_at is None

    def test_created_at_is_utc_aware(self) -> None:
        task = SwarmTask()
        assert task.created_at.tzinfo is not None

    def test_default_context_is_empty_dict(self) -> None:
        task = SwarmTask()
        assert task.context == {}

    def test_context_instances_are_independent(self) -> None:
        t1 = SwarmTask()
        t2 = SwarmTask()
        t1.context["key"] = "value"
        assert "key" not in t2.context

    def test_default_artifacts_is_empty_list(self) -> None:
        task = SwarmTask()
        assert task.artifacts == []
        assert isinstance(task.artifacts, list)

    def test_artifact_lists_are_independent(self) -> None:
        t1 = SwarmTask()
        t2 = SwarmTask()
        t1.artifacts.append("file.txt")
        assert t2.artifacts == []

    def test_default_required_capabilities_is_empty_set(self) -> None:
        task = SwarmTask()
        assert task.required_capabilities == set()

    def test_custom_fields_are_stored(self) -> None:
        task = SwarmTask(
            description="Do the thing",
            original_request="User asked: do the thing",
            priority=5,
            timeout_seconds=120,
        )
        assert task.description == "Do the thing"
        assert task.original_request == "User asked: do the thing"
        assert task.priority == 5
        assert task.timeout_seconds == 120

    def test_status_mutation(self) -> None:
        task = SwarmTask()
        task.status = AgentStatus.WORKING
        assert task.status is AgentStatus.WORKING

    def test_result_mutation(self) -> None:
        task = SwarmTask()
        task.result = "done"
        assert task.result == "done"

    def test_preferred_agent_stored(self) -> None:
        task = SwarmTask(preferred_agent=AgentType.RESEARCHER)
        assert task.preferred_agent is AgentType.RESEARCHER

    def test_required_capabilities_stored(self) -> None:
        caps = {AgentCapability.RESEARCH, AgentCapability.WEB_SEARCH}
        task = SwarmTask(required_capabilities=caps)
        assert task.required_capabilities == caps


# ---------------------------------------------------------------------------
# SwarmResult dataclass
# ---------------------------------------------------------------------------


class TestSwarmResult:
    def test_required_fields_only(self) -> None:
        result = SwarmResult(task_id="abc-123", success=True)
        assert result.task_id == "abc-123"
        assert result.success is True

    def test_default_output_is_empty_string(self) -> None:
        result = SwarmResult(task_id="x", success=False)
        assert result.output == ""

    def test_default_summary_is_empty_string(self) -> None:
        result = SwarmResult(task_id="x", success=True)
        assert result.summary == ""

    def test_default_handoffs_performed_is_zero(self) -> None:
        result = SwarmResult(task_id="x", success=True)
        assert result.handoffs_performed == 0

    def test_default_duration_is_zero(self) -> None:
        result = SwarmResult(task_id="x", success=True)
        assert result.total_duration_seconds == 0.0

    def test_default_artifacts_is_empty_list(self) -> None:
        result = SwarmResult(task_id="x", success=True)
        assert result.artifacts == []

    def test_default_agents_used_is_empty_list(self) -> None:
        result = SwarmResult(task_id="x", success=True)
        assert result.agents_used == []

    def test_default_errors_is_empty_list(self) -> None:
        result = SwarmResult(task_id="x", success=True)
        assert result.errors == []

    def test_default_metadata_is_empty_dict(self) -> None:
        result = SwarmResult(task_id="x", success=True)
        assert result.metadata == {}

    def test_lists_are_independent_between_instances(self) -> None:
        r1 = SwarmResult(task_id="a", success=True)
        r2 = SwarmResult(task_id="b", success=True)
        r1.artifacts.append("chart.png")
        assert r2.artifacts == []

    def test_all_custom_fields(self) -> None:
        result = SwarmResult(
            task_id="task-1",
            success=True,
            output="Final answer",
            artifacts=["report.pdf"],
            summary="Completed research",
            agents_used=[AgentType.RESEARCHER, AgentType.WRITER],
            handoffs_performed=2,
            total_duration_seconds=45.3,
            errors=["minor warning"],
            metadata={"model": "gpt-4"},
        )
        assert result.task_id == "task-1"
        assert result.output == "Final answer"
        assert result.artifacts == ["report.pdf"]
        assert result.summary == "Completed research"
        assert result.agents_used == [AgentType.RESEARCHER, AgentType.WRITER]
        assert result.handoffs_performed == 2
        assert result.total_duration_seconds == 45.3
        assert result.errors == ["minor warning"]
        assert result.metadata == {"model": "gpt-4"}


# ---------------------------------------------------------------------------
# AgentInstance dataclass
# ---------------------------------------------------------------------------


class TestAgentInstance:
    def _make_spec(self) -> AgentSpec:
        return _make_minimal_spec()

    def test_required_fields(self) -> None:
        spec = self._make_spec()
        instance = AgentInstance(
            id="inst-1",
            agent_type=AgentType.RESEARCHER,
            spec=spec,
        )
        assert instance.id == "inst-1"
        assert instance.agent_type is AgentType.RESEARCHER
        assert instance.spec is spec

    def test_default_status_is_idle(self) -> None:
        spec = self._make_spec()
        instance = AgentInstance(id="i", agent_type=AgentType.CODER, spec=spec)
        assert instance.status is AgentStatus.IDLE

    def test_default_current_task_is_none(self) -> None:
        spec = self._make_spec()
        instance = AgentInstance(id="i", agent_type=AgentType.CODER, spec=spec)
        assert instance.current_task is None

    def test_default_agent_is_none(self) -> None:
        spec = self._make_spec()
        instance = AgentInstance(id="i", agent_type=AgentType.CODER, spec=spec)
        assert instance.agent is None

    def test_default_tasks_completed_is_zero(self) -> None:
        spec = self._make_spec()
        instance = AgentInstance(id="i", agent_type=AgentType.CODER, spec=spec)
        assert instance.tasks_completed == 0

    def test_created_at_is_utc_aware_datetime(self) -> None:
        spec = self._make_spec()
        instance = AgentInstance(id="i", agent_type=AgentType.CODER, spec=spec)
        assert isinstance(instance.created_at, datetime)
        assert instance.created_at.tzinfo is not None

    def test_status_mutation(self) -> None:
        spec = self._make_spec()
        instance = AgentInstance(id="i", agent_type=AgentType.CODER, spec=spec)
        instance.status = AgentStatus.WORKING
        assert instance.status is AgentStatus.WORKING

    def test_tasks_completed_increment(self) -> None:
        spec = self._make_spec()
        instance = AgentInstance(id="i", agent_type=AgentType.CODER, spec=spec)
        instance.tasks_completed += 1
        assert instance.tasks_completed == 1


# ---------------------------------------------------------------------------
# SwarmConfig Pydantic model
# ---------------------------------------------------------------------------


class TestSwarmConfig:
    def test_all_defaults(self) -> None:
        cfg = SwarmConfig()
        assert cfg.max_concurrent_agents == 3
        assert cfg.max_parallel_tasks == 5
        assert cfg.default_task_timeout == 300
        assert cfg.handoff_timeout == 60
        assert cfg.max_retries == 2
        assert cfg.retry_delay == 1.0
        assert cfg.max_total_tokens == 500000
        assert cfg.max_handoffs_per_task == 10
        assert cfg.enable_parallel_execution is True
        assert cfg.enable_auto_recovery is True
        assert cfg.enable_verification is True

    def test_custom_values_accepted(self) -> None:
        cfg = SwarmConfig(
            max_concurrent_agents=5,
            max_parallel_tasks=10,
            default_task_timeout=600,
            handoff_timeout=30,
            max_retries=3,
            retry_delay=2.5,
            max_total_tokens=1_000_000,
            max_handoffs_per_task=20,
            enable_parallel_execution=False,
            enable_auto_recovery=False,
            enable_verification=False,
        )
        assert cfg.max_concurrent_agents == 5
        assert cfg.max_parallel_tasks == 10
        assert cfg.default_task_timeout == 600
        assert cfg.handoff_timeout == 30
        assert cfg.max_retries == 3
        assert cfg.retry_delay == 2.5
        assert cfg.max_total_tokens == 1_000_000
        assert cfg.max_handoffs_per_task == 20
        assert cfg.enable_parallel_execution is False
        assert cfg.enable_auto_recovery is False
        assert cfg.enable_verification is False

    # --- Lower bound violations ---

    def test_max_concurrent_agents_min_is_one(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(max_concurrent_agents=0)

    def test_max_concurrent_agents_max_is_ten(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(max_concurrent_agents=11)

    def test_max_parallel_tasks_min_is_one(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(max_parallel_tasks=0)

    def test_max_parallel_tasks_max_is_twenty(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(max_parallel_tasks=21)

    def test_default_task_timeout_min_is_thirty(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(default_task_timeout=29)

    def test_handoff_timeout_min_is_ten(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(handoff_timeout=9)

    def test_max_retries_min_is_zero(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(max_retries=-1)

    def test_max_retries_max_is_five(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(max_retries=6)

    def test_retry_delay_min_is_zero(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(retry_delay=-0.1)

    def test_max_total_tokens_min_is_10000(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(max_total_tokens=9999)

    def test_max_handoffs_per_task_min_is_one(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(max_handoffs_per_task=0)

    def test_max_handoffs_per_task_max_is_fifty(self) -> None:
        with pytest.raises(ValidationError):
            SwarmConfig(max_handoffs_per_task=51)

    # --- Boundary values (accepted) ---

    def test_boundary_max_concurrent_agents_accepts_1_and_10(self) -> None:
        SwarmConfig(max_concurrent_agents=1)
        SwarmConfig(max_concurrent_agents=10)

    def test_boundary_max_parallel_tasks_accepts_1_and_20(self) -> None:
        SwarmConfig(max_parallel_tasks=1)
        SwarmConfig(max_parallel_tasks=20)

    def test_boundary_max_retries_accepts_0_and_5(self) -> None:
        SwarmConfig(max_retries=0)
        SwarmConfig(max_retries=5)

    def test_boundary_max_handoffs_accepts_1_and_50(self) -> None:
        SwarmConfig(max_handoffs_per_task=1)
        SwarmConfig(max_handoffs_per_task=50)

    def test_retry_delay_zero_is_valid(self) -> None:
        cfg = SwarmConfig(retry_delay=0)
        assert cfg.retry_delay == 0.0


# ---------------------------------------------------------------------------
# Swarm._AGENT_TYPE_MAP class variable
# ---------------------------------------------------------------------------


class TestAgentTypeMap:
    def test_all_expected_keys_present(self) -> None:
        expected_keys = {
            "researcher",
            "coder",
            "browser",
            "analyst",
            "writer",
            "verifier",
            "reviewer",
            "summarizer",
        }
        assert set(Swarm._AGENT_TYPE_MAP.keys()) == expected_keys

    def test_all_values_are_agent_type_instances(self) -> None:
        for key, value in Swarm._AGENT_TYPE_MAP.items():
            assert isinstance(value, AgentType), f"{key!r} maps to non-AgentType {value!r}"

    def test_researcher_maps_correctly(self) -> None:
        assert Swarm._AGENT_TYPE_MAP["researcher"] is AgentType.RESEARCHER

    def test_coder_maps_correctly(self) -> None:
        assert Swarm._AGENT_TYPE_MAP["coder"] is AgentType.CODER

    def test_browser_maps_correctly(self) -> None:
        assert Swarm._AGENT_TYPE_MAP["browser"] is AgentType.BROWSER

    def test_analyst_maps_correctly(self) -> None:
        assert Swarm._AGENT_TYPE_MAP["analyst"] is AgentType.ANALYST

    def test_writer_maps_correctly(self) -> None:
        assert Swarm._AGENT_TYPE_MAP["writer"] is AgentType.WRITER

    def test_verifier_maps_correctly(self) -> None:
        assert Swarm._AGENT_TYPE_MAP["verifier"] is AgentType.VERIFIER

    def test_reviewer_maps_correctly(self) -> None:
        assert Swarm._AGENT_TYPE_MAP["reviewer"] is AgentType.REVIEWER

    def test_summarizer_maps_correctly(self) -> None:
        assert Swarm._AGENT_TYPE_MAP["summarizer"] is AgentType.SUMMARIZER


# ---------------------------------------------------------------------------
# Swarm._build_agent_prompt
# ---------------------------------------------------------------------------


class TestBuildAgentPrompt:
    def _make_swarm_and_spec(self) -> tuple[Swarm, AgentSpec]:
        swarm = _make_swarm()
        spec = _make_minimal_spec()
        return swarm, spec

    def test_contains_system_prompt(self) -> None:
        swarm, spec = self._make_swarm_and_spec()
        task = SwarmTask(description="Find latest Python news")
        prompt = swarm._build_agent_prompt(task, spec, is_coordinator=False, handoff_context=None)
        assert spec.system_prompt_template in prompt

    def test_contains_task_description(self) -> None:
        swarm, spec = self._make_swarm_and_spec()
        task = SwarmTask(description="Analyze quarterly revenue data")
        prompt = swarm._build_agent_prompt(task, spec, is_coordinator=False, handoff_context=None)
        assert "Analyze quarterly revenue data" in prompt

    def test_contains_task_header(self) -> None:
        swarm, spec = self._make_swarm_and_spec()
        task = SwarmTask(description="Do X")
        prompt = swarm._build_agent_prompt(task, spec, is_coordinator=False, handoff_context=None)
        assert "## Task" in prompt

    def test_original_request_included_when_different_from_description(self) -> None:
        swarm, spec = self._make_swarm_and_spec()
        task = SwarmTask(
            description="Summarised description",
            original_request="Original user message that is different",
        )
        prompt = swarm._build_agent_prompt(task, spec, is_coordinator=False, handoff_context=None)
        assert "Original user message that is different" in prompt
        assert "Original Request" in prompt

    def test_original_request_omitted_when_same_as_description(self) -> None:
        swarm, spec = self._make_swarm_and_spec()
        task = SwarmTask(description="Same text", original_request="Same text")
        prompt = swarm._build_agent_prompt(task, spec, is_coordinator=False, handoff_context=None)
        assert "Original Request" not in prompt

    def test_original_request_omitted_when_empty(self) -> None:
        swarm, spec = self._make_swarm_and_spec()
        task = SwarmTask(description="Task desc", original_request="")
        prompt = swarm._build_agent_prompt(task, spec, is_coordinator=False, handoff_context=None)
        assert "Original Request" not in prompt

    def test_coordinator_block_absent_for_non_coordinator(self) -> None:
        swarm, spec = self._make_swarm_and_spec()
        task = SwarmTask(description="Do X")
        prompt = swarm._build_agent_prompt(task, spec, is_coordinator=False, handoff_context=None)
        assert "Delegation Guidelines" not in prompt
        assert "[HANDOFF]" not in prompt

    def test_coordinator_block_present_for_coordinator(self) -> None:
        swarm, spec = self._make_swarm_and_spec()
        task = SwarmTask(description="Coordinate work")
        prompt = swarm._build_agent_prompt(task, spec, is_coordinator=True, handoff_context=None)
        assert "Delegation Guidelines" in prompt
        assert "Researcher" in prompt
        assert "Coder" in prompt
        assert "handoff" in prompt

    def test_handoff_context_included_when_provided(self) -> None:
        swarm, spec = self._make_swarm_and_spec()
        task = SwarmTask(description="Continue research")
        ctx = HandoffContext(
            task_description="Research climate data",
            original_request="User request",
            current_progress="Found 5 sources",
        )
        prompt = swarm._build_agent_prompt(task, spec, is_coordinator=False, handoff_context=ctx)
        # HandoffContext.to_prompt() is expected to be included
        assert ctx.to_prompt() in prompt

    def test_returns_string(self) -> None:
        swarm, spec = self._make_swarm_and_spec()
        task = SwarmTask(description="Do X")
        result = swarm._build_agent_prompt(task, spec, is_coordinator=False, handoff_context=None)
        assert isinstance(result, str)

    def test_prompt_is_non_empty(self) -> None:
        swarm, spec = self._make_swarm_and_spec()
        task = SwarmTask(description="Do X")
        prompt = swarm._build_agent_prompt(task, spec, is_coordinator=False, handoff_context=None)
        assert len(prompt.strip()) > 0


# ---------------------------------------------------------------------------
# Swarm._detect_handoff_request — JSON path
# ---------------------------------------------------------------------------


class TestDetectHandoffRequestJsonPath:
    """Tests for the structured JSON parsing branch of _detect_handoff_request."""

    def setup_method(self) -> None:
        self.swarm = _make_swarm()
        self.task = SwarmTask(
            description="Do something",
            original_request="User prompt",
            assigned_agent=AgentType.COORDINATOR,
        )

    def test_valid_json_handoff_returns_handoff_object(self) -> None:
        message = '{"handoff": {"agent": "researcher", "task": "find info", "expected_output": "summary"}}'
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is not None

    def test_json_handoff_targets_correct_agent(self) -> None:
        message = '{"handoff": {"agent": "coder", "task": "write a script", "expected_output": "Python file"}}'
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is not None
        assert result.target_agent is AgentType.CODER

    @pytest.mark.parametrize(
        "agent_name, expected_type",
        [
            ("researcher", AgentType.RESEARCHER),
            ("coder", AgentType.CODER),
            ("browser", AgentType.BROWSER),
            ("analyst", AgentType.ANALYST),
            ("writer", AgentType.WRITER),
            ("verifier", AgentType.VERIFIER),
            ("reviewer", AgentType.REVIEWER),
            ("summarizer", AgentType.SUMMARIZER),
        ],
    )
    def test_json_path_all_known_agent_names(self, agent_name: str, expected_type: AgentType) -> None:
        message = f'{{"handoff": {{"agent": "{agent_name}", "task": "do work", "expected_output": "result"}}}}'
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is not None
        assert result.target_agent is expected_type

    def test_json_with_unknown_agent_returns_none(self) -> None:
        message = '{"handoff": {"agent": "unknown_agent_xyz", "task": "do work"}}'
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is None

    def test_json_nested_in_text_is_parsed(self) -> None:
        message = 'I will delegate this.\n{"handoff": {"agent": "writer", "task": "draft report"}}\nDone.'
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is not None
        assert result.target_agent is AgentType.WRITER

    def test_malformed_json_falls_through_to_regex(self) -> None:
        # Has "handoff" keyword but invalid JSON — should fall through to regex (and return None)
        message = '"handoff" = { broken json }'
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is None

    def test_message_without_handoff_keyword_returns_none(self) -> None:
        message = "Just a normal response with no delegation needed."
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is None

    def test_empty_message_returns_none(self) -> None:
        result = self.swarm._detect_handoff_request("", self.task)
        assert result is None

    def test_agent_name_case_insensitive_via_lower(self) -> None:
        # The code does .lower() on agent_name, so "RESEARCHER" should map correctly
        message = '{"handoff": {"agent": "RESEARCHER", "task": "research"}}'
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is not None
        assert result.target_agent is AgentType.RESEARCHER


# ---------------------------------------------------------------------------
# Swarm._detect_handoff_request — regex/marker fallback path
# ---------------------------------------------------------------------------


class TestDetectHandoffRequestRegexPath:
    """Tests for the [HANDOFF]...[/HANDOFF] marker parsing branch."""

    def setup_method(self) -> None:
        self.swarm = _make_swarm()
        self.task = SwarmTask(
            description="Do research",
            original_request="Research the topic",
            assigned_agent=AgentType.COORDINATOR,
        )

    def test_valid_marker_returns_handoff(self) -> None:
        message = "[HANDOFF]\nagent: researcher\ntask: gather data\nexpected_output: summary\n[/HANDOFF]"
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is not None

    def test_marker_targets_correct_agent(self) -> None:
        message = "[HANDOFF]\nagent: coder\ntask: write tests\nexpected_output: pytest file\n[/HANDOFF]"
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is not None
        assert result.target_agent is AgentType.CODER

    @pytest.mark.parametrize(
        "agent_name, expected_type",
        [
            ("researcher", AgentType.RESEARCHER),
            ("coder", AgentType.CODER),
            ("browser", AgentType.BROWSER),
            ("analyst", AgentType.ANALYST),
            ("writer", AgentType.WRITER),
            ("verifier", AgentType.VERIFIER),
            ("reviewer", AgentType.REVIEWER),
            ("summarizer", AgentType.SUMMARIZER),
        ],
    )
    def test_marker_path_all_known_agent_names(self, agent_name: str, expected_type: AgentType) -> None:
        message = f"[HANDOFF]\nagent: {agent_name}\ntask: do work\nexpected_output: result\n[/HANDOFF]"
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is not None
        assert result.target_agent is expected_type

    def test_marker_with_unknown_agent_returns_none(self) -> None:
        message = "[HANDOFF]\nagent: unknown_bot\ntask: do work\n[/HANDOFF]"
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is None

    def test_marker_embedded_in_prose_is_detected(self) -> None:
        message = (
            "I've analysed the situation.\n"
            "[HANDOFF]\nagent: writer\ntask: draft the executive summary\n[/HANDOFF]\n"
            "Please proceed."
        )
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is not None
        assert result.target_agent is AgentType.WRITER

    def test_unclosed_marker_returns_none(self) -> None:
        message = "[HANDOFF]\nagent: researcher\ntask: find info"
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is None

    def test_marker_without_agent_field_returns_none(self) -> None:
        message = "[HANDOFF]\ntask: do something\nexpected_output: result\n[/HANDOFF]"
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is None

    def test_marker_case_insensitive_agent_name(self) -> None:
        message = "[HANDOFF]\nagent: ANALYST\ntask: compute stats\n[/HANDOFF]"
        result = self.swarm._detect_handoff_request(message, self.task)
        assert result is not None
        assert result.target_agent is AgentType.ANALYST


# ---------------------------------------------------------------------------
# Swarm._parse_structured_handoff
# ---------------------------------------------------------------------------


class TestParseStructuredHandoff:
    """Unit tests for the internal _parse_structured_handoff helper."""

    def setup_method(self) -> None:
        self.swarm = _make_swarm()
        self.task = SwarmTask(description="Base task", original_request="Request")

    def test_nested_handoff_key_parsed(self) -> None:
        data = {"handoff": {"agent": "researcher", "task": "deep dive", "expected_output": "report"}}
        result = self.swarm._parse_structured_handoff(data, self.task)
        assert result is not None
        assert result.target_agent is AgentType.RESEARCHER

    def test_flat_dict_without_handoff_key_still_parsed(self) -> None:
        # data.get("handoff", data) falls back to entire dict
        data = {"agent": "writer", "task": "draft article"}
        result = self.swarm._parse_structured_handoff(data, self.task)
        assert result is not None
        assert result.target_agent is AgentType.WRITER

    def test_unknown_agent_returns_none(self) -> None:
        data = {"handoff": {"agent": "unknown_agent", "task": "do stuff"}}
        result = self.swarm._parse_structured_handoff(data, self.task)
        assert result is None

    def test_missing_agent_key_returns_none(self) -> None:
        data = {"handoff": {"task": "do stuff"}}
        result = self.swarm._parse_structured_handoff(data, self.task)
        assert result is None

    def test_task_desc_falls_back_to_task_description(self) -> None:
        data = {"handoff": {"agent": "analyst"}}  # no "task" key
        result = self.swarm._parse_structured_handoff(data, self.task)
        assert result is not None
        # HandoffContext should have captured task.description as fallback
        assert result.context is not None
        assert self.task.description in result.context.task_description


# ---------------------------------------------------------------------------
# Swarm.get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    def test_initial_stats_are_zero(self) -> None:
        swarm = _make_swarm()
        stats = swarm.get_stats()
        assert stats["active_agents"] == 0
        assert stats["total_agents"] == 0
        assert stats["active_tasks"] == 0
        assert stats["tasks_completed"] == 0
        assert stats["total_handoffs"] == 0
        assert stats["total_errors"] == 0

    def test_agents_by_type_empty_when_no_agents(self) -> None:
        swarm = _make_swarm()
        assert swarm.get_stats()["agents_by_type"] == {}

    def test_total_agents_reflects_internal_state(self) -> None:
        swarm = _make_swarm()
        spec = _make_minimal_spec()
        inst = AgentInstance(id="a1", agent_type=AgentType.RESEARCHER, spec=spec)
        swarm._agents["a1"] = inst
        stats = swarm.get_stats()
        assert stats["total_agents"] == 1

    def test_active_agents_counts_only_working_status(self) -> None:
        swarm = _make_swarm()
        spec = _make_minimal_spec()
        idle_inst = AgentInstance(id="idle-1", agent_type=AgentType.RESEARCHER, spec=spec)
        working_inst = AgentInstance(
            id="work-1",
            agent_type=AgentType.CODER,
            spec=spec,
            status=AgentStatus.WORKING,
        )
        swarm._agents["idle-1"] = idle_inst
        swarm._agents["work-1"] = working_inst
        stats = swarm.get_stats()
        assert stats["active_agents"] == 1
        assert stats["total_agents"] == 2

    def test_agents_by_type_groups_correctly(self) -> None:
        swarm = _make_swarm()
        researcher_spec = AgentSpec(
            agent_type=AgentType.RESEARCHER,
            name="R",
            description="d",
            capabilities={AgentCapability.RESEARCH},
            tools=[],
            system_prompt_template="",
        )
        coder_spec = AgentSpec(
            agent_type=AgentType.CODER,
            name="C",
            description="d",
            capabilities={AgentCapability.CODE_WRITING},
            tools=[],
            system_prompt_template="",
        )
        swarm._agents["r1"] = AgentInstance(id="r1", agent_type=AgentType.RESEARCHER, spec=researcher_spec)
        swarm._agents["r2"] = AgentInstance(id="r2", agent_type=AgentType.RESEARCHER, spec=researcher_spec)
        swarm._agents["c1"] = AgentInstance(id="c1", agent_type=AgentType.CODER, spec=coder_spec)
        stats = swarm.get_stats()
        assert stats["agents_by_type"]["researcher"] == 2
        assert stats["agents_by_type"]["coder"] == 1

    def test_tasks_completed_reflects_internal_counter(self) -> None:
        swarm = _make_swarm()
        swarm._total_tasks_completed = 7
        assert swarm.get_stats()["tasks_completed"] == 7

    def test_total_handoffs_reflects_internal_counter(self) -> None:
        swarm = _make_swarm()
        swarm._total_handoffs = 3
        assert swarm.get_stats()["total_handoffs"] == 3

    def test_total_errors_reflects_internal_counter(self) -> None:
        swarm = _make_swarm()
        swarm._total_errors = 2
        assert swarm.get_stats()["total_errors"] == 2

    def test_active_tasks_reflects_internal_dict(self) -> None:
        swarm = _make_swarm()
        task = SwarmTask(description="Running")
        swarm._active_tasks[task.id] = task
        assert swarm.get_stats()["active_tasks"] == 1

    def test_get_stats_returns_dict(self) -> None:
        swarm = _make_swarm()
        assert isinstance(swarm.get_stats(), dict)

    def test_get_stats_required_keys_present(self) -> None:
        swarm = _make_swarm()
        required = {
            "active_agents",
            "total_agents",
            "active_tasks",
            "tasks_completed",
            "total_handoffs",
            "total_errors",
            "agents_by_type",
        }
        assert required.issubset(swarm.get_stats().keys())
