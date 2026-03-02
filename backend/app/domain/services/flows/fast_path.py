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
import socket
import time
from collections.abc import AsyncGenerator
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote, urlparse

from app.domain.exceptions.base import LLMKeysExhaustedError
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


SEARCH_RESULT_DOMAIN_BLOCKLIST = {
    "duckduckgo.com",
    "google.com",
    "bing.com",
    "search.brave.com",
}


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

# Queries matching KNOWLEDGE_PATTERNS but containing these indicators should
# be escalated to the full workflow (WEB_SEARCH / TASK) because they require
# up-to-date, cited, or multi-faceted information the LLM alone cannot provide.
KNOWLEDGE_ESCALATION_PATTERNS = [
    # Health, medical, supplement, drug topics — need authoritative/cited info
    r"\b(?:side\s+effects?|dosage|supplement|medication|drug|symptoms?|treatment|diagnosis|health\s+(?:benefits?|risks?))\b",
    r"\b(?:body|blood\s+pressure|cholesterol|heart|liver|kidney|brain|hormone|cortisol|testosterone)\b",
    # Comparison / multi-faceted analysis — need structured research
    r"\b(?:pros?\s+and\s+cons?|advantages?\s+and\s+disadvantages?|benefits?\s+and\s+(?:risks?|drawbacks?|downsides?))\b",
    r"\b(?:compare|comparison|versus|vs\.?)\b",
    # Current events, prices, stats — LLM training data is stale
    r"\b(?:price|cost|stock|worth|salary|latest|current|today|this\s+(?:year|month|week))\b",
    # Legal, financial advice — need authoritative sources
    r"\b(?:legal|illegal|lawsuit|tax|regulation|compliance)\b",
    # Safety and warnings
    r"\b(?:safe(?:ty)?|unsafe|danger(?:ous)?|warnings?|risks?|toxic(?:ity)?|poisonous|overdose)\b",
]

# Patterns for explicit short-response directives.
# These are simple conversational formatting requests that should not trigger
# full planning/report workflows (e.g. "Reply with a short sentence.").
SIMPLE_RESPONSE_PATTERNS = [
    r"^(?:please\s+)?(?:reply|respond|answer|say)\s+(?:with\s+)?(?:a\s+)?(?:short|brief|concise|single|one)\s+(?:sentence|reply|response)\b",
    r"^(?:please\s+)?(?:reply|respond|answer)\s+(?:in\s+)?(?:one|1|a\s+single)\s+sentence\b",
    r"^(?:please\s+)?write\s+(?:a\s+)?(?:short|brief|concise|single|one)\s+(?:sentence|reply|response)\b",
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
        memory_context: str | None = None,
    ):
        """Initialize the fast path router.

        Args:
            browser: Browser instance for direct navigation
            llm: LLM instance for knowledge queries
            search_engine: Search engine for web searches
            memory_context: Optional user preference/fact context from long-term memory
        """
        self._browser = browser
        self._llm = llm
        self._search_engine = search_engine
        self._memory_context = memory_context

    def _get_browser_search_url(self, query: str) -> str:
        """Get a browser-friendly search URL for the given query.

        Uses DuckDuckGo which doesn't block automated browser access.

        Args:
            query: Search query

        Returns:
            Search URL for browser navigation
        """
        return f"https://duckduckgo.com/?q={quote(query)}"

    @staticmethod
    def _normalize_target_text(value: str) -> str:
        """Normalize free-form target text for token matching."""
        return re.sub(r"[^a-z0-9]+", " ", value.lower().strip()).strip()

    @staticmethod
    def _extract_site_hint(normalized_target: str) -> str | None:
        """Extract likely site token from phrases like 'from <site>'."""
        match = re.search(r"\bfrom\s+([a-z0-9][a-z0-9.-]{2,})\b", normalized_target)
        if not match:
            return None
        site_hint = match.group(1).strip(".")
        if site_hint in {"the", "this", "that", "here", "there"}:
            return None
        return site_hint

    @staticmethod
    def _normalize_domain(value: str) -> str:
        """Return lowercase bare domain (without leading www)."""
        domain = value.lower().strip()
        if domain.startswith("www."):
            return domain[4:]
        return domain

    @classmethod
    def _is_blocklisted_search_domain(cls, domain: str) -> bool:
        """Return True when domain belongs to a search engine results page."""
        normalized = cls._normalize_domain(domain)
        return any(
            normalized == blocked or normalized.endswith(f".{blocked}") for blocked in SEARCH_RESULT_DOMAIN_BLOCKLIST
        )

    @classmethod
    def _normalize_candidate_url(cls, link: str) -> tuple[str, str] | None:
        """Normalize candidate link and return (url, domain) if valid."""
        raw = (link or "").strip()
        if not raw:
            return None
        if not raw.startswith(("http://", "https://")):
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        domain = cls._normalize_domain(parsed.netloc)
        if cls._is_blocklisted_search_domain(domain):
            return None
        return raw, domain

    @staticmethod
    def _domain_matches_site_hint(domain: str, site_hint: str) -> bool:
        """Check whether result domain aligns with inferred site hint token."""
        hint_normalized = re.sub(r"[^a-z0-9]", "", site_hint.lower())
        domain_normalized = re.sub(r"[^a-z0-9]", "", domain.lower())
        return bool(hint_normalized and hint_normalized in domain_normalized)

    def _build_website_search_query(self, target: str) -> str:
        """Build a focused query for website discovery."""
        normalized_target = self._normalize_target_text(target)
        site_hint = self._extract_site_hint(normalized_target)
        if site_hint:
            return f"{site_hint} official website"
        return normalized_target or target

    def _select_best_website_result_url(self, target: str, search_result: Any) -> str | None:
        """Select a high-confidence website URL from search API results."""
        if (
            not search_result
            or not getattr(search_result, "success", False)
            or not getattr(search_result, "data", None)
            or not getattr(search_result.data, "results", None)
        ):
            return None

        normalized_target = self._normalize_target_text(target)
        site_hint = self._extract_site_hint(normalized_target)
        candidates: list[tuple[str, str]] = []
        for result in search_result.data.results:
            normalized = self._normalize_candidate_url(getattr(result, "link", ""))
            if normalized:
                candidates.append(normalized)

        if not candidates:
            return None

        if site_hint:
            for candidate_url, candidate_domain in candidates:
                if self._domain_matches_site_hint(candidate_domain, site_hint):
                    return candidate_url
            return None

        return candidates[0][0]

    async def _resolve_target_to_url_with_search(self, target: str) -> str | None:
        """Try resolving a browse target to a concrete site URL via search API."""
        if not self._search_engine:
            return None

        search_query = self._build_website_search_query(target)
        if not search_query.strip():
            return None

        try:
            cache_key = f"browse_target::{search_query.lower().strip()}"
            cached = self._search_cache.get(cache_key)
            if cached and (time.time() - cached[0]) < self._search_cache_ttl:
                search_result = cached[1]
            else:
                search_result = await self._search_engine.search(search_query)
                if getattr(search_result, "success", False):
                    self._search_cache[cache_key] = (time.time(), search_result)

            selected_url = self._select_best_website_result_url(target, search_result)
            if selected_url:
                logger.info(
                    "Resolved '%s' via search API query '%s' to website URL: %s",
                    target,
                    search_query,
                    selected_url,
                )
                return selected_url
        except Exception as exc:
            logger.warning("Search-assisted website resolution failed for '%s': %s", target, exc)

        return None

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

        # Check for explicit short-response directives before TASK matching.
        # This avoids over-routing simple conversational requests into the full
        # planning/report pipeline.
        for pattern in SIMPLE_RESPONSE_PATTERNS:
            if re.search(pattern, message_lower):
                logger.info("Query classified as KNOWLEDGE (simple response directive)")
                return QueryIntent.KNOWLEDGE, {"question": message_clean}

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
                    # Escalation check 1: topic-based (health, safety, legal, etc.)
                    for esc_pattern in KNOWLEDGE_ESCALATION_PATTERNS:
                        if re.search(esc_pattern, message_lower):
                            logger.info(
                                "Query matched KNOWLEDGE but escalated to TASK (escalation pattern: %s)",
                                esc_pattern,
                            )
                            return QueryIntent.TASK, {}

                    # Escalation check 2: multi-sub-question queries.
                    # Queries with 3+ conjunctions ("and") or multiple question
                    # aspects signal a compound question that benefits from
                    # structured research (e.g., "X and pros and cons and side effects").
                    conjunction_count = len(re.findall(r"\band\b", message_lower))
                    if conjunction_count >= 3:
                        logger.info(
                            "Query matched KNOWLEDGE but escalated to TASK (multi-sub-question: %d conjunctions)",
                            conjunction_count,
                        )
                        return QueryIntent.TASK, {}

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

        # Check conservative partial matches in knowledge base.
        # Single-character aliases (e.g., "x") must only match standalone tokens,
        # otherwise normal words like "extract" can be misrouted to x.com.
        normalized_target = self._normalize_target_text(target_lower)
        target_tokens = normalized_target.split()
        normalized_target_with_padding = f" {normalized_target} "

        for key, url in URL_KNOWLEDGE_BASE.items():
            normalized_key = re.sub(r"[^a-z0-9]+", " ", key.lower().strip()).strip()
            if not normalized_key:
                continue

            if len(normalized_key) <= 2:
                if normalized_key in target_tokens:
                    logger.info(f"Resolved '{target}' via token alias match ('{key}') to: {url}")
                    return url
                continue

            if f" {normalized_key} " in normalized_target_with_padding:
                logger.info(f"Resolved '{target}' via partial phrase match ('{key}') to: {url}")
                return url

        # Heuristic: "from <site> website" style prompts often include task words
        # around a bare site token; infer a direct domain to preserve live browse UX.
        fallback_query = target
        site_hint = self._extract_site_hint(normalized_target)
        if site_hint:
            inferred_host = site_hint if "." in site_hint else f"{site_hint}.com"
            try:
                socket.getaddrinfo(inferred_host, 443, type=socket.SOCK_STREAM)
            except socket.gaierror:
                logger.info(
                    "Site hint '%s' did not resolve via DNS for target '%s'; falling back to search",
                    inferred_host,
                    target,
                )
                fallback_query = site_hint
            else:
                inferred_url = f"https://{inferred_host}"
                logger.info(f"Resolved '{target}' via site hint inference to: {inferred_url}")
                return inferred_url

        # Fall back to search for the target (use DuckDuckGo, not Google)
        search_url = self._get_browser_search_url(fallback_query)
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

        # Ensure browser is initialized before navigation.
        # Fast-path browse is often the first browser action in a session, so
        # initial "unhealthy" state should trigger warm-up, not immediate failure.
        ensure_browser = getattr(self._browser, "_ensure_browser", None)
        timeout_errors = (TimeoutError, asyncio.TimeoutError)
        max_init_attempts = 2
        init_timeout_seconds = 20.0
        init_error: Exception | None = None

        for attempt in range(max_init_attempts):
            try:
                if callable(ensure_browser):
                    await asyncio.wait_for(ensure_browser(), timeout=init_timeout_seconds)

                if hasattr(self._browser, "is_healthy") and not self._browser.is_healthy():
                    raise RuntimeError("Browser health check failed after initialization")

                init_error = None
                break
            except timeout_errors as exc:
                init_error = exc
                logger.warning(
                    "Browser initialization timed out for fast browse (%s/%s)",
                    attempt + 1,
                    max_init_attempts,
                )
            except Exception as exc:
                init_error = exc
                logger.warning(
                    "Browser initialization failed for fast browse (%s/%s): %s",
                    attempt + 1,
                    max_init_attempts,
                    exc,
                )

            if attempt < max_init_attempts - 1:
                await asyncio.sleep(0.75)

        if init_error is not None:
            if isinstance(init_error, timeout_errors):
                yield ErrorEvent(error="Browser not ready (timeout) - please try again")
            else:
                yield ErrorEvent(error="Browser not ready - please try again")
            yield DoneEvent()
            return

        # Prefer search-assisted website resolution for ambiguous natural-language targets.
        target_lower = target.lower().strip()
        is_explicit_target = (
            target.startswith("http://")
            or target.startswith("https://")
            or ("." in target and " " not in target)
            or target_lower in URL_KNOWLEDGE_BASE
        )

        resolved_from_search = False
        url: str
        if is_explicit_target:
            url = self.resolve_target_to_url(target)
        else:
            search_resolved_url = await self._resolve_target_to_url_with_search(target)
            if search_resolved_url:
                url = search_resolved_url
                resolved_from_search = True
            else:
                url = self.resolve_target_to_url(target)

        if resolved_from_search:
            logger.info("Fast browse using search-identified website URL: %s", url)
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
                    # Normalize results to consistent format (limit to 20 for panel display)
                    results_list: list[SearchResultItem] = [
                        SearchResultItem(
                            title=result.title or "No title",
                            link=result.link or "",
                            snippet=result.snippet or "",
                        )
                        for result in search_result.data.results[:20]
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
            from app.domain.services.prompts.system import get_current_datetime_signal

            system_content = (
                "You are Pythinker, an AI assistant created by the Pythinker Team and Mohamed Elkholy. "
                "You are NOT Claude. You are NOT made by Anthropic. "
                "Answer the following question concisely and accurately. "
                "If you're not certain about something, say so. Keep your response focused and under 500 words.\n\n"
                "Formatting rules:\n"
                "- Use consistent formatting throughout: if you use a table for one section, use tables for all comparable sections. "
                "If you use bullet points, use bullet points throughout.\n"
                "- Never mix tables and bullet points for parallel content (e.g., pros vs cons should both be the same format).\n"
                "- Prefer bullet points for short lists; prefer tables when comparing attributes side by side."
            )
            system_content += "\n" + get_current_datetime_signal()
            if self._memory_context:
                system_content += f"\n\nUser context:\n{self._memory_context}"
            messages = [
                {"role": "system", "content": system_content},
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
            if isinstance(e, LLMKeysExhaustedError):
                logger.debug("Fast knowledge skipped: %s", e)
                yield ErrorEvent(error="API quota temporarily exceeded. Please try again in a moment.")
            else:
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
            from app.domain.services.prompts.system import get_current_datetime_signal

            system_content = (
                "You are Pythinker, a helpful AI assistant. The user has greeted you. "
                "Respond with a warm, friendly greeting. Keep it natural and conversational (1-2 sentences). "
                "You can ask how you can help them today."
            )
            system_content += "\n" + get_current_datetime_signal()
            if self._memory_context:
                system_content += f"\n\nUser context (use to personalize):\n{self._memory_context}"
            messages = [
                {"role": "system", "content": system_content},
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
    return intent in (QueryIntent.GREETING, QueryIntent.KNOWLEDGE)


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
