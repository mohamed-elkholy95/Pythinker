"""Tests for critic module models and pure logic.

Tests cover:
- CriticVerdict, ReviewType, FactCheckRecommendation, CheckSeverity enums
- CriticReview, FactCheckResult, CheckResult, FiveCheckResult models
- StructuredImprovement, StructuredFeedback, CriticConfig, ReviewContext
- DataAsymmetryIssue model
- FiveCheckResult helper methods
- _default_check_result factory
"""

import pytest
from pydantic import ValidationError

from app.domain.services.agents.critic import (
    CheckResult,
    CheckSeverity,
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
)

# ── Enums ────────────────────────────────────────────────────────────


class TestCriticVerdict:
    def test_approve(self):
        assert CriticVerdict.APPROVE == "approve"

    def test_revise(self):
        assert CriticVerdict.REVISE == "revise"

    def test_reject(self):
        assert CriticVerdict.REJECT == "reject"

    def test_member_count(self):
        assert len(CriticVerdict) == 3


class TestReviewType:
    def test_general(self):
        assert ReviewType.GENERAL == "general"

    def test_code(self):
        assert ReviewType.CODE == "code"

    def test_research(self):
        assert ReviewType.RESEARCH == "research"

    def test_member_count(self):
        assert len(ReviewType) == 3


class TestFactCheckRecommendation:
    def test_deliver(self):
        assert FactCheckRecommendation.DELIVER == "deliver"

    def test_add_caveats(self):
        assert FactCheckRecommendation.ADD_CAVEATS == "add_caveats"

    def test_needs_verification(self):
        assert FactCheckRecommendation.NEEDS_VERIFICATION == "needs_verification"

    def test_reject(self):
        assert FactCheckRecommendation.REJECT == "reject"


class TestCheckSeverity:
    def test_critical(self):
        assert CheckSeverity.CRITICAL == "critical"

    def test_major(self):
        assert CheckSeverity.MAJOR == "major"

    def test_minor(self):
        assert CheckSeverity.MINOR == "minor"

    def test_pass(self):
        assert CheckSeverity.PASS == "pass"


# ── CriticReview Model ──────────────────────────────────────────────


class TestCriticReview:
    def test_construction(self):
        r = CriticReview(
            verdict=CriticVerdict.APPROVE,
            confidence=0.9,
            summary="Looks good.",
        )
        assert r.verdict == CriticVerdict.APPROVE
        assert r.confidence == 0.9
        assert r.summary == "Looks good."
        assert r.issues == []
        assert r.suggestions == []
        assert r.review_type == ReviewType.GENERAL

    def test_with_issues(self):
        r = CriticReview(
            verdict=CriticVerdict.REVISE,
            confidence=0.6,
            summary="Needs work.",
            issues=["Missing context", "Inaccurate date"],
            suggestions=["Add sources"],
        )
        assert len(r.issues) == 2
        assert len(r.suggestions) == 1

    def test_confidence_bounds_low(self):
        with pytest.raises(ValidationError):
            CriticReview(verdict=CriticVerdict.APPROVE, confidence=-0.1, summary="x")

    def test_confidence_bounds_high(self):
        with pytest.raises(ValidationError):
            CriticReview(verdict=CriticVerdict.APPROVE, confidence=1.1, summary="x")


# ── FactCheckResult Model ───────────────────────────────────────────


class TestFactCheckResult:
    def test_defaults(self):
        r = FactCheckResult(confidence_score=0.8)
        assert r.claims_analyzed == 0
        assert r.verified == 0
        assert r.unverified == 0
        assert r.contradicted == 0
        assert r.red_flags == []
        assert r.recommendation == FactCheckRecommendation.DELIVER
        assert r.caveats_to_add == []

    def test_full_construction(self):
        r = FactCheckResult(
            claims_analyzed=10,
            verified=8,
            unverified=1,
            contradicted=1,
            red_flags=["Contradicted claim about date"],
            confidence_score=0.7,
            recommendation=FactCheckRecommendation.ADD_CAVEATS,
            caveats_to_add=["Date may be inaccurate"],
        )
        assert r.claims_analyzed == 10
        assert r.contradicted == 1


# ── CheckResult Model ───────────────────────────────────────────────


class TestCheckResult:
    def test_defaults(self):
        r = CheckResult()
        assert r.check_name == "unknown"
        assert r.passed is True
        assert r.severity == CheckSeverity.PASS
        assert r.issues == []
        assert r.confidence == 1.0
        assert r.remediation is None

    def test_failed_check(self):
        r = CheckResult(
            check_name="accuracy",
            passed=False,
            severity=CheckSeverity.CRITICAL,
            issues=["Claim X is false"],
            confidence=0.85,
            remediation="Remove claim X",
        )
        assert r.passed is False
        assert r.severity == CheckSeverity.CRITICAL


class TestDefaultCheckResult:
    def test_factory(self):
        r = _default_check_result()
        assert r.check_name == "default"
        assert r.passed is True
        assert r.severity == CheckSeverity.PASS
        assert r.confidence == 0.5


# ── DataAsymmetryIssue Model ────────────────────────────────────────


class TestDataAsymmetryIssue:
    def test_construction(self):
        issue = DataAsymmetryIssue(
            item_a="GPT-4",
            item_a_metric_type="quantitative",
            item_b="Claude",
            item_b_metric_type="qualitative",
            context="Performance comparison",
            suggestion="Use same metric type for both",
        )
        assert issue.item_a == "GPT-4"
        assert issue.item_b_metric_type == "qualitative"


# ── FiveCheckResult Model ───────────────────────────────────────────


class TestFiveCheckResult:
    def test_all_defaults_pass(self):
        r = FiveCheckResult()
        assert r.overall_passed is True
        assert r.overall_confidence == 0.5
        assert r.critical_issues == []

    def test_get_failed_checks_none(self):
        r = FiveCheckResult()
        assert r.get_failed_checks() == []

    def test_get_failed_checks_some(self):
        r = FiveCheckResult(
            accuracy_check=CheckResult(check_name="accuracy", passed=False),
            completeness_check=CheckResult(check_name="completeness", passed=False),
        )
        failed = r.get_failed_checks()
        assert "accuracy" in failed
        assert "completeness" in failed
        assert len(failed) == 2

    def test_has_critical_failures_true(self):
        r = FiveCheckResult(
            accuracy_check=CheckResult(check_name="accuracy", severity=CheckSeverity.CRITICAL),
        )
        assert r.has_critical_failures() is True

    def test_has_critical_failures_false(self):
        r = FiveCheckResult(
            accuracy_check=CheckResult(check_name="accuracy", severity=CheckSeverity.MINOR),
        )
        assert r.has_critical_failures() is False

    def test_get_summary_all_passed(self):
        r = FiveCheckResult()
        summary = r.get_summary()
        assert "All 5 checks passed" in summary
        assert "confidence" in summary

    def test_get_summary_with_failures(self):
        r = FiveCheckResult(
            accuracy_check=CheckResult(check_name="accuracy", passed=False),
        )
        summary = r.get_summary()
        assert "4/5 checks passed" in summary
        assert "accuracy" in summary

    def test_asymmetry_issues(self):
        issue = DataAsymmetryIssue(
            item_a="A",
            item_a_metric_type="quantitative",
            item_b="B",
            item_b_metric_type="none",
            context="ctx",
            suggestion="fix",
        )
        r = FiveCheckResult(asymmetry_issues=[issue])
        assert len(r.asymmetry_issues) == 1


# ── StructuredImprovement Model ─────────────────────────────────────


class TestStructuredImprovement:
    def test_construction(self):
        imp = StructuredImprovement(
            category="accuracy",
            severity="critical",
            issue="Incorrect date",
            fix="Update to correct date",
        )
        assert imp.category == "accuracy"
        assert imp.location is None

    def test_with_location(self):
        imp = StructuredImprovement(
            category="completeness",
            severity="minor",
            issue="Missing section",
            fix="Add conclusions section",
            location="Section 3",
        )
        assert imp.location == "Section 3"


# ── StructuredFeedback Model ────────────────────────────────────────


class TestStructuredFeedback:
    def test_defaults(self):
        fb = StructuredFeedback(overall_quality=0.8)
        assert fb.overall_quality == 0.8
        assert fb.strengths == []
        assert fb.improvements == []
        assert fb.missing_elements == []
        assert fb.priority_order == []

    def test_quality_bounds(self):
        with pytest.raises(ValidationError):
            StructuredFeedback(overall_quality=1.5)


# ── CriticConfig Model ─────────────────────────────────────────────


class TestCriticConfig:
    def test_defaults(self):
        c = CriticConfig()
        assert c.enabled is True
        assert c.min_confidence_threshold == 0.7
        assert c.max_revision_attempts == 2
        assert c.auto_approve_simple_tasks is True
        assert c.review_code_security is True

    def test_custom(self):
        c = CriticConfig(enabled=False, max_revision_attempts=5)
        assert c.enabled is False
        assert c.max_revision_attempts == 5


# ── ReviewContext Dataclass ─────────────────────────────────────────


class TestReviewContext:
    def test_construction_minimal(self):
        ctx = ReviewContext(user_request="Do X", output="Done.")
        assert ctx.user_request == "Do X"
        assert ctx.output == "Done."
        assert ctx.task_context == ""
        assert ctx.review_type == ReviewType.GENERAL

    def test_construction_full(self):
        ctx = ReviewContext(
            user_request="Write code",
            output="def foo(): pass",
            task_context="Python task",
            files=["main.py"],
            sources=["docs"],
            review_type=ReviewType.CODE,
            language="python",
        )
        assert ctx.files == ["main.py"]
        assert ctx.review_type == ReviewType.CODE
