"""Tests for context_manager — InsightType, StepInsight, ContextGraph, InsightSynthesizer.

Covers:
  - InsightType enum members
  - StepInsight: id, is_high_confidence, is_actionable, to_context_string
  - ContextGraph: add_insight, add_edge, get_insights_for_step,
    get_related_insights, get_critical_insights, get_blockers, get_learnings,
    to_summary
  - InsightEdge defaults
  - InsightSynthesizer: extract_insights, _match_patterns, _analyze_file_result,
    _extract_tool_insight
"""

from __future__ import annotations

from app.domain.services.agents.context_manager import (
    ContextGraph,
    InsightEdge,
    InsightSynthesizer,
    InsightType,
    StepInsight,
)

# ---------------------------------------------------------------------------
# InsightType enum
# ---------------------------------------------------------------------------


class TestInsightType:
    """InsightType enum members."""

    def test_all_members(self) -> None:
        expected = {
            "discovery",
            "error_learning",
            "decision",
            "dependency",
            "assumption",
            "constraint",
            "progress",
            "blocker",
        }
        assert {m.value for m in InsightType} == expected


# ---------------------------------------------------------------------------
# StepInsight
# ---------------------------------------------------------------------------


class TestStepInsight:
    """StepInsight dataclass properties."""

    def test_id_deterministic(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.DISCOVERY, content="Found X")
        assert si.id == si.id  # Consistent
        assert "s1" in si.id
        assert "discovery" in si.id

    def test_is_high_confidence_true(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.DISCOVERY, content="x", confidence=0.9)
        assert si.is_high_confidence is True

    def test_is_high_confidence_false(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.DISCOVERY, content="x", confidence=0.5)
        assert si.is_high_confidence is False

    def test_is_high_confidence_threshold(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.DISCOVERY, content="x", confidence=0.8)
        assert si.is_high_confidence is True

    def test_is_actionable_blocker(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.BLOCKER, content="x")
        assert si.is_actionable is True

    def test_is_actionable_error_learning(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.ERROR_LEARNING, content="x")
        assert si.is_actionable is True

    def test_is_actionable_constraint(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.CONSTRAINT, content="x")
        assert si.is_actionable is True

    def test_is_not_actionable_discovery(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.DISCOVERY, content="x")
        assert si.is_actionable is False

    def test_is_not_actionable_progress(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.PROGRESS, content="x")
        assert si.is_actionable is False

    def test_to_context_string_discovery(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.DISCOVERY, content="Found a bug")
        s = si.to_context_string()
        assert "Discovered" in s
        assert "Found a bug" in s

    def test_to_context_string_blocker(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.BLOCKER, content="Permission denied")
        s = si.to_context_string()
        assert "Blocked" in s

    def test_to_context_string_error(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.ERROR_LEARNING, content="Timeout issue")
        s = si.to_context_string()
        assert "Learned" in s

    def test_to_context_string_decision(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.DECISION, content="Use approach A")
        s = si.to_context_string()
        assert "Decided" in s

    def test_defaults(self) -> None:
        si = StepInsight(step_id="s1", insight_type=InsightType.DISCOVERY, content="x")
        assert si.confidence == 0.8
        assert si.source_tool is None
        assert si.related_insights == []
        assert si.tags == []
        assert si.metadata == {}


# ---------------------------------------------------------------------------
# InsightEdge
# ---------------------------------------------------------------------------


class TestInsightEdge:
    """InsightEdge dataclass."""

    def test_defaults(self) -> None:
        edge = InsightEdge(from_insight_id="a", to_insight_id="b", relationship="depends_on")
        assert edge.weight == 1.0

    def test_custom_weight(self) -> None:
        edge = InsightEdge(from_insight_id="a", to_insight_id="b", relationship="supports", weight=0.5)
        assert edge.weight == 0.5


# ---------------------------------------------------------------------------
# ContextGraph
# ---------------------------------------------------------------------------


class TestContextGraph:
    """ContextGraph data structure."""

    def _insight(
        self, step_id: str = "s1", itype: InsightType = InsightType.DISCOVERY, content: str = "x"
    ) -> StepInsight:
        return StepInsight(step_id=step_id, insight_type=itype, content=content)

    def test_add_insight(self) -> None:
        g = ContextGraph()
        i = self._insight(content="Found data")
        g.add_insight(i)
        assert i.id in g.insights
        assert "s1" in g.step_insights
        assert i.id in g.step_insights["s1"]

    def test_add_edge(self) -> None:
        g = ContextGraph()
        i1 = self._insight(step_id="s1", content="A")
        i2 = self._insight(step_id="s2", content="B")
        g.add_insight(i1)
        g.add_insight(i2)
        g.add_edge(i1.id, i2.id, "depends_on")
        assert len(g.edges) == 1
        assert i2.id in i1.related_insights

    def test_add_edge_missing_insight(self) -> None:
        g = ContextGraph()
        g.add_edge("missing1", "missing2")
        assert len(g.edges) == 0

    def test_get_insights_for_step(self) -> None:
        g = ContextGraph()
        i1 = self._insight(step_id="s1", content="A")
        i2 = self._insight(step_id="s2", content="B")
        g.add_insight(i1)
        g.add_insight(i2)
        step1 = g.get_insights_for_step("s1")
        assert len(step1) == 1
        assert step1[0].content == "A"

    def test_get_insights_for_step_empty(self) -> None:
        g = ContextGraph()
        assert g.get_insights_for_step("missing") == []

    def test_get_related_insights(self) -> None:
        g = ContextGraph()
        i1 = self._insight(step_id="s1", content="A")
        i2 = self._insight(step_id="s2", content="B")
        i3 = self._insight(step_id="s3", content="C")
        g.add_insight(i1)
        g.add_insight(i2)
        g.add_insight(i3)
        g.add_edge(i1.id, i2.id)
        g.add_edge(i2.id, i3.id)
        related = g.get_related_insights(i1.id, max_depth=2)
        assert len(related) >= 1

    def test_get_related_insights_missing(self) -> None:
        g = ContextGraph()
        assert g.get_related_insights("missing") == []

    def test_get_critical_insights(self) -> None:
        g = ContextGraph()
        blocker = self._insight(step_id="s1", itype=InsightType.BLOCKER, content="blocked")
        progress = self._insight(step_id="s2", itype=InsightType.PROGRESS, content="progressing")
        g.add_insight(blocker)
        g.add_insight(progress)
        critical = g.get_critical_insights(limit=1)
        assert len(critical) == 1
        assert critical[0].insight_type == InsightType.BLOCKER

    def test_get_critical_insights_limit(self) -> None:
        g = ContextGraph()
        for i in range(10):
            g.add_insight(self._insight(step_id=f"s{i}", content=f"insight-{i}"))
        assert len(g.get_critical_insights(limit=3)) == 3

    def test_get_blockers(self) -> None:
        g = ContextGraph()
        g.add_insight(self._insight(itype=InsightType.BLOCKER, content="blocked"))
        g.add_insight(self._insight(step_id="s2", itype=InsightType.DISCOVERY, content="found"))
        assert len(g.get_blockers()) == 1

    def test_get_learnings(self) -> None:
        g = ContextGraph()
        g.add_insight(self._insight(itype=InsightType.ERROR_LEARNING, content="learned"))
        g.add_insight(self._insight(step_id="s2", itype=InsightType.DISCOVERY, content="found"))
        assert len(g.get_learnings()) == 1

    def test_to_summary_empty(self) -> None:
        g = ContextGraph()
        assert g.to_summary() == ""

    def test_to_summary_with_insights(self) -> None:
        g = ContextGraph()
        g.add_insight(self._insight(itype=InsightType.BLOCKER, content="permission denied"))
        g.add_insight(self._insight(step_id="s2", itype=InsightType.DISCOVERY, content="found API endpoint"))
        summary = g.to_summary()
        assert "Context Insights" in summary
        assert "permission denied" in summary

    def test_to_summary_blockers_section(self) -> None:
        g = ContextGraph()
        g.add_insight(self._insight(itype=InsightType.BLOCKER, content="access denied"))
        summary = g.to_summary()
        assert "Active Blockers" in summary

    def test_to_summary_learnings_section(self) -> None:
        g = ContextGraph()
        g.add_insight(self._insight(itype=InsightType.ERROR_LEARNING, content="retry works"))
        summary = g.to_summary()
        assert "Recent Learnings" in summary


# ---------------------------------------------------------------------------
# InsightSynthesizer
# ---------------------------------------------------------------------------


class TestInsightSynthesizer:
    """InsightSynthesizer extraction logic."""

    def test_extract_from_error_result(self) -> None:
        synth = InsightSynthesizer()
        insights = synth.extract_insights(
            step_id="s1",
            tool_name="file_read",
            result="error: File not found /tmp/data.csv",
            success=False,
        )
        assert len(insights) >= 1
        # Should detect error learning
        error_insights = [i for i in insights if i.insight_type == InsightType.ERROR_LEARNING]
        assert len(error_insights) >= 1

    def test_extract_from_success_result(self) -> None:
        synth = InsightSynthesizer()
        insights = synth.extract_insights(
            step_id="s1",
            tool_name="search_web",
            result="found: 10 relevant results about Python async",
            success=True,
        )
        # Should detect discovery
        discoveries = [i for i in insights if i.insight_type == InsightType.DISCOVERY]
        assert len(discoveries) >= 1

    def test_extract_blocker_permission(self) -> None:
        synth = InsightSynthesizer()
        insights = synth.extract_insights(
            step_id="s1",
            tool_name="shell_execute",
            result="permission denied: cannot access /root",
            success=False,
        )
        blockers = [i for i in insights if i.insight_type == InsightType.BLOCKER]
        assert len(blockers) >= 1

    def test_extract_empty_result(self) -> None:
        synth = InsightSynthesizer()
        insights = synth.extract_insights(
            step_id="s1",
            tool_name="file_read",
            result="",
            success=True,
        )
        # Should return empty or minimal insights
        assert isinstance(insights, list)

    def test_extract_none_result(self) -> None:
        synth = InsightSynthesizer()
        # None result should be handled gracefully (not raise TypeError)
        insights = synth.extract_insights(
            step_id="s1",
            tool_name="file_read",
            result=None,
            success=True,
        )
        assert isinstance(insights, list)

    def test_extract_timeout_detected(self) -> None:
        synth = InsightSynthesizer()
        insights = synth.extract_insights(
            step_id="s1",
            tool_name="browser_navigate",
            result="timeout waiting for page",
            success=False,
        )
        # Timeout should be detected — might be blocker or error_learning
        relevant = [i for i in insights if i.insight_type in (InsightType.BLOCKER, InsightType.ERROR_LEARNING)]
        assert len(relevant) >= 1
