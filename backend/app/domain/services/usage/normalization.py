"""Normalization helpers for provider-specific usage payloads."""

from typing import Any

from pydantic import BaseModel, Field


class NormalizedUsage(BaseModel):
    """Provider-agnostic usage breakdown for agent usage tracking."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    raw_usage: dict[str, Any] = Field(default_factory=dict)


def normalize_provider_usage(provider: str, raw_usage: dict[str, Any] | Any) -> NormalizedUsage:
    """Normalize provider-native usage payloads into a common shape."""
    usage_dict = _coerce_usage_dict(raw_usage)
    provider_name = provider.lower().strip()

    if provider_name == "openai":
        input_tokens = _get_int(usage_dict, "prompt_tokens")
        output_tokens = _get_int(usage_dict, "completion_tokens")
        cached_input_tokens = _get_int(
            _get_nested_mapping(usage_dict, "prompt_tokens_details"),
            "cached_tokens",
        )
        reasoning_tokens = _get_int(
            _get_nested_mapping(usage_dict, "completion_tokens_details"),
            "reasoning_tokens",
        )
        total_tokens = _get_int(usage_dict, "total_tokens", fallback=input_tokens + output_tokens)
        return NormalizedUsage(
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=total_tokens,
            raw_usage=usage_dict,
        )

    if provider_name == "anthropic":
        input_tokens = _get_int(usage_dict, "input_tokens")
        output_tokens = _get_int(usage_dict, "output_tokens")
        cache_read_tokens = _get_int(usage_dict, "cache_read_input_tokens")
        cache_creation_tokens = _get_int(usage_dict, "cache_creation_input_tokens")
        return NormalizedUsage(
            input_tokens=input_tokens,
            cached_input_tokens=cache_read_tokens,
            cache_creation_input_tokens=cache_creation_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=0,
            total_tokens=_get_int(usage_dict, "total_tokens", fallback=input_tokens + output_tokens),
            raw_usage=usage_dict,
        )

    input_tokens = _get_int(usage_dict, "prompt_tokens", fallback=_get_int(usage_dict, "input_tokens"))
    output_tokens = _get_int(
        usage_dict,
        "completion_tokens",
        fallback=_get_int(usage_dict, "output_tokens"),
    )
    return NormalizedUsage(
        input_tokens=input_tokens,
        cached_input_tokens=0,
        output_tokens=output_tokens,
        reasoning_tokens=0,
        total_tokens=_get_int(usage_dict, "total_tokens", fallback=input_tokens + output_tokens),
        raw_usage=usage_dict,
    )


def _coerce_usage_dict(raw_usage: dict[str, Any] | Any) -> dict[str, Any]:
    """Convert provider usage payloads to a plain dict."""
    if isinstance(raw_usage, dict):
        return dict(raw_usage)

    if raw_usage is None:
        return {}

    model_dump = getattr(raw_usage, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped

    dump = getattr(raw_usage, "dict", None)
    if callable(dump):
        dumped = dump()
        if isinstance(dumped, dict):
            return dumped

    usage_dict: dict[str, Any] = {}
    try:
        items = vars(raw_usage).items()
    except TypeError:
        slots = getattr(raw_usage, "__slots__", ())
        for key in slots:
            if isinstance(key, str) and not key.startswith("_"):
                usage_dict[key] = getattr(raw_usage, key)
        if usage_dict:
            return usage_dict

        for key in dir(raw_usage):
            if key.startswith("_"):
                continue
            value = getattr(raw_usage, key)
            if callable(value):
                continue
            usage_dict[key] = value
        return usage_dict

    for key, value in items:
        if key.startswith("_"):
            continue
        usage_dict[key] = value
    return usage_dict


def _get_nested_mapping(usage_dict: dict[str, Any], key: str) -> dict[str, Any]:
    """Fetch a nested mapping, coercing objects to dicts when needed."""
    value = usage_dict.get(key, {})
    if isinstance(value, dict):
        return value
    return _coerce_usage_dict(value)


def _get_int(usage_dict: dict[str, Any], key: str, fallback: int = 0) -> int:
    """Read an integer-like field from a usage mapping."""
    value = usage_dict.get(key)
    if value is None:
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return fallback
