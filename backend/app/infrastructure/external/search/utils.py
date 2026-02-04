"""Search Engine Utilities

Shared utility functions for search engine implementations:
- URL cleaning and redirect handling
- HTML text extraction
- Result count parsing
"""

import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import Tag


def clean_redirect_url(url: str, base_url: str = "") -> str:
    """Clean redirect URLs from various search engines.

    Handles:
    - DuckDuckGo /l/ redirects
    - Google /url?q= redirects
    - Whoogle /url?q= redirects
    - Baidu /link?url= redirects
    - Relative URLs

    Args:
        url: URL to clean (may be a redirect URL)
        base_url: Base URL for resolving relative paths

    Returns:
        Cleaned actual URL
    """
    if not url:
        return ""

    # DuckDuckGo redirect
    if "//duckduckgo.com/l/" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "uddg" in params:
            return unquote(params["uddg"][0])

    # Google/Whoogle redirect
    if "/url?" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "q" in params:
            return params["q"][0]

    # Baidu redirect
    if "/link?url=" in url:
        match = re.search(r"url=([^&]+)", url)
        if match:
            return match.group(1)

    # Protocol-relative URL
    if url.startswith("//"):
        return "https:" + url

    # Relative URL handling
    if url.startswith("/"):
        return urljoin(base_url, url) if base_url else url

    return url


def extract_text_from_tag(tag: Tag | None, strip: bool = True) -> str:
    """Safely extract text from a BeautifulSoup tag.

    Args:
        tag: BeautifulSoup Tag object (or None)
        strip: Whether to strip whitespace

    Returns:
        Extracted text or empty string
    """
    if tag is None:
        return ""
    text = tag.get_text(strip=strip)
    return text if text else ""


def find_snippet_from_patterns(
    container: Tag,
    class_patterns: list[str],
    min_length: int = 20,
) -> str:
    """Find snippet text using multiple CSS class patterns.

    Searches for paragraph, div, or span elements matching the given
    class patterns and returns the first text with sufficient length.

    Args:
        container: BeautifulSoup element to search within
        class_patterns: List of regex patterns for class attributes
        min_length: Minimum text length to accept

    Returns:
        First matching snippet text or empty string
    """
    for pattern in class_patterns:
        tags = container.find_all(["p", "div", "span"], class_=re.compile(pattern))
        for tag in tags:
            text = extract_text_from_tag(tag)
            if len(text) >= min_length:
                return text
    return ""


def parse_result_count(text: str, patterns: list[str] | None = None) -> int:
    """Parse result count from text using regex patterns.

    Tries multiple common patterns for extracting result counts from
    search engine result pages.

    Args:
        text: Text containing result count (e.g., "About 1,234,567 results")
        patterns: Optional list of regex patterns to try

    Returns:
        Extracted count as integer, or 0 if not found
    """
    if patterns is None:
        # Common patterns for result counts
        patterns = [
            r"(?:about\s+)?(\d[\d,\.]*)\s+results?",  # "About 1,234 results"
            r"(\d[\d,\.]*)\s+search\s+results?",  # "1234 search results"
            r"found\s+(\d[\d,\.]*)",  # "found 1234"
            r"(\d[\d,\.]*)\s+matches?",  # "1234 matches"
        ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                # Remove commas and periods used as thousand separators
                num_str = match.group(1).replace(",", "").replace(".", "")
                return int(num_str)
            except ValueError:
                continue
    return 0


def normalize_url(url: str) -> str:
    """Normalize URL for consistent comparison.

    - Ensures https:// scheme
    - Removes trailing slashes
    - Lowercases the domain

    Args:
        url: URL to normalize

    Returns:
        Normalized URL
    """
    if not url:
        return ""

    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)

    # Rebuild with normalized components
    normalized = f"{parsed.scheme}://{parsed.netloc.lower()}"
    if parsed.path and parsed.path != "/":
        normalized += parsed.path.rstrip("/")
    if parsed.query:
        normalized += "?" + parsed.query

    return normalized


def extract_domain(url: str) -> str:
    """Extract domain from URL.

    Args:
        url: Full URL

    Returns:
        Domain name (e.g., "example.com")
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


def sanitize_query(query: str, max_length: int = 500) -> str:
    """Sanitize search query.

    - Strips whitespace
    - Truncates to max length
    - Removes control characters

    Args:
        query: Raw search query
        max_length: Maximum query length

    Returns:
        Sanitized query string
    """
    if not query:
        return ""

    # Remove control characters
    query = "".join(char for char in query if ord(char) >= 32 or char in "\n\t")

    # Normalize whitespace
    query = " ".join(query.split())

    # Truncate
    if len(query) > max_length:
        query = query[:max_length]

    return query
