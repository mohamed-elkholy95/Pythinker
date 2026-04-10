from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest

from app.domain.services.agents.output_verifier import (
    HallucinationVerificationResult,
    OutputVerifier,
)

# ── HallucinationVerificationResult Tests ─────────────────────────────


class TestHallucinationVerificationResult:
    """Tests for the HallucinationVerificationResult dataclass."""

    def test_default_values(self) -> None:
        result = HallucinationVerificationResult(content="test")
        assert result.content == "test"
        assert result.blocking_issues == []
        assert result.warnings == []
        assert result.hallucination_ratio is None
        assert result.span_count == 0
        assert result.skipped is False

    def test_with_all_fields(self) -> None:
        result = HallucinationVerificationResult(
            content="verified content",
            blocking_issues=["hallucination_ratio_critical"],
            warnings=["hallucination_detected"],
            hallucination_ratio=0.65,
            span_count=5,
            skipped=False,
        )
        assert result.content == "verified content"
        assert result.blocking_issues == ["hallucination_ratio_critical"]
        assert result.warnings == ["hallucination_detected"]
        assert result.hallucination_ratio == 0.65
        assert result.span_count == 5

    def test_skipped_result(self) -> None:
        result = HallucinationVerificationResult(
            content="original",
            warnings=["hallucination_verification_skipped"],
            skipped=True,
        )
        assert result.skipped is True
        assert result.content == "original"

    def test_empty_content(self) -> None:
        result = HallucinationVerificationResult(content="")
        assert result.content == ""

    def test_has_slots(self) -> None:
        assert hasattr(HallucinationVerificationResult, "__slots__")

    def test_mutable_lists_independent(self) -> None:
        r1 = HallucinationVerificationResult(content="a")
        r2 = HallucinationVerificationResult(content="b")
        r1.blocking_issues.append("x")
        assert r2.blocking_issues == []

    def test_hallucination_ratio_zero(self) -> None:
        result = HallucinationVerificationResult(content="clean", hallucination_ratio=0.0)
        assert result.hallucination_ratio == 0.0

    def test_hallucination_ratio_one(self) -> None:
        result = HallucinationVerificationResult(content="bad", hallucination_ratio=1.0)
        assert result.hallucination_ratio == 1.0


# ── OutputVerifier Construction Tests ──────────────────────────────────


class TestOutputVerifierConstruction:
    """Tests for OutputVerifier initialization."""

    @pytest.fixture()
    def mock_deps(self) -> dict:
        mock_llm = MagicMock()
        mock_critic = MagicMock()
        mock_context_manager = MagicMock()
        mock_source_tracker = MagicMock()
        mock_source_tracker._collected_sources = []
        return {
            "llm": mock_llm,
            "critic": mock_critic,
            "context_manager": mock_context_manager,
            "source_tracker": mock_source_tracker,
        }

    def test_basic_construction(self, mock_deps: dict) -> None:
        verifier = OutputVerifier(**mock_deps)
        assert verifier._hallucination_verification_enabled is True
        assert verifier._user_request is None
        assert verifier._step_sources == []

    def test_construction_with_verification_disabled(self, mock_deps: dict) -> None:
        verifier = OutputVerifier(**mock_deps, hallucination_verification_enabled=False)
        assert verifier._hallucination_verification_enabled is False

    def test_set_user_request(self, mock_deps: dict) -> None:
        verifier = OutputVerifier(**mock_deps)
        verifier.set_user_request("test query")
        assert verifier._user_request == "test query"

    def test_set_user_request_none(self, mock_deps: dict) -> None:
        verifier = OutputVerifier(**mock_deps)
        verifier.set_user_request(None)
        assert verifier._user_request is None


# ── Step Source Tests ──────────────────────────────────────────────────


class TestStepSources:
    """Tests for per-step source accumulation."""

    @pytest.fixture()
    def verifier(self) -> OutputVerifier:
        return OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=MagicMock(),
            source_tracker=MagicMock(_collected_sources=[]),
        )

    def test_add_step_source(self, verifier: OutputVerifier) -> None:
        verifier.add_step_source("Title", "https://example.com", "Some content here")
        assert len(verifier._step_sources) == 1
        assert "Title" in verifier._step_sources[0]
        source_line = verifier._step_sources[0].splitlines()[0]
        parsed = urlparse(source_line[source_line.index("(") + 1 : -1])
        assert parsed.netloc == "example.com"

    def test_add_step_source_empty_snippet_ignored(self, verifier: OutputVerifier) -> None:
        verifier.add_step_source("Title", "https://example.com", "")
        assert len(verifier._step_sources) == 0

    def test_add_step_source_whitespace_snippet_ignored(self, verifier: OutputVerifier) -> None:
        verifier.add_step_source("Title", "https://example.com", "   ")
        assert len(verifier._step_sources) == 0

    def test_add_step_source_none_snippet_ignored(self, verifier: OutputVerifier) -> None:
        verifier.add_step_source("Title", "https://example.com", None)
        assert len(verifier._step_sources) == 0

    def test_add_step_source_truncates_at_500_chars(self, verifier: OutputVerifier) -> None:
        long_snippet = "x" * 1000
        verifier.add_step_source("Title", "url", long_snippet)
        assert len(verifier._step_sources[0]) < 600

    def test_clear_step_sources(self, verifier: OutputVerifier) -> None:
        verifier.add_step_source("Title", "url", "content")
        verifier.add_step_source("Title2", "url2", "content2")
        verifier.clear_step_sources()
        assert verifier._step_sources == []

    def test_multiple_sources(self, verifier: OutputVerifier) -> None:
        for i in range(5):
            verifier.add_step_source(f"Title {i}", f"url-{i}", f"Content {i}")
        assert len(verifier._step_sources) == 5


# ── Feature Flags Tests ───────────────────────────────────────────────


class TestFeatureFlags:
    """Tests for feature flag resolution."""

    def test_no_resolver_returns_empty(self) -> None:
        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=MagicMock(),
            source_tracker=MagicMock(_collected_sources=[]),
        )
        result = verifier._resolve_feature_flags()
        assert result == {}

    def test_resolver_returns_flags(self) -> None:
        flags = {"hallucination_verification": True, "critic_revision": False}
        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=MagicMock(),
            source_tracker=MagicMock(_collected_sources=[]),
            resolve_feature_flags_fn=lambda: flags,
        )
        result = verifier._resolve_feature_flags()
        assert result == flags

    def test_resolver_exception_returns_empty(self) -> None:
        def bad_resolver():
            raise RuntimeError("flag service down")

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=MagicMock(),
            source_tracker=MagicMock(_collected_sources=[]),
            resolve_feature_flags_fn=bad_resolver,
        )
        result = verifier._resolve_feature_flags()
        assert result == {}


# ── Strip Unverifiable Content Tests ──────────────────────────────────


class TestStripUnverifiableContent:
    """Tests for _strip_unverifiable_content static method."""

    def test_empty_string(self) -> None:
        assert OutputVerifier._strip_unverifiable_content("") == ""

    def test_no_unverifiable_content(self) -> None:
        text = "This is a normal paragraph with factual claims."
        assert OutputVerifier._strip_unverifiable_content(text) == text

    def test_strip_mermaid_block(self) -> None:
        text = "Before\n```mermaid\ngraph TD\nA-->B\n```\nAfter"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "mermaid" not in result
        assert "Before" in result
        assert "After" in result

    def test_strip_graph_block(self) -> None:
        text = "Before\n```graph TD\nA-->B\n```\nAfter"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "graph TD" not in result

    def test_strip_flowchart_block(self) -> None:
        text = "Before\n```flowchart LR\nA-->B\n```\nAfter"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "flowchart" not in result

    def test_strip_sequence_diagram(self) -> None:
        text = "Before\n```sequenceDiagram\nAlice->>Bob: Hi\n```\nAfter"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "sequenceDiagram" not in result

    def test_strip_class_diagram(self) -> None:
        text = "Before\n```classDiagram\nClass01 <|-- Class02\n```\nAfter"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "classDiagram" not in result

    def test_strip_state_diagram(self) -> None:
        text = "Before\n```stateDiagram\n[*] --> Active\n```\nAfter"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "stateDiagram" not in result

    def test_strip_gantt_diagram(self) -> None:
        text = "Before\n```gantt\ntitle A Gantt\n```\nAfter"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "gantt" not in result

    def test_strip_pie_chart(self) -> None:
        text = 'Before\n```pie\n"A": 50\n"B": 50\n```\nAfter'
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "pie" not in result

    def test_strip_er_diagram(self) -> None:
        text = "Before\n```erDiagram\nCUSTOMER ||--o{ ORDER : places\n```\nAfter"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "erDiagram" not in result

    def test_strip_multiple_mermaid_blocks(self) -> None:
        text = "```mermaid\ngraph TD\n```\nMiddle\n```flowchart LR\nA-->B\n```"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "mermaid" not in result
        assert "flowchart" not in result
        assert "Middle" in result

    def test_strip_reference_section(self) -> None:
        text = "Main content here.\n## References\nhttps://example.com/1\nhttps://example.com/2\n"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "Main content here." in result

    def test_strip_sources_section(self) -> None:
        text = "Main content.\n### Sources\nhttps://example.com/source1\nhttps://example.com/source2\n"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "Main content." in result

    def test_strip_bibliography_section(self) -> None:
        text = "Main content.\n## Bibliography\nhttps://example.com/bib1\n"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "Main content." in result

    def test_strip_bare_url_lines(self) -> None:
        text = "Content here.\n[1] Source - https://example.com\n[2] https://other.com\nMore content."
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "Content here." in result
        assert "More content." in result

    def test_preserves_inline_urls(self) -> None:
        text = "According to https://example.com, the data shows improvement."
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "According to" in result

    def test_combined_stripping(self) -> None:
        text = "Facts here.\n```mermaid\ngraph TD\nA-->B\n```\nMore facts.\n## References\nhttps://example.com\n"
        result = OutputVerifier._strip_unverifiable_content(text)
        assert "Facts here." in result
        assert "More facts." in result
        assert "mermaid" not in result


# ── Strip Cited Tables Tests ──────────────────────────────────────────


class TestStripCitedTables:
    """Tests for _strip_cited_tables static method."""

    def test_empty_string(self) -> None:
        assert OutputVerifier._strip_cited_tables("") == ""

    def test_no_tables(self) -> None:
        text = "This is just text without any tables."
        assert OutputVerifier._strip_cited_tables(text) == text

    def test_table_without_citations_preserved(self) -> None:
        text = "| Header1 | Header2 |\n| --- | --- |\n| value1 | value2 |"
        result = OutputVerifier._strip_cited_tables(text)
        assert "value1" in result
        assert "value2" in result

    def test_table_with_citations_stripped(self) -> None:
        text = "Before\n| Model | Score |\n| --- | --- |\n| GPT-4 [1] | 95% |\nAfter"
        result = OutputVerifier._strip_cited_tables(text)
        assert "Before" in result
        assert "After" in result
        assert "GPT-4 [1]" not in result

    def test_table_with_numeric_data_stripped(self) -> None:
        text = (
            "Before\n"
            "| Model | Price | Score |\n"
            "| --- | --- | --- |\n"
            "| GPT-4 | $0.03 | 95.2% |\n"
            "| Claude | $0.015 | 92.1% |\n"
            "After"
        )
        result = OutputVerifier._strip_cited_tables(text)
        assert "Before" in result
        assert "After" in result
        assert "$0.03" not in result

    def test_mixed_tables(self) -> None:
        text = "| No Data |\n| --- |\n| just text |\n---\n| Cited [1] |\n| --- |\n| data [2] |"
        result = OutputVerifier._strip_cited_tables(text)
        assert "just text" in result
        assert "[2]" not in result

    def test_non_table_pipe_not_treated_as_table(self) -> None:
        text = "This | is | not | a | table"
        result = OutputVerifier._strip_cited_tables(text)
        assert text == result


# ── Needs Verification Tests ──────────────────────────────────────────


class TestNeedsVerification:
    """Tests for needs_verification and _needs_cove_verification."""

    @pytest.fixture()
    def verifier(self) -> OutputVerifier:
        return OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=MagicMock(),
            source_tracker=MagicMock(_collected_sources=[]),
        )

    def test_short_content_returns_false(self, verifier: OutputVerifier) -> None:
        assert verifier.needs_verification("short", "query") is False

    def test_short_content_below_threshold(self, verifier: OutputVerifier) -> None:
        content = "a" * 199
        assert verifier.needs_verification(content, "research this") is False

    def test_research_task_with_percentages(self, verifier: OutputVerifier) -> None:
        content = "The benchmark results show 95.2% accuracy " + "x" * 200
        assert verifier.needs_verification(content, "research AI models") is True

    def test_research_task_with_benchmarks(self, verifier: OutputVerifier) -> None:
        content = "On MMLU the model scored well " + "x" * 200
        assert verifier.needs_verification(content, "evaluate model performance") is True

    def test_research_task_with_dates(self, verifier: OutputVerifier) -> None:
        content = "In 2024 the framework was released " + "x" * 200
        assert verifier.needs_verification(content, "research this framework") is True

    def test_comparison_task(self, verifier: OutputVerifier) -> None:
        content = "When comparing these two approaches " + "x" * 200
        assert verifier.needs_verification(content, "compare Python vs Rust") is True

    def test_versus_in_query(self, verifier: OutputVerifier) -> None:
        content = "x" * 250
        assert verifier.needs_verification(content, "GPT-4 vs Claude comparison") is True

    @pytest.mark.parametrize(
        "query",
        [
            "create a design for a dashboard",
            "design a landing page",
            "build a component for user profiles",
            "generate a logo",
            "create a page layout",
            "implement a chat widget",
            "make a todo app",
            "write a component for notifications",
            "code a REST API",
            "develop a microservice",
        ],
    )
    def test_creative_tasks_return_false(self, verifier: OutputVerifier, query: str) -> None:
        content = "Here is the design with 95.2% completion rate " + "x" * 200
        assert verifier.needs_verification(content, query) is False

    def test_empty_query(self, verifier: OutputVerifier) -> None:
        content = "x" * 250
        assert verifier.needs_verification(content, "") is False

    def test_non_research_non_comparison_no_benchmarks(self, verifier: OutputVerifier) -> None:
        content = "This is a regular response about cooking recipes " + "x" * 200
        assert verifier.needs_verification(content, "tell me about cooking") is False

    def test_benchmark_names_in_content(self, verifier: OutputVerifier) -> None:
        content = "The model scores on HumanEval benchmark " + "x" * 200
        assert verifier.needs_verification(content, "any query here") is True

    @pytest.mark.parametrize(
        "benchmark",
        [
            "mmlu",
            "humaneval",
            "gsm8k",
            "hellaswag",
            "arc",
            "winogrande",
        ],
    )
    def test_known_benchmarks(self, verifier: OutputVerifier, benchmark: str) -> None:
        content = f"Results on {benchmark} " + "x" * 250
        assert verifier.needs_verification(content, "review") is True

    def test_ranking_query(self, verifier: OutputVerifier) -> None:
        content = "Top frameworks ranked by performance " + "x" * 200
        assert verifier.needs_verification(content, "ranking of web frameworks") is True

    def test_needs_verification_delegates(self, verifier: OutputVerifier) -> None:
        content = "MMLU results " + "x" * 250
        result1 = verifier.needs_verification(content, "test")
        result2 = verifier._needs_cove_verification(content, "test")
        assert result1 == result2


# ── Build Source Context Tests ────────────────────────────────────────


class TestBuildSourceContext:
    """Tests for build_source_context."""

    def test_empty_sources(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = []
        mock_cm.get_all_insights.return_value = []

        mock_st = MagicMock()
        mock_st._collected_sources = []

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        result = verifier.build_source_context()
        assert result == []

    def test_step_sources_first(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = []
        mock_cm.get_all_insights.return_value = []

        mock_st = MagicMock()
        mock_st._collected_sources = []

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        verifier.add_step_source("Title", "url", "step source content")
        result = verifier.build_source_context()
        assert len(result) >= 1
        assert "step source content" in result[0]

    def test_collected_sources_included(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = []
        mock_cm.get_all_insights.return_value = []

        source = MagicMock()
        source.title = "Test Source"
        source.url = "https://example.com"
        source.snippet = "Important data about X."

        mock_st = MagicMock()
        mock_st._collected_sources = [source]

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        result = verifier.build_source_context()
        assert any("Test Source" in chunk for chunk in result)
        assert any("Important data" in chunk for chunk in result)

    def test_source_with_empty_snippet_and_title(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = []
        mock_cm.get_all_insights.return_value = []

        source = MagicMock()
        source.title = "Just Title"
        source.url = "https://example.com"
        source.snippet = ""

        mock_st = MagicMock()
        mock_st._collected_sources = [source]

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        result = verifier.build_source_context()
        assert any("Just Title" in chunk for chunk in result)

    def test_source_with_no_title_no_snippet_skipped(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = []
        mock_cm.get_all_insights.return_value = []

        source = MagicMock()
        source.title = None
        source.url = None
        source.snippet = ""

        mock_st = MagicMock()
        mock_st._collected_sources = [source]

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        result = verifier.build_source_context()
        assert result == []

    def test_key_facts_included(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = ["This is a key fact that is long enough to be included"]
        mock_cm.get_all_insights.return_value = []

        mock_st = MagicMock()
        mock_st._collected_sources = []

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        result = verifier.build_source_context()
        assert any("key fact" in chunk for chunk in result)

    def test_short_key_facts_excluded(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = ["short"]
        mock_cm.get_all_insights.return_value = []

        mock_st = MagicMock()
        mock_st._collected_sources = []

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        result = verifier.build_source_context()
        assert result == []

    def test_insights_with_high_confidence_included(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = []

        insight = MagicMock()
        insight.confidence = 0.8
        insight.content = "This is a high-confidence insight that is long enough"
        mock_cm.get_all_insights.return_value = [insight]

        mock_st = MagicMock()
        mock_st._collected_sources = []

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        result = verifier.build_source_context()
        assert any("high-confidence insight" in chunk for chunk in result)

    def test_insights_with_low_confidence_excluded(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = []

        insight = MagicMock()
        insight.confidence = 0.5
        insight.content = "This is a low-confidence insight that should be excluded"
        mock_cm.get_all_insights.return_value = [insight]

        mock_st = MagicMock()
        mock_st._collected_sources = []

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        result = verifier.build_source_context()
        assert not any("low-confidence" in chunk for chunk in result)

    def test_short_insights_excluded(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = []

        insight = MagicMock()
        insight.confidence = 0.9
        insight.content = "short"
        mock_cm.get_all_insights.return_value = [insight]

        mock_st = MagicMock()
        mock_st._collected_sources = []

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        result = verifier.build_source_context()
        assert not any("short" in chunk for chunk in result)

    def test_insights_exception_graceful(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = []
        mock_cm.get_all_insights.side_effect = RuntimeError("insights unavailable")

        mock_st = MagicMock()
        mock_st._collected_sources = []

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        result = verifier.build_source_context()
        assert result == []

    def test_title_same_as_url_not_duplicated(self) -> None:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = []
        mock_cm.get_all_insights.return_value = []

        source = MagicMock()
        source.title = "https://example.com"
        source.url = "https://example.com"
        source.snippet = "Some content here."

        mock_st = MagicMock()
        mock_st._collected_sources = [source]

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=mock_st,
        )
        result = verifier.build_source_context()
        assert len(result) == 1
        # Title should not be duplicated when same as URL
        assert result[0].count("https://example.com") == 1


# ── Regex Pattern Tests ───────────────────────────────────────────────


class TestRegexPatterns:
    """Tests for the compiled regex patterns on OutputVerifier."""

    def test_numeric_table_re_matches_dollar(self) -> None:
        assert OutputVerifier._NUMERIC_TABLE_RE.search("$100 per unit")

    def test_numeric_table_re_matches_euro(self) -> None:
        assert OutputVerifier._NUMERIC_TABLE_RE.search("€50.99")

    def test_numeric_table_re_matches_pound(self) -> None:
        assert OutputVerifier._NUMERIC_TABLE_RE.search("£25.50")

    def test_numeric_table_re_matches_percentage(self) -> None:
        assert OutputVerifier._NUMERIC_TABLE_RE.search("95.2%")

    def test_numeric_table_re_matches_points(self) -> None:
        assert OutputVerifier._NUMERIC_TABLE_RE.search("3.5 points")

    def test_numeric_table_re_matches_score_per_dollar(self) -> None:
        assert OutputVerifier._NUMERIC_TABLE_RE.search("score-per-dollar")

    def test_numeric_table_re_no_match_plain_text(self) -> None:
        assert not OutputVerifier._NUMERIC_TABLE_RE.search("just plain text")

    def test_mermaid_block_re_matches(self) -> None:
        text = "```mermaid\ngraph TD\nA-->B\n```"
        assert OutputVerifier._MERMAID_BLOCK_RE.search(text)

    def test_mermaid_block_re_no_match_code(self) -> None:
        text = "```python\nprint('hello')\n```"
        assert not OutputVerifier._MERMAID_BLOCK_RE.search(text)

    def test_reference_section_re_matches(self) -> None:
        text = "## References\nhttps://example.com/1\nhttps://example.com/2\n"
        assert OutputVerifier._REFERENCE_SECTION_RE.search(text)

    def test_bare_url_line_re_matches_numbered(self) -> None:
        assert OutputVerifier._BARE_URL_LINE_RE.search("[1] https://example.com")

    def test_bare_url_line_re_matches_plain(self) -> None:
        assert OutputVerifier._BARE_URL_LINE_RE.search("  https://example.com  ")


# ── Rewrite Without Unsupported Claims Tests ──────────────────────────


class TestRewriteWithoutUnsupportedClaims:
    """Tests for _rewrite_without_unsupported_claims."""

    @pytest.fixture()
    def verifier(self) -> OutputVerifier:
        mock_llm = AsyncMock()
        return OutputVerifier(
            llm=mock_llm,
            critic=MagicMock(),
            context_manager=MagicMock(),
            source_tracker=MagicMock(_collected_sources=[]),
        )

    @pytest.mark.asyncio()
    async def test_no_claims_returns_none(self, verifier: OutputVerifier) -> None:
        result = await verifier._rewrite_without_unsupported_claims("content", [])
        assert result is None

    @pytest.mark.asyncio()
    async def test_successful_rewrite(self, verifier: OutputVerifier) -> None:
        verifier._llm.ask = AsyncMock(return_value={"content": "x" * 500})
        claim = MagicMock()
        claim.claim_text = "GPT-4 scores 100%"
        result = await verifier._rewrite_without_unsupported_claims("original " * 100, [claim])
        assert result is not None
        assert len(result) > 0

    @pytest.mark.asyncio()
    async def test_rewrite_too_short_returns_none(self, verifier: OutputVerifier) -> None:
        verifier._llm.ask = AsyncMock(return_value={"content": "short"})
        claim = MagicMock()
        claim.claim_text = "some claim"
        result = await verifier._rewrite_without_unsupported_claims("original " * 100, [claim])
        assert result is None

    @pytest.mark.asyncio()
    async def test_rewrite_exception_returns_none(self, verifier: OutputVerifier) -> None:
        verifier._llm.ask = AsyncMock(side_effect=RuntimeError("LLM down"))
        claim = MagicMock()
        claim.claim_text = "some claim"
        result = await verifier._rewrite_without_unsupported_claims("content " * 50, [claim])
        assert result is None

    @pytest.mark.asyncio()
    async def test_rewrite_timeout_retries(self, verifier: OutputVerifier) -> None:
        call_count = 0

        async def slow_ask(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            import asyncio

            await asyncio.sleep(1)

        verifier._llm.ask = slow_ask
        claim = MagicMock()
        claim.claim_text = "some claim"
        # Patch timeout via settings (code reads hallucination_rewrite_timeout from config)
        mock_settings = MagicMock()
        mock_settings.hallucination_rewrite_timeout = 0.01
        with (
            patch.object(OutputVerifier, "_REWRITE_TIMEOUT_S", 0.01),
            patch.object(OutputVerifier, "_REWRITE_MAX_RETRIES", 2),
            patch("app.core.config.get_settings", return_value=mock_settings),
        ):
            result = await verifier._rewrite_without_unsupported_claims("content " * 50, [claim])
        assert result is None
        assert call_count == 2


# ── Verify Hallucination Integration Tests ────────────────────────────


class TestVerifyHallucination:
    """Tests for verify_hallucination (integration-style with mocks)."""

    @pytest.fixture()
    def verifier(self) -> OutputVerifier:
        mock_cm = MagicMock()
        mock_cm._context.key_facts = []
        mock_cm.get_all_insights.return_value = []
        mock_cm.add_insight = MagicMock()

        return OutputVerifier(
            llm=AsyncMock(),
            critic=MagicMock(),
            context_manager=mock_cm,
            source_tracker=MagicMock(_collected_sources=[]),
            hallucination_verification_enabled=False,
        )

    @pytest.mark.asyncio()
    async def test_verification_disabled(self, verifier: OutputVerifier) -> None:
        result = await verifier.verify_hallucination("test content", "query")
        assert result.content == "test content"
        assert result.blocking_issues == []

    @pytest.mark.asyncio()
    async def test_apply_hallucination_verification_delegates(self, verifier: OutputVerifier) -> None:
        content = await verifier.apply_hallucination_verification("test", "query")
        assert content == "test"
