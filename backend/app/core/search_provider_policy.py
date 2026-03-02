"""Shared search provider policy constants and normalization helpers."""

from __future__ import annotations

import json
from typing import Any

ALLOWED_SEARCH_PROVIDERS = frozenset(
    {
        "bing",
        "google",
        "duckduckgo",
        "brave",
        "tavily",
        "serper",
        "exa",
    }
)
DEFAULT_SEARCH_PROVIDER_CHAIN = ("serper", "brave", "tavily", "exa")


def _looks_like_json_input(raw_value: str) -> bool:
    """Return True when a value appears to be JSON or JSON-like."""
    return raw_value[:1] in {"[", "{", '"'}


def parse_search_provider_chain(raw: Any) -> list[str]:
    """Parse, lowercase, dedupe, and allowlist-filter provider chain values."""
    parsed: list[str] = []

    if isinstance(raw, list):
        parsed = [str(item).strip().lower() for item in raw if str(item).strip()]
    elif isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []

        decode_succeeded = False
        try:
            decoded = json.loads(stripped)
            decode_succeeded = True
        except json.JSONDecodeError:
            if _looks_like_json_input(stripped):
                return []
            decoded = None

        if decode_succeeded:
            if isinstance(decoded, list):
                parsed = [str(item).strip().lower() for item in decoded if str(item).strip()]
            else:
                return []
        else:
            parsed = [part.strip().lower() for part in stripped.split(",") if part.strip()]

    unique: list[str] = []
    for provider in parsed:
        if provider in ALLOWED_SEARCH_PROVIDERS and provider not in unique:
            unique.append(provider)
    return unique


def normalize_search_provider_chain(raw: Any) -> list[str]:
    """Return normalized provider chain, falling back to canonical defaults."""
    parsed = parse_search_provider_chain(raw)
    if parsed:
        return parsed
    return list(DEFAULT_SEARCH_PROVIDER_CHAIN)
