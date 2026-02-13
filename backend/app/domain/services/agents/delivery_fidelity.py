"""Delivery fidelity checker (2026-02-13 agent robustness plan Phase 3)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.models.request_contract import RequestContract

logger = logging.getLogger(__name__)


@dataclass
class FidelityResult:
    """Result of entity fidelity check."""

    passed: bool
    missing_entities: list[str]
    fidelity_score: float


class DeliveryFidelityChecker:
    """Validates final output against RequestContract.

    Checks that locked entities/versions from the RequestContract
    appear in the final output.
    """

    def check_entity_fidelity(
        self,
        output: str,
        contract: RequestContract | None,
    ) -> FidelityResult:
        """Check that locked entities appear in output.

        Args:
            output: Final report/output content
            contract: Request contract with locked entities (or None)

        Returns:
            FidelityResult with passed, missing_entities, fidelity_score
        """
        if not contract:
            return FidelityResult(passed=True, missing_entities=[], fidelity_score=1.0)

        output_lower = output.lower()
        missing: list[str] = [e for e in contract.locked_entities if e.lower() not in output_lower]
        missing.extend(f"version {v}" for v in contract.locked_versions if v not in output)

        total = len(contract.locked_entities) + len(contract.locked_versions)
        score = 1.0 - (len(missing) / max(total, 1)) if total else 1.0
        passed = len(missing) == 0

        return FidelityResult(
            passed=passed,
            missing_entities=missing,
            fidelity_score=score,
        )
