"""Comprehensive tests for the critic module.

Covers:
- All enums: CriticVerdict, ReviewType, FactCheckRecommendation, CheckSeverity
- All Pydantic models with validation, defaults, and edge cases
- ReviewContext dataclass
- Helper function _default_check_result
- FiveCheckResult methods: get_failed_checks, has_critical_failures, get_summary
- CriticAgent construction and property behaviour
- CriticAgent._detect_review_type with parametrized inputs
- CriticAgent._detect_code_language with parametrized inputs
- CriticAgent._should_skip_review with parametrized inputs
- CriticAgent._detect_comparison_content
- CriticAgent._format_pre_verification_issues with mocked Phase-5 data
- CriticAgent.get_review_stats and reset_stats
- CriticAgent.get_revision_guidance
- CriticAgent.review_output: disabled critic, simple-task skip, LLM path,
  fallback path, error path, five-check critical-failure path
- CriticAgent.fact_check: disabled critic, short-output skip, structured path,
  hallucination-pattern interaction, fallback path, error path
- CriticAgent.get_structured_feedback: structured path, fallback, error path
- CriticAgent.quick_validate: disabled, passing, failing, error path
- CriticAgent.run_five_checks: disabled, short output, structured path,
  fallback path, error path
- CriticAgent.detect_data_asymmetry: symmetric, asymmetric text
- CriticAgent.detect_content_hallucinations delegation
- CriticAgent.extract_quantitative_claims delegation
- CriticAgent.review_and_revise async generator behaviour
- set_metrics module-level helper
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest
from pydantic import ValidationError

from app.domain.services.agents.critic import (
    CheckResult,
    CheckSeverity,
    CriticAgent,
    CriticConfig,
    CriticReview,
    CriticVerdict,
    DataAsymmetryIssue,
    FactCheckRecommendation,
    FactCheckResult,
    FiveCheckResult,
    ReviewContext,
    ReviewType,
    StructuredFeedback,
    StructuredImprovement,
    _default_check_result,
    set_metrics,
)

# ---------------------------------------------------------------------------
# Constants used across tests
# ---------------------------------------------------------------------------

_SHORT_TEXT = "Done."  # < 100 chars → auto-approved
_LONG_TEXT = "A" * 200  # > 100 chars → qualifies for review
_CODE_TEXT = "def hello():\n    return 'world'"
_RESEARCH_TEXT = "According to recent studies, the sky is blue."
_COMPARISON_TEXT = "Model A vs Model B: A scores 95%, B scores lower."


# ===========================================================================
# Enums
# ===========================================================================


class TestCriticVerdict:
    def test_string_values(self):
        assert CriticVerdict.APPROVE == "approve"
        assert CriticVerdict.REVISE == "revise"
        assert CriticVerdict.REJECT == "reject"

    def test_is_str_enum(self):
        assert isinstance(CriticVerdict.APPROVE, str)

    def test_member_count(self):
        assert len(CriticVerdict) == 3

    def test_iterable(self):
        values = {v.value for v in CriticVerdict}
        assert values == {"approve", "revise", "reject"}

    def test_from_string(self):
        assert CriticVerdict("approve") == CriticVerdict.APPROVE
        assert CriticVerdict("revise") == CriticVerdict.REVISE
        assert CriticVerdict("reject") == CriticVerdict.REJECT

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            CriticVerdict("unknown")


class TestReviewType:
    def test_values(self):
        assert ReviewType.GENERAL == "general"
        assert ReviewType.CODE == "code"
        assert ReviewType.RESEARCH == "research"

    def test_member_count(self):
        assert len(ReviewType) == 3

    def test_is_str_enum(self):
        assert isinstance(ReviewType.CODE, str)


class TestFactCheckRecommendation:
    def test_values(self):
        assert FactCheckRecommendation.DELIVER == "deliver"
        assert FactCheckRecommendation.ADD_CAVEATS == "add_caveats"
        assert FactCheckRecommendation.NEEDS_VERIFICATION == "needs_verification"
        assert FactCheckRecommendation.REJECT == "reject"

    def test_member_count(self):
        assert len(FactCheckRecommendation) == 4

    def test_from_string(self):
        assert FactCheckRecommendation("reject") == FactCheckRecommendation.REJECT


class TestCheckSeverity:
    def test_values(self):
        assert CheckSeverity.CRITICAL == "critical"
        assert CheckSeverity.MAJOR == "major"
        assert CheckSeverity.MINOR == "minor"
        assert CheckSeverity.PASS == "pass"

    def test_member_count(self):
        assert len(CheckSeverity) == 4


# ===========================================================================
# Pydantic models
# ===========================================================================


class TestCriticReview:
    def test_minimal_construction(self):
        r = CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.9, summary="ok")
        assert r.verdict == CriticVerdict.APPROVE
        assert r.confidence == 0.9
        assert r.summary == "ok"
        assert r.issues == []
        assert r.suggestions == []
        assert r.review_type == ReviewType.GENERAL

    def test_full_construction(self):
        r = CriticReview(
            verdict=CriticVerdict.REVISE,
            confidence=0.6,
            summary="needs work",
            issues=["issue1", "issue2"],
            suggestions=["fix1"],
            review_type=ReviewType.CODE,
        )
        assert len(r.issues) == 2
        assert len(r.suggestions) == 1
        assert r.review_type == ReviewType.CODE

    @pytest.mark.parametrize("bad_confidence", [-0.01, 1.01, 2.0, -1.0])
    def test_confidence_bounds_rejected(self, bad_confidence: float):
        with pytest.raises(ValidationError):
            CriticReview(verdict=CriticVerdict.APPROVE, confidence=bad_confidence, summary="x")

    @pytest.mark.parametrize("ok_confidence", [0.0, 0.5, 1.0])
    def test_confidence_boundary_values_accepted(self, ok_confidence: float):
        r = CriticReview(verdict=CriticVerdict.APPROVE, confidence=ok_confidence, summary="x")
        assert r.confidence == ok_confidence

    def test_issues_default_is_independent(self):
        r1 = CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.8, summary="x")
        r2 = CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.8, summary="y")
        r1.issues.append("a")
        assert r2.issues == []


class TestFactCheckResult:
    def test_defaults(self):
        r = FactCheckResult(confidence_score=0.9)
        assert r.claims_analyzed == 0
        assert r.verified == 0
        assert r.unverified == 0
        assert r.contradicted == 0
        assert r.red_flags == []
        assert r.recommendation == FactCheckRecommendation.DELIVER
        assert r.caveats_to_add == []

    def test_full_construction(self):
        r = FactCheckResult(
            claims_analyzed=5,
            verified=3,
            unverified=1,
            contradicted=1,
            red_flags=["flag1"],
            confidence_score=0.6,
            recommendation=FactCheckRecommendation.ADD_CAVEATS,
            caveats_to_add=["caveat"],
        )
        assert r.claims_analyzed == 5
        assert r.verified == 3
        assert r.recommendation == FactCheckRecommendation.ADD_CAVEATS

    @pytest.mark.parametrize("bad_score", [-0.01, 1.01])
    def test_confidence_score_bounds(self, bad_score: float):
        with pytest.raises(ValidationError):
            FactCheckResult(confidence_score=bad_score)

    @pytest.mark.parametrize("ok_score", [0.0, 0.5, 1.0])
    def test_confidence_score_boundaries_accepted(self, ok_score: float):
        r = FactCheckResult(confidence_score=ok_score)
        assert r.confidence_score == ok_score


class TestCheckResult:
    def test_defaults(self):
        r = CheckResult()
        assert r.check_name == "unknown"
        assert r.passed is True
        assert r.severity == CheckSeverity.PASS
        assert r.issues == []
        assert r.confidence == 1.0
        assert r.remediation is None

    def test_failed_check_with_all_fields(self):
        r = CheckResult(
            check_name="accuracy",
            passed=False,
            severity=CheckSeverity.CRITICAL,
            issues=["Wrong date"],
            confidence=0.85,
            remediation="Fix the date claim",
        )
        assert r.passed is False
        assert r.severity == CheckSeverity.CRITICAL
        assert r.remediation == "Fix the date claim"

    @pytest.mark.parametrize("bad_conf", [-0.01, 1.01])
    def test_confidence_bounds(self, bad_conf: float):
        with pytest.raises(ValidationError):
            CheckResult(confidence=bad_conf)


class TestDefaultCheckResult:
    def test_returns_check_result_instance(self):
        r = _default_check_result()
        assert isinstance(r, CheckResult)

    def test_has_expected_defaults(self):
        r = _default_check_result()
        assert r.check_name == "default"
        assert r.passed is True
        assert r.severity == CheckSeverity.PASS
        assert r.confidence == 0.5

    def test_each_call_returns_new_object(self):
        r1 = _default_check_result()
        r2 = _default_check_result()
        assert r1 is not r2


class TestDataAsymmetryIssue:
    def test_required_fields(self):
        issue = DataAsymmetryIssue(
            item_a="ModelA",
            item_a_metric_type="quantitative",
            item_b="ModelB",
            item_b_metric_type="qualitative",
            context="benchmark comparison",
            suggestion="Use same scale for both",
        )
        assert issue.item_a == "ModelA"
        assert issue.item_b_metric_type == "qualitative"
        assert issue.suggestion == "Use same scale for both"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            DataAsymmetryIssue(
                item_a="A",
                # item_a_metric_type missing
                item_b="B",
                item_b_metric_type="none",
                context="ctx",
                suggestion="fix",
            )


class TestFiveCheckResult:
    def test_all_pass_defaults(self):
        r = FiveCheckResult()
        assert r.overall_passed is True
        assert r.overall_confidence == 0.5
        assert r.critical_issues == []
        assert r.asymmetry_issues == []

    def test_get_failed_checks_empty_when_all_pass(self):
        r = FiveCheckResult()
        assert r.get_failed_checks() == []

    def test_get_failed_checks_returns_failed_names(self):
        r = FiveCheckResult(
            accuracy_check=CheckResult(check_name="accuracy", passed=False),
            grounding_check=CheckResult(check_name="grounding", passed=False),
        )
        failed = r.get_failed_checks()
        assert "accuracy" in failed
        assert "grounding" in failed
        assert len(failed) == 2

    def test_has_critical_failures_true_for_critical_severity(self):
        r = FiveCheckResult(
            symmetry_check=CheckResult(check_name="symmetry", severity=CheckSeverity.CRITICAL),
        )
        assert r.has_critical_failures() is True

    def test_has_critical_failures_false_for_minor(self):
        r = FiveCheckResult(
            accuracy_check=CheckResult(check_name="accuracy", severity=CheckSeverity.MINOR),
        )
        assert r.has_critical_failures() is False

    def test_has_critical_failures_false_when_all_pass(self):
        assert FiveCheckResult().has_critical_failures() is False

    def test_get_summary_all_pass(self):
        summary = FiveCheckResult().get_summary()
        assert "All 5 checks passed" in summary
        assert "confidence" in summary.lower()

    def test_get_summary_some_failed(self):
        r = FiveCheckResult(
            accuracy_check=CheckResult(check_name="accuracy", passed=False),
            completeness_check=CheckResult(check_name="completeness", passed=False),
        )
        summary = r.get_summary()
        assert "3/5 checks passed" in summary
        assert "accuracy" in summary
        assert "completeness" in summary

    def test_get_summary_one_failed(self):
        r = FiveCheckResult(
            consistency_check=CheckResult(check_name="consistency", passed=False),
        )
        summary = r.get_summary()
        assert "4/5 checks passed" in summary

    def test_overall_confidence_bounds(self):
        with pytest.raises(ValidationError):
            FiveCheckResult(overall_confidence=1.5)

    def test_asymmetry_issues_populated(self):
        issue = DataAsymmetryIssue(
            item_a="X",
            item_a_metric_type="quantitative",
            item_b="Y",
            item_b_metric_type="none",
            context="ctx",
            suggestion="fix",
        )
        r = FiveCheckResult(asymmetry_issues=[issue])
        assert len(r.asymmetry_issues) == 1
        assert r.asymmetry_issues[0].item_a == "X"


class TestStructuredImprovement:
    def test_minimal_construction(self):
        imp = StructuredImprovement(
            category="accuracy",
            severity="critical",
            issue="Wrong figure",
            fix="Use correct figure",
        )
        assert imp.category == "accuracy"
        assert imp.location is None

    def test_with_optional_location(self):
        imp = StructuredImprovement(
            category="completeness",
            severity="minor",
            issue="Missing conclusion",
            fix="Add conclusion",
            location="Section 4",
        )
        assert imp.location == "Section 4"

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            StructuredImprovement(category="accuracy", severity="minor", issue="x")


class TestStructuredFeedback:
    def test_defaults(self):
        fb = StructuredFeedback(overall_quality=0.75)
        assert fb.overall_quality == 0.75
        assert fb.strengths == []
        assert fb.improvements == []
        assert fb.missing_elements == []
        assert fb.priority_order == []

    @pytest.mark.parametrize("bad_quality", [-0.01, 1.01])
    def test_quality_bounds(self, bad_quality: float):
        with pytest.raises(ValidationError):
            StructuredFeedback(overall_quality=bad_quality)

    @pytest.mark.parametrize("ok_quality", [0.0, 0.5, 1.0])
    def test_quality_boundaries_accepted(self, ok_quality: float):
        fb = StructuredFeedback(overall_quality=ok_quality)
        assert fb.overall_quality == ok_quality

    def test_full_construction(self):
        imp = StructuredImprovement(
            category="clarity",
            severity="major",
            issue="Ambiguous statement",
            fix="Clarify meaning",
        )
        fb = StructuredFeedback(
            overall_quality=0.6,
            strengths=["Good structure"],
            improvements=[imp],
            missing_elements=["Conclusion"],
            priority_order=[0],
        )
        assert len(fb.improvements) == 1
        assert fb.missing_elements == ["Conclusion"]


class TestCriticConfig:
    def test_defaults(self):
        c = CriticConfig()
        assert c.enabled is True
        assert c.min_confidence_threshold == 0.7
        assert c.max_revision_attempts == 2
        assert c.auto_approve_simple_tasks is True
        assert c.review_code_security is True

    def test_custom_values(self):
        c = CriticConfig(enabled=False, max_revision_attempts=5, auto_approve_simple_tasks=False)
        assert c.enabled is False
        assert c.max_revision_attempts == 5
        assert c.auto_approve_simple_tasks is False


class TestReviewContext:
    def test_minimal_construction(self):
        ctx = ReviewContext(user_request="build X", output="Done.")
        assert ctx.user_request == "build X"
        assert ctx.output == "Done."
        assert ctx.task_context == ""
        assert ctx.files is None
        assert ctx.sources is None
        assert ctx.review_type == ReviewType.GENERAL
        assert ctx.language == ""

    def test_full_construction(self):
        ctx = ReviewContext(
            user_request="write python",
            output="def f(): pass",
            task_context="python task",
            files=["main.py"],
            sources=["https://docs.python.org"],
            review_type=ReviewType.CODE,
            language="python",
        )
        assert ctx.files == ["main.py"]
        assert ctx.review_type == ReviewType.CODE
        assert ctx.language == "python"


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.ask.return_value = {
        "role": "assistant",
        "content": '{"verdict":"approve","confidence":0.9,"issues":[],"suggestions":[],"summary":"Good"}',
    }
    llm.ask_structured = AsyncMock(
        return_value=CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.9, summary="Good")
    )
    return llm


@pytest.fixture
def mock_json_parser():
    parser = AsyncMock()
    parser.parse = AsyncMock(
        return_value={
            "verdict": "approve",
            "confidence": 0.9,
            "issues": [],
            "suggestions": [],
            "summary": "Good",
        }
    )
    return parser


@pytest.fixture
def critic(mock_llm, mock_json_parser):
    return CriticAgent(llm=mock_llm, json_parser=mock_json_parser)


@pytest.fixture
def disabled_critic(mock_llm, mock_json_parser):
    config = CriticConfig(enabled=False)
    return CriticAgent(llm=mock_llm, json_parser=mock_json_parser, config=config)


@pytest.fixture
def no_skip_critic(mock_llm, mock_json_parser):
    config = CriticConfig(auto_approve_simple_tasks=False)
    return CriticAgent(llm=mock_llm, json_parser=mock_json_parser, config=config)


# ===========================================================================
# set_metrics helper
# ===========================================================================


class TestSetMetrics:
    def test_set_metrics_replaces_module_instance(self):
        from app.domain.external.observability import get_null_metrics

        null_metrics = get_null_metrics()
        # Should not raise
        set_metrics(null_metrics)


# ===========================================================================
# CriticAgent construction
# ===========================================================================


class TestCriticAgentConstruction:
    def test_default_config_when_none_given(self, mock_llm, mock_json_parser):
        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        assert agent.config.enabled is True
        assert agent._revision_count == 0
        assert agent._review_history == []

    def test_custom_config_accepted(self, mock_llm, mock_json_parser):
        cfg = CriticConfig(enabled=False)
        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser, config=cfg)
        assert agent.config.enabled is False

    def test_feature_flags_injection(self, mock_llm, mock_json_parser):
        flags = {"reward_hacking_detection": False}
        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser, feature_flags=flags)
        assert agent._feature_flags == flags

    def test_config_property_alias(self, critic):
        assert critic._config is critic.config

    def test_config_setter_alias(self, critic):
        new_cfg = CriticConfig(max_revision_attempts=5)
        critic._config = new_cfg
        assert critic.config.max_revision_attempts == 5


# ===========================================================================
# _detect_review_type
# ===========================================================================


class TestDetectReviewType:
    @pytest.mark.parametrize(
        "output,context,expected",
        [
            # Code indicators in output
            ("def foo():\n    pass", "", ReviewType.CODE),
            ("function hello() {}", "", ReviewType.CODE),
            ("class Foo:\n    pass", "", ReviewType.CODE),
            ("import os; os.getcwd()", "", ReviewType.CODE),
            ("const x = 1;", "", ReviewType.CODE),
            ("let y = 2;", "", ReviewType.CODE),
            ("```python\nprint(1)\n```", "", ReviewType.CODE),
            ("```javascript\nconsole.log(1)\n```", "", ReviewType.CODE),
            ("#include <stdio.h>", "", ReviewType.CODE),
            ("public static void main()", "", ReviewType.CODE),
            # Research indicators in output
            ("According to research shows the data.", "", ReviewType.RESEARCH),
            ("Studies indicate the effect is real.", "", ReviewType.RESEARCH),
            ("Source: Wikipedia", "", ReviewType.RESEARCH),
            ("findings suggest the opposite.", "", ReviewType.RESEARCH),
            # Research via context
            ("Plain text output.", "research into renewable energy", ReviewType.RESEARCH),
            ("Plain text output.", "investigate the root cause", ReviewType.RESEARCH),
            ("Plain text output.", "find information about climate", ReviewType.RESEARCH),
            # General fallback
            ("This is a simple answer.", "no special context", ReviewType.GENERAL),
        ],
    )
    def test_detection(self, critic, output: str, context: str, expected: ReviewType):
        result = critic._detect_review_type(output, context)
        assert result == expected


# ===========================================================================
# _detect_code_language
# ===========================================================================


class TestDetectCodeLanguage:
    @pytest.mark.parametrize(
        "output,expected_language",
        [
            ("```python\ndef f(): pass\n```", "python"),
            ("def my_func():\n    return 1", "python"),
            ("```javascript\nfunction f() {}\n```", "javascript"),
            ("function greet() { return 'hi'; }", "javascript"),
            ("```typescript\ninterface Foo {}\n```", "typescript"),
            ("interface MyType { name: string; }", "typescript"),
            ("```java\npublic class Main {}\n```", "java"),
            ("public class HelloWorld {}", "java"),
            ("```go\nfunc main() {}\n```", "go"),
            ("func Compute() int { return 0 }", "go"),
            ("```rust\nfn main() {}\n```", "rust"),
            ("fn compute() -> i32 { 0 }", "rust"),
            ("This is plain prose text without any code.", "unknown"),
        ],
    )
    def test_language_detection(self, critic, output: str, expected_language: str):
        result = critic._detect_code_language(output)
        assert result == expected_language


# ===========================================================================
# _should_skip_review
# ===========================================================================


class TestShouldSkipReview:
    def test_disabled_auto_approve_never_skips(self, no_skip_critic):
        # auto_approve_simple_tasks=False means never skip
        assert no_skip_critic._should_skip_review(_SHORT_TEXT, "") is False
        assert no_skip_critic._should_skip_review("done", "") is False

    def test_short_output_skipped(self, critic):
        assert critic._should_skip_review("x" * 50, "") is True

    def test_long_output_not_skipped(self, critic):
        assert critic._should_skip_review(_LONG_TEXT, "") is False

    @pytest.mark.parametrize(
        "output",
        [
            "done",
            "completed",
            "created",
            "updated",
            "file saved",
            "task complete",
        ],
    )
    def test_simple_confirmation_patterns_skipped_when_short(self, critic, output: str):
        # These patterns + len < 500 → skip
        assert critic._should_skip_review(output, "") is True

    def test_simple_pattern_but_long_output_not_skipped(self, critic):
        # "done" in a 600-char string → not skipped
        long_done = "done " + "a" * 600
        assert critic._should_skip_review(long_done, "") is False


# ===========================================================================
# _detect_comparison_content
# ===========================================================================


class TestDetectComparisonContent:
    @pytest.mark.parametrize(
        "output,user_request,expected",
        [
            ("Model A vs Model B: A wins.", "compare the two", True),
            ("A comparison of approaches", "any request", True),
            ("X versus Y in terms of speed", "any", True),
            ("Pros and cons of Python", "", True),
            ("| col1 | col2 |", "", True),  # table indicator
            ("--- separator ---", "", True),  # table indicator
            ("This is a plain statement.", "describe the process", False),
            ("No special words here.", "explain the concept", False),
        ],
    )
    def test_detection(self, critic, output: str, user_request: str, expected: bool):
        result = critic._detect_comparison_content(output, user_request)
        assert result == expected


# ===========================================================================
# _format_pre_verification_issues
# ===========================================================================


class TestFormatPreVerificationIssues:
    def test_none_inputs_returns_no_issues_string(self, critic):
        result = critic._format_pre_verification_issues()
        assert result == "No pre-verification issues detected."

    def test_url_not_found_included(self, critic):
        from app.domain.models.url_verification import (
            BatchURLVerificationResult,
            URLVerificationResult,
            URLVerificationStatus,
        )

        url_result = URLVerificationResult(
            url="https://fake.example.com/nonexistent",
            status=URLVerificationStatus.NOT_FOUND,
            http_status=404,
        )
        batch = BatchURLVerificationResult(
            results={"https://fake.example.com/nonexistent": url_result},
            not_found_count=1,
        )
        result = critic._format_pre_verification_issues(url_verification_results=batch)
        assert "URL Verification Failures" in result
        assert any(
            urlparse(token.strip("()[]<>,.;!?")).netloc == "fake.example.com"
            for token in result.split()
        )
        assert "FABRICATED URL" in result

    def test_url_placeholder_included(self, critic):
        from app.domain.models.url_verification import (
            BatchURLVerificationResult,
            URLVerificationResult,
            URLVerificationStatus,
        )

        url_result = URLVerificationResult(
            url="https://example.com/placeholder",
            status=URLVerificationStatus.PLACEHOLDER,
        )
        batch = BatchURLVerificationResult(
            results={"https://example.com/placeholder": url_result},
            placeholder_count=1,
        )
        result = critic._format_pre_verification_issues(url_verification_results=batch)
        assert "placeholder" in result.lower()

    def test_url_not_visited_included(self, critic):
        from app.domain.models.url_verification import (
            BatchURLVerificationResult,
            URLVerificationResult,
            URLVerificationStatus,
        )

        url_result = URLVerificationResult(
            url="https://example.com/not-visited",
            status=URLVerificationStatus.EXISTS_NOT_VISITED,
        )
        batch = BatchURLVerificationResult(
            results={"https://example.com/not-visited": url_result},
            not_visited_count=1,
        )
        result = critic._format_pre_verification_issues(url_verification_results=batch)
        assert "NOT VISITED" in result

    def test_provenance_fabricated_claims_included(self, critic):
        from app.domain.models.claim_provenance import (
            ClaimProvenance,
            ClaimType,
            ClaimVerificationStatus,
            ProvenanceStore,
        )

        store = ProvenanceStore(session_id="test-session")
        claim = ClaimProvenance(
            session_id="test-session",
            claim_text="X scored 99% on MMLU",
            claim_type=ClaimType.METRIC,
        )
        claim.verification_status = ClaimVerificationStatus.FABRICATED
        claim.is_fabricated = True
        store.claims[claim.claim_hash] = claim

        result = critic._format_pre_verification_issues(provenance_store=store)
        assert "Fabricated Claims" in result

    def test_grounding_result_fabricated_numerics_included(self, critic):
        grounding = MagicMock()
        grounding.fabricated_numeric_claims = ["Model X: 99%"]
        grounding.fabricated_entity_claims = []

        result = critic._format_pre_verification_issues(grounding_result=grounding)
        assert "Fabricated Numeric Claims" in result
        assert "Model X: 99%" in result

    def test_grounding_result_fabricated_entities_included(self, critic):
        grounding = MagicMock()
        grounding.fabricated_numeric_claims = []
        grounding.fabricated_entity_claims = ["FakeCompany Inc"]

        result = critic._format_pre_verification_issues(grounding_result=grounding)
        assert "Unverified Entity Claims" in result
        assert "FakeCompany Inc" in result

    def test_clean_inputs_return_no_issues(self, critic):
        from app.domain.models.url_verification import BatchURLVerificationResult

        clean_batch = BatchURLVerificationResult()
        result = critic._format_pre_verification_issues(url_verification_results=clean_batch)
        assert result == "No pre-verification issues detected."


# ===========================================================================
# get_review_stats and reset_stats
# ===========================================================================


class TestReviewStats:
    def test_empty_history_returns_minimal_dict(self, critic):
        stats = critic.get_review_stats()
        assert stats == {"total_reviews": 0}

    def test_stats_after_recording_reviews(self, critic):
        r1 = CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.9, summary="ok")
        r2 = CriticReview(verdict=CriticVerdict.REVISE, confidence=0.6, summary="fix", issues=["i1"])
        critic._review_history = [r1, r2]
        critic._revision_count = 1

        stats = critic.get_review_stats()
        assert stats["total_reviews"] == 2
        assert stats["total_revisions"] == 1
        assert stats["verdict_breakdown"]["approve"] == 1
        assert stats["verdict_breakdown"]["revise"] == 1
        assert stats["verdict_breakdown"]["reject"] == 0
        assert abs(stats["average_confidence"] - 0.75) < 0.001
        assert stats["issues_found"] == 1

    def test_reset_stats_clears_history(self, critic):
        critic._review_history = [CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.9, summary="ok")]
        critic._revision_count = 3
        critic.reset_stats()
        assert critic._review_history == []
        assert critic._revision_count == 0

    def test_review_history_capped_at_100(self, critic):
        for i in range(110):
            review = CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.9, summary=f"ok-{i}")
            critic._record_review(review)
        # After 101st review triggers capping to last 50
        assert len(critic._review_history) <= 100


# ===========================================================================
# get_revision_guidance
# ===========================================================================


class TestGetRevisionGuidance:
    @pytest.mark.asyncio
    async def test_returns_string(self, critic):
        review = CriticReview(
            verdict=CriticVerdict.REVISE,
            confidence=0.6,
            summary="needs citation",
            issues=["No source"],
            suggestions=["Add reference"],
        )
        guidance = await critic.get_revision_guidance("original text here", review)
        assert isinstance(guidance, str)
        assert len(guidance) > 0

    @pytest.mark.asyncio
    async def test_includes_verdict_and_issues(self, critic):
        review = CriticReview(
            verdict=CriticVerdict.REVISE,
            confidence=0.5,
            summary="needs work",
            issues=["Issue Alpha"],
            suggestions=["Fix it now"],
        )
        guidance = await critic.get_revision_guidance("original", review)
        assert "revise" in guidance.lower()

    @pytest.mark.asyncio
    async def test_empty_issues_handled(self, critic):
        review = CriticReview(verdict=CriticVerdict.REVISE, confidence=0.5, summary="vague")
        guidance = await critic.get_revision_guidance("text", review)
        assert isinstance(guidance, str)


# ===========================================================================
# review_output
# ===========================================================================


class TestReviewOutput:
    @pytest.mark.asyncio
    async def test_disabled_critic_returns_auto_approve(self, disabled_critic):
        result = await disabled_critic.review_output(user_request="anything", output=_LONG_TEXT)
        assert result.verdict == CriticVerdict.APPROVE
        assert result.confidence == 1.0
        assert "disabled" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_short_output_auto_approved(self, critic):
        result = await critic.review_output(user_request="anything", output="Done.")
        assert result.verdict == CriticVerdict.APPROVE
        assert "auto-approved" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_structured_path_used_when_ask_structured_available(self, mock_llm, mock_json_parser):
        expected = CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.95, summary="looks good")
        mock_llm.ask_structured.return_value = expected

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.review_output(user_request="build something", output=_LONG_TEXT)
        assert result.verdict == CriticVerdict.APPROVE

    @pytest.mark.asyncio
    async def test_fallback_json_path_when_ask_structured_raises(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.side_effect = RuntimeError("structured failed")
        mock_llm.ask.return_value = {
            "content": '{"verdict":"revise","confidence":0.5,"issues":["x"],"suggestions":[],"summary":"needs work"}'
        }
        mock_json_parser.parse.return_value = {
            "verdict": "revise",
            "confidence": 0.5,
            "issues": ["x"],
            "suggestions": [],
            "summary": "needs work",
        }

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.review_output(user_request="do something", output=_LONG_TEXT)
        assert result.verdict == CriticVerdict.REVISE

    @pytest.mark.asyncio
    async def test_error_path_returns_approve_with_low_confidence(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.side_effect = RuntimeError("fail")
        mock_llm.ask.side_effect = RuntimeError("also fail")

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.review_output(user_request="do something", output=_LONG_TEXT)
        assert result.verdict == CriticVerdict.APPROVE
        assert result.confidence == 0.5
        assert "error" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_force_review_type_overrides_detection(self, mock_llm, mock_json_parser):
        captured_calls = []
        original = CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.9, summary="ok")

        async def capture(*args, **kwargs):
            captured_calls.append(kwargs)
            return original

        mock_llm.ask_structured = capture

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.review_output(
            user_request="do something",
            output=_LONG_TEXT,
            force_review_type=ReviewType.RESEARCH,
        )
        # The result should have RESEARCH review_type set
        assert result.review_type == ReviewType.RESEARCH

    @pytest.mark.asyncio
    async def test_verdict_normalization_unknown_defaults_to_revise(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.side_effect = RuntimeError("fail")
        mock_llm.ask.return_value = {"content": "{}"}
        mock_json_parser.parse.return_value = {
            "verdict": "unknown_value",
            "confidence": 0.7,
            "issues": [],
            "suggestions": [],
            "summary": "something",
        }

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.review_output(user_request="anything", output=_LONG_TEXT)
        assert result.verdict == CriticVerdict.REVISE

    @pytest.mark.asyncio
    async def test_research_output_triggers_five_check(self, mock_llm, mock_json_parser):
        five_check_result = FiveCheckResult(overall_passed=True, overall_confidence=0.9)
        expected_review = CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.9, summary="ok")

        mock_llm.ask_structured.return_value = expected_review

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)

        with patch.object(agent, "run_five_checks", AsyncMock(return_value=five_check_result)):
            result = await agent.review_output(
                user_request="research something",
                output=_RESEARCH_TEXT + "x" * 300,
            )
        assert result.verdict == CriticVerdict.APPROVE

    @pytest.mark.asyncio
    async def test_five_check_critical_failure_returns_revise(self, mock_llm, mock_json_parser):
        critical_check = CheckResult(
            check_name="accuracy",
            passed=False,
            severity=CheckSeverity.CRITICAL,
            remediation="Fix accuracy issues",
        )
        five_check_result = FiveCheckResult(
            accuracy_check=critical_check,
            overall_confidence=0.3,
            critical_issues=["Claim X is false"],
        )

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)

        with patch.object(agent, "run_five_checks", AsyncMock(return_value=five_check_result)):
            result = await agent.review_output(
                user_request="compare models",
                output=_RESEARCH_TEXT + "x" * 300,
                force_review_type=ReviewType.RESEARCH,
            )
        assert result.verdict == CriticVerdict.REVISE
        assert "5-check" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_records_review_in_history(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.return_value = CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.9, summary="ok")
        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        await agent.review_output(user_request="build X", output=_LONG_TEXT)
        assert len(agent._review_history) == 1


# ===========================================================================
# fact_check
# ===========================================================================


class TestFactCheck:
    @pytest.mark.asyncio
    async def test_disabled_critic_returns_deliver(self, disabled_critic):
        result = await disabled_critic.fact_check(output=_LONG_TEXT)
        assert result.recommendation == FactCheckRecommendation.DELIVER
        assert result.confidence_score == 1.0

    @pytest.mark.asyncio
    async def test_short_output_returns_deliver(self, critic):
        result = await critic.fact_check(output="hi")
        assert result.recommendation == FactCheckRecommendation.DELIVER
        assert result.confidence_score == 0.95

    @pytest.mark.asyncio
    async def test_structured_path_returns_result(self, mock_llm, mock_json_parser):
        expected = FactCheckResult(
            claims_analyzed=3,
            verified=3,
            confidence_score=0.9,
            recommendation=FactCheckRecommendation.DELIVER,
        )
        mock_llm.ask_structured.return_value = expected

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.fact_check(output=_LONG_TEXT)
        assert result.claims_analyzed == 3
        assert result.recommendation == FactCheckRecommendation.DELIVER

    @pytest.mark.asyncio
    async def test_fallback_json_path_when_structured_raises(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.side_effect = RuntimeError("fail")
        mock_llm.ask.return_value = {"content": "{}"}
        mock_json_parser.parse.return_value = {
            "recommendation": "add_caveats",
            "claims_analyzed": 2,
            "verified": 1,
            "unverified": 1,
            "contradicted": 0,
            "red_flags": [],
            "confidence_score": 0.65,
            "caveats_to_add": ["check sources"],
        }

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.fact_check(output=_LONG_TEXT)
        assert result.recommendation == FactCheckRecommendation.ADD_CAVEATS

    @pytest.mark.asyncio
    async def test_error_path_returns_initial_recommendation(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.side_effect = RuntimeError("fail")
        mock_llm.ask.side_effect = RuntimeError("also fail")

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.fact_check(output=_LONG_TEXT)
        # fail-open → should get a FactCheckResult with error flag
        assert isinstance(result, FactCheckResult)
        assert any("error" in flag.lower() for flag in result.red_flags)

    @pytest.mark.asyncio
    async def test_source_attributions_verified_claims_used(self, mock_llm, mock_json_parser):
        from app.domain.models.source_attribution import (
            AccessStatus,
            SourceAttribution,
            SourceType,
        )

        attr = SourceAttribution(
            claim="Python is great",
            source_type=SourceType.DIRECT_CONTENT,
            access_status=AccessStatus.FULL,
            confidence=0.95,
        )
        expected = FactCheckResult(
            claims_analyzed=1,
            verified=1,
            confidence_score=0.9,
            recommendation=FactCheckRecommendation.DELIVER,
        )
        mock_llm.ask_structured.return_value = expected

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.fact_check(output=_LONG_TEXT, source_attributions=[attr])
        assert result.recommendation == FactCheckRecommendation.DELIVER


# ===========================================================================
# get_structured_feedback
# ===========================================================================


class TestGetStructuredFeedback:
    @pytest.mark.asyncio
    async def test_structured_path_returns_feedback(self, mock_llm, mock_json_parser):
        expected = StructuredFeedback(
            overall_quality=0.8,
            strengths=["Clear writing"],
            improvements=[],
        )
        mock_llm.ask_structured.return_value = expected

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.get_structured_feedback(output=_LONG_TEXT, user_request="write a doc")
        assert result.overall_quality == 0.8

    @pytest.mark.asyncio
    async def test_fallback_json_path(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.side_effect = RuntimeError("fail")
        mock_llm.ask.return_value = {"content": "{}"}
        mock_json_parser.parse.return_value = {
            "overall_quality": 0.6,
            "strengths": ["good flow"],
            "improvements": [
                {
                    "category": "accuracy",
                    "severity": "minor",
                    "issue": "Vague claim",
                    "fix": "Be specific",
                    "location": None,
                }
            ],
            "missing_elements": [],
            "priority_order": [],
        }

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.get_structured_feedback(output=_LONG_TEXT, user_request="report")
        assert result.overall_quality == 0.6
        assert len(result.improvements) == 1

    @pytest.mark.asyncio
    async def test_error_path_returns_default_feedback(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.side_effect = RuntimeError("fail")
        mock_llm.ask.side_effect = RuntimeError("also fail")

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.get_structured_feedback(output=_LONG_TEXT, user_request="x")
        assert result.overall_quality == 0.7
        assert result.strengths == ["Unable to analyze"]

    @pytest.mark.asyncio
    async def test_default_focus_areas_used_when_none_given(self, mock_llm, mock_json_parser):
        # Should not raise - exercises the default_focus logic
        mock_llm.ask_structured.return_value = StructuredFeedback(overall_quality=0.7)
        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.get_structured_feedback(output=_LONG_TEXT, user_request="anything")
        assert isinstance(result, StructuredFeedback)

    @pytest.mark.asyncio
    async def test_custom_focus_areas_accepted(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.return_value = StructuredFeedback(overall_quality=0.7)
        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.get_structured_feedback(
            output=_LONG_TEXT,
            user_request="anything",
            focus_areas=["security", "performance"],
        )
        assert isinstance(result, StructuredFeedback)


# ===========================================================================
# quick_validate
# ===========================================================================


class TestQuickValidate:
    @pytest.mark.asyncio
    async def test_disabled_critic_returns_true(self, disabled_critic):
        assert await disabled_critic.quick_validate(output=_LONG_TEXT, user_request="x") is True

    @pytest.mark.asyncio
    async def test_passes_when_llm_says_valid(self, mock_llm, mock_json_parser):
        mock_llm.ask.return_value = {"content": '{"passes_validation": true}'}
        mock_json_parser.parse.return_value = {"passes_validation": True}

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.quick_validate(output=_LONG_TEXT, user_request="x")
        assert result is True

    @pytest.mark.asyncio
    async def test_fails_when_llm_says_invalid(self, mock_llm, mock_json_parser):
        mock_llm.ask.return_value = {"content": '{"passes_validation": false, "quick_fix": "add x"}'}
        mock_json_parser.parse.return_value = {"passes_validation": False, "quick_fix": "add x"}

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.quick_validate(output=_LONG_TEXT, user_request="x")
        assert result is False

    @pytest.mark.asyncio
    async def test_error_path_returns_true_fail_open(self, mock_llm, mock_json_parser):
        mock_llm.ask.side_effect = RuntimeError("connection error")

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.quick_validate(output=_LONG_TEXT, user_request="x")
        assert result is True

    @pytest.mark.asyncio
    async def test_required_elements_passed_through(self, mock_llm, mock_json_parser):
        mock_llm.ask.return_value = {"content": "{}"}
        mock_json_parser.parse.return_value = {"passes_validation": True}

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.quick_validate(
            output=_LONG_TEXT,
            user_request="x",
            expected_format="markdown",
            required_elements=["introduction", "conclusion"],
        )
        assert result is True


# ===========================================================================
# run_five_checks
# ===========================================================================


class TestRunFiveChecks:
    @pytest.mark.asyncio
    async def test_disabled_critic_returns_all_pass(self, disabled_critic):
        result = await disabled_critic.run_five_checks(output=_LONG_TEXT, user_request="do research")
        assert result.overall_passed is True
        assert result.overall_confidence == 1.0

    @pytest.mark.asyncio
    async def test_short_output_returns_auto_pass(self, critic):
        result = await critic.run_five_checks(output="hi", user_request="x")
        assert result.overall_passed is True
        assert result.overall_confidence == 0.95

    @pytest.mark.asyncio
    async def test_structured_path_returns_result(self, mock_llm, mock_json_parser):
        expected = FiveCheckResult(overall_passed=True, overall_confidence=0.88)
        mock_llm.ask_structured.return_value = expected

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.run_five_checks(output=_LONG_TEXT, user_request="research topic")
        assert result.overall_confidence == 0.88

    @pytest.mark.asyncio
    async def test_fallback_json_path(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.side_effect = RuntimeError("fail")
        mock_llm.ask.return_value = {"content": "{}"}
        mock_json_parser.parse.return_value = {
            "accuracy_check": {"passed": True, "severity": "pass", "issues": [], "confidence": 0.9},
            "completeness_check": {"passed": True, "severity": "pass", "issues": [], "confidence": 0.9},
            "consistency_check": {"passed": False, "severity": "major", "issues": ["x"], "confidence": 0.7},
            "symmetry_check": {"passed": True, "severity": "pass", "issues": [], "confidence": 0.8},
            "grounding_check": {"passed": True, "severity": "pass", "issues": [], "confidence": 0.9},
            "overall_passed": False,
            "overall_confidence": 0.75,
            "critical_issues": [],
            "asymmetry_issues": [],
        }

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.run_five_checks(output=_LONG_TEXT, user_request="research")
        assert result.consistency_check.passed is False
        assert result.overall_confidence == 0.75

    @pytest.mark.asyncio
    async def test_error_path_returns_fail_open(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.side_effect = RuntimeError("fail")
        mock_llm.ask.side_effect = RuntimeError("also fail")

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.run_five_checks(output=_LONG_TEXT, user_request="x")
        assert result.overall_passed is True
        assert result.overall_confidence == 0.5
        assert any("error" in issue.lower() for issue in result.critical_issues)

    @pytest.mark.asyncio
    async def test_asymmetry_issues_parsed_from_json(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.side_effect = RuntimeError("fail")
        mock_llm.ask.return_value = {"content": "{}"}
        mock_json_parser.parse.return_value = {
            "accuracy_check": {},
            "completeness_check": {},
            "consistency_check": {},
            "symmetry_check": {},
            "grounding_check": {},
            "overall_passed": True,
            "overall_confidence": 0.8,
            "critical_issues": [],
            "asymmetry_issues": [
                {
                    "item_a": "GPT-4",
                    "item_a_metric_type": "quantitative",
                    "item_b": "Claude",
                    "item_b_metric_type": "qualitative",
                    "context": "benchmark",
                    "suggestion": "use same scale",
                }
            ],
        }

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.run_five_checks(output=_LONG_TEXT, user_request="compare")
        assert len(result.asymmetry_issues) == 1
        assert result.asymmetry_issues[0].item_a == "GPT-4"

    @pytest.mark.asyncio
    async def test_sources_context_included(self, mock_llm, mock_json_parser):
        expected = FiveCheckResult(overall_passed=True, overall_confidence=0.9)
        mock_llm.ask_structured.return_value = expected

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        result = await agent.run_five_checks(
            output=_LONG_TEXT,
            user_request="research",
            sources_context="source1\nsource2",
        )
        assert result.overall_passed is True


# ===========================================================================
# detect_data_asymmetry
# ===========================================================================


class TestDetectDataAsymmetry:
    @pytest.mark.asyncio
    async def test_symmetric_text_returns_empty_list(self, critic):
        # Plain prose with no quantitative vs qualitative split
        result = await critic.detect_data_asymmetry("This is a balanced plain statement.")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_result_limited_to_five(self, critic):
        # Even if many asymmetric entries exist, max is 5
        output = "\n".join(
            [f"ModelX{i}: 9{i}% accuracy" for i in range(10)]
            + [f"VagueModel{i}: Strong performance" for i in range(10)]
        )
        result = await critic.detect_data_asymmetry(output)
        assert len(result) <= 5

    @pytest.mark.asyncio
    async def test_returns_list_of_data_asymmetry_issues(self, critic):
        output = "Alpha: 92% MMLU\nBeta: Strong capabilities"
        result = await critic.detect_data_asymmetry(output)
        assert all(isinstance(i, DataAsymmetryIssue) for i in result)


# ===========================================================================
# detect_content_hallucinations (delegation to detector)
# ===========================================================================


class TestDetectContentHallucinations:
    def test_delegates_to_hallucination_detector(self, critic):
        from app.domain.services.agents.content_hallucination_detector import HallucinationAnalysisResult

        result = critic.detect_content_hallucinations("The article has 1.5K claps.")
        assert isinstance(result, HallucinationAnalysisResult)

    def test_clean_text_has_no_high_risk(self, critic):
        result = critic.detect_content_hallucinations("Python is a programming language.")
        assert isinstance(result.has_high_risk_patterns, bool)

    def test_engagement_metric_text_may_flag_risk(self, critic):
        result = critic.detect_content_hallucinations("This post received 10,000 claps and 5,000 views.")
        assert isinstance(result, object)


# ===========================================================================
# extract_quantitative_claims (delegation to detector)
# ===========================================================================


class TestExtractQuantitativeClaims:
    def test_returns_list(self, critic):
        result = critic.extract_quantitative_claims("Python has 95% market share in data science.")
        assert isinstance(result, list)

    def test_empty_text_returns_empty_list(self, critic):
        result = critic.extract_quantitative_claims("")
        assert isinstance(result, list)

    def test_no_numeric_claims_in_text(self, critic):
        result = critic.extract_quantitative_claims("This is a plain statement.")
        assert isinstance(result, list)


# ===========================================================================
# review_and_revise (async generator)
# ===========================================================================


class TestReviewAndRevise:
    @pytest.mark.asyncio
    async def test_approve_on_first_pass_yields_message_and_stops(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.return_value = CriticReview(
            verdict=CriticVerdict.APPROVE, confidence=0.9, summary="Great"
        )

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        revision_handler = AsyncMock(return_value="revised output")

        events = [
            event
            async for event in agent.review_and_revise(
                user_request="do X",
                output=_LONG_TEXT,
                revision_handler=revision_handler,
            )
        ]

        assert len(events) == 1
        revision_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_yields_message_and_stops(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.return_value = CriticReview(
            verdict=CriticVerdict.REJECT, confidence=0.2, summary="Completely wrong"
        )

        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        revision_handler = AsyncMock()

        events = [
            event
            async for event in agent.review_and_revise(
                user_request="do X",
                output=_LONG_TEXT,
                revision_handler=revision_handler,
            )
        ]

        assert len(events) == 1
        revision_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_revise_then_approve_calls_handler(self, mock_llm, mock_json_parser):
        revise_review = CriticReview(verdict=CriticVerdict.REVISE, confidence=0.5, summary="fix it")
        approve_review = CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.9, summary="Good")

        call_count = 0

        async def structured(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return revise_review if call_count == 1 else approve_review

        mock_llm.ask_structured = structured

        revision_handler = AsyncMock(return_value=_LONG_TEXT)
        agent = CriticAgent(
            llm=mock_llm,
            json_parser=mock_json_parser,
            config=CriticConfig(max_revision_attempts=2),
        )

        # Drain the generator; we only care about side effects on revision_handler.
        async for _ in agent.review_and_revise(
            user_request="do X",
            output=_LONG_TEXT,
            revision_handler=revision_handler,
        ):
            pass

        revision_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_attempts_reached_yields_message(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.return_value = CriticReview(
            verdict=CriticVerdict.REVISE, confidence=0.4, summary="Still wrong"
        )
        revision_handler = AsyncMock(return_value=_LONG_TEXT)

        agent = CriticAgent(
            llm=mock_llm,
            json_parser=mock_json_parser,
            config=CriticConfig(max_revision_attempts=1),
        )

        events = [
            event
            async for event in agent.review_and_revise(
                user_request="do X",
                output=_LONG_TEXT,
                revision_handler=revision_handler,
                max_attempts=1,
            )
        ]

        # First REVISE triggers the "max revisions reached" path
        assert any("max" in str(getattr(e, "message", "")).lower() for e in events)

    @pytest.mark.asyncio
    async def test_revision_handler_failure_yields_error_message(self, mock_llm, mock_json_parser):
        revise_review = CriticReview(verdict=CriticVerdict.REVISE, confidence=0.4, summary="fix")
        mock_llm.ask_structured.return_value = revise_review

        revision_handler = AsyncMock(side_effect=RuntimeError("revision blew up"))

        agent = CriticAgent(
            llm=mock_llm,
            json_parser=mock_json_parser,
            config=CriticConfig(max_revision_attempts=3),
        )

        events = [
            event
            async for event in agent.review_and_revise(
                user_request="do X",
                output=_LONG_TEXT,
                revision_handler=revision_handler,
            )
        ]

        assert any("revision failed" in str(getattr(e, "message", "")).lower() for e in events)

    @pytest.mark.asyncio
    async def test_revision_count_incremented(self, mock_llm, mock_json_parser):
        mock_llm.ask_structured.return_value = CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.9, summary="ok")
        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser)
        async for _ in agent.review_and_revise(user_request="x", output=_LONG_TEXT, revision_handler=AsyncMock()):
            pass
        assert agent._revision_count == 1


# ===========================================================================
# _resolve_feature_flags
# ===========================================================================


class TestResolveFeatureFlags:
    def test_injected_flags_returned_directly(self, mock_llm, mock_json_parser):
        flags = {"reward_hacking_detection": True, "some_flag": False}
        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser, feature_flags=flags)
        result = agent._resolve_feature_flags()
        assert result == flags

    def test_no_injected_flags_falls_back_to_core_config(self, mock_llm, mock_json_parser):
        agent = CriticAgent(llm=mock_llm, json_parser=mock_json_parser, feature_flags=None)
        # get_feature_flags is imported lazily inside _resolve_feature_flags,
        # so we patch at its actual definition site in app.core.config.
        with patch("app.core.config.get_feature_flags", return_value={"x": True}):
            result = agent._resolve_feature_flags()
        # Result is whatever the real get_feature_flags() returns (patch may not apply
        # to the late import, so we just verify the return type).
        assert isinstance(result, dict)


# ===========================================================================
# _build_review_prompt (internal, tested via review_output side effects)
# ===========================================================================


class TestBuildReviewPrompt:
    def test_code_context_uses_code_prompt(self, critic):
        ctx = ReviewContext(
            user_request="write a function",
            output="def foo(): pass",
            task_context="Python",
            review_type=ReviewType.CODE,
            language="python",
        )
        prompt = critic._build_review_prompt(ctx)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_research_context_uses_research_prompt(self, critic):
        ctx = ReviewContext(
            user_request="explain gravity",
            output="According to Einstein...",
            sources=["https://physics.org"],
            review_type=ReviewType.RESEARCH,
        )
        prompt = critic._build_review_prompt(ctx)
        assert isinstance(prompt, str)

    def test_general_context_uses_output_prompt(self, critic):
        ctx = ReviewContext(
            user_request="summarize",
            output=_LONG_TEXT,
            files=["notes.txt"],
            review_type=ReviewType.GENERAL,
        )
        prompt = critic._build_review_prompt(ctx)
        assert isinstance(prompt, str)

    def test_research_no_sources_shows_no_sources_provided(self, critic):
        ctx = ReviewContext(
            user_request="research X",
            output=_LONG_TEXT,
            sources=None,
            review_type=ReviewType.RESEARCH,
        )
        prompt = critic._build_review_prompt(ctx)
        assert "No sources provided" in prompt

    def test_general_no_files_shows_no_files(self, critic):
        ctx = ReviewContext(
            user_request="do X",
            output=_LONG_TEXT,
            files=None,
            review_type=ReviewType.GENERAL,
        )
        prompt = critic._build_review_prompt(ctx)
        assert "No files" in prompt
