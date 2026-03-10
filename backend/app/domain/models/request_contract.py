"""RequestContract domain model (2026-02-13 agent robustness plan)."""

from pydantic import BaseModel, Field


class RequestContract(BaseModel):
    """Immutable contract extracted from user request at ingress.

    Preserves exact entities, versions, and constraints that must not
    be mutated by normalization, planning, or execution stages.
    """

    exact_query: str  # Original user text, unmodified
    intent: str = ""  # Classified intent (from FastPathRouter)
    action_type: str = "general"  # "research", "browse", "code", "general"

    # Locked terms — must appear in final output
    locked_entities: list[str] = Field(default_factory=list)  # e.g., ["Claude Sonnet 4.5", "Python 3.12"]
    locked_versions: list[str] = Field(default_factory=list)  # e.g., ["4.5", "3.12"]
    numeric_constraints: list[str] = Field(default_factory=list)  # e.g., ["top 5", "under $100"]

    # Requested output filenames — user-specified artifact names to preserve end-to-end
    requested_filenames: list[str] = Field(default_factory=list)  # e.g., ["agent_observability_report.md"]

    # Extraction metadata
    extraction_method: str = "hybrid"  # "regex", "llm", "hybrid"
    extraction_confidence: float = 1.0
