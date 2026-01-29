"""Source citation model for tracking references in reports."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SourceCitation(BaseModel):
    """Represents a source citation for report bibliography.

    Attributes:
        url: The URL of the source
        title: Title of the source (page title or result title)
        snippet: Optional preview snippet from the source
        access_time: When the source was accessed
        source_type: Type of source - search result, browser navigation, or file
    """
    url: str
    title: str
    snippet: str | None = None
    access_time: datetime
    source_type: Literal["search", "browser", "file"]

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
