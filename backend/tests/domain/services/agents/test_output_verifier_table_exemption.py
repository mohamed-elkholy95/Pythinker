"""Tests for markdown table exemption from hallucination checking."""

from __future__ import annotations

from app.domain.services.agents.output_verifier import OutputVerifier


class TestTableExemption:
    def test_strips_cited_table_rows(self):
        text = (
            "Some intro text.\n\n"
            "| Model | Score | Source |\n"
            "|-------|-------|--------|\n"
            "| GPT-5.4 | 77.2% | [16] |\n"
            "| GLM-5 | 72.8% | [8] |\n\n"
            "Some conclusion text."
        )
        stripped = OutputVerifier._strip_cited_tables(text)
        assert "| GPT-5.4 |" not in stripped
        assert "| GLM-5 |" not in stripped
        assert "Some intro text." in stripped
        assert "Some conclusion text." in stripped

    def test_preserves_tables_without_citations(self):
        text = "| Name | Value |\n|------|-------|\n| foo | bar |\n"
        stripped = OutputVerifier._strip_cited_tables(text)
        assert "| foo | bar |" in stripped

    def test_preserves_non_table_content(self):
        text = "Just regular text with [1] citation."
        stripped = OutputVerifier._strip_cited_tables(text)
        assert stripped == text

    def test_strips_header_row_of_cited_table(self):
        """Header and separator of a table with cited data rows should also be stripped."""
        text = "| Model | Score | Source |\n|-------|-------|--------|\n| GPT-5.4 | 77.2% | [16] |\n"
        stripped = OutputVerifier._strip_cited_tables(text)
        # The entire table block should be gone since data rows have citations
        assert "| Model |" not in stripped

    def test_empty_string(self):
        assert OutputVerifier._strip_cited_tables("") == ""

    def test_multiple_cited_tables(self):
        text = (
            "Table 1:\n"
            "| A | B |\n|---|---|\n| x | [1] |\n\n"
            "Middle text.\n\n"
            "Table 2:\n"
            "| C | D |\n|---|---|\n| y | [2] |\n"
        )
        stripped = OutputVerifier._strip_cited_tables(text)
        assert "| x |" not in stripped
        assert "| y |" not in stripped
        assert "Table 1:" in stripped
        assert "Middle text." in stripped
        assert "Table 2:" in stripped
