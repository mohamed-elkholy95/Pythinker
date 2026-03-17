from app.core.prometheus_metrics import (
    delivery_integrity_gate_result_total,
    fast_ack_refiner_latency_seconds,
    fast_ack_refiner_total,
    final_response_tokens,
    reset_all_metrics,
    token_budget_used,
    token_budget_warnings,
)
from app.domain.external.observability import get_metrics, get_null_metrics
from app.domain.external.observability import set_metrics as set_global_metrics
from app.domain.services.agents.critic import set_metrics as set_critic_metrics
from app.domain.services.agents.error_handler import set_metrics as set_error_handler_metrics
from app.domain.services.agents.execution import set_metrics as set_execution_metrics
from app.domain.services.agents.reflection import set_metrics as set_reflection_metrics
from app.domain.services.agents.verifier import set_metrics as set_verifier_metrics
from app.domain.services.tools.tool_tracing import set_metrics as set_tool_tracing_metrics
from app.infrastructure.observability.context import request_context_scope
from app.infrastructure.observability.metrics_port_adapter import (
    PrometheusMetricsAdapter,
    configure_domain_metrics_adapter,
)


def _reset_domain_metrics_ports() -> None:
    null_metrics = get_null_metrics()
    set_global_metrics(null_metrics)
    set_execution_metrics(null_metrics)
    set_critic_metrics(null_metrics)
    set_verifier_metrics(null_metrics)
    set_error_handler_metrics(null_metrics)
    set_reflection_metrics(null_metrics)
    set_tool_tracing_metrics(null_metrics)


def setup_function() -> None:
    reset_all_metrics()
    _reset_domain_metrics_ports()


def teardown_function() -> None:
    reset_all_metrics()
    _reset_domain_metrics_ports()


def test_prometheus_adapter_records_delivery_integrity_counter() -> None:
    adapter = PrometheusMetricsAdapter()

    adapter.record_counter(
        "delivery_integrity_gate_result_total",
        labels={"provider": "openai", "result": "blocked", "strict_mode": "false"},
    )

    assert (
        delivery_integrity_gate_result_total.get({"provider": "openai", "result": "blocked", "strict_mode": "false"})
        == 1.0
    )


def test_prometheus_adapter_records_final_response_histogram() -> None:
    adapter = PrometheusMetricsAdapter()

    adapter.record_histogram("final_response_tokens", value=320.0, labels={"mode": "detailed"})

    observations = final_response_tokens.collect()
    assert len(observations) == 1
    assert observations[0]["labels"] == {"mode": "detailed"}
    assert observations[0]["count"] == 1
    assert observations[0]["sum"] == 320.0


def test_prometheus_adapter_records_fast_ack_metrics() -> None:
    adapter = PrometheusMetricsAdapter()

    adapter.record_counter(
        "fast_ack_refiner_total",
        labels={"status": "fallback", "reason": "timeout"},
    )
    adapter.record_histogram(
        "fast_ack_refiner_latency_seconds",
        value=0.12,
        labels={"status": "fallback"},
    )

    assert fast_ack_refiner_total.get({"status": "fallback", "reason": "timeout"}) == 1.0
    observations = fast_ack_refiner_latency_seconds.collect()
    assert len(observations) == 1
    assert observations[0]["labels"] == {"status": "fallback"}
    assert observations[0]["count"] == 1


def test_configure_domain_metrics_adapter_wires_global_metrics_port() -> None:
    adapter = configure_domain_metrics_adapter()

    assert get_metrics() is adapter

    get_metrics().record_counter(
        "delivery_integrity_gate_result_total",
        labels={"provider": "ollama", "result": "passed", "strict_mode": "true"},
    )

    assert (
        delivery_integrity_gate_result_total.get({"provider": "ollama", "result": "passed", "strict_mode": "true"})
        == 1.0
    )


def test_update_token_budget_records_aggregated_counters() -> None:
    adapter = PrometheusMetricsAdapter()

    with request_context_scope(session_id="session-observe-1"):
        adapter.update_token_budget(used=321, remaining=654)
        adapter.update_token_budget(used=900, remaining=100)
        adapter.update_token_budget(used=950, remaining=50)

    # Aggregated counters have no session labels.
    assert token_budget_used.get({}) == 950
    # Warning should only be emitted once per session after crossing threshold.
    assert token_budget_warnings.get({}) == 1
