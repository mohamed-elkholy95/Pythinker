"""Shared search provider policy constants and normalization helpers.

Re-exports from domain model to maintain backward compatibility.
Canonical definitions live in app.domain.models.user_settings.
"""

from __future__ import annotations

from typing import Any

from app.domain.models.user_settings import (
    ALLOWED_SEARCH_PROVIDERS,
    DEFAULT_SEARCH_PROVIDER_CHAIN,
    _normalize_provider_chain_value,
)

__all__ = [
    "ALLOWED_SEARCH_PROVIDERS",
    "DEFAULT_SEARCH_PROVIDER_CHAIN",
    "normalize_search_provider_chain",
    "parse_search_provider_chain",
]


def parse_search_provider_chain(raw: Any) -> list[str]:
    """Parse, lowercase, dedupe, and allowlist-filter provider chain values."""
    result = _normalize_provider_chain_value(raw)
    # If result equals the default, it might have been a fallback — check if input was valid
    if isinstance(raw, (list, str)) and raw:
        return result
    return []


def normalize_search_provider_chain(raw: Any) -> list[str]:
    """Return normalized provider chain, falling back to canonical defaults."""
    return _normalize_provider_chain_value(raw)
