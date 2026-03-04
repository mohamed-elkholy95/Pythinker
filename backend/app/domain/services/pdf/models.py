"""Domain models for report PDF rendering."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.domain.models.source_citation import SourceCitation


class ReportPdfPayload(BaseModel):
    """Structured input consumed by PDF renderers."""

    title: str
    markdown_content: str
    sources: list[SourceCitation] = Field(default_factory=list)
    author: str = "Pythinker AI Agent"
    subject: str | None = None
    creator: str = "Pythinker / ReportLab"
    include_toc: bool = True
    toc_min_sections: int = 3
    preferred_font: str = "DejaVuSans"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
