from __future__ import annotations
from typing import AsyncGenerator
from scenarios.engine import eid, ts, tc, delay

async def run(message: str, session_id: str) -> AsyncGenerator[tuple[str, dict], None]:
    topic = message.strip()

    yield "progress", {
        "event_id": eid(), "timestamp": ts(),
        "phase": "received", "message": "Understanding your request...",
    }
    await delay(0.5)

    yield "progress", {
        "event_id": eid(), "timestamp": ts(),
        "phase": "analyzing", "message": "Breaking down the task...",
    }
    await delay(0.6)

    yield "progress", {
        "event_id": eid(), "timestamp": ts(),
        "phase": "planning", "message": "Creating execution plan...",
        "estimated_steps": 4,
    }
    await delay(0.5)

    # Plan with 4 steps
    s1, s2, s3, s4 = eid(), eid(), eid(), eid()
    yield "plan", {
        "event_id": eid(), "timestamp": ts(),
        "steps": [
            {"id": s1, "description": "Research and gather information", "status": "pending", "event_id": eid(), "timestamp": ts()},
            {"id": s2, "description": "Analyze findings", "status": "pending", "event_id": eid(), "timestamp": ts()},
            {"id": s3, "description": "Create output files", "status": "pending", "event_id": eid(), "timestamp": ts()},
            {"id": s4, "description": "Verify and finalize", "status": "pending", "event_id": eid(), "timestamp": ts()},
        ],
    }
    await delay(0.3)

    # Step 1: Search
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": s1, "description": "Research and gather information", "status": "running"}
    await delay(0.3)

    yield "thought", {
        "event_id": eid(), "timestamp": ts(),
        "status": "thinking", "thought_type": "analysis",
        "content": f"Let me start by researching: {topic}",
    }
    await delay(0.4)

    tc1 = tc()
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc1, "name": "info_search_web", "status": "calling",
        "function": "info_search_web",
        "args": {"query": topic},
        "display_command": f"Searching: {topic[:50]}",
        "command_category": "search",
    }
    await delay(1.0)
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc1, "name": "info_search_web", "status": "called",
        "function": "info_search_web",
        "args": {"query": topic},
        "content": {"results": [
            {"title": f"Guide: {topic[:30]}", "link": "https://example.com/1", "snippet": f"Comprehensive resource about {topic}..."},
            {"title": f"{topic[:30]} - Best Practices", "link": "https://example.com/2", "snippet": "Industry best practices and recommendations..."},
        ], "query": topic},
    }
    await delay(0.2)
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": s1, "description": "Research and gather information", "status": "completed"}
    await delay(0.3)

    # Step 2: Analyze
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": s2, "description": "Analyze findings", "status": "running"}
    await delay(0.3)

    yield "thought", {
        "event_id": eid(), "timestamp": ts(),
        "status": "thought", "thought_type": "observation",
        "content": "The search results provide good coverage. Let me browse the top result for more details.",
    }
    await delay(0.4)

    tc2 = tc()
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc2, "name": "browser_navigate", "status": "calling",
        "function": "browser_navigate",
        "args": {"url": "https://example.com/1"},
        "display_command": "Opening top result",
        "command_category": "browse",
    }
    await delay(1.2)
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc2, "name": "browser_navigate", "status": "called",
        "function": "browser_navigate",
        "args": {"url": "https://example.com/1"},
        "content": {"screenshot": None, "content": f"Detailed content about {topic}..."},
    }
    await delay(0.2)
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": s2, "description": "Analyze findings", "status": "completed"}
    await delay(0.3)

    # Step 3: Create files
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": s3, "description": "Create output files", "status": "running"}
    await delay(0.3)

    tc3 = tc()
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc3, "name": "file_write", "status": "calling",
        "function": "file_write",
        "args": {"file": "/workspace/output.md"},
        "display_command": "Creating output.md",
        "command_category": "file",
        "file_path": "/workspace/output.md",
    }
    await delay(0.8)

    output_content = f"# {topic}\n\n## Summary\n\nBased on research and analysis, here are the key findings...\n\n## Details\n\nDetailed analysis and recommendations.\n"
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc3, "name": "file_write", "status": "called",
        "function": "file_write",
        "args": {"file": "/workspace/output.md"},
        "content": {"content": output_content},
        "file_path": "/workspace/output.md",
        "diff": "+" + output_content.replace("\n", "\n+"),
    }
    await delay(0.2)
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": s3, "description": "Create output files", "status": "completed"}
    await delay(0.3)

    # Step 4: Verify
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": s4, "description": "Verify and finalize", "status": "running"}
    await delay(0.3)

    tc4 = tc()
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc4, "name": "shell_exec", "status": "calling",
        "function": "shell_exec",
        "args": {"command": "wc -l /workspace/output.md"},
        "display_command": "Verifying output file",
        "command_category": "shell",
        "command": "wc -l /workspace/output.md",
    }
    await delay(0.6)
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc4, "name": "shell_exec", "status": "called",
        "function": "shell_exec",
        "args": {"command": "wc -l /workspace/output.md"},
        "content": {"console": [{"ps1": "user@sandbox:~$", "command": "wc -l /workspace/output.md", "output": "8 /workspace/output.md"}], "stdout": "8 /workspace/output.md", "exit_code": 0},
        "stdout": "8 /workspace/output.md", "exit_code": 0,
    }
    await delay(0.2)
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": s4, "description": "Verify and finalize", "status": "completed"}
    await delay(0.3)

    yield "message", {
        "event_id": eid(), "timestamp": ts(),
        "content": f"I've completed the task. Here's a summary of what I did:\n\n1. **Researched** the topic and found relevant sources\n2. **Analyzed** the top results for key information\n3. **Created** an output file with the findings\n4. **Verified** the output is correct\n\nThe results are saved in `/workspace/output.md`.",
        "role": "assistant", "attachments": [],
    }
    await delay(0.2)

    yield "suggestion", {
        "event_id": eid(), "timestamp": ts(),
        "suggestions": [
            "Expand on the findings",
            "Create a different format (PDF/slides)",
            "Run additional analysis",
        ],
    }

    yield "title", {
        "event_id": eid(), "timestamp": ts(),
        "title": topic[:50] if topic else "Task Completed",
    }

    yield "done", {"event_id": eid(), "timestamp": ts()}
