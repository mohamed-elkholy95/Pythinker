"""Clarification domain model for human-in-the-loop question gates."""

from __future__ import annotations

import enum

from pydantic import BaseModel

_ICON_MAP: dict[str, str] = {
    "missing_info": "[?]",
    "ambiguous_requirement": "[~]",
    "approach_choice": "[>]",
    "risk_confirmation": "[!]",
    "suggestion": "[*]",
}


class ClarificationType(str, enum.Enum):
    """Classifies the intent of a clarification question."""

    MISSING_INFO = "missing_info"
    AMBIGUOUS_REQUIREMENT = "ambiguous_requirement"
    APPROACH_CHOICE = "approach_choice"
    RISK_CONFIRMATION = "risk_confirmation"
    SUGGESTION = "suggestion"


class ClarificationRequest(BaseModel):
    """A typed clarification question to be surfaced to the user before proceeding."""

    question: str
    clarification_type: ClarificationType
    context: str | None = None
    options: list[str] | None = None

    def format(self) -> str:
        """Return a human-readable representation of the clarification request.

        The output includes:
        - A type icon prefix (e.g. ``[?]``)
        - An optional context prefix on the same leading line
        - The question text
        - A numbered list of options when present
        """
        icon = _ICON_MAP[self.clarification_type.value]

        parts: list[str] = []

        if self.context:
            parts.append(f"{icon} {self.context}")
            parts.append(self.question)
        else:
            parts.append(f"{icon} {self.question}")

        if self.options:
            for index, option in enumerate(self.options, start=1):
                parts.append(f"{index}. {option}")

        return "\n".join(parts)
