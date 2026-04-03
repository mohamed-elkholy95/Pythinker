"""LLM Provider Capability Profiles.

Frozen dataclass consolidating all provider-specific behavior into a single
lookup. Replaces scattered _is_glm_api, _is_deepseek, etc. booleans.

Usage:
    profile = get_provider_profile(api_base, model_name)
    if profile.tool_arg_truncation_prone:
        # validate tool args against schema before returning
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderProfile:
    """Immutable capability/behavior profile for an LLM provider.

    All fields have conservative defaults suitable for unknown providers.
    """

    name: str
    connect_timeout: float = 10.0
    read_timeout: float = 300.0
    tool_read_timeout: float = 90.0
    stream_read_timeout: float = 30.0
    supports_json_mode: bool = True
    supports_tool_choice: bool = True
    supports_system_role: bool = True
    max_tool_calls_per_response: int = 20
    needs_message_merging: bool = False
    needs_thinking_suppression: bool = False
    tool_arg_truncation_prone: bool = False
    requires_orphan_cleanup: bool = False
    slow_tool_threshold: float = 30.0
    slow_tool_trip_count: int = 2
    strict_schema: bool = False  # True for providers that reject developer role, complex tool messages, etc.


# ── Pre-built profiles ────────────────────────────────────────────────────────

_PROFILES: dict[str, ProviderProfile] = {
    "default": ProviderProfile(name="default"),
    "openai": ProviderProfile(
        name="openai",
        connect_timeout=5.0,
        read_timeout=120.0,
    ),
    "openrouter": ProviderProfile(
        name="openrouter",
        connect_timeout=5.0,
        read_timeout=120.0,
    ),
    "anthropic": ProviderProfile(
        name="anthropic",
        connect_timeout=5.0,
        read_timeout=180.0,
    ),
    "glm": ProviderProfile(
        name="glm",
        connect_timeout=10.0,
        read_timeout=90.0,
        tool_read_timeout=180.0,
        supports_json_mode=False,
        needs_message_merging=True,
        needs_thinking_suppression=True,
        tool_arg_truncation_prone=True,
        requires_orphan_cleanup=True,
        strict_schema=True,
    ),
    "deepseek": ProviderProfile(
        name="deepseek",
        connect_timeout=5.0,
        read_timeout=180.0,
    ),
    "ollama": ProviderProfile(
        name="ollama",
        connect_timeout=3.0,
        read_timeout=600.0,
        stream_read_timeout=600.0,
        supports_json_mode=False,
        supports_tool_choice=False,
    ),
    "kimi": ProviderProfile(
        name="kimi",
        connect_timeout=5.0,
        read_timeout=120.0,
        needs_thinking_suppression=True,
        strict_schema=True,
    ),
    "minimax": ProviderProfile(
        name="minimax",
        connect_timeout=10.0,
        read_timeout=180.0,
        tool_read_timeout=120.0,
    ),
}


# ── URL → profile pattern matching ────────────────────────────────────────────

_URL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"z\.ai|bigmodel\.cn|zhipuai", re.IGNORECASE), "glm"),
    (re.compile(r"api\.deepseek\.com", re.IGNORECASE), "deepseek"),
    (re.compile(r"openrouter\.ai", re.IGNORECASE), "openrouter"),
    (re.compile(r"api\.openai\.com", re.IGNORECASE), "openai"),
    (re.compile(r"anthropic\.com", re.IGNORECASE), "anthropic"),
    (re.compile(r"kimi\.(com|ai)", re.IGNORECASE), "kimi"),
    (re.compile(r"minimax\.io|minimaxi\.com", re.IGNORECASE), "minimax"),
    (re.compile(r"localhost|127\.0\.0\.1|host\.docker\.internal|:11434", re.IGNORECASE), "ollama"),
]

# Model name prefix → profile (fallback when URL doesn't match)
_MODEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^glm-", re.IGNORECASE), "glm"),
    (re.compile(r"^deepseek", re.IGNORECASE), "deepseek"),
    (re.compile(r"^claude-", re.IGNORECASE), "anthropic"),
    (re.compile(r"^gpt-|^o[134]-", re.IGNORECASE), "openai"),
    (re.compile(r"^kimi-", re.IGNORECASE), "kimi"),
    (re.compile(r"^minimax-", re.IGNORECASE), "minimax"),
    (re.compile(r"^llama|^mistral|^phi-|^gemma", re.IGNORECASE), "ollama"),
]


def get_provider_profile(api_base: str, model_name: str) -> ProviderProfile:
    """Resolve a provider profile from API base URL and model name.

    Priority: URL patterns first, then model name patterns, then conservative default.
    """
    base = (api_base or "").lower()

    # 1. Match by URL
    for pattern, profile_key in _URL_PATTERNS:
        if pattern.search(base):
            return _PROFILES[profile_key]

    # 2. Match by model name
    for pattern, profile_key in _MODEL_PATTERNS:
        if pattern.search(model_name or ""):
            return _PROFILES[profile_key]

    # 3. Conservative default
    return _PROFILES["default"]
