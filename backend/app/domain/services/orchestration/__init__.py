"""Multi-Agent Orchestration Layer.

This module provides infrastructure for orchestrating multiple specialized agents
working together on complex tasks. Key components:

- Swarm: Manages a pool of specialized agents
- Handoff: Protocol for transferring work between agents
- AgentRegistry: Registry of available agent types
- CoordinatorFlow: High-level flow integrating with existing system
- AgentFactory: Factory for creating specialized agent instances

Architecture follows the swarm pattern where:
1. A coordinator receives the task
2. Specialized agents are selected based on task requirements
3. Agents can hand off work to other agents
4. Results are aggregated and returned

Example usage:
    from app.domain.services.orchestration import (
        Swarm, SwarmConfig, SwarmTask, AgentType
    )

    # Create swarm with factory
    swarm = Swarm(
        agent_factory=agent_factory,
        config=SwarmConfig(max_concurrent_agents=3)
    )

    # Execute a task
    task = SwarmTask(
        description="Research and summarize recent AI developments",
        required_capabilities={AgentCapability.RESEARCH, AgentCapability.SUMMARIZATION}
    )

    async for event in swarm.execute(task):
        yield event

For high-level integration with the flow system:
    from app.domain.services.orchestration import (
        CoordinatorFlow, CoordinatorMode, create_coordinator_flow
    )

    flow = create_coordinator_flow(
        agent_id="agent-123",
        session_id="session-456",
        agent_repository=repo,
        session_repository=session_repo,
        llm=llm,
        sandbox=sandbox,
        browser=browser,
        json_parser=parser,
        mcp_tool=mcp,
        mode=CoordinatorMode.AUTO,
    )

    async for event in flow.run(message):
        yield event
"""

from app.domain.services.orchestration.agent_factory import (
    DefaultAgentFactory,
    SpecializedAgentFactory,
    SwarmAgent,
)
from app.domain.services.orchestration.agent_types import (
    AgentCapability,
    AgentRegistry,
    AgentSpec,
    AgentType,
    get_agent_registry,
)
from app.domain.services.orchestration.coordinator_flow import (
    CoordinatorFlow,
    CoordinatorMode,
    TaskComplexity,
    create_coordinator_flow,
)
from app.domain.services.orchestration.handoff import (
    Handoff,
    HandoffContext,
    HandoffProtocol,
    HandoffReason,
    HandoffResult,
    HandoffStatus,
    get_handoff_protocol,
)
from app.domain.services.orchestration.swarm import (
    AgentInstance,
    Swarm,
    SwarmConfig,
    SwarmResult,
    SwarmTask,
)
from app.domain.services.orchestration.swarm import (
    AgentStatus as SwarmAgentStatus,
)

__all__ = [
    # Agent Types
    "AgentType",
    "AgentCapability",
    "AgentSpec",
    "AgentRegistry",
    "get_agent_registry",
    # Handoff Protocol
    "Handoff",
    "HandoffContext",
    "HandoffReason",
    "HandoffResult",
    "HandoffStatus",
    "HandoffProtocol",
    "get_handoff_protocol",
    # Swarm
    "Swarm",
    "SwarmConfig",
    "SwarmTask",
    "SwarmResult",
    "SwarmAgentStatus",
    "AgentInstance",
    # Agent Factory
    "SwarmAgent",
    "DefaultAgentFactory",
    "SpecializedAgentFactory",
    # Coordinator Flow
    "CoordinatorFlow",
    "CoordinatorMode",
    "TaskComplexity",
    "create_coordinator_flow",
]
