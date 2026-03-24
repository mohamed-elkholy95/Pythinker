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
import time as _time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

# Maximum alternative URLs to suggest
_MAX_ALTERNATIVES = 5

# ── Cross-session URL failure cache ─────────────────────────────────────
# Module-level LRU cache of URLs that returned 404/403 in any session.
# New sessions pre-check this cache so the agent never wastes a HEAD
# request on a URL that was already confirmed dead.
# TTL: 6 hours (URLs that were 404 might return if the site deploys).
_CROSS_SESSION_CACHE_TTL_S = 6 * 3600  # 6 hours
_CROSS_SESSION_CACHE_MAX = 500  # max cached URLs

# Mapping: normalized_url → (error_message, timestamp_monotonic)
_cross_session_failures: dict[str, tuple[str, float]] = {}


def _cross_session_check(normalized_url: str) -> str | None:
    """Return the cached error message if the URL is known-bad, else None."""
    entry = _cross_session_failures.get(normalized_url)
    if entry is None:
        return None
    error, ts = entry
    if _time.monotonic() - ts > _CROSS_SESSION_CACHE_TTL_S:
        _cross_session_failures.pop(normalized_url, None)
        return None
    return error


def _cross_session_record(normalized_url: str, error: str) -> None:
    """Record a URL failure in the cross-session cache."""
    # Evict oldest entries if at capacity
    if len(_cross_session_failures) >= _CROSS_SESSION_CACHE_MAX:
        # Remove the oldest 20% by timestamp
        sorted_entries = sorted(_cross_session_failures.items(), key=lambda kv: kv[1][1])
        for url, _ in sorted_entries[: _CROSS_SESSION_CACHE_MAX // 5]:
            _cross_session_failures.pop(url, None)
    _cross_session_failures[normalized_url] = (error, _time.monotonic())


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
        # Domain-level failure tracking: block entire domain after N distinct URL failures
        self._domain_failures: dict[str, int] = {}  # domain → count of distinct failed URLs
        self._domain_block_threshold = 2  # Block domain after 2 distinct URL failures

    def check_url(self, url: str) -> GuardDecision:
        """Pre-execution check for a URL.

        Returns:
            GuardDecision with action (allow/warn/block), tier, message,
            and alternative URLs from search results.
        """
        normalized = normalize_url(url)
        record = self._failures.get(normalized)

        if record is None:
            # Domain-level block: if 2+ distinct URLs from this domain failed, block all
            try:
                domain = urlparse(normalized).netloc.lower()
            except Exception:
                domain = ""
            if domain and self._domain_failures.get(domain, 0) >= self._domain_block_threshold:
                logger.info("URL blocked by domain-level failure: %s (%d URLs failed)", domain, self._domain_failures[domain])
                return GuardDecision(
                    action="block",
                    tier=3,
                    message=(
                        f"BLOCKED: Domain {domain} has {self._domain_failures[domain]} failed URLs this session. "
                        f"This domain appears unreliable — use a different source."
                    ),
                    alternative_urls=self._get_alternatives(normalized),
                )

            # Check cross-session cache before allowing first attempt
            cached_error = _cross_session_check(normalized)
            if cached_error:
                alternatives = self._get_alternatives(normalized)
                alt_text = self._format_alternatives(alternatives)
                logger.info(
                    "URL blocked by cross-session cache: %s (%s)",
                    url[:80],
                    cached_error[:80],
                )
                return GuardDecision(
                    action="block",
                    tier=3,
                    message=(
                        f"BLOCKED: {url} failed in a previous session "
                        f"({cached_error}). Tool call was not executed. "
                        f"{alt_text}"
                        f"Pick a different URL."
                    ),
                    alternative_urls=alternatives,
                )
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

        Updates both the session-scoped tracker and the cross-session cache
        so future sessions skip this URL immediately.

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

        # Track domain-level failures (only for first failure of each URL)
        if normalized not in self._failures or self._failures[normalized].attempts == 1:
            try:
                domain = urlparse(normalized).netloc.lower()
                if domain:
                    self._domain_failures[domain] = self._domain_failures.get(domain, 0) + 1
            except Exception:
                logger.debug("Domain failure tracking failed for %s", normalized[:60], exc_info=True)

        # Persist to cross-session cache (404/403 errors only — transient
        # errors like timeouts should not be cached across sessions)
        error_lower = error.lower()
        if "404" in error_lower or "403" in error_lower or "not found" in error_lower:
            _cross_session_record(normalized, error[:120])

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
