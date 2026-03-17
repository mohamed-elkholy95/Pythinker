"""Tests for citation integrity validator and repair."""

from app.domain.services.agents.citation_integrity import (
    CitationIntegrityResult,
    count_numbered_sources,
    normalize_citation_numbering,
    parse_numbered_source_entries,
    repair_citations,
    validate_citations,
)


class TestValidateCitations:
    """Tests for validate_citations()."""

    def test_valid_report(self):
        report = (
            "# Report\n\n"
            "Finding one [1]. Finding two [2].\n\n"
            "## References\n"
            "[1] Source A - https://a.com\n"
            "[2] Source B - https://b.com\n"
        )
        result = validate_citations(report)
        assert result.is_valid
        assert result.orphan_citations == []
        assert result.phantom_references == []
        assert result.citation_gaps == []
        assert result.duplicate_urls == []

    def test_orphan_citations(self):
        report = "# Report\n\nClaim [1]. Another claim [3].\n\n## References\n[1] Source A - https://a.com\n"
        result = validate_citations(report)
        assert not result.is_valid
        assert 3 in result.orphan_citations
        assert 1 not in result.orphan_citations

    def test_phantom_references(self):
        report = "# Report\n\nClaim [1].\n\n## References\n[1] Source A - https://a.com\n[2] Source B - https://b.com\n"
        result = validate_citations(report)
        assert not result.is_valid
        assert 2 in result.phantom_references

    def test_citation_gaps(self):
        report = (
            "# Report\n\n"
            "Claim [1]. Another [3].\n\n"
            "## References\n"
            "[1] Source A - https://a.com\n"
            "[3] Source C - https://c.com\n"
        )
        result = validate_citations(report)
        assert not result.is_valid
        assert 2 in result.citation_gaps

    def test_duplicate_urls(self):
        report = (
            "# Report\n\n"
            "Claim [1]. Another [2].\n\n"
            "## References\n"
            "[1] Source A - https://example.com\n"
            "[2] Source B - https://example.com\n"
        )
        result = validate_citations(report)
        assert not result.is_valid
        assert len(result.duplicate_urls) == 1

    def test_empty_content(self):
        result = validate_citations("")
        assert result.is_valid

    def test_no_references_section(self):
        report = "# Report\n\nSome content [1] here.\n"
        result = validate_citations(report)
        assert not result.is_valid
        assert 1 in result.orphan_citations

    def test_issue_count(self):
        result = CitationIntegrityResult(
            is_valid=False,
            orphan_citations=[3, 5],
            phantom_references=[2],
            citation_gaps=[4],
            duplicate_urls=["https://x.com"],
        )
        assert result.issue_count == 5


class TestRepairCitations:
    """Tests for repair_citations()."""

    def test_repair_orphan_from_source_list(self):
        report = "# Report\n\nClaim [1]. New claim [2].\n\n## References\n[1] Source A - https://a.com\n"
        source_list = "[1] Source A - https://a.com\n[2] Source B - https://b.com\n"
        repaired = repair_citations(report, source_list)
        assert "[2] Source B - https://b.com" in repaired

    def test_repair_creates_references_section(self):
        report = "# Report\n\nClaim [1].\n"
        source_list = "[1] Source A - https://a.com\n"
        repaired = repair_citations(report, source_list)
        assert "## References" in repaired
        assert "[1] Source A - https://a.com" in repaired

    def test_no_repair_when_valid(self):
        report = "# Report\n\nClaim [1].\n\n## References\n[1] Source A - https://a.com\n"
        source_list = "[1] Source A - https://a.com\n"
        repaired = repair_citations(report, source_list)
        assert repaired == report

    def test_no_repair_when_source_missing(self):
        report = "# Report\n\nClaim [99].\n\n## References\n"
        source_list = "[1] Source A - https://a.com\n"
        repaired = repair_citations(report, source_list)
        # No source_list entry for [99], so nothing to repair with
        assert repaired == report

    def test_repair_removes_phantom_references(self):
        report = "# Report\n\nClaim [1].\n\n## References\n[1] Source A - https://a.com\n[2] Source B - https://b.com\n"
        source_list = "[1] Source A - https://a.com\n[2] Source B - https://b.com\n"

        repaired = repair_citations(report, source_list)

        assert "[1] Source A - https://a.com" in repaired
        assert "[2] Source B - https://b.com" not in repaired

    def test_empty_inputs(self):
        assert repair_citations("", "[1] X - https://x.com") == ""
        assert repair_citations("# R\n\nClaim [1].\n", "") == "# R\n\nClaim [1].\n"

    def test_repair_normalizes_sparse_numbering(self):
        report = (
            "# Report\n\n"
            "Claim [4]. Another [6].\n\n"
            "## References\n"
            "[4] Source A - https://a.com\n"
            "[6] Source B - https://b.com\n"
        )

        repaired = repair_citations(report, "")

        assert "Claim [1]. Another [2]." in repaired
        assert "[1] Source A - https://a.com" in repaired
        assert "[2] Source B - https://b.com" in repaired
        assert validate_citations(repaired).is_valid


class TestNormalizeCitationNumbering:
    """Tests for normalize_citation_numbering()."""

    def test_noop_when_already_contiguous(self):
        report = (
            "# Report\n\n"
            "Claim [1]. Another [2].\n\n"
            "## References\n"
            "[1] Source A - https://a.com\n"
            "[2] Source B - https://b.com\n"
        )
        assert normalize_citation_numbering(report) == report

    def test_years_in_brackets_not_treated_as_citations(self):
        """Years like [2024] and [2026] must not be treated as citation numbers."""
        report = (
            "# Report\n\n"
            "The market grew 47% in [2024] and is projected to reach $8B by [2026].\n"
            "According to [1], this trend is accelerating [2].\n\n"
            "## References\n"
            "[1] Source A - https://a.com\n"
            "[2] Source B - https://b.com\n"
        )
        result = validate_citations(report)
        assert result.is_valid
        assert 2024 not in result.orphan_citations
        assert 2026 not in result.orphan_citations
        assert result.citation_gaps == []

    def test_normalize_ignores_years_in_brackets(self):
        """normalize_citation_numbering must not remap year numbers."""
        report = (
            "# Report\n\n"
            "In [2024], AI grew. Claim [1]. Claim [3].\n\n"
            "## References\n"
            "[1] Source A - https://a.com\n"
            "[3] Source C - https://c.com\n"
        )
        normalized = normalize_citation_numbering(report)
        # [2024] should remain untouched as a year reference
        assert "[2024]" in normalized
        # [1] and [3] should be renumbered to [1] and [2]
        assert "Claim [1]" in normalized
        assert "Claim [2]" in normalized

    def test_repair_with_years_does_not_corrupt(self):
        """repair_citations must leave years intact and only fix real citations."""
        report = (
            "# Report\n\n"
            "Since [2024], claim [1] and claim [3] are valid.\n\n"
            "## References\n"
            "[1] Source A - https://a.com\n"
            "[3] Source C - https://c.com\n"
        )
        source_list = "[1] Source A - https://a.com\n[3] Source C - https://c.com\n"
        repaired = repair_citations(report, source_list)
        assert "[2024]" in repaired
        assert "Source A" in repaired


class TestSourceRegistry:
    """Test pre-generation stable source numbering."""

    def test_registry_assigns_stable_ids(self):
        from app.domain.services.agents.citation_integrity import SourceRegistry

        registry = SourceRegistry()
        id1 = registry.register("https://example.com/a", "Source A")
        id2 = registry.register("https://example.com/b", "Source B")
        id3 = registry.register("https://example.com/a", "Source A Duplicate")

        assert id1 == 1
        assert id2 == 2
        assert id3 == 1  # Same URL → same ID
        assert registry.count == 2

    def test_registry_get_id(self):
        from app.domain.services.agents.citation_integrity import SourceRegistry

        registry = SourceRegistry()
        registry.register("https://example.com/a", "Source A")
        assert registry.get_id("https://example.com/a") == 1
        assert registry.get_id("https://unknown.com") is None

    def test_registry_builds_references(self):
        from app.domain.services.agents.citation_integrity import SourceRegistry

        registry = SourceRegistry()
        registry.register("https://example.com/a", "Source A")
        registry.register("https://example.com/b", "Source B")
        refs = registry.build_references_section()
        assert "[1] Source A - https://example.com/a" in refs
        assert "[2] Source B - https://example.com/b" in refs

    def test_fuzzy_match_no_match(self):
        from app.domain.services.agents.citation_integrity import fuzzy_match_orphan

        refs = {1: "JAX Framework Overview - https://jax.dev"}
        result = fuzzy_match_orphan("completely unrelated text about cooking", refs)
        assert result is None

    def test_fuzzy_match_with_overlap(self):
        from app.domain.services.agents.citation_integrity import fuzzy_match_orphan

        refs = {
            1: "JAX Framework Overview guide tutorial",
            2: "PyTorch Deep Learning basics",
        }
        result = fuzzy_match_orphan("JAX Framework performance guide", refs)
        assert result == 1

    def test_url_normalization(self):
        from app.domain.services.agents.citation_integrity import SourceRegistry

        registry = SourceRegistry()
        id1 = registry.register("https://Example.com/path/", "Source")
        id2 = registry.register("https://example.com/path", "Source 2")
        assert id1 == id2  # Same after normalization


class TestParseNumberedSourceEntries:
    """Tests for parse_numbered_source_entries() multiline handling."""

    def test_single_line_entries(self):
        source_list = "[1] Source A - https://a.example\n[2] Source B - https://b.example\n"
        entries = parse_numbered_source_entries(source_list)
        assert len(entries) == 2
        assert "[1] Source A" in entries[1]
        assert "[2] Source B" in entries[2]

    def test_multiline_title(self):
        source_list = (
            "[1] Source Title Line 1\n"
            "Continuation of title - https://one.example\n"
            "[2] Source Two - https://two.example\n"
        )
        entries = parse_numbered_source_entries(source_list)
        assert len(entries) == 2
        assert "Continuation of title" in entries[1]
        assert "[2] Source Two" in entries[2]

    def test_count_numbered_sources(self):
        source_list = (
            "[1] Source Title Line 1\n"
            "Continuation of title - https://one.example\n"
            "[2] Source Two - https://two.example\n"
        )
        assert count_numbered_sources(source_list) == 2


class TestAuthoritativeRepair:
    """Tests for repair_citations() with authoritative source validation."""

    def test_repair_citations_rebuilds_fake_reference_entries_from_authoritative_source_list(self):
        report = "# Report\n\nClaim text [1]\n\n## References\n[1] Fake Source - https://fake.example\n"
        source_list = "[1] Real Source One - https://one.example\n[2] Real Source Two - https://two.example\n"

        repaired = repair_citations(report, source_list)

        assert "Fake Source" not in repaired
        assert "https://fake.example" not in repaired
        assert "Real Source One" in repaired

    def test_repair_preserves_valid_references(self):
        """References matching authoritative entries should be preserved."""
        report = (
            "# Report\n\n"
            "Claim [1]. Another [2].\n\n"
            "## References\n"
            "[1] Source A - https://a.example\n"
            "[2] Source B - https://b.example\n"
        )
        source_list = "[1] Source A - https://a.example\n[2] Source B - https://b.example\n"

        repaired = repair_citations(report, source_list)

        assert "Source A" in repaired
        assert "Source B" in repaired
