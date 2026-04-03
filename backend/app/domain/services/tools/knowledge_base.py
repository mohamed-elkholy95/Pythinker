"""Agent tool for querying user knowledge bases (RAG-Anything backed)."""

import logging
from typing import TYPE_CHECKING, Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool

if TYPE_CHECKING:
    from app.domain.services.knowledge_base_service import KnowledgeBaseService

logger = logging.getLogger(__name__)


class KnowledgeBaseTool(BaseTool):
    """Tool exposing knowledge base query and list operations to the agent."""

    name: str = "knowledge_base"
    supports_progress: bool = True

    def __init__(
        self,
        kb_service: "KnowledgeBaseService",
        user_id: str,
        max_observe: int | None = None,
    ) -> None:
        super().__init__(
            max_observe=max_observe,
            defaults=ToolDefaults(is_read_only=True, is_concurrency_safe=True, category="knowledge_base"),
        )
        self._kb_service = kb_service
        self._user_id = user_id

    @tool(
        name="kb_query",
        description=(
            "Search the user's knowledge base for information from uploaded documents. "
            "Use this when the user asks questions about their documents, files, or "
            "previously indexed content. Returns a synthesized answer with source references."
        ),
        parameters={
            "query": {
                "type": "string",
                "description": "Natural language search query",
            },
            "knowledge_base_id": {
                "type": "string",
                "description": (
                    "Knowledge base ID to search. If omitted, the first available knowledge base is used automatically."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["hybrid", "local", "global", "naive"],
                "description": (
                    "Retrieval mode: 'hybrid' (recommended), 'local' (chunk-level), "
                    "'global' (graph-level), 'naive' (vector-only)."
                ),
            },
        },
        required=["query"],
    )
    async def kb_query(
        self,
        query: str,
        knowledge_base_id: str | None = None,
        mode: str = "hybrid",
        **_: Any,
    ) -> ToolResult:
        try:
            kb_id = await self._resolve_kb_id(knowledge_base_id)
            if kb_id is None:
                return ToolResult.error("No knowledge bases found. Upload documents first to create a knowledge base.")

            result = await self._kb_service.query(
                kb_id=kb_id,
                user_id=self._user_id,
                query=query,
                mode=mode,
            )
            answer = result.answer
            if result.sources:
                sources_str = "\n\nSources:\n" + "\n".join(f"- {s}" for s in result.sources)
                answer += sources_str

            return ToolResult.ok(
                message=answer,
                data={
                    "answer": result.answer,
                    "sources": result.sources,
                    "query_time_ms": result.query_time_ms,
                    "mode": result.mode,
                    "knowledge_base_id": kb_id,
                },
            )
        except Exception as exc:
            logger.warning("kb_query failed: %s", exc)
            return ToolResult.error(f"Knowledge base query failed: {exc}")

    @tool(
        name="kb_list",
        description=("List all knowledge bases available to the current user, including document counts and status."),
        parameters={},
        required=[],
    )
    async def kb_list(self, **_: Any) -> ToolResult:
        try:
            bases = await self._kb_service.list_knowledge_bases(self._user_id)
            if not bases:
                return ToolResult.ok(
                    message="No knowledge bases found. You can create one by uploading documents.",
                    data={"knowledge_bases": []},
                )

            lines = [f"Found {len(bases)} knowledge base(s):\n"]
            for kb in bases:
                lines.append(f"- **{kb.name}** (id={kb.id}, docs={kb.document_count}, status={kb.status.value})")
                if kb.description:
                    lines.append(f"  {kb.description}")

            return ToolResult.ok(
                message="\n".join(lines),
                data={
                    "knowledge_bases": [
                        {
                            "id": kb.id,
                            "name": kb.name,
                            "description": kb.description,
                            "status": kb.status.value,
                            "document_count": kb.document_count,
                        }
                        for kb in bases
                    ]
                },
            )
        except Exception as exc:
            logger.warning("kb_list failed: %s", exc)
            return ToolResult.error(f"Failed to list knowledge bases: {exc}")

    async def _resolve_kb_id(self, kb_id: str | None) -> str | None:
        """Return the provided kb_id, or fall back to the user's first KB."""
        if kb_id:
            return kb_id
        bases = await self._kb_service.list_knowledge_bases(self._user_id)
        return bases[0].id if bases else None
