"""Tests for collaboration pattern data models.

Tests cover:
- PatternType enum — all 4 members, string values, str mixin behaviour
- CollaborationContext dataclass — required fields, defaults, auto timestamp
- CollaborationResult dataclass — required fields, defaults, success/failure states,
  participant_contributions, metadata storage
"""

from datetime import UTC, datetime

import pytest

from app.domain.services.agents.collaboration.patterns import (
    CollaborationContext,
    CollaborationResult,
    PatternType,
)

# ── PatternType Enum ─────────────────────────────────────────────────


class TestPatternType:
    def test_debate_value(self):
        assert PatternType.DEBATE == "debate"

    def test_assembly_line_value(self):
        assert PatternType.ASSEMBLY_LINE == "assembly_line"

    def test_swarm_value(self):
        assert PatternType.SWARM == "swarm"

    def test_mentor_student_value(self):
        assert PatternType.MENTOR_STUDENT == "mentor_student"

    def test_member_count(self):
        assert len(PatternType) == 4

    def test_all_members_present(self):
        names = {m.name for m in PatternType}
        assert names == {"DEBATE", "ASSEMBLY_LINE", "SWARM", "MENTOR_STUDENT"}

    def test_str_mixin_equality(self):
        # PatternType inherits from str, so direct string comparison works.
        assert PatternType.DEBATE == "debate"
        assert PatternType.SWARM == "swarm"

    def test_lookup_by_value(self):
        assert PatternType("debate") is PatternType.DEBATE
        assert PatternType("assembly_line") is PatternType.ASSEMBLY_LINE

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            PatternType("unknown_pattern")


# ── CollaborationContext Dataclass ───────────────────────────────────


class TestCollaborationContext:
    def test_construction_with_required_fields(self):
        ctx = CollaborationContext(
            session_id="sess-001",
            pattern_type=PatternType.DEBATE,
            task_description="Compare approach A vs B",
        )
        assert ctx.session_id == "sess-001"
        assert ctx.pattern_type == PatternType.DEBATE
        assert ctx.task_description == "Compare approach A vs B"

    def test_participants_default_empty_list(self):
        ctx = CollaborationContext(
            session_id="sess-002",
            pattern_type=PatternType.SWARM,
            task_description="Explore the problem space",
        )
        assert ctx.participants == []

    def test_metadata_default_empty_dict(self):
        ctx = CollaborationContext(
            session_id="sess-003",
            pattern_type=PatternType.ASSEMBLY_LINE,
            task_description="Build the feature",
        )
        assert ctx.metadata == {}

    def test_created_at_is_auto_set(self):
        before = datetime.now(UTC)
        ctx = CollaborationContext(
            session_id="sess-004",
            pattern_type=PatternType.MENTOR_STUDENT,
            task_description="Learn something",
        )
        after = datetime.now(UTC)
        assert before <= ctx.created_at <= after

    def test_created_at_is_timezone_aware(self):
        ctx = CollaborationContext(
            session_id="sess-005",
            pattern_type=PatternType.DEBATE,
            task_description="Analyse options",
        )
        assert ctx.created_at.tzinfo is not None

    def test_participants_populated(self):
        ctx = CollaborationContext(
            session_id="sess-006",
            pattern_type=PatternType.SWARM,
            task_description="Parallel research",
            participants=["agent-a", "agent-b", "agent-c"],
        )
        assert ctx.participants == ["agent-a", "agent-b", "agent-c"]

    def test_metadata_populated(self):
        ctx = CollaborationContext(
            session_id="sess-007",
            pattern_type=PatternType.DEBATE,
            task_description="Decide on DB engine",
            metadata={"priority": "high", "requester": "user-42"},
        )
        assert ctx.metadata["priority"] == "high"
        assert ctx.metadata["requester"] == "user-42"

    def test_participants_lists_are_independent_across_instances(self):
        # Ensure default_factory produces a new list per instance.
        ctx_a = CollaborationContext(
            session_id="a",
            pattern_type=PatternType.SWARM,
            task_description="Task A",
        )
        ctx_b = CollaborationContext(
            session_id="b",
            pattern_type=PatternType.SWARM,
            task_description="Task B",
        )
        ctx_a.participants.append("agent-x")
        assert ctx_b.participants == []

    def test_metadata_dicts_are_independent_across_instances(self):
        ctx_a = CollaborationContext(
            session_id="a",
            pattern_type=PatternType.DEBATE,
            task_description="Task A",
        )
        ctx_b = CollaborationContext(
            session_id="b",
            pattern_type=PatternType.DEBATE,
            task_description="Task B",
        )
        ctx_a.metadata["key"] = "value"
        assert "key" not in ctx_b.metadata

    def test_pattern_type_stored_correctly_for_all_variants(self):
        for pt in PatternType:
            ctx = CollaborationContext(
                session_id=f"sess-{pt.value}",
                pattern_type=pt,
                task_description="Generic task",
            )
            assert ctx.pattern_type is pt


# ── CollaborationResult Dataclass ────────────────────────────────────


class TestCollaborationResult:
    def test_construction_with_required_fields_only(self):
        result = CollaborationResult(
            session_id="sess-100",
            pattern_type=PatternType.DEBATE,
            success=True,
        )
        assert result.session_id == "sess-100"
        assert result.pattern_type == PatternType.DEBATE
        assert result.success is True

    def test_final_output_default_none(self):
        result = CollaborationResult(
            session_id="sess-101",
            pattern_type=PatternType.SWARM,
            success=True,
        )
        assert result.final_output is None

    def test_consensus_reached_default_false(self):
        result = CollaborationResult(
            session_id="sess-102",
            pattern_type=PatternType.DEBATE,
            success=True,
        )
        assert result.consensus_reached is False

    def test_participant_contributions_default_empty_dict(self):
        result = CollaborationResult(
            session_id="sess-103",
            pattern_type=PatternType.ASSEMBLY_LINE,
            success=True,
        )
        assert result.participant_contributions == {}

    def test_synthesis_default_none(self):
        result = CollaborationResult(
            session_id="sess-104",
            pattern_type=PatternType.MENTOR_STUDENT,
            success=True,
        )
        assert result.synthesis is None

    def test_confidence_default_zero(self):
        result = CollaborationResult(
            session_id="sess-105",
            pattern_type=PatternType.SWARM,
            success=True,
        )
        assert result.confidence == 0.0

    def test_duration_ms_default_zero(self):
        result = CollaborationResult(
            session_id="sess-106",
            pattern_type=PatternType.ASSEMBLY_LINE,
            success=True,
        )
        assert result.duration_ms == 0.0

    def test_metadata_default_empty_dict(self):
        result = CollaborationResult(
            session_id="sess-107",
            pattern_type=PatternType.DEBATE,
            success=True,
        )
        assert result.metadata == {}

    def test_success_state_true(self):
        result = CollaborationResult(
            session_id="sess-200",
            pattern_type=PatternType.DEBATE,
            success=True,
            final_output="Synthesis complete.",
            consensus_reached=True,
            confidence=0.9,
        )
        assert result.success is True
        assert result.consensus_reached is True
        assert result.final_output == "Synthesis complete."
        assert result.confidence == 0.9

    def test_failure_state(self):
        result = CollaborationResult(
            session_id="sess-201",
            pattern_type=PatternType.SWARM,
            success=False,
            final_output=None,
        )
        assert result.success is False
        assert result.final_output is None

    def test_participant_contributions_populated(self):
        result = CollaborationResult(
            session_id="sess-202",
            pattern_type=PatternType.DEBATE,
            success=True,
            participant_contributions={
                "agent-a": "Argument for position A",
                "agent-b": "Argument for position B",
            },
        )
        assert result.participant_contributions["agent-a"] == "Argument for position A"
        assert result.participant_contributions["agent-b"] == "Argument for position B"
        assert len(result.participant_contributions) == 2

    def test_metadata_storage(self):
        result = CollaborationResult(
            session_id="sess-203",
            pattern_type=PatternType.ASSEMBLY_LINE,
            success=True,
            metadata={"stages_completed": 3, "pipeline": "v2"},
        )
        assert result.metadata["stages_completed"] == 3
        assert result.metadata["pipeline"] == "v2"

    def test_synthesis_and_final_output_stored(self):
        synthesis_text = "Debate concluded: approach A wins on cost, B on speed."
        result = CollaborationResult(
            session_id="sess-204",
            pattern_type=PatternType.DEBATE,
            success=True,
            final_output=synthesis_text,
            synthesis=synthesis_text,
        )
        assert result.synthesis == synthesis_text
        assert result.final_output == synthesis_text

    def test_duration_ms_stored(self):
        result = CollaborationResult(
            session_id="sess-205",
            pattern_type=PatternType.SWARM,
            success=True,
            duration_ms=1234.56,
        )
        assert result.duration_ms == 1234.56

    def test_participant_contributions_dicts_are_independent(self):
        # Verify default_factory isolation across instances.
        r1 = CollaborationResult(
            session_id="r1",
            pattern_type=PatternType.MENTOR_STUDENT,
            success=True,
        )
        r2 = CollaborationResult(
            session_id="r2",
            pattern_type=PatternType.MENTOR_STUDENT,
            success=True,
        )
        r1.participant_contributions["agent-x"] = "contribution"
        assert "agent-x" not in r2.participant_contributions

    def test_pattern_type_preserved_on_result(self):
        for pt in PatternType:
            result = CollaborationResult(
                session_id=f"res-{pt.value}",
                pattern_type=pt,
                success=True,
            )
            assert result.pattern_type is pt
