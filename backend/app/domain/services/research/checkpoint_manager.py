"""Checkpoint management for phased research flows."""

from __future__ import annotations

from collections import defaultdict

from app.domain.models.event import CheckpointSavedEvent
from app.domain.models.research_phase import ResearchCheckpoint, ResearchPhase


class ResearchCheckpointManager:
    """Stores and retrieves phase checkpoints for a session."""

    def __init__(self):
        self._storage: dict[str, list[ResearchCheckpoint]] = defaultdict(list)

    async def save_checkpoint(
        self,
        session_id: str,
        phase: ResearchPhase,
        notes: str,
        sources: list[str],
        research_id: str | None = None,
    ) -> tuple[ResearchCheckpoint, CheckpointSavedEvent]:
        checkpoint = ResearchCheckpoint(
            phase=phase,
            notes=notes,
            sources=sources,
            query_context=self._infer_context(phase),
        )
        self._storage[session_id].append(checkpoint)

        event = CheckpointSavedEvent(
            phase=phase.value,
            research_id=research_id,
            notes_preview=(notes[:200] + "...") if len(notes) > 200 else notes,
            source_count=len(sources),
        )
        return checkpoint, event

    async def retrieve_all_checkpoints(self, session_id: str) -> list[ResearchCheckpoint]:
        return list(self._storage.get(session_id, []))

    async def clear(self, session_id: str) -> None:
        self._storage.pop(session_id, None)

    @staticmethod
    def _infer_context(phase: ResearchPhase) -> str:
        mapping = {
            ResearchPhase.PHASE_1_FUNDAMENTALS: "What is it and how does it work?",
            ResearchPhase.PHASE_2_USE_CASES: "How is it used in real scenarios?",
            ResearchPhase.PHASE_3_BEST_PRACTICES: "What are advanced patterns and risks?",
            ResearchPhase.COMPILATION: "How do findings synthesize into recommendations?",
        }
        return mapping.get(phase, "General research")
