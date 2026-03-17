"""
Tree-of-Thoughts reasoning module.

This module provides enhanced Tree-of-Thoughts exploration with:
- Better pruning strategies
- Backtracking support
- Value heuristics for path evaluation
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from app.domain.exceptions.base import ConfigurationException
from app.domain.external.llm import LLM
from app.domain.models.thought import ThoughtType

logger = logging.getLogger(__name__)


class NodeState(str, Enum):
    """State of a thought tree node."""

    UNEXPLORED = "unexplored"
    EXPLORING = "exploring"
    EVALUATED = "evaluated"
    PRUNED = "pruned"
    SELECTED = "selected"
    DEAD_END = "dead_end"


class ExplorationMode(str, Enum):
    """Mode of tree exploration."""

    FULL = "full"  # Full ToT with all features
    SHALLOW = "shallow"  # Limited depth (2 levels)
    LINEAR = "linear"  # Single path (fallback)
    BEAM = "beam"  # Beam search with top-k paths


@dataclass
class ThoughtNode:
    """A node in the thought tree."""

    id: str
    content: str
    thought_type: ThoughtType
    parent_id: str | None = None
    children: list["ThoughtNode"] = field(default_factory=list)
    state: NodeState = NodeState.UNEXPLORED
    value: float = 0.0  # Heuristic value for pruning
    confidence: float = 0.5
    depth: int = 0
    is_terminal: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_child(self, child: "ThoughtNode") -> None:
        """Add a child node."""
        child.parent_id = self.id
        child.depth = self.depth + 1
        self.children.append(child)

    def is_leaf(self) -> bool:
        """Check if this is a leaf node."""
        return len(self.children) == 0

    def is_promising(self, threshold: float = 0.4) -> bool:
        """Check if this node is promising enough to explore."""
        return self.value >= threshold and self.state != NodeState.PRUNED


@dataclass
class ThoughtPath:
    """A path through the thought tree."""

    nodes: list[ThoughtNode]
    total_value: float = 0.0
    average_confidence: float = 0.0
    is_complete: bool = False

    def __post_init__(self) -> None:
        """Calculate path metrics."""
        if self.nodes:
            self.total_value = sum(n.value for n in self.nodes)
            self.average_confidence = sum(n.confidence for n in self.nodes) / len(self.nodes)

    def get_conclusion(self) -> str | None:
        """Get the conclusion from the final node."""
        if self.nodes and self.nodes[-1].is_terminal:
            return self.nodes[-1].content
        return None


@dataclass
class ExplorationResult:
    """Result of tree exploration."""

    best_path: ThoughtPath | None
    all_paths: list[ThoughtPath]
    nodes_explored: int
    nodes_pruned: int
    max_depth_reached: int
    exploration_mode: ExplorationMode


class ValueFunction:
    """Value function for evaluating thought nodes.

    Uses heuristics to estimate the promise of a thought path
    for guiding exploration and pruning decisions.
    """

    def __init__(self) -> None:
        """Initialize the value function."""
        # Weights for different factors
        self.progress_weight = 0.3
        self.confidence_weight = 0.25
        self.novelty_weight = 0.2
        self.depth_penalty_weight = 0.15
        self.evidence_weight = 0.1

    def evaluate(
        self,
        node: ThoughtNode,
        context: dict[str, Any] | None = None,
    ) -> float:
        """Evaluate a node's value.

        Args:
            node: The node to evaluate
            context: Optional context for evaluation

        Returns:
            Value score between 0 and 1
        """
        # Base value from confidence
        value = node.confidence * self.confidence_weight

        # Progress signal based on thought type
        progress = self._calculate_progress_signal(node)
        value += progress * self.progress_weight

        # Novelty (don't repeat same type consecutively)
        novelty = self._calculate_novelty(node)
        value += novelty * self.novelty_weight

        # Depth penalty (prefer shorter paths)
        depth_penalty = min(node.depth * 0.05, 0.3)
        value -= depth_penalty * self.depth_penalty_weight

        # Evidence bonus
        if node.metadata.get("has_evidence"):
            value += self.evidence_weight

        return max(0.0, min(1.0, value))

    def _calculate_progress_signal(self, node: ThoughtNode) -> float:
        """Calculate progress signal based on thought type."""
        progress_scores = {
            ThoughtType.OBSERVATION: 0.3,  # Early stage
            ThoughtType.ANALYSIS: 0.4,
            ThoughtType.HYPOTHESIS: 0.5,
            ThoughtType.INFERENCE: 0.6,
            ThoughtType.EVALUATION: 0.7,
            ThoughtType.DECISION: 0.9,  # Near conclusion
            ThoughtType.REFLECTION: 0.5,
            ThoughtType.UNCERTAINTY: 0.3,
        }
        return progress_scores.get(node.thought_type, 0.5)

    def _calculate_novelty(self, node: ThoughtNode) -> float:
        """Calculate novelty score."""
        # High novelty for decision/conclusion nodes
        if node.thought_type == ThoughtType.DECISION:
            return 0.8
        # Medium for evaluation
        if node.thought_type == ThoughtType.EVALUATION:
            return 0.6
        return 0.4


class PruningStrategy:
    """Strategy for pruning unpromising branches."""

    def __init__(
        self,
        value_threshold: float = 0.3,
        max_children: int = 3,
        beam_width: int = 2,
    ) -> None:
        """Initialize pruning strategy.

        Args:
            value_threshold: Minimum value to keep a node
            max_children: Maximum children per node
            beam_width: Number of paths to keep in beam search
        """
        self.value_threshold = value_threshold
        self.max_children = max_children
        self.beam_width = beam_width

    def should_prune(self, node: ThoughtNode) -> bool:
        """Check if a node should be pruned."""
        # Prune low-value nodes
        if node.value < self.value_threshold:
            return True

        # Prune very uncertain nodes
        if node.confidence < 0.2:
            return True

        # Prune redundant uncertainty nodes
        return node.thought_type == ThoughtType.UNCERTAINTY and node.depth > 3

    def select_children_to_explore(
        self,
        children: list[ThoughtNode],
    ) -> list[ThoughtNode]:
        """Select which children to explore."""
        if not children:
            return []

        # Sort by value
        sorted_children = sorted(children, key=lambda n: n.value, reverse=True)

        # Keep top max_children
        return sorted_children[: self.max_children]

    def select_beam_paths(
        self,
        paths: list[ThoughtPath],
    ) -> list[ThoughtPath]:
        """Select paths for beam search."""
        if not paths:
            return []

        # Sort by total value
        sorted_paths = sorted(paths, key=lambda p: p.total_value, reverse=True)

        # Keep top beam_width
        return sorted_paths[: self.beam_width]


class ThoughtTreeExplorer:
    """Explorer for Tree-of-Thoughts reasoning.

    Implements enhanced ToT with:
    - Breadth-first search with beam pruning
    - Value function for path evaluation
    - Backtracking on dead-ends
    - Multiple exploration modes
    """

    def __init__(
        self,
        llm: LLM,
        value_function: ValueFunction | None = None,
        pruning_strategy: PruningStrategy | None = None,
        max_depth: int = 5,
        max_nodes: int = 50,
    ) -> None:
        """Initialize the explorer.

        Args:
            llm: LLM for generating thoughts
            value_function: Value function for evaluation
            pruning_strategy: Pruning strategy
            max_depth: Maximum tree depth
            max_nodes: Maximum nodes to explore
        """
        self.llm = llm
        self.value_function = value_function or ValueFunction()
        self.pruning_strategy = pruning_strategy or PruningStrategy()
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self._node_counter = 0

    async def explore(
        self,
        problem: str,
        mode: ExplorationMode = ExplorationMode.BEAM,
        context: dict[str, Any] | None = None,
    ) -> ExplorationResult:
        """Explore thought tree for a problem.

        Args:
            problem: The problem to explore
            mode: Exploration mode
            context: Optional context

        Returns:
            Exploration result with best path
        """
        logger.info(f"Starting ToT exploration: mode={mode.value}, problem={problem[:50]}...")

        # Create root node
        root = self._create_root_node(problem)

        # Track statistics
        nodes_explored = 0
        nodes_pruned = 0
        max_depth_reached = 0

        # Collect all paths
        all_paths: list[ThoughtPath] = []

        if mode == ExplorationMode.LINEAR:
            # Simple linear exploration
            path = await self._explore_linear(root, problem, context)
            all_paths.append(path)
            nodes_explored = len(path.nodes)
            max_depth_reached = path.nodes[-1].depth if path.nodes else 0

        elif mode == ExplorationMode.SHALLOW:
            # Shallow exploration (depth 2)
            paths, explored, pruned, depth = await self._explore_bfs(root, problem, context, max_depth=2)
            all_paths.extend(paths)
            nodes_explored = explored
            nodes_pruned = pruned
            max_depth_reached = depth

        elif mode == ExplorationMode.BEAM:
            # Beam search exploration
            paths, explored, pruned, depth = await self._explore_beam(root, problem, context)
            all_paths.extend(paths)
            nodes_explored = explored
            nodes_pruned = pruned
            max_depth_reached = depth

        else:  # FULL
            # Full exploration
            paths, explored, pruned, depth = await self._explore_bfs(root, problem, context)
            all_paths.extend(paths)
            nodes_explored = explored
            nodes_pruned = pruned
            max_depth_reached = depth

        # Find best path
        best_path = None
        if all_paths:
            complete_paths = [p for p in all_paths if p.is_complete]
            if complete_paths:
                best_path = max(complete_paths, key=lambda p: p.total_value)
            else:
                best_path = max(all_paths, key=lambda p: p.total_value)

        logger.info(
            f"ToT exploration complete: explored={nodes_explored}, pruned={nodes_pruned}, paths={len(all_paths)}"
        )

        return ExplorationResult(
            best_path=best_path,
            all_paths=all_paths,
            nodes_explored=nodes_explored,
            nodes_pruned=nodes_pruned,
            max_depth_reached=max_depth_reached,
            exploration_mode=mode,
        )

    async def _explore_linear(
        self,
        root: ThoughtNode,
        problem: str,
        context: dict[str, Any] | None,
    ) -> ThoughtPath:
        """Linear single-path exploration."""
        nodes = [root]
        current = root

        while not current.is_terminal and current.depth < self.max_depth:
            # Generate single next thought
            next_thoughts = await self._generate_thoughts(current, problem, context, n=1)
            if not next_thoughts:
                break

            next_node = next_thoughts[0]
            current.add_child(next_node)
            nodes.append(next_node)
            current = next_node

        current.is_terminal = True
        return ThoughtPath(nodes=nodes, is_complete=True)

    async def _explore_bfs(
        self,
        root: ThoughtNode,
        problem: str,
        context: dict[str, Any] | None,
        max_depth: int | None = None,
    ) -> tuple[list[ThoughtPath], int, int, int]:
        """Breadth-first exploration with pruning."""
        max_depth = max_depth or self.max_depth
        frontier = [root]
        nodes_explored = 0
        nodes_pruned = 0
        max_depth_reached = 0

        while frontier and nodes_explored < self.max_nodes:
            current = frontier.pop(0)
            nodes_explored += 1
            max_depth_reached = max(max_depth_reached, current.depth)

            if current.depth >= max_depth:
                current.is_terminal = True
                continue

            # Generate children
            children = await self._generate_thoughts(current, problem, context)

            for child in children:
                # Evaluate and potentially prune
                child.value = self.value_function.evaluate(child, context)

                if self.pruning_strategy.should_prune(child):
                    child.state = NodeState.PRUNED
                    nodes_pruned += 1
                else:
                    current.add_child(child)
                    frontier.append(child)

        # Extract all paths
        paths = self._extract_paths(root)
        return paths, nodes_explored, nodes_pruned, max_depth_reached

    async def _explore_beam(
        self,
        root: ThoughtNode,
        problem: str,
        context: dict[str, Any] | None,
    ) -> tuple[list[ThoughtPath], int, int, int]:
        """Beam search exploration."""
        beam_paths = [ThoughtPath(nodes=[root])]
        nodes_explored = 0
        nodes_pruned = 0
        max_depth_reached = 0

        for _depth in range(self.max_depth):
            new_paths = []

            for path in beam_paths:
                current = path.nodes[-1]
                nodes_explored += 1
                max_depth_reached = max(max_depth_reached, current.depth)

                # Generate children
                children = await self._generate_thoughts(current, problem, context)

                for child in children:
                    child.value = self.value_function.evaluate(child, context)

                    if self.pruning_strategy.should_prune(child):
                        nodes_pruned += 1
                        continue

                    current.add_child(child)
                    new_path = ThoughtPath(nodes=[*path.nodes, child])
                    new_paths.append(new_path)

            if not new_paths:
                break

            # Keep only top beam_width paths
            beam_paths = self.pruning_strategy.select_beam_paths(new_paths)

        # Mark terminal nodes
        for path in beam_paths:
            if path.nodes:
                path.nodes[-1].is_terminal = True
                path.is_complete = True

        return beam_paths, nodes_explored, nodes_pruned, max_depth_reached

    async def _generate_thoughts(
        self,
        parent: ThoughtNode,
        problem: str,
        context: dict[str, Any] | None,
        n: int = 3,
    ) -> list[ThoughtNode]:
        """Generate next thoughts from a node."""
        prompt = self._build_generation_prompt(parent, problem)

        messages = [
            {"role": "system", "content": "Generate possible next thoughts for reasoning."},
            {"role": "user", "content": prompt},
        ]

        thoughts = []
        try:
            for _i in range(n):
                response = await self.llm.ask(messages, tools=None, response_format=None)
                content = response.get("content", "")

                if content:
                    thought_type = self._infer_thought_type(content, parent)
                    node = self._create_node(content, thought_type)
                    thoughts.append(node)

        except Exception as e:
            logger.warning(f"Thought generation failed: {e}")

        return thoughts

    def _create_root_node(self, problem: str) -> ThoughtNode:
        """Create the root node for a problem."""
        self._node_counter += 1
        return ThoughtNode(
            id=f"node_{self._node_counter}",
            content=f"Problem: {problem}",
            thought_type=ThoughtType.OBSERVATION,
            state=NodeState.EXPLORED,
            value=0.5,
            depth=0,
        )

    def _create_node(self, content: str, thought_type: ThoughtType) -> ThoughtNode:
        """Create a new thought node."""
        self._node_counter += 1
        return ThoughtNode(
            id=f"node_{self._node_counter}",
            content=content,
            thought_type=thought_type,
        )

    def _build_generation_prompt(self, parent: ThoughtNode, problem: str) -> str:
        """Build prompt for generating next thoughts."""
        return f"""Problem: {problem}

Current thought: {parent.content}

What are the possible next reasoning steps? Generate a single next thought that:
- Builds on the current thought
- Makes progress toward solving the problem
- Is specific and actionable

Provide just the next thought, no explanation."""

    def _infer_thought_type(self, content: str, parent: ThoughtNode) -> ThoughtType:
        """Infer thought type from content and parent."""
        content_lower = content.lower()

        # Check for decision indicators
        if any(w in content_lower for w in ["should", "will", "decision", "choose"]):
            return ThoughtType.DECISION

        # Check for evaluation
        if any(w in content_lower for w in ["compare", "better", "evaluate", "assess"]):
            return ThoughtType.EVALUATION

        # Check for inference
        if any(w in content_lower for w in ["therefore", "thus", "means", "implies"]):
            return ThoughtType.INFERENCE

        # Progress based on parent
        type_progression = {
            ThoughtType.OBSERVATION: ThoughtType.ANALYSIS,
            ThoughtType.ANALYSIS: ThoughtType.HYPOTHESIS,
            ThoughtType.HYPOTHESIS: ThoughtType.EVALUATION,
            ThoughtType.EVALUATION: ThoughtType.DECISION,
        }

        return type_progression.get(parent.thought_type, ThoughtType.ANALYSIS)

    def _extract_paths(self, root: ThoughtNode) -> list[ThoughtPath]:
        """Extract all paths from tree."""
        paths = []

        def traverse(node: ThoughtNode, current_path: list[ThoughtNode]) -> None:
            current_path = [*current_path, node]

            if node.is_leaf() or node.is_terminal:
                paths.append(
                    ThoughtPath(
                        nodes=current_path,
                        is_complete=node.is_terminal,
                    )
                )
            else:
                for child in node.children:
                    traverse(child, current_path)

        traverse(root, [])
        return paths


# Global instance
_explorer: ThoughtTreeExplorer | None = None


def get_tree_explorer(llm: LLM | None = None) -> ThoughtTreeExplorer:
    """Get or create the global tree explorer."""
    global _explorer
    if _explorer is None:
        if llm is None:
            raise ConfigurationException("LLM required to initialize tree explorer")
        _explorer = ThoughtTreeExplorer(llm)
    return _explorer


def reset_tree_explorer() -> None:
    """Reset the global tree explorer."""
    global _explorer
    _explorer = None
