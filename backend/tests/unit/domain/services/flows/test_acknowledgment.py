"""Tests for AcknowledgmentGenerator."""

from __future__ import annotations

from unittest.mock import patch

from app.domain.services.flows.acknowledgment import AcknowledgmentGenerator


class TestAcknowledgmentGenerator:
    """Tests for AcknowledgmentGenerator.generate()."""

    def setup_method(self) -> None:
        self.gen = AcknowledgmentGenerator()

    def test_fix_keyword_returns_fix_ack(self) -> None:
        result = self.gen.generate("fix the login bug")
        assert "issue" in result.lower() or "solution" in result.lower() or "fix" in result.lower()

    def test_find_keyword_returns_search_ack(self) -> None:
        result = self.gen.generate("find information about python")
        assert "search" in result.lower() or "information" in result.lower()

    def test_explain_keyword(self) -> None:
        result = self.gen.generate("explain how docker works")
        assert "look into" in result.lower()

    def test_update_keyword(self) -> None:
        result = self.gen.generate("update the config file")
        assert "changes" in result.lower()

    def test_install_keyword(self) -> None:
        result = self.gen.generate("install redis on the server")
        assert "set" in result.lower()

    def test_test_keyword(self) -> None:
        result = self.gen.generate("test the API endpoint")
        assert "check" in result.lower()

    def test_default_generic_message(self) -> None:
        result = self.gen.generate("hello world")
        assert "Got it!" in result

    def test_create_keyword_with_focus(self) -> None:
        result = self.gen.generate("create a REST API for user management")
        assert "Got it!" in result

    @patch("app.domain.services.flows.acknowledgment.is_research_task", return_value=True)
    def test_research_task_returns_research_ack(self, mock_research: object) -> None:
        result = self.gen.generate("research the latest AI trends")
        assert "research" in result.lower()

    @patch("app.domain.services.flows.acknowledgment.is_research_task", return_value=True)
    def test_research_report_request(self, mock_research: object) -> None:
        result = self.gen.generate("create a comprehensive research report on AI safety")
        assert "research report" in result.lower()

    def test_skill_creation_with_name(self) -> None:
        result = self.gen.generate('/skill-creator "my-cool-skill"')
        assert "my-cool-skill" in result

    def test_skill_creation_without_name(self) -> None:
        result = self.gen.generate("/skill-creator")
        assert "skill" in result.lower()

    def test_large_prompt_fix_ack(self) -> None:
        long_msg = "fix " + "x" * 300
        result = self.gen.generate(long_msg)
        assert "diagnose" in result.lower() or "reliable" in result.lower()

    def test_large_prompt_find_ack(self) -> None:
        long_msg = "find " + "y" * 300
        result = self.gen.generate(long_msg)
        assert "Got it!" in result

    def test_large_prompt_default_ack(self) -> None:
        long_msg = "z" * 300
        result = self.gen.generate(long_msg)
        assert "structured" in result.lower() or "analyze" in result.lower()


class TestExtractRequestFocus:
    """Tests for _extract_request_focus."""

    def setup_method(self) -> None:
        self.gen = AcknowledgmentGenerator()

    def test_empty_message(self) -> None:
        assert self.gen._extract_request_focus("") == "this task"

    def test_strips_please_prefix(self) -> None:
        result = self.gen._extract_request_focus("please help me")
        assert not result.startswith("please")

    def test_strips_action_verbs(self) -> None:
        result = self.gen._extract_request_focus("create a website")
        assert "create" not in result.lower()
        assert result.strip() != ""

    def test_strips_polite_prefix(self) -> None:
        result = self.gen._extract_request_focus("can you fix the bug")
        assert "can you" not in result.lower()


class TestStripSystemInstructionPrefix:
    """Tests for _strip_system_instruction_prefix."""

    def test_for_delimiter(self) -> None:
        text = "Act as a professional researcher. Find information for: best python frameworks"
        result = AcknowledgmentGenerator._strip_system_instruction_prefix(text)
        assert result == "best python frameworks"

    def test_no_prefix_returns_original(self) -> None:
        text = "just a normal query"
        result = AcknowledgmentGenerator._strip_system_instruction_prefix(text)
        assert result == text

    def test_multi_sentence_instruction(self) -> None:
        text = "Act as a deal finder. Search stores. Find best coupon for cursor ai"
        result = AcknowledgmentGenerator._strip_system_instruction_prefix(text)
        assert "cursor ai" in result


class TestIsLargePrompt:
    """Tests for _is_large_prompt."""

    def setup_method(self) -> None:
        self.gen = AcknowledgmentGenerator()

    def test_short_prompt_not_large(self) -> None:
        assert self.gen._is_large_prompt("short message", "short") is False

    def test_280_chars_is_large(self) -> None:
        assert self.gen._is_large_prompt("a" * 280, "focus") is True

    def test_long_focus_is_large(self) -> None:
        assert self.gen._is_large_prompt("msg", "f" * 140) is True

    def test_newline_is_large(self) -> None:
        assert self.gen._is_large_prompt("line1\nline2", "focus") is True

    def test_numbered_list_is_large(self) -> None:
        assert self.gen._is_large_prompt("1. first 2. second", "focus") is True


class TestCompactSubject:
    """Tests for _compact_subject."""

    def setup_method(self) -> None:
        self.gen = AcknowledgmentGenerator()

    def test_none_returns_none(self) -> None:
        assert self.gen._compact_subject(None) is None

    def test_empty_returns_none(self) -> None:
        assert self.gen._compact_subject("") is None

    def test_strips_trailing_punctuation(self) -> None:
        result = self.gen._compact_subject("some topic.")
        assert result is not None
        assert not result.endswith(".")

    def test_truncates_long_subjects(self) -> None:
        long_subject = " ".join(["word"] * 20)
        result = self.gen._compact_subject(long_subject)
        assert result is not None
        assert len(result.split()) <= 14


class TestNormalizeSubject:
    """Tests for _normalize_subject."""

    def setup_method(self) -> None:
        self.gen = AcknowledgmentGenerator()

    def test_none_returns_none(self) -> None:
        assert self.gen._normalize_subject(None) is None

    def test_empty_returns_none(self) -> None:
        assert self.gen._normalize_subject("") is None

    def test_strips_research_report_prefix(self) -> None:
        result = self.gen._normalize_subject("a comprehensive research report on AI safety")
        assert result is not None
        assert "research report" not in result.lower()

    def test_corrects_typos(self) -> None:
        # "compoore" matches the typo regex \bcompo+re\b, "sonett" matches \bsonet+\b
        result = self.gen._normalize_subject("compoore sonett models")
        assert result is not None
        assert "sonnet" in result.lower()

    def test_converts_imperative_to_gerund(self) -> None:
        result = self.gen._normalize_subject("compare opus and sonnet")
        assert result is not None
        assert result.startswith("comparing")

    def test_normalizes_model_names(self) -> None:
        result = self.gen._normalize_subject("claude4.5 vs gpt4.0")
        assert result is not None
        assert "Claude" in result or "claude" in result.lower()


class TestExtractNumberedTopicsSummary:
    """Tests for _extract_numbered_topics_summary."""

    def setup_method(self) -> None:
        self.gen = AcknowledgmentGenerator()

    def test_none_returns_none(self) -> None:
        assert self.gen._extract_numbered_topics_summary(None) is None

    def test_empty_returns_none(self) -> None:
        assert self.gen._extract_numbered_topics_summary("") is None

    def test_single_item_returns_none(self) -> None:
        assert self.gen._extract_numbered_topics_summary("1. Only one item") is None

    def test_two_items_joined_with_and(self) -> None:
        text = "1. Machine learning\n2. Deep learning"
        result = self.gen._extract_numbered_topics_summary(text)
        assert result is not None
        assert "and" in result

    def test_three_items_joined_with_commas_and(self) -> None:
        text = "1. Python\n2. Rust\n3. Go"
        result = self.gen._extract_numbered_topics_summary(text)
        assert result is not None
        assert ", and" in result or "and" in result


class TestJoinSubjects:
    """Tests for _join_subjects."""

    def setup_method(self) -> None:
        self.gen = AcknowledgmentGenerator()

    def test_empty_list(self) -> None:
        assert self.gen._join_subjects([]) == ""

    def test_single_subject(self) -> None:
        assert self.gen._join_subjects(["AI"]) == "AI"

    def test_two_subjects(self) -> None:
        assert self.gen._join_subjects(["AI", "ML"]) == "AI and ML"

    def test_three_subjects(self) -> None:
        result = self.gen._join_subjects(["AI", "ML", "DL"])
        assert result == "AI, ML, and DL"
