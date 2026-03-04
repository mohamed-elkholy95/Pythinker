#!/usr/bin/env python3
"""Generate/update visual baseline hash for Telegram PDF design contract tests."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import imagehash
from PIL import Image

# Ensure backend root is importable when script runs as `python scripts/...`.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if TYPE_CHECKING:
    from app.domain.services.pdf.models import ReportPdfPayload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=str,
        default="sample_modal_parity_report.md",
        help="Markdown fixture filename under tests/fixtures/reports",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="sample_modal_parity_report.visual.json",
        help="Output baseline filename under tests/fixtures/reports",
    )
    parser.add_argument(
        "--hash-size",
        type=int,
        default=16,
        help="Perceptual hash size for imagehash.phash",
    )
    parser.add_argument(
        "--max-distance",
        type=int,
        default=12,
        help="Allowed hash distance threshold stored in baseline file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated baseline JSON without writing output file",
    )
    return parser.parse_args()


def _build_payload(markdown: str) -> ReportPdfPayload:
    from app.domain.models.source_citation import SourceCitation
    from app.domain.services.pdf.models import ReportPdfPayload

    fixed_time = datetime(2026, 1, 2, tzinfo=UTC)
    return ReportPdfPayload(
        title="Research Report: Agent Memory Design",
        markdown_content=markdown,
        sources=[
            SourceCitation(
                url="https://qdrant.tech/documentation/",
                title="Qdrant docs",
                snippet="Vector search documentation.",
                access_time=fixed_time,
                source_type="search",
            ),
            SourceCitation(
                url="https://fastapi.tiangolo.com/",
                title="FastAPI docs",
                snippet="Framework documentation.",
                access_time=fixed_time,
                source_type="search",
            ),
        ],
        generated_at=fixed_time,
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
        message = stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(message or f"pdftoppm exited with code {process.returncode}")


async def _generate_baseline(
    *,
    fixture_path: Path,
    output_path: Path,
    hash_size: int,
    max_distance: int,
    dry_run: bool,
) -> None:
    from app.infrastructure.external.pdf.playwright_pdf_renderer import PlaywrightPdfRenderer

    pdftoppm_binary = shutil.which("pdftoppm")
    if pdftoppm_binary is None:
        raise RuntimeError("pdftoppm not found in PATH. Install poppler-utils first.")

    markdown = fixture_path.read_text(encoding="utf-8")
    payload = _build_payload(markdown)
    renderer = PlaywrightPdfRenderer(timeout_ms=20_000)
    pdf_bytes = await renderer.render(payload)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        pdf_path = temp_root / "report.pdf"
        png_prefix = temp_root / "report_page_1"
        png_path = temp_root / "report_page_1.png"
        pdf_path.write_bytes(pdf_bytes)

        await _convert_first_pdf_page_to_png(
            pdftoppm_binary=pdftoppm_binary,
            pdf_path=pdf_path,
            png_prefix=png_prefix,
        )

        with Image.open(png_path) as image:
            width, height = image.size
            phash = str(imagehash.phash(image, hash_size=hash_size))

    baseline = {
        "hash_size": hash_size,
        "phash": phash,
        "width": width,
        "height": height,
        "max_distance": max_distance,
    }
    baseline_json = json.dumps(baseline, indent=2) + "\n"

    if dry_run:
        sys.stdout.write(baseline_json)
        return

    output_path.write_text(baseline_json, encoding="utf-8")
    sys.stdout.write(f"Wrote visual baseline: {output_path}\n")
    sys.stdout.write(baseline_json)


def main() -> None:
    args = _parse_args()
    fixtures_dir = BACKEND_ROOT / "tests" / "fixtures" / "reports"
    fixture_path = fixtures_dir / args.fixture
    output_path = fixtures_dir / args.output

    if not fixture_path.exists():
        raise SystemExit(f"Fixture file not found: {fixture_path}")

    asyncio.run(
        _generate_baseline(
            fixture_path=fixture_path,
            output_path=output_path,
            hash_size=args.hash_size,
            max_distance=args.max_distance,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
