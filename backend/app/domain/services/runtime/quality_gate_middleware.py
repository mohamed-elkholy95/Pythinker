"""Quality gate middleware — grounding and coverage validators as always-on hooks.

Wires an optional toolset manager, coverage validator, and grounding validator
into the runtime lifecycle so that every agent step is automatically subject to
quality checks without requiring callers to invoke validators explicitly.

All three dependencies are optional; when absent the corresponding logic is
skipped and the context is returned unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware

logger = logging.getLogger(__name__)


class QualityGateMiddleware(RuntimeMiddleware):
    """Runtime middleware that applies quality gates before and after each step.

    ``before_step`` uses the *toolset_manager* to narrow the active tool list
    to those relevant to the current step description.

    ``after_step`` runs up to two validators against the step output:

    - *coverage_validator*: a synchronous validator whose ``.validate()``
      method accepts ``output`` and ``user_request`` keyword arguments and
      returns an object with ``quality_score`` and ``is_valid`` attributes.
    - *grounding_validator*: an async validator whose ``.validate()`` method
      accepts ``output`` and ``source_context`` keyword arguments and returns
      an object with ``overall_score`` and ``is_acceptable`` attributes.

    All external calls are wrapped in ``try/except`` so a failing validator
    never interrupts normal agent execution.
    """

    def __init__(
        self,
        toolset_manager: Any | None = None,
        coverage_validator: Any | None = None,
        grounding_validator: Any | None = None,
    ) -> None:
        self._toolset_manager = toolset_manager
        self._coverage_validator = coverage_validator
        self._grounding_validator = grounding_validator

    # ─────────────────────────── before_step ─────────────────────────────────

    async def before_step(self, ctx: RuntimeContext) -> RuntimeContext:
        """Filter available tools to those relevant to the current step.

        Reads ``ctx.metadata["current_step_description"]`` and calls
        ``toolset_manager.get_tools_for_task(step_desc)``.  The result is
        stored under ``ctx.metadata["filtered_tools"]``.
        """
        if self._toolset_manager is None:
            return ctx

        step_desc: str | None = ctx.metadata.get("current_step_description")
        if not step_desc:
            return ctx

        try:
            filtered = self._toolset_manager.get_tools_for_task(step_desc)
            ctx.metadata["filtered_tools"] = filtered
        except Exception:
            logger.warning(
                "QualityGateMiddleware: toolset_manager.get_tools_for_task failed",
                exc_info=True,
            )

        return ctx

    # ─────────────────────────── after_step ──────────────────────────────────

    async def after_step(self, ctx: RuntimeContext) -> RuntimeContext:
        """Run coverage and grounding validators against the completed step output.

        Reads ``ctx.metadata["step_output"]`` and ``ctx.metadata["user_request"]``
        for the coverage check, and additionally ``ctx.metadata["source_context"]``
        for the grounding check.

        Results are merged back into ``ctx.metadata``:
        - Coverage: ``quality_score``, ``is_valid``
        - Grounding: ``grounding_score``, ``is_grounding_acceptable``
        """
        step_output: Any = ctx.metadata.get("step_output")
        if step_output is None:
            return ctx

        # ── Coverage check ────────────────────────────────────────────────────
        if self._coverage_validator is not None:
            user_request: Any = ctx.metadata.get("user_request", "")
            try:
                coverage_result = self._coverage_validator.validate(
                    output=step_output,
                    user_request=user_request,
                )
                ctx.metadata["quality_score"] = coverage_result.quality_score
                ctx.metadata["is_valid"] = coverage_result.is_valid
            except Exception:
                logger.warning(
                    "QualityGateMiddleware: coverage_validator.validate failed",
                    exc_info=True,
                )

        # ── Grounding check ───────────────────────────────────────────────────
        if self._grounding_validator is not None:
            source_context: Any = ctx.metadata.get("source_context")
            if source_context is not None:
                try:
                    grounding_result = await self._grounding_validator.validate(
                        output=step_output,
                        source_context=source_context,
                    )
                    ctx.metadata["grounding_score"] = grounding_result.overall_score
                    ctx.metadata["is_grounding_acceptable"] = grounding_result.is_acceptable
                except Exception:
                    logger.warning(
                        "QualityGateMiddleware: grounding_validator.validate failed",
                        exc_info=True,
                    )

        return ctx
