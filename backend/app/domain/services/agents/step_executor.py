"""Step-level execution helpers for the ExecutionAgent.

Owns model routing, result payload validation, and multimodal finding
tracking — methods that are exclusively called within the execute_step()
dispatch loop.

Usage:
    step_exec = StepExecutor(
        context_manager=ctx_mgr,
        source_tracker=src_tracker,
        view_tools=frozenset(ToolName._VIEW),
        metrics=metrics_port,
    )
    model = step_exec.select_model_for_step("Analyse data", thinking_mode="fast")
    step_exec.track_multimodal_findings(tool_event)
    ok = StepExecutor.apply_step_result_payload(step, parsed, raw)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.domain.external.observability import MetricsPort, get_null_metrics
from app.domain.models.agent_response import ExecutionStepResult
from app.domain.models.tool_name import ToolName

if TYPE_CHECKING:
    from app.domain.models.event import ToolEvent
    from app.domain.models.plan import Step
    from app.domain.services.agents.context_manager import ContextManager
    from app.domain.services.agents.source_tracker import SourceTracker

logger = logging.getLogger(__name__)


class StepExecutor:
    """Step-level execution helpers extracted from ExecutionAgent.

    Responsibilities:
    - Adaptive model selection per step (DeepCode Phase 1)
    - Structured result payload validation (strict + best-effort)
    - Multimodal finding tracking and persistence (view/browser operations)
    - Source tracking delegation (thin wrapper)

    All methods were previously private on ExecutionAgent and are
    called exclusively from ``execute_step()``.
    """

    __slots__ = (
        "_context_manager",
        "_metrics",
        "_multimodal_findings",
        "_source_tracker",
        "_view_operation_count",
        "_view_tools",
    )

    def __init__(
        self,
        *,
        context_manager: ContextManager,
        source_tracker: SourceTracker,
        view_tools: frozenset[str] | set[str] | None = None,
        metrics: MetricsPort | None = None,
    ) -> None:
        self._context_manager = context_manager
        self._source_tracker = source_tracker
        self._view_tools: frozenset[str] = (
            frozenset(view_tools) if view_tools else frozenset(t.value for t in ToolName._VIEW)
        )
        self._metrics: MetricsPort = metrics or get_null_metrics()
        self._view_operation_count: int = 0
        self._multimodal_findings: list[dict] = []

    # ── Model Selection ───────────────────────────────────────────────

    def select_model_for_step(
        self,
        step_description: str,
        *,
        user_thinking_mode: str | None = None,
    ) -> str | None:
        """Select appropriate model for the current step using ModelRouter.

        Args:
            step_description: The step description to analyze for complexity.
            user_thinking_mode: Optional user preference ("fast", "deep_think", or None/auto).

        Returns:
            Model name for the selected tier, or None on failure.
        """
        from app.domain.services.agents.model_router import ModelRouter, ModelTier, get_model_router

        try:
            if user_thinking_mode == "fast":
                router: ModelRouter = ModelRouter(force_tier=ModelTier.FAST, metrics=self._metrics)
                config = router.route(step_description)
                logger.debug("Model routing (forced fast): model=%s", config.model_name)
                return config.model_name
            if user_thinking_mode == "deep_think":
                router = ModelRouter(force_tier=ModelTier.POWERFUL, metrics=self._metrics)
                config = router.route(step_description)
                logger.debug("Model routing (forced deep_think): model=%s", config.model_name)
                return config.model_name

            # Default: auto — complexity-based routing via singleton
            router = get_model_router(metrics=self._metrics)
            config = router.route(step_description)
            logger.debug(
                "Model routing: tier=%s, model=%s, temp=%s, max_tokens=%s",
                config.tier.value,
                config.model_name,
                config.temperature,
                config.max_tokens,
            )
            return config.model_name

        except Exception as e:
            logger.warning("Model routing failed, using default: %s", e)
            return None

    # ── Result Payload Validation ─────────────────────────────────────

    @staticmethod
    def apply_step_result_payload(step: Step, parsed_response: Any, raw_message: str) -> bool:
        """Apply execution step payload with strict schema validation and safe fallback.

        Attempts ``ExecutionStepResult.model_validate`` first (strict).
        Falls back to best-effort extraction from partially structured payloads.
        As a last resort, marks the step unsuccessful.

        Args:
            step: Mutable Step object to update.
            parsed_response: LLM response parsed as dict/JSON.
            raw_message: The raw string LLM response.

        Returns:
            True if strict validation passed, False otherwise.
        """
        try:
            step_result = ExecutionStepResult.model_validate(parsed_response)
            step.success = step_result.success
            step.result = step_result.result or raw_message
            step.attachments = list(step_result.attachments)
            step.error = None if step_result.success else (step.error or "Step reported failure")
            return True
        except ValidationError as validation_err:
            logger.warning("Step response validation failed: %s", validation_err)

        # Best-effort extraction for partially structured payloads.
        if isinstance(parsed_response, dict) and any(
            key in parsed_response for key in ("success", "result", "attachments")
        ):
            success_value = parsed_response.get("success")
            step.success = success_value if isinstance(success_value, bool) else False

            result_value = parsed_response.get("result")
            step.result = str(result_value) if result_value is not None else raw_message

            attachments_value = parsed_response.get("attachments")
            if isinstance(attachments_value, list):
                step.attachments = [str(item) for item in attachments_value]
            else:
                step.attachments = []

            if not step.success:
                error_value = parsed_response.get("error")
                step.error = str(error_value) if error_value else "Step payload validation failed"
            return False

        step.success = False
        step.result = raw_message
        step.attachments = []
        step.error = "Step response did not match expected JSON schema"
        return False

    # ── Source Tracking ───────────────────────────────────────────────

    def track_sources_from_tool_event(self, event: ToolEvent) -> None:
        """Delegate source citation tracking to SourceTracker."""
        self._source_tracker.track_tool_event(event)

    # ── Multimodal Finding Tracking ───────────────────────────────────

    def track_multimodal_findings(self, event: ToolEvent) -> None:
        """Track and persist key findings from view operations.

        Per Pythinker pattern: save key findings every 2 view/browser
        operations, ensuring important visual information is persisted
        and available for later reference even if context is compressed.
        """
        if event.function_name not in self._view_tools:
            return

        if not event.function_result or not event.function_result.success:
            return

        self._view_operation_count += 1

        finding = self._extract_multimodal_finding(event)
        if finding:
            self._multimodal_findings.append(finding)

        # Persist every 2 operations (Pythinker pattern)
        if self._view_operation_count >= 2:
            self._persist_key_findings()
            self._view_operation_count = 0

    def get_multimodal_findings(self) -> list[dict]:
        """Return a shallow copy of accumulated multimodal findings."""
        return self._multimodal_findings.copy()

    def clear(self) -> None:
        """Reset multimodal tracking state."""
        self._view_operation_count = 0
        self._multimodal_findings = []

    # ── Internal ──────────────────────────────────────────────────────

    def _extract_multimodal_finding(self, event: ToolEvent) -> dict | None:
        """Extract structured finding from a view operation.

        Returns:
            Dict with finding data, or None if no significant finding.
        """
        if not event.function_result:
            return None

        func_result = event.function_result
        if hasattr(func_result, "data"):
            data = func_result.data or {}
            result = (
                func_result.message
                if hasattr(func_result, "message")
                else str(func_result.data)
                if func_result.data
                else ""
            )
        elif hasattr(func_result, "result"):
            result = func_result.result
            data = {}
        else:
            result = str(func_result) if func_result else ""
            data = func_result if isinstance(func_result, dict) else {}

        finding: dict[str, Any] = {
            "tool": event.function_name,
            "timestamp": event.started_at.isoformat() if event.started_at else None,
            "source": event.function_args.get("file") or event.function_args.get("url", ""),
        }

        if event.function_name == ToolName.FILE_VIEW:
            finding["type"] = "file_view"
            finding["file_type"] = data.get("file_type", "unknown") if isinstance(data, dict) else "unknown"
            finding["content_preview"] = result[:500] if result else ""
            if isinstance(data, dict) and data.get("extracted_text"):
                finding["extracted_text"] = data["extracted_text"][:1000]

        elif event.function_name in {ToolName.BROWSER_VIEW, ToolName.BROWSER_GET_CONTENT}:
            finding["type"] = "browser_view"
            finding["url"] = event.function_args.get("url", "")
            finding["content_preview"] = result[:500] if result else ""

        elif event.function_name == ToolName.BROWSER_AGENT_EXTRACT:
            finding["type"] = "extraction"
            finding["extraction_goal"] = event.function_args.get("goal", "")
            finding["result"] = result[:1000] if result else ""

        return finding if finding.get("content_preview") or finding.get("result") else None

    def _persist_key_findings(self) -> None:
        """Persist accumulated multimodal findings to context manager."""
        if not self._multimodal_findings:
            return

        findings_text = self._format_findings_for_context()

        self._context_manager.add_observation(
            observation_type="multimodal_findings",
            content=findings_text,
            importance=0.8,
        )

        self._multimodal_findings = []
        logger.debug("Persisted multimodal findings to context")

    def _format_findings_for_context(self) -> str:
        """Format multimodal findings as a context string."""
        if not self._multimodal_findings:
            return ""

        parts = ["## Key Visual Findings\n"]

        for i, finding in enumerate(self._multimodal_findings, 1):
            finding_type = finding.get("type", "view")
            source = finding.get("source") or finding.get("url", "")

            parts.append(f"### Finding {i}: {finding_type}")
            if source:
                parts.append(f"**Source:** {source}")

            if finding.get("content_preview"):
                parts.append(f"**Preview:** {finding['content_preview'][:300]}...")
            elif finding.get("result"):
                parts.append(f"**Result:** {finding['result'][:300]}...")

            if finding.get("extracted_text"):
                parts.append(f"**Text:** {finding['extracted_text'][:200]}...")

            parts.append("")

        return "\n".join(parts)
