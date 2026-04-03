"""Helpers for generating short opaque task identifiers."""

from __future__ import annotations

import secrets
from typing import Final

_TASK_ID_LENGTH_BYTES = 8
_ALLOWED_PREFIXES: Final[set[str]] = {"b_", "a_", "r_", "w_"}


def generate_prefixed_task_id(prefix: str) -> str:
    """Generate a short opaque task identifier with the requested prefix."""
    cleaned_prefix = prefix.strip()
    if cleaned_prefix not in _ALLOWED_PREFIXES:
        raise ValueError(f"Unsupported task ID prefix: {prefix!r}")
    return f"{cleaned_prefix}{secrets.token_urlsafe(_TASK_ID_LENGTH_BYTES)}"


def generate_bash_task_id() -> str:
    return generate_prefixed_task_id("b_")


def generate_agent_task_id() -> str:
    return generate_prefixed_task_id("a_")


def generate_remote_task_id() -> str:
    return generate_prefixed_task_id("r_")


def generate_workflow_task_id() -> str:
    return generate_prefixed_task_id("w_")
