"""Domain model for RESEARCH_TRACE memory tier.

Separates transient search breadcrumbs (queries, URLs, snippets) from
durable project knowledge (distilled outcomes) using TTL-based expiry.
"""

import enum
import time
from typing import Any

from pydantic import BaseModel, Field


class TraceType(str, enum.Enum):
    """Classifies the kind of information captured in a trace entry."""

    SEARCH_QUERY = "search_query"
    URL_VISITED = "url_visited"
    SEARCH_SNIPPET = "search_snippet"
    BROWSER_CONTENT = "browser_content"
    DISTILLED_OUTCOME = "distilled_outcome"


class TraceTier(str, enum.Enum):
    """Determines the retention policy applied to a trace entry."""

    TRANSIENT = "transient"
    DURABLE = "durable"


class TraceEntry(BaseModel):
    """A single research breadcrumb captured during a session.

    Transient entries are subject to TTL expiry inside ResearchTraceStore.
    Durable entries (e.g. DISTILLED_OUTCOME) persist until explicitly cleared.
    """

    session_id: str
    trace_type: TraceType
    content: str
    source_tool: str = ""
    tier: TraceTier = TraceTier.TRANSIENT
    created_at: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)
