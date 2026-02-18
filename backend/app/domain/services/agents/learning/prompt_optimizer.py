"""
Prompt Optimization module.

This module provides automatic prompt optimization using
multi-armed bandit algorithms (Thompson sampling).
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PromptVariant:
    """A variant of a prompt for A/B testing."""

    variant_id: str
    prompt_template: str
    description: str = ""
    # Thompson sampling parameters (Beta distribution)
    alpha: float = 1.0  # Success count + 1
    beta: float = 1.0  # Failure count + 1
    total_trials: int = 0
    success_count: int = 0
    average_quality: float = 0.0
    average_latency_ms: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = True

    @property
    def success_rate(self) -> float:
        """Calculate the success rate."""
        if self.total_trials == 0:
            return 0.5
        return self.success_count / self.total_trials

    def sample_value(self) -> float:
        """Sample a value from the Beta distribution (Thompson sampling)."""
        return float(np.random.beta(self.alpha, self.beta))

    def update(
        self,
        success: bool,
        quality_score: float | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Update the variant with a new outcome.

        Args:
            success: Whether the prompt was successful
            quality_score: Optional quality score (0-1)
            latency_ms: Optional latency in milliseconds
        """
        self.total_trials += 1
        self.last_used = datetime.now(UTC)

        if success:
            self.alpha += 1
            self.success_count += 1
        else:
            self.beta += 1

        # Update average quality
        if quality_score is not None:
            alpha = 0.2
            self.average_quality = alpha * quality_score + (1 - alpha) * self.average_quality

        # Update average latency
        if latency_ms is not None:
            alpha = 0.2
            self.average_latency_ms = alpha * latency_ms + (1 - alpha) * self.average_latency_ms


@dataclass
class PromptContext:
    """Context for prompt selection."""

    task_type: str
    complexity: str = "medium"
    agent_type: str = "executor"
    additional_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptOutcome:
    """Outcome of using a prompt variant."""

    variant_id: str
    success: bool
    quality_score: float | None = None
    latency_ms: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PromptOptimizer:
    """Optimizer for prompt variants using Thompson sampling.

    Maintains multiple prompt variants and uses multi-armed bandit
    algorithms to select and optimize prompts over time.
    """

    # Minimum trials before considering a variant for selection
    MIN_TRIALS = 5
    # Exploration bonus for underexplored variants
    EXPLORATION_BONUS = 0.1
    # Maximum variants per prompt category
    MAX_VARIANTS = 10

    def __init__(self) -> None:
        """Initialize the prompt optimizer."""
        self._variants: dict[str, dict[str, PromptVariant]] = {}  # category -> variants
        self._selection_history: list[tuple[str, str, datetime]] = []

    def register_variant(
        self,
        category: str,
        variant_id: str,
        prompt_template: str,
        description: str = "",
    ) -> PromptVariant:
        """Register a new prompt variant.

        Args:
            category: Category of prompt (e.g., "planning", "execution")
            variant_id: Unique ID for the variant
            prompt_template: The prompt template
            description: Description of the variant

        Returns:
            The registered variant
        """
        if category not in self._variants:
            self._variants[category] = {}

        if len(self._variants[category]) >= self.MAX_VARIANTS:
            # Remove worst performing variant
            self._prune_worst_variant(category)

        variant = PromptVariant(
            variant_id=variant_id,
            prompt_template=prompt_template,
            description=description,
        )
        self._variants[category][variant_id] = variant

        logger.info(f"Registered prompt variant: {category}/{variant_id}")
        return variant

    def select_variant(
        self,
        category: str,
        context: PromptContext | None = None,
    ) -> PromptVariant | None:
        """Select the best variant using Thompson sampling.

        Args:
            category: Category of prompt
            context: Optional context for selection

        Returns:
            Selected variant, or None if no variants available
        """
        if category not in self._variants or not self._variants[category]:
            return None

        active_variants = [v for v in self._variants[category].values() if v.is_active]

        if not active_variants:
            return None

        # Thompson sampling: sample from each variant's distribution
        samples = []
        for variant in active_variants:
            sample = variant.sample_value()

            # Add exploration bonus for underexplored variants
            if variant.total_trials < self.MIN_TRIALS:
                sample += self.EXPLORATION_BONUS

            samples.append((sample, variant))

        # Select variant with highest sample
        best_sample, best_variant = max(samples, key=lambda x: x[0])

        # Record selection
        self._selection_history.append((category, best_variant.variant_id, datetime.now(UTC)))

        logger.debug(
            f"Selected variant {best_variant.variant_id} for {category} "
            f"(sample={best_sample:.3f}, success_rate={best_variant.success_rate:.2f})"
        )

        return best_variant

    def record_outcome(
        self,
        category: str,
        outcome: PromptOutcome,
    ) -> None:
        """Record the outcome of using a prompt variant.

        Args:
            category: Category of prompt
            outcome: The outcome to record
        """
        if category not in self._variants:
            return

        if outcome.variant_id not in self._variants[category]:
            return

        variant = self._variants[category][outcome.variant_id]
        variant.update(
            success=outcome.success,
            quality_score=outcome.quality_score,
            latency_ms=outcome.latency_ms,
        )

        logger.debug(
            f"Updated variant {outcome.variant_id}: "
            f"success_rate={variant.success_rate:.2f}, "
            f"trials={variant.total_trials}"
        )

    def get_best_variant(
        self,
        category: str,
        min_trials: int | None = None,
    ) -> PromptVariant | None:
        """Get the best performing variant.

        Args:
            category: Category of prompt
            min_trials: Minimum trials required

        Returns:
            Best variant by success rate
        """
        if category not in self._variants:
            return None

        min_trials = min_trials or self.MIN_TRIALS
        eligible = [v for v in self._variants[category].values() if v.total_trials >= min_trials and v.is_active]

        if not eligible:
            return None

        return max(eligible, key=lambda v: v.success_rate)

    def get_variant_stats(self, category: str) -> list[dict[str, Any]]:
        """Get statistics for all variants in a category.

        Args:
            category: Category of prompt

        Returns:
            List of variant statistics
        """
        if category not in self._variants:
            return []

        return [
            {
                "variant_id": v.variant_id,
                "description": v.description,
                "success_rate": v.success_rate,
                "total_trials": v.total_trials,
                "average_quality": v.average_quality,
                "average_latency_ms": v.average_latency_ms,
                "is_active": v.is_active,
            }
            for v in self._variants[category].values()
        ]

    def deactivate_variant(self, category: str, variant_id: str) -> None:
        """Deactivate a variant (stop using it).

        Args:
            category: Category of prompt
            variant_id: Variant to deactivate
        """
        if category in self._variants and variant_id in self._variants[category]:
            self._variants[category][variant_id].is_active = False
            logger.info(f"Deactivated variant: {category}/{variant_id}")

    def _prune_worst_variant(self, category: str) -> None:
        """Remove the worst performing variant in a category."""
        if category not in self._variants:
            return

        variants = list(self._variants[category].values())
        eligible = [v for v in variants if v.total_trials >= self.MIN_TRIALS]

        if not eligible:
            # Remove least explored variant
            worst = min(variants, key=lambda v: v.total_trials)
        else:
            # Remove lowest success rate
            worst = min(eligible, key=lambda v: v.success_rate)

        del self._variants[category][worst.variant_id]
        logger.info(f"Pruned variant: {category}/{worst.variant_id}")

    def get_exploration_stats(self) -> dict[str, Any]:
        """Get exploration/exploitation statistics."""
        total_selections = len(self._selection_history)
        categories = list(self._variants.keys())

        return {
            "total_selections": total_selections,
            "categories": len(categories),
            "variants_by_category": {cat: len(variants) for cat, variants in self._variants.items()},
        }


# Global optimizer instance
_optimizer: PromptOptimizer | None = None


def get_prompt_optimizer() -> PromptOptimizer:
    """Get or create the global prompt optimizer."""
    global _optimizer
    if _optimizer is None:
        _optimizer = PromptOptimizer()
    return _optimizer


def reset_prompt_optimizer() -> None:
    """Reset the global prompt optimizer."""
    global _optimizer
    _optimizer = None
