"""Mermaid diagram pre-rendering for PDF reports.

Detects ```mermaid code blocks in markdown, renders them to PNG via the
sandbox's mmdc CLI, and returns the processed markdown with image data
for embedding in ReportLab or Playwright PDF renderers.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_MERMAID_BLOCK_RE = re.compile(
    r"```[Mm]ermaid\s*\n(.*?)```",
    re.DOTALL,
)

# Timeout for the full mmdc render cycle (write + exec + download)
_RENDER_TIMEOUT_SECONDS = 20.0

# mmdc CLI command template
_MMDC_CMD = "mmdc -i {input} -o {output} -t neutral -b white -w 700 -q -p /opt/mermaid-puppeteer.json"


@dataclass
class MermaidBlock:
    """A detected mermaid code block with its source and placeholder key."""

    source: str
    placeholder: str
    key: str


def extract_mermaid_blocks(markdown: str) -> list[MermaidBlock]:
    """Extract all ```mermaid blocks from markdown.

    Returns list of MermaidBlock with source content and unique placeholder keys.
    Non-mermaid code blocks are ignored.
    """
    blocks: list[MermaidBlock] = []
    for match in _MERMAID_BLOCK_RE.finditer(markdown):
        source = match.group(1).strip()
        if not source:
            continue
        key = hashlib.md5(source.encode()).hexdigest()[:8]  # noqa: S324
        placeholder = f"<!--MERMAID:{key}-->"
        blocks.append(MermaidBlock(source=source, placeholder=placeholder, key=key))
    return blocks


class MermaidPreprocessor:
    """Pre-renders Mermaid code blocks to PNG via sandbox mmdc CLI.

    Architecture:
        1. Extract ```mermaid blocks from markdown
        2. For each block: write .mmd file to sandbox /tmp/
        3. Execute mmdc via sandbox shell API to produce .png
        4. Download rendered PNG via sandbox file API
        5. Replace mermaid block with placeholder in markdown
        6. Return (processed_markdown, {key: png_bytes}) dict

    Graceful fallback: if any step fails for a block, the original
    code block is preserved unchanged in the output.
    """

    def __init__(self, sandbox_base_url: str) -> None:
        self._sandbox_url = sandbox_base_url.rstrip("/")

    async def preprocess_markdown(self, markdown: str) -> tuple[str, dict[str, bytes]]:
        """Process markdown, rendering mermaid blocks to PNG.

        Returns:
            Tuple of (processed_markdown, images_dict).
            processed_markdown has mermaid blocks replaced with <!--MERMAID:key-->
            images_dict maps key -> PNG bytes for each successfully rendered block.
            Failed blocks remain as original ```mermaid code blocks.
        """
        blocks = extract_mermaid_blocks(markdown)
        if not blocks:
            return markdown, {}

        images: dict[str, bytes] = {}
        processed = markdown

        for block in blocks:
            try:
                png_bytes = await self._render_block(block)
                if png_bytes and len(png_bytes) > 100:  # sanity check
                    images[block.key] = png_bytes
                    # Replace the full ```mermaid...``` block with placeholder
                    processed = _MERMAID_BLOCK_RE.sub(
                        lambda m, b=block, s=block.source: b.placeholder if m.group(1).strip() == s else m.group(0),
                        processed,
                        count=1,
                    )
            except Exception:
                logger.warning(
                    "Mermaid render failed for block %s, keeping raw code",
                    block.key,
                    exc_info=True,
                )

        return processed, images

    async def _render_block(self, block: MermaidBlock) -> bytes | None:
        """Render a single mermaid block to PNG via sandbox APIs.

        Steps:
            1. POST /api/v1/file/write — write .mmd source to /tmp/
            2. POST /api/v1/shell/exec — run mmdc to produce .png
            3. POST /api/v1/shell/wait — wait for mmdc to finish
            4. GET  /api/v1/file/download — retrieve PNG bytes

        Returns PNG bytes or None on failure.
        """
        input_path = f"/tmp/mermaid_{block.key}.mmd"
        output_path = f"/tmp/mermaid_{block.key}.png"

        async with httpx.AsyncClient(timeout=httpx.Timeout(_RENDER_TIMEOUT_SECONDS)) as client:
            # 1. Write mermaid source file
            resp = await client.post(
                f"{self._sandbox_url}/api/v1/file/write",
                json={"path": input_path, "content": block.source},
            )
            if resp.status_code != 200:
                logger.warning("Mermaid file write failed: HTTP %d", resp.status_code)
                return None

            # 2. Execute mmdc
            cmd = _MMDC_CMD.format(input=input_path, output=output_path)
            resp = await client.post(
                f"{self._sandbox_url}/api/v1/shell/exec",
                json={"id": f"mermaid_{block.key}", "exec_dir": "/tmp", "command": cmd},
            )
            if resp.status_code != 200:
                logger.warning("Mermaid mmdc exec failed: HTTP %d", resp.status_code)
                return None

            # 3. Wait for mmdc to finish
            resp = await client.post(
                f"{self._sandbox_url}/api/v1/shell/wait",
                json={"id": f"mermaid_{block.key}", "seconds": 15},
            )
            if resp.status_code != 200:
                logger.warning("Mermaid mmdc wait failed: HTTP %d", resp.status_code)
                return None

            data = resp.json()
            returncode = data.get("data", {}).get("returncode")
            if returncode is not None and returncode != 0:
                output = data.get("data", {}).get("output", "")
                logger.warning("mmdc exited with code %d: %s", returncode, output[:200])
                return None

            # 4. Download rendered PNG
            resp = await client.get(
                f"{self._sandbox_url}/api/v1/file/download",
                params={"path": output_path},
            )
            if resp.status_code != 200:
                logger.warning("Mermaid PNG download failed: HTTP %d", resp.status_code)
                return None

            png_bytes = resp.content
            logger.info(
                "Mermaid block %s rendered to PNG (%d bytes)",
                block.key,
                len(png_bytes),
            )
            return png_bytes
