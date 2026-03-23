"""Metrics API Routes

Provides endpoints for Prometheus scraping and metrics inspection.

Endpoints:
    GET /metrics - Prometheus text exposition format (HTTP Basic Auth)
    GET /metrics/json - JSON format metrics (Admin auth)
    GET /metrics/health - Health check for monitoring (Admin auth)
"""

import logging
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, Security, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.prometheus_metrics import (
    active_sessions,
    collect_all_metrics,
    format_prometheus,
    metrics_auth_failure_total,
)
from app.domain.models.user import User
from app.domain.services.agents.metrics import get_metrics_collector
from app.domain.services.tools.cache_layer import get_cache_stats, get_combined_cache_stats
from app.domain.services.tools.dynamic_toolset import get_toolset_manager
from app.infrastructure.observability.llm_tracer import NoOpLLMTracer, get_llm_tracer
from app.infrastructure.observability.otel_exporter import get_otel_config
from app.infrastructure.observability.tracer import get_tracer
from app.interfaces.dependencies import require_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])

# HTTP Basic Auth for Prometheus scraping endpoint
_http_basic = HTTPBasic(auto_error=False)


async def _verify_metrics_basic_auth(
    credentials: HTTPBasicCredentials | None = Security(_http_basic),
) -> None:
    """Verify HTTP Basic Auth credentials for the Prometheus metrics endpoint.

    When METRICS_PASSWORD is empty (development default), authentication is
    bypassed to maintain backward compatibility. In production, set
    METRICS_PASSWORD in .env to enforce authentication.

    Uses constant-time comparison to prevent timing attacks.

    Raises:
        HTTPException: 401 Unauthorized if credentials are invalid.
    """
    settings = get_settings()

    # If no password configured, allow unauthenticated access (development mode)
    if not settings.metrics_password:
        return

    # Password is configured -- credentials are now required
    if not credentials:
        metrics_auth_failure_total.inc()
        logger.warning("[SECURITY] Metrics endpoint accessed without credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Constant-time comparison to prevent timing attacks
    correct_username = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.metrics_username.encode("utf-8"),
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.metrics_password.encode("utf-8"),
    )

    if not (correct_username and correct_password):
        metrics_auth_failure_total.inc()
        logger.warning(
            "[SECURITY] Failed metrics authentication attempt from user: %s",
            credentials.username,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


class TypoCorrectionFeedbackRequest(BaseModel):
    """Feedback payload for typo correction overrides."""

    original: str = Field(min_length=1, description="Original word/token")
    corrected: str = Field(min_length=1, description="System-corrected word/token")
    user_override: str = Field(min_length=1, description="User-preferred correction")


@router.get("", response_class=Response)
async def get_prometheus_metrics(
    _auth: None = Depends(_verify_metrics_basic_auth),
):
    """Get metrics in Prometheus text exposition format.

    This endpoint is designed to be scraped by Prometheus.
    Returns metrics in the standard Prometheus text format.

    Authentication: HTTP Basic Auth when METRICS_PASSWORD is configured.
    """
    # Update dynamic metrics before collection
    await _update_dynamic_metrics()

    # Generate Prometheus format
    content = format_prometheus()

    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/json")
async def get_json_metrics(
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Get metrics in JSON format.

    Returns all metrics in a structured JSON format for
    custom dashboards or debugging.
    """
    # Update dynamic metrics
    await _update_dynamic_metrics()

    # Collect all metrics
    metrics_data = collect_all_metrics()

    # Add tracer metrics
    tracer = get_tracer()
    tracer_metrics = tracer.get_all_metrics()

    # Add cache stats
    cache_stats = get_cache_stats().to_dict()

    # Add OTEL status
    otel_config = get_otel_config()
    otel_status = {
        "enabled": otel_config.enabled if otel_config else False,
        "endpoint": otel_config.endpoint if otel_config else None,
    }

    return {
        **metrics_data,
        "tracer": tracer_metrics,
        "cache": cache_stats,
        "otel": otel_status,
    }


@router.get("/health")
async def health_check(
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Health check endpoint for monitoring systems.

    Returns basic health information and uptime status.
    """
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "pythinker-agent",
    }


@router.get("/tracer")
async def get_tracer_metrics(
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Get detailed tracer metrics.

    Returns metrics from the internal tracer including
    active traces and per-agent statistics.
    """
    tracer = get_tracer()
    return {
        "metrics": tracer.get_all_metrics(),
        "active_traces": len(tracer.get_active_traces()),
    }


@router.get("/cache")
async def get_cache_metrics(
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Get tool cache statistics.

    Returns cache hit/miss rates and other caching metrics.
    """
    return {
        "cache": get_cache_stats().to_dict(),
    }


@router.get("/agent")
async def get_agent_optimization_metrics(
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Get agent optimization metrics.

    Returns comprehensive metrics for all agent optimizations:
    - Token usage and cache savings
    - L1/L2 cache hit rates
    - Tool execution statistics
    - Hallucination detection counts
    - Dynamic toolset reduction rates
    - Latency percentiles
    """
    collector = get_metrics_collector()
    return collector.get_summary()


@router.get("/agent/prometheus")
async def get_agent_prometheus_metrics(
    current_user: User = Depends(require_admin_user),
):
    """Get agent metrics in Prometheus format.

    Designed for Prometheus scraping of agent-specific metrics.
    """
    collector = get_metrics_collector()
    content = collector.export_prometheus()

    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/agent/timeseries")
async def get_agent_timeseries(
    minutes: int = 60,
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Get time-series metrics for the last N minutes.

    Args:
        minutes: Number of minutes of history (max 60)

    Returns time-bucketed metrics for trend analysis.
    """
    collector = get_metrics_collector()
    minutes = min(minutes, 60)  # Cap at 60 minutes

    return {"period_minutes": minutes, "buckets": collector.get_time_series(minutes)}


@router.get("/agent/cache")
async def get_agent_cache_details(
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Get detailed cache metrics including L1 and L2.

    Returns multi-tier cache performance data.
    """
    combined = get_combined_cache_stats()
    collector = get_metrics_collector()

    return {
        "l1": combined["l1"],
        "l2": combined["l2"],
        "combined": combined["combined"],
        "collector": {
            "l1_hits": collector.cache.l1_hits,
            "l1_misses": collector.cache.l1_misses,
            "l2_hits": collector.cache.l2_hits,
            "l2_misses": collector.cache.l2_misses,
        },
    }


@router.get("/agent/toolset")
async def get_toolset_metrics(
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Get dynamic toolset filtering metrics.

    Returns statistics about tool filtering effectiveness.
    """
    manager = get_toolset_manager()
    collector = get_metrics_collector()

    return {
        "toolset": manager.get_stats(),
        "avg_reduction": f"{collector.avg_toolset_reduction:.1%}",
        "samples": len(collector._toolset_reductions),
    }


@router.post("/agent/reset")
async def reset_agent_metrics(
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Reset all agent optimization metrics.

    Returns confirmation of reset.
    """
    collector = get_metrics_collector()
    collector.reset()

    return {"status": "reset", "timestamp": time.time()}


@router.get("/tokens/summary")
async def get_token_usage_summary(
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Get token usage summary across all LLM calls.

    Returns aggregated token counts, costs, and latency by model.
    This endpoint provides data for cost dashboards and usage monitoring.
    """
    llm_tracer = get_llm_tracer()

    # Get metrics from LLM tracer
    if isinstance(llm_tracer, NoOpLLMTracer):
        metrics = llm_tracer.get_metrics_summary()
    else:
        # For external tracers, return basic info
        metrics = {
            "total_calls": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "note": "Detailed metrics available in external tracing platform",
        }

    # Add tracer URL if available
    trace_url = llm_tracer.get_trace_url("latest") if hasattr(llm_tracer, "get_trace_url") else None

    return {
        "summary": metrics,
        "trace_dashboard_url": trace_url,
        "timestamp": time.time(),
    }


@router.get("/tokens/timeline")
async def get_token_timeline(
    minutes: int = 60,
    model: str | None = None,
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Get time-series token usage data.

    Args:
        minutes: Number of minutes of history (max 1440 = 24h)
        model: Optional model filter

    Returns time-bucketed token usage for trend analysis.
    """
    # Cap at 24 hours
    minutes = min(minutes, 1440)

    llm_tracer = get_llm_tracer()

    if isinstance(llm_tracer, NoOpLLMTracer):
        # Build timeline from stored traces
        now = time.time()
        cutoff = now - (minutes * 60)

        # Group by 5-minute buckets
        bucket_size = 5 * 60  # 5 minutes in seconds
        buckets: dict[int, dict[str, Any]] = {}

        for trace in llm_tracer.get_traces():
            trace_time = trace.start_time.timestamp()
            if trace_time < cutoff:
                continue

            if model and trace.model != model:
                continue

            bucket_key = int(trace_time // bucket_size) * bucket_size

            if bucket_key not in buckets:
                buckets[bucket_key] = {
                    "timestamp": bucket_key,
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cost_usd": 0.0,
                    "avg_latency_ms": 0.0,
                    "latencies": [],
                }

            buckets[bucket_key]["calls"] += 1
            buckets[bucket_key]["prompt_tokens"] += trace.prompt_tokens
            buckets[bucket_key]["completion_tokens"] += trace.completion_tokens
            buckets[bucket_key]["cost_usd"] += trace.total_cost_usd
            buckets[bucket_key]["latencies"].append(trace.latency_ms)

        # Calculate averages and sort
        timeline = []
        for bucket in sorted(buckets.values(), key=lambda x: x["timestamp"]):
            latencies = bucket.pop("latencies")
            bucket["avg_latency_ms"] = sum(latencies) / len(latencies) if latencies else 0
            bucket["cost_usd"] = round(bucket["cost_usd"], 6)
            timeline.append(bucket)

        return {
            "period_minutes": minutes,
            "bucket_size_seconds": bucket_size,
            "model_filter": model,
            "timeline": timeline,
        }
    return {
        "period_minutes": minutes,
        "note": "Timeline available in external tracing platform",
        "timeline": [],
    }


@router.get("/costs")
async def get_cost_tracking(
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Get cost tracking data for LLM usage.

    Returns cost breakdown by model, session, and time period.
    Useful for budget monitoring and cost optimization.
    """
    llm_tracer = get_llm_tracer()

    if isinstance(llm_tracer, NoOpLLMTracer):
        metrics = llm_tracer.get_metrics_summary()

        # Calculate cost breakdown
        by_model = metrics.get("by_model", {})
        total_cost = metrics.get("total_cost_usd", 0.0)

        # Calculate percentages
        cost_breakdown = {}
        for model_name, model_stats in by_model.items():
            model_cost = model_stats.get("cost_usd", 0.0)
            cost_breakdown[model_name] = {
                "cost_usd": round(model_cost, 6),
                "percentage": round(model_cost / total_cost * 100, 2) if total_cost > 0 else 0,
                "calls": model_stats.get("calls", 0),
                "tokens": model_stats.get("tokens", 0),
            }

        return {
            "total_cost_usd": round(total_cost, 6),
            "by_model": cost_breakdown,
            "period": "all_time",
            "timestamp": time.time(),
        }
    return {
        "note": "Cost tracking available in external tracing platform",
        "total_cost_usd": 0.0,
        "by_model": {},
    }


@router.get("/typo-correction")
async def get_typo_correction_metrics(
    current_user: User = Depends(require_admin_user),
) -> dict[str, Any]:
    """Get typo correction analytics and learned feedback summary."""
    from app.application.services.typo_correction_service import get_typo_correction_service

    service = get_typo_correction_service()
    return {
        "data": service.get_summary(),
        "status": "success",
    }


@router.post("/typo-correction/feedback")
async def submit_typo_correction_feedback(
    request: TypoCorrectionFeedbackRequest,
    current_user: User = Depends(require_admin_user),
) -> dict[str, str]:
    """Record user override feedback for typo correction decisions."""
    from app.application.services.typo_correction_service import get_typo_correction_service

    service = get_typo_correction_service()
    service.submit_feedback(
        original=request.original,
        corrected=request.corrected,
        user_override=request.user_override,
    )
    return {"status": "recorded"}


async def _update_dynamic_metrics() -> None:
    """Update metrics that need to be calculated dynamically.

    This is called before metrics collection to ensure
    gauges reflect current state.
    """
    tracer = get_tracer()
    tracer_metrics = tracer.get_all_metrics()

    # Update active counts
    active_sessions.set({}, tracer_metrics.get("active_traces", 0))
    # Note: active_agents would be updated by the agent service


@router.get("/stream")
async def stream_metrics(
    current_user: User = Depends(require_admin_user),
):
    """Stream real-time metrics via SSE (Phase 6).

    Returns:
        Server-Sent Events stream with metrics updates every 2 seconds
    """
    import asyncio
    import json

    from sse_starlette.sse import EventSourceResponse

    async def event_generator():
        while True:
            # Collect Prometheus data
            await _update_dynamic_metrics()
            prometheus_data = collect_all_metrics()

            # Get agent-level metrics
            metrics_collector = get_metrics_collector()
            agent_data = metrics_collector.get_summary()

            payload = {
                "timestamp": time.time(),
                "prometheus": prometheus_data.get("metrics", {}),
                "agent": agent_data,
            }

            yield {"data": json.dumps(payload)}
            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())


@router.get("/dashboard")
async def get_dashboard_summary(
    current_user: User = Depends(require_admin_user),
):
    """Get comprehensive dashboard metrics (Phase 6).

    Returns:
        Dashboard summary with performance, workflow, tool, and error metrics
    """
    from app.application.services.analytics_service import get_analytics_service

    analytics = get_analytics_service()
    summary = await analytics.get_dashboard_summary()

    return {
        "data": summary,
        "status": "success",
    }


@router.get("/workflow-efficiency")
async def get_workflow_efficiency(
    current_user: User = Depends(require_admin_user),
):
    """Get workflow efficiency metrics (Phase 6).

    Returns:
        Workflow efficiency metrics including completion rate and replanning frequency
    """
    from app.application.services.analytics_service import get_analytics_service

    analytics = get_analytics_service()
    metrics = await analytics.get_workflow_efficiency_metrics(days=7)

    return {
        "data": metrics,
        "status": "success",
    }


@router.get("/tool-performance")
async def get_tool_performance(
    current_user: User = Depends(require_admin_user),
):
    """Get tool performance breakdown (Phase 6).

    Returns:
        Tool performance metrics including success rates and average durations
    """
    from app.application.services.analytics_service import get_analytics_service

    analytics = get_analytics_service()
    metrics = await analytics.get_tool_performance_breakdown()

    return {
        "data": metrics,
        "status": "success",
    }
