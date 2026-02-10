"""Graph-based workflow engine for declarative agent orchestration.

This module provides a lightweight workflow abstraction
that enables declarative definition of agent workflows as directed graphs.

Key features:
- Declarative node and edge definitions
- Conditional routing based on state
- Cycle support for iterative workflows
- State checkpointing for recovery
- Event streaming from node execution

Usage:
    graph = WorkflowGraph("plan-act")

    # Define nodes
    graph.add_node("planning", planning_handler)
    graph.add_node("executing", execution_handler)
    graph.add_node("updating", update_handler)
    graph.add_node("summarizing", summarize_handler)

    # Define edges with conditions
    graph.add_edge("planning", "executing")
    graph.add_conditional_edge("executing", route_after_execution)
    graph.add_edge("updating", "executing")
    graph.add_edge("summarizing", END)

    # Run the workflow
    async for event in graph.run(initial_state):
        yield event
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.domain.models.event import BaseEvent

logger = logging.getLogger(__name__)


# Special node names
START = "__start__"
END = "__end__"


class NodeStatus(str, Enum):
    """Status of a workflow node execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowState:
    """Base state class for workflows.

    Subclass this to define custom state for your workflow.
    The state is passed between nodes and can be mutated.
    """

    current_node: str = START
    previous_node: str | None = None
    iteration_count: int = 0
    max_iterations: int = 100
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def should_continue(self) -> bool:
        """Check if workflow should continue executing."""
        return self.current_node != END and self.error is None and self.iteration_count < self.max_iterations

    def transition_to(self, next_node: str) -> None:
        """Transition to a new node."""
        self.previous_node = self.current_node
        self.current_node = next_node
        self.iteration_count += 1


# Type aliases
NodeHandler = Callable[[WorkflowState], AsyncGenerator[BaseEvent, None]]
ConditionalRouter = Callable[[WorkflowState], str | Awaitable[str]]


@dataclass
class Node:
    """A node in the workflow graph."""

    name: str
    handler: NodeHandler
    description: str = ""


@dataclass
class Edge:
    """An edge connecting two nodes."""

    from_node: str
    to_node: str
    condition: str | None = None  # Human-readable condition description


@dataclass
class ConditionalEdge:
    """A conditional edge that routes based on state."""

    from_node: str
    router: ConditionalRouter
    possible_targets: list[str] = field(default_factory=list)


@dataclass
class NodeExecution:
    """Record of a node execution for debugging/tracing."""

    node_name: str
    status: NodeStatus
    duration_ms: float = 0
    events_emitted: int = 0
    error: str | None = None


class WorkflowGraph:
    """A directed graph representing an agent workflow.

    The graph consists of nodes (handlers) connected by edges (transitions).
    Execution starts at START and continues until END is reached or an error occurs.
    """

    def __init__(self, name: str, description: str = ""):
        """Initialize a workflow graph.

        Args:
            name: Name of the workflow
            description: Human-readable description
        """
        self.name = name
        self.description = description
        self._nodes: dict[str, Node] = {}
        self._edges: dict[str, list[Edge]] = {}
        self._conditional_edges: dict[str, ConditionalEdge] = {}
        self._entry_point: str | None = None
        self._execution_history: list[NodeExecution] = []

    def add_node(self, name: str, handler: NodeHandler, description: str = "") -> "WorkflowGraph":
        """Add a node to the graph.

        Args:
            name: Unique name for the node
            handler: Async generator function that processes state and yields events
            description: Human-readable description

        Returns:
            Self for chaining
        """
        if name in (START, END):
            raise ValueError(f"Cannot use reserved node name: {name}")

        self._nodes[name] = Node(name=name, handler=handler, description=description)

        # Initialize edge list for this node
        if name not in self._edges:
            self._edges[name] = []

        return self

    def add_edge(self, from_node: str, to_node: str, condition: str | None = None) -> "WorkflowGraph":
        """Add a direct edge between nodes.

        Args:
            from_node: Source node name (or START)
            to_node: Target node name (or END)
            condition: Human-readable condition description

        Returns:
            Self for chaining
        """
        # Validate nodes exist (except START/END)
        if from_node not in (START, END) and from_node not in self._nodes:
            raise ValueError(f"Source node not found: {from_node}")
        if to_node not in (START, END) and to_node not in self._nodes:
            raise ValueError(f"Target node not found: {to_node}")

        edge = Edge(from_node=from_node, to_node=to_node, condition=condition)

        if from_node not in self._edges:
            self._edges[from_node] = []
        self._edges[from_node].append(edge)

        return self

    def add_conditional_edge(
        self, from_node: str, router: ConditionalRouter, possible_targets: list[str] | None = None
    ) -> "WorkflowGraph":
        """Add a conditional edge that routes based on state.

        Args:
            from_node: Source node name
            router: Function that returns the next node name based on state
            possible_targets: List of possible target nodes (for validation/visualization)

        Returns:
            Self for chaining
        """
        if from_node not in self._nodes:
            raise ValueError(f"Source node not found: {from_node}")

        self._conditional_edges[from_node] = ConditionalEdge(
            from_node=from_node, router=router, possible_targets=possible_targets or []
        )

        return self

    def set_entry_point(self, node_name: str) -> "WorkflowGraph":
        """Set the entry point node (first node after START).

        Args:
            node_name: Name of the entry point node

        Returns:
            Self for chaining
        """
        if node_name not in self._nodes:
            raise ValueError(f"Entry point node not found: {node_name}")
        self._entry_point = node_name
        self.add_edge(START, node_name)
        return self

    def _get_next_node(self, state: WorkflowState) -> str | None:
        """Determine the next node based on current state and edges."""
        current = state.current_node

        # Check for conditional edge first
        if current in self._conditional_edges:
            return None  # Will be resolved asynchronously

        # Check for direct edges
        edges = self._edges.get(current, [])
        if edges:
            # For now, take the first edge (could add priority/conditions later)
            return edges[0].to_node

        return None

    async def _resolve_next_node(self, state: WorkflowState) -> str:
        """Resolve the next node, handling conditional routing."""
        current = state.current_node

        # Check for conditional edge
        if current in self._conditional_edges:
            conditional = self._conditional_edges[current]
            result = conditional.router(state)
            if asyncio.iscoroutine(result):
                result = await result
            if conditional.possible_targets and result not in conditional.possible_targets and result != END:
                raise ValueError(
                    f"Conditional router returned invalid target '{result}' for node '{current}'. "
                    f"Allowed: {conditional.possible_targets}"
                )
            return result

        # Check for direct edges
        edges = self._edges.get(current, [])
        if edges:
            return edges[0].to_node

        # No outgoing edge - end the workflow
        return END

    async def run(
        self,
        initial_state: WorkflowState,
        on_node_start: Callable[[str, WorkflowState], None] | None = None,
        on_node_end: Callable[[str, WorkflowState, NodeExecution], None] | None = None,
        checkpoint_manager: Any | None = None,
        checkpoint_interval: int = 1,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute the workflow graph.

        Args:
            initial_state: Initial workflow state
            on_node_start: Optional callback when node starts
            on_node_end: Optional callback when node completes

        Yields:
            Events from node handlers
        """
        state = initial_state
        self._execution_history = []

        # Start from entry point
        if self._entry_point:
            state.transition_to(self._entry_point)
        elif self._edges.get(START):
            state.transition_to(self._edges[START][0].to_node)
        else:
            raise ValueError("No entry point defined for workflow")

        while state.should_continue():
            current_node = state.current_node

            # Get the node handler
            node = self._nodes.get(current_node)
            if not node:
                logger.error(f"Node not found: {current_node}")
                state.error = f"Node not found: {current_node}"
                break

            # Notify node start
            if on_node_start:
                on_node_start(current_node, state)

            # Execute node
            import time

            start_time = time.time()
            execution = NodeExecution(node_name=current_node, status=NodeStatus.RUNNING)

            try:
                logger.debug(f"Workflow '{self.name}' executing node: {current_node}")

                events_count = 0
                async for event in node.handler(state):
                    events_count += 1
                    yield event

                execution.status = NodeStatus.COMPLETED
                execution.events_emitted = events_count

            except Exception as e:
                execution.status = NodeStatus.FAILED
                execution.error = str(e)
                state.error = str(e)
                logger.error(f"Node '{current_node}' failed: {e}")

            finally:
                execution.duration_ms = (time.time() - start_time) * 1000
                self._execution_history.append(execution)

                if on_node_end:
                    on_node_end(current_node, state, execution)

                # Optional checkpointing hook (feature-flagged)
                try:
                    flags = getattr(state, "metadata", {}).get("feature_flags", {})
                    if (
                        checkpoint_manager
                        and flags.get("workflow_checkpointing")
                        and state.iteration_count % max(checkpoint_interval, 1) == 0
                    ):
                        session_id = getattr(state, "session_id", None) or "unknown"
                        await checkpoint_manager.save_checkpoint(
                            session_id=session_id,
                            node_name=current_node,
                            iteration=state.iteration_count,
                            state=state,
                            execution={
                                "status": execution.status.value,
                                "duration_ms": execution.duration_ms,
                                "events_emitted": execution.events_emitted,
                                "error": execution.error,
                            },
                        )
                except Exception as e:
                    logger.debug(f"Checkpoint save failed (non-blocking): {e}")

            # If error occurred, stop
            if state.error:
                break

            # Determine next node
            next_node = await self._resolve_next_node(state)
            logger.debug(f"Workflow '{self.name}' transitioning: {current_node} -> {next_node}")
            state.transition_to(next_node)

        logger.info(f"Workflow '{self.name}' completed after {state.iteration_count} iterations")

    def get_execution_history(self) -> list[NodeExecution]:
        """Get the execution history from the last run."""
        return self._execution_history.copy()

    def get_graph_structure(self) -> dict[str, Any]:
        """Get the graph structure for visualization/debugging."""
        nodes = []
        edges = []

        for name, node in self._nodes.items():
            nodes.append({"name": name, "description": node.description})

        for from_node, edge_list in self._edges.items():
            for edge in edge_list:
                edges.append({"from": from_node, "to": edge.to_node, "condition": edge.condition, "type": "direct"})

        for from_node, conditional in self._conditional_edges.items():
            for target in conditional.possible_targets:
                edges.append({"from": from_node, "to": target, "type": "conditional"})

        return {
            "name": self.name,
            "description": self.description,
            "nodes": nodes,
            "edges": edges,
            "entry_point": self._entry_point,
        }


class WorkflowBuilder:
    """Fluent builder for creating workflow graphs."""

    def __init__(self, name: str, description: str = ""):
        self._graph = WorkflowGraph(name, description)
        self._current_node: str | None = None

    def node(self, name: str, handler: NodeHandler, description: str = "") -> "WorkflowBuilder":
        """Add a node."""
        self._graph.add_node(name, handler, description)
        self._current_node = name
        return self

    def entry(self, node_name: str) -> "WorkflowBuilder":
        """Set entry point."""
        self._graph.set_entry_point(node_name)
        return self

    def edge(self, to_node: str) -> "WorkflowBuilder":
        """Add edge from current node."""
        if not self._current_node:
            raise ValueError("No current node - add a node first")
        self._graph.add_edge(self._current_node, to_node)
        return self

    def conditional(self, router: ConditionalRouter, targets: list[str]) -> "WorkflowBuilder":
        """Add conditional edge from current node."""
        if not self._current_node:
            raise ValueError("No current node - add a node first")
        self._graph.add_conditional_edge(self._current_node, router, targets)
        return self

    def build(self) -> WorkflowGraph:
        """Build and return the workflow graph."""
        return self._graph
