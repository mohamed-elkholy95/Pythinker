from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from stores import session_store
from routes.auth import _get_current_user
from scenarios.engine import select_scenario

router = APIRouter(prefix="/sessions")


def _wrap(data):
    return {"code": 0, "msg": "success", "data": data}


# ── CRUD ─────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    mode: str | None = "agent"
    message: str | None = None


@router.post("")
async def stream_sessions(request: Request):
    """SSE endpoint for real-time session list updates (matches backend POST /sessions)."""
    user = _get_current_user(request)

    async def event_generator():
        try:
            while True:
                sessions = session_store.list_sessions(user["id"])
                items = []
                for s in sessions:
                    items.append({
                        "session_id": s["session_id"],
                        "title": s.get("title"),
                        "latest_message": s.get("latest_message"),
                        "latest_message_at": s.get("latest_message_at"),
                        "status": s["status"],
                        "unread_message_count": s.get("unread_message_count", 0),
                        "is_shared": s.get("is_shared", False),
                    })
                data = json.dumps({"sessions": items})
                yield {"event": "sessions", "data": data}
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            return

    return EventSourceResponse(event_generator())


@router.put("")
async def create_session(req: CreateSessionRequest, request: Request):
    user = _get_current_user(request)
    session = session_store.create_session(req.mode or "agent", user["id"])
    return _wrap({
        "session_id": session["session_id"],
        "mode": session["mode"],
        "sandbox": {
            "sandbox_id": f"sbx_{session['session_id'][-8:]}",
            "vnc_url": None,
            "status": "initializing",
        },
        "status": session["status"],
    })


@router.get("")
async def list_sessions(request: Request):
    user = _get_current_user(request)
    sessions = session_store.list_sessions(user["id"])
    items = []
    for s in sessions:
        items.append({
            "session_id": s["session_id"],
            "title": s.get("title"),
            "latest_message": s.get("latest_message"),
            "latest_message_at": s.get("latest_message_at"),
            "status": s["status"],
            "unread_message_count": s.get("unread_message_count", 0),
            "is_shared": s.get("is_shared", False),
        })
    return _wrap({"sessions": items})


@router.get("/shared/{session_id}")
async def get_shared_session(session_id: str):
    session = session_store.get_session(session_id)
    if not session:
        return {"code": 404, "msg": "Session not found", "data": None}
    events = session_store.get_events(session_id)
    return _wrap({
        "session_id": session_id,
        "title": session.get("title"),
        "status": session["status"],
        "events": events,
        "is_shared": True,
    })


@router.get("/{session_id}")
async def get_session(session_id: str):
    session = session_store.get_session(session_id)
    if not session:
        return {"code": 404, "msg": "Session not found", "data": None}
    events = session_store.get_events(session_id)
    return _wrap({
        "session_id": session_id,
        "title": session.get("title"),
        "status": session["status"],
        "events": events,
        "is_shared": session.get("is_shared", False),
    })


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    session_store.delete_session(session_id)
    return _wrap({})


class RenameRequest(BaseModel):
    title: str


@router.patch("/{session_id}/rename")
async def rename_session(session_id: str, req: RenameRequest):
    session = session_store.get_session(session_id)
    if session:
        session["title"] = req.title
    return _wrap({})


@router.post("/{session_id}/stop")
async def stop_session(session_id: str):
    session = session_store.get_session(session_id)
    if session:
        session["status"] = "completed"
    return _wrap({})


@router.post("/{session_id}/pause")
async def pause_session(session_id: str):
    session = session_store.get_session(session_id)
    if session:
        session["status"] = "waiting"
    return _wrap({})


class ResumeRequest(BaseModel):
    context: str | None = None
    persist_login_state: bool | None = None


@router.post("/{session_id}/resume")
async def resume_session(session_id: str, req: ResumeRequest):
    session = session_store.get_session(session_id)
    if session:
        session["status"] = "running"
    return _wrap({})


@router.post("/{session_id}/share")
async def share_session(session_id: str):
    session = session_store.get_session(session_id)
    if session:
        session["is_shared"] = True
    return _wrap({"session_id": session_id, "is_shared": True})


@router.delete("/{session_id}/share")
async def unshare_session(session_id: str):
    session = session_store.get_session(session_id)
    if session:
        session["is_shared"] = False
    return _wrap({"session_id": session_id, "is_shared": False})


@router.post("/{session_id}/clear_unread_message_count")
async def clear_unread(session_id: str):
    session = session_store.get_session(session_id)
    if session:
        session["unread_message_count"] = 0
    return _wrap({})


# ── SSE Chat ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    timestamp: int | None = None
    message: str | None = None
    attachments: list[dict] | None = None
    event_id: str | None = None
    skills: list[str] | None = None
    deep_research: bool | None = None


@router.post("/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest):
    session = session_store.get_session(session_id)
    if not session:
        return {"code": 404, "msg": "Session not found", "data": None}

    message = req.message or ""
    deep_research = req.deep_research or False

    # Store user message event
    if message:
        import uuid
        user_event = {
            "event": "message",
            "data": {
                "event_id": uuid.uuid4().hex[:12],
                "timestamp": int(time.time()),
                "content": message,
                "role": "user",
                "attachments": req.attachments or [],
            },
        }
        session_store.add_event(session_id, user_event)
        session["status"] = "running"
        session["latest_message"] = message
        session["latest_message_at"] = int(time.time())

    async def event_generator():
        try:
            # Use discuss-mode simple chat if mode is "discuss"
            if session.get("mode") == "discuss" and not deep_research:
                from scenarios.simple_chat import run as simple_run
                scenario = simple_run
            else:
                scenario = select_scenario(message, deep_research)

            async for event_type, data in scenario(message, session_id):
                # Store event for replay
                evt = {"event": event_type, "data": data}
                session_store.add_event(session_id, evt)

                # Update session state from events
                if event_type == "title":
                    session["title"] = data.get("title")
                if event_type == "message" and data.get("role") == "assistant":
                    session["latest_message"] = data.get("content", "")[:100]
                    session["latest_message_at"] = int(time.time())
                if event_type == "done":
                    session["status"] = "completed"

                yield {"event": event_type, "data": json.dumps(data)}

        except asyncio.CancelledError:
            session["status"] = "completed"
        except Exception as e:
            error_data = {"event_id": "err", "timestamp": int(time.time()), "error": str(e)}
            yield {"event": "error", "data": json.dumps(error_data)}
            session["status"] = "failed"

    return EventSourceResponse(event_generator())


# ── SSE Browse ───────────────────────────────────────────────────────

class BrowseRequest(BaseModel):
    url: str


@router.post("/{session_id}/browse")
async def browse_url(session_id: str, req: BrowseRequest):
    from scenarios.browser_navigation import run as browser_run

    async def event_generator():
        async for event_type, data in browser_run(f"browse {req.url}", session_id):
            session_store.add_event(session_id, {"event": event_type, "data": data})
            yield {"event": event_type, "data": json.dumps(data)}

    return EventSourceResponse(event_generator())


# ── Shell / File View ────────────────────────────────────────────────

@router.post("/{session_id}/shell")
async def view_shell(session_id: str):
    return _wrap({
        "output": "user@sandbox:~$ ls\nmain.py  requirements.txt  src/  tests/\nuser@sandbox:~$ ",
        "session_id": session_id,
        "console": [
            {"ps1": "user@sandbox:~$", "command": "ls", "output": "main.py  requirements.txt  src/  tests/"},
        ],
    })


class FileViewRequest(BaseModel):
    file: str


@router.post("/{session_id}/file")
async def view_file(session_id: str, req: FileViewRequest):
    return _wrap({
        "content": f"# Content of {req.file}\n\n# This is a demo file content placeholder.\n# In production, this would read from the sandbox filesystem.\n",
        "file": req.file,
    })


@router.get("/{session_id}/files")
async def get_session_files(session_id: str):
    return _wrap([
        {
            "file_id": "file_demo_001",
            "filename": "output.md",
            "content_type": "text/markdown",
            "size": 1024,
            "upload_date": "2025-12-20T10:30:00Z",
            "metadata": {},
            "file_url": "/api/v1/files/file_demo_001/download",
        },
    ])


@router.get("/{session_id}/share/files")
async def get_shared_session_files(session_id: str):
    return _wrap([])


# ── Tool Action Confirm ──────────────────────────────────────────────

class ConfirmRequest(BaseModel):
    accept: bool


@router.post("/{session_id}/actions/{action_id}/confirm")
async def confirm_action(session_id: str, action_id: str, req: ConfirmRequest):
    return _wrap({})


# ── Deep Research Control ────────────────────────────────────────────

@router.post("/{session_id}/deep-research/approve")
async def approve_deep_research(session_id: str):
    approval = session_store.deep_research_approvals.get(session_id)
    if approval and isinstance(approval, asyncio.Event):
        approval.set()
    return _wrap({})


class SkipQueryRequest(BaseModel):
    query_id: str | None = None


@router.post("/{session_id}/deep-research/skip")
async def skip_deep_research_query(session_id: str, req: SkipQueryRequest):
    return _wrap({})


@router.get("/{session_id}/deep-research/status")
async def deep_research_status(session_id: str):
    return _wrap({
        "research_id": f"dr_{session_id[-8:]}",
        "status": "completed",
        "total_queries": 5,
        "completed_queries": 5,
    })


# ── VNC / Sandbox ────────────────────────────────────────────────────

# Minimal valid JPEG: 1x1 gray pixel
_JPEG_1x1 = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
    0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
    0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
    0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
    0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
    0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
    0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
    0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
    0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
    0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
    0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
    0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
    0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
    0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
    0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
    0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
    0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
    0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
    0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
    0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
    0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
    0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94, 0x11, 0x00, 0x00, 0x00, 0x00, 0xFF,
    0xD9,
])


class SignedUrlRequest(BaseModel):
    expire_minutes: int = 15


@router.post("/{session_id}/vnc/signed-url")
async def vnc_signed_url(session_id: str, req: SignedUrlRequest):
    return _wrap({
        "signed_url": f"ws://localhost:8083/vnc/{session_id}?token=mock_signed",
        "expires_in": req.expire_minutes * 60,
    })


@router.get("/{session_id}/vnc/screenshot")
async def vnc_screenshot(session_id: str, quality: int = 75, scale: float = 0.5):
    return Response(content=_JPEG_1x1, media_type="image/jpeg")


@router.get("/{session_id}/sandbox/url")
async def sandbox_url(session_id: str):
    return _wrap({"sandbox_url": "http://localhost:8083"})
