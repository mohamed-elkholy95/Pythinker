"""URL Failure Guard — 3-Tier Auto-Correction for LLM URL Hallucination.

Tracks failed URLs across all steps in a session and provides pre-execution
checks with escalating responses:
  Tier 1 (1st failure): Allow execution, return structured error
  Tier 2 (2nd attempt): Inject warning with alternative URLs, allow execution
  Tier 3 (3rd attempt): Hard-block tool call, return synthetic failure

Designed to prevent the LLM from retrying hallucinated URLs that return 404.

Root cause: Session 3fdec66859ff45b3 was cancelled after GLM-5 fabricated
https://vuejs.org/guide/best-practices/ (404). The agent retried the same
URL until StuckDetector killed the session.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

# Maximum alternative URLs to suggest
_MAX_ALTERNATIVES = 5


def normalize_url(url: str) -> str:
    """Normalize URL for comparison.

    - Strip trailing slashes
    - Lowercase scheme and host
    - Sort query parameters
    - Remove fragments (#anchors)
    """
    if not url:
        return ""

    parsed = urlparse(url)

    # If no scheme, urlparse puts everything in path — handle gracefully
    if not parsed.scheme:
        # Strip trailing slash from the raw URL
        return url.rstrip("/")

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or ""
    # Sort query parameters
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    sorted_query = urlencode(sorted(query_params.items()), doseq=True)
    # Remove fragment
    fragment = ""

    return urlunparse((scheme, netloc, path, parsed.params, sorted_query, fragment))


@dataclass
class UrlFailureRecord:
    """Tracks failure history for a single normalized URL."""

    url: str
    error: str
    attempts: int = 1
    first_failed: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_failed: datetime = field(default_factory=lambda: datetime.now(UTC))
    source_tool: str = ""


@dataclass
class GuardDecision:
    """Result of a pre-execution URL check."""

    action: str  # "allow", "warn", "block"
    tier: int  # 1, 2, 3
    message: str | None = None
    alternative_urls: list[str] = field(default_factory=list)


class UrlFailureGuard:
    """Session-scoped URL failure tracker with 3-tier escalation.

    Instantiated once per session in PlanActFlow, passed to BaseAgent.
    Persists across all steps in a session.
    """

    def __init__(self, max_failures_per_url: int = 3) -> None:
        self._max_failures = max_failures_per_url
        self._failures: dict[str, UrlFailureRecord] = {}
        self._known_good_urls: list[str] = []
        self._total_failures = 0
        self._tier2_escalations = 0
        self._tier3_escalations = 0

    def check_url(self, url: str) -> GuardDecision:
        """Pre-execution check for a URL.

        Returns:
            GuardDecision with action (allow/warn/block), tier, message,
            and alternative URLs from search results.
        """
        normalized = normalize_url(url)
        record = self._failures.get(normalized)

        if record is None:
            # Tier 1: First attempt — allow
            return GuardDecision(action="allow", tier=1)

        alternatives = self._get_alternatives(normalized)

        if record.attempts >= self._max_failures - 1:
            # Tier 3: 3rd+ attempt — hard block
            self._tier3_escalations += 1
            alt_text = self._format_alternatives(alternatives)
            return GuardDecision(
                action="block",
                tier=3,
                message=(
                    f"BLOCKED: {url} has failed {record.attempts} times "
                    f"({record.error}). Tool call was not executed. "
                    f"{alt_text}"
                    f"Pick one of these URLs instead."
                ),
                alternative_urls=alternatives,
            )

        # Tier 2: 2nd attempt — warn but allow
        self._tier2_escalations += 1
        alt_text = self._format_alternatives(alternatives)
        return GuardDecision(
            action="warn",
            tier=2,
            message=(
                f"WARNING: You already tried {url} and it failed "
                f"({record.error}). Do NOT retry this URL. "
                f"{alt_text}"
                f"Use a different URL from your search results."
            ),
            alternative_urls=alternatives,
        )

    def record_failure(self, url: str, error: str, tool: str) -> None:
        """Record a URL failure after tool execution.

        Args:
            url: The URL that failed
            error: Error description (e.g., "HTTP 404 Not Found")
            tool: Tool name that attempted the URL
        """
        normalized = normalize_url(url)
        self._total_failures += 1

        if normalized in self._failures:
            record = self._failures[normalized]
            record.attempts += 1
            record.last_failed = datetime.now(UTC)
            record.error = error
        else:
            self._failures[normalized] = UrlFailureRecord(
                url=normalized,
                error=error,
                source_tool=tool,
            )

        logger.info(
            "URL failure recorded: %s (attempts=%d, error=%s, tool=%s)",
            url,
            self._failures[normalized].attempts,
            error,
            tool,
        )

    def record_search_results(self, urls: list[str]) -> None:
        """Record known-good URLs from search results.

        These are used as alternative suggestions when the LLM
        tries a failed URL.

        Args:
            urls: List of URLs from search result items
        """
        for url in urls:
            normalized = normalize_url(url)
            if normalized and normalized not in self._known_good_urls:
                self._known_good_urls.append(normalized)

    def get_failed_urls_summary(self) -> str | None:
        """Human-readable summary of all failed URLs.

        Returns None if no failures recorded.
        """
        if not self._failures:
            return None

        lines = [f"  - {record.url} ({record.error}, {record.attempts} attempts)" for record in self._failures.values()]
        return "Failed URLs this session:\n" + "\n".join(lines)

    def get_metrics(self) -> dict[str, int]:
        """Metrics for Prometheus export."""
        return {
            "tracked_urls": len(self._failures),
            "total_failures": self._total_failures,
            "tier2_escalations": self._tier2_escalations,
            "tier3_escalations": self._tier3_escalations,
            "known_good_urls": len(self._known_good_urls),
        }

    def _get_alternatives(self, failed_normalized: str) -> list[str]:
        """Get known-good URLs excluding failed ones."""
        failed_set = set(self._failures.keys())
        alternatives = [url for url in self._known_good_urls if url not in failed_set]
        return alternatives[:_MAX_ALTERNATIVES]

    def _format_alternatives(self, alternatives: list[str]) -> str:
        """Format alternative URLs for LLM context injection."""
        if not alternatives:
            return ""
        lines = "\n".join(f"  - {url}" for url in alternatives)
        return f"Available URLs:\n{lines}\n"
