from __future__ import annotations
from typing import AsyncGenerator
from scenarios.engine import eid, ts, delay

async def run(message: str, session_id: str) -> AsyncGenerator[tuple[str, dict], None]:
    topic = message.lower().replace("wide research", "").replace("on", "").strip()
    if not topic:
        topic = "the requested topic"

    research_id = f"wr_{eid()}"
    search_types = ["general", "news", "academic", "social"]

    yield "progress", {
        "event_id": eid(), "timestamp": ts(),
        "phase": "received", "message": "Initiating wide research...",
    }
    await delay(0.5)

    # Pending
    yield "wide_research", {
        "event_id": eid(), "timestamp": ts(),
        "research_id": research_id, "topic": topic,
        "status": "pending",
        "total_queries": 8, "completed_queries": 0,
        "sources_found": 0, "search_types": search_types,
    }
    await delay(0.5)

    # Searching - 4 updates
    total_sources = 0
    queries_done = 0
    for i, st in enumerate(search_types):
        for j in range(2):  # 2 queries per search type
            queries_done += 1
            total_sources += 3 + i
            yield "wide_research", {
                "event_id": eid(), "timestamp": ts(),
                "research_id": research_id, "topic": topic,
                "status": "searching",
                "total_queries": 8, "completed_queries": queries_done,
                "sources_found": total_sources, "search_types": search_types,
                "current_query": f"{topic} ({st} search {j+1})",
            }
            await delay(0.8)

    # Aggregating
    yield "wide_research", {
        "event_id": eid(), "timestamp": ts(),
        "research_id": research_id, "topic": topic,
        "status": "aggregating",
        "total_queries": 8, "completed_queries": 8,
        "sources_found": total_sources, "search_types": search_types,
        "aggregation_strategy": "relevance_weighted",
    }
    await delay(1.5)

    # Completed
    yield "wide_research", {
        "event_id": eid(), "timestamp": ts(),
        "research_id": research_id, "topic": topic,
        "status": "completed",
        "total_queries": 8, "completed_queries": 8,
        "sources_found": total_sources, "search_types": search_types,
    }
    await delay(0.5)

    # Report
    yield "report", {
        "event_id": eid(), "timestamp": ts(),
        "id": f"report_{eid()}",
        "title": f"Wide Research: {topic.title()}",
        "content": f"# Wide Research: {topic.title()}\n\n## Research Scope\nSearched across {len(search_types)} source categories with {8} total queries.\n\n## Sources Found\n{total_sources} unique sources identified and analyzed.\n\n## Key Insights\n\n### General Web\nBroad coverage of {topic} with focus on recent developments.\n\n### News Sources\nCurrent events and breaking developments.\n\n### Academic\nPeer-reviewed research and technical papers.\n\n### Social Media\nCommunity discussions, expert opinions, and trends.\n\n## Synthesis\nCross-referencing multiple source types provides a comprehensive picture of {topic}.",
    }
    await delay(0.3)

    yield "message", {
        "event_id": eid(), "timestamp": ts(),
        "content": f"Wide research on **{topic}** is complete. I searched across {len(search_types)} categories (general, news, academic, social) and found {total_sources} sources in total.",
        "role": "assistant", "attachments": [],
    }
    await delay(0.2)

    yield "suggestion", {
        "event_id": eid(), "timestamp": ts(),
        "suggestions": [
            "Focus on a specific category",
            "Compare different viewpoints",
            "Create a summary presentation",
        ],
    }

    yield "title", {
        "event_id": eid(), "timestamp": ts(),
        "title": f"Wide Research: {topic.title()}"[:50],
    }

    yield "done", {"event_id": eid(), "timestamp": ts()}
