"""Adaptive response policy for concise, high-quality outputs."""

from dataclasses import dataclass, field
from enum import Enum

from app.domain.services.agents.guardrails import InputAnalysisResult, InputIssueType


class VerbosityMode(str, Enum):
    """Supported response verbosity modes."""

    CONCISE = "concise"
    STANDARD = "standard"
    DETAILED = "detailed"


@dataclass(slots=True)
class TaskAssessment:
    """Deterministic assessment of task characteristics."""

    complexity_score: float
    risk_score: float
    ambiguity_score: float
    evidence_need_score: float
    confidence_score: float
    needs_clarification: bool
    clarification_questions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResponsePolicy:
    """Execution-safe output policy."""

    mode: VerbosityMode
    force_detailed_reason: str | None = None
    min_required_sections: list[str] = field(default_factory=list)
    allow_compression: bool = False
    max_chars: int = 4000  # Increased from 1400 to preserve more information


class ResponsePolicyEngine:
    """Evaluates task risk/ambiguity and returns a response policy."""

    _HIGH_RISK_KEYWORDS = (
        "production",
        "security",
        "payment",
        "migration",
        "legal",
        "medical",
        "financial",
        "compliance",
        "delete",
        "drop table",
        "rm -rf",
    )
    _EVIDENCE_KEYWORDS = (
        "latest",
        "today",
        "current",
        "compare",
        "benchmark",
        "source",
        "proof",
        "evidence",
        "numbers",
        "stats",
        "metrics",
        "insights",
        "analysis",
        "analyze",
        "research",
        "report",
        "summarize",
        "summary",
    )
    _AMBIGUOUS_TOKENS = ("it", "this", "that", "something", "anything", "stuff", "things")

    def assess_task(
        self,
        task_description: str,
        complexity_score: float | None = None,
        guardrail_result: InputAnalysisResult | None = None,
    ) -> TaskAssessment:
        """Assess a task before planning/execution."""
        text = (task_description or "").strip()
        words = [word.strip(".,!?;:()[]{}\"'").lower() for word in text.split() if word.strip()]

        risk_score = self._keyword_ratio(words, self._HIGH_RISK_KEYWORDS, weight=0.35)
        evidence_need_score = self._keyword_ratio(words, self._EVIDENCE_KEYWORDS, weight=0.3)

        ambiguity_score = 0.0
        ambiguous_hits = sum(1 for token in words if token in self._AMBIGUOUS_TOKENS)
        if words:
            ambiguity_score += min(0.4, (ambiguous_hits / len(words)) * 2.0)
        if len(words) < 4:
            ambiguity_score += 0.25

        clarification_questions: list[str] = []
        if guardrail_result:
            clarification_questions.extend(guardrail_result.clarification_questions)
            for issue in guardrail_result.issues:
                if issue.issue_type in (InputIssueType.AMBIGUOUS_REQUEST, InputIssueType.UNDERSPECIFIED):
                    ambiguity_score = max(ambiguity_score, issue.severity + 0.2)

        ambiguity_score = self._clamp(ambiguity_score)
        complexity = self._clamp(complexity_score if complexity_score is not None else 0.5)
        confidence_score = self._clamp(0.95 - (0.7 * ambiguity_score) - (0.2 * evidence_need_score))
        needs_clarification = ambiguity_score >= 0.6 or confidence_score < 0.65

        if needs_clarification and not clarification_questions:
            clarification_questions = [
                "Could you clarify the exact outcome you want me to produce?",
                "What constraints or acceptance criteria should I follow?",
            ]

        return TaskAssessment(
            complexity_score=complexity,
            risk_score=risk_score,
            ambiguity_score=ambiguity_score,
            evidence_need_score=evidence_need_score,
            confidence_score=confidence_score,
            needs_clarification=needs_clarification,
            clarification_questions=clarification_questions[:3],
        )

    def decide_policy(
        self,
        assessment: TaskAssessment,
        verbosity_preference: str = "adaptive",
        quality_floor_enforced: bool = True,
    ) -> ResponsePolicy:
        """Choose a response policy from the task assessment."""
        preference = (verbosity_preference or "adaptive").lower()
        force_detailed_reason: str | None = None

        if assessment.risk_score >= 0.7:
            mode = VerbosityMode.DETAILED
            force_detailed_reason = "high-risk-task"
        elif preference == "concise":
            mode = VerbosityMode.CONCISE
        elif preference == "detailed":
            mode = VerbosityMode.DETAILED
        else:
            # Adaptive default: concise only for low-risk, low-ambiguity tasks.
            if (
                assessment.risk_score < 0.45
                and assessment.ambiguity_score < 0.35
                and assessment.complexity_score < 0.45
            ):
                mode = VerbosityMode.CONCISE
            elif assessment.complexity_score >= 0.75 or assessment.evidence_need_score >= 0.7:
                mode = VerbosityMode.DETAILED
            else:
                mode = VerbosityMode.STANDARD

        min_required_sections = ["final result"]
        if assessment.evidence_need_score >= 0.45 or assessment.complexity_score >= 0.55:
            min_required_sections.append("artifact references")
        if assessment.risk_score >= 0.45:
            min_required_sections.append("key caveat")
        if mode == VerbosityMode.CONCISE:
            min_required_sections.append("next step")

        allow_compression = mode == VerbosityMode.CONCISE and quality_floor_enforced and assessment.risk_score < 0.7

        return ResponsePolicy(
            mode=mode,
            force_detailed_reason=force_detailed_reason,
            min_required_sections=min_required_sections,
            allow_compression=allow_compression,
            max_chars=4000 if mode == VerbosityMode.CONCISE else 12000,  # Increased from 1400
        )

    def should_request_clarification(self, assessment: TaskAssessment, clarification_policy: str = "auto") -> bool:
        """Determine if execution should pause for user clarification."""
        policy = (clarification_policy or "auto").lower()
        if policy == "never":
            return False
        if policy == "always":
            return True
        return assessment.needs_clarification

    def build_clarification_prompt(self, assessment: TaskAssessment) -> str:
        """Build a concise clarification prompt."""
        lead = "I need one clarification before I continue:"
        question = (
            assessment.clarification_questions[0]
            if assessment.clarification_questions
            else "What should I optimize for first?"
        )
        return f"{lead} {question}"

    @staticmethod
    def _keyword_ratio(words: list[str], keywords: tuple[str, ...], weight: float) -> float:
        if not words:
            return 0.0
        hits = 0
        text = " ".join(words)
        for keyword in keywords:
            if keyword in text:
                hits += 1
        return min(1.0, hits * weight)

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))
