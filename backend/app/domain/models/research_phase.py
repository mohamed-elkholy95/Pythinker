"""Domain models for phased research workflows."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ResearchPhase(str, Enum):
    """Phases for structured research execution."""

    PHASE_1_FUNDAMENTALS = "phase_1"
    PHASE_2_USE_CASES = "phase_2"
    PHASE_3_BEST_PRACTICES = "phase_3"
    COMPILATION = "compilation"


class ResearchCheckpoint(BaseModel):
    """Saved notes from a completed research phase."""

    phase: ResearchPhase
    notes: str
    sources: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
    query_context: str


class ResearchState(BaseModel):
    """Tracks progress across phased research execution."""

    current_phase: ResearchPhase
    checkpoints: list[ResearchCheckpoint] = Field(default_factory=list)
    action_count: int = 0
    last_reflection: str | None = None
    next_step: str | None = None
