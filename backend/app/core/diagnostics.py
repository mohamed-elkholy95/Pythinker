"""Core helpers for diagnostics endpoints."""

from __future__ import annotations

from app.infrastructure.observability.container_log_tail import tail_running_container_logs


def tail_container_logs_preview(
    *,
    name_hints: tuple[str, ...] = ("backend", "sandbox"),
    tail_lines: int = 48,
):
    """Tail recent container logs for the diagnostics preview route."""
    return tail_running_container_logs(name_hints=name_hints, tail_lines=tail_lines)
