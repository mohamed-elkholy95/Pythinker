"""Telegram-specific delivery policy for text vs PDF responses."""

from __future__ import annotations

import hashlib
import html
import logging
import re
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from app.core import prometheus_metrics as pm
from app.domain.models.channel import InboundMessage, MediaAttachment, OutboundMessage
from app.domain.models.source_citation import SourceCitation
from app.domain.utils.markdown_to_pdf import build_pdf_bytes

logger = logging.getLogger(__name__)

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


class TelegramPdfRateLimiter(Protocol):
    """Rate limiter contract for per-user PDF generation throttling."""

    async def allow(self, key: str, limit_per_minute: int) -> bool:
        """Return whether a PDF generation request is allowed."""
        ...


class InMemoryTelegramPdfRateLimiter:
    """Simple sliding-window limiter used when Redis-backed limiter is not injected."""

    def __init__(self) -> None:
        self._events: dict[str, deque[datetime]] = defaultdict(deque)

    async def allow(self, key: str, limit_per_minute: int) -> bool:
        if limit_per_minute <= 0:
            return True
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=1)
        window = self._events[key]
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= limit_per_minute:
            return False
        window.append(now)
        return True


class TelegramDeliveryPolicy:
    """Decides Telegram response delivery mode and generates PDFs when needed."""

    MAX_TELEGRAM_DOCUMENT_BYTES = 50 * 1024 * 1024

    def __init__(
        self,
        *,
        pdf_delivery_enabled: bool = True,
        message_min_chars: int = 3500,
        report_min_chars: int = 2000,
        caption_max_chars: int = 900,
        async_threshold_chars: int = 10000,
        include_toc: bool = True,
        toc_min_sections: int = 3,
        unicode_font: str = "DejaVuSans",
        rate_limit_per_minute: int = 5,
        force_long_text_pdf: bool = False,
        temp_dir: Path | None = None,
        rate_limiter: TelegramPdfRateLimiter | None = None,
    ) -> None:
        self._pdf_delivery_enabled = pdf_delivery_enabled
        self._message_min_chars = message_min_chars
        self._report_min_chars = report_min_chars
        self._caption_max_chars = min(caption_max_chars, 1024)
        self._async_threshold_chars = async_threshold_chars
        self._include_toc = include_toc
        self._toc_min_sections = toc_min_sections
        self._unicode_font = unicode_font
        self._rate_limit_per_minute = rate_limit_per_minute
        self._force_long_text_pdf = force_long_text_pdf
        self._temp_dir = temp_dir or Path("/tmp/pythinker-telegram-pdf")
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limiter = rate_limiter or InMemoryTelegramPdfRateLimiter()

    async def build_for_event(
        self,
        event: object,
        source: InboundMessage,
        *,
        user_id: str,
        force_pdf: bool = False,
    ) -> list[OutboundMessage]:
        """Convert an event into one or more outbound Telegram messages."""
        event_type = getattr(event, "type", "")
        if event_type == "message":
            if getattr(event, "role", "assistant") == "user":
                return []
            title = "Response"
            content = getattr(event, "message", "") or ""
            sources = None
        elif event_type == "report":
            title = (getattr(event, "title", "Report") or "Report").strip()
            content = getattr(event, "content", "") or ""
            sources = getattr(event, "sources", None)
        else:
            return []

        return await self.build_for_content(
            event_type=event_type,
            title=title,
            content=content,
            sources=sources,
            source=source,
            user_id=user_id,
            force_pdf=force_pdf,
        )

    async def build_for_content(
        self,
        *,
        event_type: str,
        title: str,
        content: str,
        source: InboundMessage,
        user_id: str,
        sources: list[SourceCitation] | None = None,
        force_pdf: bool = False,
    ) -> list[OutboundMessage]:
        """Build delivery messages from structured content payload."""
        sanitized_content = self._sanitize_text(content)
        sanitized_title = self._sanitize_text(title) or "Report"

        if not sanitized_content:
            return []

        long_content = self._is_long_content(event_type, sanitized_content)

        if self._is_borderline(event_type, sanitized_content) and not force_pdf and not self._force_long_text_pdf:
            return [
                self._build_text_outbound(
                    event_type,
                    sanitized_title,
                    sanitized_content,
                    source,
                    metadata={
                        "delivery_mode": "text",
                        "reply_markup": {
                            "inline_keyboard": [
                                [{"text": "Get as PDF", "callback_data": "telegram:get_pdf:last"}],
                            ]
                        },
                    },
                )
            ]

        if not self._should_generate_pdf(event_type, sanitized_content, force_pdf=force_pdf):
            return [self._build_text_outbound(event_type, sanitized_title, sanitized_content, source)]

        allow_text_fallback = not (self._force_long_text_pdf and (long_content or force_pdf))

        rate_limit_key = f"telegram_pdf:{user_id}:{source.chat_id}"
        allowed = await self._rate_limiter.allow(rate_limit_key, self._rate_limit_per_minute)
        if not allowed:
            logger.info("telegram.pdf.generate.fallback reason=rate_limit user=%s chat=%s", user_id, source.chat_id)
            if not allow_text_fallback:
                return [self._build_pdf_required_retry_outbound(source, reason="rate_limit")]
            return [
                self._build_text_outbound(
                    event_type,
                    sanitized_title,
                    sanitized_content,
                    source,
                    metadata={"delivery_mode": "text", "pdf_rate_limited": True},
                )
            ]

        if len(sanitized_content) >= self._async_threshold_chars and not force_pdf:
            ack = OutboundMessage(
                channel=source.channel,
                chat_id=source.chat_id,
                content="Generating PDF report...",
                reply_to=source.id,
                metadata={"delivery_mode": "text", "async_pdf": True},
            )
            pdf_outbound = await self._build_pdf_outbound(
                event_type=event_type,
                title=sanitized_title,
                content=sanitized_content,
                source=source,
                sources=sources,
                allow_text_fallback=allow_text_fallback,
            )
            return [ack, pdf_outbound]

        return [
            await self._build_pdf_outbound(
                event_type=event_type,
                title=sanitized_title,
                content=sanitized_content,
                source=source,
                sources=sources,
                allow_text_fallback=allow_text_fallback,
            )
        ]

    def _should_generate_pdf(self, event_type: str, content: str, *, force_pdf: bool) -> bool:
        if not self._pdf_delivery_enabled:
            return False
        if force_pdf:
            return True
        threshold = self._report_min_chars if event_type == "report" else self._message_min_chars
        if len(content) >= threshold:
            return True
        return self._looks_report_like(content)

    def _is_borderline(self, event_type: str, content: str) -> bool:
        threshold = self._report_min_chars if event_type == "report" else self._message_min_chars
        lower_bound = int(threshold * 0.8)
        return lower_bound <= len(content) < threshold

    def _is_long_content(self, event_type: str, content: str) -> bool:
        threshold = self._report_min_chars if event_type == "report" else self._message_min_chars
        return len(content) >= threshold

    def _looks_report_like(self, content: str) -> bool:
        heading_count = len(re.findall(r"(?m)^#{1,6}\s+", content))
        has_citations = bool(re.search(r"(?im)\breferences?\b|\bsources?\b|\[\d+\]", content))
        return heading_count >= 2 and has_citations

    async def _build_pdf_outbound(
        self,
        *,
        event_type: str,
        title: str,
        content: str,
        source: InboundMessage,
        sources: list[SourceCitation] | None,
        allow_text_fallback: bool,
    ) -> OutboundMessage:
        logger.info("telegram.pdf.generate.start chat=%s title=%s", source.chat_id, title)
        try:
            attachment = await self._render_pdf_attachment(title=title, content=content, sources=sources)
            caption = self._build_caption(title=title, content=content)
            pm.telegram_pdf_generated_total.inc()
            pm.telegram_pdf_sent_total.inc()
            logger.info(
                "telegram.pdf.generate.success chat=%s file=%s size_bytes=%s",
                source.chat_id,
                attachment.filename,
                attachment.size_bytes,
            )
            return OutboundMessage(
                channel=source.channel,
                chat_id=source.chat_id,
                content=caption,
                reply_to=source.id,
                media=[attachment],
                metadata={
                    "delivery_mode": "pdf_only",
                    "report_title": title,
                    "parse_mode": "HTML",
                    "caption": caption,
                    "cleanup_media_paths": [attachment.url],
                    "content_hash": self._content_hash(title, content),
                    "event_type": event_type,
                },
            )
        except Exception as exc:
            reason = type(exc).__name__.lower()
            pm.telegram_pdf_generation_failed_total.inc({"reason": reason})
            logger.exception("telegram.pdf.generate.fallback reason=%s title=%s", reason, title)
            if not allow_text_fallback:
                return self._build_pdf_required_retry_outbound(source, reason=reason)
            return self._build_text_outbound(
                event_type,
                title,
                content,
                source,
                metadata={"delivery_mode": "text", "pdf_fallback_reason": reason},
            )

    def _build_pdf_required_retry_outbound(
        self,
        source: InboundMessage,
        *,
        reason: str,
    ) -> OutboundMessage:
        if reason == "rate_limit":
            content = "PDF delivery is temporarily rate-limited. Please wait a minute and try /pdf again."
        else:
            content = "This response requires PDF delivery. PDF generation is temporarily unavailable, try /pdf again."
        return OutboundMessage(
            channel=source.channel,
            chat_id=source.chat_id,
            content=content,
            reply_to=source.id,
            metadata={"delivery_mode": "text", "pdf_required": True, "pdf_fallback_reason": reason},
        )

    async def _render_pdf_attachment(
        self,
        *,
        title: str,
        content: str,
        sources: list[SourceCitation] | None,
    ) -> MediaAttachment:
        pdf_bytes = build_pdf_bytes(
            title=title,
            content=content,
            sources=sources,
            include_toc=self._include_toc,
            toc_min_sections=self._toc_min_sections,
            preferred_font=self._unicode_font,
        )
        filename = self._build_filename(title)
        output_path = self._temp_dir / filename
        output_path.write_bytes(pdf_bytes)
        size_bytes = output_path.stat().st_size
        if size_bytes > self.MAX_TELEGRAM_DOCUMENT_BYTES:
            output_path.unlink(missing_ok=True)
            raise ValueError("pdf_too_large")

        return MediaAttachment(
            url=str(output_path),
            mime_type="application/pdf",
            filename=filename,
            size_bytes=size_bytes,
        )

    def _build_text_outbound(
        self,
        event_type: str,
        title: str,
        content: str,
        source: InboundMessage,
        *,
        metadata: dict[str, object] | None = None,
    ) -> OutboundMessage:
        text = f"## {title}\n\n{content}" if event_type == "report" else content
        payload = {"delivery_mode": "text"}
        if metadata:
            payload.update(metadata)
        return OutboundMessage(
            channel=source.channel,
            chat_id=source.chat_id,
            content=self._sanitize_text(text),
            reply_to=source.id,
            metadata=payload,
        )

    def _build_caption(self, *, title: str, content: str) -> str:
        title_html = html.escape(title.strip() or "Report")
        summary_plain = self._plain_text(content)
        if len(summary_plain) > 1500:
            summary_plain = summary_plain[:1500]

        boilerplate = "Full report attached as PDF."
        budget = self._caption_max_chars
        prefix = f"<b>{title_html}</b>\n\n"
        suffix = f"\n\n{boilerplate}"

        available = max(0, budget - len(prefix) - len(suffix))
        if available == 0:
            return (prefix + suffix).strip()[:budget]

        summary = self._truncate_at_sentence_boundary(summary_plain, available)
        caption = f"{prefix}{html.escape(summary)}{suffix}".strip()
        return caption[:budget]

    @staticmethod
    def _truncate_at_sentence_boundary(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        chunks: list[str] = []
        total = 0
        for sentence in _SENTENCE_BOUNDARY_RE.split(text):
            sentence = sentence.strip()
            if not sentence:
                continue
            delta = len(sentence) + (1 if chunks else 0)
            if total + delta > max_chars:
                break
            chunks.append(sentence)
            total += delta
        if chunks:
            return " ".join(chunks)
        return f"{text[: max(0, max_chars - 3)].rstrip()}..."

    @staticmethod
    def _sanitize_text(text: str) -> str:
        sanitized = _CONTROL_CHARS_RE.sub("", text or "")
        return sanitized.replace("\r\n", "\n").strip()

    @staticmethod
    def _plain_text(markdown: str) -> str:
        text = re.sub(r"```[\s\S]*?```", " ", markdown)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
        text = re.sub(r"#{1,6}\s+", "", text)
        text = re.sub(r"[*_~]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _build_filename(title: str) -> str:
        safe_stem = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower() or "report"
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return f"{safe_stem[:60]}_{timestamp}.pdf"

    @staticmethod
    def _content_hash(title: str, content: str) -> str:
        digest = hashlib.sha256()
        digest.update(title.encode("utf-8", errors="ignore"))
        digest.update(b"\n")
        digest.update(content.encode("utf-8", errors="ignore"))
        return digest.hexdigest()
