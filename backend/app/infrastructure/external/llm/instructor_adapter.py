"""Thin adapter for the ``instructor`` library.

Provides two pure functions that map our capability flags to the correct
instructor mode and produce a patched async client.  Keeping instructor
behind this adapter means:

1. Only one file imports ``instructor`` - clean dependency boundary.
2. Soft-import friendly - callers check ``INSTRUCTOR_AVAILABLE`` first.
3. Mode selection is independently testable without an OpenAI client.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# --- soft import ---------------------------------------------------------

try:
    import instructor
    from instructor import AsyncInstructor, Mode

    INSTRUCTOR_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    INSTRUCTOR_AVAILABLE = False
    AsyncInstructor = None  # type: ignore[assignment,misc]
    Mode = None  # type: ignore[assignment,misc]


# --- public API ----------------------------------------------------------


def select_instructor_mode(
    *,
    supports_json_schema: bool,
    supports_json_object: bool,
) -> Mode:
    """Pick the strongest ``instructor.Mode`` the provider can handle.

    Args:
        supports_json_schema: Provider honours ``response_format.type = "json_schema"``
        supports_json_object: Provider honours ``response_format.type = "json_object"``

    Returns:
        The best available ``instructor.Mode`` enum member.

    Raises:
        RuntimeError: If instructor is not installed.
    """
    if not INSTRUCTOR_AVAILABLE:
        raise RuntimeError("instructor is not installed")

    if supports_json_schema:
        return instructor.Mode.JSON_SCHEMA
    if supports_json_object:
        return instructor.Mode.JSON
    return instructor.Mode.MD_JSON


def patch_client(
    client: AsyncOpenAI,
    mode: Mode,
) -> AsyncInstructor:
    """Wrap an :class:`AsyncOpenAI` client with instructor validation.

    Args:
        client: An already-configured ``AsyncOpenAI`` instance.
        mode: The instructor mode to use (from :func:`select_instructor_mode`).

    Returns:
        An ``AsyncInstructor`` instance that validates responses against
        Pydantic models and retries on validation failure.

    Raises:
        RuntimeError: If instructor is not installed.
    """
    if not INSTRUCTOR_AVAILABLE:
        raise RuntimeError("instructor is not installed")

    return instructor.from_openai(client, mode=mode)
