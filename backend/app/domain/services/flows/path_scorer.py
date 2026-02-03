"""Path scorer for evaluating and ranking exploration paths.

The PathScorer evaluates paths based on:
- Result quality (assessed by LLM)
- Confidence scores
- Efficiency (steps, tokens, time)
- Error rate

This enables selection of the best path and early abandonment of poor paths.
"""

import logging

from app.domain.external.llm import LLM
from app.domain.models.path_state import (
    PathState,
    TreeOfThoughtsConfig,
)
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


QUALITY_ASSESSMENT_PROMPT = """Assess the quality of this solution path's results.

## Original Goal:
{goal}

## Strategy Used:
{strategy}

## Results Achieved:
{results}

## Steps Completed:
{steps_completed}

## Errors Encountered:
{error_count}

---

Rate the quality of results on a scale of 0.0 to 1.0, where:
- 0.0-0.3: Poor - results are incorrect, incomplete, or off-target
- 0.3-0.6: Moderate - partial success, some useful results
- 0.6-0.8: Good - mostly achieved the goal with minor gaps
- 0.8-1.0: Excellent - fully achieved the goal

Respond with JSON:
{{"quality": 0.0-1.0, "reasoning": "brief explanation"}}
"""


class PathScorer:
    """Scores exploration paths to enable selection and abandonment decisions.

    The scorer combines multiple factors:
    1. Result quality (LLM assessment)
    2. Confidence scores from execution
    3. Efficiency metrics
    4. Error penalty

    Scores are normalized to 0.0-1.0 range.
    """

    def __init__(
        self,
        llm: LLM | None = None,
        json_parser: JsonParser | None = None,
        config: TreeOfThoughtsConfig | None = None,
        goal: str = "",
    ):
        """Initialize the scorer.

        Args:
            llm: Language model for quality assessment (optional)
            json_parser: Parser for structured responses
            config: Tree-of-Thoughts configuration
            goal: The original task goal for quality assessment
        """
        self.llm = llm
        self.json_parser = json_parser
        self.config = config or TreeOfThoughtsConfig()
        self.weights = self.config.score_weights
        self.goal = goal

    def score(self, path: PathState) -> float:
        """Calculate path score using available metrics.

        This is a fast scoring method that doesn't require LLM calls.
        Use score_with_quality for comprehensive assessment.

        Args:
            path: The path to score

        Returns:
            Score from 0.0 to 1.0
        """
        scores = {}

        # Confidence component
        scores["confidence"] = path.metrics.average_confidence

        # Efficiency component (normalized)
        # Assume baseline of 5 steps, penalize excessive steps
        efficiency = 1.0 - min(path.metrics.steps_completed / 10, 1.0) * 0.3
        efficiency = max(efficiency, 0.3)  # Floor at 0.3
        scores["efficiency"] = efficiency

        # Error penalty component
        error_penalty = 1.0 - min(path.metrics.error_rate, 1.0)
        scores["error_penalty"] = error_penalty

        # Result quality placeholder (use cached if available)
        scores["result_quality"] = path.metrics.results_quality or 0.5

        # Calculate weighted score
        total_weight = (
            self.weights.confidence + self.weights.efficiency + self.weights.error_penalty + self.weights.result_quality
        )

        weighted_score = (
            scores["confidence"] * self.weights.confidence
            + scores["efficiency"] * self.weights.efficiency
            + scores["error_penalty"] * self.weights.error_penalty
            + scores["result_quality"] * self.weights.result_quality
        ) / total_weight

        # Store breakdown
        path.score_breakdown = scores
        path.score = weighted_score

        return weighted_score

    async def score_with_quality(self, path: PathState) -> float:
        """Calculate comprehensive path score including LLM quality assessment.

        Args:
            path: The path to score

        Returns:
            Score from 0.0 to 1.0
        """
        # Get basic score first
        base_score = self.score(path)

        # Skip LLM assessment if not configured
        if not self.llm or not self.json_parser:
            return base_score

        # Skip if no results to assess
        if not path.intermediate_results:
            return base_score

        try:
            # Assess quality with LLM
            quality = await self._assess_quality(path)
            path.metrics.results_quality = quality

            # Recalculate with quality
            return self.score(path)

        except Exception as e:
            logger.error(f"Quality assessment failed: {e}")
            return base_score

    async def _assess_quality(self, path: PathState) -> float:
        """Assess result quality using LLM.

        Args:
            path: The path with results to assess

        Returns:
            Quality score from 0.0 to 1.0
        """
        # Format results
        results_text = "\n".join(
            [
                f"- Step {r['step_id']}: {str(r.get('result', 'No result'))[:100]}"
                for r in path.intermediate_results[-5:]  # Last 5 results
            ]
        )

        prompt = QUALITY_ASSESSMENT_PROMPT.format(
            goal=self.goal,
            strategy=path.strategy,
            results=results_text or "No results recorded",
            steps_completed=path.metrics.steps_completed,
            error_count=path.metrics.errors_encountered,
        )

        response = await self.llm.ask(
            messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}
        )

        content = response.get("content", "")
        parsed = await self.json_parser.parse(content)

        return float(parsed.get("quality", 0.5))

    def rank_paths(self, paths: list[PathState]) -> list[PathState]:
        """Rank paths by score (highest first).

        Args:
            paths: List of paths to rank

        Returns:
            Sorted list with highest scores first
        """
        # Score any paths that haven't been scored
        for path in paths:
            if path.score == 0.0:
                self.score(path)

        return sorted(paths, key=lambda p: p.score, reverse=True)

    def get_comparison_summary(self, paths: list[PathState]) -> str:
        """Generate a summary comparing paths.

        Args:
            paths: List of paths to compare

        Returns:
            Human-readable comparison summary
        """
        ranked = self.rank_paths(paths)

        lines = ["## Path Comparison\n"]

        for i, path in enumerate(ranked):
            status_emoji = {
                "completed": "✓",
                "exploring": "→",
                "abandoned": "✗",
                "failed": "!",
            }.get(path.status.value, "?")

            lines.append(f"{i + 1}. {status_emoji} **{path.description[:50]}** (Score: {path.score:.2f})")

            if path.score_breakdown:
                breakdown = ", ".join(f"{k}: {v:.2f}" for k, v in path.score_breakdown.items())
                lines.append(f"   - {breakdown}")

        return "\n".join(lines)
