from __future__ import annotations
import asyncio
import uuid
import time

# session_id -> session dict
sessions: dict[str, dict] = {}

# session_id -> list of SSE event dicts (for replay)
session_events: dict[str, list[dict]] = {}

# session_id -> asyncio.Event for deep research approval
deep_research_approvals: dict[str, asyncio.Event] = {}


def create_session(mode: str = "agent", user_id: str = "usr_demo_001") -> dict:
    sid = f"ses_{uuid.uuid4().hex[:12]}"
    now = int(time.time())
    session = {
        "session_id": sid,
        "title": None,
        "status": "pending",
        "mode": mode,
        "user_id": user_id,
        "is_shared": False,
        "created_at": now,
        "latest_message": None,
        "latest_message_at": None,
        "unread_message_count": 0,
    }
    sessions[sid] = session
    session_events[sid] = []
    return session


def get_session(session_id: str) -> dict | None:
    return sessions.get(session_id)


def list_sessions(user_id: str = "usr_demo_001") -> list[dict]:
    result = []
    for s in sessions.values():
        if s.get("user_id") == user_id:
            result.append(s)
    result.sort(
        key=lambda x: x.get("latest_message_at") or x.get("created_at", 0), reverse=True
    )
    return result


def delete_session(session_id: str) -> bool:
    if session_id in sessions:
        del sessions[session_id]
        session_events.pop(session_id, None)
        return True
    return False


def add_event(session_id: str, event: dict) -> None:
    if session_id in session_events:
        session_events[session_id].append(event)


def get_events(session_id: str) -> list[dict]:
    return session_events.get(session_id, [])
