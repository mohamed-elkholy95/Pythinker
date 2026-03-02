"""Content safety utilities for agent-fetched web content.

Provides:
- detect_prompt_injection(): regex-based detection of prompt injection patterns
"""

import logging
import re

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|system)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(your\s+)?(system|previous)\s+(prompt|instructions)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a\s+different|no\s+longer)", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+prompt|api\s+key|secret)", re.IGNORECASE),
    re.compile(r"exfiltrate\s+", re.IGNORECASE),
    re.compile(r"output\s+the\s+contents\s+of\s+your\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"new\s+instructions?:?\s*\n", re.IGNORECASE),
]


def detect_prompt_injection(content: str, source_url: str = "") -> bool:
    """Return True if content likely contains a prompt injection attempt.

    When injection is detected, logs at WARNING level. Callers should exclude
    the fetched content from agent context but may still include the URL.

    Args:
        content: Web page content or snippet to inspect
        source_url: URL the content came from (for logging only)

    Returns:
        True if any injection pattern matched
    """
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(content):
            logger.warning(
                "Prompt injection pattern detected from %s: pattern=%s",
                source_url or "<unknown>",
                pattern.pattern,
            )
            return True
    return False
