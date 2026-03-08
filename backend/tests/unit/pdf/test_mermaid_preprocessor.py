"""Tests for MermaidPreprocessor — mermaid block detection and replacement."""

from __future__ import annotations

import pytest

from app.domain.services.pdf.mermaid_preprocessor import (
    MermaidPreprocessor,
    extract_mermaid_blocks,
)


class TestExtractMermaidBlocks:
    """Unit tests for mermaid block extraction from markdown."""

    def test_extracts_single_mermaid_block(self):
        md = "Hello\n\n```mermaid\ngraph TD\n  A-->B\n```\n\nWorld"
        blocks = extract_mermaid_blocks(md)
        assert len(blocks) == 1
        assert blocks[0].source == "graph TD\n  A-->B"
        assert "<!--MERMAID:" in blocks[0].placeholder

    def test_extracts_multiple_mermaid_blocks(self):
        md = '```mermaid\ngraph LR\n  A-->B\n```\n\nText\n\n```mermaid\npie\n  "A":30\n  "B":70\n```'
        blocks = extract_mermaid_blocks(md)
        assert len(blocks) == 2

    def test_ignores_non_mermaid_code_blocks(self):
        md = "```python\nprint('hello')\n```\n\n```mermaid\ngraph TD\n  A-->B\n```"
        blocks = extract_mermaid_blocks(md)
        assert len(blocks) == 1
        assert blocks[0].source == "graph TD\n  A-->B"

    def test_no_mermaid_blocks(self):
        md = "Just plain markdown\n\n```python\ncode\n```"
        blocks = extract_mermaid_blocks(md)
        assert len(blocks) == 0

    def test_case_insensitive_mermaid_tag(self):
        md = "```Mermaid\ngraph TD\n  A-->B\n```"
        blocks = extract_mermaid_blocks(md)
        assert len(blocks) == 1

    def test_replace_with_placeholder(self):
        md = "Before\n\n```mermaid\ngraph TD\n  A-->B\n```\n\nAfter"
        blocks = extract_mermaid_blocks(md)
        replaced = md
        for b in blocks:
            replaced = replaced.replace(
                f"```mermaid\n{b.source}\n```", b.placeholder
            )
        assert "<!--MERMAID:" in replaced
        assert "```mermaid" not in replaced


class TestMermaidPreprocessor:
    """Tests for the full preprocessor (sandbox interaction mocked)."""

    @pytest.mark.asyncio
    async def test_preprocess_no_mermaid_blocks(self):
        pp = MermaidPreprocessor(sandbox_base_url="http://fake:8080")
        content, images = await pp.preprocess_markdown("No mermaid here")
        assert content == "No mermaid here"
        assert images == {}

    @pytest.mark.asyncio
    async def test_preprocess_returns_original_on_render_failure(self):
        """When sandbox is unavailable, mermaid blocks stay as-is."""
        pp = MermaidPreprocessor(sandbox_base_url="http://unreachable:9999")
        md = "```mermaid\ngraph TD\n  A-->B\n```"
        content, images = await pp.preprocess_markdown(md)
        # Should return original content unchanged (graceful fallback)
        assert "graph TD" in content
        assert images == {}
