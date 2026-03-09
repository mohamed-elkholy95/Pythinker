"""Clarification gate middleware — surfaces pending questions before each step."""

from __future__ import annotations

from app.domain.models.clarification import ClarificationRequest
from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware


class ClarificationMiddleware(RuntimeMiddleware):
    """Intercepts agent steps to surface any pending clarification question.

    When a ``ClarificationRequest`` is stored under
    ``ctx.metadata["pending_clarification"]``, this middleware:

    1. Marks ``ctx.metadata["awaiting_clarification"] = True`` so downstream
       components know execution should pause.
    2. Appends a structured event dict to ``ctx.events`` with all relevant
       fields plus the pre-formatted question string.
    3. Removes the ``pending_clarification`` key so the request is not
       processed a second time.

    If no pending clarification is present the context is returned unchanged.
    """

    async def before_step(self, ctx: RuntimeContext) -> RuntimeContext:
        pending = ctx.metadata.get("pending_clarification")
        if pending is None:
            return ctx

        request: ClarificationRequest = pending

        ctx.metadata["awaiting_clarification"] = True
        ctx.events.append(
            {
                "type": "clarification",
                "question": request.question,
                "clarification_type": request.clarification_type.value,
                "context": request.context,
                "options": request.options,
                "formatted": request.format(),
            }
        )
        ctx.metadata.pop("pending_clarification")

        return ctx
