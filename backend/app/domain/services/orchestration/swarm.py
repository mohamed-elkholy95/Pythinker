"""Swarm orchestrator for managing multiple specialized agents.

Provides infrastructure for:
1. Creating and managing a pool of specialized agents
2. Distributing tasks to appropriate agents
3. Managing parallel and sequential agent execution
4. Aggregating results from multiple agents
5. Handling agent failures and recovery

The Swarm follows the coordinator pattern where a lead agent
delegates tasks to specialized agents based on requirements.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, Field

from app.domain.exceptions.base import AgentNotFoundException, ResourceLimitExceeded
from app.domain.models.event import BaseEvent, ErrorEvent, MessageEvent
from app.domain.models.state_manifest import StateManifest
from app.domain.services.orchestration.agent_types import (
    AgentCapability,
    AgentRegistry,
    AgentSpec,
    AgentType,
    get_agent_registry,
)
from app.domain.services.orchestration.handoff import (
    Handoff,
    HandoffContext,
    HandoffProtocol,
    HandoffReason,
    get_handoff_protocol,
)
from app.domain.utils.task_ids import generate_agent_task_id

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Status of an agent in the swarm."""

    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SwarmTask:
    """A task for the swarm to execute."""

    id: str = field(default_factory=generate_agent_task_id)
    description: str = ""
    original_request: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    required_capabilities: set[AgentCapability] = field(default_factory=set)
    preferred_agent: AgentType | None = None
    priority: int = 0
    timeout_seconds: int = 300
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Results
    status: AgentStatus = AgentStatus.IDLE
    result: str | None = None
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None

    # Execution tracking
    assigned_agent: AgentType | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class SwarmResult:
    """Result of swarm task execution."""

    task_id: str
    success: bool
    output: str = ""
    artifacts: list[str] = field(default_factory=list)
    summary: str = ""
    agents_used: list[AgentType] = field(default_factory=list)
    handoffs_performed: int = 0
    total_duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentFactory(Protocol):
    """Protocol for creating agent instances."""

    async def create_agent(
        self,
        agent_type: AgentType,
        agent_id: str,
        spec: AgentSpec,
    ) -> Any:
        """Create an agent instance of the specified type."""
        ...

    async def execute_agent(
        self,
        agent: Any,
        prompt: str,
        context: dict[str, Any],
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute an agent with the given prompt and context."""
        ...


class SwarmConfig(BaseModel):
    """Configuration for the Swarm orchestrator."""

    # Concurrency settings
    max_concurrent_agents: int = Field(default=3, ge=1, le=10)
    max_parallel_tasks: int = Field(default=5, ge=1, le=20)

    # Timeouts
    default_task_timeout: int = Field(default=300, ge=30)  # seconds
    handoff_timeout: int = Field(default=60, ge=10)  # seconds

    # Retry settings
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_delay: float = Field(default=1.0, ge=0)

    # Resource limits
    max_total_tokens: int = Field(default=500000, ge=10000)
    max_handoffs_per_task: int = Field(default=10, ge=1, le=50)

    # Behavior
    enable_parallel_execution: bool = True
    enable_auto_recovery: bool = True
    enable_verification: bool = True


@dataclass
class AgentInstance:
    """An active agent instance in the swarm."""

    id: str
    agent_type: AgentType
    spec: AgentSpec
    status: AgentStatus = AgentStatus.IDLE
    current_task: SwarmTask | None = None
    agent: Any = None  # The actual agent object
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    tasks_completed: int = 0


class Swarm:
    """Multi-agent swarm orchestrator.

    Manages a pool of specialized agents that work together on complex tasks.
    Implements the coordinator pattern with automatic task delegation.

    Example:
        swarm = Swarm(agent_factory, SwarmConfig(max_concurrent_agents=3))

        async for event in swarm.execute(task):
            yield event
    """

    def __init__(
        self,
        agent_factory: AgentFactory,
        config: SwarmConfig | None = None,
        registry: AgentRegistry | None = None,
        handoff_protocol: HandoffProtocol | None = None,
        session_id: str | None = None,
    ):
        self._factory = agent_factory
        self._config = config or SwarmConfig()
        self._registry = registry or get_agent_registry()
        self._protocol = handoff_protocol or get_handoff_protocol()
        # Swarm-level session identifier used for the shared blackboard.
        # Callers should pass the user/task session_id for correlation; a
        # random UUID is generated when none is provided so the constructor
        # never raises a Pydantic ValidationError.
        self._session_id: str = session_id or generate_agent_task_id()

        # Active agents
        self._agents: dict[str, AgentInstance] = {}
        self._agent_semaphore = asyncio.Semaphore(self._config.max_concurrent_agents)

        # Task queue
        self._task_queue: asyncio.Queue[SwarmTask] = asyncio.Queue()
        self._active_tasks: dict[str, SwarmTask] = {}

        # Statistics
        self._total_tasks_completed = 0
        self._total_handoffs = 0
        self._total_errors = 0

        # Phase 4: Shared StateManifest blackboard — enables agents to post and read
        # shared findings without direct coupling (post_state/read_state API in BaseAgent)
        self._shared_state = StateManifest(session_id=self._session_id)

    async def execute(
        self,
        task: SwarmTask,
        coordinator_type: AgentType = AgentType.COORDINATOR,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute a task using the swarm.

        The coordinator agent will analyze the task and delegate to
        specialized agents as needed.

        Args:
            task: The task to execute
            coordinator_type: Type of agent to use as coordinator

        Yields:
            Events from the execution process
        """
        logger.info(f"Swarm executing task {task.id[:8]}: {task.description[:50]}...")

        task.status = AgentStatus.WORKING
        task.started_at = datetime.now(UTC)
        self._active_tasks[task.id] = task

        try:
            # Select the best agent for this task
            selected_agents = self._select_agents(task)

            if not selected_agents:
                # No specialized agent found, use coordinator
                selected_agents = [self._registry.get(coordinator_type)]
                if not selected_agents[0]:
                    raise AgentNotFoundException("coordinator")

            primary_agent_spec = selected_agents[0]
            logger.info(f"Selected primary agent: {primary_agent_spec.agent_type.value}")

            # Execute with the primary agent
            async for event in self._execute_with_agent(
                task,
                primary_agent_spec,
                is_coordinator=(primary_agent_spec.agent_type == coordinator_type),
            ):
                yield event

            task.status = AgentStatus.COMPLETED
            task.completed_at = datetime.now(UTC)
            self._total_tasks_completed += 1

            logger.info(f"Swarm completed task {task.id[:8]}")

        except TimeoutError:
            task.status = AgentStatus.FAILED
            task.error = "Task timed out"
            self._total_errors += 1
            yield ErrorEvent(error=f"Task timed out after {task.timeout_seconds} seconds")

        except Exception as e:
            task.status = AgentStatus.FAILED
            task.error = str(e)
            self._total_errors += 1
            logger.error(f"Swarm task {task.id[:8]} failed: {e}")
            yield ErrorEvent(error=f"Task failed: {e!s}")

        finally:
            del self._active_tasks[task.id]

    async def _execute_with_agent(
        self,
        task: SwarmTask,
        spec: AgentSpec,
        is_coordinator: bool = False,
        handoff_context: HandoffContext | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute a task with a specific agent.

        Args:
            task: The task to execute
            spec: Agent specification
            is_coordinator: Whether this is the coordinator agent
            handoff_context: Context from a handoff (if applicable)

        Yields:
            Events from agent execution
        """
        async with self._agent_semaphore:
            # Create or get agent instance
            instance = await self._get_or_create_agent(spec)
            instance.status = AgentStatus.WORKING
            instance.current_task = task
            task.assigned_agent = spec.agent_type

            try:
                # Build the prompt
                prompt = self._build_agent_prompt(task, spec, is_coordinator, handoff_context)

                # Execute the agent
                async for event in self._factory.execute_agent(
                    instance.agent,
                    prompt,
                    task.context,
                ):
                    # Check for handoff requests in the output
                    if isinstance(event, MessageEvent):
                        handoff = self._detect_handoff_request(event.message, task)
                        if handoff:
                            # Process handoff
                            async for handoff_event in self._process_handoff(handoff, task, instance):
                                yield handoff_event
                            continue

                    yield event

                instance.tasks_completed += 1

            finally:
                instance.status = AgentStatus.IDLE
                instance.current_task = None

    async def _process_handoff(
        self,
        handoff: Handoff,
        task: SwarmTask,
        source_instance: AgentInstance,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Process a handoff request to another agent.

        Args:
            handoff: The handoff request
            task: The current task
            source_instance: The agent instance requesting the handoff

        Yields:
            Events from the handoff execution
        """
        if self._total_handoffs >= self._config.max_handoffs_per_task:
            yield ErrorEvent(error="Maximum handoffs reached")
            return

        self._total_handoffs += 1
        logger.info(
            f"Processing handoff from {source_instance.agent_type.value} "
            f"to {handoff.target_agent or handoff.target_capability}"
        )

        # Select target agent
        target_spec = None
        if handoff.target_agent:
            target_spec = self._registry.get(handoff.target_agent)
        elif handoff.target_capability:
            candidates = self._registry.get_by_capability(handoff.target_capability)
            if candidates:
                target_spec = candidates[0]

        if not target_spec:
            handoff.reject("No suitable agent found")
            yield ErrorEvent(error=f"Handoff failed: no agent for {handoff.target_agent or handoff.target_capability}")
            return

        handoff.target_agent = target_spec.agent_type
        handoff.accept()

        # Create handoff context
        handoff_context = handoff.context or HandoffContext(
            task_description=task.description,
            original_request=task.original_request,
            current_progress="Handed off from previous agent",
        )

        # Phase 4: Include shared blackboard snapshot so the receiving agent has full context
        if self._shared_state:
            try:
                blackboard_snapshot = self._shared_state.to_context_string(max_entries=20)
                if blackboard_snapshot:
                    handoff_context.set_shared_resource("blackboard", blackboard_snapshot)
            except Exception as _bb_err:
                logger.debug("Failed to inject blackboard into handoff context: %s", _bb_err)

        # Execute with target agent
        try:
            async with asyncio.timeout(self._config.handoff_timeout):
                async for event in self._execute_with_agent(
                    task, target_spec, is_coordinator=False, handoff_context=handoff_context
                ):
                    yield event

            # Complete handoff
            self._protocol.complete_handoff(
                handoff.id,
                output=task.result or "",
                summary=f"Completed by {target_spec.agent_type.value}",
            )
            logger.info(f"Handoff {handoff.id[:8]} completed successfully")

        except TimeoutError:
            self._protocol.fail_handoff(handoff.id, "Handoff timed out")
            yield ErrorEvent(error="Handoff timed out")

        except Exception as e:
            self._protocol.fail_handoff(handoff.id, str(e))
            yield ErrorEvent(error=f"Handoff failed: {e!s}")

    async def execute_parallel(
        self,
        tasks: list[SwarmTask],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute multiple tasks in parallel.

        Args:
            tasks: List of tasks to execute in parallel

        Yields:
            Results dict containing all task outputs
        """
        if len(tasks) > self._config.max_parallel_tasks:
            raise ResourceLimitExceeded(f"Too many parallel tasks: {len(tasks)} > {self._config.max_parallel_tasks}")

        logger.info(f"Executing {len(tasks)} tasks in parallel")

        # Create tasks for each execution
        async def collect_events(task: SwarmTask) -> dict[str, Any]:
            events = []
            result = None
            error = None

            try:
                async for event in self.execute(task):
                    events.append(event)
                    if isinstance(event, MessageEvent):
                        result = event.message
                    elif isinstance(event, ErrorEvent):
                        error = event.error
            except Exception as e:
                error = str(e)

            return {
                "task_id": task.id,
                "success": error is None,
                "result": result,
                "error": error,
                "events": events,
            }

        # Execute all tasks concurrently
        results = await asyncio.gather(*[collect_events(task) for task in tasks], return_exceptions=True)

        # Process results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(
                    {
                        "task_id": tasks[i].id,
                        "success": False,
                        "error": str(result),
                    }
                )
            else:
                final_results.append(result)

        yield {
            "completed": len([r for r in final_results if r.get("success")]),
            "failed": len([r for r in final_results if not r.get("success")]),
            "results": final_results,
        }

    async def delegate_subtasks(
        self,
        parent_task: SwarmTask,
        subtasks: list[dict[str, Any]],
    ) -> AsyncGenerator[BaseEvent, None]:
        """Delegate subtasks to specialized agents.

        Used by coordinator agents to distribute work.

        Args:
            parent_task: The parent task being decomposed
            subtasks: List of subtask specifications with:
                - description: Subtask description
                - required_capabilities: Set of required capabilities
                - preferred_agent: Optional preferred agent type

        Yields:
            Events from subtask execution
        """
        logger.info(f"Delegating {len(subtasks)} subtasks from {parent_task.id[:8]}")

        # Create handoffs for parallel execution
        shared_context = HandoffContext(
            task_description=parent_task.description,
            original_request=parent_task.original_request,
            current_progress="Delegated from coordinator",
        )

        handoffs = self._protocol.create_parallel_handoffs(
            source_agent=parent_task.assigned_agent or AgentType.COORDINATOR,
            subtasks=[
                {
                    "target_agent": st.get("preferred_agent"),
                    "target_capability": (
                        next(iter(st.get("required_capabilities", set()))) if st.get("required_capabilities") else None
                    ),
                    "instructions": st.get("description", ""),
                    "expected_output": st.get("expected_output", ""),
                }
                for st in subtasks
            ],
            shared_context=shared_context,
        )

        # Execute handoffs in parallel
        if self._config.enable_parallel_execution:
            tasks_to_run = []
            for _handoff, subtask_spec in zip(handoffs, subtasks, strict=False):
                subtask = SwarmTask(
                    description=subtask_spec.get("description", ""),
                    original_request=parent_task.original_request,
                    context=parent_task.context,
                    required_capabilities=subtask_spec.get("required_capabilities", set()),
                    preferred_agent=subtask_spec.get("preferred_agent"),
                )
                tasks_to_run.append(subtask)

            async for result in self.execute_parallel(tasks_to_run):
                yield MessageEvent(message=f"Completed {result['completed']}/{len(tasks_to_run)} subtasks")
        else:
            # Sequential execution
            for _handoff, subtask_spec in zip(handoffs, subtasks, strict=False):
                subtask = SwarmTask(
                    description=subtask_spec.get("description", ""),
                    original_request=parent_task.original_request,
                    context=parent_task.context,
                )
                async for event in self.execute(subtask):
                    yield event

    def _select_agents(self, task: SwarmTask) -> list[AgentSpec]:
        """Select the best agents for a task.

        Args:
            task: The task to select agents for

        Returns:
            List of suitable agent specs, sorted by match quality
        """
        if task.preferred_agent:
            spec = self._registry.get(task.preferred_agent)
            if spec:
                return [spec]

        return self._registry.select_for_task(
            task_description=task.description,
            context=task.context,
            required_capabilities=task.required_capabilities,
        )

    async def _get_or_create_agent(self, spec: AgentSpec) -> AgentInstance:
        """Get an existing agent instance or create a new one.

        Args:
            spec: Agent specification

        Returns:
            An agent instance
        """
        # Look for idle agent of this type
        for instance in self._agents.values():
            if instance.agent_type == spec.agent_type and instance.status == AgentStatus.IDLE:
                return instance

        # Create new instance
        instance_id = generate_agent_task_id()
        agent = await self._factory.create_agent(spec.agent_type, instance_id, spec)

        # Phase 4: Inject shared StateManifest blackboard so agents can exchange findings
        if hasattr(agent, "state_manifest"):
            agent.state_manifest = self._shared_state

        instance = AgentInstance(
            id=instance_id,
            agent_type=spec.agent_type,
            spec=spec,
            agent=agent,
        )

        self._agents[instance_id] = instance
        logger.debug(f"Created new agent instance: {spec.agent_type.value} ({instance_id[:8]})")

        return instance

    def _build_agent_prompt(
        self,
        task: SwarmTask,
        spec: AgentSpec,
        is_coordinator: bool,
        handoff_context: HandoffContext | None,
    ) -> str:
        """Build the execution prompt for an agent.

        Args:
            task: The task to execute
            spec: Agent specification
            is_coordinator: Whether this is the coordinator
            handoff_context: Optional handoff context

        Returns:
            The formatted prompt string
        """
        parts = [spec.system_prompt_template, "\n\n"]

        if handoff_context:
            parts.append(handoff_context.to_prompt())
            parts.append("\n")

        parts.append(f"## Task\n{task.description}\n")

        if task.original_request and task.original_request != task.description:
            parts.append(f"\n**Original Request:** {task.original_request}\n")

        if is_coordinator:
            parts.append("""
## Delegation Guidelines

As coordinator, you can delegate subtasks to these specialized agents:
- **Researcher**: For information gathering and research
- **Coder**: For code writing and modification
- **Browser**: For web browsing tasks
- **Analyst**: For data analysis
- **Writer**: For content creation
- **Verifier**: For output verification

To delegate, use **either** format:

**Structured JSON (preferred):**
```json
{"handoff": {"agent": "<agent_type>", "task": "<task description>", "expected_output": "<what you expect back>"}}
```

**Marker format (fallback):**
```
[HANDOFF]
agent: <agent_type>
task: <task description>
expected_output: <what you expect back>
[/HANDOFF]
```

You can delegate multiple tasks in parallel when they are independent.
""")

        return "".join(parts)

    # Phase 2: Agent name → AgentType mapping shared by both handoff parsers
    _AGENT_TYPE_MAP: ClassVar[dict[str, Any]] = {
        "researcher": AgentType.RESEARCHER,
        "coder": AgentType.CODER,
        "browser": AgentType.BROWSER,
        "analyst": AgentType.ANALYST,
        "writer": AgentType.WRITER,
        "verifier": AgentType.VERIFIER,
        "reviewer": AgentType.REVIEWER,
        "summarizer": AgentType.SUMMARIZER,
    }

    def _detect_handoff_request(
        self,
        message: str,
        task: SwarmTask,
    ) -> Handoff | None:
        """Detect if an agent is requesting a handoff.

        Phase 2: Tries structured JSON parsing first for reliability, then
        falls back to regex marker parsing for backward compatibility.

        Args:
            message: The agent's output message
            task: The current task

        Returns:
            A Handoff object if a handoff was requested, None otherwise
        """
        # Phase 2: Primary path — try structured JSON handoff format first.
        # Use brace-depth counting to extract the outermost JSON object so that
        # nested payloads like {"handoff": {"agent": "...", "task": "..."}} are
        # correctly matched (the old flat-regex [^{}]* could not match nested {}).
        if '"handoff"' in message:
            try:
                _start = message.index("{")
                _depth = 0
                _end = -1
                for _i, _ch in enumerate(message[_start:], _start):
                    if _ch == "{":
                        _depth += 1
                    elif _ch == "}":
                        _depth -= 1
                        if _depth == 0:
                            _end = _i + 1
                            break
                if _end != -1:
                    data = json.loads(message[_start:_end])
                    result = self._parse_structured_handoff(data, task)
                    if result is not None:
                        logger.debug("Handoff parsed via structured JSON path")
                        return result
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

        # Fallback: regex marker parsing [HANDOFF]...[/HANDOFF]
        return self._parse_regex_handoff(message, task)

    def _parse_structured_handoff(self, data: dict[str, Any], task: SwarmTask) -> Handoff | None:
        """Parse a handoff from a structured JSON dict.

        Phase 2: Handles the structured format:
        {"handoff": {"agent": "researcher", "task": "...", "expected_output": "..."}}

        Args:
            data: Parsed JSON dict containing handoff payload
            task: The current task for context

        Returns:
            Handoff object or None if data is invalid
        """
        handoff_data = data.get("handoff", data)
        agent_name = str(handoff_data.get("agent", "")).lower()
        task_desc = str(handoff_data.get("task", task.description))
        expected_output = str(handoff_data.get("expected_output", ""))

        target_agent = self._AGENT_TYPE_MAP.get(agent_name)
        if not target_agent:
            logger.warning("Structured handoff: unknown agent type '%s'", agent_name)
            return None

        context = HandoffContext(
            task_description=task_desc,
            original_request=task.original_request,
            current_progress=f"Coordinator delegated to {agent_name} (structured)",
        )
        return self._protocol.create_handoff(
            source_agent=task.assigned_agent or AgentType.COORDINATOR,
            target_agent=target_agent,
            reason=HandoffReason.SPECIALIZATION,
            context=context,
            instructions=task_desc,
            expected_output=expected_output,
        )

    def _parse_regex_handoff(self, message: str, task: SwarmTask) -> Handoff | None:
        """Parse a handoff using [HANDOFF]...[/HANDOFF] regex markers.

        Phase 2: Legacy/backward-compatible parsing path, now the fallback.

        Args:
            message: The agent's output message
            task: The current task

        Returns:
            Handoff object or None if no marker found
        """
        import re

        pattern = r"\[HANDOFF\](.*?)\[/HANDOFF\]"
        match = re.search(pattern, message, re.DOTALL)
        if not match:
            return None

        handoff_text = match.group(1)
        agent_match = re.search(r"agent:\s*(\w+)", handoff_text, re.IGNORECASE)
        task_match = re.search(r"task:\s*(.+?)(?=expected_output:|$)", handoff_text, re.IGNORECASE | re.DOTALL)
        output_match = re.search(r"expected_output:\s*(.+)", handoff_text, re.IGNORECASE | re.DOTALL)

        if not agent_match:
            return None

        agent_name = agent_match.group(1).lower()
        target_agent = self._AGENT_TYPE_MAP.get(agent_name)
        if not target_agent:
            logger.warning("Regex handoff: unknown agent type '%s'", agent_name)
            return None

        context = HandoffContext(
            task_description=task_match.group(1).strip() if task_match else task.description,
            original_request=task.original_request,
            current_progress=f"Coordinator delegated to {agent_name}",
        )
        return self._protocol.create_handoff(
            source_agent=task.assigned_agent or AgentType.COORDINATOR,
            target_agent=target_agent,
            reason=HandoffReason.SPECIALIZATION,
            context=context,
            instructions=task_match.group(1).strip() if task_match else "",
            expected_output=output_match.group(1).strip() if output_match else "",
        )

    def get_stats(self) -> dict[str, Any]:
        """Get swarm statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            "active_agents": len([a for a in self._agents.values() if a.status == AgentStatus.WORKING]),
            "total_agents": len(self._agents),
            "active_tasks": len(self._active_tasks),
            "tasks_completed": self._total_tasks_completed,
            "total_handoffs": self._total_handoffs,
            "total_errors": self._total_errors,
            "agents_by_type": {
                t.value: len([a for a in self._agents.values() if a.agent_type == t])
                for t in AgentType
                if any(a.agent_type == t for a in self._agents.values())
            },
        }

    async def shutdown(self) -> None:
        """Shutdown the swarm gracefully.

        Waits for active tasks to complete and cleans up resources.
        """
        logger.info("Shutting down swarm...")

        # Wait for active tasks (with timeout)
        if self._active_tasks:
            logger.info(f"Waiting for {len(self._active_tasks)} active tasks to complete...")
            try:
                async with asyncio.timeout(30):
                    while self._active_tasks:  # noqa: ASYNC110
                        await asyncio.sleep(0.5)
            except TimeoutError:
                logger.warning("Shutdown timeout, some tasks may be incomplete")

        # Clear agents
        self._agents.clear()
        logger.info("Swarm shutdown complete")
