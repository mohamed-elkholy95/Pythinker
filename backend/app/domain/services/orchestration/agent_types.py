"""Agent type definitions and registry for the multi-agent orchestration system.

Defines specialized agent types with their capabilities, tool access,
and routing rules for automatic task delegation.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AgentCapability(str, Enum):
    """Capabilities that agents can possess."""

    # Core capabilities
    PLANNING = "planning"  # Can create and manage plans
    EXECUTION = "execution"  # Can execute general tasks
    ANALYSIS = "analysis"  # Can analyze data/code/content

    # Domain-specific capabilities
    CODE_WRITING = "code_writing"  # Can write code
    CODE_REVIEW = "code_review"  # Can review and critique code
    CODE_EXECUTION = "code_execution"  # Can execute Python/JS/Bash/SQL code in sandbox
    WEB_BROWSING = "web_browsing"  # Can browse the web
    WEB_SEARCH = "web_search"  # Can search the web
    FILE_OPERATIONS = "file_operations"  # Can read/write files
    SHELL_COMMANDS = "shell_commands"  # Can execute shell commands

    # Advanced capabilities
    RESEARCH = "research"  # Deep research and information gathering
    SUMMARIZATION = "summarization"  # Content summarization
    TRANSLATION = "translation"  # Language translation
    DATA_EXTRACTION = "data_extraction"  # Extract structured data
    VERIFICATION = "verification"  # Verify facts and outputs
    CREATIVE = "creative"  # Creative writing/design


class AgentType(str, Enum):
    """Types of specialized agents available in the swarm."""

    # Core agents
    COORDINATOR = "coordinator"  # Orchestrates other agents
    PLANNER = "planner"  # Creates task plans
    EXECUTOR = "executor"  # General-purpose executor

    # Specialized agents
    RESEARCHER = "researcher"  # Deep research tasks
    CODER = "coder"  # Code writing and modification
    REVIEWER = "reviewer"  # Code/content review
    BROWSER = "browser"  # Web browsing specialist
    ANALYST = "analyst"  # Data analysis
    WRITER = "writer"  # Content writing
    VERIFIER = "verifier"  # Output verification

    # Meta agents
    CRITIC = "critic"  # Quality assurance
    SUMMARIZER = "summarizer"  # Task summarization


@dataclass
class AgentSpec:
    """Specification for an agent type including capabilities and configuration."""

    agent_type: AgentType
    name: str
    description: str
    capabilities: set[AgentCapability]
    tools: list[str]  # Tool names this agent has access to
    system_prompt_template: str
    max_iterations: int = 50
    priority: int = 0  # Higher = more likely to be selected

    # Routing configuration
    trigger_patterns: list[str] = field(default_factory=list)  # Regex patterns
    required_context: list[str] = field(default_factory=list)  # Required context keys

    # Resource limits
    max_tokens: int = 100000
    max_concurrent_tasks: int = 1

    def matches_task(self, task_description: str, context: dict[str, Any]) -> float:
        """Calculate how well this agent matches a task.

        Returns a score between 0.0 and 1.0, where higher is better.
        """
        score = 0.0

        # Check trigger patterns
        for pattern in self.trigger_patterns:
            try:
                if re.search(pattern, task_description, re.IGNORECASE):
                    score += 0.3
                    break
            except re.error:
                logger.warning(f"Invalid regex pattern: {pattern}")

        # Check required context
        if self.required_context:
            context_matches = sum(1 for key in self.required_context if key in context)
            context_score = context_matches / len(self.required_context)
            score += context_score * 0.2

        # Base priority contribution
        score += min(self.priority / 100, 0.3)

        # Capability-based matching
        capability_keywords = {
            AgentCapability.CODE_WRITING: ["code", "implement", "write", "function", "class", "script"],
            AgentCapability.CODE_REVIEW: ["review", "critique", "check", "verify code", "bugs"],
            AgentCapability.CODE_EXECUTION: [
                "execute",
                "run code",
                "python",
                "javascript",
                "calculate",
                "script",
                "compute",
            ],
            AgentCapability.WEB_BROWSING: ["browse", "visit", "navigate", "website", "page"],
            AgentCapability.WEB_SEARCH: ["search", "find", "look up", "google", "query"],
            AgentCapability.RESEARCH: ["research", "investigate", "study", "analyze", "deep dive"],
            AgentCapability.FILE_OPERATIONS: ["file", "read", "write", "save", "create file"],
            AgentCapability.SHELL_COMMANDS: ["run", "execute", "shell", "command", "terminal"],
            AgentCapability.SUMMARIZATION: ["summarize", "summary", "brief", "overview"],
            AgentCapability.VERIFICATION: ["verify", "validate", "confirm", "check"],
        }

        task_lower = task_description.lower()
        for capability, keywords in capability_keywords.items():
            if capability in self.capabilities:
                for keyword in keywords:
                    if keyword in task_lower:
                        score += 0.1
                        break

        return min(score, 1.0)


class AgentRegistry:
    """Registry of available agent types and their specifications.

    Provides methods to register, retrieve, and select agents based on tasks.
    """

    def __init__(self):
        self._agents: dict[AgentType, AgentSpec] = {}
        self._register_default_agents()

    def _register_default_agents(self) -> None:
        """Register the default set of specialized agents."""

        # Coordinator Agent - Orchestrates task delegation
        self.register(
            AgentSpec(
                agent_type=AgentType.COORDINATOR,
                name="Coordinator",
                description="Orchestrates complex tasks by delegating to specialized agents",
                capabilities={
                    AgentCapability.PLANNING,
                    AgentCapability.ANALYSIS,
                },
                tools=["message_ask_user"],
                system_prompt_template="""You are a Coordinator agent responsible for:
1. Analyzing complex tasks and breaking them into subtasks
2. Selecting the most appropriate specialized agents for each subtask
3. Managing handoffs between agents
4. Aggregating results from multiple agents

When delegating, consider each agent's capabilities and the task requirements.
Prefer parallel execution when subtasks are independent.""",
                priority=100,
                trigger_patterns=[r"complex", r"multiple steps", r"coordinate"],
                max_iterations=20,
            )
        )

        # Researcher Agent - Deep research and information gathering
        self.register(
            AgentSpec(
                agent_type=AgentType.RESEARCHER,
                name="Researcher",
                description="Specializes in deep research, information gathering, and analysis",
                capabilities={
                    AgentCapability.RESEARCH,
                    AgentCapability.WEB_SEARCH,
                    AgentCapability.WEB_BROWSING,
                    AgentCapability.ANALYSIS,
                    AgentCapability.DATA_EXTRACTION,
                },
                tools=[
                    "info_search_web",
                    "browser_view",
                    "browser_get_content",
                    "file_read",
                    "file_write",
                ],
                system_prompt_template="""You are a Research specialist agent. Your expertise includes:
1. Conducting thorough web searches to gather information
2. Analyzing and synthesizing information from multiple sources
3. Extracting key facts and data points
4. Providing well-sourced, accurate research summaries

Always cite your sources and verify information when possible.
Focus on depth and accuracy over speed.""",
                priority=80,
                trigger_patterns=[
                    r"research",
                    r"investigate",
                    r"find out",
                    r"look up",
                    r"what is",
                    r"how does",
                    r"learn about",
                    r"gather information",
                ],
                max_iterations=30,
            )
        )

        # Coder Agent - Code writing and modification
        self.register(
            AgentSpec(
                agent_type=AgentType.CODER,
                name="Coder",
                description="Specializes in writing, modifying, debugging, and executing code",
                capabilities={
                    AgentCapability.CODE_WRITING,
                    AgentCapability.CODE_EXECUTION,
                    AgentCapability.FILE_OPERATIONS,
                    AgentCapability.SHELL_COMMANDS,
                    AgentCapability.ANALYSIS,
                },
                tools=[
                    "file_read",
                    "file_write",
                    "file_search",
                    "file_list_directory",
                    "shell_run",
                    "code_execute",
                    "code_execute_python",
                    "code_execute_javascript",
                    "code_list_artifacts",
                    "code_read_artifact",
                ],
                system_prompt_template="""You are a Coding specialist agent. Your expertise includes:
1. Writing clean, efficient, and well-documented code
2. Debugging and fixing code issues
3. Refactoring and improving existing code
4. Following best practices and design patterns

Always write tests when appropriate.
Explain your code decisions clearly.
Follow the project's existing style conventions.""",
                priority=85,
                trigger_patterns=[
                    r"write code",
                    r"implement",
                    r"create function",
                    r"fix bug",
                    r"refactor",
                    r"code",
                    r"script",
                    r"program",
                    r"debug",
                ],
                max_iterations=50,
            )
        )

        # Reviewer Agent - Code and content review
        self.register(
            AgentSpec(
                agent_type=AgentType.REVIEWER,
                name="Reviewer",
                description="Specializes in reviewing code and content for quality",
                capabilities={
                    AgentCapability.CODE_REVIEW,
                    AgentCapability.VERIFICATION,
                    AgentCapability.ANALYSIS,
                },
                tools=[
                    "file_read",
                    "file_search",
                ],
                system_prompt_template="""You are a Review specialist agent. Your expertise includes:
1. Reviewing code for bugs, security issues, and best practices
2. Providing constructive feedback with specific suggestions
3. Checking for consistency with project standards
4. Verifying logical correctness and edge cases

Be thorough but constructive.
Prioritize issues by severity.
Provide actionable suggestions for improvement.""",
                priority=70,
                trigger_patterns=[
                    r"review",
                    r"check",
                    r"audit",
                    r"critique",
                    r"find issues",
                    r"code review",
                    r"verify",
                ],
                max_iterations=20,
            )
        )

        # Browser Agent - Web browsing specialist
        self.register(
            AgentSpec(
                agent_type=AgentType.BROWSER,
                name="Browser",
                description="Specializes in web browsing and content extraction",
                capabilities={
                    AgentCapability.WEB_BROWSING,
                    AgentCapability.DATA_EXTRACTION,
                },
                tools=[
                    "browser_view",
                    "browser_click",
                    "browser_input",
                    "browser_scroll",
                    "browser_get_content",
                    "browser_screenshot",
                ],
                system_prompt_template="""You are a Browser specialist agent. Your expertise includes:
1. Navigating websites efficiently
2. Interacting with web forms and UI elements
3. Extracting specific content from web pages
4. Handling authentication and multi-step web processes

Be precise with selectors and interactions.
Verify page state before taking actions.
Handle errors gracefully and retry when appropriate.""",
                priority=75,
                trigger_patterns=[
                    r"browse",
                    r"visit",
                    r"navigate to",
                    r"go to website",
                    r"click",
                    r"fill form",
                    r"download from",
                ],
                max_iterations=40,
            )
        )

        # Writer Agent - Content writing
        self.register(
            AgentSpec(
                agent_type=AgentType.WRITER,
                name="Writer",
                description="Specializes in writing high-quality content",
                capabilities={
                    AgentCapability.CREATIVE,
                    AgentCapability.SUMMARIZATION,
                    AgentCapability.TRANSLATION,
                },
                tools=[
                    "file_write",
                    "file_read",
                ],
                system_prompt_template="""You are a Writing specialist agent. Your expertise includes:
1. Writing clear, engaging, and well-structured content
2. Adapting tone and style for different audiences
3. Creating various document types (reports, articles, documentation)
4. Editing and improving existing content

Focus on clarity and readability.
Use appropriate formatting (headings, lists, etc.).
Maintain consistent tone throughout.""",
                priority=65,
                trigger_patterns=[
                    r"write",
                    r"draft",
                    r"compose",
                    r"create document",
                    r"article",
                    r"report",
                    r"documentation",
                ],
                max_iterations=25,
            )
        )

        # Analyst Agent - Data analysis
        self.register(
            AgentSpec(
                agent_type=AgentType.ANALYST,
                name="Analyst",
                description="Specializes in data analysis, computation, and insights",
                capabilities={
                    AgentCapability.ANALYSIS,
                    AgentCapability.CODE_EXECUTION,
                    AgentCapability.DATA_EXTRACTION,
                    AgentCapability.SUMMARIZATION,
                },
                tools=[
                    "file_read",
                    "file_write",
                    "shell_run",
                    "code_execute",
                    "code_execute_python",
                    "code_list_artifacts",
                    "code_read_artifact",
                ],
                system_prompt_template="""You are an Analysis specialist agent. Your expertise includes:
1. Analyzing data to extract meaningful insights
2. Identifying patterns, trends, and anomalies
3. Creating visualizations and summaries
4. Making data-driven recommendations

Be precise with calculations and statistics.
Clearly explain your methodology.
Highlight key findings prominently.""",
                priority=70,
                trigger_patterns=[r"analyze", r"analysis", r"data", r"statistics", r"insights", r"trends", r"patterns"],
                max_iterations=30,
            )
        )

        # Verifier Agent - Output verification
        self.register(
            AgentSpec(
                agent_type=AgentType.VERIFIER,
                name="Verifier",
                description="Verifies outputs and validates results",
                capabilities={
                    AgentCapability.VERIFICATION,
                    AgentCapability.ANALYSIS,
                },
                tools=[
                    "file_read",
                    "shell_run",
                    "browser_get_content",
                ],
                system_prompt_template="""You are a Verification specialist agent. Your expertise includes:
1. Validating that outputs meet requirements
2. Testing code and verifying correctness
3. Cross-referencing information for accuracy
4. Identifying inconsistencies and errors

Be thorough and systematic.
Document verification steps taken.
Report both passes and failures clearly.""",
                priority=60,
                trigger_patterns=[r"verify", r"validate", r"test", r"check", r"confirm", r"ensure"],
                max_iterations=20,
            )
        )

        # Summarizer Agent - Task summarization
        self.register(
            AgentSpec(
                agent_type=AgentType.SUMMARIZER,
                name="Summarizer",
                description="Creates concise summaries of completed work",
                capabilities={
                    AgentCapability.SUMMARIZATION,
                    AgentCapability.ANALYSIS,
                },
                tools=[
                    "file_read",
                ],
                system_prompt_template="""You are a Summarization specialist agent. Your expertise includes:
1. Creating concise, accurate summaries
2. Highlighting key accomplishments and results
3. Organizing information hierarchically
4. Adapting detail level for different audiences

Be concise but complete.
Structure summaries with clear sections.
Include relevant metrics and outcomes.""",
                priority=50,
                trigger_patterns=[r"summarize", r"summary", r"recap", r"overview", r"brief"],
                max_iterations=10,
            )
        )

    def register(self, spec: AgentSpec) -> None:
        """Register an agent specification."""
        self._agents[spec.agent_type] = spec
        logger.debug(f"Registered agent type: {spec.agent_type.value}")

    def get(self, agent_type: AgentType) -> AgentSpec | None:
        """Get an agent specification by type."""
        return self._agents.get(agent_type)

    def get_all(self) -> list[AgentSpec]:
        """Get all registered agent specifications."""
        return list(self._agents.values())

    def select_for_task(
        self,
        task_description: str,
        context: dict[str, Any],
        exclude: set[AgentType] | None = None,
        required_capabilities: set[AgentCapability] | None = None,
    ) -> list[AgentSpec]:
        """Select the best agents for a given task.

        Args:
            task_description: Description of the task
            context: Task context dictionary
            exclude: Agent types to exclude from selection
            required_capabilities: Required capabilities (all must be present)

        Returns:
            List of agent specs, sorted by match score (best first)
        """
        exclude = exclude or set()
        candidates = []

        for spec in self._agents.values():
            # Skip excluded types
            if spec.agent_type in exclude:
                continue

            # Check required capabilities
            if required_capabilities and not required_capabilities.issubset(spec.capabilities):
                continue

            # Calculate match score
            score = spec.matches_task(task_description, context)
            if score > 0:
                candidates.append((spec, score))

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)

        return [spec for spec, _ in candidates]

    def get_by_capability(self, capability: AgentCapability) -> list[AgentSpec]:
        """Get all agents with a specific capability."""
        return [spec for spec in self._agents.values() if capability in spec.capabilities]


# Global registry instance
_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry instance."""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
