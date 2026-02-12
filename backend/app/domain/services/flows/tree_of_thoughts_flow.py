"""Tree-of-Thoughts Flow for multi-path exploration.

.. deprecated::
    TreeOfThoughtsFlow is experimental and not used in production.
    Use PlanActFlow via FlowMode.PLAN_ACT instead.

This flow enables exploration of multiple solution strategies for complex tasks,
implementing the Tree-of-Thoughts pattern:

1. Analyze task complexity
2. If complex, branch into multiple strategies
3. Explore paths (sequentially or in parallel)
4. Score paths and abandon low-performers
5. Select best path or synthesize results
6. Continue with standard execution

For simple/moderate tasks, falls back to standard linear execution.
"""

import logging
from collections.abc import AsyncGenerator

from app.domain.external.browser import Browser
from app.domain.external.llm import LLM
from app.domain.external.observability import get_tracer
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    MessageEvent,
    PathEvent,
    PlanEvent,
    PlanStatus,
    TitleEvent,
)
from app.domain.models.message import Message
from app.domain.models.path_state import (
    TreeOfThoughtsConfig,
)
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.flows.base import BaseFlow
from app.domain.services.flows.complexity_analyzer import TaskComplexityAnalyzer
from app.domain.services.flows.path_aggregator import PathAggregator
from app.domain.services.flows.path_explorer import PathExplorer
from app.domain.services.flows.path_scorer import PathScorer
from app.domain.services.tools.browser import BrowserTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.idle import IdleTool
from app.domain.services.tools.mcp import MCPTool
from app.domain.services.tools.message import MessageTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.shell import ShellTool
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


class TreeOfThoughtsFlow(BaseFlow):
    """Flow implementing Tree-of-Thoughts multi-path exploration.

    For complex tasks, this flow:
    1. Analyzes task complexity
    2. Creates multiple strategy paths
    3. Explores paths with early abandonment
    4. Aggregates results from best paths

    Falls back to linear execution for simple tasks.
    """

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        session_id: str,
        session_repository: SessionRepository,
        llm: LLM,
        sandbox: Sandbox,
        browser: Browser,
        json_parser: JsonParser,
        mcp_tool: MCPTool,
        search_engine: SearchEngine | None = None,
        cdp_url: str | None = None,
        config: TreeOfThoughtsConfig | None = None,
        browser_agent_enabled: bool = False,
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self._llm = llm
        self._json_parser = json_parser
        self.config = config or TreeOfThoughtsConfig()

        # Build tools
        tools = [ShellTool(sandbox), BrowserTool(browser), FileTool(sandbox, session_id=session_id), MessageTool(), IdleTool(), mcp_tool]

        # Pass browser to SearchTool for visual search when search_prefer_browser is enabled
        if search_engine:
            tools.append(SearchTool(search_engine, browser=browser))

        if cdp_url and browser_agent_enabled:
            from app.domain.services.tools.browser_agent import BrowserAgentTool

            tools.append(BrowserAgentTool(cdp_url))

        # Create agents
        self.planner = PlannerAgent(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
        )

        self.executor = ExecutionAgent(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
        )

        # Create ToT components
        self.complexity_analyzer = TaskComplexityAnalyzer(llm=llm, json_parser=json_parser, config=self.config)

        self.path_explorer = PathExplorer(planner=self.planner, executor=self.executor, config=self.config)

        self.path_scorer = PathScorer(llm=llm, json_parser=json_parser, config=self.config)

        self.path_aggregator = PathAggregator(llm=llm, json_parser=json_parser, config=self.config)

        # Track tool descriptions for complexity analysis
        self._tools_summary = self._build_tools_summary(tools)

    def _build_tools_summary(self, tools) -> str:
        """Build a summary of available tools for complexity analysis."""
        tool_names = []
        for tool in tools:
            for tool_def in tool.get_tools():
                name = tool_def.get("function", {}).get("name", "")
                if name:
                    tool_names.append(name)
        return ", ".join(tool_names[:15])  # Limit for prompt

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """Execute the Tree-of-Thoughts flow.

        Args:
            message: User message to process

        Yields:
            Events from execution
        """
        tracer = get_tracer()

        with tracer.trace(
            "tree-of-thoughts-flow",
            agent_id=self._agent_id,
            session_id=self._session_id,
            attributes={"message.preview": message.message[:100]},
        ):
            # Step 1: Analyze complexity
            logger.info("Analyzing task complexity")
            analysis = await self.complexity_analyzer.analyze(task=message.message, tools_summary=self._tools_summary)

            logger.info(f"Complexity: {analysis.complexity.value}, Branching: {analysis.branching_decision.value}")

            # Step 2: Decide on approach
            if not self.complexity_analyzer.should_use_tot(analysis):
                # Fall back to linear execution
                logger.info("Using linear execution (complexity below threshold)")
                async for event in self._run_linear(message):
                    yield event
                return

            # Step 3: Multi-path exploration
            logger.info(f"Using Tree-of-Thoughts with {len(analysis.suggested_strategies)} strategies")

            # Initialize path scorer with goal
            self.path_scorer.goal = message.message

            # Create paths
            strategies = self.complexity_analyzer.get_strategy_plans(analysis)
            list(self.path_explorer.create_paths(strategies, message))

            # Emit path creation events
            for path in self.path_explorer.get_paths():
                yield PathEvent(path_id=path.id, action="created", description=path.description)

            # Explore paths
            async for event in self.path_explorer.explore_all_paths(
                message=message,
                scorer=self.path_scorer,
                parallel=False,  # Sequential for now (safer)
            ):
                yield event

            # Step 4: Aggregate results
            logger.info("Aggregating path results")
            aggregation = await self.path_aggregator.aggregate(
                paths=self.path_explorer.get_paths(), goal=message.message, synthesize=True
            )

            if aggregation["success"]:
                best_path = self.path_explorer.get_best_path()
                if best_path:
                    yield PathEvent(
                        path_id=best_path.id,
                        action="selected",
                        score=best_path.score,
                        description=f"Selected: {best_path.description}",
                    )

                # Generate summary
                summary = self.path_aggregator.generate_summary(
                    paths=self.path_explorer.get_paths(), goal=message.message
                )

                yield MessageEvent(message=summary)

                # If synthesis available, include it
                if "synthesis" in aggregation:
                    yield MessageEvent(message=f"\n## Synthesized Result\n\n{aggregation['synthesis']}")
            else:
                # No successful paths
                yield MessageEvent(
                    message=f"Tree-of-Thoughts exploration completed but no paths succeeded. "
                    f"Error: {aggregation.get('error', 'Unknown')}"
                )

            yield DoneEvent()

    async def _run_linear(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """Fall back to linear PlanAct execution.

        Args:
            message: User message

        Yields:
            Events from linear execution
        """
        # Create plan
        async for event in self.planner.create_plan(message):
            if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                yield TitleEvent(title=event.plan.title)
                self._current_plan = event.plan
            yield event

        if not hasattr(self, "_current_plan") or not self._current_plan:
            yield MessageEvent(message="Failed to create plan")
            yield DoneEvent()
            return

        # Execute steps
        plan = self._current_plan
        for step in plan.steps:
            async for event in self.executor.execute_step(plan, step, message):
                yield event

        # Summarize
        async for event in self.executor.summarize():
            yield event

        yield DoneEvent()

    def is_done(self) -> bool:
        """Check if flow is complete."""
        return True
