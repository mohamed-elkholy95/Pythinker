"""URL filtering utilities for browser automation.

Consolidated video URL detection and SSRF protection logic.
- Video URL detection: avoid processing heavy media content
- SSRF protection: block navigation to internal/private network addresses
"""

import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Video streaming domains to skip (consolidated from all browser implementations)
VIDEO_DOMAINS: set[str] = {
    # YouTube
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "m.youtube.com",
    # Vimeo
    "vimeo.com",
    "www.vimeo.com",
    "player.vimeo.com",
    # Dailymotion
    "dailymotion.com",
    "www.dailymotion.com",
    # Twitch
    "twitch.tv",
    "www.twitch.tv",
    "clips.twitch.tv",
    # TikTok
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    # Streaming services
    "netflix.com",
    "www.netflix.com",
    "hulu.com",
    "www.hulu.com",
    "disneyplus.com",
    "www.disneyplus.com",
    "primevideo.com",
    "www.primevideo.com",
    "hbomax.com",
    "www.hbomax.com",
    "max.com",
    "peacocktv.com",
    "www.peacocktv.com",
    # Anime streaming
    "crunchyroll.com",
    "www.crunchyroll.com",
    "funimation.com",
    "www.funimation.com",
    # Alternative platforms
    "rumble.com",
    "www.rumble.com",
    "bitchute.com",
    "www.bitchute.com",
    "odysee.com",
    "www.odysee.com",
    # International
    "bilibili.com",
    "www.bilibili.com",
    "nicovideo.jp",
    "www.nicovideo.jp",
    # Adult content (skipped to avoid inappropriate content)
    "pornhub.com",
    "www.pornhub.com",
    "xvideos.com",
    "www.xvideos.com",
}

# Video file extensions to skip
VIDEO_EXTENSIONS: set[str] = {
    ".mp4",
    ".webm",
    ".avi",
    ".mov",
    ".mkv",
    ".flv",
    ".wmv",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".3gp",
    ".ogv",
    ".m3u8",  # HLS streaming
}

# URL patterns that indicate video content
VIDEO_URL_PATTERNS: list[re.Pattern] = [
    re.compile(r"/watch\?v=", re.IGNORECASE),  # YouTube-style
    re.compile(r"/video/", re.IGNORECASE),
    re.compile(r"/videos/", re.IGNORECASE),
    re.compile(r"/embed/", re.IGNORECASE),  # Embedded videos
    re.compile(r"/player/", re.IGNORECASE),  # Video players
    re.compile(r"\.m3u8", re.IGNORECASE),  # HLS streams
    re.compile(r"/stream/", re.IGNORECASE),
]


def is_video_url(url: str) -> bool:
    """Check if URL is a video URL that should be skipped.

    Detects video URLs to prevent browser automation from attempting to load
    heavy media content that can cause crashes, timeouts, or excessive resource usage.

    Args:
        url: URL to check

    Returns:
        True if URL appears to be video content, False otherwise

    Detection methods:
    - Known video streaming domain (YouTube, Vimeo, Netflix, etc.)
    - Video file extension (.mp4, .webm, etc.)
    - Video URL patterns (/watch?v=, /embed/, etc.)
    """
    if not url:
        return False

    try:
        url_lower = url.lower()

        # Handle scheme-less URLs (e.g., "youtube.com/watch?v=...")
        if not url_lower.startswith(("http://", "https://", "//")):
            url_lower = f"https://{url_lower}"

        parsed = urlparse(url_lower)

        # Use hostname instead of netloc to exclude ports
        # hostname returns None for invalid URLs, handle gracefully
        hostname = parsed.hostname
        domain = hostname if hostname else parsed.netloc.split(":")[0] if parsed.netloc else ""

        # Normalize domain (remove www. prefix)
        domain_normalized = domain.replace("www.", "") if domain else ""

        # Check if domain is a known video site
        if domain_normalized in VIDEO_DOMAINS or f"www.{domain_normalized}" in VIDEO_DOMAINS:
            return True

        # Check if path has video file extension
        for ext in VIDEO_EXTENSIONS:
            if parsed.path.endswith(ext):
                return True

        # Check if URL matches video patterns
        return any(pattern.search(url_lower) for pattern in VIDEO_URL_PATTERNS)

    except Exception as e:
        logger.debug(f"URL video check failed for {url}: {e}")
        return False


def filter_video_urls(urls: list[str]) -> list[str]:
    """Filter out video URLs from a list.

    Args:
        urls: List of URLs to filter

    Returns:
        Filtered list containing only non-video URLs
    """
    return [url for url in urls if not is_video_url(url)]


# ---------------------------------------------------------------------------
# SSRF Protection — block navigation to internal/private network addresses
# ---------------------------------------------------------------------------

# Internal Docker service hostnames that the browser must never reach
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    "localhost",
    "sandbox",
    "sandbox2",
    "backend",
    "mongodb",
    "redis",
    "redis-cache",
    "qdrant",
    "minio",
    "prometheus",
    "grafana",
    "loki",
    "promtail",
    "worker",
    "frontend",
    "frontend-dev",
    # Cloud metadata endpoints
    "metadata.google.internal",
    "metadata.goog",
})

# Schemes the browser is allowed to use
_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})


def is_ssrf_target(url: str) -> str | None:
    """Check if a URL targets an internal/private network address (SSRF).

    Resolves the hostname to an IP and checks against private ranges.
    Also blocks known Docker service hostnames and cloud metadata endpoints.

    Args:
        url: URL to validate

    Returns:
        None if the URL is safe, or an error message string if it's blocked.
    """
    if not url:
        return "Empty URL"

    try:
        # Normalize
        url_lower = url.strip()
        if not url_lower.startswith(("http://", "https://", "//")):
            url_lower = f"https://{url_lower}"

        parsed = urlparse(url_lower)

        # Scheme check
        scheme = parsed.scheme.lower()
        if scheme not in _ALLOWED_SCHEMES:
            return f"Blocked scheme: {scheme} (only http/https allowed)"

        hostname = parsed.hostname
        if not hostname:
            return "No hostname in URL"

        hostname_lower = hostname.lower().rstrip(".")

        # Block known internal hostnames
        if hostname_lower in _BLOCKED_HOSTNAMES:
            return f"Blocked internal hostname: {hostname_lower}"

        # Block 169.254.169.254 (AWS/GCP metadata) even if hostname differs
        if hostname_lower in ("169.254.169.254",):
            return "Blocked cloud metadata endpoint"

        # Resolve hostname to IP(s) and check each
        try:
            addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror:
            # DNS resolution failed — allow the browser to handle the error naturally
            return None

        for addr_info in addr_infos:
            ip_str = addr_info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return f"Blocked private/internal IP: {ip_str} (resolved from {hostname})"

        return None

    except Exception as e:
        logger.warning("SSRF check failed for %s: %s", url, e)
        # Fail-open for parsing errors — the browser will handle invalid URLs
        return None
