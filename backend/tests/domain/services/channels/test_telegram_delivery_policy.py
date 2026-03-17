"""Tests for Telegram PDF delivery policy."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.models.channel import ChannelType, InboundMessage
from app.domain.models.source_citation import SourceCitation
from app.domain.services.channels.telegram_delivery_policy import (
    TelegramDeliveryPolicy,
    TelegramPdfRateLimiter,
)
from app.domain.services.pdf.models import ReportPdfPayload
from app.domain.services.pdf.pdf_renderer import PdfReportRenderer


class _FakeReportEvent:
    type = "report"

    def __init__(self, title: str, content: str, sources=None) -> None:
        self.title = title
        self.content = content
        self.sources = sources


class _FakeMessageEvent:
    type = "message"
    role = "assistant"

    def __init__(self, message: str) -> None:
        self.message = message


class _DenyAllLimiter(TelegramPdfRateLimiter):
    async def allow(self, key: str, limit_per_minute: int) -> bool:
        return False


class _StubPdfRenderer(PdfReportRenderer):
    def __init__(self) -> None:
        self.payloads: list[ReportPdfPayload] = []

    async def render(self, payload: ReportPdfPayload) -> bytes:
        self.payloads.append(payload)
        return b"%PDF-1.4 stub"


def _inbound(content: str = "hello") -> InboundMessage:
    return InboundMessage(
        channel=ChannelType.TELEGRAM,
        sender_id="tg-user",
        chat_id="tg-chat",
        content=content,
    )


def _cleanup_media(messages) -> None:
    for msg in messages:
        for media in msg.media:
            path = Path(media.url)
            if path.exists():
                path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_report_threshold_triggers_pdf_delivery(tmp_path: Path) -> None:
    policy = TelegramDeliveryPolicy(
        report_min_chars=50,
        message_min_chars=100,
        temp_dir=tmp_path,
    )
    event = _FakeReportEvent("Report", "A" * 60)

    messages = await policy.build_for_event(event, _inbound(), user_id="user-1")
    try:
        assert len(messages) == 1
        outbound = messages[0]
        assert outbound.media
        assert outbound.media[0].mime_type == "application/pdf"
        assert outbound.metadata["delivery_mode"] == "pdf_only"
        assert outbound.content == ""
        assert "caption" not in outbound.metadata
    finally:
        _cleanup_media(messages)


@pytest.mark.asyncio
async def test_message_threshold_stays_text_delivery(tmp_path: Path) -> None:
    policy = TelegramDeliveryPolicy(
        report_min_chars=200,
        message_min_chars=80,
        temp_dir=tmp_path,
    )
    event = _FakeMessageEvent("B" * 80)

    messages = await policy.build_for_event(event, _inbound(), user_id="user-2")
    assert len(messages) == 1
    assert messages[0].media == []
    assert messages[0].metadata["delivery_mode"] == "text"


@pytest.mark.asyncio
async def test_short_text_stays_inline() -> None:
    policy = TelegramDeliveryPolicy(report_min_chars=200, message_min_chars=300)
    event = _FakeReportEvent("Short", "Tiny content")

    messages = await policy.build_for_event(event, _inbound(), user_id="user-3")

    assert len(messages) == 1
    assert messages[0].media == []
    assert "Tiny content" in messages[0].content


@pytest.mark.asyncio
async def test_borderline_content_returns_inline_keyboard_offer() -> None:
    policy = TelegramDeliveryPolicy(report_min_chars=200, message_min_chars=100)
    event = _FakeMessageEvent("C" * 85)  # within 20% of threshold

    messages = await policy.build_for_event(event, _inbound(), user_id="user-4")

    assert len(messages) == 1
    outbound = messages[0]
    assert outbound.media == []
    assert "reply_markup" not in outbound.metadata
    assert outbound.metadata["delivery_mode"] == "text"


@pytest.mark.asyncio
async def test_message_force_pdf_still_generates_document(tmp_path: Path) -> None:
    policy = TelegramDeliveryPolicy(
        report_min_chars=200,
        message_min_chars=10_000,
        temp_dir=tmp_path,
    )
    event = _FakeMessageEvent("Force PDF for this response.")

    messages = await policy.build_for_event(event, _inbound(), user_id="user-force", force_pdf=True)
    try:
        assert len(messages) == 1
        assert messages[0].media
        assert messages[0].metadata["delivery_mode"] == "pdf_only"
    finally:
        _cleanup_media(messages)


@pytest.mark.asyncio
async def test_generation_failure_falls_back_to_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy = TelegramDeliveryPolicy(report_min_chars=50, message_min_chars=200, temp_dir=tmp_path)
    event = _FakeReportEvent("Broken", "D" * 100)

    async def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(policy, "_render_pdf_attachment", _raise)

    messages = await policy.build_for_event(event, _inbound(), user_id="user-5")

    assert len(messages) == 1
    assert messages[0].media == []
    assert messages[0].metadata["delivery_mode"] == "text"


@pytest.mark.asyncio
async def test_caption_output_respects_max_chars(tmp_path: Path) -> None:
    policy = TelegramDeliveryPolicy(
        report_min_chars=10,
        message_min_chars=200,
        caption_max_chars=120,
        pdf_caption_enabled=True,
        temp_dir=tmp_path,
    )
    event = _FakeReportEvent("Long", "Sentence one. Sentence two. Sentence three. " * 10)

    messages = await policy.build_for_event(event, _inbound(), user_id="user-6")
    try:
        assert len(messages) == 1
        assert len(messages[0].content) <= 120
    finally:
        _cleanup_media(messages)


@pytest.mark.asyncio
async def test_sanitization_handles_malformed_content(tmp_path: Path) -> None:
    policy = TelegramDeliveryPolicy(report_min_chars=10, message_min_chars=200, temp_dir=tmp_path)
    event = _FakeReportEvent("Malformed", "Text with \x00 control and [broken link](http://example")

    messages = await policy.build_for_event(event, _inbound(), user_id="user-7")
    try:
        assert len(messages) == 1
        assert "\x00" not in messages[0].content
    finally:
        _cleanup_media(messages)


@pytest.mark.asyncio
async def test_async_threshold_returns_ack_and_document(tmp_path: Path) -> None:
    policy = TelegramDeliveryPolicy(
        report_min_chars=50,
        message_min_chars=200,
        async_threshold_chars=120,
        pdf_progress_ack_enabled=True,
        temp_dir=tmp_path,
    )
    sources = [
        SourceCitation(
            url="https://example.com",
            title="Example",
            snippet=None,
            access_time=datetime.now(UTC),
            source_type="search",
        )
    ]
    event = _FakeReportEvent("Async", "E" * 200, sources=sources)

    messages = await policy.build_for_event(event, _inbound(), user_id="user-8")
    try:
        assert len(messages) == 2
        assert "Generating PDF report" in messages[0].content
        assert messages[1].media
    finally:
        _cleanup_media(messages)


@pytest.mark.asyncio
async def test_async_threshold_without_progress_ack_returns_document_only(tmp_path: Path) -> None:
    policy = TelegramDeliveryPolicy(
        report_min_chars=50,
        message_min_chars=200,
        async_threshold_chars=120,
        temp_dir=tmp_path,
    )
    event = _FakeReportEvent("Async", "E" * 200)

    messages = await policy.build_for_event(event, _inbound(), user_id="user-8b")
    try:
        assert len(messages) == 1
        assert messages[0].media
        assert messages[0].content == ""
    finally:
        _cleanup_media(messages)


@pytest.mark.asyncio
async def test_rate_limit_exceeded_falls_back_to_text() -> None:
    policy = TelegramDeliveryPolicy(
        report_min_chars=10,
        message_min_chars=10,
        rate_limiter=_DenyAllLimiter(),
    )
    event = _FakeReportEvent("Rate Limited", "F" * 100)

    messages = await policy.build_for_event(event, _inbound(), user_id="user-9")

    assert len(messages) == 1
    assert messages[0].media == []
    assert messages[0].metadata["delivery_mode"] == "text"


@pytest.mark.asyncio
async def test_strict_long_text_mode_rate_limit_returns_short_retry_message() -> None:
    policy = TelegramDeliveryPolicy(
        report_min_chars=10,
        message_min_chars=10,
        rate_limiter=_DenyAllLimiter(),
        force_long_text_pdf=True,
    )
    long_content = "Long output " * 30
    event = _FakeReportEvent("Rate Limited", long_content)

    messages = await policy.build_for_event(event, _inbound(), user_id="user-10")

    assert len(messages) == 1
    assert messages[0].media == []
    assert messages[0].metadata["delivery_mode"] == "text"
    assert messages[0].metadata["pdf_required"] is True
    assert "rate-limited" in messages[0].content.lower()
    assert long_content not in messages[0].content


@pytest.mark.asyncio
async def test_strict_long_text_mode_render_failure_returns_short_retry_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = TelegramDeliveryPolicy(
        report_min_chars=10,
        message_min_chars=10,
        temp_dir=tmp_path,
        force_long_text_pdf=True,
    )
    long_content = "Failure output " * 30
    event = _FakeReportEvent("Broken", long_content)

    async def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(policy, "_render_pdf_attachment", _raise)

    messages = await policy.build_for_event(event, _inbound(), user_id="user-11")

    assert len(messages) == 1
    assert messages[0].media == []
    assert messages[0].metadata["delivery_mode"] == "text"
    assert messages[0].metadata["pdf_required"] is True
    assert "try /pdf again" in messages[0].content.lower()
    assert long_content not in messages[0].content


@pytest.mark.asyncio
async def test_custom_pdf_renderer_is_used_for_pdf_generation(tmp_path: Path) -> None:
    renderer = _StubPdfRenderer()
    policy = TelegramDeliveryPolicy(
        report_min_chars=10,
        message_min_chars=10,
        temp_dir=tmp_path,
        pdf_renderer=renderer,
    )
    event = _FakeReportEvent("Custom Renderer", "G" * 120)

    messages = await policy.build_for_event(event, _inbound(), user_id="user-renderer")
    try:
        assert len(messages) == 1
        assert messages[0].media
        assert renderer.payloads
        assert renderer.payloads[0].title == "Custom Renderer"
        assert renderer.payloads[0].markdown_content == "G" * 120
    finally:
        _cleanup_media(messages)
