import logging
import re
import threading
import time

try:
    import docker
except Exception:
    docker = None
from app.core.config import get_settings

logger = logging.getLogger(__name__)

class DockerLogMonitor:
    def __init__(self, project_network: str | None = None, throttle_seconds: int | None = None):
        self._project_network = project_network
        self._throttle_seconds = throttle_seconds or get_settings().alert_throttle_seconds
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._last_alert_by_key: dict[str, float] = {}
        self._patterns: list[tuple[re.Pattern, int]] = [
            (re.compile(r"\b(error|exception|critical|panic|traceback|failed|unauthorized|timeout)\b", re.IGNORECASE), logging.ERROR),
            (re.compile(r"\bconnection refused|network unreachable|broken pipe|reset by peer\b", re.IGNORECASE), logging.ERROR),
            (re.compile(r"\boom|out\s*of\s*memory|oom-killer|killed process\b", re.IGNORECASE), logging.CRITICAL),
            (re.compile(r"\bdeprecation warning|deprecated endpoint\b", re.IGNORECASE), logging.WARNING),
            (re.compile(r"\bstuck pattern detected|shutdown timed out|failed to create task\b", re.IGNORECASE), logging.WARNING),
        ]
        self._client = None

    def start(self) -> None:
        if docker is None:
            logger.warning("Docker SDK not available; skipping DockerLogMonitor")
            return
        try:
            self._client = docker.from_env()
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            return
        containers = self._list_target_containers()
        for c in containers:
            t = threading.Thread(target=self._stream_container_logs, args=(c,), daemon=True)
            t.start()
            self._threads.append(t)
        logger.info(f"DockerLogMonitor started for {len(containers)} containers")

    def stop(self) -> None:
        self._stop_event.set()
        for t in self._threads:
            try:
                t.join(timeout=1.0)
            except Exception as e:
                logger.debug(f"Thread join failed during shutdown: {e}")
        self._threads.clear()
        logger.info("DockerLogMonitor stopped")

    def _list_target_containers(self):
        try:
            if self._project_network:
                containers = []
                for c in self._client.containers.list(all=False):
                    try:
                        networks = (c.attrs.get("NetworkSettings", {}).get("Networks", {}) or {})
                        if self._project_network in networks:
                            containers.append(c)
                    except Exception as e:
                        logger.debug(f"Skipping container due to error: {e}")
                        continue
                return containers
            return self._client.containers.list(all=False)
        except Exception as e:
            logger.error(f"Failed to list containers: {e}")
            return []

    def _stream_container_logs(self, container) -> None:
        name = getattr(container, "name", "unknown")
        try:
            # Fix for "Invalid stream ID specified as stream command argument" error:
            # Don't combine since parameter with stream/follow as it can cause API errors
            # Instead, use tail to get recent logs and then follow for new ones
            log_stream = container.logs(
                stream=True,
                follow=True,
                tail=50  # Get last 50 lines instead of using 'since'
            )
            for raw in log_stream:
                if self._stop_event.is_set():
                    break
                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception as e:
                    logger.debug(f"Failed to decode log line: {e}")
                    continue
                if not line:
                    continue
                self._process_line(name, line)
        except Exception as e:
            logger.warning(f"Log stream ended for {name}: {e}")

    def _process_line(self, container_name: str, line: str) -> None:
        # Prevent infinite cascade: ignore our own log output
        if "docker_log_monitor" in line:
            return
        # Ignore known benign containerized Chrome D-Bus errors
        if "dbus" in line.lower() and ("Failed to connect to the bus" in line or "NameHasOwner" in line):
            return
        # Ignore GCM deprecation/auth errors (expected in sandboxed Chrome)
        if "gcm" in line.lower() and ("DEPRECATED_ENDPOINT" in line or "Authentication Failed" in line):
            return
        level = None
        for pattern, lvl in self._patterns:
            if pattern.search(line):
                level = lvl
                break
        if level is None:
            lower = line.lower()
            if "warn" in lower:
                level = logging.WARNING
        if level is None:
            return
        key = f"{container_name}:{level}:{line[:180]}"
        now = time.time()
        last = self._last_alert_by_key.get(key)
        if last is not None and (now - last) < self._throttle_seconds:
            return
        self._last_alert_by_key[key] = now
        msg = f"[container={container_name}] {line}"
        if level >= logging.ERROR:
            logger.error(msg)
        elif level == logging.WARNING:
            logger.warning(msg)
