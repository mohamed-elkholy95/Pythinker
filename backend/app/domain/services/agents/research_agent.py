"""Research sub-agent for wide research pattern.

This module implements the ResearchSubAgent, a lightweight agent for
individual research tasks in the wide research pattern. Each instance
has its own context, preventing interference between parallel research tasks.
"""

import logging
from typing import Any, Protocol, runtime_checkable

from app.domain.models.research_task import ResearchTask

logger = logging.getLogger(__name__)


@runtime_checkable
class SearchToolProtocol(Protocol):
    """Protocol for search tool interface."""

    async def execute(self, query: str) -> dict[str, Any]:
        """Execute a search query.

        Args:
            query: The search query string

        Returns:
            Dictionary containing search results
        """
        ...


@runtime_checkable
class LLMProtocol(Protocol):
    """Protocol for LLM chat interface."""

    async def chat(self, messages: list[dict[str, str]]) -> Any:
        """Send chat messages to the LLM.

        Args:
            messages: List of message dictionaries with role and content

        Returns:
            Response object with content attribute or string
        """
        ...


class ResearchSubAgent:
    """
    Lightweight sub-agent for individual research tasks.

    Each instance has its own context, preventing interference
    between parallel research tasks. This ensures consistent
    quality regardless of batch position.

    Attributes:
        session_id: The session identifier for this research
        llm: Language model for synthesis
        tools: Dictionary of available tools (search, etc.)
        max_iterations: Maximum iterations for research loop
    """

    SYSTEM_PROMPT = """You are a research assistant. Your task is to:
1. Search for information on the given topic
2. Extract key facts and insights
3. Cite sources where possible
4. Provide a concise, factual summary

Focus on accuracy and relevance. Do not speculate."""

    # Maximum number of search results to process
    MAX_SEARCH_RESULTS = 5

    def __init__(
        self,
        session_id: str,
        llm: LLMProtocol,
        tools: dict[str, SearchToolProtocol],
        max_iterations: int = 3,
    ):
        """
        Initialize the research sub-agent.

        Args:
            session_id: The session identifier for this research
            llm: Language model for synthesis (must implement LLMProtocol)
            tools: Dictionary of available tools (key: tool name, value: tool instance)
            max_iterations: Maximum iterations for research loop (default: 3)
        """
        self.session_id = session_id
        self.llm = llm
        self.tools = tools
        self.max_iterations = max_iterations

    async def research(self, task: ResearchTask) -> str:
        """
        Execute research for a single task.

        Uses search tool to gather information, then synthesizes
        with LLM into a coherent finding.

        Args:
            task: The research task containing the query

        Returns:
            Research findings as a string
        """
        logger.debug(
            "Starting research for task %s: %s",
            task.id,
            task.query,
        )

        # First, search for information
        search_tool = self.tools.get("search")
        context = ""

        if search_tool:
            logger.debug("Executing search for query: %s", task.query)
            search_result = await search_tool.execute(query=task.query)

            # Extract content from results
            content_parts = []
            if isinstance(search_result, dict) and "results" in search_result:
                for r in search_result["results"][: self.MAX_SEARCH_RESULTS]:
                    if "content" in r:
                        content_parts.append(r["content"])
                    elif "snippet" in r:
                        content_parts.append(r["snippet"])

            context = "\n\n".join(content_parts)
            logger.debug(
                "Search returned %d results, extracted %d content parts",
                len(search_result.get("results", [])),
                len(content_parts),
            )
        else:
            logger.warning("No search tool available for research task %s", task.id)

        # Synthesize with LLM
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Research topic: {task.query}\n\nContext:\n{context}\n\nProvide a concise research summary.",
            },
        ]

        logger.debug("Sending research synthesis request to LLM")
        response = await self.llm.chat(messages)

        # Handle both object with content attribute and plain string responses
        result = response.content if hasattr(response, "content") else str(response)

        logger.debug(
            "Completed research for task %s, result length: %d chars",
            task.id,
            len(result),
        )

        return result
