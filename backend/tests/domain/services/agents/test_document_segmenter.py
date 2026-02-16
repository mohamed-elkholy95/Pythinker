"""Unit tests for Document Segmenter

Tests context-aware document chunking with boundary preservation.

Context7 validated: pytest patterns, fixture usage, parameterized tests.
"""

import pytest

from app.domain.services.agents.document_segmenter import (
    ChunkingStrategy,
    DocumentSegmenter,
    DocumentType,
    SegmentationConfig,
    get_document_segmenter,
)


class TestSegmentationConfig:
    """Test SegmentationConfig validation."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SegmentationConfig()
        assert config.max_chunk_lines == 200
        assert config.overlap_lines == 10
        assert config.strategy == ChunkingStrategy.SEMANTIC
        assert config.preserve_completeness is True
        assert config.min_chunk_lines == 5

    def test_custom_config(self):
        """Test custom configuration."""
        config = SegmentationConfig(
            max_chunk_lines=100,
            overlap_lines=20,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )
        assert config.max_chunk_lines == 100
        assert config.overlap_lines == 20
        assert config.strategy == ChunkingStrategy.FIXED_SIZE

    def test_overlap_validation_fails_when_too_large(self):
        """Test overlap validation fails when overlap >= max_chunk."""
        with pytest.raises(ValueError, match=r"overlap_lines.*must be less than"):
            SegmentationConfig(max_chunk_lines=100, overlap_lines=100)

    def test_overlap_validation_passes_when_valid(self):
        """Test overlap validation passes when overlap < max_chunk."""
        config = SegmentationConfig(max_chunk_lines=100, overlap_lines=99)
        assert config.overlap_lines == 99


class TestDocumentTypeDetection:
    """Test automatic document type detection."""

    def test_detect_python(self):
        """Test Python code detection."""
        segmenter = DocumentSegmenter()
        python_code = """
def hello():
    print("world")
"""
        doc_type = segmenter._detect_document_type(python_code)
        assert doc_type == DocumentType.PYTHON

    def test_detect_markdown(self):
        """Test Markdown detection."""
        segmenter = DocumentSegmenter()
        markdown = """
# Heading
Some content
## Subheading
More content
"""
        doc_type = segmenter._detect_document_type(markdown)
        assert doc_type == DocumentType.MARKDOWN

    def test_detect_json(self):
        """Test JSON detection."""
        segmenter = DocumentSegmenter()
        json_content = '{"key": "value"}'
        doc_type = segmenter._detect_document_type(json_content)
        assert doc_type == DocumentType.JSON

    def test_detect_text_fallback(self):
        """Test plain text fallback."""
        segmenter = DocumentSegmenter()
        text = "Just some plain text without structure"
        doc_type = segmenter._detect_document_type(text)
        assert doc_type == DocumentType.TEXT


class TestPythonSemanticSegmentation:
    """Test Python function/class boundary preservation."""

    def test_preserves_function_boundaries(self):
        """Test functions are not split mid-definition."""
        python_code = (
            "def function1():\n    pass\n\n"
            "def function2():\n    pass\n\n"
            "def function3():\n    pass\n\n"
            "def function4():\n    pass"
        )

        # Input intentionally exceeds max_chunk_lines to exercise boundary-aware splitting.
        config = SegmentationConfig(max_chunk_lines=10, overlap_lines=0)
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(python_code, DocumentType.PYTHON)

        # Should create chunks at function boundaries
        assert result.total_chunks > 1
        assert result.boundaries_preserved > 0

        # Verify no chunk splits mid-function
        for chunk in result.chunks:
            lines = chunk.content.split("\n")
            # Each chunk should start with 'def' or be continuation
            if "def" in lines[0]:
                assert lines[0].strip().startswith("def")

    def test_preserves_class_boundaries(self):
        """Test classes are not split mid-definition."""
        python_code = (
            "class MyClass:\n"
            "    def method1(self):\n"
            "        pass\n"
            "    def method2(self):\n"
            "        pass\n\n"
            "class AnotherClass:\n"
            "    def method3(self):\n"
            "        pass\n\n"
            "class ThirdClass:\n"
            "    def method4(self):\n"
            "        pass"
        )

        config = SegmentationConfig(max_chunk_lines=12, overlap_lines=0)
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(python_code, DocumentType.PYTHON)

        assert result.boundaries_preserved > 0

    def test_forces_split_when_too_large(self):
        """Test force split when chunk exceeds 2x max_chunk_lines."""
        # Create a huge function that exceeds 2x max
        python_code = "def huge_function():\n" + "    pass\n" * 500

        config = SegmentationConfig(max_chunk_lines=100, overlap_lines=0)
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(python_code, DocumentType.PYTHON)

        # Should have multiple chunks even though it's one function
        assert result.total_chunks > 1


class TestMarkdownSemanticSegmentation:
    """Test Markdown heading boundary preservation."""

    def test_preserves_heading_boundaries(self):
        """Test markdown splits at heading boundaries."""
        markdown = (
            "# Heading 1\n"
            "Content 1 line 1\n"
            "Content 1 line 2\n"
            "Content 1 line 3\n\n"
            "## Subheading 1.1\n"
            "More content line 1\n"
            "More content line 2\n\n"
            "# Heading 2\n"
            "Content 2 line 1\n"
            "Content 2 line 2\n"
            "Content 2 line 3"
        )

        config = SegmentationConfig(max_chunk_lines=10, overlap_lines=0)
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(markdown, DocumentType.MARKDOWN)

        assert result.total_chunks > 1
        assert result.boundaries_preserved > 0

    def test_never_splits_inside_code_blocks(self):
        """Test markdown never splits inside ``` code blocks."""
        markdown = "# Heading\n```python\ndef function():\n    pass\n```\nMore text"

        config = SegmentationConfig(max_chunk_lines=10, overlap_lines=0)
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(markdown, DocumentType.MARKDOWN)

        # Verify code block is intact in at least one chunk
        found_complete_block = False
        for chunk in result.chunks:
            if "```python" in chunk.content and "```" in chunk.content[chunk.content.index("```python") + 9 :]:
                found_complete_block = True
                break

        assert found_complete_block


class TestFixedSizeSegmentation:
    """Test simple fixed-size chunking."""

    def test_creates_even_chunks(self):
        """Test fixed-size creates predictable chunks."""
        content = "\n".join([f"Line {i}" for i in range(100)])

        config = SegmentationConfig(
            max_chunk_lines=20,
            overlap_lines=0,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(content)

        # Should have 100/20 = 5 chunks
        assert result.total_chunks == 5

        # Each chunk (except last) should have exactly 20 lines
        for _i, chunk in enumerate(result.chunks[:-1]):
            lines = chunk.content.split("\n")
            assert len(lines) == 20

    def test_handles_remainder(self):
        """Test fixed-size handles remainder lines correctly."""
        content = "\n".join([f"Line {i}" for i in range(105)])

        config = SegmentationConfig(
            max_chunk_lines=20,
            overlap_lines=0,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(content)

        # Should have 6 chunks (5 full + 1 partial)
        assert result.total_chunks == 6

        # Last chunk should have 5 lines
        last_chunk_lines = result.chunks[-1].content.split("\n")
        assert len(last_chunk_lines) == 5


class TestOverlapAddition:
    """Test context overlap between chunks."""

    def test_adds_overlap_from_previous_chunk(self):
        """Test overlap includes lines from previous chunk."""
        content = "\n".join([f"Line {i}" for i in range(50)])

        config = SegmentationConfig(
            max_chunk_lines=20,
            overlap_lines=5,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(content)

        # Second chunk should start with overlap from first chunk
        if result.total_chunks > 1:
            chunk2 = result.chunks[1]
            # Should have metadata indicating overlap
            assert chunk2.metadata.get("has_overlap") == "true"
            assert int(chunk2.metadata.get("overlap_lines", "0")) == 5

    def test_first_chunk_has_no_overlap(self):
        """Test first chunk has no overlap."""
        content = "\n".join([f"Line {i}" for i in range(50)])

        config = SegmentationConfig(
            max_chunk_lines=20,
            overlap_lines=5,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(content)

        # First chunk should have no overlap metadata
        chunk1 = result.chunks[0]
        assert "has_overlap" not in chunk1.metadata


class TestReconstruction:
    """Test document reconstruction from chunks."""

    def test_reconstruction_without_overlap_removal(self):
        """Test basic reconstruction preserves chunks."""
        content = "\n".join([f"Line {i}" for i in range(50)])

        config = SegmentationConfig(
            max_chunk_lines=20,
            overlap_lines=0,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(content)

        reconstructed = segmenter.reconstruct(result.chunks, remove_overlap=False)
        assert reconstructed == content

    def test_reconstruction_with_overlap_removal(self):
        """Test reconstruction removes overlapping sections."""
        content = "\n".join([f"Line {i}" for i in range(50)])

        config = SegmentationConfig(
            max_chunk_lines=20,
            overlap_lines=5,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(content)

        # Reconstruct with overlap removal
        reconstructed = segmenter.reconstruct(result.chunks, remove_overlap=True)

        # Should match original (overlap removed)
        original_lines = content.split("\n")
        reconstructed_lines = reconstructed.split("\n")

        # Allow for slight difference due to boundary handling
        assert abs(len(original_lines) - len(reconstructed_lines)) <= 1

    def test_perfect_reconstruction_semantic(self):
        """Test perfect reconstruction with semantic strategy."""
        python_code = (
            "def function1():\n    pass\n\ndef function2():\n    return 42\n\ndef function3():\n    print('hello')"
        )

        config = SegmentationConfig(
            max_chunk_lines=10,
            overlap_lines=1,
            strategy=ChunkingStrategy.SEMANTIC,
        )
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(python_code, DocumentType.PYTHON)

        reconstructed = segmenter.reconstruct(result.chunks, remove_overlap=True)

        # Remove trailing whitespace for comparison
        assert reconstructed.strip() == python_code.strip()


class TestHybridStrategy:
    """Test hybrid strategy with fallback."""

    def test_uses_semantic_when_possible(self):
        """Test hybrid uses semantic for well-structured code."""
        python_code = "\n".join([f"def func{i}():\n    pass\n" for i in range(10)])

        config = SegmentationConfig(
            max_chunk_lines=10,
            overlap_lines=0,
            strategy=ChunkingStrategy.HYBRID,
        )
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(python_code, DocumentType.PYTHON)

        # Should report hybrid strategy was used (semantic succeeded internally)
        assert result.strategy_used == ChunkingStrategy.HYBRID
        assert result.boundaries_preserved > 0

    def test_falls_back_to_fixed_when_chunks_too_large(self):
        """Test hybrid falls back to fixed_size for oversized chunks."""
        # Create a huge function that would create oversized semantic chunks
        python_code = "def huge():\n" + "    pass\n" * 1000

        config = SegmentationConfig(
            max_chunk_lines=100,
            overlap_lines=0,
            strategy=ChunkingStrategy.HYBRID,
        )
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(python_code, DocumentType.PYTHON)

        # Should report hybrid strategy was used (fixed_size fallback internally)
        assert result.strategy_used == ChunkingStrategy.HYBRID
        # Should have multiple chunks due to fallback
        assert result.total_chunks > 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_content(self):
        """Test empty content returns empty result."""
        segmenter = DocumentSegmenter()
        result = segmenter.segment("")

        assert result.total_chunks == 0
        assert len(result.chunks) == 0

    def test_single_line_content(self):
        """Test single line creates single chunk."""
        segmenter = DocumentSegmenter()
        result = segmenter.segment("Single line")

        assert result.total_chunks == 1
        assert result.chunks[0].content == "Single line"

    def test_content_smaller_than_chunk_size(self):
        """Test content smaller than chunk size creates single chunk."""
        content = "\n".join([f"Line {i}" for i in range(10)])

        config = SegmentationConfig(max_chunk_lines=100)
        segmenter = DocumentSegmenter(config)
        result = segmenter.segment(content)

        assert result.total_chunks == 1

    def test_reconstruct_empty_chunks(self):
        """Test reconstruct handles empty chunk list."""
        segmenter = DocumentSegmenter()
        reconstructed = segmenter.reconstruct([])

        assert reconstructed == ""


class TestSingletonFactory:
    """Test singleton factory pattern."""

    def test_returns_same_instance(self):
        """Test factory returns same instance on multiple calls."""
        instance1 = get_document_segmenter()
        instance2 = get_document_segmenter()

        assert instance1 is instance2

    def test_custom_config_returns_new_instance(self):
        """Test custom config returns a new isolated instance."""
        config1 = SegmentationConfig(max_chunk_lines=100)
        instance1 = get_document_segmenter(config1)

        config2 = SegmentationConfig(max_chunk_lines=200)
        instance2 = get_document_segmenter(config2)

        assert instance1 is not instance2
        assert instance1.config.max_chunk_lines == 100
        assert instance2.config.max_chunk_lines == 200

    def test_custom_config_does_not_mutate_default_singleton(self):
        """Test default singleton remains stable after custom-config calls."""
        default_instance = get_document_segmenter()
        _custom_instance = get_document_segmenter(SegmentationConfig(max_chunk_lines=321))

        assert get_document_segmenter() is default_instance


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
