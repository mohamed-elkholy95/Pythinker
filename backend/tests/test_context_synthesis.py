"""Tests for inter-step context synthesis.

Tests the enhanced context manager with:
- StepInsight creation and management
- ContextGraph for insight dependencies
- InsightSynthesizer for automatic extraction
- Integration with ContextManager
"""

from app.domain.services.agents.context_manager import (
    ContextGraph,
    ContextManager,
    InsightEdge,
    InsightSynthesizer,
    InsightType,
    StepInsight,
)


class TestInsightType:
    """Tests for InsightType enum."""

    def test_all_insight_types_exist(self):
        """Test that all insight types are defined."""
        assert InsightType.DISCOVERY.value == "discovery"
        assert InsightType.ERROR_LEARNING.value == "error_learning"
        assert InsightType.DECISION.value == "decision"
        assert InsightType.DEPENDENCY.value == "dependency"
        assert InsightType.ASSUMPTION.value == "assumption"
        assert InsightType.CONSTRAINT.value == "constraint"
        assert InsightType.PROGRESS.value == "progress"
        assert InsightType.BLOCKER.value == "blocker"


class TestStepInsight:
    """Tests for StepInsight dataclass."""

    def test_basic_creation(self):
        """Test basic insight creation."""
        insight = StepInsight(
            step_id="step1",
            insight_type=InsightType.DISCOVERY,
            content="Found important information",
        )

        assert insight.step_id == "step1"
        assert insight.insight_type == InsightType.DISCOVERY
        assert insight.content == "Found important information"
        assert insight.confidence == 0.8  # Default

    def test_id_generation(self):
        """Test that ID is generated correctly."""
        insight = StepInsight(
            step_id="step1",
            insight_type=InsightType.DISCOVERY,
            content="Test content",
        )

        assert insight.id.startswith("step1_discovery_")

    def test_is_high_confidence(self):
        """Test high confidence detection."""
        high = StepInsight(
            step_id="s1",
            insight_type=InsightType.DISCOVERY,
            content="High confidence",
            confidence=0.9,
        )
        low = StepInsight(
            step_id="s1",
            insight_type=InsightType.DISCOVERY,
            content="Low confidence",
            confidence=0.5,
        )

        assert high.is_high_confidence is True
        assert low.is_high_confidence is False

    def test_is_actionable(self):
        """Test actionable insight detection."""
        blocker = StepInsight(
            step_id="s1",
            insight_type=InsightType.BLOCKER,
            content="Blocked",
        )
        discovery = StepInsight(
            step_id="s1",
            insight_type=InsightType.DISCOVERY,
            content="Found",
        )
        error = StepInsight(
            step_id="s1",
            insight_type=InsightType.ERROR_LEARNING,
            content="Learned",
        )

        assert blocker.is_actionable is True
        assert error.is_actionable is True
        assert discovery.is_actionable is False

    def test_to_context_string(self):
        """Test context string formatting."""
        insight = StepInsight(
            step_id="s1",
            insight_type=InsightType.BLOCKER,
            content="Permission denied",
        )

        result = insight.to_context_string()
        assert "🛑" in result
        assert "Permission denied" in result


class TestContextGraph:
    """Tests for ContextGraph."""

    def test_add_insight(self):
        """Test adding insight to graph."""
        graph = ContextGraph()
        insight = StepInsight(
            step_id="step1",
            insight_type=InsightType.DISCOVERY,
            content="Found info",
        )

        graph.add_insight(insight)

        assert insight.id in graph.insights
        assert "step1" in graph.step_insights
        assert insight.id in graph.step_insights["step1"]

    def test_add_edge(self):
        """Test adding edge between insights."""
        graph = ContextGraph()
        insight1 = StepInsight(
            step_id="step1",
            insight_type=InsightType.DISCOVERY,
            content="First",
        )
        insight2 = StepInsight(
            step_id="step2",
            insight_type=InsightType.DEPENDENCY,
            content="Depends on first",
        )

        graph.add_insight(insight1)
        graph.add_insight(insight2)
        graph.add_edge(insight2.id, insight1.id, relationship="depends_on")

        assert len(graph.edges) == 1
        assert graph.edges[0].relationship == "depends_on"
        assert insight1.id in insight2.related_insights

    def test_get_insights_for_step(self):
        """Test getting insights for a specific step."""
        graph = ContextGraph()
        insight1 = StepInsight(step_id="step1", insight_type=InsightType.DISCOVERY, content="A")
        insight2 = StepInsight(step_id="step1", insight_type=InsightType.PROGRESS, content="B")
        insight3 = StepInsight(step_id="step2", insight_type=InsightType.DISCOVERY, content="C")

        graph.add_insight(insight1)
        graph.add_insight(insight2)
        graph.add_insight(insight3)

        step1_insights = graph.get_insights_for_step("step1")
        assert len(step1_insights) == 2
        assert all(i.step_id == "step1" for i in step1_insights)

    def test_get_related_insights(self):
        """Test getting related insights via graph traversal."""
        graph = ContextGraph()
        i1 = StepInsight(step_id="s1", insight_type=InsightType.DISCOVERY, content="Root")
        i2 = StepInsight(step_id="s2", insight_type=InsightType.DEPENDENCY, content="Child")
        i3 = StepInsight(step_id="s3", insight_type=InsightType.PROGRESS, content="Grandchild")

        graph.add_insight(i1)
        graph.add_insight(i2)
        graph.add_insight(i3)
        graph.add_edge(i2.id, i1.id, "derived_from")
        graph.add_edge(i3.id, i2.id, "derived_from")

        related = graph.get_related_insights(i1.id, max_depth=2)
        assert len(related) >= 1
        assert any(i.id == i2.id for i in related)

    def test_get_critical_insights(self):
        """Test getting critical insights prioritized by type and connectivity."""
        graph = ContextGraph()
        blocker = StepInsight(step_id="s1", insight_type=InsightType.BLOCKER, content="Critical")
        discovery = StepInsight(step_id="s2", insight_type=InsightType.DISCOVERY, content="Info")
        progress = StepInsight(step_id="s3", insight_type=InsightType.PROGRESS, content="Done")

        graph.add_insight(blocker)
        graph.add_insight(discovery)
        graph.add_insight(progress)

        critical = graph.get_critical_insights(limit=2)
        assert len(critical) == 2
        # Blocker should be first due to higher type weight
        assert critical[0].insight_type == InsightType.BLOCKER

    def test_get_blockers(self):
        """Test getting all blockers."""
        graph = ContextGraph()
        b1 = StepInsight(step_id="s1", insight_type=InsightType.BLOCKER, content="Block 1")
        b2 = StepInsight(step_id="s2", insight_type=InsightType.BLOCKER, content="Block 2")
        d1 = StepInsight(step_id="s3", insight_type=InsightType.DISCOVERY, content="Not a blocker")

        graph.add_insight(b1)
        graph.add_insight(b2)
        graph.add_insight(d1)

        blockers = graph.get_blockers()
        assert len(blockers) == 2
        assert all(b.insight_type == InsightType.BLOCKER for b in blockers)

    def test_get_learnings(self):
        """Test getting error learnings."""
        graph = ContextGraph()
        l1 = StepInsight(step_id="s1", insight_type=InsightType.ERROR_LEARNING, content="Learned 1")
        l2 = StepInsight(step_id="s2", insight_type=InsightType.ERROR_LEARNING, content="Learned 2")
        d1 = StepInsight(step_id="s3", insight_type=InsightType.DISCOVERY, content="Discovery")

        graph.add_insight(l1)
        graph.add_insight(l2)
        graph.add_insight(d1)

        learnings = graph.get_learnings()
        assert len(learnings) == 2
        assert all(learning.insight_type == InsightType.ERROR_LEARNING for learning in learnings)

    def test_to_summary(self):
        """Test generating graph summary."""
        graph = ContextGraph()
        graph.add_insight(StepInsight(step_id="s1", insight_type=InsightType.BLOCKER, content="Blocked by X"))
        graph.add_insight(StepInsight(step_id="s2", insight_type=InsightType.DISCOVERY, content="Found Y"))

        summary = graph.to_summary()
        assert "## Context Insights" in summary
        assert "Active Blockers" in summary
        assert "Blocked by X" in summary


class TestInsightSynthesizer:
    """Tests for InsightSynthesizer."""

    def test_extract_error_insights(self):
        """Test extracting insights from error results."""
        synthesizer = InsightSynthesizer()

        insights = synthesizer.extract_insights(
            step_id="step1",
            tool_name="shell",
            result="Error: command not found",
            success=False,
        )

        # Should have at least the error learning from failure
        assert len(insights) >= 1
        error_insights = [i for i in insights if i.insight_type == InsightType.ERROR_LEARNING]
        assert len(error_insights) >= 1

    def test_extract_discovery_insights(self):
        """Test extracting discovery insights."""
        synthesizer = InsightSynthesizer()

        insights = synthesizer.extract_insights(
            step_id="step1",
            tool_name="search",
            result="Found 10 results for Python tutorials",
            success=True,
        )

        # Should detect the "found" pattern
        discovery_insights = [i for i in insights if i.insight_type == InsightType.DISCOVERY]
        assert len(discovery_insights) >= 1

    def test_extract_dependency_insights(self):
        """Test extracting dependency insights."""
        synthesizer = InsightSynthesizer()

        insights = synthesizer.extract_insights(
            step_id="step1",
            tool_name="analyze",
            result="This module requires numpy and pandas",
            success=True,
        )

        dep_insights = [i for i in insights if i.insight_type == InsightType.DEPENDENCY]
        assert len(dep_insights) >= 1

    def test_tool_specific_search(self):
        """Test search tool specific extraction."""
        synthesizer = InsightSynthesizer()

        insights = synthesizer.extract_insights(
            step_id="step1",
            tool_name="info_search_web",
            result="Search results found",
            success=True,
            args={"query": "Python best practices"},
        )

        discovery = [i for i in insights if i.insight_type == InsightType.DISCOVERY]
        assert len(discovery) >= 1
        assert any("Python best practices" in i.content for i in discovery)

    def test_tool_specific_file(self):
        """Test file operation specific extraction."""
        synthesizer = InsightSynthesizer()

        insights = synthesizer.extract_insights(
            step_id="step1",
            tool_name="file_write",
            result="File written successfully",
            success=True,
            args={"path": "/workspace/report.md"},
        )

        progress = [i for i in insights if i.insight_type == InsightType.PROGRESS]
        assert len(progress) >= 1
        assert any("report.md" in i.content for i in progress)

    def test_tool_specific_shell(self):
        """Test shell command specific extraction."""
        synthesizer = InsightSynthesizer()

        insights = synthesizer.extract_insights(
            step_id="step1",
            tool_name="shell_exec",
            result="Command completed",
            success=True,
            args={"command": "pip install requests"},
        )

        progress = [i for i in insights if i.insight_type == InsightType.PROGRESS]
        assert len(progress) >= 1
        assert any("pip install" in i.content for i in progress)

    def test_tool_specific_browser(self):
        """Test browser specific extraction."""
        synthesizer = InsightSynthesizer()

        insights = synthesizer.extract_insights(
            step_id="step1",
            tool_name="browser_navigate",
            result="Page loaded",
            success=True,
            args={"url": "https://docs.python.org"},
        )

        discovery = [i for i in insights if i.insight_type == InsightType.DISCOVERY]
        assert len(discovery) >= 1
        assert any("docs.python.org" in i.content for i in discovery)

    def test_synthesize_from_steps(self):
        """Test synthesizing context from step insights."""
        synthesizer = InsightSynthesizer()

        step_insights = {
            "step1": [
                StepInsight(
                    step_id="step1",
                    insight_type=InsightType.DISCOVERY,
                    content="Found Python docs",
                ),
                StepInsight(
                    step_id="step1",
                    insight_type=InsightType.ERROR_LEARNING,
                    content="Rate limit hit, wait 60s",
                ),
            ],
            "step2": [
                StepInsight(
                    step_id="step2",
                    insight_type=InsightType.PROGRESS,
                    content="Downloaded file",
                ),
            ],
        }

        context = synthesizer.synthesize_from_steps(step_insights, "step3")

        assert "## Prior Step Insights" in context
        assert "Found Python docs" in context or "Rate limit" in context


class TestContextManagerIntegration:
    """Integration tests for ContextManager with insights."""

    def test_set_current_step(self):
        """Test setting current step."""
        cm = ContextManager()
        cm.set_current_step("step1")

        # Should be able to add insights now
        insight = cm.add_insight(
            insight_type=InsightType.DISCOVERY,
            content="Test insight",
        )
        assert insight.step_id == "step1"

    def test_record_tool_insight(self):
        """Test recording tool insights."""
        cm = ContextManager()
        cm.set_current_step("step1")

        insights = cm.record_tool_insight(
            tool_name="search",
            result="Found 5 results for query",
            success=True,
            args={"query": "test"},
        )

        assert len(insights) >= 1
        graph = cm.get_context_graph()
        assert len(graph.insights) >= 1

    def test_add_manual_insight(self):
        """Test adding manual insight."""
        cm = ContextManager()
        cm.set_current_step("step1")

        insight = cm.add_insight(
            insight_type=InsightType.DECISION,
            content="Decided to use approach A",
            confidence=0.9,
            tags=["architecture"],
        )

        assert insight.insight_type == InsightType.DECISION
        assert insight.confidence == 0.9
        assert "architecture" in insight.tags

    def test_link_insights(self):
        """Test linking insights."""
        cm = ContextManager()
        cm.set_current_step("step1")

        insight1 = cm.add_insight(
            insight_type=InsightType.DISCOVERY,
            content="Found requirement",
        )
        insight2 = cm.add_insight(
            insight_type=InsightType.DECISION,
            content="Based on requirement, decided X",
        )

        cm.link_insights(insight2, insight1, relationship="derived_from")

        graph = cm.get_context_graph()
        assert len(graph.edges) == 1

    def test_get_synthesized_context(self):
        """Test getting synthesized context."""
        cm = ContextManager()

        # Step 1 insights
        cm.set_current_step("step1")
        cm.add_insight(InsightType.DISCOVERY, "Found important data")
        cm.add_insight(InsightType.ERROR_LEARNING, "API requires auth token")

        # Step 2 insights
        cm.set_current_step("step2")
        cm.add_insight(InsightType.PROGRESS, "Downloaded file")

        # Get context for step 3
        context = cm.get_synthesized_context(for_step_id="step3")

        assert "Prior Step Insights" in context

    def test_get_critical_insights(self):
        """Test getting critical insights."""
        cm = ContextManager()
        cm.set_current_step("step1")

        cm.add_insight(InsightType.BLOCKER, "Permission denied")
        cm.add_insight(InsightType.DISCOVERY, "Found info")

        critical = cm.get_critical_insights(limit=5)
        assert len(critical) == 2
        # Blocker should be prioritized
        assert critical[0].insight_type == InsightType.BLOCKER

    def test_get_blockers(self):
        """Test getting blockers."""
        cm = ContextManager()
        cm.set_current_step("step1")

        cm.add_insight(InsightType.BLOCKER, "Auth failed")
        cm.add_insight(InsightType.DISCOVERY, "Not a blocker")

        blockers = cm.get_blockers()
        assert len(blockers) == 1
        assert blockers[0].content == "Auth failed"

    def test_get_learnings(self):
        """Test getting error learnings."""
        cm = ContextManager()
        cm.set_current_step("step1")

        cm.add_insight(InsightType.ERROR_LEARNING, "Rate limit requires backoff")
        cm.add_insight(InsightType.DISCOVERY, "Not a learning")

        learnings = cm.get_learnings()
        assert len(learnings) == 1
        assert "Rate limit" in learnings[0].content

    def test_get_insights_for_step(self):
        """Test getting insights for specific step."""
        cm = ContextManager()

        cm.set_current_step("step1")
        cm.add_insight(InsightType.DISCOVERY, "Step 1 insight")

        cm.set_current_step("step2")
        cm.add_insight(InsightType.DISCOVERY, "Step 2 insight")

        step1_insights = cm.get_insights_for_step("step1")
        assert len(step1_insights) == 1
        assert "Step 1" in step1_insights[0].content

    def test_get_graph_summary(self):
        """Test graph summary statistics."""
        cm = ContextManager()
        cm.set_current_step("step1")

        cm.add_insight(InsightType.BLOCKER, "Block")
        cm.add_insight(InsightType.ERROR_LEARNING, "Learn")
        cm.add_insight(InsightType.DISCOVERY, "Discover")

        summary = cm.get_graph_summary()

        assert summary["total_insights"] == 3
        assert summary["blockers"] == 1
        assert summary["learnings"] == 1
        assert summary["insight_types"]["blocker"] == 1

    def test_clear_clears_insights(self):
        """Test that clear() clears the insight graph."""
        cm = ContextManager()
        cm.set_current_step("step1")
        cm.add_insight(InsightType.DISCOVERY, "Test")

        cm.clear()

        assert len(cm.get_context_graph().insights) == 0
        assert cm._current_step_id is None


class TestInsightEdge:
    """Tests for InsightEdge dataclass."""

    def test_basic_edge_creation(self):
        """Test basic edge creation."""
        edge = InsightEdge(
            from_insight_id="a",
            to_insight_id="b",
            relationship="depends_on",
            weight=0.8,
        )

        assert edge.from_insight_id == "a"
        assert edge.to_insight_id == "b"
        assert edge.relationship == "depends_on"
        assert edge.weight == 0.8

    def test_default_weight(self):
        """Test default weight is 1.0."""
        edge = InsightEdge(
            from_insight_id="a",
            to_insight_id="b",
            relationship="same_step",
        )

        assert edge.weight == 1.0


class TestComplexScenarios:
    """Tests for complex multi-step scenarios."""

    def test_multi_step_workflow(self):
        """Test a complete multi-step workflow."""
        cm = ContextManager()

        # Step 1: Search
        cm.set_current_step("step1")
        cm.record_tool_insight(
            tool_name="info_search_web",
            result="Found 10 results about Python async",
            success=True,
            args={"query": "Python async programming"},
        )
        cm.add_insight(
            InsightType.DISCOVERY,
            "asyncio is the standard library for async",
            confidence=0.9,
        )

        # Step 2: Browse
        cm.set_current_step("step2")
        cm.record_tool_insight(
            tool_name="browser_navigate",
            result="Loaded Python docs",
            success=True,
            args={"url": "https://docs.python.org/3/library/asyncio.html"},
        )
        cm.add_insight(
            InsightType.DECISION,
            "Will use asyncio.gather for concurrent execution",
        )

        # Step 3: Implement - get context from previous steps
        cm.set_current_step("step3")
        cm.get_synthesized_context()

        # Should have insights from steps 1 and 2
        graph = cm.get_context_graph()
        assert len(graph.step_insights) >= 2
        assert "step1" in graph.step_insights
        assert "step2" in graph.step_insights

    def test_error_recovery_flow(self):
        """Test error learning and recovery."""
        cm = ContextManager()

        # Step 1: Attempt that fails
        cm.set_current_step("step1")
        cm.record_tool_insight(
            tool_name="shell_exec",
            result="Error: Permission denied for /etc/config",
            success=False,
            args={"command": "cat /etc/config"},
        )

        # Step 2: Retry with different approach
        cm.set_current_step("step2")

        # Get learnings from previous step
        learnings = cm.get_learnings()
        assert len(learnings) >= 1
        assert any(
            "Permission denied" in learning.content or "failed" in learning.content.lower() for learning in learnings
        )

    def test_insight_chain(self):
        """Test chaining insights across steps."""
        cm = ContextManager()

        cm.set_current_step("step1")
        discovery = cm.add_insight(
            InsightType.DISCOVERY,
            "Project uses TypeScript",
        )

        cm.set_current_step("step2")
        decision = cm.add_insight(
            InsightType.DECISION,
            "Need to compile TS before running",
        )
        cm.link_insights(decision, discovery, "derived_from")

        cm.set_current_step("step3")
        progress = cm.add_insight(
            InsightType.PROGRESS,
            "Compiled TypeScript successfully",
        )
        cm.link_insights(progress, decision, "derived_from")

        # Get related insights for the decision
        graph = cm.get_context_graph()
        related = graph.get_related_insights(decision.id, max_depth=2)

        # Should find both discovery (parent) and potentially progress (child)
        assert len(related) >= 1
