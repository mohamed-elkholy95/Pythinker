"""Generate concise, descriptive session titles from user messages via LLM.

This service replaces naive message truncation with smart LLM-generated titles.
It runs as a fire-and-forget background task so it never blocks the response stream.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.external.llm import LLM
    from app.domain.repositories.session_repository import SessionRepository

logger = logging.getLogger(__name__)

_TITLE_SYSTEM_PROMPT = (
    "You are a session title generator. Given a user's message, generate a concise, "
    "descriptive title (max 80 characters) that captures the intent or topic. "
    "Rules:\n"
    "- Use plain language, no quotes or special formatting\n"
    "- Be specific about the task/topic, not generic\n"
    "- Use title case\n"
    "- If the message is a greeting or trivial, return the message as-is\n"
    "- Never exceed 80 characters\n"
    "- Output ONLY the title, nothing else"
)


async def generate_smart_title(
    llm: "LLM",
    session_id: str,
    user_message: str,
    session_repository: "SessionRepository",
) -> None:
    """Generate a smart title for a session and persist it.

    Designed to be called via fire-and-forget (asyncio.create_task).
    All exceptions are caught and logged — never propagates errors.
    """
    if not user_message or not user_message.strip():
        return

    # Short messages don't need LLM summarization
    trimmed = user_message.strip()
    if len(trimmed) <= 50:
        return

    try:
        response = await llm.ask(
            messages=[
                {"role": "system", "content": _TITLE_SYSTEM_PROMPT},
                {"role": "user", "content": trimmed[:500]},  # Cap input to avoid waste
            ],
            max_tokens=60,
            temperature=0.3,
            enable_caching=False,
        )

        title = (response.get("content") or "").strip().strip('"').strip("'")
        if not title or len(title) > 80:
            return

        await session_repository.update_title(session_id, title)
        logger.debug("Smart title generated for session %s: %s", session_id, title)

    except Exception:
        logger.debug("Smart title generation failed for session %s (non-critical)", session_id, exc_info=True)
