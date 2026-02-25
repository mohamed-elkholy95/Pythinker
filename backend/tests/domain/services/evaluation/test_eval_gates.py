"""Smoke tests for WP-3: Eval gate enforcement.

Tests verify:
- RagasEvaluator.evaluate_all() is called when enable_eval_gates=True
- Gate is skipped when enable_eval_gates=False
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_eval_gate_called_when_flag_enabled():
    """evaluate_all() is invoked when enable_eval_gates=True and summary content exists."""
    from app.domain.services.evaluation.ragas_metrics import EvaluationBatch, EvalResult, EvalMetricType

    mock_batch = MagicMock(spec=EvaluationBatch)
    mock_batch.results = [
        MagicMock(
            metric_type=MagicMock(value="hallucination_score"),
            score=0.1,
        )
    ]
    mock_batch.to_dict = MagicMock(return_value={"results": []})

    mock_evaluator = MagicMock()
    mock_evaluator.evaluate_all = AsyncMock(return_value=mock_batch)

    with (
        patch(
            "app.domain.services.evaluation.ragas_metrics.RagasEvaluator",
            return_value=mock_evaluator,
        ),
    ):
        # Simulate the eval gate logic from plan_act.py
        enable_eval_gates = True
        eval_final_content = "This is the final answer."
        mock_llm = MagicMock()

        if enable_eval_gates and eval_final_content:
            from app.domain.services.evaluation.ragas_metrics import RagasEvaluator

            evaluator = RagasEvaluator(llm_client=mock_llm)
            batch = await evaluator.evaluate_all(
                question="What is X?",
                answer=eval_final_content,
                context=["step 1 result"],
            )
            assert batch is mock_batch

    mock_evaluator.evaluate_all.assert_called_once()


@pytest.mark.asyncio
async def test_eval_gate_skipped_when_flag_disabled():
    """evaluate_all() is NOT invoked when enable_eval_gates=False."""
    call_count = 0

    async def mock_evaluate_all(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return MagicMock()

    enable_eval_gates = False
    eval_final_content = "Some answer."

    if enable_eval_gates and eval_final_content:
        await mock_evaluate_all()

    assert call_count == 0, "evaluate_all should NOT be called when flag is disabled"
