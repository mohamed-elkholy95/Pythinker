"""Tests for Playwright PDF renderer behavior and fallbacks."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.prometheus_metrics import (
    reset_all_metrics,
    telegram_pdf_citation_integrity_total,
    telegram_pdf_renderer_fallback_total,
    telegram_pdf_renderer_invocations_total,
    telegram_pdf_renderer_success_total,
)
from app.domain.models.source_citation import SourceCitation
from app.domain.services.pdf.models import ReportPdfPayload
from app.domain.services.pdf.pdf_renderer import PdfReportRenderer
from app.infrastructure.external.pdf.playwright_pdf_renderer import (
    PlaywrightPdfRenderer,
    _decorate_reference_ids,
)


class _FallbackRenderer(PdfReportRenderer):
    def __init__(self) -> None:
        self.called = False

    async def render(self, payload: ReportPdfPayload) -> bytes:
        self.called = True
        return b"fallback-pdf"


@pytest.fixture(autouse=True)
def _reset_metrics_between_tests() -> None:
    reset_all_metrics()
    yield
    reset_all_metrics()


@pytest.mark.asyncio
async def test_playwright_renderer_uses_fallback_when_primary_render_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    fallback = _FallbackRenderer()
    renderer = PlaywrightPdfRenderer(timeout_ms=1_000, fallback_renderer=fallback)

    async def _raise(_html: str) -> bytes:
        raise RuntimeError("playwright down")

    monkeypatch.setattr(renderer, "_render_with_playwright", _raise)

    payload = ReportPdfPayload(
        title="Report",
        markdown_content="# Title\n\nBody [1]",
        sources=[],
        generated_at=datetime.now(UTC),
    )

    pdf = await renderer.render(payload)

    assert pdf == b"fallback-pdf"
    assert fallback.called is True
    assert telegram_pdf_renderer_invocations_total.get({"renderer": "playwright"}) == 1
    assert telegram_pdf_renderer_success_total.get({"renderer": "playwright"}) == 0
    assert (
        telegram_pdf_renderer_fallback_total.get(
            {"from_renderer": "playwright", "to_renderer": "fallbackrenderer", "reason": "runtimeerror"}
        )
        == 1
    )


@pytest.mark.asyncio
async def test_playwright_renderer_emits_linked_citations_and_reference_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    renderer = PlaywrightPdfRenderer(timeout_ms=1_000)
    captured_html: dict[str, str] = {}

    async def _capture(html: str) -> bytes:
        captured_html["value"] = html
        return b"pdf-bytes"

    monkeypatch.setattr(renderer, "_render_with_playwright", _capture)

    payload = ReportPdfPayload(
        title="Parity",
        markdown_content="# Report\n\nClaim [1].",
        sources=[
            SourceCitation(
                url="https://example.com/source",
                title="Source",
                snippet=None,
                access_time=datetime.now(UTC),
                source_type="search",
            )
        ],
        generated_at=datetime.now(UTC),
    )

    pdf = await renderer.render(payload)

    assert pdf == b"pdf-bytes"
    html = captured_html["value"]
    assert 'href="#ref-1"' in html
    assert ">[1]</a>" in html
    assert 'id="ref-1"' in html
    assert telegram_pdf_renderer_invocations_total.get({"renderer": "playwright"}) == 1
    assert telegram_pdf_renderer_success_total.get({"renderer": "playwright"}) == 1
    assert telegram_pdf_citation_integrity_total.get({"status": "ok"}) == 1


@pytest.mark.asyncio
async def test_playwright_renderer_records_unresolved_citation_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    renderer = PlaywrightPdfRenderer(timeout_ms=1_000)

    async def _capture(_html: str) -> bytes:
        return b"pdf-bytes"

    monkeypatch.setattr(renderer, "_render_with_playwright", _capture)

    payload = ReportPdfPayload(
        title="Parity",
        markdown_content="# Report\n\nClaim [2].\n\n## References\n\n1. https://example.com",
        sources=[],
        generated_at=datetime.now(UTC),
    )

    pdf = await renderer.render(payload)

    assert pdf == b"pdf-bytes"
    assert telegram_pdf_citation_integrity_total.get({"status": "unresolved"}) == 1


@pytest.mark.asyncio
async def test_playwright_renderer_formats_github_alert_blockquotes(monkeypatch: pytest.MonkeyPatch) -> None:
    renderer = PlaywrightPdfRenderer(timeout_ms=1_000)
    captured_html: dict[str, str] = {}

    async def _capture(html: str) -> bytes:
        captured_html["value"] = html
        return b"pdf-bytes"

    monkeypatch.setattr(renderer, "_render_with_playwright", _capture)

    payload = ReportPdfPayload(
        title="Alerts",
        markdown_content="# Report\n\n> [!IMPORTANT]\n> Keep this visible.\n\n> [!WARNING]\n> Double-check the data.",
        sources=[],
        generated_at=datetime.now(UTC),
    )

    pdf = await renderer.render(payload)

    assert pdf == b"pdf-bytes"
    html = captured_html["value"]
    assert 'class="alert alert-important"' in html
    assert 'class="alert alert-warning"' in html
    assert "Important" in html
    assert "Warning" in html
    assert "[!IMPORTANT]" not in html
    assert "[!WARNING]" not in html


def test_decorate_reference_ids_assigns_anchors_to_reference_items() -> None:
    html = """
    <h2>References</h2>
    <ol>
      <li>One</li>
      <li>Two</li>
    </ol>
    """

    rendered = _decorate_reference_ids(html)

    assert 'id="ref-1"' in rendered
    assert 'id="ref-2"' in rendered


def test_decorate_reference_ids_assigns_anchors_to_bracket_reference_lines() -> None:
    html = """
    <h2>References</h2>
    <p>[1] One source
[2] Two source</p>
    """

    rendered = _decorate_reference_ids(html)

    assert 'id="ref-1"' in rendered
    assert 'id="ref-2"' in rendered
