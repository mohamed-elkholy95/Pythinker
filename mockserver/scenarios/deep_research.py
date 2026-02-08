from __future__ import annotations
import asyncio
from typing import AsyncGenerator
from scenarios.engine import eid, ts, tc, delay
from stores import session_store

async def run(message: str, session_id: str) -> AsyncGenerator[tuple[str, dict], None]:
    topic = message.lower().replace("deep research", "").replace("on", "").strip()
    if not topic:
        topic = "the requested topic"

    research_id = f"dr_{eid()}"

    queries = [
        {"id": f"q_{eid()}", "query": f"{topic} overview and fundamentals", "status": "pending"},
        {"id": f"q_{eid()}", "query": f"{topic} latest developments 2025", "status": "pending"},
        {"id": f"q_{eid()}", "query": f"{topic} expert analysis and opinions", "status": "pending"},
        {"id": f"q_{eid()}", "query": f"{topic} challenges and limitations", "status": "pending"},
        {"id": f"q_{eid()}", "query": f"{topic} future directions and predictions", "status": "pending"},
    ]

    yield "progress", {
        "event_id": eid(), "timestamp": ts(),
        "phase": "received", "message": "Preparing deep research...",
    }
    await delay(0.5)

    # Emit deep_research event in awaiting_approval state
    yield "deep_research", {
        "event_id": eid(), "timestamp": ts(),
        "research_id": research_id,
        "status": "awaiting_approval",
        "total_queries": len(queries),
        "completed_queries": 0,
        "queries": queries,
        "auto_run": False,
    }

    # Create an asyncio.Event for approval
    approval_event = asyncio.Event()
    session_store.deep_research_approvals[session_id] = approval_event

    # Wait for approval (auto-approve after 30s for demo)
    try:
        await asyncio.wait_for(approval_event.wait(), timeout=30.0)
    except asyncio.TimeoutError:
        pass  # Auto-approve

    # Emit started status
    yield "deep_research", {
        "event_id": eid(), "timestamp": ts(),
        "research_id": research_id,
        "status": "started",
        "total_queries": len(queries),
        "completed_queries": 0,
        "queries": queries,
        "auto_run": False,
    }
    await delay(0.5)

    # Process each query
    for i, q in enumerate(queries):
        q["status"] = "searching"
        q["started_at"] = ts()
        yield "deep_research", {
            "event_id": eid(), "timestamp": ts(),
            "research_id": research_id,
            "status": "started",
            "total_queries": len(queries),
            "completed_queries": i,
            "queries": queries,
            "auto_run": False,
        }
        await delay(1.5)

        q["status"] = "completed"
        q["completed_at"] = ts()
        q["result"] = [
            {"title": f"Result for: {q['query'][:30]}", "link": f"https://example.com/dr/{i}", "snippet": f"Relevant findings about {q['query']}..."},
        ]
        yield "deep_research", {
            "event_id": eid(), "timestamp": ts(),
            "research_id": research_id,
            "status": "started",
            "total_queries": len(queries),
            "completed_queries": i + 1,
            "queries": queries,
            "auto_run": False,
        }
        await delay(0.3)

    # Completed
    yield "deep_research", {
        "event_id": eid(), "timestamp": ts(),
        "research_id": research_id,
        "status": "completed",
        "total_queries": len(queries),
        "completed_queries": len(queries),
        "queries": queries,
        "auto_run": False,
    }
    await delay(0.5)

    # Generate report
    yield "report", {
        "event_id": eid(), "timestamp": ts(),
        "id": f"report_{eid()}",
        "title": f"Deep Research: {topic.title()}",
        "content": f"# Deep Research: {topic.title()}\n\n## Overview\nComprehensive multi-source analysis of {topic}.\n\n## Findings\nAcross {len(queries)} parallel research queries, we identified key themes and patterns.\n\n## Conclusion\nThe deep research process uncovered significant insights that would not be apparent from a single search.",
        "sources": [{"url": f"https://example.com/dr/{i}", "title": q["query"], "snippet": "Research findings...", "access_time": "2025-12-20T10:30:00Z", "source_type": "search"} for i, q in enumerate(queries)],
    }
    await delay(0.3)

    yield "message", {
        "event_id": eid(), "timestamp": ts(),
        "content": f"Deep research on **{topic}** is complete. I conducted {len(queries)} parallel searches and compiled the findings into a comprehensive report.",
        "role": "assistant", "attachments": [],
    }
    await delay(0.2)

    yield "suggestion", {
        "event_id": eid(), "timestamp": ts(),
        "suggestions": [
            "Dive deeper into a specific finding",
            "Export the research as PDF",
            "Start a follow-up research",
        ],
    }

    yield "title", {
        "event_id": eid(), "timestamp": ts(),
        "title": f"Deep Research: {topic.title()}"[:50],
    }

    # Cleanup before final yield (code after final yield is unreachable)
    session_store.deep_research_approvals.pop(session_id, None)

    yield "done", {"event_id": eid(), "timestamp": ts()}
