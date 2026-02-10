from __future__ import annotations
import time
import uuid
from stores import session_store

def _eid() -> str:
    return uuid.uuid4().hex[:12]

def _ts(offset: int = 0) -> int:
    return int(time.time()) - 86400 + offset  # yesterday

def seed_sessions() -> None:
    """Create 3 pre-seeded completed sessions with event histories."""

    # Session 1: Research session
    s1 = session_store.create_session("agent")
    s1["title"] = "Research: AI Agent Architectures"
    s1["status"] = "completed"
    s1["latest_message"] = "Here's a comprehensive report on AI agent architectures..."
    s1["latest_message_at"] = _ts(3600)
    session_store.session_events[s1["session_id"]] = [
        {"event": "message", "data": {"event_id": _eid(), "timestamp": _ts(0), "content": "Research the latest AI agent architectures and frameworks", "role": "user", "attachments": []}},
        {"event": "progress", "data": {"event_id": _eid(), "timestamp": _ts(10), "phase": "received", "message": "Analyzing your request..."}},
        {"event": "progress", "data": {"event_id": _eid(), "timestamp": _ts(20), "phase": "planning", "message": "Creating research plan...", "estimated_steps": 3}},
        {"event": "plan", "data": {"event_id": _eid(), "timestamp": _ts(30), "steps": [
            {"id": "step_1", "description": "Search for AI agent frameworks", "status": "completed", "event_id": _eid(), "timestamp": _ts(30)},
            {"id": "step_2", "description": "Analyze architecture patterns", "status": "completed", "event_id": _eid(), "timestamp": _ts(30)},
            {"id": "step_3", "description": "Compile research report", "status": "completed", "event_id": _eid(), "timestamp": _ts(30)},
        ]}},
        {"event": "tool", "data": {"event_id": _eid(), "timestamp": _ts(60), "tool_call_id": "tc_1", "name": "info_search_web", "status": "called", "function": "info_search_web", "args": {"query": "AI agent architectures 2025"}, "content": {"results": [{"title": "Legacy Flow: Multi-Agent Orchestration", "link": "https://example.com/legacy-flow", "snippet": "Legacy Flow provides a framework for building stateful multi-agent systems..."}], "query": "AI agent architectures 2025"}}},
        {"event": "message", "data": {"event_id": _eid(), "timestamp": _ts(3600), "content": "Here's a comprehensive report on AI agent architectures covering Legacy Flow, CrewAI, AutoGen, and emerging patterns in 2025.", "role": "assistant", "attachments": []}},
        {"event": "suggestion", "data": {"event_id": _eid(), "timestamp": _ts(3610), "suggestions": ["Compare Legacy Flow vs CrewAI in detail", "Research agent memory systems", "Create a diagram of agent architectures"]}},
        {"event": "done", "data": {"event_id": _eid(), "timestamp": _ts(3620)}},
    ]

    # Session 2: Code generation session
    s2 = session_store.create_session("agent")
    s2["title"] = "Build a Python REST API"
    s2["status"] = "completed"
    s2["latest_message"] = "I've created the FastAPI application with all the endpoints."
    s2["latest_message_at"] = _ts(7200)
    session_store.session_events[s2["session_id"]] = [
        {"event": "message", "data": {"event_id": _eid(), "timestamp": _ts(0), "content": "Create a Python REST API with FastAPI for a todo app", "role": "user", "attachments": []}},
        {"event": "progress", "data": {"event_id": _eid(), "timestamp": _ts(10), "phase": "planning", "message": "Planning the API structure..."}},
        {"event": "tool", "data": {"event_id": _eid(), "timestamp": _ts(120), "tool_call_id": "tc_2", "name": "file_write", "status": "called", "function": "file_write", "args": {"file": "main.py"}, "file_path": "/workspace/main.py", "diff": "+from fastapi import FastAPI\n+app = FastAPI()\n+\n+@app.get('/todos')\n+async def list_todos():\n+    return []"}},
        {"event": "message", "data": {"event_id": _eid(), "timestamp": _ts(7200), "content": "I've created the FastAPI application with all the endpoints. The project includes:\n- CRUD endpoints for todos\n- Pydantic models for validation\n- In-memory storage", "role": "assistant", "attachments": []}},
        {"event": "done", "data": {"event_id": _eid(), "timestamp": _ts(7210)}},
    ]

    # Session 3: Discussion session
    s3 = session_store.create_session("discuss")
    s3["title"] = "Understanding Docker Networking"
    s3["status"] = "completed"
    s3["latest_message"] = "Docker networking provides several drivers..."
    s3["latest_message_at"] = _ts(1800)
    session_store.session_events[s3["session_id"]] = [
        {"event": "message", "data": {"event_id": _eid(), "timestamp": _ts(0), "content": "Explain Docker networking modes", "role": "user", "attachments": []}},
        {"event": "message", "data": {"event_id": _eid(), "timestamp": _ts(1800), "content": "Docker networking provides several drivers:\n\n**Bridge** (default): Isolated network on single host. Containers communicate via IP.\n\n**Host**: Container shares host's network. Best for performance-critical apps.\n\n**Overlay**: Multi-host networking for Docker Swarm/Kubernetes.\n\n**Macvlan**: Assigns MAC address to container, appears as physical device.\n\n**None**: Disables networking entirely.", "role": "assistant", "attachments": []}},
        {"event": "suggestion", "data": {"event_id": _eid(), "timestamp": _ts(1810), "suggestions": ["How do I create a custom bridge network?", "Explain Docker Compose networking", "Compare overlay vs bridge performance"]}},
        {"event": "done", "data": {"event_id": _eid(), "timestamp": _ts(1820)}},
    ]
