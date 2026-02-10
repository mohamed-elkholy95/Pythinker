"""Phased research flow with checkpointing and phase transitions."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from app.domain.external.search import SearchEngine
from app.domain.models.event import (
    BaseEvent,
    PhaseTransitionEvent,
    ReportEvent,
)
from app.domain.models.research_phase import ResearchCheckpoint, ResearchPhase
from app.domain.services.research.checkpoint_manager import ResearchCheckpointManager


class PhasedResearchFlow:
    """Executes research through explicit phases and emits progress events."""

    def __init__(
        self,
        search_engine: SearchEngine,
        session_id: str,
        checkpoint_manager: ResearchCheckpointManager | None = None,
    ):
        self.search_engine = search_engine
        self.session_id = session_id
        self.checkpoint_manager = checkpoint_manager or ResearchCheckpointManager()

        self._phase_query_suffix: dict[ResearchPhase, str] = {
            ResearchPhase.PHASE_1_FUNDAMENTALS: "overview fundamentals setup",
            ResearchPhase.PHASE_2_USE_CASES: "practical use cases examples",
            ResearchPhase.PHASE_3_BEST_PRACTICES: "best practices pitfalls advanced patterns",
        }

    async def run(self, query: str) -> AsyncGenerator[BaseEvent, None]:
        research_id = str(uuid.uuid4())[:12]

        for phase in (
            ResearchPhase.PHASE_1_FUNDAMENTALS,
            ResearchPhase.PHASE_2_USE_CASES,
            ResearchPhase.PHASE_3_BEST_PRACTICES,
        ):
            yield self._phase_transition(phase, research_id)

            search_query = f"{query} {self._phase_query_suffix[phase]}".strip()
            search_result = await self.search_engine.search(search_query)
            notes, sources = self._build_notes(search_query, search_result)

            _, checkpoint_event = await self.checkpoint_manager.save_checkpoint(
                session_id=self.session_id,
                phase=phase,
                notes=notes,
                sources=sources,
                research_id=research_id,
            )
            yield checkpoint_event

        yield self._phase_transition(ResearchPhase.COMPILATION, research_id)
        checkpoints = await self.checkpoint_manager.retrieve_all_checkpoints(self.session_id)
        yield self._build_report(query, checkpoints, research_id)
        yield PhaseTransitionEvent(
            phase="completed",
            label="Completed",
            research_id=research_id,
            source="deep_research",
        )

    @staticmethod
    def _phase_transition(phase: ResearchPhase, research_id: str) -> PhaseTransitionEvent:
        label_map = {
            ResearchPhase.PHASE_1_FUNDAMENTALS: "Phase 1: Fundamentals",
            ResearchPhase.PHASE_2_USE_CASES: "Phase 2: Use Cases",
            ResearchPhase.PHASE_3_BEST_PRACTICES: "Phase 3: Best Practices",
            ResearchPhase.COMPILATION: "Compiling final report",
        }
        return PhaseTransitionEvent(
            phase=phase.value,
            label=label_map[phase],
            research_id=research_id,
            source="deep_research",
        )

    @staticmethod
    def _build_notes(search_query: str, search_result) -> tuple[str, list[str]]:
        if not search_result or not search_result.success or not search_result.data:
            message = getattr(search_result, "message", "Search failed")
            return f"Query: {search_query}\nOutcome: {message}", []

        data = search_result.data
        lines = [f"Query: {search_query}"]
        sources: list[str] = []

        for item in data.results[:5]:
            lines.append(f"- {item.title}: {item.snippet}")
            sources.append(item.link)

        if len(lines) == 1:
            lines.append("- No concrete results returned.")

        return "\n".join(lines), sources

    @staticmethod
    def _build_report(query: str, checkpoints: list[ResearchCheckpoint], research_id: str) -> ReportEvent:
        lines = [f"# Research Report: {query}", ""]

        for checkpoint in checkpoints:
            lines.append(f"## {checkpoint.phase.value}")
            lines.append(checkpoint.notes)
            if checkpoint.sources:
                lines.append("Sources:")
                lines.extend([f"- {source}" for source in checkpoint.sources])
            lines.append("")

        if not checkpoints:
            lines.append("No checkpoint data was captured.")

        return ReportEvent(
            id=research_id,
            title=f"Research: {query}",
            content="\n".join(lines).strip(),
            attachments=[],
        )
