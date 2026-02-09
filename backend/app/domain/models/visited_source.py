"""Visited Source Model for Provenance Tracking.

Persistent record of URLs actually visited during a session,
with content hashing for verification.
"""

import hashlib
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ContentAccessMethod(str, Enum):
    """How the content was accessed."""

    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_GET_CONTENT = "browser_get_content"
    HTTP_FETCH = "http_fetch"  # Fast search tool fallback
    SEARCH_SNIPPET = "search_snippet"  # Not actually visited, just snippet
    FILE_READ = "file_read"
    MCP_TOOL = "mcp_tool"


class VisitedSource(BaseModel):
    """Persistent record of a URL actually visited during a session.

    Links to the ToolEvent that produced this source via tool_event_id.
    Contains a hash of the extracted content for verification.

    Usage:
        # Create from tool event
        source = VisitedSource.create(
            session_id="abc123",
            tool_event_id="event456",
            url="https://example.com",
            content="Page content here...",
            access_method=ContentAccessMethod.BROWSER_NAVIGATE,
        )

        # Check if a claim appears in source
        if source.content_contains("92% accuracy"):
            # Claim is grounded
            pass
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    tool_event_id: str  # References ToolEvent.id that produced this

    # URL and access info
    url: str
    final_url: str | None = None  # After redirects
    access_method: ContentAccessMethod
    access_time: datetime = Field(default_factory=datetime.utcnow)

    # Content fingerprint
    content_hash: str  # SHA-256 of extracted text content
    content_length: int
    content_preview: str = Field(default="", max_length=2000)  # First 2000 chars

    # Page metadata
    page_title: str | None = None
    meta_description: str | None = None
    last_modified: datetime | None = None

    # Access status
    access_status: str = "full"  # "full", "partial", "paywall", "error"
    paywall_confidence: float = 0.0

    # Extraction metadata
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    extraction_method: str = "html_to_text"  # or "browser_dom", "pdf", etc.

    # Full content (stored separately for large content)
    _full_content: str | None = None

    @classmethod
    def create(
        cls,
        session_id: str,
        tool_event_id: str,
        url: str,
        content: str,
        access_method: ContentAccessMethod,
        final_url: str | None = None,
        page_title: str | None = None,
        access_status: str = "full",
        paywall_confidence: float = 0.0,
    ) -> "VisitedSource":
        """Create a VisitedSource with content hashing.

        Args:
            session_id: Session this source belongs to
            tool_event_id: ToolEvent that produced this source
            url: Original URL requested
            content: Full text content extracted
            access_method: How the content was accessed
            final_url: Final URL after redirects
            page_title: Page title if available
            access_status: Access level achieved
            paywall_confidence: Confidence that content is paywalled
        """
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        source = cls(
            session_id=session_id,
            tool_event_id=tool_event_id,
            url=url,
            final_url=final_url,
            access_method=access_method,
            content_hash=content_hash,
            content_length=len(content),
            content_preview=content[:2000],
            page_title=page_title,
            access_status=access_status,
            paywall_confidence=paywall_confidence,
        )
        source._full_content = content
        return source

    @property
    def full_content(self) -> str | None:
        """Get the full content if available."""
        return self._full_content

    def set_full_content(self, content: str) -> None:
        """Set the full content (for lazy loading)."""
        self._full_content = content

    def content_contains(self, text: str, case_sensitive: bool = False) -> bool:
        """Check if the source content contains specific text.

        Args:
            text: Text to search for
            case_sensitive: Whether to match case

        Returns:
            True if text is found in content
        """
        content = self._full_content or self.content_preview
        if not content:
            return False

        if case_sensitive:
            return text in content
        return text.lower() in content.lower()

    def content_contains_number(self, number: float | int, tolerance: float = 0.001) -> bool:
        """Check if the source content contains a specific number.

        Handles variations like "92%", "92.0%", "92 percent", etc.

        Args:
            number: Number to search for
            tolerance: Tolerance for floating point comparison

        Returns:
            True if number is found
        """
        import re

        content = self._full_content or self.content_preview
        if not content:
            return False

        # Extract all numbers from content
        number_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*%?")
        matches = number_pattern.findall(content)

        for match in matches:
            try:
                found_number = float(match)
                if abs(found_number - float(number)) <= tolerance:
                    return True
            except ValueError:
                continue

        return False

    def get_excerpt_containing(self, text: str, context_chars: int = 200) -> str | None:
        """Get an excerpt of content containing the specified text.

        Args:
            text: Text to find
            context_chars: Number of characters of context on each side

        Returns:
            Excerpt with context, or None if not found
        """
        content = self._full_content or self.content_preview
        if not content:
            return None

        lower_content = content.lower()
        lower_text = text.lower()

        idx = lower_content.find(lower_text)
        if idx == -1:
            return None

        start = max(0, idx - context_chars)
        end = min(len(content), idx + len(text) + context_chars)

        excerpt = content[start:end]
        if start > 0:
            excerpt = "..." + excerpt
        if end < len(content):
            excerpt = excerpt + "..."

        return excerpt

    @property
    def is_fully_accessible(self) -> bool:
        """Check if full content was accessible."""
        return self.access_status == "full" and self.paywall_confidence < 0.5

    @property
    def is_search_snippet_only(self) -> bool:
        """Check if this is just a search snippet, not actual visit."""
        return self.access_method == ContentAccessMethod.SEARCH_SNIPPET
