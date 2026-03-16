"""Tests for phased research checkpoint manager."""

import pytest

from app.domain.models.research_phase import ResearchPhase
from app.domain.services.research.checkpoint_manager import ResearchCheckpointManager


@pytest.mark.asyncio
async def test_save_checkpoint_creates_event_with_preview_and_source_count():
    manager = ResearchCheckpointManager()

    notes = "A" * 250
    checkpoint, event = await manager.save_checkpoint(
        session_id="session-1",
        phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
        notes=notes,
        sources=["https://a.com", "https://b.com"],
        research_id="research-1",
    )

    assert checkpoint.phase == ResearchPhase.PHASE_1_FUNDAMENTALS
    assert checkpoint.query_context
    assert event.type == "checkpoint_saved"
    assert event.phase == "phase_1"
    assert event.source_count == 2
    assert event.notes_preview is not None
    assert event.notes_preview.endswith("...")


@pytest.mark.asyncio
async def test_retrieve_all_checkpoints_is_scoped_per_session():
    manager = ResearchCheckpointManager()

    await manager.save_checkpoint(
        session_id="session-1",
        phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
        notes="notes-1",
        sources=[],
    )
    await manager.save_checkpoint(
        session_id="session-2",
        phase=ResearchPhase.PHASE_2_USE_CASES,
        notes="notes-2",
        sources=["https://x.dev"],
    )

    session_1 = await manager.retrieve_all_checkpoints("session-1")
    session_2 = await manager.retrieve_all_checkpoints("session-2")

    assert len(session_1) == 1
    assert session_1[0].notes == "notes-1"
    assert len(session_2) == 1
    assert session_2[0].phase == ResearchPhase.PHASE_2_USE_CASES
