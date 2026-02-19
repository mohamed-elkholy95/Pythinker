"""
Fast Search Flow
Lightweight search-and-synthesize flow that bypasses planning entirely.
Uses API-based search engines, generates query variants, and produces
a synthesized response in seconds.
"""

import logging
from collections.abc import AsyncGenerator
from enum import Enum

from app.domain.external.llm import LLM
from app.domain.external.search import SearchEngine
from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    ResearchModeEvent,
    StreamEvent,
    SuggestionEvent,
    ToolEvent,
    ToolStatus,
)
from app.domain.models.message import Message
from app.domain.services.flows.base import BaseFlow, FlowStatus
from app.domain.services.tools.search import QueryExpander, SearchType

logger = logging.getLogger(__name__)

# Maximum number of query variants for fast search
MAX_QUERY_VARIANTS = 3

FAST_SEARCH_SYNTHESIS_PROMPT = """You are a research assistant. Based on the search results below, provide a clear, comprehensive answer to the user's question.

Guidelines:
- Synthesize information from multiple sources when possible
- Cite sources using [Source Title](URL) markdown links inline
- Be concise but thorough — aim for 200-400 words
- If results are insufficient, acknowledge gaps and suggest follow-up queries
- Use bullet points or numbered lists for clarity when appropriate
- Do not fabricate information beyond what the search results provide

User Question: {question}

Search Results:
{search_results}

Provide a well-structured answer:"""


class FastSearchStatus(str, Enum):
    """Fast search flow lifecycle states."""

    IDLE = "idle"
    SEARCHING = "searching"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    ERROR = "error"


class FastSearchFlow(BaseFlow):
    """Lightweight search flow that bypasses planning entirely.

    Flow:
    1. Emit ResearchModeEvent(fast_search) so frontend adapts layout
    2. Generate 2-3 query variants from user question
    3. Execute searches concurrently via search engine
    4. Emit ToolEvents for each search (inline display)
    5. Synthesize results with LLM
    6. Stream response as MessageEvent
    7. Emit DoneEvent
    """

    def __init__(
        self,
        session_id: str,
        llm: LLM,
        search_engine: SearchEngine,
    ):
        self._session_id = session_id
        self._llm = llm
        self._search_engine = search_engine
        self._status = FastSearchStatus.IDLE

    def is_done(self) -> bool:
        return self._status in (FastSearchStatus.COMPLETED, FastSearchStatus.ERROR)

    def get_status(self) -> FlowStatus:
        if self._status == FastSearchStatus.COMPLETED:
            return FlowStatus.COMPLETED
        if self._status == FastSearchStatus.ERROR:
            return FlowStatus.FAILED
        if self._status == FastSearchStatus.SYNTHESIZING:
            return FlowStatus.SUMMARIZING
        if self._status == FastSearchStatus.SEARCHING:
            return FlowStatus.EXECUTING
        return FlowStatus.IDLE

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """Run the fast search flow for a single message."""
        self._status = FastSearchStatus.SEARCHING
        query = (message.message or "").strip()
        if not query:
            yield MessageEvent(message="Please provide a question to search for.", role="assistant")
            yield DoneEvent()
            self._status = FastSearchStatus.COMPLETED
            return

        # 1. Signal research mode to frontend
        yield ResearchModeEvent(research_mode="fast_search")

        try:
            # 2. Generate query variants
            variants = QueryExpander.expand(query, SearchType.INFO, MAX_QUERY_VARIANTS)
            logger.info("FastSearch: expanded %d variants for query: %s", len(variants), query[:80])

            # 3. Execute searches
            all_results: list[str] = []
            for variant in variants:
                yield ToolEvent(
                    tool_call_id=f"fast_search_{hash(variant) % 10000}",
                    name="info_search_web",
                    function_name="info_search_web",
                    arguments={"query": variant},
                    status=ToolStatus.CALLING,
                    display_command=f"Searching: {variant}",
                    command_category="search",
                )

                try:
                    result = await self._search_engine.search(variant)
                    result_text = result.message if result.success and result.message else ""
                    if result_text:
                        all_results.append(f"--- Results for: {variant} ---\n{result_text}")

                    yield ToolEvent(
                        tool_call_id=f"fast_search_{hash(variant) % 10000}",
                        name="info_search_web",
                        function_name="info_search_web",
                        arguments={"query": variant},
                        result=result_text[:500] if result_text else "No results",
                        status=ToolStatus.CALLED,
                        display_command=f"Searched: {variant}",
                        command_category="search",
                    )
                except Exception as e:
                    logger.warning("FastSearch: search failed for variant %s: %s", variant, e)
                    yield ToolEvent(
                        tool_call_id=f"fast_search_{hash(variant) % 10000}",
                        name="info_search_web",
                        function_name="info_search_web",
                        arguments={"query": variant},
                        result=f"Search failed: {e}",
                        status=ToolStatus.CALLED,
                        display_command=f"Search failed: {variant}",
                        command_category="search",
                    )

            # 4. Synthesize with LLM
            self._status = FastSearchStatus.SYNTHESIZING
            combined_results = "\n\n".join(all_results) if all_results else "No search results found."

            synthesis_prompt = FAST_SEARCH_SYNTHESIS_PROMPT.format(
                question=query,
                search_results=combined_results[:12000],  # Cap context to avoid token overflow
            )

            yield StreamEvent(content="", phase="synthesizing")

            response = await self._llm.ask(
                messages=[{"role": "user", "content": synthesis_prompt}],
                tools=None,
                tool_choice=None,
            )

            answer = response.get("content", "I was unable to synthesize an answer from the search results.")
            if not isinstance(answer, str):
                answer = str(answer)

            yield MessageEvent(message=answer, role="assistant")

            # 5. Generate follow-up suggestions
            suggestions = self._generate_suggestions(query, answer)
            if suggestions:
                yield SuggestionEvent(suggestions=suggestions, source="fast_search")

            self._status = FastSearchStatus.COMPLETED

        except Exception as e:
            logger.exception("FastSearchFlow error: %s", e)
            self._status = FastSearchStatus.ERROR
            yield ErrorEvent(error=f"Fast search failed: {e}")

        yield DoneEvent()

    def _generate_suggestions(self, query: str, answer: str) -> list[str]:
        """Generate simple follow-up suggestions based on the query."""
        suggestions = []
        query_lower = query.lower()

        if "what" in query_lower or "who" in query_lower:
            suggestions.append(f"Why is {query.split()[-1] if query.split() else 'this'} important?")
        if "how" not in query_lower:
            suggestions.append("How does this work in practice?")
        suggestions.append("Can you go deeper on this topic?")

        return suggestions[:3]
