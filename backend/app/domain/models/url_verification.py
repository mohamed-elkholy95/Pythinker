"""URL Verification Models for Hallucination Prevention.

These models track URL verification results to ensure citations
reference real URLs that were actually visited during the session.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class URLVerificationStatus(str, Enum):
    """Status of URL verification."""

    VERIFIED = "verified"  # URL exists and was visited
    EXISTS_NOT_VISITED = "exists_not_visited"  # URL exists but wasn't visited
    NOT_FOUND = "not_found"  # URL returns 404 or doesn't resolve
    PLACEHOLDER = "placeholder"  # Fake URL pattern detected
    TIMEOUT = "timeout"  # Verification timed out
    ERROR = "error"  # Verification failed with error


@dataclass
class URLVerificationResult:
    """Result of verifying a single URL."""

    url: str
    status: URLVerificationStatus
    exists: bool = False
    was_visited: bool = False
    http_status: int | None = None
    redirect_url: str | None = None
    verification_time_ms: float = 0.0
    error: str | None = None
    verified_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_valid_citation(self) -> bool:
        """Check if this URL is valid for use as a citation."""
        return self.status == URLVerificationStatus.VERIFIED

    @property
    def is_suspicious(self) -> bool:
        """Check if this URL is suspicious (placeholder or not visited)."""
        return self.status in (
            URLVerificationStatus.PLACEHOLDER,
            URLVerificationStatus.EXISTS_NOT_VISITED,
            URLVerificationStatus.NOT_FOUND,
        )

    def get_warning_message(self) -> str | None:
        """Get a warning message if URL has issues."""
        messages = {
            URLVerificationStatus.EXISTS_NOT_VISITED: f"URL was cited but never visited during session: {self.url}",
            URLVerificationStatus.NOT_FOUND: f"Cited URL does not exist (HTTP {self.http_status}): {self.url}",
            URLVerificationStatus.PLACEHOLDER: f"Placeholder/fake URL detected: {self.url}",
            URLVerificationStatus.TIMEOUT: f"Could not verify URL (timeout): {self.url}",
            URLVerificationStatus.ERROR: f"URL verification failed: {self.url} - {self.error}",
        }
        return messages.get(self.status)


@dataclass
class BatchURLVerificationResult:
    """Result of verifying multiple URLs."""

    results: dict[str, URLVerificationResult] = field(default_factory=dict)
    total_urls: int = 0
    verified_count: int = 0
    not_visited_count: int = 0
    not_found_count: int = 0
    placeholder_count: int = 0
    error_count: int = 0
    verification_time_ms: float = 0.0
    verified_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def all_valid(self) -> bool:
        """Check if all URLs are valid citations."""
        return all(r.is_valid_citation for r in self.results.values())

    @property
    def has_critical_issues(self) -> bool:
        """Check if any URLs have critical issues (not found or placeholder)."""
        return self.not_found_count > 0 or self.placeholder_count > 0

    @property
    def has_warnings(self) -> bool:
        """Check if any URLs have warnings (not visited)."""
        return self.not_visited_count > 0

    def get_invalid_urls(self) -> list[str]:
        """Get list of invalid URLs."""
        return [url for url, r in self.results.items() if not r.is_valid_citation]

    def get_warnings(self) -> list[str]:
        """Get all warning messages."""
        warnings = []
        for result in self.results.values():
            msg = result.get_warning_message()
            if msg:
                warnings.append(msg)
        return warnings

    def get_summary(self) -> str:
        """Get a summary of verification results."""
        lines = [
            "URL Verification Summary:",
            f"  Total: {self.total_urls}",
            f"  Verified: {self.verified_count}",
            f"  Not Visited: {self.not_visited_count}",
            f"  Not Found: {self.not_found_count}",
            f"  Placeholder: {self.placeholder_count}",
            f"  Errors: {self.error_count}",
        ]
        return "\n".join(lines)
