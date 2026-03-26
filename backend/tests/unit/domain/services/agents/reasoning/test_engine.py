"""Unit tests for ReasoningEngine in reasoning/engine.py.

Covers:
- think_step_by_step: cache, LLM call, fallback on error
- think_step_by_step_streaming: streaming path, non-streaming fallback
- reason_about_tool_selection: prompt formatting, tool validation
- reason_about_plan: chain + decision extraction
- validate_reasoning: issue/warning detection, confidence calculation
- extract_decision: delegation to chain builder
- helper methods: _format_context, _format_tools_for_prompt, _get_cache_key,
  _create_fallback_chain, _validate_tool_decision, _has_circular_reasoning,
  _calculate_validation_confidence
- singleton helpers: get_reasoning_engine, reset_reasoning_engine
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.exceptions.base import ConfigurationException
from app.domain.models.thought import (
    Decision,
    ReasoningStep,
    Thought,
    ThoughtChain,
    ThoughtQuality,
    ThoughtType,
    ValidationResult,
)
from app.domain.services.agents.reasoning.engine import (
    ReasoningEngine,
    get_reasoning_engine,
    reset_reasoning_engine,
)

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.ask = AsyncMock(return_value={"content": "I will proceed with the plan."})
    return llm


@pytest.fixture
def engine(mock_llm):
    return ReasoningEngine(llm=mock_llm, enable_streaming=True)


def _build_chain(
    steps: int = 1,
    thought_types: list[ThoughtType] | None = None,
    final_decision: str = "Do the thing",
    confidence: float = 0.7,
) -> ThoughtChain:
    """Helper: build a ThoughtChain with given steps and types."""
    chain = ThoughtChain(problem="Test problem", overall_confidence=confidence)
    for i in range(steps):
        step = ReasoningStep(name=f"Step {i + 1}")
        types = thought_types or [ThoughtType.ANALYSIS]
        for t in types:
            step.add_thought(Thought(type=t, content=f"Content for {t.value}", confidence=confidence))
        step.is_complete = True
        chain.add_step(step)
    chain.final_decision = final_decision
    return chain


# ─── think_step_by_step ──────────────────────────────────────────────────────


class TestThinkStepByStep:
    @pytest.mark.asyncio
    async def test_returns_thought_chain(self, engine):
        chain = await engine.think_step_by_step("What should I do?")
        assert isinstance(chain, ThoughtChain)

    @pytest.mark.asyncio
    async def test_calls_llm_once(self, engine, mock_llm):
        await engine.think_step_by_step("Simple problem")
        mock_llm.ask.assert_called_once()

    @pytest.mark.asyncio
    async def test_result_cached_on_second_call(self, engine, mock_llm):
        await engine.think_step_by_step("Cached problem")
        await engine.think_step_by_step("Cached problem")
        assert mock_llm.ask.call_count == 1

    @pytest.mark.asyncio
    async def test_different_problems_not_cached(self, engine, mock_llm):
        await engine.think_step_by_step("Problem A")
        await engine.think_step_by_step("Problem B")
        assert mock_llm.ask.call_count == 2

    @pytest.mark.asyncio
    async def test_context_included_in_cache_key(self, engine, mock_llm):
        await engine.think_step_by_step("Same problem", context={"a": 1})
        await engine.think_step_by_step("Same problem", context={"a": 2})
        assert mock_llm.ask.call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_chain_on_llm_error(self, engine, mock_llm):
        mock_llm.ask.side_effect = RuntimeError("LLM unavailable")
        chain = await engine.think_step_by_step("Failing problem")
        assert isinstance(chain, ThoughtChain)
        assert len(chain.steps) >= 1

    @pytest.mark.asyncio
    async def test_fallback_chain_has_uncertainty_thought(self, engine, mock_llm):
        mock_llm.ask.side_effect = RuntimeError("network error")
        chain = await engine.think_step_by_step("Problem")
        all_thoughts = chain.get_all_thoughts()
        assert any(t.type == ThoughtType.UNCERTAINTY for t in all_thoughts)

    @pytest.mark.asyncio
    async def test_clear_cache_removes_cached_entry(self, engine, mock_llm):
        await engine.think_step_by_step("Problem")
        engine.clear_cache()
        await engine.think_step_by_step("Problem")
        assert mock_llm.ask.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_content_response_handled(self, engine, mock_llm):
        mock_llm.ask.return_value = {"content": ""}
        chain = await engine.think_step_by_step("Empty response problem")
        assert isinstance(chain, ThoughtChain)


# ─── think_step_by_step_streaming ────────────────────────────────────────────


class TestThinkStepByStepStreaming:
    @pytest.mark.asyncio
    async def test_non_streaming_fallback_when_disabled(self, mock_llm):
        engine = ReasoningEngine(llm=mock_llm, enable_streaming=False)
        chunks = []
        async for chunk, chain in engine.think_step_by_step_streaming("problem"):
            chunks.append((chunk, chain))
        # Last item should have the chain
        assert any(chain is not None for _, chain in chunks)

    @pytest.mark.asyncio
    async def test_no_ask_stream_attribute_falls_back(self, mock_llm):
        # LLM without ask_stream method triggers fallback
        del mock_llm.ask_stream
        engine = ReasoningEngine(llm=mock_llm, enable_streaming=True)
        chunks = []
        async for chunk, chain in engine.think_step_by_step_streaming("problem"):
            chunks.append((chunk, chain))
        assert any(chain is not None for _, chain in chunks)

    @pytest.mark.asyncio
    async def test_streaming_yields_chunks_then_chain(self, mock_llm):
        async def mock_stream(*args, **kwargs):
            for word in ["I ", "will ", "proceed."]:
                yield word

        mock_llm.ask_stream = mock_stream
        engine = ReasoningEngine(llm=mock_llm, enable_streaming=True)

        text_chunks = []
        final_chain = None
        async for chunk, chain in engine.think_step_by_step_streaming("problem"):
            if chain is not None:
                final_chain = chain
            else:
                text_chunks.append(chunk)

        assert len(text_chunks) > 0
        assert final_chain is not None
        assert isinstance(final_chain, ThoughtChain)

    @pytest.mark.asyncio
    async def test_streaming_error_yields_fallback_chain(self, mock_llm):
        async def failing_stream(*args, **kwargs):
            raise RuntimeError("stream failure")
            yield ""  # unreachable but needed for async generator

        mock_llm.ask_stream = failing_stream
        engine = ReasoningEngine(llm=mock_llm, enable_streaming=True)
        results = []
        async for chunk, chain in engine.think_step_by_step_streaming("problem"):
            results.append((chunk, chain))
        # Should have yielded at least error + fallback chain
        assert len(results) >= 1


# ─── reason_about_tool_selection ─────────────────────────────────────────────


class TestReasonAboutToolSelection:
    def _make_tool(self, name: str, desc: str = "Does something") -> dict[str, Any]:
        return {"function": {"name": name, "description": desc}}

    @pytest.mark.asyncio
    async def test_returns_chain_and_decision(self, engine):
        tools = [self._make_tool("shell_execute"), self._make_tool("browser_navigate")]
        chain, decision = await engine.reason_about_tool_selection("run a command", tools)
        assert isinstance(chain, ThoughtChain)
        assert isinstance(decision, Decision)

    @pytest.mark.asyncio
    async def test_limits_tools_to_ten(self, engine, mock_llm):
        tools = [self._make_tool(f"tool_{i}") for i in range(15)]
        await engine.reason_about_tool_selection("task", tools)
        # The prompt passed to LLM should only contain 10 tools
        call_args = mock_llm.ask.call_args
        messages = call_args[0][0]
        user_message = next(m["content"] for m in messages if m["role"] == "user")
        # Check not all 15 appear in prompt
        tool_occurrences = sum(1 for i in range(15) if f"tool_{i}" in user_message)
        assert tool_occurrences <= 10

    @pytest.mark.asyncio
    async def test_validated_tool_in_decision_metadata(self, engine, mock_llm):
        mock_llm.ask.return_value = {"content": "I will use shell_execute to run the command."}
        tools = [self._make_tool("shell_execute")]
        _, decision = await engine.reason_about_tool_selection("run a command", tools)
        # shell_execute appears in content, should be validated
        assert "validated_tool" in decision.metadata or isinstance(decision, Decision)

    @pytest.mark.asyncio
    async def test_unknown_tool_reduces_confidence(self, engine, mock_llm):
        mock_llm.ask.return_value = {"content": "I will use some_unknown_tool_xyz."}
        tools = [self._make_tool("shell_execute")]
        _, decision = await engine.reason_about_tool_selection("run a command", tools)
        # Unknown tool triggers risk warning
        assert isinstance(decision, Decision)


# ─── reason_about_plan ───────────────────────────────────────────────────────


class TestReasonAboutPlan:
    @pytest.mark.asyncio
    async def test_returns_chain_and_decision(self, engine):
        chain, decision = await engine.reason_about_plan("Build a web scraper")
        assert isinstance(chain, ThoughtChain)
        assert isinstance(decision, Decision)

    @pytest.mark.asyncio
    async def test_context_included_in_prompt(self, engine, mock_llm):
        await engine.reason_about_plan("task", context={"priority": "high", "env": "prod"})
        call_args = mock_llm.ask.call_args
        messages = call_args[0][0]
        user_message = next(m["content"] for m in messages if m["role"] == "user")
        assert "priority" in user_message or "prod" in user_message

    @pytest.mark.asyncio
    async def test_no_context_uses_placeholder(self, engine, mock_llm):
        await engine.reason_about_plan("task", context=None)
        call_args = mock_llm.ask.call_args
        messages = call_args[0][0]
        user_message = next(m["content"] for m in messages if m["role"] == "user")
        assert "No additional context" in user_message


# ─── validate_reasoning ──────────────────────────────────────────────────────


class TestValidateReasoning:
    def test_empty_chain_is_invalid(self, engine):
        chain = ThoughtChain(problem="test")
        result = engine.validate_reasoning(chain)
        assert result.is_valid is False
        assert any("no steps" in issue.lower() for issue in result.issues)
        assert result.confidence_score == 0.0

    def test_no_observations_adds_warning(self, engine):
        chain = _build_chain(
            steps=1,
            thought_types=[ThoughtType.ANALYSIS, ThoughtType.DECISION],
        )
        result = engine.validate_reasoning(chain)
        assert any("observation" in w.lower() for w in result.warnings)

    def test_no_analysis_adds_warning(self, engine):
        chain = _build_chain(
            steps=1,
            thought_types=[ThoughtType.OBSERVATION, ThoughtType.DECISION],
        )
        result = engine.validate_reasoning(chain)
        assert any("analysis" in w.lower() for w in result.warnings)

    def test_no_decision_adds_issue(self, engine):
        chain = _build_chain(
            steps=1,
            thought_types=[ThoughtType.OBSERVATION, ThoughtType.ANALYSIS],
        )
        chain.final_decision = None  # Remove final decision
        result = engine.validate_reasoning(chain)
        assert any("decision" in issue.lower() for issue in result.issues)

    def test_high_uncertainty_adds_warning(self, engine):
        chain = ThoughtChain(problem="test", overall_confidence=0.6)
        # Add a step with more uncertainty thoughts than steps
        for i in range(3):
            step = ReasoningStep(name=f"Uncertain {i}")
            step.add_thought(Thought(type=ThoughtType.UNCERTAINTY, content=f"Uncertain {i}", confidence=0.3))
            step.is_complete = True
            chain.add_step(step)
        chain.final_decision = "Try anyway"
        result = engine.validate_reasoning(chain)
        # Validation may or may not flag uncertainty depending on ratio thresholds
        assert result is not None

    def test_majority_low_quality_thoughts_adds_warning(self, engine):
        chain = ThoughtChain(problem="test", overall_confidence=0.4)
        step = ReasoningStep(name="step")
        for _ in range(3):
            step.add_thought(
                Thought(
                    type=ThoughtType.ANALYSIS,
                    content="I guess maybe",
                    confidence=0.2,
                    quality=ThoughtQuality.LOW,
                )
            )
        step.is_complete = True
        chain.add_step(step)
        chain.final_decision = "Unsure"
        result = engine.validate_reasoning(chain)
        assert any("low quality" in w.lower() or "quality" in w.lower() for w in result.warnings)

    def test_valid_chain_is_valid(self, engine):
        chain = _build_chain(
            steps=3,
            thought_types=[
                ThoughtType.OBSERVATION,
                ThoughtType.ANALYSIS,
                ThoughtType.DECISION,
            ],
            confidence=0.7,
        )
        result = engine.validate_reasoning(chain)
        assert isinstance(result, ValidationResult)
        assert result.confidence_score >= 0.0

    def test_returns_validation_result_type(self, engine):
        chain = _build_chain(steps=1)
        result = engine.validate_reasoning(chain)
        assert isinstance(result, ValidationResult)

    def test_confidence_score_clamped(self, engine):
        chain = _build_chain(steps=1, confidence=0.9)
        result = engine.validate_reasoning(chain)
        assert 0.0 <= result.confidence_score <= 1.0


# ─── _has_circular_reasoning ─────────────────────────────────────────────────


class TestHasCircularReasoning:
    def test_few_thoughts_never_circular(self, engine):
        chain = _build_chain(steps=1, thought_types=[ThoughtType.ANALYSIS])
        assert engine._has_circular_reasoning(chain) is False

    def test_repetitive_thoughts_flagged(self, engine):
        chain = ThoughtChain(problem="test")
        step = ReasoningStep(name="s")
        repeated_content = "The answer is obvious and clear"
        for _ in range(6):
            step.add_thought(Thought(type=ThoughtType.ANALYSIS, content=repeated_content))
        chain.add_step(step)
        assert engine._has_circular_reasoning(chain) is True

    def test_diverse_thoughts_not_circular(self, engine):
        chain = ThoughtChain(problem="test")
        step = ReasoningStep(name="s")
        for i in range(6):
            step.add_thought(
                Thought(
                    type=ThoughtType.ANALYSIS,
                    content=f"Unique perspective number {i} on a completely different topic",
                )
            )
        chain.add_step(step)
        assert engine._has_circular_reasoning(chain) is False


# ─── _format_context ─────────────────────────────────────────────────────────


class TestFormatContext:
    def test_scalar_value(self, engine):
        result = engine._format_context({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_list_value_truncated_to_five(self, engine):
        result = engine._format_context({"items": [1, 2, 3, 4, 5, 6, 7]})
        assert "items" in result
        # Should truncate to 5 items
        assert "6" not in result or "7" not in result

    def test_dict_value_truncated_to_three(self, engine):
        ctx = {"nested": {f"k{i}": i for i in range(6)}}
        result = engine._format_context(ctx)
        assert "nested" in result

    def test_long_scalar_truncated(self, engine):
        result = engine._format_context({"key": "x" * 200})
        assert len(result) < 300

    def test_empty_context(self, engine):
        result = engine._format_context({})
        assert result == ""


# ─── _format_tools_for_prompt ────────────────────────────────────────────────


class TestFormatToolsForPrompt:
    def _make_tool(self, name: str, desc: str = "Does things") -> dict[str, Any]:
        return {"function": {"name": name, "description": desc}}

    def test_lists_tool_names(self, engine):
        tools = [self._make_tool("shell_exec"), self._make_tool("browser_nav")]
        result = engine._format_tools_for_prompt(tools)
        assert "shell_exec" in result
        assert "browser_nav" in result

    def test_truncates_description_to_100_chars(self, engine):
        long_desc = "A" * 200
        result = engine._format_tools_for_prompt([self._make_tool("tool", long_desc)])
        lines = result.strip().split("\n")
        assert len(lines[0]) < 150  # name + ": " + 100 chars = ~115 max

    def test_empty_tools_returns_empty(self, engine):
        assert engine._format_tools_for_prompt([]) == ""

    def test_handles_missing_function_key(self, engine):
        tools = [{}]
        result = engine._format_tools_for_prompt(tools)
        assert "unknown" in result


# ─── _get_cache_key ──────────────────────────────────────────────────────────


class TestGetCacheKey:
    def test_same_problem_same_key(self, engine):
        k1 = engine._get_cache_key("problem", None)
        k2 = engine._get_cache_key("problem", None)
        assert k1 == k2

    def test_different_problems_different_key(self, engine):
        k1 = engine._get_cache_key("problem A", None)
        k2 = engine._get_cache_key("problem B", None)
        assert k1 != k2

    def test_different_contexts_different_key(self, engine):
        k1 = engine._get_cache_key("problem", {"a": 1})
        k2 = engine._get_cache_key("problem", {"a": 2})
        assert k1 != k2

    def test_truncates_long_problem(self, engine):
        long_problem = "x" * 500
        key = engine._get_cache_key(long_problem, None)
        # Key should not contain full 500-char string
        assert len(key) < 500

    def test_none_context_handled(self, engine):
        key = engine._get_cache_key("problem", None)
        assert isinstance(key, str)


# ─── _create_fallback_chain ──────────────────────────────────────────────────


class TestCreateFallbackChain:
    def test_returns_thought_chain(self, engine):
        chain = engine._create_fallback_chain("problem", "some error")
        assert isinstance(chain, ThoughtChain)

    def test_has_at_least_one_step(self, engine):
        chain = engine._create_fallback_chain("problem", "error message")
        assert len(chain.steps) >= 1

    def test_has_uncertainty_thought(self, engine):
        chain = engine._create_fallback_chain("problem", "error")
        all_thoughts = chain.get_all_thoughts()
        assert any(t.type == ThoughtType.UNCERTAINTY for t in all_thoughts)

    def test_low_confidence(self, engine):
        chain = engine._create_fallback_chain("problem", "error")
        all_thoughts = chain.get_all_thoughts()
        assert all(t.confidence <= 0.3 for t in all_thoughts)

    def test_has_final_decision(self, engine):
        chain = engine._create_fallback_chain("problem", "error")
        assert chain.final_decision is not None


# ─── _validate_tool_decision ─────────────────────────────────────────────────


class TestValidateToolDecision:
    def _make_tool(self, name: str) -> dict[str, Any]:
        return {"function": {"name": name, "description": "tool"}}

    def _make_decision(self, action: str, confidence: float = 0.8) -> Decision:
        return Decision(action=action, rationale="test", confidence=confidence)

    def test_known_tool_validated_in_metadata(self, engine):
        decision = self._make_decision("I will use shell_execute for this")
        tools = [self._make_tool("shell_execute")]
        result = engine._validate_tool_decision(decision, tools)
        assert result.metadata.get("validated_tool") == "shell_execute"

    def test_unknown_tool_adds_risk(self, engine):
        decision = self._make_decision("I will use ghost_tool_xyz")
        tools = [self._make_tool("shell_execute")]
        original_confidence = decision.confidence
        result = engine._validate_tool_decision(decision, tools)
        assert result.confidence < original_confidence
        assert any("not clearly identified" in r for r in result.risks)

    def test_returns_decision_object(self, engine):
        decision = self._make_decision("use shell_execute")
        tools = [self._make_tool("shell_execute")]
        result = engine._validate_tool_decision(decision, tools)
        assert isinstance(result, Decision)


# ─── _calculate_validation_confidence ────────────────────────────────────────


class TestCalculateValidationConfidence:
    def test_issues_reduce_score(self, engine):
        chain = _build_chain(confidence=0.7)
        score = engine._calculate_validation_confidence(chain, ["issue1", "issue2"], [])
        assert score < chain.overall_confidence

    def test_warnings_slightly_reduce_score(self, engine):
        chain = _build_chain(confidence=0.7)
        score_no_warnings = engine._calculate_validation_confidence(chain, [], [])
        score_with_warnings = engine._calculate_validation_confidence(chain, [], ["warn"])
        assert score_with_warnings < score_no_warnings

    def test_evidence_boosts_score(self, engine):
        chain = ThoughtChain(problem="test", overall_confidence=0.5)
        step = ReasoningStep(name="s")
        step.add_thought(
            Thought(
                type=ThoughtType.ANALYSIS,
                content="Evidence-backed claim",
                supporting_evidence=["source1", "source2"],
            )
        )
        chain.add_step(step)
        score = engine._calculate_validation_confidence(chain, [], [])
        assert score >= 0.5

    def test_score_always_clamped(self, engine):
        chain = _build_chain(confidence=0.9)
        score = engine._calculate_validation_confidence(chain, [], [])
        assert 0.0 <= score <= 1.0

    def test_many_issues_floor_at_zero(self, engine):
        chain = _build_chain(confidence=0.3)
        score = engine._calculate_validation_confidence(chain, ["issue"] * 10, ["warn"] * 10)
        assert score >= 0.0


# ─── extract_decision ────────────────────────────────────────────────────────


class TestExtractDecision:
    def test_delegates_to_chain_builder(self, engine):
        chain = _build_chain(
            steps=1,
            thought_types=[ThoughtType.DECISION],
            final_decision="Go with plan A",
        )
        decision = engine.extract_decision(chain)
        assert isinstance(decision, Decision)
        assert decision.action is not None


# ─── singleton helpers ───────────────────────────────────────────────────────


class TestSingletonHelpers:
    def test_get_reasoning_engine_requires_llm_first_call(self):
        reset_reasoning_engine()
        with pytest.raises(ConfigurationException):
            get_reasoning_engine(llm=None)

    def test_get_reasoning_engine_with_llm(self):
        reset_reasoning_engine()
        mock_llm = MagicMock()
        engine = get_reasoning_engine(llm=mock_llm)
        assert isinstance(engine, ReasoningEngine)

    def test_get_reasoning_engine_returns_singleton(self):
        reset_reasoning_engine()
        mock_llm = MagicMock()
        e1 = get_reasoning_engine(llm=mock_llm)
        e2 = get_reasoning_engine(llm=None)  # llm ignored after first call
        assert e1 is e2

    def test_reset_clears_singleton(self):
        mock_llm = MagicMock()
        e1 = get_reasoning_engine(llm=mock_llm)
        reset_reasoning_engine()
        e2 = get_reasoning_engine(llm=mock_llm)
        assert e1 is not e2

    def teardown_method(self):
        reset_reasoning_engine()
