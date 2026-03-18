from __future__ import annotations
from typing import AsyncGenerator
from scenarios.engine import eid, ts, delay


async def run(message: str, session_id: str) -> AsyncGenerator[tuple[str, dict], None]:
    await delay(0.5)

    yield (
        "progress",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "phase": "received",
            "message": "Processing your message...",
        },
    )
    await delay(0.8)

    # Generate a contextual response
    response = _generate_response(message)

    yield (
        "message",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "content": response,
            "role": "assistant",
            "attachments": [],
        },
    )
    await delay(0.3)

    yield (
        "suggestion",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "suggestions": [
                "Tell me more about this topic",
                "Can you provide examples?",
                "What are the alternatives?",
            ],
        },
    )
    await delay(0.1)

    yield (
        "title",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "title": message[:50] + ("..." if len(message) > 50 else ""),
        },
    )

    yield "done", {"event_id": eid(), "timestamp": ts()}


def _generate_response(message: str) -> str:
    msg = message.lower()
    if "hello" in msg or "hi" in msg:
        return "Hello! I'm Pythinker, your AI assistant. I can help with research, coding, data analysis, and much more. What would you like to work on today?"
    if "help" in msg:
        return "I can help you with:\n\n- **Research**: Find and synthesize information from the web\n- **Coding**: Write, debug, and refactor code\n- **Analysis**: Analyze data and create visualizations\n- **Writing**: Create reports, documentation, and content\n- **Automation**: Run commands and automate tasks\n\nJust describe what you need and I'll get started!"
    return f"I understand you're asking about: *{message}*\n\nThis is a demo mode response. In the full version, I would use my tools (search, browser, code execution, file editing) to help you accomplish this task.\n\nWould you like me to demonstrate any specific capability?"
