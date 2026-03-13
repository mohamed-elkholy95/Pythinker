"""Tests for PDF renderer factory wiring."""

from __future__ import annotations

from types import SimpleNamespace

from app.infrastructure.external.pdf.playwright_pdf_renderer import PlaywrightPdfRenderer
from app.interfaces.dependencies import build_pdf_renderer_from_settings


def test_build_pdf_renderer_from_settings_normalizes_sandbox_address_for_reportlab() -> None:
    settings = SimpleNamespace(
        telegram_pdf_renderer="reportlab",
        telegram_pdf_renderer_timeout_ms=20000,
        sandbox_address="sandbox",
    )

    renderer = build_pdf_renderer_from_settings(settings)

    assert renderer._mermaid is not None
    assert str(renderer._mermaid._client.base_url).rstrip("/") == "http://sandbox:8080"


def test_build_pdf_renderer_from_settings_passes_sandbox_address_to_playwright() -> None:
    settings = SimpleNamespace(
        telegram_pdf_renderer="playwright",
        telegram_pdf_renderer_timeout_ms=20000,
        sandbox_address="sandbox",
    )

    renderer = build_pdf_renderer_from_settings(settings)

    assert isinstance(renderer, PlaywrightPdfRenderer)
    assert renderer._mermaid is not None
    assert str(renderer._mermaid._client.base_url).rstrip("/") == "http://sandbox:8080"


def test_build_pdf_renderer_from_settings_uses_first_static_sandbox_address() -> None:
    settings = SimpleNamespace(
        telegram_pdf_renderer="playwright",
        telegram_pdf_renderer_timeout_ms=20000,
        sandbox_address="http://sandbox-a:8081,sandbox-b",
    )

    renderer = build_pdf_renderer_from_settings(settings)

    assert isinstance(renderer, PlaywrightPdfRenderer)
    assert renderer._mermaid is not None
    assert str(renderer._mermaid._client.base_url).rstrip("/") == "http://sandbox-a:8081"
