"""RequestContract domain model (2026-02-13 agent robustness plan)."""

from pydantic import BaseModel


class RequestContract(BaseModel):
    """Immutable contract extracted from user request at ingress.

    Preserves exact entities, versions, and constraints that must not
    be mutated by normalization, planning, or execution stages.
    """

    exact_query: str  # Original user text, unmodified
    intent: str = ""  # Classified intent (from FastPathRouter)
    action_type: str = "general"  # "research", "browse", "code", "general"

    # Locked terms — must appear in final output
    locked_entities: list[str] = []  # e.g., ["Claude Sonnet 4.5", "Python 3.12"]
    locked_versions: list[str] = []  # e.g., ["4.5", "3.12"]
    numeric_constraints: list[str] = []  # e.g., ["top 5", "under $100"]

    # Extraction metadata
    extraction_method: str = "hybrid"  # "regex", "llm", "hybrid"
    extraction_confidence: float = 1.0
