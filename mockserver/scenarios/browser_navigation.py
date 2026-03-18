from __future__ import annotations
from typing import AsyncGenerator
from scenarios.engine import eid, ts, tc, delay
import base64

# 1x1 gray pixel PNG
PLACEHOLDER_SCREENSHOT = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
    b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
).decode()


async def run(message: str, session_id: str) -> AsyncGenerator[tuple[str, dict], None]:
    # Extract URL or site from message
    url = "https://example.com"
    msg = message.lower()
    explicit_url = False
    for word in message.split():
        if word.startswith("http"):
            url = word
            explicit_url = True
            break
    if not explicit_url:
        for site in ["github.com", "google.com", "wikipedia.org", "python.org"]:
            if site in msg:
                url = f"https://{site}"
                break

    yield (
        "progress",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "phase": "received",
            "message": "Preparing browser...",
        },
    )
    await delay(0.5)

    step1_id, step2_id = eid(), eid()
    yield (
        "plan",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "steps": [
                {
                    "id": step1_id,
                    "description": f"Navigate to {url}",
                    "status": "pending",
                    "event_id": eid(),
                    "timestamp": ts(),
                },
                {
                    "id": step2_id,
                    "description": "Extract page content",
                    "status": "pending",
                    "event_id": eid(),
                    "timestamp": ts(),
                },
            ],
        },
    )
    await delay(0.3)

    # Step 1: Navigate
    yield (
        "step",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "id": step1_id,
            "description": f"Navigate to {url}",
            "status": "running",
        },
    )
    await delay(0.3)

    tc1 = tc()
    yield (
        "tool",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "tool_call_id": tc1,
            "name": "browser_navigate",
            "status": "calling",
            "function": "browser_navigate",
            "args": {"url": url},
            "display_command": f"Opening {url}",
            "command_category": "browse",
        },
    )
    await delay(1.5)

    yield (
        "tool",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "tool_call_id": tc1,
            "name": "browser_navigate",
            "status": "called",
            "function": "browser_navigate",
            "args": {"url": url},
            "content": {
                "screenshot": PLACEHOLDER_SCREENSHOT,
                "content": f"Page loaded: {url}",
            },
        },
    )
    await delay(0.3)

    yield (
        "step",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "id": step1_id,
            "description": f"Navigate to {url}",
            "status": "completed",
        },
    )
    await delay(0.3)

    # Step 2: Extract content
    yield (
        "step",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "id": step2_id,
            "description": "Extract page content",
            "status": "running",
        },
    )
    await delay(0.3)

    tc2 = tc()
    yield (
        "tool",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "tool_call_id": tc2,
            "name": "browser_get_content",
            "status": "calling",
            "function": "browser_get_content",
            "args": {},
            "display_command": "Extracting page content",
            "command_category": "browse",
        },
    )
    await delay(1.0)

    yield (
        "tool",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "tool_call_id": tc2,
            "name": "browser_get_content",
            "status": "called",
            "function": "browser_get_content",
            "args": {},
            "content": {
                "content": f"# Page Content from {url}\n\nThis is a demo of the browser content extraction feature. In production, the actual page content would be extracted and displayed here.\n\n## Key Elements\n- Page title and metadata\n- Main content area\n- Navigation structure\n- Links and references"
            },
        },
    )
    await delay(0.3)

    yield (
        "step",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "id": step2_id,
            "description": "Extract page content",
            "status": "completed",
        },
    )
    await delay(0.3)

    yield (
        "message",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "content": f"I've navigated to **{url}** and extracted the page content. The browser captured a screenshot and the main content has been parsed for analysis.",
            "role": "assistant",
            "attachments": [],
        },
    )
    await delay(0.2)

    yield (
        "suggestion",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "suggestions": [
                "Extract specific data from the page",
                "Navigate to another page",
                "Save the page content to a file",
            ],
        },
    )

    yield (
        "title",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "title": f"Browse: {url[:40]}",
        },
    )

    yield "done", {"event_id": eid(), "timestamp": ts()}
