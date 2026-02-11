"""Application service for typo correction analytics and feedback."""

from __future__ import annotations

from typing import Any

from app.infrastructure.observability.typo_correction_analytics import get_typo_correction_analytics


class TypoCorrectionService:
    """Coordinates typo correction feedback and analytics queries."""

    def get_summary(self) -> dict[str, Any]:
        return get_typo_correction_analytics().get_summary()

    def submit_feedback(self, *, original: str, corrected: str, user_override: str) -> None:
        get_typo_correction_analytics().record_feedback(
            original=original,
            corrected=corrected,
            user_override=user_override,
        )


_typo_correction_service: TypoCorrectionService | None = None


def get_typo_correction_service() -> TypoCorrectionService:
    global _typo_correction_service
    if _typo_correction_service is None:
        _typo_correction_service = TypoCorrectionService()
    return _typo_correction_service
