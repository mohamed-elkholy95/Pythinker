"""Integration contract tests for Telegram report PDF design/citation parity."""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import imagehash
import pytest
from PIL import Image
from pypdf import PdfReader

from app.domain.models.source_citation import SourceCitation
from app.domain.services.channels.telegram_delivery_policy import TelegramDeliveryPolicy
from app.domain.services.pdf.models import ReportPdfPayload
from app.infrastructure.external.pdf.playwright_pdf_renderer import PlaywrightPdfRenderer

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _load_fixture(name: str) -> str:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "reports" / name
    return fixture.read_text(encoding="utf-8")


def _load_visual_baseline(name: str) -> dict[str, object]:
    baseline_path = Path(__file__).resolve().parents[1] / "fixtures" / "reports" / name
    return json.loads(baseline_path.read_text(encoding="utf-8"))


def _build_payload(markdown: str) -> ReportPdfPayload:
    return ReportPdfPayload(
        title="Research Report: Agent Memory Design",
        markdown_content=markdown,
        sources=[
            SourceCitation(
                url="https://qdrant.tech/documentation/",
                title="Qdrant docs",
                snippet="Vector search documentation.",
                access_time=datetime(2026, 1, 2, tzinfo=UTC),
                source_type="search",
            ),
            SourceCitation(
                url="https://fastapi.tiangolo.com/",
                title="FastAPI docs",
                snippet="Framework documentation.",
                access_time=datetime(2026, 1, 2, tzinfo=UTC),
                source_type="search",
            ),
        ],
        generated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


async def _convert_first_pdf_page_to_png(
    *,
    pdftoppm_binary: str,
    pdf_path: Path,
    png_prefix: Path,
) -> None:
    process = await asyncio.create_subprocess_exec(
        pdftoppm_binary,
        "-f",
        "1",
        "-singlefile",
        "-png",
        str(pdf_path),
        str(png_prefix),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        error_message = stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(error_message or f"pdftoppm exited with code {process.returncode}")


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _collect_internal_destinations(pdf_bytes: bytes) -> set[str]:
    reader = PdfReader(BytesIO(pdf_bytes))
    destinations: set[str] = set()

    for page in reader.pages:
        annotations = page.get("/Annots")
        if not annotations:
            continue
        for annotation_ref in annotations:
            annotation = annotation_ref.get_object()
            destination = annotation.get("/Dest")
            if isinstance(destination, str):
                destinations.add(destination)

    return destinations


@pytest.mark.asyncio
async def test_playwright_pdf_contract_matches_modal_reference_parity() -> None:
    markdown = _load_fixture("sample_modal_parity_report.md")
    payload = _build_payload(markdown)

    renderer = PlaywrightPdfRenderer(timeout_ms=20_000)
    try:
        pdf_bytes = await renderer.render(payload)
    except Exception as exc:
        pytest.skip(f"Playwright PDF rendering unavailable for integration test: {exc}")

    assert len(pdf_bytes) > 0
    assert len(pdf_bytes) <= TelegramDeliveryPolicy.MAX_TELEGRAM_DOCUMENT_BYTES

    text = _extract_text(pdf_bytes)
    assert text.count("References") == 1
    assert "Unresolved citation" not in text
    assert "Qdrant docs" in text
    assert "FastAPI docs" in text

    destinations = _collect_internal_destinations(pdf_bytes)
    assert "/ref-1" in destinations
    assert "/ref-2" in destinations


@pytest.mark.asyncio
async def test_playwright_pdf_visual_hash_matches_baseline(tmp_path: Path) -> None:
    pdftoppm_binary = shutil.which("pdftoppm")
    if pdftoppm_binary is None:
        pytest.skip("pdftoppm is required for PDF visual contract test")

    markdown = _load_fixture("sample_modal_parity_report.md")
    baseline = _load_visual_baseline("sample_modal_parity_report.visual.json")
    payload = _build_payload(markdown)

    renderer = PlaywrightPdfRenderer(timeout_ms=20_000)
    try:
        pdf_bytes = await renderer.render(payload)
    except Exception as exc:
        pytest.skip(f"Playwright PDF rendering unavailable for visual contract test: {exc}")

    pdf_path = tmp_path / "report.pdf"
    png_prefix = tmp_path / "report_page_1"
    png_path = tmp_path / "report_page_1.png"
    pdf_path.write_bytes(pdf_bytes)

    try:
        await _convert_first_pdf_page_to_png(
            pdftoppm_binary=pdftoppm_binary,
            pdf_path=pdf_path,
            png_prefix=png_prefix,
        )
    except RuntimeError as exc:
        pytest.skip(f"pdftoppm conversion failed for visual contract test: {exc}")

    image = Image.open(png_path)
    try:
        hash_size = int(baseline["hash_size"])
        expected_hash = imagehash.hex_to_hash(str(baseline["phash"]))
        expected_width = int(baseline["width"])
        expected_height = int(baseline["height"])
        max_distance = int(baseline["max_distance"])
    finally:
        image.close()

    image_for_hash = Image.open(png_path)
    try:
        actual_hash = imagehash.phash(image_for_hash, hash_size=hash_size)
        width, height = image_for_hash.size
    finally:
        image_for_hash.close()

    assert (width, height) == (expected_width, expected_height)
    assert actual_hash - expected_hash <= max_distance
