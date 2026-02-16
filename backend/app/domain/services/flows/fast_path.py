"""Fast-path routing for simple queries that don't need full planning.

This module provides query classification and fast execution paths for:
- Direct browser navigation ("open google.com", "go to X docs")
- Web searches ("search for X")
- Simple knowledge questions ("what is X?")

These queries bypass the full plan-execute-reflect workflow for much faster responses.
"""

import asyncio
import logging
import re
import time
from collections.abc import AsyncGenerator
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote

from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    PlanningPhase,
    ProgressEvent,
    SearchToolContent,
    StreamEvent,
    ToolEvent,
    ToolStatus,
)
from app.domain.models.message import Message
from app.domain.models.search import SearchResultItem

if TYPE_CHECKING:
    from app.domain.external.browser import Browser
    from app.domain.external.llm import LLM
    from app.domain.external.search import SearchEngine

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Classification of user query intent."""

    GREETING = "greeting"  # "hi", "hello", "hey mate", casual greetings
    DIRECT_BROWSE = "direct_browse"  # "open google.com", "go to X"
    WEB_SEARCH = "web_search"  # "search for X on the web"
    KNOWLEDGE = "knowledge"  # "what is X?", factual questions
    TASK = "task"  # Complex multi-step task requiring planning


# Pre-mapped URLs for common targets to avoid URL guessing
URL_KNOWLEDGE_BASE: dict[str, str] = {
    # Claude & Anthropic
    "claude code": "https://docs.anthropic.com/en/docs/claude-code",
    "claude code docs": "https://docs.anthropic.com/en/docs/claude-code",
    "claude code documentation": "https://docs.anthropic.com/en/docs/claude-code",
    "claude docs": "https://docs.anthropic.com",
    "claude documentation": "https://docs.anthropic.com",
    "anthropic docs": "https://docs.anthropic.com",
    "anthropic documentation": "https://docs.anthropic.com",
    "anthropic api": "https://docs.anthropic.com/en/api",
    "claude api": "https://docs.anthropic.com/en/api",
    "claude": "https://claude.ai",
    "anthropic": "https://www.anthropic.com",
    # OpenAI
    "openai": "https://platform.openai.com",
    "openai docs": "https://platform.openai.com/docs",
    "openai api": "https://platform.openai.com/docs/api-reference",
    "chatgpt": "https://chat.openai.com",
    "gpt": "https://platform.openai.com/docs",
    # Google
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "google docs": "https://docs.google.com",
    "google drive": "https://drive.google.com",
    "youtube": "https://www.youtube.com",
    # Development
    "github": "https://github.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "npm": "https://www.npmjs.com",
    "pypi": "https://pypi.org",
    "docker hub": "https://hub.docker.com",
    "docker docs": "https://docs.docker.com",
    # Python
    "python docs": "https://docs.python.org/3/",
    "python documentation": "https://docs.python.org/3/",
    "fastapi docs": "https://fastapi.tiangolo.com",
    "fastapi": "https://fastapi.tiangolo.com",
    "pydantic": "https://docs.pydantic.dev",
    "pydantic docs": "https://docs.pydantic.dev",
    # JavaScript/TypeScript
    "mdn": "https://developer.mozilla.org",
    "mdn docs": "https://developer.mozilla.org",
    "typescript docs": "https://www.typescriptlang.org/docs/",
    "react docs": "https://react.dev",
    "vue docs": "https://vuejs.org/guide/",
    "nextjs docs": "https://nextjs.org/docs",
    # Common sites
    "wikipedia": "https://www.wikipedia.org",
    "reddit": "https://www.reddit.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "linkedin": "https://www.linkedin.com",
    "facebook": "https://www.facebook.com",
    "amazon": "https://www.amazon.com",
    "hacker news": "https://news.ycombinator.com",
    "hn": "https://news.ycombinator.com",
}

# Patterns for greetings and casual conversation
# Using flexible patterns that allow additional words after greeting (e.g., "hey mate", "hi there")
# NOTE: Patterns use [.!?,\s]* to allow punctuation OR whitespace between greeting and follow-up word
# This handles cases like "hi. mate", "hello, friend", "hey! there", "hi mate4" (typos), etc.
# The \w* at the end allows trailing characters (typos like "mate4", "hii", etc.)
GREETING_PATTERNS = [
    # Basic greetings (allow optional words after, with punctuation/whitespace separator)
    # \w* at end allows trailing alphanumeric (typos like "mate4")
    r"^(?:hi+|hello+|hey+|heya|hiya|greetings)[.!?,\s]*(?:there|mate|buddy|pal|man|friend|you|everyone|all)?\w*[.!?,\s]*$",
    # Good morning/afternoon/evening
    r"^(?:good\s+)?(?:morning|afternoon|evening|day)[.!?,\s]*(?:mate|buddy|pal|friend)?\w*[.!?,\s]*$",
    # Casual/slang greetings
    r"^(?:sup|wassup|what'?s\s+up|yo+|howdy)[.!?,\s]*(?:mate|buddy|pal|dude|man)?\w*[.!?,\s]*$",
    # Regional greetings (including Portuguese olá/ola)
    r"^(?:g'?day|hola|ol[aá]|bonjour|namaste|ciao|salut)[.!?,\s]*(?:mate|friend|amigo)?\w*[.!?,\s]*$",
    # How are you variations
    r"^(?:how\s+are\s+you|how'?s\s+it\s+going|how\s+are\s+things)[.!?,\s]*$",
]

# Patterns for acknowledgments (thanks, goodbye, etc.)
# NOTE: Same flexible punctuation/whitespace handling as GREETING_PATTERNS
ACKNOWLEDGMENT_PATTERNS = [
    r"^(?:thanks|thank\s+you|thx|ty|cheers)[.!?,\s]*(?:mate|buddy|pal|so\s+much|a\s+lot)?[.!?,\s]*$",
    r"^(?:bye|goodbye|see\s+you|see\s+ya|later|cya|take\s+care)[.!?,\s]*$",
    r"^(?:ok|okay|got\s+it|understood|alright|sounds\s+good)[.!?,\s]*$",
    r"^(?:yes|yeah|yep|yup|sure|no|nope|nah)[.!?,\s]*$",
    r"^(?:cool|nice|great|awesome|perfect|excellent)[.!?,\s]*$",
]

# Patterns for direct browse intent
DIRECT_BROWSE_PATTERNS = [
    # Explicit navigation commands
    r"^(?:please\s+)?(?:open|go\s+to|browse|visit|navigate\s+to|take\s+me\s+to|show\s+me)\s+(.+?)(?:\s+(?:website|page|site|docs?|documentation))?$",
    # URL in message
    r"(https?://\S+)",
    # Domain-like patterns
    r"^(?:open|go\s+to|browse|visit)\s+(\S+\.\S+)$",
]

# Patterns for web search intent
WEB_SEARCH_PATTERNS = [
    r"^(?:please\s+)?(?:search|google|look\s+up|find)\s+(?:for\s+)?(.+?)(?:\s+(?:on\s+the\s+web|online|on\s+google))?$",
    r"^(?:what\s+are\s+the\s+)?(?:latest|recent|current)\s+(.+)$",
]

# Patterns for knowledge/factual questions (can be answered directly by LLM)
KNOWLEDGE_PATTERNS = [
    r"^(?:what|who|when|where|why|how|which)\s+(?:is|are|was|were|do|does|did|can|could|would|should)\s+",
    r"^(?:explain|define|describe|tell\s+me\s+about)\s+",
    r"^(?:can\s+you\s+)?(?:help\s+me\s+)?(?:understand|explain)\s+",
    r"\?$",  # Ends with question mark (likely a question)
]

# Patterns that indicate a complex task requiring planning
TASK_PATTERNS = [
    # "create/build full/complete X" - strong task indicator (handles typos in target word)
    r"(?:create|build|make|write|generate)\s+(?:a\s+|an\s+|the\s+)?(?:full|complete|detailed|comprehensive)\s+",
    # Creation verbs with article
    r"(?:create|build|make|write|develop|implement|design|set\s+up)\s+(?:a|an|the)\s+",
    # Creation verbs with report-like targets (handles common typos)
    r"(?:create|build|make|write|generate)\s+(?:\w+\s+)*(?:report|assess?ment|analy[sz]is|summary|document|overview)",
    # Fix/debug tasks
    r"(?:fix|debug|solve|resolve|troubleshoot)\s+",
    # Improvement tasks
    r"(?:refactor|optimize|improve|enhance)\s+",
    # Analysis tasks
    r"(?:analyze|analyse|compare|evaluate|review|audit|assess)\s+(?:all\s+)?(?:the\s+)?",
    # Multi-step indicators
    r"(?:step\s+by\s+step|multiple|several|various)",
    r"(?:first|then|after\s+that|finally)",  # Sequential instructions
    # Research/investigation tasks
    r"(?:research|investigate|find\s+out|gather|collect)\s+(?:information|data|details|issues?)\s+",
    # Task keywords (handles typos: assesment, assessement, etc.)
    r"(?:risk\s+)?assess?e?ment",
    r"full\s+(?:report|analy[sz]is|review)",
    # "about all" with action context - indicates research task
    r"(?:about|for|on)\s+all\s+(?:the\s+)?(?:issues?|problems?|bugs?|errors?)",
]

# Suggestion-style follow-up prompts that should use full contextual flow
SUGGESTION_FOLLOW_UP_PATTERNS = [
    r"^can you explain (?:this|that|it|your (?:previous|last) (?:answer|response)) in more detail\??$",
    r"^what are (?:the )?best next steps\??$",
    r"^what should i prioritize as next steps\??$",
    r"^what should i ask next about (?:this|that|it)\??$",
    r"^can you (?:give me|give|provide) (?:a )?practical example(?: for (?:this|that|it))?\??$",
    r"^can you summarize (?:this|that|it|your (?:previous|last) (?:answer|response)) (?:in|into) (?:three|3) key points\??$",
]


class FastPathRouter:
    """Routes simple queries to fast execution paths, bypassing full planning.

    For queries that don't need multi-step planning (like opening a URL or
    answering a simple question), this router provides much faster responses
    by skipping the plan-execute-reflect workflow.
    """

    # Simple search cache for fast path to avoid redundant API calls
    _search_cache: ClassVar[dict[str, tuple[float, Any]]] = {}
    _search_cache_ttl: ClassVar[int] = 3600  # 1 hour, same as SearchTool

    def __init__(
        self,
        browser: "Browser | None" = None,
        llm: "LLM | None" = None,
        search_engine: "SearchEngine | None" = None,
    ):
        """Initialize the fast path router.

        Args:
            browser: Browser instance for direct navigation
            llm: LLM instance for knowledge queries
            search_engine: Search engine for web searches
        """
        self._browser = browser
        self._llm = llm
        self._search_engine = search_engine

    def _get_browser_search_url(self, query: str) -> str:
        """Get a browser-friendly search URL for the given query.

        Uses DuckDuckGo which doesn't block automated browser access.

        Args:
            query: Search query

        Returns:
            Search URL for browser navigation
        """
        return f"https://duckduckgo.com/?q={quote(query)}"

    def classify(self, message: str) -> tuple[QueryIntent, dict[str, Any]]:
        """Classify query intent and extract relevant parameters.

        Args:
            message: User message to classify

        Returns:
            Tuple of (QueryIntent, extracted parameters dict)
        """
        message_clean = message.strip()
        message_lower = message_clean.lower()

        # Check for greetings and acknowledgments FIRST (highest priority)
        # These should always be detected before other patterns
        for pattern in GREETING_PATTERNS:
            if re.match(pattern, message_lower):
                logger.info(f"Query classified as GREETING: {message_clean[:50]}")
                return QueryIntent.GREETING, {"original_message": message_clean}

        for pattern in ACKNOWLEDGMENT_PATTERNS:
            if re.match(pattern, message_lower):
                logger.info(f"Query classified as GREETING (acknowledgment): {message_clean[:50]}")
                return QueryIntent.GREETING, {"original_message": message_clean}

        # Check for explicit task indicators
        for pattern in TASK_PATTERNS:
            if re.search(pattern, message_lower):
                logger.debug("Query classified as TASK (matched task pattern)")
                return QueryIntent.TASK, {}

        # Check for direct browse patterns
        for pattern in DIRECT_BROWSE_PATTERNS:
            match = re.search(pattern, message_clean, re.IGNORECASE)
            if match:
                target = match.group(1).strip()
                # Remove trailing punctuation
                target = re.sub(r"[.!?]+$", "", target)
                logger.info(f"Query classified as DIRECT_BROWSE: target='{target}'")
                return QueryIntent.DIRECT_BROWSE, {"target": target}

        # Check for web search patterns
        for pattern in WEB_SEARCH_PATTERNS:
            match = re.search(pattern, message_clean, re.IGNORECASE)
            if match:
                query = match.group(1).strip()
                logger.info(f"Query classified as WEB_SEARCH: query='{query}'")
                return QueryIntent.WEB_SEARCH, {"query": query}

        # Check for knowledge questions (simple enough for direct LLM response)
        # But only if it's short enough (long questions may need research)
        word_count = len(message_clean.split())
        if word_count < 35:
            for pattern in KNOWLEDGE_PATTERNS:
                if re.search(pattern, message_lower):
                    logger.info("Query classified as KNOWLEDGE")
                    return QueryIntent.KNOWLEDGE, {"question": message_clean}

        # Default to TASK for anything else
        logger.debug("Query classified as TASK (default)")
        return QueryIntent.TASK, {}

    def resolve_target_to_url(self, target: str) -> str:
        """Resolve a target description to a URL.

        Uses the knowledge base for known targets, falls back to search
        or direct URL construction.

        Args:
            target: Target description (e.g., "claude code docs", "google.com")

        Returns:
            Resolved URL string
        """
        target_lower = target.lower().strip()

        # Check knowledge base first
        if target_lower in URL_KNOWLEDGE_BASE:
            url = URL_KNOWLEDGE_BASE[target_lower]
            logger.info(f"Resolved '{target}' to known URL: {url}")
            return url

        # Check if it's already a URL
        if target.startswith("http://") or target.startswith("https://"):
            return target

        # Check if it looks like a domain (contains a dot)
        if "." in target and " " not in target:
            # Assume it's a domain
            url = f"https://{target}"
            logger.info(f"Resolved '{target}' as domain: {url}")
            return url

        # Check partial matches in knowledge base
        for key, url in URL_KNOWLEDGE_BASE.items():
            if target_lower in key or key in target_lower:
                logger.info(f"Resolved '{target}' via partial match to: {url}")
                return url

        # Fall back to search for the target (use DuckDuckGo, not Google)
        search_url = self._get_browser_search_url(target)
        logger.info(f"Resolved '{target}' to search URL: {search_url}")
        return search_url

    async def execute_fast_browse(
        self,
        target: str,
        message: Message | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute direct browser navigation without planning.

        Args:
            target: Target to navigate to (URL or description)
            message: Original message (optional, for context)

        Yields:
            Events for progress, content, and completion
        """
        import uuid

        if not self._browser:
            yield ErrorEvent(error="Browser not available for fast browse")
            yield DoneEvent()
            return

        # Check if browser is healthy and ready before proceeding
        try:
            # Check browser health
            if hasattr(self._browser, "is_healthy") and not self._browser.is_healthy():
                logger.warning("Browser not healthy, fast browse unavailable")
                yield ErrorEvent(error="Browser not ready - please try again")
                yield DoneEvent()
                return

            # Try to ensure browser is connected - this will initialize if needed
            if hasattr(self._browser, "_ensure_browser"):
                await asyncio.wait_for(self._browser._ensure_browser(), timeout=15.0)
        except TimeoutError:
            logger.warning("Browser initialization timed out for fast browse")
            yield ErrorEvent(error="Browser not ready (timeout) - please try again")
            yield DoneEvent()
            return
        except Exception as e:
            logger.warning(f"Browser initialization failed: {e}")
            yield ErrorEvent(error="Browser not ready - please try again")
            yield DoneEvent()
            return

        url = self.resolve_target_to_url(target)
        tool_call_id = f"fast_browse_{uuid.uuid4().hex[:8]}"

        # Emit ToolEvent CALLING to trigger live preview in frontend
        yield ToolEvent(
            status=ToolStatus.CALLING,
            tool_call_id=tool_call_id,
            tool_name="browser",
            function_name="browser_navigate",
            function_args={"url": url},
        )

        # Small delay to allow frontend to establish preview connection and render
        await asyncio.sleep(0.3)

        # Emit progress
        yield ProgressEvent(
            phase=PlanningPhase.RECEIVED,
            message=f"Navigating to {url}...",
            progress_percent=20,
        )

        try:
            # Use fast navigation mode (with 30s overall timeout to prevent hanging)
            if hasattr(self._browser, "navigate_fast"):
                result = await asyncio.wait_for(self._browser.navigate_fast(url), timeout=30.0)
            else:
                # Fallback to regular navigate with minimal options
                result = await asyncio.wait_for(
                    self._browser.navigate(url, timeout=15000, auto_extract=True), timeout=30.0
                )

            if result.success:
                yield ProgressEvent(
                    phase=PlanningPhase.FINALIZING,
                    message="Page loaded successfully",
                    progress_percent=80,
                )

                # Emit ToolEvent CALLED to complete the tool call
                data = result.data or {}
                title = data.get("title", "Page")

                yield ToolEvent(
                    status=ToolStatus.CALLED,
                    tool_call_id=tool_call_id,
                    tool_name="browser",
                    function_name="browser_navigate",
                    function_args={"url": url},
                    function_result={"success": True, "title": title, "url": url},
                )

                yield MessageEvent(
                    message=f"Opened **{title}** in the browser. You can view and interact with the page."
                )
            else:
                # Emit ToolEvent CALLED with error
                yield ToolEvent(
                    status=ToolStatus.CALLED,
                    tool_call_id=tool_call_id,
                    tool_name="browser",
                    function_name="browser_navigate",
                    function_args={"url": url},
                    function_result={"success": False, "error": result.message},
                )
                yield ErrorEvent(error=f"Failed to navigate: {result.message}")

        except TimeoutError:
            logger.warning(f"Fast browse timed out for {url}")
            yield ToolEvent(
                status=ToolStatus.CALLED,
                tool_call_id=tool_call_id,
                tool_name="browser",
                function_name="browser_navigate",
                function_args={"url": url},
                function_result={"success": False, "error": "Navigation timed out"},
            )
            yield ErrorEvent(error=f"Browser navigation to {url} timed out")
        except Exception as e:
            logger.exception(f"Fast browse error: {e}")
            # Emit ToolEvent CALLED with error
            yield ToolEvent(
                status=ToolStatus.CALLED,
                tool_call_id=tool_call_id,
                tool_name="browser",
                function_name="browser_navigate",
                function_args={"url": url},
                function_result={"success": False, "error": str(e)},
            )
            yield ErrorEvent(error=f"Browser navigation failed: {e!s}")

        yield DoneEvent()

    async def execute_fast_search(
        self,
        query: str,
        message: Message | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute web search without planning.

        Uses search API directly for instant results, emitting ToolEvents
        so the frontend can display structured search results.

        Args:
            query: Search query
            message: Original message (optional)

        Yields:
            Events for progress, results, and completion
        """
        import uuid

        tool_call_id = f"fast_search_{uuid.uuid4().hex[:8]}"

        # Emit ToolEvent CALLING before search
        yield ToolEvent(
            status=ToolStatus.CALLING,
            tool_call_id=tool_call_id,
            tool_name="search",
            function_name="info_search_web",
            function_args={"query": query},
        )

        yield ProgressEvent(
            phase=PlanningPhase.RECEIVED,
            message=f"Searching for: {query}...",
            progress_percent=20,
        )

        try:
            # Prefer API search (faster, more reliable) over browser search
            # Browser content extraction has reliability issues
            if self._search_engine:
                # Check fast-path search cache
                cache_key = query.lower().strip()
                cached = self._search_cache.get(cache_key)
                if cached and (time.time() - cached[0]) < self._search_cache_ttl:
                    search_result = cached[1]
                else:
                    # Use search engine API directly (faster but invisible)
                    search_result = await self._search_engine.search(query)
                    if search_result.success:
                        self._search_cache[cache_key] = (time.time(), search_result)

                yield ProgressEvent(
                    phase=PlanningPhase.FINALIZING,
                    message="Search complete",
                    progress_percent=80,
                )

                if search_result.success and search_result.data and search_result.data.results:
                    # Normalize results to consistent format (limit to 5)
                    results_list: list[SearchResultItem] = [
                        SearchResultItem(
                            title=result.title or "No title",
                            link=result.link or "",
                            snippet=result.snippet or "",
                        )
                        for result in search_result.data.results[:5]
                    ]

                    # Emit ToolEvent CALLED with structured results for frontend
                    yield ToolEvent(
                        status=ToolStatus.CALLED,
                        tool_call_id=tool_call_id,
                        tool_name="search",
                        function_name="info_search_web",
                        function_args={"query": query},
                        function_result={"success": True, "results": [r.model_dump() for r in results_list]},
                        tool_content=SearchToolContent(results=results_list),
                    )

                    # Also emit a MessageEvent for chat history display
                    response_parts = [f"**Search results for:** {query}\n"]
                    for i, result in enumerate(results_list, 1):
                        response_parts.append(f"\n{i}. **{result.title}**")
                        if result.link:
                            response_parts.append(f"   {result.link}")
                        if result.snippet:
                            response_parts.append(f"   {result.snippet[:200]}...")

                    yield MessageEvent(message="\n".join(response_parts))
                else:
                    # Emit ToolEvent CALLED with empty results
                    yield ToolEvent(
                        status=ToolStatus.CALLED,
                        tool_call_id=tool_call_id,
                        tool_name="search",
                        function_name="info_search_web",
                        function_args={"query": query},
                        function_result={"success": True, "results": []},
                    )
                    yield MessageEvent(message=f"No results found for: {query}")

            elif self._browser:
                # Emit ToolEvent CALLED to close the calling state before fallback
                yield ToolEvent(
                    status=ToolStatus.CALLED,
                    tool_call_id=tool_call_id,
                    tool_name="search",
                    function_name="info_search_web",
                    function_args={"query": query},
                    function_result={"success": False, "error": "Falling back to browser search"},
                )
                # Fall back to browser-based search
                search_url = self._get_browser_search_url(query)
                async for event in self.execute_fast_browse(search_url):
                    yield event
                return

            else:
                # Emit ToolEvent CALLED with error
                yield ToolEvent(
                    status=ToolStatus.CALLED,
                    tool_call_id=tool_call_id,
                    tool_name="search",
                    function_name="info_search_web",
                    function_args={"query": query},
                    function_result={"success": False, "error": "No search engine or browser available"},
                )
                yield ErrorEvent(error="No search engine or browser available")

        except Exception as e:
            logger.exception(f"Fast search error: {e}")
            # Emit ToolEvent CALLED with error
            yield ToolEvent(
                status=ToolStatus.CALLED,
                tool_call_id=tool_call_id,
                tool_name="search",
                function_name="info_search_web",
                function_args={"query": query},
                function_result={"success": False, "error": str(e)},
            )
            yield ErrorEvent(error=f"Search failed: {e!s}")

        yield DoneEvent()

    async def execute_fast_knowledge(
        self,
        question: str,
        message: Message | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Answer a simple knowledge question directly with LLM.

        Args:
            question: The question to answer
            message: Original message (optional)

        Yields:
            Events for progress, answer, and completion
        """
        if not self._llm:
            yield ErrorEvent(error="LLM not available for knowledge query")
            yield DoneEvent()
            return

        yield ProgressEvent(
            phase=PlanningPhase.RECEIVED,
            message="Processing your question...",
            progress_percent=20,
        )

        try:
            # Direct LLM call for simple questions
            messages = [
                {
                    "role": "system",
                    "content": "You are Pythinker, an AI assistant created by the Pythinker Team and Mohamed Elkholy. "
                    "You are NOT Claude. You are NOT made by Anthropic. "
                    "Answer the following question concisely and accurately. "
                    "If you're not certain about something, say so. Keep your response focused and under 500 words.",
                },
                {"role": "user", "content": question},
            ]

            # Try streaming if available
            if hasattr(self._llm, "ask_stream"):
                yield ProgressEvent(
                    phase=PlanningPhase.PLANNING,
                    message="Generating response...",
                    progress_percent=40,
                )

                full_response = ""
                async for chunk in self._llm.ask_stream(messages):
                    full_response += chunk
                    yield StreamEvent(content=chunk, is_final=False)

                yield StreamEvent(content="", is_final=True)
                yield MessageEvent(message=full_response)
            else:
                # Non-streaming fallback
                response = await self._llm.ask(messages)
                content = response.get("content", "")
                yield MessageEvent(message=content)

        except Exception as e:
            logger.exception(f"Fast knowledge error: {e}")
            yield ErrorEvent(error=f"Failed to answer question: {e!s}")

        yield DoneEvent()

    async def execute_fast_greeting(
        self,
        original_message: str,
        message: Message | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Respond to a greeting with a friendly, contextual message.

        Args:
            original_message: The original greeting message
            message: Original message object (optional)

        Yields:
            Events for progress, greeting response, and completion
        """
        if not self._llm:
            yield ErrorEvent(error="LLM not available for greeting")
            yield DoneEvent()
            return

        yield ProgressEvent(
            phase=PlanningPhase.RECEIVED,
            message="Responding to your greeting...",
            progress_percent=50,
        )

        try:
            # Direct LLM call for greeting response
            messages = [
                {
                    "role": "system",
                    "content": "You are Pythinker, a helpful AI assistant. The user has greeted you. "
                    "Respond with a warm, friendly greeting. Keep it natural and conversational (1-2 sentences). "
                    "You can ask how you can help them today.",
                },
                {"role": "user", "content": original_message},
            ]

            # Try streaming if available
            if hasattr(self._llm, "ask_stream"):
                full_response = ""
                async for chunk in self._llm.ask_stream(messages):
                    full_response += chunk
                    yield StreamEvent(content=chunk, is_final=False)

                yield StreamEvent(content="", is_final=True)
                yield MessageEvent(message=full_response)
            else:
                # Non-streaming fallback
                response = await self._llm.ask(messages)
                content = response.get("content", "")
                yield MessageEvent(message=content)

        except Exception as e:
            logger.exception(f"Fast greeting error: {e}")
            yield ErrorEvent(error=f"Failed to respond to greeting: {e!s}")

        yield DoneEvent()

    async def execute(
        self,
        intent: QueryIntent,
        params: dict[str, Any],
        message: Message | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute the appropriate fast path based on intent.

        Args:
            intent: Classified query intent
            params: Extracted parameters from classification
            message: Original message

        Yields:
            Events from the appropriate fast path execution
        """
        if intent == QueryIntent.GREETING:
            async for event in self.execute_fast_greeting(params.get("original_message", ""), message):
                yield event

        elif intent == QueryIntent.DIRECT_BROWSE:
            async for event in self.execute_fast_browse(params.get("target", ""), message):
                yield event

        elif intent == QueryIntent.WEB_SEARCH:
            async for event in self.execute_fast_search(params.get("query", ""), message):
                yield event

        elif intent == QueryIntent.KNOWLEDGE:
            async for event in self.execute_fast_knowledge(params.get("question", ""), message):
                yield event

        else:
            # TASK intent should not reach here
            yield ErrorEvent(error="Task queries should use full workflow")
            yield DoneEvent()


# Module-level singleton for classify-only checks (no browser/llm/search needed)
_classify_router: FastPathRouter | None = None


def is_suggestion_follow_up_message(message: str) -> bool:
    """Return True when a message matches known follow-up suggestion phrasing."""
    if not message or not message.strip():
        return False

    normalized = re.sub(r"\s+", " ", message.strip().lower())
    return any(re.match(pattern, normalized) for pattern in SUGGESTION_FOLLOW_UP_PATTERNS)


def should_use_fast_path(message: str, follow_up_source: str | None = None) -> bool:
    """Return True when a message should be handled by the fast path.

    Args:
        message: The message text to classify
        follow_up_source: Optional metadata indicating follow-up source (e.g., 'suggestion_click')

    Returns:
        False if message should bypass fast path (use full contextual flow)
        True if message can use fast path
    """
    global _classify_router
    if not message or not message.strip():
        return False

    # Primary detection: Check metadata for suggestion-click follow-ups
    if follow_up_source == "suggestion_click":
        return False

    # Fallback detection: Check regex patterns for backwards compatibility
    if is_suggestion_follow_up_message(message):
        return False

    if _classify_router is None:
        _classify_router = FastPathRouter()
    intent, _ = _classify_router.classify(message)
    return intent != QueryIntent.TASK


def get_fast_path_router(
    browser: "Browser | None" = None,
    llm: "LLM | None" = None,
    search_engine: "SearchEngine | None" = None,
) -> FastPathRouter:
    """Factory function to create a FastPathRouter instance.

    Args:
        browser: Browser instance for navigation
        llm: LLM instance for knowledge queries
        search_engine: Search engine for web searches

    Returns:
        Configured FastPathRouter instance
    """
    return FastPathRouter(browser=browser, llm=llm, search_engine=search_engine)
