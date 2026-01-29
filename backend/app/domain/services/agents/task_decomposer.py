"""Task Decomposer using Decomposed Prompting (DecomP) Pattern

Implements the DecomP framework for breaking complex tasks into
simpler, atomic subtasks that can be solved independently.

Research shows DecomP achieves 2-3x accuracy improvement on complex
reasoning tasks by:
1. Breaking tasks into atomic operations
2. Routing subtasks to specialized handlers
3. Maintaining context across subtask solutions
4. Supporting recursive decomposition

Key concepts:
- Atomic Task: Single operation, < 30 seconds, clear input/output
- Subtask Handler: Specialized function/prompt for a subtask type
- Decomposition Tree: Hierarchical structure of task breakdown
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Awaitable, Set
from enum import Enum
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class SubtaskType(str, Enum):
    """Types of subtasks for routing."""
    RESEARCH = "research"           # Information gathering
    ANALYSIS = "analysis"           # Data analysis/reasoning
    CREATION = "creation"           # Creating files/content
    MODIFICATION = "modification"   # Modifying existing content
    VALIDATION = "validation"       # Checking/verifying results
    AGGREGATION = "aggregation"     # Combining multiple results
    COMMUNICATION = "communication" # User interaction


class DecompositionStrategy(str, Enum):
    """Strategies for decomposing tasks."""
    SEQUENTIAL = "sequential"   # Steps depend on each other
    PARALLEL = "parallel"       # Steps can run concurrently
    RECURSIVE = "recursive"     # Subtasks need further decomposition
    ATOMIC = "atomic"           # No decomposition needed


@dataclass
class Subtask:
    """A single subtask in a decomposition."""
    id: str
    description: str
    subtask_type: SubtaskType
    strategy: DecompositionStrategy
    dependencies: List[str] = field(default_factory=list)  # IDs of dependent subtasks
    input_context: Optional[str] = None  # Context from previous subtasks
    expected_output: Optional[str] = None  # What this subtask should produce
    estimated_complexity: float = 0.5  # 0-1 scale
    parent_id: Optional[str] = None  # For recursive decomposition
    children: List["Subtask"] = field(default_factory=list)

    # Execution state
    status: str = "pending"  # pending, in_progress, completed, failed
    result: Optional[str] = None
    error: Optional[str] = None

    def is_atomic(self) -> bool:
        """Check if this subtask is atomic (no further decomposition needed)."""
        return self.strategy == DecompositionStrategy.ATOMIC or len(self.children) == 0

    def is_ready(self, completed_ids: Set[str]) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep_id in completed_ids for dep_id in self.dependencies)


@dataclass
class DecompositionResult:
    """Result of task decomposition."""
    original_task: str
    subtasks: List[Subtask]
    strategy: DecompositionStrategy
    estimated_total_complexity: float
    decomposition_tree_depth: int
    parallel_groups: List[List[str]]  # Groups of subtask IDs that can run in parallel
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def atomic_subtasks(self) -> List[Subtask]:
        """Get all atomic (leaf) subtasks."""
        return [s for s in self.subtasks if s.is_atomic()]

    @property
    def total_subtasks(self) -> int:
        """Total number of subtasks including nested."""
        return len(self.subtasks)


class TaskDecomposer:
    """Decomposes complex tasks into atomic subtasks.

    Usage:
        decomposer = TaskDecomposer()

        result = decomposer.decompose(
            "Research AI trends and create a report with comparisons"
        )

        for subtask in result.atomic_subtasks:
            # Execute each subtask
            result = await execute_subtask(subtask)
            decomposer.mark_completed(subtask.id, result)

        # Get final aggregated result
        final = decomposer.aggregate_results()
    """

    # Patterns for detecting task complexity
    COMPLEXITY_INDICATORS = {
        "research": ["research", "find", "search", "gather", "collect", "discover"],
        "analysis": ["analyze", "compare", "evaluate", "assess", "examine", "review"],
        "creation": ["create", "build", "make", "generate", "write", "develop"],
        "modification": ["update", "modify", "change", "edit", "fix", "improve"],
        "multi_step": ["then", "after that", "next", "finally", "also", "and then"],
    }

    # Subtask type detection patterns
    SUBTASK_TYPE_PATTERNS = {
        SubtaskType.RESEARCH: [
            r'\b(search|find|research|look\s+up|gather|collect)\b',
        ],
        SubtaskType.ANALYSIS: [
            r'\b(analyze|compare|evaluate|assess|review|examine)\b',
        ],
        SubtaskType.CREATION: [
            r'\b(create|write|generate|build|make|develop|design)\b',
        ],
        SubtaskType.MODIFICATION: [
            r'\b(update|modify|change|edit|fix|improve|refactor)\b',
        ],
        SubtaskType.VALIDATION: [
            r'\b(verify|validate|check|test|confirm|ensure)\b',
        ],
        SubtaskType.AGGREGATION: [
            r'\b(combine|merge|aggregate|summarize|compile)\b',
        ],
    }

    # Maximum subtask depth for recursive decomposition
    MAX_DECOMPOSITION_DEPTH = 3

    # Atomic task thresholds
    MAX_ATOMIC_WORDS = 30
    MAX_ATOMIC_ACTIONS = 1

    def __init__(
        self,
        max_depth: int = 3,
        force_atomic_threshold: int = 30,
    ):
        """Initialize the task decomposer.

        Args:
            max_depth: Maximum recursion depth for decomposition
            force_atomic_threshold: Word count below which tasks are atomic
        """
        self.max_depth = max_depth
        self.force_atomic_threshold = force_atomic_threshold

        # Compile regex patterns
        self._type_patterns = {
            k: [re.compile(p, re.IGNORECASE) for p in patterns]
            for k, patterns in self.SUBTASK_TYPE_PATTERNS.items()
        }

        # Track decomposed subtasks
        self._subtasks: Dict[str, Subtask] = {}
        self._completed_ids: Set[str] = set()
        self._results: Dict[str, str] = {}

    def decompose(
        self,
        task: str,
        context: Optional[str] = None,
        depth: int = 0,
    ) -> DecompositionResult:
        """Decompose a task into subtasks.

        Args:
            task: The task description to decompose
            context: Optional context from parent task
            depth: Current recursion depth

        Returns:
            DecompositionResult with subtasks
        """
        if not task:
            return DecompositionResult(
                original_task=task,
                subtasks=[],
                strategy=DecompositionStrategy.ATOMIC,
                estimated_total_complexity=0,
                decomposition_tree_depth=0,
                parallel_groups=[],
            )

        # Check if task is already atomic
        if self._is_atomic(task) or depth >= self.max_depth:
            subtask = self._create_atomic_subtask(task, context)
            self._subtasks[subtask.id] = subtask

            return DecompositionResult(
                original_task=task,
                subtasks=[subtask],
                strategy=DecompositionStrategy.ATOMIC,
                estimated_total_complexity=subtask.estimated_complexity,
                decomposition_tree_depth=depth,
                parallel_groups=[[subtask.id]],
            )

        # Decompose into subtasks
        subtasks = self._extract_subtasks(task, context, depth)

        if len(subtasks) <= 1:
            # Couldn't decompose meaningfully
            subtask = self._create_atomic_subtask(task, context)
            self._subtasks[subtask.id] = subtask

            return DecompositionResult(
                original_task=task,
                subtasks=[subtask],
                strategy=DecompositionStrategy.ATOMIC,
                estimated_total_complexity=subtask.estimated_complexity,
                decomposition_tree_depth=depth,
                parallel_groups=[[subtask.id]],
            )

        # Store subtasks
        for subtask in subtasks:
            self._subtasks[subtask.id] = subtask

        # Determine overall strategy
        strategy = self._determine_strategy(subtasks)

        # Create parallel groups
        parallel_groups = self._create_parallel_groups(subtasks)

        # Calculate total complexity
        total_complexity = sum(s.estimated_complexity for s in subtasks) / len(subtasks)

        logger.info(
            f"Decomposed task into {len(subtasks)} subtasks "
            f"(strategy={strategy.value}, depth={depth})"
        )

        return DecompositionResult(
            original_task=task,
            subtasks=subtasks,
            strategy=strategy,
            estimated_total_complexity=total_complexity,
            decomposition_tree_depth=depth,
            parallel_groups=parallel_groups,
        )

    def _is_atomic(self, task: str) -> bool:
        """Check if a task is atomic (doesn't need decomposition)."""
        words = task.split()

        # Very short tasks are atomic
        if len(words) < self.force_atomic_threshold:
            return True

        # Count action verbs
        action_count = 0
        for category, indicators in self.COMPLEXITY_INDICATORS.items():
            for indicator in indicators:
                if indicator in task.lower():
                    action_count += 1

        # Single action is atomic
        if action_count <= 1:
            return True

        # No multi-step indicators
        if not any(ind in task.lower() for ind in self.COMPLEXITY_INDICATORS["multi_step"]):
            # Check for list markers
            if not re.search(r'(?:^|\n)\s*(?:\d+[.\)]|[-*])\s', task):
                return True

        return False

    def _create_atomic_subtask(
        self,
        task: str,
        context: Optional[str],
    ) -> Subtask:
        """Create an atomic subtask."""
        subtask_type = self._detect_subtask_type(task)
        complexity = self._estimate_complexity(task)

        return Subtask(
            id=str(uuid.uuid4())[:8],
            description=task.strip(),
            subtask_type=subtask_type,
            strategy=DecompositionStrategy.ATOMIC,
            input_context=context,
            estimated_complexity=complexity,
        )

    def _extract_subtasks(
        self,
        task: str,
        context: Optional[str],
        depth: int,
    ) -> List[Subtask]:
        """Extract subtasks from a complex task."""
        subtasks = []

        # Try to extract from numbered list
        numbered = re.findall(r'(?:^|\n)\s*(\d+)[.\)]\s*(.+?)(?=\n\s*\d+[.\)]|\n\n|\Z)', task, re.DOTALL)
        if numbered:
            prev_id = None
            for num, item in numbered:
                subtask = self._create_subtask_from_item(item.strip(), context, depth, prev_id)
                subtasks.append(subtask)
                prev_id = subtask.id
            return subtasks

        # Try to extract from bullet list
        bullets = re.findall(r'(?:^|\n)\s*[-*]\s*(.+?)(?=\n\s*[-*]|\n\n|\Z)', task, re.DOTALL)
        if bullets:
            for item in bullets:
                subtask = self._create_subtask_from_item(item.strip(), context, depth)
                subtasks.append(subtask)
            return subtasks

        # Try to split on conjunctions
        parts = re.split(r'\s+(?:and\s+then|then|after\s+that|next|finally)\s+', task, flags=re.IGNORECASE)
        if len(parts) > 1:
            prev_id = None
            for part in parts:
                if part.strip():
                    subtask = self._create_subtask_from_item(part.strip(), context, depth, prev_id)
                    subtasks.append(subtask)
                    prev_id = subtask.id
            return subtasks

        # Try to split on "and" for parallel tasks
        parts = re.split(r'\s+and\s+', task, flags=re.IGNORECASE)
        if len(parts) > 1 and all(len(p.split()) > 3 for p in parts):
            for part in parts:
                if part.strip():
                    subtask = self._create_subtask_from_item(part.strip(), context, depth)
                    # No dependencies - parallel
                    subtasks.append(subtask)
            return subtasks

        return subtasks

    def _create_subtask_from_item(
        self,
        item: str,
        context: Optional[str],
        depth: int,
        depends_on: Optional[str] = None,
    ) -> Subtask:
        """Create a subtask from an extracted item."""
        subtask_type = self._detect_subtask_type(item)
        complexity = self._estimate_complexity(item)

        # Check if this subtask needs further decomposition
        needs_decomposition = not self._is_atomic(item) and depth < self.max_depth - 1
        strategy = DecompositionStrategy.RECURSIVE if needs_decomposition else DecompositionStrategy.ATOMIC

        subtask = Subtask(
            id=str(uuid.uuid4())[:8],
            description=item,
            subtask_type=subtask_type,
            strategy=strategy,
            dependencies=[depends_on] if depends_on else [],
            input_context=context,
            estimated_complexity=complexity,
        )

        # Recursively decompose if needed
        if needs_decomposition:
            child_result = self.decompose(item, context, depth + 1)
            subtask.children = child_result.subtasks
            for child in subtask.children:
                child.parent_id = subtask.id

        return subtask

    def _detect_subtask_type(self, text: str) -> SubtaskType:
        """Detect the type of a subtask."""
        text_lower = text.lower()

        for subtask_type, patterns in self._type_patterns.items():
            for pattern in patterns:
                if pattern.search(text_lower):
                    return subtask_type

        return SubtaskType.CREATION  # Default

    def _estimate_complexity(self, text: str) -> float:
        """Estimate complexity of a subtask (0-1 scale)."""
        # Base complexity on length
        words = len(text.split())
        length_score = min(words / 100, 1.0)

        # Complexity indicators
        complexity_words = [
            "complex", "detailed", "comprehensive", "thorough",
            "multiple", "various", "all", "every",
        ]
        complexity_boost = sum(0.1 for w in complexity_words if w in text.lower())

        # Action verb count
        action_count = 0
        for patterns in self._type_patterns.values():
            for pattern in patterns:
                if pattern.search(text):
                    action_count += 1

        action_score = min(action_count * 0.15, 0.5)

        return min(length_score + complexity_boost + action_score, 1.0)

    def _determine_strategy(self, subtasks: List[Subtask]) -> DecompositionStrategy:
        """Determine the overall decomposition strategy."""
        if not subtasks:
            return DecompositionStrategy.ATOMIC

        # If all have dependencies, it's sequential
        if all(s.dependencies for s in subtasks[1:]):
            return DecompositionStrategy.SEQUENTIAL

        # If none have dependencies, it's parallel
        if not any(s.dependencies for s in subtasks):
            return DecompositionStrategy.PARALLEL

        # Mixed - some parallel, some sequential
        return DecompositionStrategy.SEQUENTIAL  # Default to safer option

    def _create_parallel_groups(self, subtasks: List[Subtask]) -> List[List[str]]:
        """Create groups of subtasks that can run in parallel."""
        groups = []
        remaining = list(subtasks)
        completed_ids: Set[str] = set()

        while remaining:
            # Find all subtasks with satisfied dependencies
            ready = [s for s in remaining if s.is_ready(completed_ids)]

            if not ready:
                # Circular dependency or bug - add remaining sequentially
                groups.extend([[s.id] for s in remaining])
                break

            # Add ready subtasks as a parallel group
            group_ids = [s.id for s in ready]
            groups.append(group_ids)

            # Mark as completed for next iteration
            completed_ids.update(group_ids)
            remaining = [s for s in remaining if s.id not in completed_ids]

        return groups

    def mark_completed(self, subtask_id: str, result: str) -> None:
        """Mark a subtask as completed with its result.

        Args:
            subtask_id: ID of the completed subtask
            result: Result/output of the subtask
        """
        if subtask_id in self._subtasks:
            self._subtasks[subtask_id].status = "completed"
            self._subtasks[subtask_id].result = result
            self._completed_ids.add(subtask_id)
            self._results[subtask_id] = result

            logger.debug(f"Subtask {subtask_id} completed")

    def mark_failed(self, subtask_id: str, error: str) -> None:
        """Mark a subtask as failed.

        Args:
            subtask_id: ID of the failed subtask
            error: Error message
        """
        if subtask_id in self._subtasks:
            self._subtasks[subtask_id].status = "failed"
            self._subtasks[subtask_id].error = error

            logger.warning(f"Subtask {subtask_id} failed: {error}")

    def get_next_ready_subtasks(self) -> List[Subtask]:
        """Get subtasks that are ready to execute.

        Returns:
            List of subtasks with satisfied dependencies
        """
        return [
            s for s in self._subtasks.values()
            if s.status == "pending" and s.is_ready(self._completed_ids)
        ]

    def get_context_for_subtask(self, subtask_id: str) -> str:
        """Get accumulated context for a subtask from completed dependencies.

        Args:
            subtask_id: ID of the subtask

        Returns:
            Combined context from completed dependencies
        """
        subtask = self._subtasks.get(subtask_id)
        if not subtask:
            return ""

        context_parts = []

        # Add results from dependencies
        for dep_id in subtask.dependencies:
            if dep_id in self._results:
                dep_subtask = self._subtasks.get(dep_id)
                if dep_subtask:
                    context_parts.append(
                        f"[{dep_subtask.description[:50]}...]: {self._results[dep_id][:500]}"
                    )

        return "\n\n".join(context_parts)

    def aggregate_results(self) -> str:
        """Aggregate results from all completed subtasks.

        Returns:
            Combined results string
        """
        results = []

        for subtask_id, subtask in self._subtasks.items():
            if subtask.status == "completed" and subtask.result:
                results.append(f"## {subtask.description[:100]}\n{subtask.result}")

        return "\n\n".join(results)

    def get_progress(self) -> Dict[str, Any]:
        """Get decomposition progress."""
        total = len(self._subtasks)
        completed = len(self._completed_ids)
        failed = sum(1 for s in self._subtasks.values() if s.status == "failed")

        return {
            "total_subtasks": total,
            "completed": completed,
            "failed": failed,
            "pending": total - completed - failed,
            "progress_percent": (completed / total * 100) if total > 0 else 100,
        }

    def reset(self) -> None:
        """Reset the decomposer state."""
        self._subtasks.clear()
        self._completed_ids.clear()
        self._results.clear()


# Singleton instance
_decomposer: Optional[TaskDecomposer] = None


def get_task_decomposer() -> TaskDecomposer:
    """Get the global task decomposer instance."""
    global _decomposer
    if _decomposer is None:
        _decomposer = TaskDecomposer()
    return _decomposer


def decompose_task(task: str, context: Optional[str] = None) -> DecompositionResult:
    """Convenience function to decompose a task.

    Args:
        task: Task description to decompose
        context: Optional context

    Returns:
        DecompositionResult
    """
    return get_task_decomposer().decompose(task, context)
