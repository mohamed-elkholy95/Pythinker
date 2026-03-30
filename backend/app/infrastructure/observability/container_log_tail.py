"""Best-effort Docker container log tails for operator / UI diagnostics.

Requires Docker socket access (same as DockerLogMonitor). Intended for local dev
when ``container_log_preview_enabled`` is set — not for production exposure.
"""

from __future__ import annotations

import logging

try:
    import docker
except Exception:
    docker = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)


def tail_running_container_logs(
    name_hints: tuple[str, ...] = ("backend", "sandbox"),
    tail_lines: int = 48,
) -> tuple[dict[str, list[str]], str | None]:
    """Return the last *tail_lines* log lines per hint for running containers.

    For each hint (e.g. ``\"backend\"``), picks the first *running* container whose
    name contains that substring (case-insensitive). Missing Docker or containers
    yield an empty list for that key.

    Second tuple element is a short UI hint when Docker is unusable (e.g. socket
    permission denied) or listing fails.
    """
    out: dict[str, list[str]] = {h: [] for h in name_hints}
    if docker is None:
        logger.debug("docker SDK unavailable; skipping container log tail")
        return out, "Docker SDK unavailable in this process."

    try:
        client = docker.from_env()
    except Exception as e:
        logger.warning("Docker client init failed for log tail: %s: %r", type(e).__name__, e)
        return out, (
            "Cannot open Docker socket (permission denied or missing mount). "
            "Ensure the backend service has group access to /var/run/docker.sock "
            "(see docker-compose group_add for OrbStack / Docker Desktop)."
        )

    try:
        containers = client.containers.list(all=False)
    except Exception as e:
        logger.warning("Docker list containers failed: %s: %r", type(e).__name__, e)
        return out, f"Could not list containers: {type(e).__name__}"

    for hint in name_hints:
        hint_lower = hint.lower()
        chosen = None
        for c in containers:
            try:
                name = (getattr(c, "name", "") or "").lower()
            except Exception as e:
                logger.debug("container name read failed: %s: %r", type(e).__name__, e)
                continue
            if hint_lower in name:
                chosen = c
                break
        if chosen is None:
            continue
        try:
            raw = chosen.logs(tail=tail_lines, timestamps=False)
        except Exception as e:
            logger.debug("logs() failed for %s: %s: %r", hint, type(e).__name__, e)
            continue
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = str(raw)
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
        out[hint] = lines[-tail_lines:]

    return out, None
