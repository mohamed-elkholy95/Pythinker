"""Shell session DTOs with automatic sanitization of internal markers.

The sandbox wraps command output in ``[CMD_BEGIN]``/``[CMD_END]`` markers for
reliable parsing.  These markers are infrastructure plumbing and must never
reach the frontend.  Pydantic ``@field_validator(mode='before')`` ensures
every code path that creates these DTOs (sandbox API, MongoDB event replay,
future consumers) receives clean data automatically.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ValidationInfo, field_validator

# Compiled once at import time — matches [CMD_BEGIN] and [CMD_END]
_CMD_MARKER_RE = re.compile(r"\[CMD_(?:BEGIN|END)\]")


def _strip_markers(text: str) -> str:
    """Remove all ``[CMD_BEGIN]``/``[CMD_END]`` marker occurrences."""
    return _CMD_MARKER_RE.sub("", text)


class ConsoleRecord(BaseModel):
    """Application DTO for a single shell console entry (prompt + command + output).

    Validators automatically strip internal sandbox markers so that consumers
    never see ``[CMD_BEGIN]`` or ``[CMD_END]`` in any field.
    """

    ps1: str
    command: str
    output: str

    @field_validator("ps1", mode="before")
    @classmethod
    def clean_ps1(cls, v: str) -> str:
        """Strip markers, normalise whitespace, ensure prompt ends with ``$``."""
        if not isinstance(v, str):
            return v
        cleaned = _strip_markers(v).strip()
        if cleaned and not cleaned.endswith("$"):
            cleaned += " $"
        return cleaned

    @field_validator("output", mode="before")
    @classmethod
    def clean_output(cls, v: str, info: ValidationInfo) -> str:
        """Strip markers and remove the duplicated header (PS1 + command echo).

        The sandbox initialises ``ConsoleRecord.output`` as
        ``[CMD_BEGIN]\\n{ps1} {command}\\n{actual output}``.  Since ``ps1``
        and ``command`` are already separate fields, we strip the header
        portion so ``output`` contains only the command's stdout.
        """
        if not isinstance(v, str):
            return v
        cleaned = _strip_markers(v)
        # ``info.data`` holds already-validated fields (ps1 is validated
        # before output because of field declaration order).
        command = ""
        if hasattr(info, "data") and isinstance(info.data, dict):
            command = info.data.get("command", "")
        if command:
            # Header format after marker removal: \n{user}@{host}:{path}\n {command}\n
            idx = cleaned.find(f" {command}\n")
            if idx >= 0:
                cleaned = cleaned[idx + len(f" {command}\n"):]
            else:
                idx = cleaned.find(f"{command}\n")
                if idx >= 0:
                    cleaned = cleaned[idx + len(f"{command}\n"):]
        return cleaned.strip("\n")


class ShellViewResponse(BaseModel):
    """Application DTO for shell session output."""

    output: str
    session_id: str
    console: list[ConsoleRecord] | None = None

    @field_validator("output", mode="before")
    @classmethod
    def clean_output(cls, v: str) -> str:
        """Strip internal markers from the raw output string."""
        if not isinstance(v, str):
            return v
        return _strip_markers(v)
