"""URL Verification Service for Hallucination Prevention.

Verifies that cited URLs are real and were actually visited during the session.
This prevents the agent from fabricating citations to non-existent pages.

Usage:
    service = URLVerificationService()

    # Single URL verification
    result = await service.verify_url(
        url="https://openrouter.ai/models",
        session_urls={"https://openrouter.ai/models", "https://example.com"}
    )

    if not result.is_valid_citation:
        print(f"Invalid citation: {result.get_warning_message()}")

    # Batch verification
    batch_result = await service.batch_verify(
        urls=["https://example.com", "https://fake.invalid"],
        session_urls=session_visited_urls
    )
"""

import asyncio
import logging
import re
import time
from typing import ClassVar
from urllib.parse import urlparse

import httpx

from app.domain.models.url_verification import (
    BatchURLVerificationResult,
    URLVerificationResult,
    URLVerificationStatus,
)

logger = logging.getLogger(__name__)


class URLVerificationService:
    """Service for verifying URLs are real and were visited.

    Detects:
    - Placeholder URLs (example.com, localhost, [URL])
    - Non-existent URLs (404, DNS failure)
    - URLs that exist but weren't visited during the session
    """

    # Placeholder URL patterns that indicate fabricated citations
    PLACEHOLDER_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"example\.(com|org|net)", re.IGNORECASE),
        re.compile(r"localhost", re.IGNORECASE),
        re.compile(r"127\.0\.0\.1"),
        re.compile(r"\[URL\]", re.IGNORECASE),
        re.compile(r"\[link\]", re.IGNORECASE),
        re.compile(r"placeholder", re.IGNORECASE),
        re.compile(r"your-?domain", re.IGNORECASE),
        re.compile(r"test\.(com|org|net)", re.IGNORECASE),
        re.compile(r"fake\.(com|org|net)", re.IGNORECASE),
        re.compile(r"sample\.(com|org|net)", re.IGNORECASE),
        re.compile(r"xxx+\.(com|org|net)", re.IGNORECASE),
        re.compile(r"domain\.com", re.IGNORECASE),
        re.compile(r"website\.com", re.IGNORECASE),
        re.compile(r"url\.com", re.IGNORECASE),
    ]

    # Suspicious TLDs that often indicate fake URLs
    SUSPICIOUS_TLDS: ClassVar[set[str]] = {
        ".invalid",
        ".test",
        ".example",
        ".localhost",
    }

    def __init__(
        self,
        timeout: float = 10.0,
        max_redirects: int = 5,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize URL verification service.

        Args:
            timeout: HTTP request timeout in seconds
            max_redirects: Maximum number of redirects to follow
            verify_ssl: Whether to verify SSL certificates
        """
        self._timeout = timeout
        self._max_redirects = max_redirects
        self._verify_ssl = verify_ssl

    def detect_placeholder_url(self, url: str) -> bool:
        """Check if URL matches placeholder patterns.

        Args:
            url: URL to check

        Returns:
            True if URL appears to be a placeholder/fake
        """
        # Check against placeholder patterns
        for pattern in self.PLACEHOLDER_PATTERNS:
            if pattern.search(url):
                return True

        # Check for suspicious TLDs
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            for tld in self.SUSPICIOUS_TLDS:
                if hostname.endswith(tld):
                    return True
        except Exception:
            pass

        return False

    def is_valid_url_format(self, url: str) -> bool:
        """Check if URL has valid format.

        Args:
            url: URL to validate

        Returns:
            True if URL format is valid
        """
        try:
            parsed = urlparse(url)
            return all([
                parsed.scheme in ("http", "https"),
                parsed.netloc,
                len(url) < 2048,  # Reasonable URL length limit
            ])
        except Exception:
            return False

    async def verify_url_exists(self, url: str) -> URLVerificationResult:
        """Verify that a URL exists by making a HEAD request.

        Args:
            url: URL to verify

        Returns:
            URLVerificationResult with existence status
        """
        start_time = time.time()

        # Check for placeholder URLs first
        if self.detect_placeholder_url(url):
            return URLVerificationResult(
                url=url,
                status=URLVerificationStatus.PLACEHOLDER,
                exists=False,
                was_visited=False,
                verification_time_ms=(time.time() - start_time) * 1000,
            )

        # Validate URL format
        if not self.is_valid_url_format(url):
            return URLVerificationResult(
                url=url,
                status=URLVerificationStatus.ERROR,
                exists=False,
                was_visited=False,
                error="Invalid URL format",
                verification_time_ms=(time.time() - start_time) * 1000,
            )

        # Make HTTP request to verify existence
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                max_redirects=self._max_redirects,
                verify=self._verify_ssl,
            ) as client:
                # Try HEAD first (faster)
                response = await client.head(url)

                # If HEAD fails with 405, try GET
                if response.status_code == 405:
                    response = await client.get(url)

                exists = response.status_code < 400
                redirect_url = None

                # Check for redirects
                if response.history:
                    redirect_url = str(response.url)

                return URLVerificationResult(
                    url=url,
                    status=URLVerificationStatus.EXISTS_NOT_VISITED if exists else URLVerificationStatus.NOT_FOUND,
                    exists=exists,
                    was_visited=False,  # Will be updated by verify_url()
                    http_status=response.status_code,
                    redirect_url=redirect_url,
                    verification_time_ms=(time.time() - start_time) * 1000,
                )

        except httpx.TimeoutException:
            return URLVerificationResult(
                url=url,
                status=URLVerificationStatus.TIMEOUT,
                exists=False,
                was_visited=False,
                error="Request timed out",
                verification_time_ms=(time.time() - start_time) * 1000,
            )
        except httpx.ConnectError as e:
            return URLVerificationResult(
                url=url,
                status=URLVerificationStatus.NOT_FOUND,
                exists=False,
                was_visited=False,
                error=f"Connection failed: {e!s}",
                verification_time_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            logger.warning(f"URL verification error for {url}: {e}")
            return URLVerificationResult(
                url=url,
                status=URLVerificationStatus.ERROR,
                exists=False,
                was_visited=False,
                error=str(e),
                verification_time_ms=(time.time() - start_time) * 1000,
            )

    def verify_url_was_visited(
        self,
        url: str,
        session_urls: set[str],
    ) -> bool:
        """Check if URL was visited during the session.

        Args:
            url: URL to check
            session_urls: Set of URLs visited during the session

        Returns:
            True if URL was visited
        """
        if not session_urls:
            return False

        # Normalize URL for comparison
        normalized = self._normalize_url(url)

        # Check exact match first
        if url in session_urls or normalized in session_urls:
            return True

        # Check normalized versions of session URLs
        for session_url in session_urls:
            if self._normalize_url(session_url) == normalized:
                return True

        return False

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison.

        Removes trailing slashes, fragments, and normalizes case.
        """
        try:
            parsed = urlparse(url)
            # Remove fragment and trailing slash
            path = parsed.path.rstrip("/") or "/"
            # Reconstruct without fragment
            normalized = f"{parsed.scheme}://{parsed.netloc.lower()}{path}"
            if parsed.query:
                normalized += f"?{parsed.query}"
            return normalized
        except Exception:
            return url.lower().rstrip("/")

    async def verify_url(
        self,
        url: str,
        session_urls: set[str] | None = None,
    ) -> URLVerificationResult:
        """Verify a single URL exists and was visited.

        Args:
            url: URL to verify
            session_urls: Optional set of URLs visited during session

        Returns:
            URLVerificationResult with full verification status
        """
        # First check if it's a placeholder
        if self.detect_placeholder_url(url):
            return URLVerificationResult(
                url=url,
                status=URLVerificationStatus.PLACEHOLDER,
                exists=False,
                was_visited=False,
            )

        # Check if URL was visited (if session URLs provided)
        was_visited = False
        if session_urls is not None:
            was_visited = self.verify_url_was_visited(url, session_urls)

            # If visited, we can trust it exists
            if was_visited:
                return URLVerificationResult(
                    url=url,
                    status=URLVerificationStatus.VERIFIED,
                    exists=True,
                    was_visited=True,
                )

        # Verify URL exists
        result = await self.verify_url_exists(url)

        # Update was_visited status if URL exists
        if result.exists and session_urls is not None:
            result.was_visited = was_visited
            if not was_visited:
                result.status = URLVerificationStatus.EXISTS_NOT_VISITED

        return result

    async def batch_verify(
        self,
        urls: list[str],
        session_urls: set[str] | None = None,
        max_concurrent: int = 10,
    ) -> BatchURLVerificationResult:
        """Verify multiple URLs in parallel.

        Args:
            urls: List of URLs to verify
            session_urls: Optional set of URLs visited during session
            max_concurrent: Maximum concurrent verification requests

        Returns:
            BatchURLVerificationResult with all results
        """
        start_time = time.time()

        if not urls:
            return BatchURLVerificationResult()

        # Deduplicate URLs
        unique_urls = list(set(urls))

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def verify_with_semaphore(url: str) -> tuple[str, URLVerificationResult]:
            async with semaphore:
                result = await self.verify_url(url, session_urls)
                return url, result

        # Run verifications in parallel
        tasks = [verify_with_semaphore(url) for url in unique_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        batch_result = BatchURLVerificationResult(
            total_urls=len(unique_urls),
            verification_time_ms=(time.time() - start_time) * 1000,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"URL verification task failed: {result}")
                continue

            url, verification = result
            batch_result.results[url] = verification

            # Update counts
            if verification.status == URLVerificationStatus.VERIFIED:
                batch_result.verified_count += 1
            elif verification.status == URLVerificationStatus.EXISTS_NOT_VISITED:
                batch_result.not_visited_count += 1
            elif verification.status == URLVerificationStatus.NOT_FOUND:
                batch_result.not_found_count += 1
            elif verification.status == URLVerificationStatus.PLACEHOLDER:
                batch_result.placeholder_count += 1
            else:
                batch_result.error_count += 1

        return batch_result

    def extract_urls_from_text(self, text: str) -> list[str]:
        """Extract URLs from text content.

        Args:
            text: Text to extract URLs from

        Returns:
            List of extracted URLs
        """
        # URL regex pattern
        url_pattern = re.compile(
            r'https?://[^\s<>"\')\]]+',
            re.IGNORECASE,
        )

        urls = url_pattern.findall(text)

        # Clean up URLs (remove trailing punctuation)
        cleaned = []
        for url in urls:
            # Remove common trailing punctuation
            url = url.rstrip(".,;:!?")
            if self.is_valid_url_format(url):
                cleaned.append(url)

        return list(set(cleaned))


# Singleton instance for reuse
_url_verification_service: URLVerificationService | None = None


def get_url_verification_service() -> URLVerificationService:
    """Get or create the URL verification service singleton."""
    global _url_verification_service
    if _url_verification_service is None:
        _url_verification_service = URLVerificationService()
    return _url_verification_service
