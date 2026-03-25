"""Tests for knowledge_gap — GapType, GapSeverity, KnowledgeGap, InformationRequest,
KnowledgeDomain, KnowledgeAssessment.

Covers:
  - Enum members
  - KnowledgeGap: is_blocking, is_fillable_by_tool
  - KnowledgeDomain: has_knowledge, lacks_knowledge
  - KnowledgeAssessment defaults
  - InformationRequest defaults
"""

from __future__ import annotations

from app.domain.models.knowledge_gap import (
    GapSeverity,
    GapType,
    InformationRequest,
    KnowledgeAssessment,
    KnowledgeDomain,
    KnowledgeGap,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    """GapType and GapSeverity enums."""

    def test_gap_types(self) -> None:
        assert GapType.FACTUAL.value == "factual"
        assert GapType.PROCEDURAL.value == "procedural"
        assert GapType.ACCESS.value == "access"
        assert len(GapType) == 6

    def test_gap_severities(self) -> None:
        assert GapSeverity.CRITICAL.value == "critical"
        assert GapSeverity.LOW.value == "low"
        assert len(GapSeverity) == 4


# ---------------------------------------------------------------------------
# KnowledgeGap
# ---------------------------------------------------------------------------


class TestKnowledgeGap:
    """KnowledgeGap model methods."""

    def test_is_blocking_critical(self) -> None:
        gap = KnowledgeGap(
            gap_type=GapType.FACTUAL,
            severity=GapSeverity.CRITICAL,
            description="Missing API key",
            topic="authentication",
        )
        assert gap.is_blocking() is True

    def test_is_not_blocking_high(self) -> None:
        gap = KnowledgeGap(
            gap_type=GapType.FACTUAL,
            severity=GapSeverity.HIGH,
            description="Missing docs",
            topic="docs",
        )
        assert gap.is_blocking() is False

    def test_is_fillable_by_tool_factual(self) -> None:
        gap = KnowledgeGap(
            gap_type=GapType.FACTUAL,
            severity=GapSeverity.MEDIUM,
            description="Need to find pricing",
            topic="pricing",
            can_be_filled=True,
            requires_external=False,
        )
        assert gap.is_fillable_by_tool() is True

    def test_is_fillable_by_tool_contextual(self) -> None:
        gap = KnowledgeGap(
            gap_type=GapType.CONTEXTUAL,
            severity=GapSeverity.LOW,
            description="Need background",
            topic="context",
        )
        assert gap.is_fillable_by_tool() is True

    def test_not_fillable_by_tool_procedural(self) -> None:
        gap = KnowledgeGap(
            gap_type=GapType.PROCEDURAL,
            severity=GapSeverity.MEDIUM,
            description="Don't know how",
            topic="process",
        )
        assert gap.is_fillable_by_tool() is False

    def test_not_fillable_by_tool_requires_external(self) -> None:
        gap = KnowledgeGap(
            gap_type=GapType.FACTUAL,
            severity=GapSeverity.HIGH,
            description="Need external API",
            topic="api",
            requires_external=True,
        )
        assert gap.is_fillable_by_tool() is False

    def test_not_fillable_by_tool_cannot_fill(self) -> None:
        gap = KnowledgeGap(
            gap_type=GapType.FACTUAL,
            severity=GapSeverity.HIGH,
            description="Impossible",
            topic="x",
            can_be_filled=False,
        )
        assert gap.is_fillable_by_tool() is False

    def test_defaults(self) -> None:
        gap = KnowledgeGap(
            gap_type=GapType.FACTUAL,
            severity=GapSeverity.LOW,
            description="desc",
            topic="topic",
        )
        assert gap.can_be_filled is True
        assert gap.requires_external is False
        assert gap.resolution_options == []
        assert gap.id.startswith("gap_")


# ---------------------------------------------------------------------------
# InformationRequest
# ---------------------------------------------------------------------------


class TestInformationRequest:
    """InformationRequest model."""

    def test_defaults(self) -> None:
        req = InformationRequest(
            gap_ids=["gap_1"],
            request_type="search",
            query="how to deploy",
        )
        assert req.priority == 1
        assert req.expected_info is None
        assert req.alternative_queries == []
        assert req.id.startswith("request_")


# ---------------------------------------------------------------------------
# KnowledgeDomain
# ---------------------------------------------------------------------------


class TestKnowledgeDomain:
    """KnowledgeDomain model."""

    def test_has_knowledge_exact(self) -> None:
        domain = KnowledgeDomain(name="Python", known_topics=["asyncio", "typing", "dataclasses"])
        assert domain.has_knowledge("asyncio") is True

    def test_has_knowledge_partial(self) -> None:
        domain = KnowledgeDomain(name="Python", known_topics=["asyncio patterns"])
        assert domain.has_knowledge("asyncio") is True

    def test_has_knowledge_false(self) -> None:
        domain = KnowledgeDomain(name="Python", known_topics=["asyncio"])
        assert domain.has_knowledge("machine learning") is False

    def test_lacks_knowledge_true(self) -> None:
        domain = KnowledgeDomain(name="Python", unknown_topics=["quantum computing"])
        assert domain.lacks_knowledge("quantum computing") is True

    def test_lacks_knowledge_false(self) -> None:
        domain = KnowledgeDomain(name="Python", unknown_topics=["quantum computing"])
        assert domain.lacks_knowledge("web development") is False

    def test_defaults(self) -> None:
        domain = KnowledgeDomain(name="Test")
        assert domain.confidence == 0.5
        assert domain.known_topics == []
        assert domain.unknown_topics == []
        assert domain.limitations == []


# ---------------------------------------------------------------------------
# KnowledgeAssessment
# ---------------------------------------------------------------------------


class TestKnowledgeAssessment:
    """KnowledgeAssessment model."""

    def test_defaults(self) -> None:
        assessment = KnowledgeAssessment(task="Build API")
        assert assessment.overall_confidence == 0.5
        assert assessment.can_proceed is True
        assert assessment.blocking_gaps == []
        assert assessment.gaps == []

    def test_with_gaps(self) -> None:
        gap = KnowledgeGap(
            gap_type=GapType.FACTUAL,
            severity=GapSeverity.CRITICAL,
            description="Missing schema",
            topic="database",
        )
        assessment = KnowledgeAssessment(
            task="Build API",
            gaps=[gap],
            blocking_gaps=[gap.id],
            can_proceed=False,
        )
        assert len(assessment.gaps) == 1
        assert assessment.can_proceed is False
