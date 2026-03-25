"""Extended tests for AcknowledgmentGenerator.

Covers paths not exercised by test_plan_act_acknowledgment.py:
- Skill creation, fix/debug, find/search, explain, update, install, test paths
- Helper methods: _is_large_prompt, _compact_subject, _strip_system_instruction_prefix,
  _clean_numbered_topic_item, _join_subjects, _is_reference_design_request
"""

import pytest

from app.domain.services.flows.acknowledgment import AcknowledgmentGenerator


@pytest.fixture()
def gen() -> AcknowledgmentGenerator:
    return AcknowledgmentGenerator()


# ─── Skill creation path ───


class TestAckSkillCreation:
    def test_skill_creator_with_name(self, gen: AcknowledgmentGenerator) -> None:
        result = gen.generate('/skill-creator "my-awesome-skill"')
        assert "my-awesome-skill" in result
        assert "skill creation guidelines" in result.lower()

    def test_skill_creator_bare_name(self, gen: AcknowledgmentGenerator) -> None:
        result = gen.generate("/skill-creator web-scraper")
        assert "web-scraper" in result
        assert "skill creation guidelines" in result.lower()

    def test_skill_creator_no_name(self, gen: AcknowledgmentGenerator) -> None:
        result = gen.generate("/skill-creator")
        assert "create that skill" in result.lower()

    def test_skill_creator_embedded_in_sentence(self, gen: AcknowledgmentGenerator) -> None:
        result = gen.generate('I want to use /skill-creator to build "code-reviewer"')
        assert "code-reviewer" in result
        assert "skill creation guidelines" in result.lower()


# ─── Fix / debug / solve path ───


class TestAckFix:
    def test_fix_short_prompt(self, gen: AcknowledgmentGenerator) -> None:
        result = gen.generate("Fix the login bug")
        assert result == "Got it! I will analyze the issue and work on a solution."

    def test_debug_short_prompt(self, gen: AcknowledgmentGenerator) -> None:
        result = gen.generate("Debug the API endpoint")
        assert "analyze the issue" in result.lower()

    def test_fix_large_prompt(self, gen: AcknowledgmentGenerator) -> None:
        result = gen.generate(
            "Fix the authentication bug that occurs when users try to login with expired tokens. "
            "The error trace shows a NullPointerException in the TokenValidator class. "
            "Please also check the refresh token flow.\n1. Check token validator\n2. Fix refresh flow"
        )
        assert "diagnose the issue" in result.lower()


# ─── Find / search path ───


class TestAckFind:
    def test_locate_non_research(self, gen: AcknowledgmentGenerator) -> None:
        # "locate" is not in RESEARCH_TASK_INDICATORS, so it reaches the find path
        result = gen.generate("Locate the config file on disk")
        assert result == "Got it! I will search for that information."

    def test_find_triggers_research_path(self, gen: AcknowledgmentGenerator) -> None:
        # "find" is a research indicator, so it goes through the research path
        result = gen.generate("Find the best Python libraries")
        assert "research" in result.lower()


# ─── Explain / how does / what is path ───


class TestAckExplain:
    def test_explain(self, gen: AcknowledgmentGenerator) -> None:
        assert gen.generate("Explain how Docker networking works") == "Got it! I will look into that for you."

    def test_what_is(self, gen: AcknowledgmentGenerator) -> None:
        assert gen.generate("What is dependency injection?") == "Got it! I will look into that for you."

    def test_how_does(self, gen: AcknowledgmentGenerator) -> None:
        assert gen.generate("How does the garbage collector work?") == "Got it! I will look into that for you."


# ─── Update / modify path ───


class TestAckUpdate:
    def test_update(self, gen: AcknowledgmentGenerator) -> None:
        assert gen.generate("Update the database schema") == "Got it! I will work on making those changes."

    def test_modify(self, gen: AcknowledgmentGenerator) -> None:
        assert gen.generate("Modify the user profile page") == "Got it! I will work on making those changes."


# ─── Install / setup path ───


class TestAckInstall:
    def test_install(self, gen: AcknowledgmentGenerator) -> None:
        assert gen.generate("Install Redis on the server") == "Got it! I will help you set that up."

    def test_configure(self, gen: AcknowledgmentGenerator) -> None:
        assert gen.generate("Configure nginx as a reverse proxy") == "Got it! I will help you set that up."


# ─── Test / check / verify path ───


class TestAckTest:
    def test_test(self, gen: AcknowledgmentGenerator) -> None:
        assert gen.generate("Test the payment flow") == "Got it! I will run checks on that."

    def test_verify(self, gen: AcknowledgmentGenerator) -> None:
        assert gen.generate("Verify the SSL certificate is valid") == "Got it! I will run checks on that."


# ─── Default path ───


class TestAckDefault:
    def test_default_short(self, gen: AcknowledgmentGenerator) -> None:
        assert gen.generate("Hello") == "Got it! I will help with that."

    def test_default_large_prompt(self, gen: AcknowledgmentGenerator) -> None:
        result = gen.generate("I need you to do several things.\n1. First thing\n2. Second thing")
        assert "structured response" in result.lower()


# ─── _is_large_prompt ───


class TestIsLargePrompt:
    def test_short_prompt_not_large(self, gen: AcknowledgmentGenerator) -> None:
        assert not gen._is_large_prompt("Short message", "Short message")

    def test_long_message_is_large(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._is_large_prompt("x" * 300, "x" * 300)

    def test_long_focus_is_large(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._is_large_prompt("short", "y" * 150)

    def test_newline_is_large(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._is_large_prompt("line one\nline two", "line one")

    def test_numbered_list_is_large(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._is_large_prompt("Do things: 1. First 2. Second", "Do things")


# ─── _compact_subject ───


class TestCompactSubject:
    def test_none_input(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._compact_subject(None) is None

    def test_empty_input(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._compact_subject("") is None

    def test_strips_trailing_punctuation(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._compact_subject("some topic.")
        assert result is not None
        assert not result.endswith(".")

    def test_truncates_long_subject(self, gen: AcknowledgmentGenerator) -> None:
        long_text = " ".join(f"word{i}" for i in range(20))
        result = gen._compact_subject(long_text)
        assert result is not None
        assert len(result.split()) <= 14

    def test_splits_at_semicolon(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._compact_subject("main topic; secondary topic")
        assert result is not None
        assert "secondary" not in result

    def test_removes_report_should_include(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._compact_subject("AI tools the report should include detailed analysis")
        assert result is not None
        assert "report should include" not in result.lower()


# ─── _strip_system_instruction_prefix ───


class TestStripSystemInstructionPrefix:
    def test_strips_for_delimiter(self) -> None:
        text = "Act as a deal finder. Search all stores for: best laptop deals"
        result = AcknowledgmentGenerator._strip_system_instruction_prefix(text)
        assert result == "best laptop deals"

    def test_strips_about_delimiter(self) -> None:
        text = "Research everything about: quantum computing advances"
        result = AcknowledgmentGenerator._strip_system_instruction_prefix(text)
        assert result == "quantum computing advances"

    def test_strips_multi_sentence_instruction(self) -> None:
        text = "Act as an expert. Do thorough research. Find the best options. cursor ai pricing"
        result = AcknowledgmentGenerator._strip_system_instruction_prefix(text)
        assert result == "cursor ai pricing"

    def test_preserves_normal_text(self) -> None:
        text = "What is the best Python framework?"
        result = AcknowledgmentGenerator._strip_system_instruction_prefix(text)
        assert result == text

    def test_short_candidate_not_extracted(self) -> None:
        text = "Search for: ab"
        result = AcknowledgmentGenerator._strip_system_instruction_prefix(text)
        # "ab" is only 2 chars — below the 3-char threshold
        assert result == text


# ─── _clean_numbered_topic_item ───


class TestCleanNumberedTopicItem:
    def test_basic_cleanup(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._clean_numbered_topic_item("  LLM architecture  ")
        assert result == "LLM architecture"

    def test_removes_qualifying_clauses(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._clean_numbered_topic_item("AI tools, including GPT and Claude")
        assert result is not None
        assert "including" not in result

    def test_splits_at_sentence_boundary(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._clean_numbered_topic_item("First topic. Second topic here")
        assert result is not None
        assert "Second" not in result

    def test_truncates_long_item(self, gen: AcknowledgmentGenerator) -> None:
        long_item = " ".join(f"word{i}" for i in range(15))
        result = gen._clean_numbered_topic_item(long_item)
        assert result is not None
        assert len(result.split()) <= 11

    def test_none_input(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._clean_numbered_topic_item(None) is None

    def test_empty_input(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._clean_numbered_topic_item("") is None


# ─── _join_subjects ───


class TestJoinSubjects:
    def test_empty_list(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._join_subjects([]) == ""

    def test_single_item(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._join_subjects(["AI tools"]) == "AI tools"

    def test_two_items(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._join_subjects(["AI tools", "ML frameworks"]) == "AI tools and ML frameworks"

    def test_three_items(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._join_subjects(["AI", "ML", "Deep Learning"])
        assert result == "AI, ML, and Deep Learning"


# ─── _is_reference_design_request ───


class TestIsReferenceDesignRequest:
    def test_matches_reference_design(self, gen: AcknowledgmentGenerator) -> None:
        msg = "create a website with global design and standardized buttons and colors based on code.html reference"
        assert gen._is_reference_design_request(msg)

    def test_no_html_file(self, gen: AcknowledgmentGenerator) -> None:
        msg = "create a website with global design and standardized buttons and colors"
        assert not gen._is_reference_design_request(msg)

    def test_no_design_terms(self, gen: AcknowledgmentGenerator) -> None:
        msg = "build an application based on template.html reference"
        assert not gen._is_reference_design_request(msg)


# ─── _normalize_subject ───


class TestNormalizeSubject:
    def test_removes_research_report_prefix(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._normalize_subject("a comprehensive research report on AI safety")
        assert result is not None
        assert not result.lower().startswith("a comprehensive")
        assert "ai safety" in result.lower()

    def test_corrects_typos(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._normalize_subject("comparre sonet 4.5")
        assert result is not None
        assert "compare" in result.lower() or "comparing" in result.lower()
        assert "sonnet" in result.lower()

    def test_converts_imperative_to_gerund(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._normalize_subject("compare Claude and GPT")
        assert result is not None
        assert result.startswith("comparing")

    def test_none_input(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._normalize_subject(None) is None

    def test_empty_input(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._normalize_subject("") is None


# ─── _extract_research_topic ───


class TestExtractResearchTopic:
    def test_research_report_on(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._extract_research_topic("Create a research report on quantum computing")
        assert result is not None
        assert "quantum computing" in result

    def test_research_about(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._extract_research_topic("Research about machine learning trends")
        assert result is not None
        assert "machine learning" in result

    def test_investigate_pattern(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._extract_research_topic("Investigate: the impact of AI on healthcare")
        assert result is not None
        assert "impact" in result.lower()

    def test_bare_research_prefix(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._extract_research_topic("Research best practices for Docker security")
        assert result is not None
        assert "docker" in result.lower() or "best practices" in result.lower()

    def test_no_research_pattern(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._extract_research_topic("Build a web application")
        assert result is None


# ─── _extract_request_focus ───


class TestExtractRequestFocus:
    def test_strips_please_can_you(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._extract_request_focus("Please can you create an API health check endpoint")
        assert result == "an API health check endpoint"

    def test_strips_action_verb(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._extract_request_focus("Build a REST API for user management")
        assert "REST API" in result or "rest api" in result.lower()

    def test_empty_returns_this_task(self, gen: AcknowledgmentGenerator) -> None:
        assert gen._extract_request_focus("") == "this task"

    def test_feature_button_prefix_stripped(self, gen: AcknowledgmentGenerator) -> None:
        result = gen._extract_request_focus(
            "Act as a professional researcher. Search all major sources. "
            "Find comprehensive info for: best Python frameworks 2026"
        )
        assert "best python frameworks 2026" in result.lower()
