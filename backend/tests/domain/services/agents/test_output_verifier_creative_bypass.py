"""Tests for creative/design task bypass in _needs_cove_verification.

Creative and generative tasks (design, build, generate, implement, etc.) have no
external sources to ground against, so hallucination checks produce false positives.
The bypass exits early before the research/comparison checks fire.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.services.agents.output_verifier import OutputVerifier

# ---------------------------------------------------------------------------
# Shared fixture — minimal OutputVerifier instance
# ---------------------------------------------------------------------------

@pytest.fixture()
def verifier() -> OutputVerifier:
    """Minimal OutputVerifier with all injected deps mocked out.

    _needs_cove_verification only uses `self` for logging, so None/MagicMock
    for all deps is sufficient for these unit tests.
    """
    mock_source_tracker = MagicMock()
    mock_source_tracker._collected_sources = []

    return OutputVerifier(
        llm=MagicMock(),
        critic=MagicMock(),
        cove=MagicMock(),
        context_manager=MagicMock(),
        source_tracker=mock_source_tracker,
        resolve_feature_flags_fn=None,
    )


# ---------------------------------------------------------------------------
# Long content helper (> 200 chars) so length gate doesn't fire
# ---------------------------------------------------------------------------

LONG_CONTENT = (
    "This is a detailed design specification for a button component system. "
    "It includes primary, secondary, and ghost variants with hover states, "
    "focus rings, and disabled styles. Each variant uses design tokens for "
    "consistent theming across the entire product design system."
)

assert len(LONG_CONTENT) > 200, "LONG_CONTENT fixture must exceed the 200-char length gate"


# ---------------------------------------------------------------------------
# Creative task bypass — should return False
# ---------------------------------------------------------------------------

class TestCreativeTaskBypass:
    """Creative queries must bypass CoVe regardless of content."""

    def test_create_a_design_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Create a design for: a button component system")
        assert result is False

    def test_design_a_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Design a modern dashboard")
        assert result is False

    def test_design_for_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Design for: a responsive card layout")
        assert result is False

    def test_build_a_component_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Build a React component for a data table")
        assert result is False

    def test_build_a_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Build a REST API wrapper in Python")
        assert result is False

    def test_generate_a_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Generate a login page")
        assert result is False

    def test_create_a_component_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Create a component for displaying user avatars")
        assert result is False

    def test_create_a_page_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Create a page for account settings")
        assert result is False

    def test_implement_a_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Implement a dark mode toggle")
        assert result is False

    def test_make_a_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Make a sidebar navigation component")
        assert result is False

    def test_write_a_component_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Write a component for the checkout flow")
        assert result is False

    def test_code_a_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Code a form validation utility")
        assert result is False

    def test_develop_a_query(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(LONG_CONTENT, "Develop a notification banner component")
        assert result is False

    def test_case_insensitive_query(self, verifier: OutputVerifier) -> None:
        """Creative indicators must match case-insensitively."""
        result = verifier.needs_verification(LONG_CONTENT, "DESIGN A mobile navigation bar")
        assert result is False

    def test_query_with_extra_context(self, verifier: OutputVerifier) -> None:
        """Creative indicator embedded inside a longer query."""
        result = verifier.needs_verification(
            LONG_CONTENT,
            "Please design a button component system using Tailwind CSS with primary/secondary/ghost variants",
        )
        assert result is False


# ---------------------------------------------------------------------------
# Length gate — content under 200 chars returns False even for design queries
# ---------------------------------------------------------------------------

class TestLengthGate:
    def test_short_content_creative_query_returns_false(self, verifier: OutputVerifier) -> None:
        short = "Short content."
        assert len(short) < 200
        result = verifier.needs_verification(short, "Design a button")
        assert result is False


# ---------------------------------------------------------------------------
# No regression — factual/research tasks must still return True
# ---------------------------------------------------------------------------

FACTUAL_CONTENT = (
    "Python 3.12 was released in 2023 and delivers a 25% performance improvement "
    "over Python 3.11 on the standard benchmarks. The CPython interpreter now "
    "generates more optimized bytecode for common patterns. Studies show that "
    "async frameworks like FastAPI achieve 45% higher throughput with these changes. "
    "The performance data was collected using standardised MMLU evaluation suites."
)

assert len(FACTUAL_CONTENT) > 200, "FACTUAL_CONTENT fixture must exceed the 200-char length gate"

COMPARISON_CONTENT = (
    "Docker Swarm versus Kubernetes: in 2024, Kubernetes holds 89% market share "
    "for container orchestration. Benchmarks show Kubernetes scheduling latency of "
    "~150ms versus Swarm's ~40ms for small clusters. However, Kubernetes outperforms "
    "Swarm at scale — clusters of 500+ nodes show 3x higher throughput. "
    "The ranking favours Kubernetes for production workloads above 100 nodes."
)

assert len(COMPARISON_CONTENT) > 200, "COMPARISON_CONTENT fixture must exceed the 200-char length gate"


class TestNoRegression:
    """Factual and comparative queries must still trigger CoVe."""

    def test_research_query_with_percentages_returns_true(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(FACTUAL_CONTENT, "Research the best Python frameworks 2026")
        assert result is True

    def test_compare_query_returns_true(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(COMPARISON_CONTENT, "Compare Docker vs Kubernetes")
        assert result is True

    def test_versus_in_query_returns_true(self, verifier: OutputVerifier) -> None:
        result = verifier.needs_verification(COMPARISON_CONTENT, "Docker Swarm versus Kubernetes performance")
        assert result is True

    def test_benchmark_content_returns_true(self, verifier: OutputVerifier) -> None:
        """Content containing known benchmark names always triggers CoVe."""
        content_with_benchmark = (
            "The MMLU evaluation suite shows GPT-5 achieving 92.3% accuracy, "
            "surpassing the previous state-of-the-art by a wide margin. This result "
            "was validated across 57 academic subjects. The HumanEval pass@1 metric "
            "reached 87.4%, a new record as of 2024. Performance improvements were "
            "confirmed on GSM8K and HellaSwag as well."
        )
        result = verifier.needs_verification(content_with_benchmark, "Analyze GPT-5 benchmark results")
        assert result is True

    def test_report_query_with_factual_claims_returns_true(self, verifier: OutputVerifier) -> None:
        """The word 'report' in a research query must still trigger CoVe for factual content.

        Uses a query that does NOT contain a creative indicator so only the
        research_indicators path is exercised.
        """
        result = verifier.needs_verification(FACTUAL_CONTENT, "Summarize the report on Python performance 2026")
        # 'report' is in research_indicators; content has percentages + MMLU → should verify
        assert result is True
