from app.domain.services.agents.guardrails import InputAnalysisResult, InputIssue, InputIssueType, InputRiskLevel
from app.domain.services.agents.response_policy import ResponsePolicyEngine, VerbosityMode


def test_ambiguous_short_request_requires_clarification() -> None:
    engine = ResponsePolicyEngine()
    assessment = engine.assess_task("Fix it")

    assert assessment.needs_clarification is True
    assert assessment.ambiguity_score >= 0.6
    assert len(assessment.clarification_questions) >= 1


def test_guardrail_ambiguity_increases_clarification_confidence() -> None:
    engine = ResponsePolicyEngine()
    guardrail_result = InputAnalysisResult(
        risk_level=InputRiskLevel.LOW_RISK,
        issues=[
            InputIssue(
                issue_type=InputIssueType.AMBIGUOUS_REQUEST,
                description="Ambiguous reference",
                severity=0.45,
            )
        ],
        clarification_needed=True,
        clarification_questions=["What exactly should I change?"],
    )

    assessment = engine.assess_task(
        task_description="Please update this",
        complexity_score=0.4,
        guardrail_result=guardrail_result,
    )

    assert assessment.needs_clarification is True
    assert "What exactly should I change?" in assessment.clarification_questions


def test_high_risk_task_forces_detailed_mode() -> None:
    engine = ResponsePolicyEngine()
    assessment = engine.assess_task("Perform a production payment migration with security checks")
    policy = engine.decide_policy(assessment)

    assert policy.mode == VerbosityMode.DETAILED
    assert policy.force_detailed_reason == "high-risk-task"


def test_low_risk_task_prefers_concise_mode() -> None:
    engine = ResponsePolicyEngine()
    assessment = engine.assess_task("List files in the project root", complexity_score=0.2)
    policy = engine.decide_policy(assessment)

    assert policy.mode == VerbosityMode.CONCISE
    assert policy.allow_compression is True
