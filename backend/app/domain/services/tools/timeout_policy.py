"""Timeout tier system for shell command execution.

Maps CommandClassification to (soft, hard) timeout pairs.
Soft timeout emits a warning; hard timeout kills the process.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from app.domain.services.tools.shell_classifier import CommandClassification


@dataclass(frozen=True)
class TimeoutTier:
    """Soft and hard timeouts for a command classification."""

    soft_seconds: int  # Warn at this point
    hard_seconds: int  # Kill process at this point


class TimeoutPolicy:
    """Maps CommandClassification to TimeoutTier.

    Usage:
        policy = TimeoutPolicy()
        tier = policy.get_tier(CommandClassification.NETWORK)
        # tier.soft_seconds == 90, tier.hard_seconds == 300
    """

    TIERS: ClassVar[dict[CommandClassification, TimeoutTier]] = {
        CommandClassification.SEARCH: TimeoutTier(soft_seconds=30, hard_seconds=60),
        CommandClassification.READ: TimeoutTier(soft_seconds=30, hard_seconds=60),
        CommandClassification.LIST: TimeoutTier(soft_seconds=30, hard_seconds=60),
        CommandClassification.WRITE: TimeoutTier(soft_seconds=60, hard_seconds=120),
        CommandClassification.EXECUTE: TimeoutTier(soft_seconds=60, hard_seconds=120),
        CommandClassification.NETWORK: TimeoutTier(soft_seconds=90, hard_seconds=300),
        CommandClassification.DESTRUCTIVE: TimeoutTier(soft_seconds=60, hard_seconds=120),
        CommandClassification.UNKNOWN: TimeoutTier(soft_seconds=60, hard_seconds=120),
    }

    def get_tier(self, classification: CommandClassification) -> TimeoutTier:
        """Return the TimeoutTier for the given classification."""
        return self.TIERS.get(classification, self.TIERS[CommandClassification.UNKNOWN])
