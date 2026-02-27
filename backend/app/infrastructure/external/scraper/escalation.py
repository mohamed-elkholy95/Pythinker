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


def should_escalate(result: ScrapedContent, min_content_length: int = 500) -> bool:
    """Return True if the result warrants escalation to the next fetch tier.

    Triggers:
    - Fetch failed entirely (success=False)
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
