"""Tests for ResearchPhase enum, ResearchCheckpoint, and ResearchState models."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

import pytest
from pydantic import ValidationError

from app.domain.models.research_phase import (
    ResearchCheckpoint,
    ResearchPhase,
    ResearchState,
)


@pytest.mark.unit
class TestResearchPhaseEnum:
    def test_all_four_values_exist(self) -> None:
        assert ResearchPhase.PHASE_1_FUNDAMENTALS.value == "phase_1"
        assert ResearchPhase.PHASE_2_USE_CASES.value == "phase_2"
        assert ResearchPhase.PHASE_3_BEST_PRACTICES.value == "phase_3"
        assert ResearchPhase.COMPILATION.value == "compilation"

    def test_exact_member_count(self) -> None:
        assert len(ResearchPhase) == 4

    def test_is_str_enum(self) -> None:
        assert isinstance(ResearchPhase.PHASE_1_FUNDAMENTALS, str)
        assert ResearchPhase.PHASE_2_USE_CASES == "phase_2"

    def test_lookup_by_value(self) -> None:
        assert ResearchPhase("phase_1") is ResearchPhase.PHASE_1_FUNDAMENTALS
        assert ResearchPhase("phase_3") is ResearchPhase.PHASE_3_BEST_PRACTICES
        assert ResearchPhase("compilation") is ResearchPhase.COMPILATION

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            ResearchPhase("phase_9")

    def test_all_phases_are_strings(self) -> None:
        for phase in ResearchPhase:
            assert isinstance(phase.value, str)


@pytest.mark.unit
class TestResearchCheckpoint:
    def test_required_fields(self) -> None:
        cp = ResearchCheckpoint(
            phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
            notes="Initial findings on fundamentals",
            query_context="What is X?",
        )
        assert cp.phase is ResearchPhase.PHASE_1_FUNDAMENTALS
        assert cp.notes == "Initial findings on fundamentals"
        assert cp.query_context == "What is X?"

    def test_sources_default_empty_list(self) -> None:
        cp = ResearchCheckpoint(
            phase=ResearchPhase.PHASE_2_USE_CASES,
            notes="Use cases noted",
            query_context="examples of X",
        )
        assert cp.sources == []

    def test_sources_provided(self) -> None:
        cp = ResearchCheckpoint(
            phase=ResearchPhase.PHASE_3_BEST_PRACTICES,
            notes="Best practice summary",
            sources=["https://example.com", "https://docs.example.org"],
            query_context="best practices for X",
        )
        assert len(cp.sources) == 2
        assert any(urlparse(url).netloc == "example.com" for url in cp.sources)

    def test_timestamp_default_is_utc_aware(self) -> None:
        cp = ResearchCheckpoint(
            phase=ResearchPhase.COMPILATION,
            notes="Compilation notes",
            query_context="compile all findings",
        )
        assert cp.timestamp.tzinfo is not None
        assert cp.timestamp.tzinfo == UTC

    def test_timestamp_explicit(self) -> None:
        t = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
        cp = ResearchCheckpoint(
            phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
            notes="Notes",
            query_context="context",
            timestamp=t,
        )
        assert cp.timestamp == t

    def test_missing_notes_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResearchCheckpoint(  # type: ignore[call-arg]
                phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
                query_context="context",
            )

    def test_missing_phase_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResearchCheckpoint(  # type: ignore[call-arg]
                notes="Some notes",
                query_context="context",
            )

    def test_missing_query_context_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResearchCheckpoint(  # type: ignore[call-arg]
                phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
                notes="Some notes",
            )

    def test_sources_lists_are_independent(self) -> None:
        cp1 = ResearchCheckpoint(
            phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
            notes="n1",
            query_context="q1",
        )
        cp2 = ResearchCheckpoint(
            phase=ResearchPhase.PHASE_2_USE_CASES,
            notes="n2",
            query_context="q2",
        )
        cp1.sources.append("https://source.com")
        assert cp2.sources == []

    def test_serialization_roundtrip(self) -> None:
        t = datetime(2026, 3, 1, 9, 0, 0, tzinfo=UTC)
        cp = ResearchCheckpoint(
            phase=ResearchPhase.PHASE_2_USE_CASES,
            notes="Use case notes",
            sources=["https://example.com"],
            query_context="use cases of X",
            timestamp=t,
        )
        data = cp.model_dump()
        cp2 = ResearchCheckpoint.model_validate(data)
        assert cp2.phase is ResearchPhase.PHASE_2_USE_CASES
        assert cp2.notes == cp.notes
        assert cp2.sources == cp.sources
        assert cp2.query_context == cp.query_context

    def test_phase_coercion_from_string(self) -> None:
        cp = ResearchCheckpoint(
            phase="phase_3",  # type: ignore[arg-type]
            notes="Notes",
            query_context="q",
        )
        assert cp.phase is ResearchPhase.PHASE_3_BEST_PRACTICES


@pytest.mark.unit
class TestResearchState:
    def test_required_field_only(self) -> None:
        state = ResearchState(current_phase=ResearchPhase.PHASE_1_FUNDAMENTALS)
        assert state.current_phase is ResearchPhase.PHASE_1_FUNDAMENTALS

    def test_defaults(self) -> None:
        state = ResearchState(current_phase=ResearchPhase.PHASE_1_FUNDAMENTALS)
        assert state.checkpoints == []
        assert state.action_count == 0
        assert state.last_reflection is None
        assert state.next_step is None

    def test_action_count_explicit(self) -> None:
        state = ResearchState(
            current_phase=ResearchPhase.PHASE_2_USE_CASES,
            action_count=7,
        )
        assert state.action_count == 7

    def test_last_reflection_set(self) -> None:
        state = ResearchState(
            current_phase=ResearchPhase.PHASE_3_BEST_PRACTICES,
            last_reflection="Found sufficient evidence.",
        )
        assert state.last_reflection == "Found sufficient evidence."

    def test_next_step_set(self) -> None:
        state = ResearchState(
            current_phase=ResearchPhase.COMPILATION,
            next_step="Compile all gathered notes.",
        )
        assert state.next_step == "Compile all gathered notes."

    def test_checkpoints_attached(self) -> None:
        cp = ResearchCheckpoint(
            phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
            notes="Checkpoint notes",
            query_context="initial query",
        )
        state = ResearchState(
            current_phase=ResearchPhase.PHASE_2_USE_CASES,
            checkpoints=[cp],
        )
        assert len(state.checkpoints) == 1
        assert state.checkpoints[0].phase is ResearchPhase.PHASE_1_FUNDAMENTALS

    def test_state_progression(self) -> None:
        state = ResearchState(current_phase=ResearchPhase.PHASE_1_FUNDAMENTALS)
        assert state.current_phase == "phase_1"

        cp = ResearchCheckpoint(
            phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
            notes="Phase 1 complete",
            query_context="fundamentals query",
        )
        state.checkpoints.append(cp)
        state.action_count += 3
        state.current_phase = ResearchPhase.PHASE_2_USE_CASES

        assert state.current_phase is ResearchPhase.PHASE_2_USE_CASES
        assert state.action_count == 3
        assert len(state.checkpoints) == 1

    def test_missing_current_phase_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResearchState()  # type: ignore[call-arg]

    def test_checkpoints_lists_are_independent(self) -> None:
        s1 = ResearchState(current_phase=ResearchPhase.PHASE_1_FUNDAMENTALS)
        s2 = ResearchState(current_phase=ResearchPhase.PHASE_2_USE_CASES)
        s1.checkpoints.append(
            ResearchCheckpoint(
                phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
                notes="n",
                query_context="q",
            )
        )
        assert s2.checkpoints == []

    def test_serialization_roundtrip(self) -> None:
        cp = ResearchCheckpoint(
            phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
            notes="Fundamentals complete",
            sources=["https://ref.example.com"],
            query_context="fundamentals of X",
        )
        state = ResearchState(
            current_phase=ResearchPhase.COMPILATION,
            checkpoints=[cp],
            action_count=12,
            last_reflection="All phases done.",
            next_step="Write final report.",
        )
        data = state.model_dump()
        state2 = ResearchState.model_validate(data)
        assert state2.current_phase is ResearchPhase.COMPILATION
        assert state2.action_count == 12
        assert state2.last_reflection == "All phases done."
        assert state2.next_step == "Write final report."
        assert len(state2.checkpoints) == 1
        assert state2.checkpoints[0].phase is ResearchPhase.PHASE_1_FUNDAMENTALS

    def test_current_phase_coercion_from_string(self) -> None:
        state = ResearchState(current_phase="compilation")  # type: ignore[arg-type]
        assert state.current_phase is ResearchPhase.COMPILATION
