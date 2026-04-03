from app.domain.models.event import MessageEvent, PartialResultEvent
from app.interfaces.schemas.event import EventMapper, PartialResultSSEEvent
from app.interfaces.schemas.session import ListSessionItem


async def test_event_mapper_strips_leaked_tool_call_markup_from_message_events() -> None:
    event = MessageEvent(
        role="assistant",
        message=(
            "Got it! I'll research the latest AI/ML engineering roadmaps and best practices to create "
            'a comprehensive report for you. <tool_call> {"tool": "Browser", "params": {"task": "research", '
            '"url": "https://roadmap.sh/ai-engineer", "objective": "Explore the roadmap"}}'
        ),
    )

    sse_event = await EventMapper.event_to_sse_event(event)

    assert sse_event.event == "message"
    assert "<tool_call>" not in sse_event.data.content
    assert '"tool": "Browser"' not in sse_event.data.content
    assert sse_event.data.content.endswith("for you.")


def test_list_session_item_strips_leaked_tool_call_markup_from_latest_message() -> None:
    item = ListSessionItem(
        session_id="session-1",
        status="running",
        unread_message_count=0,
        latest_message=(
            'Got it! I will research the topic. <tool_call>{"tool":"Browser","params":{"task":"research"}}</tool_call>'
        ),
    )

    assert item.latest_message == "Got it! I will research the topic."


async def test_event_mapper_strips_leaked_browser_status_prefix_from_message_events() -> None:
    event = MessageEvent(
        role="assistant",
        message=(
            "Got it! I'll research best practices for professional code setup and investigate OpenCode to create "
            "a comprehensive report. **[Sandbox Browser: Navigating to research sources for."
        ),
    )

    sse_event = await EventMapper.event_to_sse_event(event)

    assert sse_event.event == "message"
    assert "Sandbox Browser:" not in sse_event.data.content
    assert "Navigating to research sources for." not in sse_event.data.content
    assert sse_event.data.content.startswith("Got it! I'll research best practices")


def test_list_session_item_strips_leaked_browser_status_prefix_from_latest_message() -> None:
    item = ListSessionItem(
        session_id="session-2",
        status="running",
        unread_message_count=0,
        latest_message=(
            "Got it! I'll research best practices for professional code setup. **[Sandbox Browser: Navigating to "
            "research sources for."
        ),
    )

    assert item.latest_message == "Got it! I'll research best practices for professional code setup."


async def test_event_mapper_strips_other_internal_status_prefixes_from_message_events() -> None:
    event = MessageEvent(
        role="assistant",
        message="Got it! I will analyze the issue. [SYSTEM NOTE: Top search result URLs are being previewed in the background.",
    )

    sse_event = await EventMapper.event_to_sse_event(event)

    assert sse_event.event == "message"
    assert "SYSTEM NOTE:" not in sse_event.data.content
    assert "Top search result URLs are being previewed in the background." not in sse_event.data.content
    assert sse_event.data.content == "Got it! I will analyze the issue."


async def test_event_mapper_maps_partial_result_events() -> None:
    event = PartialResultEvent(
        step_index=3,
        step_title="Research",
        headline="Found three relevant sources.",
    )

    sse_event = await EventMapper.event_to_sse_event(event)

    assert isinstance(sse_event, PartialResultSSEEvent)
    assert sse_event.event == "partial_result"
    assert sse_event.data.step_title == "Research"
