"""
Multi-Agent Collaboration Patterns.

This module provides patterns for agents to collaborate on complex tasks:
- Debate: Agents argue positions, synthesize conclusions
- Assembly Line: Sequential specialists
- Swarm: Parallel exploration with aggregation
- Mentor-Student: Main agent with specialist advisors
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from app.domain.models.agent_capability import CapabilityCategory
from app.domain.models.agent_message import MessageType
from app.domain.services.agents.communication.protocol import (
    CommunicationProtocol,
    get_communication_protocol,
)
from app.domain.services.agents.registry.capability_registry import (
    AgentRegistry,
    get_agent_registry,
)

logger = logging.getLogger(__name__)


class PatternType(str, Enum):
    """Types of collaboration patterns."""

    DEBATE = "debate"
    ASSEMBLY_LINE = "assembly_line"
    SWARM = "swarm"
    MENTOR_STUDENT = "mentor_student"


@dataclass
class CollaborationContext:
    """Context for a collaboration session."""

    session_id: str
    pattern_type: PatternType
    task_description: str
    participants: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollaborationResult:
    """Result of a collaboration session."""

    session_id: str
    pattern_type: PatternType
    success: bool
    final_output: str | None = None
    consensus_reached: bool = False
    participant_contributions: dict[str, str] = field(default_factory=dict)
    synthesis: str | None = None
    confidence: float = 0.0
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class CollaborationPattern(ABC):
    """Base class for collaboration patterns."""

    def __init__(
        self,
        registry: AgentRegistry | None = None,
        protocol: CommunicationProtocol | None = None,
    ) -> None:
        """Initialize the collaboration pattern.

        Args:
            registry: Agent registry
            protocol: Communication protocol
        """
        self._registry = registry or get_agent_registry()
        self._protocol = protocol or get_communication_protocol()

    @property
    @abstractmethod
    def pattern_type(self) -> PatternType:
        """Get the pattern type."""
        pass

    @abstractmethod
    async def execute(
        self,
        context: CollaborationContext,
        **kwargs: Any,
    ) -> CollaborationResult:
        """Execute the collaboration pattern.

        Args:
            context: Collaboration context
            **kwargs: Pattern-specific arguments

        Returns:
            Collaboration result
        """
        pass

    def _create_session_id(self) -> str:
        """Create a unique session ID."""
        return f"collab_{datetime.now().timestamp()}"


class DebatePattern(CollaborationPattern):
    """Debate pattern: Agents argue different positions and synthesize.

    Multiple agents take different positions on a problem, present
    arguments, counter-arguments, and work toward synthesis.
    """

    @property
    def pattern_type(self) -> PatternType:
        return PatternType.DEBATE

    async def execute(
        self,
        context: CollaborationContext,
        positions: list[str] | None = None,
        max_rounds: int = 3,
        require_synthesis: bool = True,
    ) -> CollaborationResult:
        """Execute the debate pattern.

        Args:
            context: Collaboration context
            positions: Optional list of positions to argue
            max_rounds: Maximum debate rounds
            require_synthesis: Whether to require synthesis

        Returns:
            Collaboration result with synthesized conclusion
        """
        start_time = datetime.now()
        contributions: dict[str, list[str]] = {}

        logger.info(f"Starting debate: {context.session_id}")

        # Assign positions to participants
        if not positions:
            positions = ["Position A", "Position B"]

        position_assignments: dict[str, str] = {}
        for i, participant in enumerate(context.participants[: len(positions)]):
            position_assignments[participant] = positions[i % len(positions)]
            contributions[participant] = []

        # Conduct debate rounds
        round_arguments: list[dict[str, str]] = []

        for round_num in range(max_rounds):
            logger.debug(f"Debate round {round_num + 1}")
            round_args: dict[str, str] = {}

            # Each participant presents their argument
            for participant, position in position_assignments.items():
                # Request argument from participant
                self._protocol.send_message(
                    sender_id="debate_coordinator",
                    sender_type="coordinator",
                    recipient_id=participant,
                    message_type=MessageType.INFORMATION_REQUEST,
                    subject=f"Debate Round {round_num + 1}",
                    content=f"Present your argument for '{position}' regarding: {context.task_description}",
                    payload={
                        "position": position,
                        "round": round_num + 1,
                        "previous_arguments": round_arguments,
                    },
                )

                # Simulate argument (in real implementation, wait for response)
                argument = f"[{participant}] Round {round_num + 1} argument for {position}"
                round_args[participant] = argument
                contributions[participant].append(argument)

            round_arguments.append(round_args)

        # Synthesize conclusions
        synthesis = None
        consensus = False

        if require_synthesis:
            synthesis = await self._synthesize_debate(
                context.task_description,
                round_arguments,
                position_assignments,
            )
            consensus = len(set(position_assignments.values())) > 1

        duration = (datetime.now() - start_time).total_seconds() * 1000

        # Flatten contributions
        flat_contributions = {p: "\n".join(args) for p, args in contributions.items()}

        return CollaborationResult(
            session_id=context.session_id,
            pattern_type=self.pattern_type,
            success=True,
            final_output=synthesis,
            consensus_reached=consensus,
            participant_contributions=flat_contributions,
            synthesis=synthesis,
            confidence=0.7 if consensus else 0.5,
            duration_ms=duration,
        )

    async def _synthesize_debate(
        self,
        task: str,
        arguments: list[dict[str, str]],
        positions: dict[str, str],
    ) -> str:
        """Synthesize conclusions from debate arguments."""
        # In real implementation, use LLM to synthesize
        return f"Synthesis of debate on: {task}"


class AssemblyLinePattern(CollaborationPattern):
    """Assembly Line pattern: Sequential specialists.

    Task flows through a sequence of specialized agents,
    each adding their expertise to the output.
    """

    @property
    def pattern_type(self) -> PatternType:
        return PatternType.ASSEMBLY_LINE

    async def execute(
        self,
        context: CollaborationContext,
        stages: list[tuple[str, CapabilityCategory]] | None = None,
    ) -> CollaborationResult:
        """Execute the assembly line pattern.

        Args:
            context: Collaboration context
            stages: List of (stage_name, required_capability) tuples

        Returns:
            Collaboration result with assembled output
        """
        start_time = datetime.now()
        contributions: dict[str, str] = {}

        logger.info(f"Starting assembly line: {context.session_id}")

        # Default stages if not provided
        if not stages:
            stages = [
                ("planning", CapabilityCategory.PLANNING),
                ("execution", CapabilityCategory.CODING),
                ("review", CapabilityCategory.VERIFICATION),
            ]

        current_output = context.task_description
        stage_outputs: list[str] = []

        for stage_name, required_capability in stages:
            logger.debug(f"Assembly line stage: {stage_name}")

            # Find agent for this stage
            agents = self._registry.get_agents_by_category(required_capability)
            if not agents:
                logger.warning(f"No agent available for stage: {stage_name}")
                continue

            agent = agents[0]

            # Send task to agent
            self._protocol.send_message(
                sender_id="assembly_coordinator",
                sender_type="coordinator",
                recipient_id=agent.agent_name,
                message_type=MessageType.TASK_DELEGATION,
                subject=f"Assembly Stage: {stage_name}",
                content=f"Process the following for {stage_name}: {current_output}",
                payload={
                    "stage": stage_name,
                    "input": current_output,
                },
            )

            # Simulate stage output (in real implementation, wait for response)
            stage_output = f"[{stage_name}] Processed: {current_output[:50]}..."
            contributions[agent.agent_name] = stage_output
            stage_outputs.append(stage_output)
            current_output = stage_output

        duration = (datetime.now() - start_time).total_seconds() * 1000

        return CollaborationResult(
            session_id=context.session_id,
            pattern_type=self.pattern_type,
            success=True,
            final_output=current_output,
            participant_contributions=contributions,
            confidence=0.8,
            duration_ms=duration,
            metadata={"stages_completed": len(stage_outputs)},
        )


class SwarmPattern(CollaborationPattern):
    """Swarm pattern: Parallel exploration with aggregation.

    Multiple agents explore the problem space in parallel,
    with results aggregated for comprehensive coverage.
    """

    @property
    def pattern_type(self) -> PatternType:
        return PatternType.SWARM

    async def execute(
        self,
        context: CollaborationContext,
        subtasks: list[str] | None = None,
        aggregation_strategy: str = "merge",
    ) -> CollaborationResult:
        """Execute the swarm pattern.

        Args:
            context: Collaboration context
            subtasks: List of subtasks to explore in parallel
            aggregation_strategy: How to aggregate results (merge, vote, best)

        Returns:
            Collaboration result with aggregated output
        """
        start_time = datetime.now()
        contributions: dict[str, str] = {}

        logger.info(f"Starting swarm: {context.session_id}")

        # Generate subtasks if not provided
        if not subtasks:
            subtasks = [
                f"Explore aspect 1 of: {context.task_description}",
                f"Explore aspect 2 of: {context.task_description}",
                f"Explore aspect 3 of: {context.task_description}",
            ]

        # Assign subtasks to participants
        task_results: dict[str, str] = {}

        # Simulate parallel execution
        async def execute_subtask(participant: str, subtask: str) -> tuple[str, str]:
            self._protocol.send_message(
                sender_id="swarm_coordinator",
                sender_type="coordinator",
                recipient_id=participant,
                message_type=MessageType.TASK_DELEGATION,
                subject="Swarm Subtask",
                content=subtask,
            )
            # Simulate result
            return participant, f"[{participant}] Result for: {subtask[:30]}..."

        # Execute subtasks in parallel
        tasks = []
        for i, subtask in enumerate(subtasks):
            if i < len(context.participants):
                participant = context.participants[i]
                tasks.append(execute_subtask(participant, subtask))

        results = await asyncio.gather(*tasks)
        for participant, result in results:
            task_results[participant] = result
            contributions[participant] = result

        # Aggregate results
        aggregated = await self._aggregate_results(
            task_results,
            aggregation_strategy,
        )

        duration = (datetime.now() - start_time).total_seconds() * 1000

        return CollaborationResult(
            session_id=context.session_id,
            pattern_type=self.pattern_type,
            success=True,
            final_output=aggregated,
            participant_contributions=contributions,
            confidence=0.75,
            duration_ms=duration,
            metadata={
                "subtasks_completed": len(results),
                "aggregation_strategy": aggregation_strategy,
            },
        )

    async def _aggregate_results(
        self,
        results: dict[str, str],
        strategy: str,
    ) -> str:
        """Aggregate swarm results."""
        if strategy == "merge":
            return "\n\n".join(results.values())
        if strategy == "vote":
            # In real implementation, use voting logic
            return next(iter(results.values())) if results else ""
        if strategy == "best":
            # In real implementation, evaluate and select best
            return next(iter(results.values())) if results else ""
        return "\n\n".join(results.values())


class MentorStudentPattern(CollaborationPattern):
    """Mentor-Student pattern: Main agent with specialist advisors.

    A primary agent leads execution while consulting specialist
    agents for domain-specific guidance.
    """

    @property
    def pattern_type(self) -> PatternType:
        return PatternType.MENTOR_STUDENT

    async def execute(
        self,
        context: CollaborationContext,
        mentor_id: str | None = None,
        advice_topics: list[str] | None = None,
    ) -> CollaborationResult:
        """Execute the mentor-student pattern.

        Args:
            context: Collaboration context
            mentor_id: ID of the mentor (lead) agent
            advice_topics: Topics to seek advice on

        Returns:
            Collaboration result
        """
        start_time = datetime.now()
        contributions: dict[str, str] = {}

        logger.info(f"Starting mentor-student: {context.session_id}")

        # Identify mentor and students
        if not mentor_id and context.participants:
            mentor_id = context.participants[0]
        students = [p for p in context.participants if p != mentor_id]

        # Generate advice topics if not provided
        if not advice_topics:
            advice_topics = ["approach", "potential issues", "best practices"]

        # Mentor requests advice from students
        advice_collected: dict[str, dict[str, str]] = {}

        for student in students:
            advice_collected[student] = {}
            for topic in advice_topics:
                self._protocol.send_message(
                    sender_id=mentor_id,
                    sender_type="mentor",
                    recipient_id=student,
                    message_type=MessageType.INFORMATION_REQUEST,
                    subject=f"Advice Request: {topic}",
                    content=f"Please advise on {topic} for: {context.task_description}",
                    payload={"topic": topic},
                )
                # Simulate advice
                advice = f"[{student}] Advice on {topic}"
                advice_collected[student][topic] = advice

            contributions[student] = str(advice_collected[student])

        # Mentor synthesizes advice and produces output
        mentor_output = await self._mentor_synthesize(
            context.task_description,
            advice_collected,
        )
        contributions[mentor_id] = mentor_output

        duration = (datetime.now() - start_time).total_seconds() * 1000

        return CollaborationResult(
            session_id=context.session_id,
            pattern_type=self.pattern_type,
            success=True,
            final_output=mentor_output,
            participant_contributions=contributions,
            confidence=0.8,
            duration_ms=duration,
            metadata={
                "mentor": mentor_id,
                "students": students,
                "advice_topics": advice_topics,
            },
        )

    async def _mentor_synthesize(
        self,
        task: str,
        advice: dict[str, dict[str, str]],
    ) -> str:
        """Mentor synthesizes advice into final output."""
        # In real implementation, use LLM to synthesize
        advice_summary = []
        for topics in advice.values():
            for topic, content in topics.items():
                advice_summary.append(f"- {topic}: {content}")

        return f"Synthesized output for: {task}\n\nAdvice incorporated:\n" + "\n".join(advice_summary)


class PatternExecutor:
    """Executor for running collaboration patterns."""

    def __init__(self) -> None:
        """Initialize the pattern executor."""
        self._patterns: dict[PatternType, CollaborationPattern] = {
            PatternType.DEBATE: DebatePattern(),
            PatternType.ASSEMBLY_LINE: AssemblyLinePattern(),
            PatternType.SWARM: SwarmPattern(),
            PatternType.MENTOR_STUDENT: MentorStudentPattern(),
        }

    def get_pattern(self, pattern_type: PatternType) -> CollaborationPattern:
        """Get a pattern by type."""
        if pattern_type not in self._patterns:
            raise ValueError(f"Unknown pattern type: {pattern_type}")
        return self._patterns[pattern_type]

    async def execute_pattern(
        self,
        pattern_type: PatternType,
        task_description: str,
        participants: list[str],
        **kwargs: Any,
    ) -> CollaborationResult:
        """Execute a collaboration pattern.

        Args:
            pattern_type: Type of pattern to execute
            task_description: Description of the task
            participants: List of participant agent IDs
            **kwargs: Pattern-specific arguments

        Returns:
            Collaboration result
        """
        pattern = self.get_pattern(pattern_type)

        context = CollaborationContext(
            session_id=f"collab_{datetime.now().timestamp()}",
            pattern_type=pattern_type,
            task_description=task_description,
            participants=participants,
        )

        return await pattern.execute(context, **kwargs)

    def suggest_pattern(
        self,
        task_description: str,
        num_participants: int,
        task_complexity: float,
    ) -> PatternType:
        """Suggest the best pattern for a task.

        Args:
            task_description: Task description
            num_participants: Number of available participants
            task_complexity: Task complexity (0-1)

        Returns:
            Recommended pattern type
        """
        task_lower = task_description.lower()

        # Check for debate-suitable tasks
        if any(word in task_lower for word in ["compare", "evaluate", "decide between"]) and num_participants >= 2:
            return PatternType.DEBATE

        # Check for swarm-suitable tasks
        if any(word in task_lower for word in ["explore", "research", "comprehensive"]) and num_participants >= 3:
            return PatternType.SWARM

        # Check for assembly-suitable tasks
        if task_complexity >= 0.7:
            return PatternType.ASSEMBLY_LINE

        # Default to mentor-student for most tasks
        return PatternType.MENTOR_STUDENT


# Global executor instance
_executor: PatternExecutor | None = None


def get_pattern_executor() -> PatternExecutor:
    """Get or create the global pattern executor."""
    global _executor
    if _executor is None:
        _executor = PatternExecutor()
    return _executor


def reset_pattern_executor() -> None:
    """Reset the global pattern executor."""
    global _executor
    _executor = None
