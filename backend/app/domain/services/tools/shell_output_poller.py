"""Real-time shell output poller for live terminal streaming.

Supports two modes (chosen automatically at startup):

1. **Push-based SSE** (preferred): Connects to the sandbox's
   ``GET /api/v1/shell/stream/{session_id}`` endpoint and consumes
   server-sent events.  Lower latency, lower overhead.

2. **Poll-based fallback**: Periodically calls ``Sandbox.view_shell()``
   to capture incremental stdout deltas.  Used when the sandbox image
   does not expose the SSE endpoint (HTTP 404).

Both modes emit ``ToolStreamEvent`` (delta output) and
``ToolProgressEvent`` (elapsed time, %) into an asyncio.Queue for the
caller to drain.

DDD-compliant: depends only on the Sandbox protocol (domain interface).
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from app.domain.models.event import ToolProgressEvent, ToolStreamEvent

if TYPE_CHECKING:
    from app.domain.external.sandbox import Sandbox

logger = logging.getLogger(__name__)

# Queue capacity — prevents unbounded memory growth
_QUEUE_MAX_SIZE = 1000


class ShellOutputPoller:
    """Polls sandbox shell output and queues streaming events.

    Usage::

        poller = ShellOutputPoller(sandbox, session_id, tool_call_id, ...)
        poll_task = asyncio.create_task(poller.start_polling())
        try:
            # ... run tool concurrently ...
            async for event in poller.drain_events():
                yield event
        finally:
            poller.stop()
            await poll_task
    """

    def __init__(
        self,
        sandbox: "Sandbox",
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        function_name: str,
        poll_interval_ms: int = 500,
        max_polls: int = 600,
    ) -> None:
        self._sandbox = sandbox
        self._session_id = session_id
        self._tool_call_id = tool_call_id
        self._tool_name = tool_name
        self._function_name = function_name
        self._poll_interval_s = poll_interval_ms / 1000.0
        self._max_polls = max_polls

        self._queue: asyncio.Queue[ToolStreamEvent | ToolProgressEvent] = asyncio.Queue(
            maxsize=_QUEUE_MAX_SIZE,
        )
        self._stop_event = asyncio.Event()
        self._last_output = ""
        self._start_time: float = 0.0
        self._poll_count = 0
        self._using_sse = False  # True when push-based mode is active

    # ── Public API ───────────────────────────────────────────────

    async def start_polling(self) -> None:
        """Main entry point.  Run as an ``asyncio.Task``.

        Tries push-based SSE first.  On failure (404 or any error
        during setup), falls back to the legacy polling loop.
        """
        self._start_time = time.monotonic()

        # Attempt SSE push-based streaming first
        try:
            await self._run_sse_stream()
            return  # SSE stream completed cleanly
        except Exception:
            if self._using_sse:
                # SSE was working but broke mid-stream — log and fall back
                logger.debug(
                    "SSE stream interrupted for session %s — falling back to polling",
                    self._session_id,
                    exc_info=True,
                )
            else:
                # SSE not available (404 or connection error) — expected on older images
                logger.debug(
                    "SSE endpoint not available for session %s — using polling",
                    self._session_id,
                )

        # Fall back to poll-based loop
        self._using_sse = False
        await self._run_poll_loop()

    def stop(self) -> None:
        """Signal the polling/streaming loop to stop."""
        self._stop_event.set()

    async def drain_events(self) -> AsyncGenerator[ToolStreamEvent | ToolProgressEvent, None]:
        """Yield all queued events without blocking."""
        while not self._queue.empty():
            try:
                yield self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    # ── SSE push-based streaming ────────────────────────────────

    async def _run_sse_stream(self) -> None:
        """Consume the sandbox SSE endpoint and enqueue events."""
        sse_gen = self._sandbox.stream_shell_output(self._session_id)
        self._using_sse = True

        async for event_type, data in sse_gen:
            if self._stop_event.is_set():
                break

            self._poll_count += 1
            elapsed_ms = (time.monotonic() - self._start_time) * 1000

            if event_type == "output":
                content = data.get("content", "")
                if content:
                    stream_event = ToolStreamEvent(
                        tool_call_id=self._tool_call_id,
                        tool_name=self._tool_name,
                        function_name=self._function_name,
                        partial_content=content,
                        content_type="terminal",
                    )
                    self._enqueue(stream_event)
                    self._record_stream_event_metric()
                    self._record_poll_metric("success")

            elif event_type == "complete":
                # Final progress at 99% (tool completion sets 100%)
                progress_event = ToolProgressEvent(
                    tool_call_id=self._tool_call_id,
                    tool_name=self._tool_name,
                    function_name=self._function_name,
                    progress_percent=99,
                    current_step="Command finished",
                    steps_completed=self._poll_count,
                    elapsed_ms=elapsed_ms,
                )
                self._enqueue(progress_event)
                self._record_poll_metric("success")
                break

            elif event_type == "heartbeat":
                # Emit progress on heartbeats
                progress_percent = min(
                    int((elapsed_ms / (self._max_polls * self._poll_interval_s * 1000)) * 100),
                    99,
                )
                progress_event = ToolProgressEvent(
                    tool_call_id=self._tool_call_id,
                    tool_name=self._tool_name,
                    function_name=self._function_name,
                    progress_percent=progress_percent,
                    current_step="Executing command",
                    steps_completed=self._poll_count,
                    elapsed_ms=elapsed_ms,
                )
                self._enqueue(progress_event)

            elif event_type == "error":
                logger.debug("SSE error event for session %s: %s", self._session_id, data)
                self._record_poll_metric("error")
                break

            # Emit periodic progress events (every 5 output events)
            if event_type == "output" and self._poll_count % 5 == 0:
                progress_percent = min(
                    int((elapsed_ms / (self._max_polls * self._poll_interval_s * 1000)) * 100),
                    99,
                )
                progress_event = ToolProgressEvent(
                    tool_call_id=self._tool_call_id,
                    tool_name=self._tool_name,
                    function_name=self._function_name,
                    progress_percent=progress_percent,
                    current_step="Executing command",
                    steps_completed=self._poll_count,
                    elapsed_ms=elapsed_ms,
                )
                self._enqueue(progress_event)

    # ── Poll-based fallback ─────────────────────────────────────

    async def _run_poll_loop(self) -> None:
        """Legacy polling loop — calls view_shell() periodically."""
        while not self._stop_event.is_set() and self._poll_count < self._max_polls:
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._poll_interval_s,
                )
                # stop_event was set — exit loop
                break
            except TimeoutError:
                # Normal timeout — time to poll
                pass

            self._poll_count += 1
            await self._poll_once()

    async def _poll_once(self) -> None:
        """Run a single poll and enqueue delta events."""
        try:
            result = await self._sandbox.view_shell(self._session_id)
        except Exception:
            logger.debug(
                "Shell poll failed for session %s (poll #%d)",
                self._session_id,
                self._poll_count,
                exc_info=True,
            )
            self._record_poll_metric("error")
            return

        # Extract current output from result
        current_output = self._extract_output(result)
        if current_output is None:
            self._record_poll_metric("empty")
            return

        self._record_poll_metric("success")

        # Compute delta
        delta = ""
        if len(current_output) > len(self._last_output):
            delta = current_output[len(self._last_output) :]
        elif current_output != self._last_output:
            # Output changed but not appended (reset/truncation) — send full
            delta = current_output

        self._last_output = current_output

        elapsed_ms = (time.monotonic() - self._start_time) * 1000

        # Emit ToolStreamEvent for delta content
        if delta:
            stream_event = ToolStreamEvent(
                tool_call_id=self._tool_call_id,
                tool_name=self._tool_name,
                function_name=self._function_name,
                partial_content=delta,
                content_type="terminal",
            )
            self._enqueue(stream_event)
            self._record_stream_event_metric()

        # Emit ToolProgressEvent for timing
        progress_percent = min(
            int((self._poll_count / self._max_polls) * 100),
            99,  # Never 100% until the tool actually completes
        )
        progress_event = ToolProgressEvent(
            tool_call_id=self._tool_call_id,
            tool_name=self._tool_name,
            function_name=self._function_name,
            progress_percent=progress_percent,
            current_step="Executing command",
            steps_completed=self._poll_count,
            steps_total=self._max_polls,
            elapsed_ms=elapsed_ms,
        )
        self._enqueue(progress_event)

    # ── Shared helpers ──────────────────────────────────────────

    def _enqueue(self, event: ToolStreamEvent | ToolProgressEvent) -> None:
        """Non-blocking enqueue with backpressure drop."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop event rather than blocking tool execution
            logger.debug(
                "Shell poller queue full for %s — dropping event",
                self._tool_call_id,
            )

    @staticmethod
    def _record_poll_metric(status: str) -> None:
        """Record poll outcome metric (non-fatal on import failure)."""
        try:
            from app.core.prometheus_metrics import live_shell_polls_total

            live_shell_polls_total.inc({"status": status})
        except Exception:  # noqa: S110
            # Metrics are best-effort — never block tool execution
            pass

    def _record_stream_event_metric(self) -> None:
        """Record stream event emission metric."""
        try:
            from app.core.prometheus_metrics import live_stream_events_total

            live_stream_events_total.inc({"tool_name": self._tool_name})
        except Exception:  # noqa: S110
            # Metrics are best-effort — never block tool execution
            pass

    @staticmethod
    def _extract_output(result: object) -> str | None:
        """Extract stdout text from a ToolResult."""
        # ToolResult has .data which may contain stdout or console output
        if hasattr(result, "data") and result.data is not None:
            data = result.data
            if isinstance(data, dict):
                # Prefer 'output' then 'stdout' then 'console'
                for key in ("output", "stdout", "console"):
                    val = data.get(key)
                    if isinstance(val, str):
                        return val
                    if isinstance(val, list):
                        # Console records — join text
                        return "\n".join(r.get("text", str(r)) if isinstance(r, dict) else str(r) for r in val)
            if isinstance(data, str):
                return data
        # Fallback: check message
        if hasattr(result, "message") and isinstance(result.message, str):
            return result.message
        return None
