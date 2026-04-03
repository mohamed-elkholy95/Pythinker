"""Context retention system for execution continuity across steps.

Solves the problem where ExecutionAgent loses context between steps,
requiring re-reading of files created in previous steps.

Enhanced with inter-step context synthesis (Phase 2.5):
- StepInsight: Structured insights from each step
- ContextGraph: Dependency graph between insights
- InsightSynthesizer: Automatic insight extraction from tool results
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class InsightType(str, Enum):
    """Types of insights captured from step execution."""

    DISCOVERY = "discovery"  # New information discovered
    ERROR_LEARNING = "error_learning"  # Learned from an error
    DECISION = "decision"  # Decision made during execution
    DEPENDENCY = "dependency"  # Something depends on this
    ASSUMPTION = "assumption"  # Assumption made
    CONSTRAINT = "constraint"  # Constraint identified
    PROGRESS = "progress"  # Progress towards goal
    BLOCKER = "blocker"  # Something blocking progress


@dataclass
class StepInsight:
    """Structured insight from a step execution.

    Captures key learnings that should be passed to subsequent steps.
    """

    step_id: str
    insight_type: InsightType
    content: str
    confidence: float = 0.8  # 0.0-1.0 confidence in this insight
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source_tool: str | None = None  # Tool that produced this insight
    related_insights: list[str] = field(default_factory=list)  # IDs of related insights
    tags: list[str] = field(default_factory=list)  # Categorization tags
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Generate unique ID for this insight."""
        return f"{self.step_id}_{self.insight_type.value}_{hash(self.content) % 10000}"

    @property
    def is_high_confidence(self) -> bool:
        """Check if insight has high confidence (>=0.8)."""
        return self.confidence >= 0.8

    @property
    def is_actionable(self) -> bool:
        """Check if insight requires action."""
        return self.insight_type in (
            InsightType.BLOCKER,
            InsightType.ERROR_LEARNING,
            InsightType.CONSTRAINT,
        )

    def to_context_string(self) -> str:
        """Format insight for context injection."""
        prefix = {
            InsightType.DISCOVERY: "📍 Discovered",
            InsightType.ERROR_LEARNING: "⚠️ Learned",
            InsightType.DECISION: "✓ Decided",
            InsightType.DEPENDENCY: "🔗 Depends on",
            InsightType.ASSUMPTION: "💭 Assuming",
            InsightType.CONSTRAINT: "🚧 Constraint",
            InsightType.PROGRESS: "📈 Progress",
            InsightType.BLOCKER: "🛑 Blocked by",
        }.get(self.insight_type, "•")
        return f"{prefix}: {self.content}"


@dataclass
class InsightEdge:
    """Edge in the context graph connecting two insights."""

    from_insight_id: str
    to_insight_id: str
    relationship: str  # "depends_on", "derived_from", "contradicts", "supports"
    weight: float = 1.0  # Strength of relationship


@dataclass
class ContextGraph:
    """Graph structure showing dependencies between insights.

    Tracks how insights relate to each other for:
    - Understanding information flow
    - Identifying critical path insights
    - Surfacing relevant context for new steps
    """

    insights: dict[str, StepInsight] = field(default_factory=dict)
    edges: list[InsightEdge] = field(default_factory=list)
    step_insights: dict[str, list[str]] = field(default_factory=dict)  # step_id -> insight_ids

    def add_insight(self, insight: StepInsight) -> None:
        """Add an insight to the graph."""
        self.insights[insight.id] = insight
        if insight.step_id not in self.step_insights:
            self.step_insights[insight.step_id] = []
        self.step_insights[insight.step_id].append(insight.id)

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        relationship: str = "derived_from",
        weight: float = 1.0,
    ) -> None:
        """Add an edge between insights."""
        if from_id in self.insights and to_id in self.insights:
            self.edges.append(
                InsightEdge(
                    from_insight_id=from_id,
                    to_insight_id=to_id,
                    relationship=relationship,
                    weight=weight,
                )
            )
            # Update related_insights in both directions
            self.insights[from_id].related_insights.append(to_id)

    def get_insights_for_step(self, step_id: str) -> list[StepInsight]:
        """Get all insights from a specific step."""
        insight_ids = self.step_insights.get(step_id, [])
        return [self.insights[iid] for iid in insight_ids if iid in self.insights]

    def get_related_insights(self, insight_id: str, max_depth: int = 2) -> list[StepInsight]:
        """Get insights related to a given insight (BFS traversal)."""
        if insight_id not in self.insights:
            return []

        visited = {insight_id}
        queue = [(insight_id, 0)]
        related = []

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            # Find connected insights
            for edge in self.edges:
                neighbor_id = None
                if edge.from_insight_id == current_id:
                    neighbor_id = edge.to_insight_id
                elif edge.to_insight_id == current_id:
                    neighbor_id = edge.from_insight_id

                if neighbor_id and neighbor_id not in visited:
                    visited.add(neighbor_id)
                    if neighbor_id in self.insights:
                        related.append(self.insights[neighbor_id])
                        queue.append((neighbor_id, depth + 1))

        return related

    def get_critical_insights(self, limit: int = 5) -> list[StepInsight]:
        """Get most important insights based on connectivity and type."""
        # Score insights by: connectivity + type importance + confidence
        scored = []
        for insight in self.insights.values():
            # Count connections
            connections = sum(1 for e in self.edges if e.from_insight_id == insight.id or e.to_insight_id == insight.id)
            # Type importance
            type_weight = {
                InsightType.BLOCKER: 2.0,
                InsightType.ERROR_LEARNING: 1.8,
                InsightType.CONSTRAINT: 1.5,
                InsightType.DISCOVERY: 1.2,
                InsightType.DECISION: 1.0,
                InsightType.DEPENDENCY: 0.9,
                InsightType.ASSUMPTION: 0.7,
                InsightType.PROGRESS: 0.5,
            }.get(insight.insight_type, 1.0)

            score = (connections * 0.3) + (type_weight * 0.4) + (insight.confidence * 0.3)
            scored.append((score, insight))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [insight for _, insight in scored[:limit]]

    def get_blockers(self) -> list[StepInsight]:
        """Get all blocker insights."""
        return [i for i in self.insights.values() if i.insight_type == InsightType.BLOCKER]

    def get_learnings(self) -> list[StepInsight]:
        """Get all error learnings."""
        return [i for i in self.insights.values() if i.insight_type == InsightType.ERROR_LEARNING]

    def to_summary(self, max_insights: int = 10) -> str:
        """Generate a summary of the context graph."""
        if not self.insights:
            return ""

        lines = ["## Context Insights"]

        # Add critical insights first
        critical = self.get_critical_insights(limit=max_insights)
        if critical:
            lines.append("\n### Key Insights")
            lines.extend(f"- {insight.to_context_string()}" for insight in critical)

        # Add blockers if any
        blockers = self.get_blockers()
        if blockers:
            lines.append("\n### Active Blockers")
            lines.extend(f"- {blocker.content}" for blocker in blockers)

        # Add recent learnings
        learnings = self.get_learnings()[-3:]  # Last 3 learnings
        if learnings:
            lines.append("\n### Recent Learnings")
            lines.extend(f"- {learning.content}" for learning in learnings)

        return "\n".join(lines)


class InsightSynthesizer:
    """Automatically extracts insights from tool results.

    Analyzes tool execution results to identify:
    - New discoveries
    - Error patterns and learnings
    - Dependencies between components
    - Constraints and blockers
    """

    # Patterns for insight extraction
    ERROR_PATTERNS: ClassVar[list[tuple[str, InsightType]]] = [
        (r"error[:\s]+(.+)", InsightType.ERROR_LEARNING),
        (r"failed[:\s]+(.+)", InsightType.ERROR_LEARNING),
        (r"exception[:\s]+(.+)", InsightType.ERROR_LEARNING),
        (r"not found[:\s]*(.+)?", InsightType.CONSTRAINT),
        (r"permission denied", InsightType.BLOCKER),
        (r"timeout", InsightType.BLOCKER),
    ]

    DISCOVERY_PATTERNS: ClassVar[list[tuple[str, InsightType]]] = [
        (r"found[:\s]+(.+)", InsightType.DISCOVERY),
        (r"discovered[:\s]+(.+)", InsightType.DISCOVERY),
        (r"identified[:\s]+(.+)", InsightType.DISCOVERY),
        (r"contains[:\s]+(.+)", InsightType.DISCOVERY),
    ]

    DEPENDENCY_PATTERNS: ClassVar[list[tuple[str, InsightType]]] = [
        (r"requires[:\s]+(.+)", InsightType.DEPENDENCY),
        (r"depends on[:\s]+(.+)", InsightType.DEPENDENCY),
        (r"needs[:\s]+(.+)", InsightType.DEPENDENCY),
    ]

    def __init__(self) -> None:
        self._compiled_patterns: list[tuple[re.Pattern, InsightType]] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for efficiency."""
        all_patterns = self.ERROR_PATTERNS + self.DISCOVERY_PATTERNS + self.DEPENDENCY_PATTERNS
        self._compiled_patterns = [(re.compile(pattern, re.IGNORECASE), itype) for pattern, itype in all_patterns]

    def extract_insights(
        self,
        step_id: str,
        tool_name: str,
        result: str,
        success: bool = True,
        args: dict[str, Any] | None = None,
    ) -> list[StepInsight]:
        """Extract insights from a tool execution result.

        Args:
            step_id: ID of the step that executed the tool
            tool_name: Name of the tool
            result: Tool execution result text
            success: Whether the tool succeeded
            args: Tool arguments

        Returns:
            List of extracted insights
        """
        insights: list[StepInsight] = []
        args = args or {}

        # Normalise result to string so downstream slicing/regex never fails on None
        result = result or ""

        # Handle errors specially
        if not success:
            insights.append(
                StepInsight(
                    step_id=step_id,
                    insight_type=InsightType.ERROR_LEARNING,
                    content=f"{tool_name} failed: {result[:200]}",
                    confidence=0.9,
                    source_tool=tool_name,
                    tags=["error", tool_name],
                )
            )

        # Pattern-based extraction
        for pattern, insight_type in self._compiled_patterns:
            matches = pattern.findall(result[:2000])  # Limit search length
            for match in matches[:2]:  # Limit matches per pattern
                content = match if isinstance(match, str) else match[0] if match else ""
                if content and len(content) > 10:
                    insights.append(
                        StepInsight(
                            step_id=step_id,
                            insight_type=insight_type,
                            content=content[:200].strip(),
                            confidence=0.7,
                            source_tool=tool_name,
                            tags=[insight_type.value, tool_name],
                        )
                    )

        # Tool-specific insight extraction
        insights.extend(self._extract_tool_specific(step_id, tool_name, result, args))

        return insights

    def _extract_tool_specific(
        self,
        step_id: str,
        tool_name: str,
        result: str,
        args: dict[str, Any],
    ) -> list[StepInsight]:
        """Extract tool-specific insights."""
        insights: list[StepInsight] = []

        # Search tool insights
        if tool_name in ("info_search_web", "search", "web_search"):
            # Extract key search findings
            if "results" in result.lower() or "found" in result.lower():
                query = args.get("query", "")
                insights.append(
                    StepInsight(
                        step_id=step_id,
                        insight_type=InsightType.DISCOVERY,
                        content=f"Search for '{query[:50]}' returned results",
                        confidence=0.8,
                        source_tool=tool_name,
                        tags=["search", "discovery"],
                        metadata={"query": query},
                    )
                )

        # File operation insights
        elif tool_name in ("file_write", "file_create", "file_read"):
            path = args.get("path", "")
            if path:
                operation = "created" if "create" in tool_name or "write" in tool_name else "read"
                insights.append(
                    StepInsight(
                        step_id=step_id,
                        insight_type=InsightType.PROGRESS,
                        content=f"File {operation}: {path}",
                        confidence=0.95,
                        source_tool=tool_name,
                        tags=["file", operation],
                        metadata={"path": path, "operation": operation},
                    )
                )

        # Shell command insights
        elif tool_name in ("shell_exec", "shell", "terminal"):
            command = args.get("command", "")[:100]
            if command:
                insights.append(
                    StepInsight(
                        step_id=step_id,
                        insight_type=InsightType.PROGRESS,
                        content=f"Executed command: {command}",
                        confidence=0.85,
                        source_tool=tool_name,
                        tags=["shell", "command"],
                        metadata={"command": command},
                    )
                )

        # Browser insights
        elif tool_name in ("browser_navigate", "browser_view", "browser"):
            url = args.get("url", "")
            if url:
                insights.append(
                    StepInsight(
                        step_id=step_id,
                        insight_type=InsightType.DISCOVERY,
                        content=f"Visited: {url[:100]}",
                        confidence=0.8,
                        source_tool=tool_name,
                        tags=["browser", "navigation"],
                        metadata={"url": url},
                    )
                )

        return insights

    def synthesize_from_steps(
        self,
        step_insights: dict[str, list[StepInsight]],
        current_step_id: str,
    ) -> str:
        """Synthesize insights from previous steps for the current step.

        Args:
            step_insights: Map of step_id to insights
            current_step_id: ID of the step being executed

        Returns:
            Synthesized context string
        """
        if not step_insights:
            return ""

        lines = ["## Prior Step Insights"]

        # Collect all insights except current step
        all_insights: list[StepInsight] = []
        for sid, insights in step_insights.items():
            if sid != current_step_id:
                all_insights.extend(insights)

        if not all_insights:
            return ""

        # Group by type and prioritize
        by_type: dict[InsightType, list[StepInsight]] = {}
        for insight in all_insights:
            if insight.insight_type not in by_type:
                by_type[insight.insight_type] = []
            by_type[insight.insight_type].append(insight)

        # Priority order for context
        priority_order = [
            InsightType.BLOCKER,
            InsightType.ERROR_LEARNING,
            InsightType.CONSTRAINT,
            InsightType.DISCOVERY,
            InsightType.DECISION,
            InsightType.DEPENDENCY,
        ]

        for itype in priority_order:
            if by_type.get(itype):
                type_insights = by_type[itype][:3]  # Max 3 per type
                lines.append(f"\n### {itype.value.replace('_', ' ').title()}")
                lines.extend(f"- {insight.content}" for insight in type_insights)

        return "\n".join(lines)


@dataclass
class FileContext:
    """Context for a file that was created or read"""

    path: str
    operation: str  # "created", "read", "modified"
    timestamp: datetime
    size_bytes: int | None = None
    content_summary: str | None = None  # Brief description
    is_deliverable: bool = False


@dataclass(frozen=True)
class ToolContext:
    """Context from tool execution"""

    tool_name: str
    timestamp: datetime
    summary: str  # Brief result summary
    key_findings: list[str] = field(default_factory=list)
    urls_visited: list[str] = field(default_factory=list)
    files_affected: list[str] = field(default_factory=list)


@dataclass
class WorkingContext:
    """Accumulated context during execution"""

    files: dict[str, FileContext] = field(default_factory=dict)  # path -> context
    tools: list[ToolContext] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)  # Important discoveries
    deliverables: list[str] = field(default_factory=list)  # Completed deliverables
    total_tokens: int = 0  # Estimated context size


class ContextManager:
    """Manages working context across execution steps.

    Features:
    - Tracks files created/read to avoid re-reading
    - Stores key findings from research/browsing
    - Generates token-aware context summaries
    - Prioritizes recent and important context
    - Inter-step context synthesis with insight graph (Phase 2.5)
    """

    def __init__(self, max_context_tokens: int = 8000):
        self._context = WorkingContext()
        self._max_tokens = max_context_tokens
        self._token_per_char = 0.25  # Conservative estimate

        # Inter-step context synthesis (Phase 2.5)
        self._context_graph = ContextGraph()
        self._insight_synthesizer = InsightSynthesizer()
        self._current_step_id: str | None = None

    @property
    def _max_context_tokens(self) -> int:
        """Backward-compatible max token alias."""
        return self._max_tokens

    @_max_context_tokens.setter
    def _max_context_tokens(self, value: int) -> None:
        self._max_tokens = value

    def track_file_operation(
        self,
        path: str,
        operation: str,
        size_bytes: int | None = None,
        content_summary: str | None = None,
        is_deliverable: bool = False,
    ) -> None:
        """Track file creation/read/modification"""
        self._context.files[path] = FileContext(
            path=path,
            operation=operation,
            timestamp=datetime.now(UTC),
            size_bytes=size_bytes,
            content_summary=content_summary,
            is_deliverable=is_deliverable,
        )
        logger.debug(f"Tracked file {operation}: {path}")

    def track_tool_execution(
        self,
        tool_name: str,
        summary: str,
        key_findings: list[str] | None = None,
        urls_visited: list[str] | None = None,
        files_affected: list[str] | None = None,
    ) -> None:
        """Track tool execution results"""
        self._context.tools.append(
            ToolContext(
                tool_name=tool_name,
                timestamp=datetime.now(UTC),
                summary=summary,
                key_findings=key_findings or [],
                urls_visited=urls_visited or [],
                files_affected=files_affected or [],
            )
        )
        logger.debug(f"Tracked tool execution: {tool_name}")

    def add_key_fact(self, fact: str) -> None:
        """Add important discovery/fact"""
        if fact not in self._context.key_facts:
            self._context.key_facts.append(fact)

    def add_observation(
        self,
        observation_type: str,
        content: str,
        importance: float = 0.5,
    ) -> None:
        """Add an observation to the context.

        Args:
            observation_type: Type of observation (e.g., 'multimodal_findings')
            content: The observation content
            importance: Importance score 0.0-1.0 (higher = more important)
        """
        # Store as a key fact with type prefix for prioritization
        fact = f"[{observation_type}] {content[:500]}"  # Limit length
        if importance >= 0.7:
            # High importance: add at the beginning
            self._context.key_facts.insert(0, fact)
        else:
            self._context.key_facts.append(fact)
        logger.debug(f"Added observation: {observation_type} (importance={importance})")

    def mark_deliverable_complete(self, deliverable_path: str) -> None:
        """Mark a deliverable as completed"""
        if deliverable_path not in self._context.deliverables:
            self._context.deliverables.append(deliverable_path)
            # Also mark in files context
            if deliverable_path in self._context.files:
                self._context.files[deliverable_path].is_deliverable = True

    def get_context_summary(self, max_tokens: int | None = None) -> str:
        """Generate token-aware context summary for prompt injection.

        Prioritizes:
        1. Deliverables (most important)
        2. Recent tool executions
        3. Key facts
        4. File operations
        """
        max_tokens = max_tokens or self._max_tokens

        sections = []

        # 1. Deliverables (highest priority)
        if self._context.deliverables:
            sections.append("## Completed Deliverables")
            sections.extend(f"- {path}" for path in self._context.deliverables)
            sections.append("")

        # 2. Files context
        if self._context.files:
            sections.append("## Working Files")
            # Prioritize deliverables and recently modified
            sorted_files = sorted(
                self._context.files.values(), key=lambda f: (f.is_deliverable, f.timestamp), reverse=True
            )
            for file_ctx in sorted_files[:20]:  # Limit to 20 most important
                summary = file_ctx.content_summary or "No summary"
                sections.append(f"- {file_ctx.path} ({file_ctx.operation}): {summary}")
            sections.append("")

        # 3. Key facts
        if self._context.key_facts:
            sections.append("## Key Findings")
            sections.extend(f"- {fact}" for fact in self._context.key_facts[-10:])  # Last 10 facts
            sections.append("")

        # 4. Recent tool executions
        if self._context.tools:
            sections.append("## Recent Actions")
            sections.extend(
                f"- {tool_ctx.tool_name}: {tool_ctx.summary}"
                for tool_ctx in self._context.tools[-5:]  # Last 5 tools
            )
            sections.append("")

        full_summary = "\n".join(sections)

        # Token limit enforcement (truncate if needed)
        estimated_tokens = int(len(full_summary) * self._token_per_char)
        if estimated_tokens > max_tokens:
            # Truncate proportionally
            char_limit = int(max_tokens / self._token_per_char)
            full_summary = full_summary[:char_limit] + "\n... (truncated)"

        return full_summary

    def get_files_created(self) -> list[str]:
        """Get list of files created in this session"""
        return [path for path, ctx in self._context.files.items() if ctx.operation == "created"]

    def get_deliverables(self) -> list[str]:
        """Get list of completed deliverables"""
        return self._context.deliverables.copy()

    def clear(self) -> None:
        """Clear all context (use at task boundaries)"""
        self._context = WorkingContext()
        self._context_graph = ContextGraph()
        self._current_step_id = None
        logger.info("Context cleared")

    # Inter-Step Context Synthesis (Phase 2.5)

    def set_current_step(self, step_id: str) -> None:
        """Set the current step being executed.

        Args:
            step_id: ID of the step about to execute
        """
        self._current_step_id = step_id
        logger.debug(f"Context manager: current step set to {step_id}")

    def record_tool_insight(
        self,
        tool_name: str,
        result: str,
        success: bool = True,
        args: dict[str, Any] | None = None,
    ) -> list[StepInsight]:
        """Record insights from a tool execution.

        Automatically extracts insights and adds them to the context graph.

        Args:
            tool_name: Name of the tool that executed
            result: Tool execution result text
            success: Whether the tool succeeded
            args: Tool arguments

        Returns:
            List of extracted insights
        """
        step_id = self._current_step_id or "unknown"
        insights = self._insight_synthesizer.extract_insights(
            step_id=step_id,
            tool_name=tool_name,
            result=result,
            success=success,
            args=args,
        )

        for insight in insights:
            self._context_graph.add_insight(insight)
            logger.debug(f"Recorded insight: {insight.insight_type.value} from {tool_name}")

        # Link insights from the same step
        step_insights = self._context_graph.step_insights.get(step_id, [])
        if len(step_insights) > 1:
            for i in range(len(step_insights) - 1):
                self._context_graph.add_edge(
                    step_insights[i],
                    step_insights[-1],
                    relationship="same_step",
                    weight=0.5,
                )

        return insights

    def add_insight(
        self,
        insight_type: InsightType,
        content: str,
        confidence: float = 0.8,
        source_tool: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StepInsight:
        """Manually add an insight to the context graph.

        Args:
            insight_type: Type of insight
            content: Insight content
            confidence: Confidence level (0.0-1.0)
            source_tool: Tool that produced this insight
            tags: Categorization tags
            metadata: Additional metadata

        Returns:
            The created StepInsight
        """
        step_id = self._current_step_id or "unknown"
        insight = StepInsight(
            step_id=step_id,
            insight_type=insight_type,
            content=content,
            confidence=confidence,
            source_tool=source_tool,
            tags=tags or [],
            metadata=metadata or {},
        )
        self._context_graph.add_insight(insight)
        logger.debug(f"Added insight: {insight_type.value} - {content[:50]}")
        return insight

    def link_insights(
        self,
        from_insight: StepInsight,
        to_insight: StepInsight,
        relationship: str = "derived_from",
    ) -> None:
        """Create a link between two insights.

        Args:
            from_insight: Source insight
            to_insight: Target insight
            relationship: Type of relationship
        """
        self._context_graph.add_edge(
            from_insight.id,
            to_insight.id,
            relationship=relationship,
        )

    def get_synthesized_context(
        self,
        for_step_id: str | None = None,
        max_insights: int = 10,
    ) -> str:
        """Get synthesized context from previous steps.

        Generates a context string with relevant insights for the current
        or specified step.

        Args:
            for_step_id: Step ID to generate context for (defaults to current)
            max_insights: Maximum number of insights to include

        Returns:
            Synthesized context string
        """
        step_id = for_step_id or self._current_step_id

        # Get insights from all previous steps
        all_step_insights = {}
        for sid, insight_ids in self._context_graph.step_insights.items():
            if sid != step_id:
                all_step_insights[sid] = [
                    self._context_graph.insights[iid] for iid in insight_ids if iid in self._context_graph.insights
                ]

        # Use synthesizer to generate context
        return self._insight_synthesizer.synthesize_from_steps(
            all_step_insights,
            step_id or "current",
        )

    def get_critical_insights(self, limit: int = 5) -> list[StepInsight]:
        """Get the most critical insights from the context graph.

        Args:
            limit: Maximum number of insights to return

        Returns:
            List of critical insights
        """
        return self._context_graph.get_critical_insights(limit=limit)

    def get_blockers(self) -> list[StepInsight]:
        """Get all active blockers.

        Returns:
            List of blocker insights
        """
        return self._context_graph.get_blockers()

    def get_learnings(self) -> list[StepInsight]:
        """Get all error learnings.

        Returns:
            List of error learning insights
        """
        return self._context_graph.get_learnings()

    def get_insights_for_step(self, step_id: str) -> list[StepInsight]:
        """Get all insights from a specific step.

        Args:
            step_id: ID of the step

        Returns:
            List of insights from that step
        """
        return self._context_graph.get_insights_for_step(step_id)

    def get_all_insights(self) -> list[StepInsight]:
        """Return all recorded insights (backward-compatible helper)."""
        return list(self._context_graph.insights.values())

    def get_context_graph(self) -> ContextGraph:
        """Get the full context graph.

        Returns:
            The ContextGraph instance
        """
        return self._context_graph

    def get_graph_summary(self) -> dict[str, Any]:
        """Get a summary of the context graph for monitoring.

        Returns:
            Dict with graph statistics
        """
        return {
            "total_insights": len(self._context_graph.insights),
            "total_edges": len(self._context_graph.edges),
            "steps_with_insights": len(self._context_graph.step_insights),
            "blockers": len(self.get_blockers()),
            "learnings": len(self.get_learnings()),
            "insight_types": {
                itype.value: sum(1 for i in self._context_graph.insights.values() if i.insight_type == itype)
                for itype in InsightType
            },
        }
