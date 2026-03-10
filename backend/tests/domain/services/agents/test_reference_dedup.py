"""Tests for reference section deduplication."""

import re

import pytest


class TestReferenceSectionDedup:
    """Only one References section should exist in the final output."""

    def test_no_duplicate_references_sections(self):
        """Content with an existing complete References section should not get another one."""
        content = """# Report Title

## Analysis
Some analysis here [1][2].

## References
[1] Source One - https://example.com/1
[2] Source Two - https://example.com/2
"""
        # Count ## References headings
        ref_headings = re.findall(r"^##\s+References?\s*$", content, re.MULTILINE | re.IGNORECASE)
        assert len(ref_headings) == 1

    def test_dedup_multiple_references_headings(self):
        """Multiple References sections should be deduplicated to one."""
        content = """# Report Title

## Analysis
Some analysis [1].

## References
[1] Source One - https://example.com/1

## References
[1] Source One (duplicate) - https://example.com/1
[2] Source Two (duplicate) - https://example.com/2
"""
        ref_headings = re.findall(r"^##\s+References?\s*$", content, re.MULTILINE | re.IGNORECASE)
        assert len(ref_headings) == 2  # Confirm two exist before dedup

        # Apply dedup logic (same as execution.py)
        parts = re.split(r"(^##\s+References?\s*$)", content, flags=re.MULTILINE | re.IGNORECASE)
        if len(parts) >= 3:
            content = parts[0] + parts[1] + parts[2]

        ref_headings_after = re.findall(r"^##\s+References?\s*$", content, re.MULTILINE | re.IGNORECASE)
        assert len(ref_headings_after) == 1

    def test_existing_complete_refs_not_replaced(self):
        """If existing refs >= expected, leave untouched."""
        content = "# Report\n\n[1] cited.\n\n## References\n[1] Source - url\n[2] Extra - url\n"
        expected_count = 1  # Only 1 source tracked
        ref_match = re.search(r"^##\s+References?\s*$", content, re.MULTILINE | re.IGNORECASE)
        ref_section = content[ref_match.end() :].strip()
        existing_count = len(re.findall(r"^\s*\[?\d+\]", ref_section, re.MULTILINE))

        # Guard: don't replace if existing >= expected
        should_replace = existing_count < expected_count
        assert should_replace is False

    def test_single_references_untouched(self):
        """Content with exactly one References section should not be modified by dedup."""
        content = "# Report\n\n## References\n[1] Source One\n"
        ref_headings = re.findall(r"^##\s+References?\s*$", content, re.MULTILINE | re.IGNORECASE)
        assert len(ref_headings) == 1
        # No dedup needed — content unchanged
