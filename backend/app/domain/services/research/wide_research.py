"""Wide research orchestrator for parallel multi-agent research."""

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from app.domain.models.research_task import ResearchStatus, ResearchTask

if TYPE_CHECKING:
    from app.domain.services.agents.critic_agent import CriticAgent

logger = logging.getLogger(__name__)


class SearchToolProtocol(Protocol):
    """Protocol for search tool interface."""

    async def execute(self, query: str) -> dict[str, Any]: ...


class LLMProtocol(Protocol):
    """Protocol for LLM interface."""

    async def complete(self, prompt: str) -> str: ...


class WideResearchOrchestrator:
    """
    Orchestrates wide research using parallel sub-agents.

    Implements Manus AI's "Wide Research" pattern:
    - Decomposes research into independent sub-tasks
    - Executes sub-tasks in parallel with separate contexts
    - Ensures consistent quality across all items (100th = 1st)
    - Synthesizes results into unified output
    """

    MAX_RESULTS_PER_QUERY = 5
    MAX_SOURCES_IN_SYNTHESIS = 3

    def __init__(
        self,
        session_id: str,
        search_tool: SearchToolProtocol,
        llm: LLMProtocol | None,
        max_concurrency: int = 10,
        on_progress: Callable[[ResearchTask], None] | None = None,
        critic: "CriticAgent | None" = None,
    ):
        """
        Initialize the wide research orchestrator.

        Args:
            session_id: The session identifier for this research
            search_tool: Tool for executing search queries
            llm: Language model for synthesis
            max_concurrency: Maximum number of parallel tasks
            on_progress: Optional callback for progress updates
            critic: Optional CriticAgent for quality review of synthesis
        """
        self.session_id = session_id
        self.search_tool = search_tool
        self.llm = llm
        self.max_concurrency = max_concurrency
        self.on_progress = on_progress
        self.critic = critic
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def decompose(
        self,
        queries: list[str],
        parent_id: str,
    ) -> list[ResearchTask]:
        """
        Decompose a list of queries into independent research tasks.

        Each task gets its own context and can be processed without
        interference from other tasks.

        Args:
            queries: List of research queries to decompose
            parent_id: ID of the parent research request

        Returns:
            List of ResearchTask objects ready for parallel execution
        """
        return [
            ResearchTask(
                query=query,
                parent_task_id=parent_id,
                index=i,
                total=len(queries),
            )
            for i, query in enumerate(queries)
        ]

    async def _execute_single(self, task: ResearchTask) -> ResearchTask:
        """
        Execute a single research task with isolated context.

        Uses semaphore to limit concurrency and prevent resource exhaustion.

        Args:
            task: The research task to execute

        Returns:
            The task with updated status and results
        """
        async with self._semaphore:
            logger.debug(
                "Starting research task %d/%d: %s",
                task.index + 1,
                task.total,
                task.query,
            )
            task.start()
            if self.on_progress:
                self.on_progress(task)

            try:
                # Search for information
                search_result = await self.search_tool.execute(query=task.query)

                # Extract sources and content
                sources = []
                content_parts = []
                if isinstance(search_result, dict) and "results" in search_result:
                    for r in search_result["results"][: self.MAX_RESULTS_PER_QUERY]:
                        if "url" in r:
                            sources.append(r["url"])
                        if "content" in r:
                            content_parts.append(r["content"])
                        elif "snippet" in r:
                            content_parts.append(r["snippet"])

                # Build result from content parts
                result = "\n\n".join(content_parts) if content_parts else "No results found"
                task.complete(result, sources)
                logger.debug(
                    "Completed research task %d/%d with %d sources",
                    task.index + 1,
                    task.total,
                    len(sources),
                )

            except Exception as e:
                logger.warning(
                    "Research task %d/%d failed: %s",
                    task.index + 1,
                    task.total,
                    str(e),
                )
                task.fail(str(e))

            if self.on_progress:
                self.on_progress(task)

            return task

    async def execute_parallel(
        self,
        tasks: list[ResearchTask],
    ) -> list[ResearchTask]:
        """
        Execute all research tasks in parallel.

        Uses semaphore to limit concurrency and prevent resource exhaustion.
        Each task runs in its own context, ensuring the 100th item gets
        the same quality attention as the 1st.

        Args:
            tasks: List of research tasks to execute

        Returns:
            List of tasks with updated statuses and results
        """
        results = await asyncio.gather(
            *[self._execute_single(task) for task in tasks],
            return_exceptions=True,
        )

        # Handle any exceptions that weren't caught
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                tasks[i].fail(str(result))

        return tasks

    async def synthesize(
        self,
        tasks: list[ResearchTask],
        synthesis_prompt: str | None = None,
    ) -> str:
        """
        Synthesize all research results into a unified report.

        This is the aggregation phase where a main agent combines
        the independent findings into a coherent output.

        Args:
            tasks: List of completed research tasks
            synthesis_prompt: Optional prompt for LLM synthesis

        Returns:
            Synthesized research report
        """
        completed = [t for t in tasks if t.status == ResearchStatus.COMPLETED]

        if not completed:
            return "No research results to synthesize."

        # Build synthesis input
        logger.debug("Synthesizing %d completed research tasks", len(completed))
        findings = []
        for task in completed:
            finding = f"### {task.query}\n{task.result}"
            if task.sources:
                finding += f"\n\nSources: {', '.join(task.sources[: self.MAX_SOURCES_IN_SYNTHESIS])}"
            findings.append(finding)

        synthesis_input = "\n\n---\n\n".join(findings)

        # Use LLM to synthesize if available
        if synthesis_prompt and self.llm:
            prompt = f"{synthesis_prompt}\n\n## Research Findings\n\n{synthesis_input}"
            return await self.llm.complete(prompt)

        return synthesis_input

    async def synthesize_with_review(
        self,
        tasks: list[ResearchTask],
        synthesis_prompt: str | None = None,
        max_revisions: int = 2,
    ) -> str:
        """
        Synthesize results with critic review loop.

        Implements self-correction pattern:
        1. Synthesize initial result
        2. Critic reviews
        3. If not approved, revise and re-review (up to max_revisions)

        Args:
            tasks: List of completed research tasks
            synthesis_prompt: Optional prompt for LLM synthesis
            max_revisions: Maximum number of revision attempts

        Returns:
            Synthesized research report (possibly revised)
        """
        result = await self.synthesize(tasks, synthesis_prompt)

        if not self.critic:
            return result

        for _ in range(max_revisions):
            review = await self.critic.review(
                output=result,
                task=synthesis_prompt or "Synthesize research findings",
                criteria=["accuracy", "completeness", "coherence"],
            )

            if review.approved:
                return result

            # Revise based on feedback
            if self.llm and review.issues:
                revision_prompt = f"""
The following synthesis was reviewed and needs improvement.

## Original Synthesis
{result}

## Issues Found
{chr(10).join(f"- {issue}" for issue in review.issues)}

## Suggestions
{chr(10).join(f"- {s}" for s in review.suggestions)}

Please provide an improved synthesis addressing these issues.
"""
                result = await self.llm.complete(revision_prompt)
            else:
                # No LLM available for revision, return current result
                break

        return result
