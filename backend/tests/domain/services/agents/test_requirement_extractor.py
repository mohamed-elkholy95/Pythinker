"""Tests for RequirementExtractor, RequirementSet, and Requirement models.

Covers numbered/bullet/conjunction extraction, priority detection,
deduplication, coverage metrics, and requirement matching.
"""

import pytest

from app.domain.services.agents.requirement_extractor import (
    Requirement,
    RequirementExtractor,
    RequirementPriority,
    RequirementSet,
    extract_requirements,
    get_requirement_extractor,
)


# ─────────────────────────────────────────────────────────────
# Requirement dataclass
# ─────────────────────────────────────────────────────────────


class TestRequirement:
    def test_create(self):
        r = Requirement(
            id="REQ-001",
            description="Read CSV file",
            priority=RequirementPriority.MUST_HAVE,
            source_text="1. Read CSV file",
        )
        assert r.id == "REQ-001"
        assert r.addressed is False
        assert r.addressed_by_step is None

    def test_mark_addressed(self):
        r = Requirement(
            id="REQ-001",
            description="Read CSV file",
            priority=RequirementPriority.MUST_HAVE,
            source_text="1. Read CSV file",
        )
        r.mark_addressed("step-3")
        assert r.addressed is True
        assert r.addressed_by_step == "step-3"


# ─────────────────────────────────────────────────────────────
# RequirementSet properties
# ─────────────────────────────────────────────────────────────


class TestRequirementSet:
    def test_empty_set(self):
        rs = RequirementSet()
        assert rs.must_haves == []
        assert rs.unaddressed == []
        assert rs.coverage_percent == 100.0
        assert rs.must_have_coverage_percent == 100.0

    def test_must_haves_filter(self):
        rs = RequirementSet(
            requirements=[
                Requirement(id="1", description="A", priority=RequirementPriority.MUST_HAVE, source_text="A"),
                Requirement(id="2", description="B", priority=RequirementPriority.SHOULD_HAVE, source_text="B"),
                Requirement(id="3", description="C", priority=RequirementPriority.MUST_HAVE, source_text="C"),
            ]
        )
        assert len(rs.must_haves) == 2

    def test_unaddressed(self):
        r1 = Requirement(id="1", description="A", priority=RequirementPriority.MUST_HAVE, source_text="A")
        r2 = Requirement(
            id="2", description="B", priority=RequirementPriority.MUST_HAVE, source_text="B", addressed=True
        )
        rs = RequirementSet(requirements=[r1, r2])
        assert len(rs.unaddressed) == 1
        assert rs.unaddressed[0].id == "1"

    def test_coverage_percent_none_addressed(self):
        rs = RequirementSet(
            requirements=[
                Requirement(id="1", description="A", priority=RequirementPriority.MUST_HAVE, source_text="A"),
                Requirement(id="2", description="B", priority=RequirementPriority.MUST_HAVE, source_text="B"),
            ]
        )
        assert rs.coverage_percent == 0.0

    def test_coverage_percent_half_addressed(self):
        r1 = Requirement(
            id="1", description="A", priority=RequirementPriority.MUST_HAVE, source_text="A", addressed=True
        )
        r2 = Requirement(id="2", description="B", priority=RequirementPriority.MUST_HAVE, source_text="B")
        rs = RequirementSet(requirements=[r1, r2])
        assert rs.coverage_percent == 50.0

    def test_coverage_percent_all_addressed(self):
        r1 = Requirement(
            id="1", description="A", priority=RequirementPriority.MUST_HAVE, source_text="A", addressed=True
        )
        r2 = Requirement(
            id="2", description="B", priority=RequirementPriority.MUST_HAVE, source_text="B", addressed=True
        )
        rs = RequirementSet(requirements=[r1, r2])
        assert rs.coverage_percent == 100.0

    def test_must_have_coverage_no_must_haves(self):
        rs = RequirementSet(
            requirements=[
                Requirement(id="1", description="A", priority=RequirementPriority.NICE_TO_HAVE, source_text="A"),
            ]
        )
        assert rs.must_have_coverage_percent == 100.0

    def test_must_have_coverage_partial(self):
        r1 = Requirement(
            id="1", description="A", priority=RequirementPriority.MUST_HAVE, source_text="A", addressed=True
        )
        r2 = Requirement(id="2", description="B", priority=RequirementPriority.MUST_HAVE, source_text="B")
        r3 = Requirement(
            id="3", description="C", priority=RequirementPriority.SHOULD_HAVE, source_text="C", addressed=True
        )
        rs = RequirementSet(requirements=[r1, r2, r3])
        assert rs.must_have_coverage_percent == 50.0

    def test_get_summary_empty(self):
        rs = RequirementSet()
        assert rs.get_summary() == ""

    def test_get_summary_with_items(self):
        rs = RequirementSet(
            requirements=[
                Requirement(
                    id="1", description="Read CSV", priority=RequirementPriority.MUST_HAVE, source_text="1. Read CSV"
                ),
                Requirement(
                    id="2",
                    description="Filter rows",
                    priority=RequirementPriority.SHOULD_HAVE,
                    source_text="2. Filter rows",
                    addressed=True,
                ),
            ]
        )
        summary = rs.get_summary()
        assert "## User Requirements Checklist" in summary
        assert "[ ] **Read CSV**" in summary
        assert "[x] Filter rows" in summary

    def test_get_unaddressed_reminder_none_when_all_addressed(self):
        r = Requirement(
            id="1", description="A", priority=RequirementPriority.MUST_HAVE, source_text="A", addressed=True
        )
        rs = RequirementSet(requirements=[r])
        assert rs.get_unaddressed_reminder() is None

    def test_get_unaddressed_reminder_with_must_haves(self):
        r = Requirement(id="1", description="Read CSV", priority=RequirementPriority.MUST_HAVE, source_text="x")
        rs = RequirementSet(requirements=[r])
        reminder = rs.get_unaddressed_reminder()
        assert reminder is not None
        assert "REMINDER" in reminder
        assert "Read CSV" in reminder

    def test_get_unaddressed_reminder_only_nice_to_have(self):
        r = Requirement(id="1", description="Add colors", priority=RequirementPriority.NICE_TO_HAVE, source_text="x")
        rs = RequirementSet(requirements=[r])
        # Only NICE_TO_HAVE unaddressed — no must-have reminder
        assert rs.get_unaddressed_reminder() is None


# ─────────────────────────────────────────────────────────────
# RequirementExtractor.extract — numbered lists
# ─────────────────────────────────────────────────────────────


class TestExtractNumbered:
    def test_numbered_list(self):
        prompt = """Create a script that:
1. Reads a CSV file
2. Filters rows where age > 18
3. Outputs to JSON format"""
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        assert len(result.requirements) == 3
        assert "csv" in result.requirements[0].description.lower()

    def test_numbered_with_parentheses(self):
        prompt = """Tasks:
1) Build the frontend
2) Write unit tests
3) Deploy to staging"""
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        assert len(result.requirements) == 3

    def test_ignores_short_items(self):
        prompt = "1. OK\n2. This is a real requirement"
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        # "OK" is only 2 chars, should be skipped (min is > 3)
        assert len(result.requirements) == 1

    def test_req_ids_sequential(self):
        prompt = "1. First item here\n2. Second item here\n3. Third item here"
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        ids = [r.id for r in result.requirements]
        assert ids == ["REQ-001", "REQ-002", "REQ-003"]


# ─────────────────────────────────────────────────────────────
# RequirementExtractor.extract — bullet lists
# ─────────────────────────────────────────────────────────────


class TestExtractBullets:
    def test_dash_bullets(self):
        prompt = """Requirements:
- Parse the configuration file
- Validate all required fields
- Generate an error report"""
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        assert len(result.requirements) >= 3

    def test_asterisk_bullets(self):
        prompt = """Tasks:
* Create database schema
* Write migration scripts
* Add seed data"""
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        assert len(result.requirements) >= 3

    def test_mixed_numbered_and_bullets(self):
        prompt = """Steps:
1. Design the API
2. Implement endpoints
- Add authentication
- Add rate limiting"""
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        # Should capture both numbered and bullet items
        assert len(result.requirements) >= 4


# ─────────────────────────────────────────────────────────────
# RequirementExtractor.extract — conjunction extraction
# ─────────────────────────────────────────────────────────────


class TestExtractConjunction:
    def test_conjunction_with_action_words(self):
        prompt = "create a login page and build a dashboard and add user settings"
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        assert len(result.requirements) >= 2

    def test_conjunction_fallback_only(self):
        # Conjunction extraction only runs if no numbered/bullet items found
        prompt = "1. First task\n2. Second task"
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        # Should use numbered extraction, not conjunction
        assert all("REQ" in r.id for r in result.requirements)

    def test_no_extraction_for_simple_text(self):
        prompt = "just do the thing"
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        assert len(result.requirements) == 0


# ─────────────────────────────────────────────────────────────
# Priority detection
# ─────────────────────────────────────────────────────────────


class TestPriorityDetection:
    def test_must_have_indicators(self):
        extractor = RequirementExtractor()
        for indicator in ["must include", "should have", "need to add", "ensure correctness", "make sure it works"]:
            prompt = f"1. {indicator} validation logic"
            result = extractor.extract(prompt)
            assert result.requirements[0].priority == RequirementPriority.MUST_HAVE, f"Failed for: {indicator}"

    def test_optional_indicators(self):
        extractor = RequirementExtractor()
        for indicator in ["optionally add", "if possible include", "bonus feature", "nice to have"]:
            prompt = f"1. {indicator} dark mode support"
            result = extractor.extract(prompt)
            assert result.requirements[0].priority == RequirementPriority.NICE_TO_HAVE, f"Failed for: {indicator}"

    def test_default_priority_is_must_have(self):
        prompt = "1. Read the configuration file"
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        assert result.requirements[0].priority == RequirementPriority.MUST_HAVE


# ─────────────────────────────────────────────────────────────
# Text cleaning
# ─────────────────────────────────────────────────────────────


class TestCleanText:
    def test_strips_whitespace(self):
        extractor = RequirementExtractor()
        assert extractor._clean_text("  hello   world  ") == "Hello world"

    def test_strips_trailing_punctuation(self):
        extractor = RequirementExtractor()
        assert extractor._clean_text("read the file.") == "Read the file"
        assert extractor._clean_text("do the thing;") == "Do the thing"
        assert extractor._clean_text("parse data,") == "Parse data"

    def test_capitalizes_first_letter(self):
        extractor = RequirementExtractor()
        assert extractor._clean_text("lowercase start") == "Lowercase start"

    def test_empty_string(self):
        extractor = RequirementExtractor()
        assert extractor._clean_text("") == ""


# ─────────────────────────────────────────────────────────────
# Deduplication
# ─────────────────────────────────────────────────────────────


class TestDeduplication:
    def test_removes_exact_duplicates(self):
        extractor = RequirementExtractor()
        reqs = [
            Requirement(id="1", description="Read file", priority=RequirementPriority.MUST_HAVE, source_text="a"),
            Requirement(id="2", description="Read file", priority=RequirementPriority.MUST_HAVE, source_text="b"),
        ]
        result = extractor._deduplicate(reqs)
        assert len(result) == 1

    def test_case_insensitive_dedup(self):
        extractor = RequirementExtractor()
        reqs = [
            Requirement(id="1", description="Read File", priority=RequirementPriority.MUST_HAVE, source_text="a"),
            Requirement(id="2", description="read file", priority=RequirementPriority.MUST_HAVE, source_text="b"),
        ]
        result = extractor._deduplicate(reqs)
        assert len(result) == 1

    def test_keeps_different_items(self):
        extractor = RequirementExtractor()
        reqs = [
            Requirement(id="1", description="Read file", priority=RequirementPriority.MUST_HAVE, source_text="a"),
            Requirement(id="2", description="Write output", priority=RequirementPriority.MUST_HAVE, source_text="b"),
        ]
        result = extractor._deduplicate(reqs)
        assert len(result) == 2

    def test_single_item(self):
        extractor = RequirementExtractor()
        reqs = [
            Requirement(id="1", description="A", priority=RequirementPriority.MUST_HAVE, source_text="a"),
        ]
        result = extractor._deduplicate(reqs)
        assert len(result) == 1


# ─────────────────────────────────────────────────────────────
# match_requirement_to_step
# ─────────────────────────────────────────────────────────────


class TestMatchRequirementToStep:
    def test_perfect_overlap(self):
        extractor = RequirementExtractor()
        req = Requirement(
            id="1", description="Read CSV file", priority=RequirementPriority.MUST_HAVE, source_text="x"
        )
        score = extractor.match_requirement_to_step(req, "Read CSV file")
        assert score > 0.5

    def test_partial_overlap(self):
        extractor = RequirementExtractor()
        req = Requirement(
            id="1", description="Read CSV file", priority=RequirementPriority.MUST_HAVE, source_text="x"
        )
        score = extractor.match_requirement_to_step(req, "Parse the CSV data from input")
        assert 0.0 < score < 1.0

    def test_no_overlap(self):
        extractor = RequirementExtractor()
        req = Requirement(
            id="1", description="Read CSV file", priority=RequirementPriority.MUST_HAVE, source_text="x"
        )
        score = extractor.match_requirement_to_step(req, "Deploy to production server")
        assert score < 0.2

    def test_empty_requirement(self):
        extractor = RequirementExtractor()
        req = Requirement(id="1", description="", priority=RequirementPriority.MUST_HAVE, source_text="x")
        assert extractor.match_requirement_to_step(req, "anything") == 0.0

    def test_empty_step(self):
        extractor = RequirementExtractor()
        req = Requirement(
            id="1", description="Read file", priority=RequirementPriority.MUST_HAVE, source_text="x"
        )
        assert extractor.match_requirement_to_step(req, "") == 0.0

    def test_stop_words_ignored(self):
        extractor = RequirementExtractor()
        req = Requirement(
            id="1", description="Read the CSV file", priority=RequirementPriority.MUST_HAVE, source_text="x"
        )
        # "the" is a stop word, score should be similar with or without
        score_with = extractor.match_requirement_to_step(req, "Read the CSV file")
        score_without = extractor.match_requirement_to_step(req, "Read CSV file")
        assert abs(score_with - score_without) < 0.3


# ─────────────────────────────────────────────────────────────
# Empty / edge cases
# ─────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_prompt(self):
        extractor = RequirementExtractor()
        result = extractor.extract("")
        assert len(result.requirements) == 0
        assert result.original_prompt == ""

    def test_whitespace_only(self):
        extractor = RequirementExtractor()
        result = extractor.extract("   \n\n  ")
        assert len(result.requirements) == 0

    def test_preserves_original_prompt(self):
        prompt = "1. Do the thing\n2. Do another thing"
        extractor = RequirementExtractor()
        result = extractor.extract(prompt)
        assert result.original_prompt == prompt


# ─────────────────────────────────────────────────────────────
# Module-level convenience functions
# ─────────────────────────────────────────────────────────────


class TestConvenienceFunctions:
    def test_get_requirement_extractor_singleton(self):
        e1 = get_requirement_extractor()
        e2 = get_requirement_extractor()
        assert e1 is e2

    def test_extract_requirements_function(self):
        result = extract_requirements("1. Parse JSON data\n2. Validate schema")
        assert len(result.requirements) >= 2
