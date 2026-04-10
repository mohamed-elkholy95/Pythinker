"""Shared semantic validation for comparison charts."""

from __future__ import annotations

import math
from collections.abc import Sequence

_ALLOWED_CHART_TYPES = {"bar", "line", "pie", "grouped_bar"}
_SEMANTIC_FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "performance": (
        "performance",
        "benchmark",
        "benchmarks",
        "latency",
        "throughput",
        "speed",
        "inference",
        "fps",
        "tps",
        "tokens/s",
        "tok/s",
    ),
    "cost": ("price", "pricing", "cost", "costs", "fee", "fees", "usd", "$"),
    "quality": ("score", "scores", "rating", "ratings", "accuracy", "error rate", "failure rate"),
    "capacity": (
        "parameter",
        "parameters",
        "parameter count",
        "model size",
        "vram",
        "memory",
        "ram",
        "storage",
        "core count",
        "cores",
        "bandwidth",
    ),
    "power": ("power", "watt", "watts", "consumption", "energy"),
}
_COMPATIBLE_FAMILIES: dict[str, set[str]] = {
    "performance": {"quality"},
    "quality": {"performance"},
}


def get_chart_spec_rejection_reason(
    *,
    report_title: str,
    chart_title: str,
    metric_name: str,
    labels: Sequence[str],
    values: Sequence[object],
    chart_type: str | None = None,
) -> str | None:
    """Reject malformed or semantically inconsistent chart specs.

    The checks are intentionally coarse and conservative. They are meant to
    block obviously misleading charts, not to fully understand the report.
    """
    if chart_type is not None and chart_type not in _ALLOWED_CHART_TYPES:
        return f"unsupported chart type: {chart_type}"

    if not chart_title.strip() or not metric_name.strip():
        return "missing chart title or metric name"

    if len(labels) != len(values):
        return "labels and values length mismatch"

    normalized_labels: list[str] = []
    for label, raw_value in zip(labels, values, strict=False):
        normalized_label = str(label).strip()
        if not normalized_label:
            return "point label is blank"

        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return f"point '{normalized_label}' has a non-numeric value"

        if not math.isfinite(value):
            return f"point '{normalized_label}' has a non-finite value"

        normalized_labels.append(normalized_label.casefold())

    if len(set(normalized_labels)) < 2:
        return "need at least two uniquely labeled points"

    metric_families = _semantic_families(metric_name)
    title_families = _semantic_families(chart_title)
    report_families = _semantic_families(report_title)

    if metric_families and title_families and not _families_are_compatible(metric_families, title_families):
        return f"chart title '{chart_title}' does not match metric '{metric_name}'"

    if metric_families and report_families and not _families_are_compatible(metric_families, report_families):
        return f"report title '{report_title}' does not support metric '{metric_name}'"

    return None


def _semantic_families(text: str) -> set[str]:
    """Map free text into coarse semantic families for mismatch checks."""
    lowered = text.casefold()
    return {
        family
        for family, keywords in _SEMANTIC_FAMILY_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    }


def _families_are_compatible(left: set[str], right: set[str]) -> bool:
    """Allow direct family matches plus a small compatibility map.

    Note: ``_COMPATIBLE_FAMILIES`` must be kept symmetric (if A→B then B→A)
    so that checking only ``left`` against ``right`` covers both directions.
    """
    if not left.isdisjoint(right):
        return True

    return any(
        family in _COMPATIBLE_FAMILIES and not _COMPATIBLE_FAMILIES[family].isdisjoint(right) for family in left
    )
