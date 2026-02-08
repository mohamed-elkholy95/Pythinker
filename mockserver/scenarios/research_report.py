from __future__ import annotations
from typing import AsyncGenerator
from scenarios.engine import eid, ts, tc, delay

SAMPLE_REPORT = """# Research Report: {topic}

## Executive Summary

This research explores the key aspects of {topic}, analyzing current trends, major developments, and future implications based on multiple authoritative sources.

## Key Findings

### 1. Current State
The field of {topic} has seen significant advancement in recent years. Industry adoption has accelerated, with major organizations investing heavily in related technologies and methodologies.

### 2. Major Trends
- **Trend A**: Increasing automation and AI integration
- **Trend B**: Growing focus on scalability and performance
- **Trend C**: Enhanced security and privacy considerations
- **Trend D**: Community-driven open source development

### 3. Challenges
Several challenges remain, including:
- Integration complexity with existing systems
- Skill gaps in the workforce
- Regulatory uncertainty in some jurisdictions
- Cost optimization for large-scale deployments

## Analysis

Based on our research across multiple sources, {topic} represents a rapidly evolving space with significant potential for impact. The convergence of several technological trends suggests continued growth and innovation.

## Recommendations

1. **Stay informed** about the latest developments through regular monitoring
2. **Invest in training** to build organizational capability
3. **Start with pilot projects** before full-scale adoption
4. **Engage with the community** to share learnings and best practices

## Sources

1. Industry Analysis Report 2025
2. Academic Research Papers (2024-2025)
3. Expert Interviews and Conference Proceedings
4. Official Documentation and Technical Specifications
"""

async def run(message: str, session_id: str) -> AsyncGenerator[tuple[str, dict], None]:
    topic = message.replace("research", "").replace("search", "").replace("find", "").strip()
    if not topic:
        topic = "the requested topic"

    # Phase 1: Progress
    yield "progress", {
        "event_id": eid(), "timestamp": ts(),
        "phase": "received", "message": "Analyzing your research request...",
    }
    await delay(0.6)

    yield "progress", {
        "event_id": eid(), "timestamp": ts(),
        "phase": "analyzing", "message": "Identifying key research areas...",
    }
    await delay(0.8)

    yield "progress", {
        "event_id": eid(), "timestamp": ts(),
        "phase": "planning", "message": "Creating research plan...",
        "estimated_steps": 3,
    }
    await delay(0.5)

    # Phase 2: Plan
    step1_id, step2_id, step3_id = eid(), eid(), eid()
    yield "plan", {
        "event_id": eid(), "timestamp": ts(),
        "steps": [
            {"id": step1_id, "description": f"Search for information on {topic}", "status": "pending", "event_id": eid(), "timestamp": ts()},
            {"id": step2_id, "description": "Analyze and cross-reference sources", "status": "pending", "event_id": eid(), "timestamp": ts()},
            {"id": step3_id, "description": "Compile comprehensive research report", "status": "pending", "event_id": eid(), "timestamp": ts()},
        ],
    }
    await delay(0.4)

    # Phase 3: Step 1 - Search
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step1_id, "description": f"Search for information on {topic}", "status": "running"}
    await delay(0.3)

    yield "thought", {
        "event_id": eid(), "timestamp": ts(),
        "status": "thinking", "thought_type": "analysis",
        "content": f"I need to search for comprehensive information about {topic}. Let me start with a broad web search.",
        "step_name": step1_id,
    }
    await delay(0.4)

    # Tool: search
    tc1 = tc()
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc1, "name": "info_search_web", "status": "calling",
        "function": "info_search_web",
        "args": {"query": f"{topic} comprehensive overview 2025"},
        "display_command": f"Search for '{topic} comprehensive overview 2025'",
        "command_category": "search",
    }
    await delay(1.2)

    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc1, "name": "info_search_web", "status": "called",
        "function": "info_search_web",
        "args": {"query": f"{topic} comprehensive overview 2025"},
        "content": {
            "results": [
                {"title": f"Comprehensive Guide to {topic.title()}", "link": "https://example.com/guide", "snippet": f"An in-depth exploration of {topic} covering fundamentals, applications, and future directions..."},
                {"title": f"{topic.title()} - State of the Art 2025", "link": "https://example.com/sota", "snippet": f"Latest research and developments in {topic}, including breakthrough findings and industry adoption..."},
                {"title": f"Understanding {topic.title()}: Expert Analysis", "link": "https://example.com/analysis", "snippet": f"Expert-driven analysis of {topic} trends, challenges, and opportunities in the modern landscape..."},
            ],
            "query": f"{topic} comprehensive overview 2025",
            "total_results": 3,
        },
    }
    await delay(0.3)

    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step1_id, "description": f"Search for information on {topic}", "status": "completed"}
    await delay(0.3)

    # Phase 4: Step 2 - Browse
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step2_id, "description": "Analyze and cross-reference sources", "status": "running"}
    await delay(0.3)

    tc2 = tc()
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc2, "name": "browser_navigate", "status": "calling",
        "function": "browser_navigate",
        "args": {"url": "https://example.com/guide"},
        "display_command": "Opening: Comprehensive Guide",
        "command_category": "browse",
    }
    await delay(1.5)

    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc2, "name": "browser_navigate", "status": "called",
        "function": "browser_navigate",
        "args": {"url": "https://example.com/guide"},
        "content": {"screenshot": None, "content": f"Detailed content about {topic}..."},
    }
    await delay(0.3)

    yield "thought", {
        "event_id": eid(), "timestamp": ts(),
        "status": "thought", "thought_type": "observation",
        "content": f"I've gathered good information from multiple sources. The key themes are: current trends, challenges, and future directions for {topic}.",
    }
    await delay(0.3)

    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step2_id, "description": "Analyze and cross-reference sources", "status": "completed"}
    await delay(0.3)

    # Phase 5: Step 3 - Write report
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step3_id, "description": "Compile comprehensive research report", "status": "running"}
    await delay(0.3)

    tc3 = tc()
    report_content = SAMPLE_REPORT.replace("{topic}", topic)
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc3, "name": "file_write", "status": "calling",
        "function": "file_write",
        "args": {"file": f"/workspace/research_{topic.replace(' ', '_')[:20]}.md"},
        "display_command": f"Writing research report",
        "command_category": "file",
        "file_path": f"/workspace/research_{topic.replace(' ', '_')[:20]}.md",
    }
    await delay(0.8)

    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc3, "name": "file_write", "status": "called",
        "function": "file_write",
        "args": {"file": f"/workspace/research_{topic.replace(' ', '_')[:20]}.md"},
        "content": {"content": report_content},
        "file_path": f"/workspace/research_{topic.replace(' ', '_')[:20]}.md",
        "diff": "+" + report_content.replace("\n", "\n+"),
    }
    await delay(0.3)

    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step3_id, "description": "Compile comprehensive research report", "status": "completed"}
    await delay(0.3)

    # Phase 6: Report event
    yield "report", {
        "event_id": eid(), "timestamp": ts(),
        "id": f"report_{eid()}",
        "title": f"Research Report: {topic.title()}",
        "content": report_content,
        "sources": [
            {"url": "https://example.com/guide", "title": f"Comprehensive Guide to {topic.title()}", "snippet": "An in-depth exploration...", "access_time": "2025-12-20T10:30:00Z", "source_type": "search"},
            {"url": "https://example.com/sota", "title": f"{topic.title()} - State of the Art 2025", "snippet": "Latest research and developments...", "access_time": "2025-12-20T10:31:00Z", "source_type": "search"},
            {"url": "https://example.com/analysis", "title": f"Understanding {topic.title()}: Expert Analysis", "snippet": "Expert-driven analysis...", "access_time": "2025-12-20T10:32:00Z", "source_type": "browser"},
        ],
    }
    await delay(0.3)

    # Phase 7: Summary message
    yield "message", {
        "event_id": eid(), "timestamp": ts(),
        "content": f"I've completed the research on **{topic}** and compiled a comprehensive report. The report covers current state, major trends, challenges, and recommendations based on multiple sources.\n\nYou can view the full report above or download the file from the workspace.",
        "role": "assistant", "attachments": [],
    }
    await delay(0.3)

    yield "suggestion", {
        "event_id": eid(), "timestamp": ts(),
        "suggestions": [
            f"Deep dive into a specific aspect of {topic}",
            "Create a presentation from this research",
            f"Find more recent data about {topic}",
        ],
    }

    yield "title", {
        "event_id": eid(), "timestamp": ts(),
        "title": f"Research: {topic.title()}"[:50],
    }

    yield "done", {"event_id": eid(), "timestamp": ts()}
