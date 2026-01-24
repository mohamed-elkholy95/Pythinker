"""Path explorer for managing multiple exploration paths in Tree-of-Thoughts.

The PathExplorer manages the lifecycle of multiple solution paths:
- Creating paths from strategy suggestions
- Tracking path progress
- Coordinating parallel or sequential exploration
- Abandoning low-scoring paths
"""

import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime
import asyncio

from app.domain.models.path_state import (
    PathState,
    PathStatus,
    PathMetrics,
    TreeOfThoughtsConfig,
)
from app.domain.models.plan import Plan, Step
from app.domain.models.event import BaseEvent, PathEvent
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.models.message import Message


logger = logging.getLogger(__name__)


class PathExplorer:
    """Manages exploration of multiple solution paths.

    The PathExplorer coordinates:
    1. Path creation from strategy suggestions
    2. Sequential/parallel path exploration
    3. Progress tracking and early abandonment
    4. Token budget management across paths
    """

    def __init__(
        self,
        planner: PlannerAgent,
        executor: ExecutionAgent,
        config: Optional[TreeOfThoughtsConfig] = None
    ):
        """Initialize the path explorer.

        Args:
            planner: Planner agent for creating path plans
            executor: Execution agent for running path steps
            config: Tree-of-Thoughts configuration
        """
        self.planner = planner
        self.executor = executor
        self.config = config or TreeOfThoughtsConfig()

        self._paths: List[PathState] = []
        self._token_budget_used: int = 0
        self._active_path: Optional[PathState] = None

    def create_paths(
        self,
        strategies: List[Dict[str, Any]],
        base_message: Message
    ) -> List[PathState]:
        """Create exploration paths from strategy suggestions.

        Args:
            strategies: List of strategy descriptions
            base_message: Original user message

        Returns:
            List of created PathState objects
        """
        paths = []

        for i, strategy in enumerate(strategies[:self.config.max_paths]):
            path = PathState(
                description=strategy.get("description", f"Strategy {i+1}"),
                strategy=strategy.get("description", ""),
            )
            paths.append(path)

            yield PathEvent(
                path_id=path.id,
                action="created",
                description=path.description
            )

        self._paths = paths
        logger.info(f"Created {len(paths)} exploration paths")
        return paths

    async def explore_path(
        self,
        path: PathState,
        message: Message,
        scorer: "PathScorer"
    ) -> AsyncGenerator[BaseEvent, None]:
        """Explore a single path with early abandonment checks.

        Args:
            path: The path to explore
            message: Original user message
            scorer: Path scorer for abandonment decisions

        Yields:
            Events from path exploration
        """
        path.start()
        self._active_path = path

        yield PathEvent(
            path_id=path.id,
            action="exploring",
            description=f"Starting exploration: {path.description}"
        )

        try:
            # Create plan for this path's strategy
            plan = await self._create_path_plan(path, message)

            if not plan or not plan.steps:
                path.fail("Could not create plan for strategy")
                yield PathEvent(
                    path_id=path.id,
                    action="failed",
                    description="Planning failed"
                )
                return

            path.steps = [s.model_dump() for s in plan.steps]

            # Execute steps
            for i, step in enumerate(plan.steps):
                # Check abandonment before each step
                if self._should_abandon(path, scorer):
                    path.abandon(f"Score too low ({path.score:.2f})")
                    yield PathEvent(
                        path_id=path.id,
                        action="abandoned",
                        score=path.score,
                        description=f"Abandoned due to low score"
                    )
                    return

                # Check token budget
                if self._is_budget_exhausted():
                    path.abandon("Token budget exhausted")
                    yield PathEvent(
                        path_id=path.id,
                        action="abandoned",
                        description="Budget exhausted"
                    )
                    return

                # Execute step
                path.current_step_index = i

                async for event in self.executor.execute_step(plan, step, message):
                    yield event

                    # Track token usage (approximate)
                    self._token_budget_used += 500  # Rough estimate per step

                # Record result
                path.add_result(
                    step_id=str(step.id),
                    result=step.result if hasattr(step, 'result') else None,
                    confidence=0.8  # Could be extracted from execution
                )

                # Update score
                path.score = scorer.score(path)

            # Path completed successfully
            path.complete(f"Completed {len(plan.steps)} steps")
            yield PathEvent(
                path_id=path.id,
                action="completed",
                score=path.score,
                description=f"Completed with score {path.score:.2f}"
            )

        except Exception as e:
            logger.error(f"Path {path.id} exploration failed: {e}")
            path.fail(str(e))
            yield PathEvent(
                path_id=path.id,
                action="failed",
                description=f"Error: {str(e)[:100]}"
            )

        finally:
            self._active_path = None

    async def explore_all_paths(
        self,
        message: Message,
        scorer: "PathScorer",
        parallel: bool = False
    ) -> AsyncGenerator[BaseEvent, None]:
        """Explore all paths.

        Args:
            message: Original user message
            scorer: Path scorer
            parallel: Whether to explore paths in parallel

        Yields:
            Events from all path explorations
        """
        if not self._paths:
            logger.warning("No paths to explore")
            return

        if parallel and len(self._paths) > 1:
            # Parallel exploration (more complex, higher resource usage)
            logger.info(f"Starting parallel exploration of {len(self._paths)} paths")
            tasks = []
            for path in self._paths:
                async def explore_and_collect(p):
                    events = []
                    async for event in self.explore_path(p, message, scorer):
                        events.append(event)
                    return events

                tasks.append(explore_and_collect(path))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Yield all events
            for result in results:
                if isinstance(result, list):
                    for event in result:
                        yield event
        else:
            # Sequential exploration (safer, easier to track)
            logger.info(f"Starting sequential exploration of {len(self._paths)} paths")
            for path in self._paths:
                async for event in self.explore_path(path, message, scorer):
                    yield event

                # Stop if budget exhausted
                if self._is_budget_exhausted():
                    logger.warning("Token budget exhausted, stopping exploration")
                    break

    async def _create_path_plan(
        self,
        path: PathState,
        message: Message
    ) -> Optional[Plan]:
        """Create a plan for a specific strategy path.

        Args:
            path: The path needing a plan
            message: Original user message

        Returns:
            Plan for the path or None if creation failed
        """
        try:
            # Augment message with strategy context
            strategy_context = f"\n\nApproach: {path.strategy}"
            augmented_message = Message(
                message=message.message + strategy_context,
                attachments=message.attachments
            )

            # Get plan from planner
            plan = None
            async for event in self.planner.create_plan(augmented_message):
                from app.domain.models.event import PlanEvent, PlanStatus
                if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                    plan = event.plan
                    break

            return plan

        except Exception as e:
            logger.error(f"Failed to create plan for path {path.id}: {e}")
            return None

    def _should_abandon(self, path: PathState, scorer: "PathScorer") -> bool:
        """Check if a path should be abandoned due to low score.

        Args:
            path: The path to check
            scorer: Path scorer

        Returns:
            True if path should be abandoned
        """
        # Don't abandon too early
        if path.metrics.steps_completed < self.config.min_steps_before_abandon:
            return False

        # Check score threshold
        if path.score < self.config.auto_abandon_threshold:
            return True

        return False

    def _is_budget_exhausted(self) -> bool:
        """Check if token budget is exhausted."""
        budget = self.config.token_budget_per_session
        threshold = budget * self.config.budget_exhaustion_threshold
        return self._token_budget_used >= threshold

    def get_paths(self) -> List[PathState]:
        """Get all paths."""
        return self._paths

    def get_active_paths(self) -> List[PathState]:
        """Get currently exploring paths."""
        return [p for p in self._paths if p.status == PathStatus.EXPLORING]

    def get_completed_paths(self) -> List[PathState]:
        """Get successfully completed paths."""
        return [p for p in self._paths if p.status == PathStatus.COMPLETED]

    def get_best_path(self) -> Optional[PathState]:
        """Get the highest-scoring completed path."""
        completed = self.get_completed_paths()
        if not completed:
            return None
        return max(completed, key=lambda p: p.score)

    def reset(self) -> None:
        """Reset explorer state for new task."""
        self._paths = []
        self._token_budget_used = 0
        self._active_path = None
