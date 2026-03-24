"""
Tests for pre-trim report direct delivery and richness fallback.

Covers:
- Layer 1: _can_deliver_pretrim_report_directly allows web sessions (not just Telegram)
- Layer 2: Post-summarization richness fallback prefers cached report when LLM output is shallow
- Layer 3: Meta-commentary detection catches artifact-referencing summaries
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.agents.execution import ExecutionAgent

# ---------------------------------------------------------------------------
# Sample content fixtures
# ---------------------------------------------------------------------------

FULL_GUIDE = (
    "# Complete Guide to Passing the Virginia DMV Permit Test\n\n"
    "## Table of Contents\n\n"
    "1. Test Overview\n2. Eligibility\n3. Test Format\n4. Study Strategies\n5. Resources\n\n"
    "## 1. Test Overview\n\n"
    "The Virginia DMV knowledge exam is a computer-based, multiple-choice test "
    "required to obtain a learner's permit or a Virginia driver's license. The exam "
    "tests your understanding of Virginia traffic laws, road signs, safe driving "
    "practices, and rules specific to the Commonwealth.\n\n"
    "## 2. Eligibility & Documents Required\n\n"
    "### Age Requirements\n"
    "- Minimum age for learner's permit: 15 years and 6 months\n"
    "- Minimum age for driver's license: 16 years and 3 months (after holding permit for 9 months)\n\n"
    "### Documents to Bring\n"
    "| Category | Accepted Examples |\n|----------|-------------------|\n"
    "| Identity | U.S. birth certificate, valid U.S. passport, Certificate of Citizenship |\n"
    "| Residency | Utility bill, bank statement, rental agreement with Virginia address |\n"
    "| Social Security | Social Security card, W-2 form, pay stub showing full SSN |\n"
    "| Legal Presence | U.S. birth certificate, U.S. passport, Permanent Resident Card |\n\n"
    "All documents must be original or certified copies. Photocopies are not accepted.\n\n"
    "## 3. Test Format & Structure\n\n"
    "The Virginia DMV knowledge exam is administered on a touchscreen computer.\n\n"
    "| Feature | Details |\n|---------|--------|\n"
    "| Format | Multiple-choice on touchscreen kiosk |\n"
    "| Sections | Part 1 (Traffic Signs) and Part 2 (General Knowledge) |\n"
    "| Total Questions | 10 (Signs) + 25 (General) = 35 total |\n"
    "| Time Limit | No strict limit; most finish in 15-30 minutes |\n"
    "| Retake Policy | If you fail, retake after 15 days |\n\n"
    "### Scoring Requirements\n"
    "| Section | Questions | Passing Score |\n|---------|-----------|---------------|\n"
    "| Part 1: Traffic Signs | 10 | 100% (all correct) |\n"
    "| Part 2: General Knowledge | 25 | 80% (20 out of 25) |\n\n"
    "## 4. Study Strategies\n\n"
    "### Strategy 1: The 3-Phase Plan\n"
    "**Phase 1 (1-2 weeks before):** Read the Virginia Driver's Manual cover to cover. "
    "Highlight key facts: speed limits, BAC limits, sign meanings, right-of-way rules.\n\n"
    "**Phase 2 (1 week before):** Take 2-3 practice tests per day on Driving-Tests.org. "
    "Review every wrong answer carefully. Focus extra time on traffic signs.\n\n"
    "**Phase 3 (1-2 days before):** Retake the official online practice exam. "
    "Review your challenge bank of missed questions.\n\n"
    "### Strategy 2: Key Numbers to Memorize\n"
    "| Fact | Value |\n|------|-------|\n"
    "| Legal BAC (adults 21+) | 0.08% |\n"
    "| Legal BAC (under 21) | 0.02% |\n"
    "| School zone speed limit | 25 mph |\n"
    "| Residential speed limit | 25 mph |\n"
    "| Minimum following distance | 2 seconds |\n\n"
    "## 5. Resources\n\n"
    "- Virginia DMV official website and practice tests\n"
    "- Driving-Tests.org Virginia practice tests\n"
    "- DMV-Permit-Test.com exam simulator\n\n"
    "## References\n\n"
    "[1] Virginia DMV - https://dmv.virginia.gov\n"
    "[2] Driving Tests - https://driving-tests.org\n"
)

SHORT_SUMMARY = (
    "# Virginia DMV Permit Test Guide\n\n"
    "## Key Findings\n"
    "- Two-part exam: 10 signs (100%) + 25 general (80%)\n"
    "- Free practice tests available online\n\n"
    "## Introduction\n"
    "This guide covers the Virginia DMV permit test.\n\n"
    "Key artifacts:\n"
    "- See the full report in `virginia_dmv_permit_test_guide.md`\n"
)

ARTIFACT_REF_SUMMARY = (
    "# Research Summary\n\n"
    "## Key Findings\n"
    "- Finding 1 [1]\n- Finding 2 [2]\n\n"
    "See the full report in `virginia_dmv_permit_test_guide.md`\n\n"
    "## References\n"
    "[1] Source 1\n[2] Source 2\n"
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_agent_repository():
    repo = AsyncMock()
    repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
    repo.save_memory = AsyncMock()
    return repo


@pytest.fixture
def executor(mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
    """Executor without delivery channel (web session)."""
    return ExecutionAgent(
        agent_id="test-pretrim",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        tools=mock_tools,
        json_parser=mock_json_parser,
        feature_flags={"delivery_integrity_gate": True},
    )


@pytest.fixture
def executor_with_telegram(executor):
    """Executor with Telegram delivery channel."""
    executor.set_delivery_channel("telegram")
    return executor


# ===========================================================================
# Layer 1: _can_deliver_pretrim_report_directly — remove Telegram-only gate
# ===========================================================================


class TestPretrimDirectDeliveryGate:
    """Layer 1: Web sessions should be eligible for direct delivery."""

    @staticmethod
    def _setup_coverage_and_gate(executor):
        """Wire up mock coverage validator and delivery gate for direct delivery tests."""
        mock_validator = MagicMock()
        mock_validator.validate.return_value = MagicMock(passed=True, issues=[])
        executor._output_coverage_validator = mock_validator
        # Mock the executor-level gate method (delegates to ResponseGenerator)
        executor._run_delivery_integrity_gate = MagicMock(return_value=(True, []))

    def test_web_session_allowed_when_cache_is_rich(self, executor):
        """Web sessions (no delivery_channel) with a rich pre-trim cache should
        be allowed to deliver directly, skipping the LLM summarization."""
        self._setup_coverage_and_gate(executor)
        executor._pre_trim_report_cache = FULL_GUIDE
        executor._user_request = "Virginia DMV permit test guide"

        result = executor._can_deliver_pretrim_report_directly(
            response_policy=MagicMock(min_required_sections=["final result"]),
            all_steps_completed=True,
            delivery_channel=None,
        )
        assert result is True

    def test_telegram_still_works(self, executor_with_telegram):
        """Telegram delivery should still work (regression guard)."""
        self._setup_coverage_and_gate(executor_with_telegram)
        executor_with_telegram._pre_trim_report_cache = FULL_GUIDE
        executor_with_telegram._user_request = "Virginia DMV permit test guide"

        result = executor_with_telegram._can_deliver_pretrim_report_directly(
            response_policy=MagicMock(min_required_sections=["final result"]),
            all_steps_completed=True,
            delivery_channel="telegram",
        )
        assert result is True

    def test_rejected_when_steps_not_completed(self, executor):
        """Direct delivery requires all steps completed."""
        executor._pre_trim_report_cache = FULL_GUIDE
        result = executor._can_deliver_pretrim_report_directly(
            response_policy=MagicMock(min_required_sections=["final result"]),
            all_steps_completed=False,
            delivery_channel=None,
        )
        assert result is False

    def test_rejected_when_cache_empty(self, executor):
        """Direct delivery requires non-empty cache."""
        executor._pre_trim_report_cache = ""
        result = executor._can_deliver_pretrim_report_directly(
            response_policy=MagicMock(min_required_sections=["final result"]),
            all_steps_completed=True,
            delivery_channel=None,
        )
        assert result is False

    def test_rejected_when_cache_too_short(self, executor):
        """Direct delivery requires minimum length content."""
        executor._pre_trim_report_cache = "# Short\nToo short."
        result = executor._can_deliver_pretrim_report_directly(
            response_policy=MagicMock(min_required_sections=["final result"]),
            all_steps_completed=True,
            delivery_channel=None,
        )
        assert result is False


# ===========================================================================
# Layer 2: Post-summarization richness fallback
# ===========================================================================


class TestRichnessFallback:
    """Layer 2: When the LLM produces a summary much shorter than the cached
    full report, prefer the cached version."""

    def test_prefers_cache_when_summary_much_shorter(self, executor):
        """If pre-trim cache is >=2.5x longer and >=2000 chars, prefer it."""
        result = executor._richness_fallback(
            llm_content=SHORT_SUMMARY,
            pre_trim_cache=FULL_GUIDE,
        )
        assert result == FULL_GUIDE

    def test_keeps_llm_when_lengths_similar(self, executor):
        """If LLM output is close in length to cache, keep the LLM output."""
        similar_length_content = FULL_GUIDE[: len(FULL_GUIDE) - 100]
        result = executor._richness_fallback(
            llm_content=similar_length_content,
            pre_trim_cache=FULL_GUIDE,
        )
        assert result == similar_length_content

    def test_keeps_llm_when_no_cache(self, executor):
        """Without a cache, always keep the LLM output."""
        result = executor._richness_fallback(
            llm_content=SHORT_SUMMARY,
            pre_trim_cache="",
        )
        assert result == SHORT_SUMMARY

    def test_keeps_llm_when_cache_too_short(self, executor):
        """Even if ratio is high, cache must be >=2000 chars to qualify."""
        tiny_cache = "# Title\nSome content here."
        result = executor._richness_fallback(
            llm_content="# T\nShort.",
            pre_trim_cache=tiny_cache,
        )
        assert result == "# T\nShort."

    def test_keeps_llm_when_none_cache(self, executor):
        """None cache should be handled gracefully."""
        result = executor._richness_fallback(
            llm_content=SHORT_SUMMARY,
            pre_trim_cache=None,
        )
        assert result == SHORT_SUMMARY


# ===========================================================================
# Layer 3: Meta-commentary detection for artifact-referencing summaries
# ===========================================================================


class TestArtifactRefMetaCommentary:
    """Layer 3: Short summaries that reference artifacts should be detected
    as meta-commentary so the full cached report can be recovered."""

    def test_detects_artifact_reference_in_short_content(self, executor):
        """A short summary referencing 'See the full report in `file.md`'
        should be flagged as meta-commentary."""
        assert executor._is_meta_commentary(ARTIFACT_REF_SUMMARY) is True

    def test_does_not_flag_long_content_with_artifact_ref(self, executor):
        """Long genuine reports that happen to mention an artifact file
        should NOT be flagged."""
        long_content = FULL_GUIDE + "\nSee also: `extra_data.md`\n"
        assert executor._is_meta_commentary(long_content) is False

    def test_does_not_flag_content_without_artifact_ref(self, executor):
        """Content without artifact references uses normal detection."""
        normal_report = (
            "# Research Report\n\n"
            "## Key Findings\n"
            "- Finding A\n- Finding B\n\n"
            "## Analysis\n"
            "Detailed analysis content here.\n"
        )
        assert executor._is_meta_commentary(normal_report) is False
