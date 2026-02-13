"""Adapter wiring domain MetricsPort calls to Prometheus metrics."""

import logging

from app.domain.external.observability import MetricsPort
from app.infrastructure.observability import prometheus_metrics as pm

logger = logging.getLogger(__name__)


class PrometheusMetricsAdapter(MetricsPort):
    """Concrete MetricsPort implementation backed by in-process Prometheus metrics."""

    def __init__(self) -> None:
        self._unknown_event_types: set[str] = set()
        self._unknown_counter_names: set[str] = set()
        self._unknown_histogram_names: set[str] = set()
        self._unknown_gauge_names: set[str] = set()

        self._counter_map: dict[str, pm.Counter] = {
            "response_policy_mode_total": pm.response_policy_mode_total,
            "compression_rejected_total": pm.compression_rejected_total,
            "clarification_requested_total": pm.clarification_requested_total,
            "clarification_resolved_total": pm.clarification_resolved_total,
            "user_stop_before_done_total": pm.user_stop_before_done_total,
            "fast_ack_refiner_total": pm.fast_ack_refiner_total,
            "entity_drift_detected_total": pm.entity_drift_detected_total,
            "output_relevance_failures_total": pm.output_relevance_failures_total,
            "guardrail_tripwire_total": pm.guardrail_tripwire_total,
            "delivery_fidelity_blocks_total": pm.delivery_fidelity_blocks_total,
            "delivery_integrity_gate_result_total": pm.delivery_integrity_gate_result_total,
            "delivery_integrity_gate_warning_total": pm.delivery_integrity_gate_warning_total,
            "delivery_integrity_gate_block_reason_total": pm.delivery_integrity_gate_block_reason_total,
            "delivery_integrity_stream_truncation_total": pm.delivery_integrity_stream_truncation_total,
        }

        self._histogram_map: dict[str, pm.Histogram] = {
            "fast_ack_refiner_latency_seconds": pm.fast_ack_refiner_latency_seconds,
            "final_response_tokens": pm.final_response_tokens,
            "clarification_wait_seconds": pm.clarification_wait_seconds,
            "guardrail_latency_seconds": pm.guardrail_latency_seconds,
            "workflow_phase_duration_seconds": pm.workflow_phase_duration,
        }

        self._gauge_map: dict[str, pm.Gauge] = {}

    def record_event(self, event_type: str, labels: dict[str, str] | None = None) -> None:
        """Record generic events (currently unmapped in Prometheus adapter)."""
        self._log_unknown_metric(
            name=event_type or "unknown",
            metric_type="event",
            cache=self._unknown_event_types,
        )

    def record_counter(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        try:
            metric = self._counter_map.get(name)
            if metric is None:
                self._log_unknown_metric(
                    name=name,
                    metric_type="counter",
                    cache=self._unknown_counter_names,
                )
                return
            metric.inc(labels or {}, value)
        except Exception as e:
            logger.debug("Failed to record counter metric '%s': %s", name, e)

    def record_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        try:
            metric = self._gauge_map.get(name)
            if metric is None:
                self._log_unknown_metric(
                    name=name,
                    metric_type="gauge",
                    cache=self._unknown_gauge_names,
                )
                return
            metric.set(labels or {}, value)
        except Exception as e:
            logger.debug("Failed to record gauge metric '%s': %s", name, e)

    def record_histogram(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        try:
            metric = self._histogram_map.get(name)
            if metric is None:
                self._log_unknown_metric(
                    name=name,
                    metric_type="histogram",
                    cache=self._unknown_histogram_names,
                )
                return
            metric.observe(labels or {}, value)
        except Exception as e:
            logger.debug("Failed to record histogram metric '%s': %s", name, e)

    def record_reward_hacking_signal(self, signal_type: str, severity: str) -> None:
        try:
            pm.record_reward_hacking_signal(signal=signal_type, severity=severity)
        except Exception as e:
            logger.debug("Failed to record reward hacking signal: %s", e)

    def record_plan_verification(self, status: str) -> None:
        try:
            pm.record_plan_verification(result=status)
        except Exception as e:
            logger.debug("Failed to record plan verification: %s", e)

    def record_failure_prediction(self, prediction: str, confidence: float) -> None:
        try:
            pm.record_failure_prediction(result=prediction, probability=confidence)
        except Exception as e:
            logger.debug("Failed to record failure prediction: %s", e)

    def record_error(self, error_type: str, message: str) -> None:
        try:
            pm.record_error(error_type=error_type, component="domain")
        except Exception as e:
            logger.debug("Failed to record error metric: %s", e)

    def update_token_budget(self, used: int, remaining: int) -> None:
        # Use request context session ID when available.
        try:
            from app.infrastructure.observability.context import get_session_id

            session_id = get_session_id() or "unknown"
        except Exception:
            session_id = "unknown"
        try:
            pm.update_token_budget(session_id=session_id, used=used, remaining=remaining)
        except Exception as e:
            logger.debug("Failed to update token budget metric: %s", e)

    def record_tool_trace_anomaly(self, tool_name: str, anomaly_type: str) -> None:
        try:
            pm.record_tool_trace_anomaly(tool=tool_name, anomaly_type=anomaly_type)
        except Exception as e:
            logger.debug("Failed to record tool trace anomaly: %s", e)

    def record_reflection_check(self, status: str) -> None:
        try:
            pm.record_reflection_check(result=status)
        except Exception as e:
            logger.debug("Failed to record reflection check: %s", e)

    def record_reflection_decision(self, decision: str) -> None:
        try:
            pm.record_reflection_decision(decision=decision)
        except Exception as e:
            logger.debug("Failed to record reflection decision: %s", e)

    def record_reflection_trigger(self, trigger_type: str) -> None:
        try:
            pm.record_reflection_trigger(trigger=trigger_type)
        except Exception as e:
            logger.debug("Failed to record reflection trigger: %s", e)

    def update_llm_concurrent_requests(self, active: int) -> None:
        try:
            pm.update_llm_concurrent_requests(count=active)
        except Exception as e:
            logger.debug("Failed to update LLM concurrent requests: %s", e)

    def update_llm_queue_waiting(self, waiting: int) -> None:
        try:
            pm.update_llm_queue_waiting(count=waiting)
        except Exception as e:
            logger.debug("Failed to update LLM queue waiting: %s", e)

    def _log_unknown_metric(self, name: str, metric_type: str, cache: set[str]) -> None:
        """Log unknown metric names once to keep logs low-noise."""
        normalized = (name or "").strip()
        if not normalized or normalized in cache:
            return
        cache.add(normalized)
        logger.debug("PrometheusMetricsAdapter: unknown %s metric name '%s'", metric_type, normalized)


def configure_domain_metrics_adapter() -> PrometheusMetricsAdapter:
    """Wire PrometheusMetricsAdapter into domain-level metric injection points."""
    from app.domain.external.observability import set_metrics as set_global_metrics
    from app.domain.services.agents.critic import set_metrics as set_critic_metrics
    from app.domain.services.agents.error_handler import set_metrics as set_error_handler_metrics
    from app.domain.services.agents.execution import set_metrics as set_execution_metrics
    from app.domain.services.agents.reflection import set_metrics as set_reflection_metrics
    from app.domain.services.agents.verifier import set_metrics as set_verifier_metrics
    from app.domain.services.tools.tool_tracing import set_metrics as set_tool_tracing_metrics

    adapter = PrometheusMetricsAdapter()
    set_global_metrics(adapter)
    set_execution_metrics(adapter)
    set_critic_metrics(adapter)
    set_verifier_metrics(adapter)
    set_error_handler_metrics(adapter)
    set_reflection_metrics(adapter)
    set_tool_tracing_metrics(adapter)
    logger.info("Prometheus MetricsPort adapter configured for domain services")
    return adapter
