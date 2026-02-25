"""Dynamic Toolset Management

Provides intelligent tool filtering and semantic search to reduce token usage
by providing only relevant tools to the LLM based on task context.

Key Features:
- Category-based tool organization
- Semantic similarity matching for tool discovery
- Task-based tool filtering (up to 96% token reduction)
- Usage-based tool prioritization
- Compiled regex patterns for fast matching (Phase 4 optimization)
"""

import asyncio
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


class ToolCategory(str, Enum):
    """Categories for tool organization."""

    FILE = "file"  # File operations (read, write, list)
    BROWSER = "browser"  # Web browsing and scraping
    SEARCH = "search"  # Web search and information retrieval
    SHELL = "shell"  # Command execution
    MESSAGE = "message"  # User communication
    MCP = "mcp"  # MCP server tools
    CODE = "code"  # Code execution and analysis
    PLAN = "plan"  # Planning and orchestration
    SYSTEM = "system"  # System utilities


# Task type patterns for automatic detection
TASK_PATTERNS = {
    "research": [
        r"research",
        r"find",
        r"search",
        r"investigate",
        r"look up",
        r"information about",
        r"what is",
        r"who is",
        r"how to",
    ],
    "coding": [
        r"code",
        r"program",
        r"implement",
        r"function",
        r"class",
        r"debug",
        r"fix",
        r"refactor",
        r"optimize",
        r"test",
    ],
    "file_management": [r"file", r"read", r"write", r"create", r"delete", r"move", r"copy", r"directory", r"folder"],
    "web_browsing": [r"browse", r"navigate", r"website", r"page", r"click", r"form", r"screenshot", r"scrape"],
    "analysis": [
        r"analyze",
        r"compare",
        r"evaluate",
        r"assess",
        r"review",
        r"summarize",
        r"report",
        r"chart",
        r"graph",
        r"visualize",
        r"plot",
    ],
    "communication": [r"ask", r"tell", r"notify", r"message", r"clarify"],
}

# Mapping of task types to relevant tool categories
TASK_TO_CATEGORIES = {
    "research": [ToolCategory.SEARCH, ToolCategory.BROWSER, ToolCategory.FILE],
    "coding": [ToolCategory.FILE, ToolCategory.SHELL, ToolCategory.CODE],
    "file_management": [ToolCategory.FILE, ToolCategory.SHELL],
    "web_browsing": [ToolCategory.BROWSER, ToolCategory.SEARCH],
    "analysis": [ToolCategory.FILE, ToolCategory.SEARCH, ToolCategory.CODE],
    # Note: "visualization" mapping removed - no corresponding TASK_PATTERNS key exists
    # Visualization keywords are handled under "analysis" pattern
    "communication": [ToolCategory.MESSAGE],
}

# Tool name patterns for category detection
TOOL_CATEGORY_PATTERNS = {
    ToolCategory.FILE: [r"file_", r"directory", r"read", r"write"],
    ToolCategory.BROWSER: [r"browser_", r"page_", r"navigate", r"screenshot"],
    ToolCategory.SEARCH: [r"search", r"info_search", r"web_search"],
    ToolCategory.SHELL: [r"shell_", r"execute", r"command"],
    ToolCategory.MESSAGE: [r"message_", r"ask_", r"notify"],
    ToolCategory.MCP: [r"mcp_"],
    ToolCategory.CODE: [r"code_", r"execute_", r"run_", r"chart_"],
    ToolCategory.PLAN: [r"plan_", r"step_"],
}


# Pre-compiled regex patterns for performance (Phase 4 optimization)
# Avoids recompiling patterns on every task classification call
_get_compiled_task_patterns_init_lock = threading.Lock()


@lru_cache(maxsize=1)
def _get_compiled_task_patterns() -> dict[str, list[re.Pattern[str]]]:
    """Get compiled regex patterns for task type detection."""
    with _get_compiled_task_patterns_init_lock:
        return {
            task_type: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for task_type, patterns in TASK_PATTERNS.items()
        }


_get_compiled_category_patterns_init_lock = threading.Lock()


@lru_cache(maxsize=1)
def _get_compiled_category_patterns() -> dict[ToolCategory, list[re.Pattern[str]]]:
    """Get compiled regex patterns for tool category detection."""
    with _get_compiled_category_patterns_init_lock:
        return {
            category: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for category, patterns in TOOL_CATEGORY_PATTERNS.items()
        }


@dataclass
class ToolInfo:
    """Information about a tool for filtering and ranking."""

    name: str
    description: str
    category: ToolCategory
    schema: dict[str, Any]
    keywords: set[str] = field(default_factory=set)
    usage_count: int = 0
    last_used: datetime | None = None
    average_duration_ms: float = 0


@dataclass
class ToolsetConfig:
    """Configuration for dynamic toolset management."""

    enabled: bool = True
    max_tools_per_request: int = 20  # Maximum tools to include
    always_include: set[str] = field(
        default_factory=lambda: {
            "message_ask_user",  # Always need user communication
            "file_read",  # Common operation
            "file_write",  # Common operation
        }
    )
    keyword_similarity_threshold: float = 0.3
    boost_recent_tools: bool = True
    boost_successful_tools: bool = True
    enable_task_type_cache: bool = True  # Cache tools by task type
    cache_ttl_seconds: int = 300  # 5 minute cache TTL


class DynamicToolsetManager:
    """Manages dynamic tool filtering based on task context.

    Reduces token usage by providing only relevant tools to the LLM,
    achieving up to 96% token reduction in tool definitions.

    Usage:
        manager = DynamicToolsetManager(all_tools)
        relevant_tools = manager.get_tools_for_task(
            "Research the best keyboards for Mac"
        )
    """

    def __init__(self, config: ToolsetConfig | None = None):
        """Initialize the toolset manager.

        Args:
            config: Optional configuration settings
        """
        self.config = config or ToolsetConfig()
        self._tools: dict[str, ToolInfo] = {}
        self._category_index: dict[ToolCategory, list[str]] = {cat: [] for cat in ToolCategory}
        self._keyword_index: dict[str, set[str]] = {}  # keyword -> tool names

        # Task-type based tool cache for prefetching
        self._task_type_cache: dict[str, tuple[list[dict[str, Any]], datetime]] = {}
        self._prefetch_in_progress: dict[str, bool] = {}

    def register_tools(self, tools: list[dict[str, Any]]) -> None:
        """Register tools for filtering.

        Args:
            tools: List of tool schemas in standard format
        """
        for tool_schema in tools:
            func_info = tool_schema.get("function", {})
            name = func_info.get("name", "")
            description = func_info.get("description", "")

            if not name:
                continue

            # Detect category
            category = self._detect_category(name)

            # Extract keywords
            keywords = self._extract_keywords(name, description)

            tool_info = ToolInfo(
                name=name, description=description, category=category, schema=tool_schema, keywords=keywords
            )

            self._tools[name] = tool_info
            self._category_index[category].append(name)

            # Build keyword index
            for keyword in keywords:
                if keyword not in self._keyword_index:
                    self._keyword_index[keyword] = set()
                self._keyword_index[keyword].add(name)

        logger.info(f"Registered {len(self._tools)} tools across {len(ToolCategory)} categories")

    def _detect_category(self, tool_name: str) -> ToolCategory:
        """Detect tool category from its name.

        Uses pre-compiled regex patterns for faster matching (Phase 4 optimization).
        """
        name_lower = tool_name.lower()

        # Use pre-compiled patterns for faster matching
        compiled_patterns = _get_compiled_category_patterns()

        for category, patterns in compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(name_lower):
                    return category

        return ToolCategory.SYSTEM

    def _extract_keywords(self, name: str, description: str) -> set[str]:
        """Extract searchable keywords from tool name and description."""
        keywords = set()

        # Split name by underscores and camelCase
        name_parts = re.split(r"[_\s]", name)
        for part in name_parts:
            # Also split camelCase
            camel_parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", part).split()
            keywords.update(p.lower() for p in camel_parts if len(p) > 2)

        # Extract words from description
        desc_words = re.findall(r"\b\w{3,}\b", description.lower())
        # Filter common words
        stop_words = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "from",
            "will",
            "can",
            "has",
            "have",
            "are",
            "was",
            "were",
        }
        keywords.update(w for w in desc_words if w not in stop_words)

        return keywords

    def detect_task_type(self, task_description: str) -> list[str]:
        """Detect task types from description.

        Uses pre-compiled regex patterns for faster matching (Phase 4 optimization).

        Args:
            task_description: Natural language task description

        Returns:
            List of detected task types
        """
        task_lower = task_description.lower()
        detected = []

        # Use pre-compiled patterns for faster matching
        compiled_patterns = _get_compiled_task_patterns()

        for task_type, patterns in compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(task_lower):
                    detected.append(task_type)
                    break

        return detected or ["general"]

    def get_tools_for_task(
        self, task_description: str, include_mcp: bool = True, additional_tools: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Get relevant tools for a task.

        Args:
            task_description: Natural language task description
            include_mcp: Whether to include MCP tools
            additional_tools: Additional tool names to always include

        Returns:
            Filtered list of tool schemas
        """
        if not self.config.enabled:
            return [t.schema for t in self._tools.values()]

        # Detect task types
        task_types = self.detect_task_type(task_description)
        logger.debug(f"Detected task types: {task_types}")

        # Get relevant categories
        relevant_categories = set()
        for task_type in task_types:
            categories = TASK_TO_CATEGORIES.get(task_type, [])
            relevant_categories.update(categories)

        # Always include system tools
        relevant_categories.add(ToolCategory.SYSTEM)

        # Optionally include MCP
        if include_mcp:
            relevant_categories.add(ToolCategory.MCP)

        # Collect candidate tools
        candidates: dict[str, float] = {}  # tool_name -> score

        # Add category-based tools
        for category in relevant_categories:
            for tool_name in self._category_index.get(category, []):
                candidates[tool_name] = candidates.get(tool_name, 0) + 1.0

        # Add keyword-matched tools
        keyword_scores = self._keyword_search(task_description)
        for tool_name, score in keyword_scores.items():
            candidates[tool_name] = candidates.get(tool_name, 0) + score

        # Always include specified tools
        for tool_name in self.config.always_include:
            if tool_name in self._tools:
                candidates[tool_name] = candidates.get(tool_name, 0) + 2.0

        if additional_tools:
            for tool_name in additional_tools:
                if tool_name in self._tools:
                    candidates[tool_name] = candidates.get(tool_name, 0) + 2.0

        # Boost based on usage
        if self.config.boost_recent_tools:
            for tool_name, info in self._tools.items():
                if info.last_used and tool_name in candidates:
                    # Boost recently used tools
                    age = (datetime.now(UTC) - info.last_used).total_seconds()
                    if age < 300:  # Used in last 5 minutes
                        candidates[tool_name] += 0.5

        if self.config.boost_successful_tools:
            for tool_name, info in self._tools.items():
                if info.usage_count > 0 and tool_name in candidates:
                    # Boost frequently used tools
                    candidates[tool_name] += min(info.usage_count * 0.1, 1.0)

        # Sort by score and limit
        sorted_tools = sorted(candidates.items(), key=lambda x: x[1], reverse=True)[: self.config.max_tools_per_request]

        # Collect tool schemas
        result = []
        for tool_name, _score in sorted_tools:
            if tool_name in self._tools:
                result.append(self._tools[tool_name].schema)

        _total = len(self._tools)
        _reduction = (100 - len(result) * 100 // _total) if _total else 0
        logger.info(
            f"Dynamic toolset: {len(result)}/{_total} tools ({_reduction}% reduction)"
        )

        return result

    def _keyword_search(self, query: str) -> dict[str, float]:
        """Search tools by keyword matching.

        Phase 4 optimizations:
        - Pre-compiled word extraction regex
        - Limited partial match iterations to cap complexity
        - Early score accumulation for better cache locality

        Args:
            query: Search query

        Returns:
            Dict of tool_name -> relevance score
        """
        query_keywords = set(re.findall(r"\b\w{3,}\b", query.lower()))

        scores: dict[str, float] = {}

        for keyword in query_keywords:
            # Exact matches (O(1) lookup)
            if keyword in self._keyword_index:
                for tool_name in self._keyword_index[keyword]:
                    scores[tool_name] = scores.get(tool_name, 0) + 1.0

        # Partial matches - limited to avoid O(n*m) explosion on large keyword sets
        # Only check if we have few query keywords and indexed keywords
        if len(query_keywords) <= 10 and len(self._keyword_index) <= 500:
            for keyword in query_keywords:
                for indexed_keyword, tool_names in self._keyword_index.items():
                    # Skip exact matches (already counted above)
                    if keyword == indexed_keyword:
                        continue
                    if keyword in indexed_keyword or indexed_keyword in keyword:
                        for tool_name in tool_names:
                            scores[tool_name] = scores.get(tool_name, 0) + 0.5

        return scores

    def search_tools(
        self, query: str, limit: int = 10, category: ToolCategory | None = None
    ) -> list[tuple[str, float, str]]:
        """Search for tools semantically.

        Args:
            query: Search query
            limit: Maximum results
            category: Optional category filter

        Returns:
            List of (tool_name, score, description) tuples
        """
        scores = self._keyword_search(query)

        # Filter by category if specified
        if category:
            scores = {
                name: score
                for name, score in scores.items()
                if self._tools.get(name, ToolInfo("", "", ToolCategory.SYSTEM, {})).category == category
            }

        # Sort and limit
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]

        return [
            (name, score, self._tools[name].description[:100]) for name, score in sorted_results if name in self._tools
        ]

    def record_tool_usage(self, tool_name: str, success: bool = True, duration_ms: float = 0) -> None:
        """Record tool usage for prioritization.

        Args:
            tool_name: Name of the tool
            success: Whether the call was successful
            duration_ms: Call duration in milliseconds
        """
        if tool_name not in self._tools:
            return

        info = self._tools[tool_name]
        info.usage_count += 1
        info.last_used = datetime.now(UTC)

        # Update average duration
        if duration_ms > 0:
            if info.average_duration_ms == 0:
                info.average_duration_ms = duration_ms
            else:
                info.average_duration_ms = info.average_duration_ms * 0.8 + duration_ms * 0.2

    def get_stats(self) -> dict[str, Any]:
        """Get toolset statistics."""
        category_counts = {cat.value: len(tools) for cat, tools in self._category_index.items()}

        top_used = sorted([(n, t.usage_count) for n, t in self._tools.items()], key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_tools": len(self._tools),
            "categories": category_counts,
            "keywords_indexed": len(self._keyword_index),
            "top_used": top_used,
            "config": {"enabled": self.config.enabled, "max_tools": self.config.max_tools_per_request},
        }

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Get all registered tools (bypass filtering)."""
        return [t.schema for t in self._tools.values()]

    def _classify_task_type(self, message: str) -> str:
        """Classify a message into a task type for caching.

        Args:
            message: User message or task description

        Returns:
            Task type string (e.g., "research", "coding", "general")
        """
        task_types = self.detect_task_type(message)
        if task_types and task_types[0] != "general":
            return task_types[0]
        return "general"

    def _is_cache_valid(self, task_type: str) -> bool:
        """Check if cached tools for a task type are still valid.

        Args:
            task_type: The task type to check

        Returns:
            True if cache exists and is not expired
        """
        if not self.config.enable_task_type_cache:
            return False

        if task_type not in self._task_type_cache:
            return False

        _, cached_time = self._task_type_cache[task_type]
        age = (datetime.now(UTC) - cached_time).total_seconds()
        return age < self.config.cache_ttl_seconds

    def prefetch_tools_for_message(self, message: str, include_mcp: bool = True) -> list[dict[str, Any]]:
        """Prefetch and cache tools based on message/task type.

        This method is optimized for speed - uses cached results when available
        to reduce latency during planning phase.

        Args:
            message: User message or task description
            include_mcp: Whether to include MCP tools

        Returns:
            List of relevant tool schemas
        """
        task_type = self._classify_task_type(message)

        # Check cache first
        cache_key = f"{task_type}_{include_mcp}"
        if self._is_cache_valid(cache_key):
            cached_tools, _ = self._task_type_cache[cache_key]
            logger.debug(f"Prefetch cache hit for task type: {task_type}")
            return cached_tools

        # Generate tools if not cached
        tools = self.get_tools_for_task(message, include_mcp=include_mcp)

        # Cache the result
        if self.config.enable_task_type_cache:
            self._task_type_cache[cache_key] = (tools, datetime.now(UTC))
            logger.debug(f"Prefetch cached {len(tools)} tools for task type: {task_type}")

        return tools

    async def prefetch_tools_async(self, message: str, include_mcp: bool = True) -> list[dict[str, Any]]:
        """Async version of prefetch for use in parallel operations.

        Can be run concurrently with other async operations like planning.

        Args:
            message: User message or task description
            include_mcp: Whether to include MCP tools

        Returns:
            List of relevant tool schemas
        """
        task_type = self._classify_task_type(message)
        cache_key = f"{task_type}_{include_mcp}"

        # Check if prefetch is already in progress
        if self._prefetch_in_progress.get(cache_key):
            # Wait for existing prefetch to complete
            while self._prefetch_in_progress.get(cache_key, False):  # noqa: ASYNC110
                await asyncio.sleep(0.01)
            if self._is_cache_valid(cache_key):
                return self._task_type_cache[cache_key][0]

        # Mark as in progress
        self._prefetch_in_progress[cache_key] = True

        try:
            # Run prefetch (this is CPU-bound but quick)
            return self.prefetch_tools_for_message(message, include_mcp)
        finally:
            self._prefetch_in_progress[cache_key] = False

    def validate_tool_contracts(self) -> list[str]:
        """Validate tool parameter schemas and detect description overlap.

        WP-7: Called at startup to catch tool contract violations early.
        Checks:
        1. Every registered tool has a non-empty description.
        2. Every tool parameter has 'type' and 'description' fields.
        3. No two tools have >80% Jaccard keyword overlap in their descriptions.

        Returns:
            List of violation messages (empty when all contracts are valid).
        """
        violations: list[str] = []
        tool_list = list(self._tools.values())

        # 1. Parameter schema compliance
        for tool_info in tool_list:
            func = tool_info.schema.get("function", {})
            if not func.get("description"):
                violations.append(f"Tool '{tool_info.name}' has no description")
            params = func.get("parameters", {})
            props = params.get("properties", {}) if isinstance(params, dict) else {}
            for param_name, param_schema in props.items():
                if not isinstance(param_schema, dict):
                    continue
                if "type" not in param_schema:
                    violations.append(
                        f"Tool '{tool_info.name}' parameter '{param_name}' missing 'type'"
                    )
                if "description" not in param_schema:
                    violations.append(
                        f"Tool '{tool_info.name}' parameter '{param_name}' missing 'description'"
                    )

        # 2. Description keyword overlap (Jaccard similarity > 80%)
        for i in range(len(tool_list)):
            for j in range(i + 1, len(tool_list)):
                a, b = tool_list[i], tool_list[j]
                if a.keywords and b.keywords:
                    union = a.keywords | b.keywords
                    if union:
                        overlap_ratio = len(a.keywords & b.keywords) / len(union)
                        if overlap_ratio > 0.8:
                            violations.append(
                                f"Tools '{a.name}' and '{b.name}' have "
                                f"{overlap_ratio:.0%} keyword overlap — consider disambiguating descriptions"
                            )

        for v in violations:
            logger.warning("Tool contract violation: %s", v)

        if not violations:
            logger.debug("WP-7 tool contract validation passed (%d tools checked)", len(tool_list))

        return violations

    def warm_cache_for_common_tasks(self) -> None:
        """Pre-warm cache with tools for common task types.

        Call during application startup to reduce cold-start latency.
        """
        common_task_messages = {
            "research": "Research and find information about the topic",
            "coding": "Write code to implement the feature",
            "file_management": "Read and write files as needed",
            "web_browsing": "Browse the web and navigate pages",
            "analysis": "Analyze the data and provide insights",
        }

        for task_type, message in common_task_messages.items():
            self.prefetch_tools_for_message(message)
            logger.debug(f"Warmed cache for task type: {task_type}")

        logger.info(f"Cache warmed for {len(common_task_messages)} common task types")

        # WP-7: Validate tool contracts at startup to detect schema violations early
        self.validate_tool_contracts()

    def clear_cache(self) -> None:
        """Clear all cached tool prefetch data."""
        self._task_type_cache.clear()
        self._prefetch_in_progress.clear()
        logger.debug("Tool prefetch cache cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get statistics about the tool cache."""
        cache_entries = []
        for key, (tools, cached_time) in self._task_type_cache.items():
            age = (datetime.now(UTC) - cached_time).total_seconds()
            cache_entries.append(
                {
                    "key": key,
                    "tool_count": len(tools),
                    "age_seconds": age,
                    "expired": age >= self.config.cache_ttl_seconds,
                }
            )

        return {
            "total_entries": len(self._task_type_cache),
            "entries": cache_entries,
            "cache_enabled": self.config.enable_task_type_cache,
            "ttl_seconds": self.config.cache_ttl_seconds,
        }


class CacheWarmupManager:
    """Manages cache warmup for common operations.

    Pre-populates caches with frequently accessed data to reduce
    cold-start latency and improve response times.
    """

    def __init__(self):
        self._warmup_tasks: list[dict[str, Any]] = []
        self._warmed_up = False

    def register_warmup_task(self, name: str, coroutine_factory, priority: int = 5) -> None:
        """Register a cache warmup task.

        Args:
            name: Task name for logging
            coroutine_factory: Callable that returns a coroutine
            priority: Priority (1=highest, 10=lowest)
        """
        self._warmup_tasks.append({"name": name, "factory": coroutine_factory, "priority": priority})
        self._warmup_tasks.sort(key=lambda x: x["priority"])

    async def warmup(self, max_concurrent: int = 3) -> dict[str, bool]:
        """Execute cache warmup tasks.

        Args:
            max_concurrent: Maximum concurrent warmup tasks

        Returns:
            Dict of task_name -> success status
        """
        import asyncio

        results: dict[str, bool] = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_task(task: dict[str, Any]) -> tuple[str, bool]:
            async with semaphore:
                try:
                    await task["factory"]()
                    logger.debug(f"Warmup completed: {task['name']}")
                    return task["name"], True
                except Exception as e:
                    logger.warning(f"Warmup failed for {task['name']}: {e}")
                    return task["name"], False

        if self._warmup_tasks:
            completed = await asyncio.gather(*[run_task(t) for t in self._warmup_tasks], return_exceptions=True)

            for item in completed:
                if isinstance(item, tuple):
                    results[item[0]] = item[1]

        self._warmed_up = True
        logger.info(f"Cache warmup completed: {sum(results.values())}/{len(results)} tasks succeeded")

        return results

    @property
    def is_warmed_up(self) -> bool:
        """Check if warmup has been completed."""
        return self._warmed_up


# Global instances
_toolset_manager: DynamicToolsetManager | None = None
_warmup_manager: CacheWarmupManager | None = None


def get_toolset_manager() -> DynamicToolsetManager:
    """Get or create the global toolset manager.

    WP-7: Calls warm_cache_for_common_tasks() on first creation so that
    validate_tool_contracts() runs at startup and logs any schema violations.
    """
    global _toolset_manager
    if _toolset_manager is None:
        _toolset_manager = DynamicToolsetManager()
        # Wire the previously dead-code path: warm cache + validate contracts on startup
        try:
            _toolset_manager.warm_cache_for_common_tasks()
        except Exception as _wc_err:
            logger.warning("Tool contract warm-up failed (non-critical): %s", _wc_err)
    return _toolset_manager


def get_warmup_manager() -> CacheWarmupManager:
    """Get or create the global warmup manager."""
    global _warmup_manager
    if _warmup_manager is None:
        _warmup_manager = CacheWarmupManager()
    return _warmup_manager
