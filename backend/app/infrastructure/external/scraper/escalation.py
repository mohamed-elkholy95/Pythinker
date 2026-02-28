"""Three-tier escalation decision logic.

Separated from ScraplingAdapter so threshold tuning is isolated.
The adapter owns per-tier fetch calls; this module owns upgrade decisions.
"""

from __future__ import annotations

from app.domain.external.scraper import ScrapedContent

# HTTP status codes that always trigger escalation to the next tier
ESCALATION_STATUS_CODES = frozenset({403, 429, 503})

# Text signals that indicate a bot challenge or block page
_BLOCK_SIGNALS = (
    "just a moment",  # Cloudflare interstitial
    "checking your browser",  # Cloudflare
    "enable javascript",  # JS-gated content
    "please enable cookies",  # bot check
    "access denied",
    "403 forbidden",
    "ddos-guard",
    "datadome",
    "please verify you are a human",
    "ray id",  # Cloudflare Ray ID
)

# Low-level HTTP/2 transport error markers.
# These indicate the curl_cffi transport layer (not the server content) failed.
# curl error 92 = CURLE_HTTP2_STREAM / NGHTTP2_INTERNAL_ERROR.
# When detected, the same-transport HTTP/1.1 retry is attempted once; if it
# also fails, escalation to the Dynamic (Playwright) tier is required because
# Playwright does not share curl_cffi's transport stack.
_HTTP2_TRANSPORT_SIGNALS: tuple[str, ...] = (
    "curl: (92)",
    "curle_http2_stream",
    "nghttp2_internal_error",
    "http/2 stream",
    "h2 stream",
    "was not closed cleanly",
    "err_http2",
    "http2_protocol_error",
)


def has_http2_transport_error(error: str | None) -> bool:
    """Return True when an error string indicates an HTTP/2 transport failure.

    Used by ScraplingAdapter to decide whether to attempt an HTTP/1.1 retry
    before escalating to the Dynamic tier.
    """
    if not error:
        return False
    lower = error.lower()
    return any(sig in lower for sig in _HTTP2_TRANSPORT_SIGNALS)


def should_escalate(result: ScrapedContent, min_content_length: int = 500) -> bool:
    """Return True if the result warrants escalation to the next fetch tier.

    Triggers:
    - Fetch failed entirely (success=False) — covers HTTP/2 transport errors
      where curl: (92) caused failure after all same-transport retries exhausted
    - Content is shorter than the minimum threshold
    - Content looks like a bot-challenge page
    - HTTP status code signals a block (403, 429, 503)
    """
    if not result.success:
        return True
    if len(result.text) < min_content_length:
        return True
    if result.status_code and result.status_code in ESCALATION_STATUS_CODES:
        return True
    lower = result.text.lower()
    return any(sig in lower for sig in _BLOCK_SIGNALS)
