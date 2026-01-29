"""Path aggregator for combining results from multiple exploration paths.

The PathAggregator:
- Selects the best path based on scores
- Synthesizes results from multiple paths if beneficial
- Generates final output from path exploration
"""

import logging
from typing import Any

from app.domain.external.llm import LLM
from app.domain.models.path_state import (
    PathState,
    PathStatus,
    TreeOfThoughtsConfig,
)
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


SYNTHESIS_PROMPT = """Synthesize the best results from multiple solution approaches.

## Original Goal:
{goal}

## Approaches Explored:

{path_summaries}

## Best Performing Path:
{best_path}

---

Create a synthesized final result that:
1. Uses the best approach's results as the foundation
2. Incorporates any valuable insights from other approaches
3. Ensures completeness and quality

Provide the synthesized result."""


class PathAggregator:
    """Aggregates results from multiple exploration paths.

    The aggregator handles:
    1. Selecting the winning path
    2. Optionally synthesizing results from multiple paths
    3. Generating final output
    """

    def __init__(
        self,
        llm: LLM | None = None,
        json_parser: JsonParser | None = None,
        config: TreeOfThoughtsConfig | None = None
    ):
        """Initialize the aggregator.

        Args:
            llm: Language model for synthesis (optional)
            json_parser: Parser for structured responses
            config: Tree-of-Thoughts configuration
        """
        self.llm = llm
        self.json_parser = json_parser
        self.config = config or TreeOfThoughtsConfig()

    def select_best_path(
        self,
        paths: list[PathState],
        min_score: float = 0.0
    ) -> PathState | None:
        """Select the best path from completed paths.

        Args:
            paths: List of paths to select from
            min_score: Minimum score threshold

        Returns:
            Best path or None if no qualifying paths
        """
        # Filter to completed paths above threshold
        candidates = [
            p for p in paths
            if p.status == PathStatus.COMPLETED and p.score >= min_score
        ]

        if not candidates:
            # Try completed paths without score threshold
            candidates = [
                p for p in paths
                if p.status == PathStatus.COMPLETED
            ]

        if not candidates:
            logger.warning("No completed paths to select from")
            return None

        # Select highest scoring
        best = max(candidates, key=lambda p: p.score)
        best.select()

        logger.info(
            f"Selected path {best.id} with score {best.score:.2f}: "
            f"{best.description[:50]}"
        )

        return best

    async def aggregate(
        self,
        paths: list[PathState],
        goal: str,
        synthesize: bool = True
    ) -> dict[str, Any]:
        """Aggregate results from explored paths.

        Args:
            paths: List of explored paths
            goal: Original task goal
            synthesize: Whether to synthesize from multiple paths

        Returns:
            Aggregation result with best path and optional synthesis
        """
        # Select best path
        best_path = self.select_best_path(paths)

        if not best_path:
            return {
                "success": False,
                "error": "No completed paths",
                "paths_explored": len(paths),
            }

        result = {
            "success": True,
            "best_path": best_path.to_dict(),
            "best_score": best_path.score,
            "final_result": best_path.final_result,
            "paths_explored": len(paths),
            "paths_completed": len([p for p in paths if p.status == PathStatus.COMPLETED]),
        }

        # Add synthesis if enabled and multiple good paths
        good_paths = [
            p for p in paths
            if p.status == PathStatus.COMPLETED and p.score >= 0.5
        ]

        if synthesize and len(good_paths) > 1 and self.llm:
            try:
                synthesis = await self._synthesize(good_paths, goal, best_path)
                result["synthesis"] = synthesis
            except Exception as e:
                logger.error(f"Synthesis failed: {e}")
                # Continue without synthesis

        return result

    async def _synthesize(
        self,
        paths: list[PathState],
        goal: str,
        best_path: PathState
    ) -> str:
        """Synthesize results from multiple paths.

        Args:
            paths: Completed paths with good scores
            goal: Original task goal
            best_path: The selected best path

        Returns:
            Synthesized result
        """
        # Format path summaries
        path_summaries = []
        for i, path in enumerate(paths):
            summary = f"""
### Approach {i+1}: {path.description}
- Score: {path.score:.2f}
- Steps: {path.metrics.steps_completed}
- Results: {path.final_result[:200] if path.final_result else 'No result'}
"""
            path_summaries.append(summary)

        prompt = SYNTHESIS_PROMPT.format(
            goal=goal,
            path_summaries="\n".join(path_summaries),
            best_path=f"{best_path.description}\n\n{best_path.final_result}"
        )

        response = await self.llm.ask(
            messages=[{"role": "user", "content": prompt}]
        )

        return response.get("content", "")

    def generate_summary(
        self,
        paths: list[PathState],
        goal: str
    ) -> str:
        """Generate a summary of path exploration.

        Args:
            paths: All explored paths
            goal: Original task goal

        Returns:
            Human-readable summary
        """
        lines = [
            "# Tree-of-Thoughts Exploration Summary\n",
            f"**Goal:** {goal[:100]}...\n" if len(goal) > 100 else f"**Goal:** {goal}\n",
            f"**Paths Explored:** {len(paths)}\n",
        ]

        # Status breakdown
        status_counts = {}
        for path in paths:
            status = path.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        lines.append("**Status Breakdown:**")
        for status, count in status_counts.items():
            lines.append(f"- {status}: {count}")

        # Best path
        best = self.select_best_path(paths)
        if best:
            lines.append(f"\n**Selected Approach:** {best.description}")
            lines.append(f"**Score:** {best.score:.2f}")

        # Path details
        lines.append("\n## Path Details\n")
        for i, path in enumerate(sorted(paths, key=lambda p: p.score, reverse=True)):
            emoji = {
                "selected": "🏆",
                "completed": "✅",
                "exploring": "🔄",
                "abandoned": "⏹",
                "failed": "❌",
                "created": "📝",
            }.get(path.status.value, "•")

            lines.append(f"{emoji} **{path.description[:50]}** - Score: {path.score:.2f}")

        return "\n".join(lines)
