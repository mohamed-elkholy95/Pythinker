"""Tests for AcknowledgmentGenerator — brief pre-planning feedback messages."""

from __future__ import annotations

import pytest

from app.domain.services.flows.acknowledgment import AcknowledgmentGenerator


@pytest.fixture()
def ack() -> AcknowledgmentGenerator:
    return AcknowledgmentGenerator()


# ── Skill creation acknowledgment ──────────────────────────────────────────


class TestAckSkillCreation:
    def test_skill_creator_with_name(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate('/skill-creator "data-analyzer"')
        assert "data-analyzer" in result
        assert "skill" in result.lower()

    def test_skill_creator_without_name(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("/skill-creator")
        assert "skill" in result.lower()
        assert "guidelines" in result.lower()

    def test_skill_creator_quoted_name_in_body(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate('Create a skill called "web-scraper" using /skill-creator')
        assert "web-scraper" in result


# ── Research acknowledgment ────────────────────────────────────────────────


class TestAckResearch:
    def test_research_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Research the latest AI agents in 2026")
        assert result.startswith("Got it!")
        assert "research" in result.lower()

    def test_research_report_request(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Create a comprehensive research report on quantum computing")
        assert "research report" in result.lower()


# ── Create / Build acknowledgment ──────────────────────────────────────────


class TestAckCreateBuild:
    def test_create_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Create a Python script for data analysis")
        assert result.startswith("Got it!")

    def test_build_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Build a REST API for user management")
        assert result.startswith("Got it!")

    def test_generate_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Generate a report on sales data")
        assert result.startswith("Got it!")


# ── Fix / Debug acknowledgment ─────────────────────────────────────────────


class TestAckFixDebug:
    def test_fix_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Fix the login bug")
        assert "issue" in result.lower() or "solution" in result.lower()

    def test_debug_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Debug the authentication failure")
        assert result.startswith("Got it!")

    def test_fix_large_prompt(self, ack: AcknowledgmentGenerator) -> None:
        msg = "Fix the authentication system.\n1. Check token validation\n2. Verify refresh flow\n3. Update error handling"
        result = ack.generate(msg)
        assert "diagnose" in result.lower() or "fix" in result.lower()


# ── Find / Search acknowledgment ──────────────────────────────────────────


class TestAckFindSearch:
    def test_find_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Find the best laptop deals")
        assert "search" in result.lower() or "information" in result.lower()

    def test_search_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Search for Python tutorials")
        assert result.startswith("Got it!")


# ── Other task type acknowledgments ────────────────────────────────────────


class TestAckOtherTypes:
    def test_explain_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Explain how Docker works")
        assert "look into" in result.lower()

    def test_update_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Update the user profile page")
        assert "changes" in result.lower()

    def test_install_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Install and configure nginx")
        assert "set" in result.lower()

    def test_test_keyword(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Test the payment integration")
        assert "check" in result.lower()


# ── Default / Fallback acknowledgment ──────────────────────────────────────


class TestAckDefault:
    def test_generic_message(self, ack: AcknowledgmentGenerator) -> None:
        result = ack.generate("Do something interesting")
        assert result.startswith("Got it!")

    def test_large_prompt_default(self, ack: AcknowledgmentGenerator) -> None:
        long_msg = "x" * 300
        result = ack.generate(long_msg)
        assert "structured" in result.lower() or "analyze" in result.lower()


# ── Helper methods ─────────────────────────────────────────────────────────


class TestHelperMethods:
    def test_is_large_prompt_short_message(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._is_large_prompt("short msg", "focus") is False

    def test_is_large_prompt_long_message(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._is_large_prompt("x" * 300, "focus") is True

    def test_is_large_prompt_long_focus(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._is_large_prompt("msg", "x" * 150) is True

    def test_is_large_prompt_with_newline(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._is_large_prompt("line1\nline2", "focus") is True

    def test_is_large_prompt_with_numbered_items(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._is_large_prompt("1. first 2. second", "focus") is True

    def test_join_subjects_empty(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._join_subjects([]) == ""

    def test_join_subjects_single(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._join_subjects(["AI"]) == "AI"

    def test_join_subjects_two(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._join_subjects(["AI", "ML"]) == "AI and ML"

    def test_join_subjects_three(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._join_subjects(["AI", "ML", "NLP"]) == "AI, ML, and NLP"

    def test_is_generic_list_placeholder_true(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._is_generic_list_placeholder("the following topics") is True

    def test_is_generic_list_placeholder_false(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._is_generic_list_placeholder("quantum computing") is False

    def test_is_generic_list_placeholder_none(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._is_generic_list_placeholder(None) is False

    def test_compact_subject_none(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._compact_subject(None) is None

    def test_compact_subject_empty(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._compact_subject("") is None

    def test_compact_subject_normal(self, ack: AcknowledgmentGenerator) -> None:
        result = ack._compact_subject("a detailed research topic")
        assert result is not None
        assert "research" in result

    def test_compact_subject_truncates_long_text(self, ack: AcknowledgmentGenerator) -> None:
        long_subject = " ".join(["word"] * 20)
        result = ack._compact_subject(long_subject)
        assert result is not None
        assert len(result.split()) <= 14

    def test_is_research_report_request_true(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._is_research_report_request("Create a research report on AI") is True

    def test_is_research_report_request_false(self, ack: AcknowledgmentGenerator) -> None:
        assert ack._is_research_report_request("Tell me about AI") is False

    def test_extract_numbered_topics_summary_returns_joined(self, ack: AcknowledgmentGenerator) -> None:
        msg = "1. Quantum computing\n2. Machine learning\n3. Blockchain"
        result = ack._extract_numbered_topics_summary(msg)
        assert result is not None
        assert "and" in result

    def test_extract_numbered_topics_summary_single_item_returns_none(self, ack: AcknowledgmentGenerator) -> None:
        result = ack._extract_numbered_topics_summary("1. Just one topic")
        assert result is None

    def test_strip_system_instruction_prefix_for_pattern(self, ack: AcknowledgmentGenerator) -> None:
        result = ack._strip_system_instruction_prefix("Act as a deal finder. Search stores for: best laptop deals 2026")
        assert result == "best laptop deals 2026"

    def test_strip_system_instruction_prefix_no_prefix(self, ack: AcknowledgmentGenerator) -> None:
        text = "Find the best laptop deals"
        assert ack._strip_system_instruction_prefix(text) == text
