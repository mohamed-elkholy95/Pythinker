"""Tests for Agent Robustness Prometheus metrics (2026-02-13 plan)."""

import pytest

from app.core.prometheus_metrics import (
    delivery_fidelity_blocks_total,
    entity_drift_detected_total,
    guardrail_latency_seconds,
    guardrail_tripwire_total,
    output_relevance_failures_total,
    output_relevance_score,
    reset_all_metrics,
    step_name_quality_violations_total,
)


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_all_metrics()
    yield
    reset_all_metrics()


def test_entity_drift_detected_total_increments() -> None:
    entity_drift_detected_total.inc({"phase": "summarize"})
    entity_drift_detected_total.inc({"phase": "summarize"})
    assert entity_drift_detected_total.get({"phase": "summarize"}) == 2.0


def test_output_relevance_failures_total_increments() -> None:
    output_relevance_failures_total.inc({"severity": "high"})
    output_relevance_failures_total.inc({"severity": "medium"})
    assert output_relevance_failures_total.get({"severity": "high"}) == 1.0
    assert output_relevance_failures_total.get({"severity": "medium"}) == 1.0


def test_step_name_quality_violations_total_increments() -> None:
    step_name_quality_violations_total.inc({"violation": "empty_verb"})
    step_name_quality_violations_total.inc({"violation": "banned_verb"})
    assert step_name_quality_violations_total.get({"violation": "empty_verb"}) == 1.0
    assert step_name_quality_violations_total.get({"violation": "banned_verb"}) == 1.0


def test_guardrail_tripwire_total_increments() -> None:
    guardrail_tripwire_total.inc({"guardrail": "relevance"})
    guardrail_tripwire_total.inc({"guardrail": "fidelity"})
    assert guardrail_tripwire_total.get({"guardrail": "relevance"}) == 1.0
    assert guardrail_tripwire_total.get({"guardrail": "fidelity"}) == 1.0


def test_delivery_fidelity_blocks_total_increments() -> None:
    delivery_fidelity_blocks_total.inc({"mode": "enforce"})
    assert delivery_fidelity_blocks_total.get({"mode": "enforce"}) == 1.0


def test_guardrail_latency_seconds_observes() -> None:
    guardrail_latency_seconds.observe({"phase": "extract"}, 0.05)
    guardrail_latency_seconds.observe({"phase": "extract"}, 0.03)
    observations = guardrail_latency_seconds.collect()
    phase_extract = next(o for o in observations if o["labels"].get("phase") == "extract")
    assert phase_extract["count"] == 2
    assert phase_extract["sum"] == pytest.approx(0.08)


def test_output_relevance_score_observes() -> None:
    output_relevance_score.observe({}, 0.85)
    output_relevance_score.observe({}, 0.42)
    observations = output_relevance_score.collect()
    assert len(observations) >= 1
    total_count = sum(o["count"] for o in observations)
    assert total_count == 2
