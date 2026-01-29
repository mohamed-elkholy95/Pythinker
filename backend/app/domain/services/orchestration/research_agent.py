"""Specialized research agent for deep information gathering.

Integrates with existing AgentRegistry for automatic dispatch.
"""
import logging
from collections.abc import AsyncGenerator

from app.domain.external.browser import Browser
from app.domain.external.llm import LLM
from app.domain.external.search import SearchEngine
from app.domain.models.event import BaseEvent, MessageEvent, ToolEvent, ToolStatus
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.agents.base import BaseAgent
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """Specialized agent for comprehensive research tasks.

    Workflow:
    1. Generate diverse search queries (3-8 based on depth)
    2. Execute searches and rank sources
    3. Browse top sources
    4. Synthesize findings with cross-referencing
    5. Generate bibliography
    6. Create final report with citations
    """

    name: str = "research"
    system_prompt: str = """You are a research specialist agent focused on comprehensive information gathering.

Your workflow:
1. Generate diverse, complementary search queries
2. Evaluate source credibility (.edu, .gov = high)
3. Extract and synthesize key information
4. Cross-reference findings
5. Cite all sources properly

Prioritize authoritative sources and recent information."""

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository | None,
        llm: LLM,
        json_parser: JsonParser,
        search_engine: SearchEngine | None = None,
        browser: Browser | None = None,
        max_sources: int = 10,
        search_depth: str = "deep",  # "quick", "standard", "deep"
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            json_parser=json_parser,
            tools=[],
        )
        self._search_engine = search_engine
        self._browser = browser
        self._max_sources = max_sources
        self._search_depth = search_depth

        # Search query counts by depth
        self._query_counts = {
            "quick": 3,
            "standard": 5,
            "deep": 8,
        }

    async def research(
        self,
        topic: str,
        requirements: str | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute research workflow.

        Args:
            topic: Research topic/question
            requirements: Specific requirements or constraints

        Yields:
            Events documenting research progress
        """
        logger.info(f"Starting research: {topic}")

        # Step 1: Generate search queries
        yield MessageEvent(
            message=f"Generating search queries for: {topic}",
            role="assistant"
        )

        queries = await self._generate_queries(topic, requirements)

        yield MessageEvent(
            message=f"Generated {len(queries)} search queries",
            role="assistant"
        )

        # Step 2: Execute searches
        all_results = []
        if self._search_engine:
            for query in queries:
                yield ToolEvent(
                    tool_call_id=f"search_{hash(query)}",
                    tool_name="search_web",
                    function_name="search_web",
                    function_args={"query": query},
                    status=ToolStatus.CALLING,
                    display_command=f"Searching '{query}'",
                    command_category="search",
                )

                try:
                    results = await self._search_engine.search(query)
                    all_results.extend(results)
                except Exception as e:
                    logger.error(f"Search failed for query '{query}': {e}")

        # Deduplicate and rank
        ranked_sources = self._rank_sources(all_results)[:self._max_sources]

        yield MessageEvent(
            message=f"Found {len(ranked_sources)} relevant sources",
            role="assistant"
        )

        # Step 3: Browse and extract
        extracted_content = []
        if self._browser:
            for source in ranked_sources:
                yield ToolEvent(
                    tool_call_id=f"browse_{hash(source.get('url', ''))}",
                    tool_name="browser_navigate",
                    function_name="browser_navigate",
                    function_args={"url": source.get('url', '')},
                    status=ToolStatus.CALLING,
                    display_command=f"Browsing {source.get('url', '')}",
                    command_category="browse",
                )

                try:
                    content = await self._browser.get_page_content(source.get('url', ''))
                    extracted_content.append({
                        "url": source.get('url', ''),
                        "title": source.get('title', 'Unknown'),
                        "content": content,
                        "credibility": source.get('credibility', 'medium'),
                    })
                except Exception as e:
                    logger.error(f"Failed to browse {source.get('url', '')}: {e}")

        # Step 4: Synthesize findings
        yield MessageEvent(
            message="Synthesizing research findings...",
            role="assistant"
        )

        synthesis = await self._synthesize_findings(
            topic=topic,
            sources=extracted_content,
            requirements=requirements,
        )

        # Step 5: Generate report
        report = self._generate_report(
            topic=topic,
            synthesis=synthesis,
            sources=extracted_content,
        )

        yield MessageEvent(
            message=report,
            role="assistant"
        )

        logger.info("Research complete")

    async def _generate_queries(
        self,
        topic: str,
        requirements: str | None,
    ) -> list[str]:
        """Generate diverse search queries using LLM"""
        query_count = self._query_counts.get(self._search_depth, 5)

        prompt = f"""Generate {query_count} diverse, complementary search queries for researching: {topic}

Requirements: {requirements or "Comprehensive coverage"}

Return JSON array of queries:
{{"queries": ["query 1", "query 2", ...]}}"""

        try:
            response = await self.llm.generate(
                messages=[{"role": "user", "content": prompt}],
                format="json_object",
            )

            parsed = self.json_parser.parse(response)
            return parsed.get("queries", [topic])
        except Exception as e:
            logger.error(f"Failed to generate queries: {e}")
            return [topic]

    def _rank_sources(self, results: list[dict]) -> list[dict]:
        """Rank sources by credibility and relevance"""
        def credibility_score(result):
            url = result.get('url', '')
            score = 0

            # High credibility domains
            if any(domain in url for domain in ['.edu', '.gov', '.org']):
                score += 3

            # Academic/research indicators
            if any(term in url.lower() for term in ['scholar', 'research', 'journal', 'arxiv']):
                score += 2

            # Penalize low-quality sources
            if any(term in url.lower() for term in ['blog', 'forum', 'reddit']):
                score -= 1

            result['credibility_score'] = score
            result['credibility'] = 'high' if score >= 3 else 'medium' if score >= 1 else 'low'

            return score

        # Sort by credibility score (descending)
        sorted_results = sorted(results, key=credibility_score, reverse=True)

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for result in sorted_results:
            url = result.get('url', '')
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)

        return unique_results

    async def _synthesize_findings(
        self,
        topic: str,
        sources: list[dict],
        requirements: str | None,
    ) -> str:
        """Synthesize findings using LLM"""
        # Build context from sources
        context = "\n\n".join([
            f"Source: {s['title']} ({s['url']})\nCredibility: {s['credibility']}\n{s['content'][:1000]}..."
            for s in sources[:10]  # Limit to top 10 sources
        ])

        prompt = f"""Synthesize comprehensive findings on: {topic}

Requirements: {requirements or "Comprehensive analysis"}

Sources:
{context}

Provide a 500-800 word synthesis that:
1. Answers the research question
2. Cross-references multiple sources
3. Notes any conflicting information
4. Highlights key findings

Return JSON:
{{"synthesis": "...", "key_findings": ["...", "..."], "conflicts": ["..."]}}"""

        try:
            response = await self.llm.generate(
                messages=[{"role": "user", "content": prompt}],
                format="json_object",
            )

            return self.json_parser.parse(response).get("synthesis", "")
        except Exception as e:
            logger.error(f"Failed to synthesize findings: {e}")
            return "Synthesis failed due to an error."

    def _generate_report(
        self,
        topic: str,
        synthesis: str,
        sources: list[dict],
    ) -> str:
        """Generate final markdown report with citations"""
        report = f"""# Research Report: {topic}

## Synthesis

{synthesis}

## Bibliography

"""

        for i, source in enumerate(sources, 1):
            report += f"{i}. [{source['title']}]({source['url']}) - Credibility: {source['credibility']}\n"

        report += f"\n---\n*Research completed with {len(sources)} sources*"

        return report
