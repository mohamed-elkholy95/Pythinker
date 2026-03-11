"""Tests for conditional hallucination downgrade gating (Fix 5)."""

from unittest.mock import MagicMock

from app.domain.services.agents.execution import ExecutionAgent


def _make_agent(*, has_sources: bool = False, has_evidence: bool = False):
    """Create a mock ExecutionAgent with controllable evidence state."""
    agent = MagicMock(spec=ExecutionAgent)
    agent._source_tracker = MagicMock()
    agent._source_tracker.get_collected_sources.return_value = [MagicMock()] if has_sources else []
    agent._research_execution_policy = MagicMock()
    agent._research_execution_policy.evidence_records = [MagicMock()] if has_evidence else []
    # Bind the real method
    agent._can_downgrade_delivery_integrity_issues = ExecutionAgent._can_downgrade_delivery_integrity_issues.__get__(
        agent
    )
    return agent


class TestHallucinationDowngradeGating:
    def test_ungrounded_not_downgradable_without_evidence(self):
        agent = _make_agent(has_sources=False, has_evidence=False)
        result = agent._can_downgrade_delivery_integrity_issues(["hallucination_verification_ungrounded: high ratio"])
        assert result is False

    def test_ungrounded_downgradable_with_sources(self):
        agent = _make_agent(has_sources=True, has_evidence=False)
        result = agent._can_downgrade_delivery_integrity_issues(["hallucination_verification_ungrounded: high ratio"])
        assert result is True

    def test_ungrounded_downgradable_with_evidence_records(self):
        agent = _make_agent(has_sources=False, has_evidence=True)
        result = agent._can_downgrade_delivery_integrity_issues(["hallucination_verification_ungrounded: high ratio"])
        assert result is True

    def test_truncation_never_downgradable(self):
        """stream_truncation_unresolved is always non-downgradable regardless of evidence."""
        agent = _make_agent(has_sources=True, has_evidence=True)
        result = agent._can_downgrade_delivery_integrity_issues(["stream_truncation_unresolved: content cut off"])
        assert result is False

    def test_citation_integrity_never_downgradable(self):
        agent = _make_agent(has_sources=True, has_evidence=True)
        result = agent._can_downgrade_delivery_integrity_issues(["citation_integrity_unresolved: broken refs"])
        assert result is False

    def test_other_issues_always_downgradable(self):
        agent = _make_agent(has_sources=False, has_evidence=False)
        result = agent._can_downgrade_delivery_integrity_issues(["coverage_gap: missing section"])
        assert result is True
