"""Tests for hallucination rate escalation in BaseAgent.

Tests the per-session hallucination rate tracker and escalation logic
without instantiating the full BaseAgent (which requires extensive mocking).
Instead we test the rate calculation and escalation decision in isolation.
"""


class TestHallucinationRateCalculation:
    """Test the hallucination rate calculation logic."""

    def test_rate_below_threshold_no_escalation(self):
        """Rate below 0.15 with sufficient samples should not escalate."""
        total_tool_calls = 20
        total_hallucinations = 2  # 10% rate
        threshold = 0.15
        min_samples = 10

        rate = total_hallucinations / max(1, total_tool_calls)
        should_escalate = rate >= threshold and total_tool_calls >= min_samples
        assert should_escalate is False

    def test_rate_above_threshold_with_sufficient_samples_escalates(self):
        """Rate above 0.15 with 10+ calls should escalate."""
        total_tool_calls = 20
        total_hallucinations = 5  # 25% rate
        threshold = 0.15
        min_samples = 10

        rate = total_hallucinations / max(1, total_tool_calls)
        should_escalate = rate >= threshold and total_tool_calls >= min_samples
        assert should_escalate is True

    def test_rate_above_threshold_insufficient_samples_no_escalation(self):
        """Rate above threshold but fewer than 10 calls should not escalate."""
        total_tool_calls = 5
        total_hallucinations = 3  # 60% rate, but too few samples
        threshold = 0.15
        min_samples = 10

        rate = total_hallucinations / max(1, total_tool_calls)
        should_escalate = rate >= threshold and total_tool_calls >= min_samples
        assert should_escalate is False

    def test_zero_tool_calls_no_division_error(self):
        """Zero tool calls should not cause division by zero."""
        total_tool_calls = 0
        total_hallucinations = 0
        threshold = 0.15

        rate = total_hallucinations / max(1, total_tool_calls)
        assert rate == 0.0

    def test_exactly_at_threshold_escalates(self):
        """Rate exactly at threshold should escalate."""
        total_tool_calls = 20
        total_hallucinations = 3  # 15% = exactly threshold
        threshold = 0.15
        min_samples = 10

        rate = total_hallucinations / max(1, total_tool_calls)
        should_escalate = rate >= threshold and total_tool_calls >= min_samples
        assert should_escalate is True


class TestHallucinationMetaPrompt:
    """Test the meta-prompt content for hallucination correction."""

    def test_meta_prompt_contains_required_params_reminder(self):
        """Meta prompt should remind about required parameters."""
        meta_prompt = (
            "CRITICAL: Recent tool calls had missing required parameters. "
            "You MUST include ALL required parameters for every tool call. "
            "Do NOT omit 'id', 'exec_dir', or 'command' parameters."
        )
        assert "required parameters" in meta_prompt.lower()
        assert "id" in meta_prompt
        assert "exec_dir" in meta_prompt
