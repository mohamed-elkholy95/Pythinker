"""Deep Research Flow for parallel search execution.

Enables parallel research queries with real-time progress tracking.
Features:
- Parallel search execution (configurable concurrency)
- User approval workflow for non-auto-run mode
- Skip functionality for long-running searches
- Real-time SSE progress updates
- JSON compilation of all research results
- Report generation from compiled research
"""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from app.domain.external.search import SearchEngine
from app.domain.models.deep_research import (
    DeepResearchConfig,
    DeepResearchSession,
    ResearchQuery,
    ResearchQueryStatus,
)
from app.domain.models.event import (
    BaseEvent,
    DeepResearchEvent,
    DeepResearchQueryData,
    DeepResearchQueryStatus,
    DeepResearchStatus,
)
from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


class DeepResearchFlow:
    """Executes parallel research queries with progress tracking.

    The flow manages:
    - User approval workflow (optional)
    - Parallel query execution with semaphore
    - Skip signals for individual queries
    - Progress event emission

    Usage:
        flow = DeepResearchFlow(search_engine)
        async for event in flow.run(config):
            yield event
    """

    def __init__(
        self,
        search_engine: SearchEngine,
        session_id: str,
    ):
        """Initialize the deep research flow.

        Args:
            search_engine: Search engine for executing queries
            session_id: Parent session ID for tracking
        """
        self.search_engine = search_engine
        self.session_id = session_id

        # Internal state
        self._research_id: str | None = None
        self._session: DeepResearchSession | None = None
        self._approval_event: asyncio.Event | None = None
        self._skip_events: dict[str, asyncio.Event] = {}
        self._cancelled = False
        self._event_queue: asyncio.Queue[BaseEvent] = asyncio.Queue()

    @property
    def research_id(self) -> str | None:
        """Get the current research ID."""
        return self._research_id

    def _create_queries(self, query_strings: list[str]) -> list[ResearchQuery]:
        """Create ResearchQuery objects from query strings."""
        return [
            ResearchQuery(
                id=str(uuid.uuid4())[:8],
                query=q.strip(),
                status=ResearchQueryStatus.PENDING,
            )
            for q in query_strings
            if q.strip()
        ]

    def _to_query_data(self, query: ResearchQuery) -> DeepResearchQueryData:
        """Convert ResearchQuery to event data format."""
        return DeepResearchQueryData(
            id=query.id,
            query=query.query,
            status=DeepResearchQueryStatus(query.status.value),
            result=query.result,
            started_at=query.started_at,
            completed_at=query.completed_at,
        )

    def _create_event(self, status: DeepResearchStatus) -> DeepResearchEvent:
        """Create a DeepResearchEvent with current state."""
        return DeepResearchEvent(
            research_id=self._research_id,
            status=status,
            total_queries=len(self._session.queries),
            completed_queries=self._session.completed_count,
            queries=[self._to_query_data(q) for q in self._session.queries],
            auto_run=self._session.config.auto_run,
        )

    async def run(
        self,
        config: DeepResearchConfig,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute the deep research flow.

        Args:
            config: Research configuration with queries and settings

        Yields:
            DeepResearchEvent updates as progress is made
        """
        # Initialize session
        self._research_id = str(uuid.uuid4())[:12]
        queries = self._create_queries(config.queries)

        if not queries:
            logger.warning("No valid queries provided for deep research")
            return

        self._session = DeepResearchSession(
            research_id=self._research_id,
            session_id=self.session_id,
            config=config,
            queries=queries,
            status="pending",
        )

        # Initialize skip events for each query
        for query in queries:
            self._skip_events[query.id] = asyncio.Event()

        # Initialize approval event
        self._approval_event = asyncio.Event()

        logger.info(f"Starting deep research {self._research_id} with {len(queries)} queries")

        # Emit initial state
        if config.auto_run:
            # Auto-run: skip approval, start immediately
            self._session.status = "started"
            self._session.started_at = datetime.now()
            yield self._create_event(DeepResearchStatus.STARTED)
        else:
            # Awaiting approval
            self._session.status = "awaiting_approval"
            yield self._create_event(DeepResearchStatus.AWAITING_APPROVAL)

            # Wait for approval or cancellation
            try:
                await asyncio.wait_for(
                    self._approval_event.wait(),
                    timeout=300.0,  # 5 minute timeout
                )
            except TimeoutError:
                self._session.status = "cancelled"
                yield self._create_event(DeepResearchStatus.CANCELLED)
                return

            if self._cancelled:
                self._session.status = "cancelled"
                yield self._create_event(DeepResearchStatus.CANCELLED)
                return

            # Approved - start execution
            self._session.status = "started"
            self._session.started_at = datetime.now()
            yield self._create_event(DeepResearchStatus.STARTED)

        # Execute queries in parallel
        async for event in self._execute_queries(config):
            yield event

        # Mark completed
        self._session.status = "completed"
        self._session.completed_at = datetime.now()
        yield self._create_event(DeepResearchStatus.COMPLETED)

        logger.info(
            f"Deep research {self._research_id} completed: {self._session.completed_count}/{len(queries)} queries"
        )

    async def _execute_queries(
        self,
        config: DeepResearchConfig,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute queries in parallel with concurrency control.

        Args:
            config: Research configuration

        Yields:
            Progress events for each query
        """
        semaphore = asyncio.Semaphore(config.max_concurrent)

        async def execute_query(query: ResearchQuery) -> None:
            """Execute a single query with semaphore control."""
            async with semaphore:
                if self._cancelled:
                    return

                # Check if already skipped
                if self._skip_events[query.id].is_set():
                    query.status = ResearchQueryStatus.SKIPPED
                    query.completed_at = datetime.now()
                    await self._event_queue.put(self._create_event(DeepResearchStatus.QUERY_SKIPPED))
                    return

                # Mark as searching
                query.status = ResearchQueryStatus.SEARCHING
                query.started_at = datetime.now()
                await self._event_queue.put(self._create_event(DeepResearchStatus.QUERY_STARTED))

                try:
                    # Execute search with timeout and skip check
                    result = await asyncio.wait_for(
                        self._search_with_skip_check(query, config.timeout_per_query),
                        timeout=config.timeout_per_query + 5,  # Extra buffer
                    )

                    if query.status == ResearchQueryStatus.SKIPPED:
                        # Was skipped during execution
                        await self._event_queue.put(self._create_event(DeepResearchStatus.QUERY_SKIPPED))
                        return

                    if result and result.success:
                        query.status = ResearchQueryStatus.COMPLETED
                        # Extract search results as list of dicts
                        # ToolResult uses 'data' field for the typed result
                        if result.data and hasattr(result.data, "results"):
                            query.result = [r.model_dump() for r in result.data.results]
                        else:
                            query.result = []
                    else:
                        query.status = ResearchQueryStatus.FAILED
                        query.error = result.message if result else "Search failed"

                except TimeoutError:
                    query.status = ResearchQueryStatus.FAILED
                    query.error = "Query timed out"
                except Exception as e:
                    logger.error(f"Query {query.id} failed: {e}")
                    query.status = ResearchQueryStatus.FAILED
                    query.error = str(e)

                query.completed_at = datetime.now()
                await self._event_queue.put(self._create_event(DeepResearchStatus.QUERY_COMPLETED))

        # Start all queries as tasks
        tasks = [asyncio.create_task(execute_query(q)) for q in self._session.queries]

        # Yield events as they come in
        pending_count = len(tasks)
        done_tasks = set()

        while pending_count > 0:
            # Check for completed tasks
            newly_done = set()
            for task in tasks:
                if task.done() and task not in done_tasks:
                    newly_done.add(task)
                    done_tasks.add(task)
                    pending_count -= 1

            # Yield any queued events
            while not self._event_queue.empty():
                try:
                    event = self._event_queue.get_nowait()
                    yield event
                except asyncio.QueueEmpty:
                    break

            # Small delay to prevent busy loop
            if pending_count > 0:
                await asyncio.sleep(0.1)

        # Yield any remaining events
        while not self._event_queue.empty():
            try:
                event = self._event_queue.get_nowait()
                yield event
            except asyncio.QueueEmpty:
                break

    async def _search_with_skip_check(
        self,
        query: ResearchQuery,
        timeout: int,  # noqa: ASYNC109
    ) -> ToolResult | None:
        """Execute search with periodic skip checks.

        Args:
            query: Query to execute
            timeout: Timeout in seconds

        Returns:
            Search result or None if skipped
        """
        # Create the search task
        search_task = asyncio.create_task(self.search_engine.search(query.query))

        # Periodically check for skip signal
        check_interval = 0.5
        elapsed = 0.0

        while not search_task.done() and elapsed < timeout:
            # Check skip signal
            if self._skip_events[query.id].is_set():
                search_task.cancel()
                query.status = ResearchQueryStatus.SKIPPED
                return None

            # Wait a bit
            try:
                await asyncio.wait_for(
                    asyncio.shield(search_task),
                    timeout=check_interval,
                )
            except TimeoutError:
                elapsed += check_interval
            except asyncio.CancelledError:
                query.status = ResearchQueryStatus.SKIPPED
                return None

        if search_task.done():
            try:
                return search_task.result()
            except Exception as e:
                logger.error(f"Search task failed: {e}")
                return None

        # Timeout reached
        search_task.cancel()
        return None

    async def approve(self) -> None:
        """Approve the research to start execution."""
        if self._approval_event:
            logger.info(f"Deep research {self._research_id} approved")
            self._approval_event.set()

    async def cancel(self) -> None:
        """Cancel the research."""
        self._cancelled = True
        if self._approval_event:
            self._approval_event.set()
        logger.info(f"Deep research {self._research_id} cancelled")

    async def skip_query(self, query_id: str) -> bool:
        """Skip a specific query.

        Args:
            query_id: ID of the query to skip

        Returns:
            True if query was found and skip signal set
        """
        if query_id in self._skip_events:
            self._skip_events[query_id].set()
            logger.info(f"Skip signal set for query {query_id}")
            return True
        return False

    async def skip_all(self) -> None:
        """Skip all pending queries."""
        for query_id in self._skip_events:
            self._skip_events[query_id].set()
        logger.info(f"Skip all signal set for research {self._research_id}")

    def get_session(self) -> DeepResearchSession | None:
        """Get the current research session."""
        return self._session

    def get_query_status(self, query_id: str) -> ResearchQueryStatus | None:
        """Get the status of a specific query."""
        if not self._session:
            return None
        for query in self._session.queries:
            if query.id == query_id:
                return query.status
        return None

    def compile_results_to_json(self) -> dict[str, Any]:
        """Compile all research results into a structured JSON format.

        Returns:
            Dictionary containing all research results in a structured format
            similar to Manus's research.json output
        """
        if not self._session:
            return {}

        results = []
        for query in self._session.queries:
            if query.status == ResearchQueryStatus.COMPLETED and query.result:
                results.append(
                    {
                        "input": query.query,
                        "output": {
                            "results": query.result,
                            "total_results": len(query.result),
                            "completed_at": query.completed_at.isoformat() if query.completed_at else None,
                        },
                    }
                )
            elif query.status == ResearchQueryStatus.SKIPPED:
                results.append(
                    {
                        "input": query.query,
                        "output": {
                            "status": "skipped",
                            "results": [],
                        },
                    }
                )
            elif query.status == ResearchQueryStatus.FAILED:
                results.append(
                    {
                        "input": query.query,
                        "output": {
                            "status": "failed",
                            "error": query.error,
                            "results": [],
                        },
                    }
                )

        return {
            "research_id": self._research_id,
            "session_id": self.session_id,
            "created_at": self._session.created_at.isoformat() if self._session.created_at else None,
            "completed_at": self._session.completed_at.isoformat() if self._session.completed_at else None,
            "total_queries": len(self._session.queries),
            "completed_queries": self._session.completed_count,
            "results": results,
        }

    def get_results_json_string(self, indent: int = 2) -> str:
        """Get research results as a formatted JSON string.

        Args:
            indent: JSON indentation level

        Returns:
            Formatted JSON string of research results
        """
        return json.dumps(self.compile_results_to_json(), indent=indent, ensure_ascii=False)

    def get_all_search_results(self) -> list[dict[str, Any]]:
        """Get all search results flattened for report generation.

        Returns:
            List of all search results with their source queries
        """
        if not self._session:
            return []

        all_results = []
        for query in self._session.queries:
            if query.status == ResearchQueryStatus.COMPLETED and query.result:
                all_results.extend(
                    {
                        "query": query.query,
                        "title": result.get("title", ""),
                        "link": result.get("link", ""),
                        "snippet": result.get("snippet", ""),
                    }
                    for result in query.result
                )
        return all_results

    def generate_research_summary(self) -> str:
        """Generate a markdown summary of the research results.

        Returns:
            Markdown formatted summary of research findings
        """
        if not self._session:
            return ""

        lines = [
            "# Deep Research Summary",
            "",
            f"**Research ID:** {self._research_id}",
            f"**Total Queries:** {len(self._session.queries)}",
            f"**Completed:** {self._session.completed_count}",
            "",
            "## Research Queries",
            "",
        ]

        for i, query in enumerate(self._session.queries, 1):
            status_icon = {
                ResearchQueryStatus.COMPLETED: "v",
                ResearchQueryStatus.SKIPPED: "-",
                ResearchQueryStatus.FAILED: "x",
                ResearchQueryStatus.PENDING: "o",
                ResearchQueryStatus.SEARCHING: "...",
            }.get(query.status, "?")

            lines.append(f"### {i}. [{status_icon}] {query.query}")
            lines.append("")

            if query.status == ResearchQueryStatus.COMPLETED and query.result:
                lines.append(f"**Found {len(query.result)} results:**")
                lines.append("")
                for j, result in enumerate(query.result[:5], 1):  # Limit to top 5
                    title = result.get("title", "Untitled")
                    link = result.get("link", "")
                    snippet = result.get("snippet", "")[:200]
                    lines.append(f"{j}. [{title}]({link})")
                    if snippet:
                        lines.append(f"   > {snippet}...")
                    lines.append("")
                if len(query.result) > 5:
                    lines.append(f"   *... and {len(query.result) - 5} more results*")
                    lines.append("")
            elif query.status == ResearchQueryStatus.SKIPPED:
                lines.append("*Query was skipped*")
                lines.append("")
            elif query.status == ResearchQueryStatus.FAILED:
                lines.append(f"*Query failed: {query.error or 'Unknown error'}*")
                lines.append("")

        return "\n".join(lines)
