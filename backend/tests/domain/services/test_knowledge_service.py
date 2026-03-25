"""Tests for KnowledgeService."""

from __future__ import annotations

import pytest

from app.domain.models.event import KnowledgeEvent
from app.domain.services.knowledge import KnowledgeService


class TestKnowledgeServiceGetRelevantKnowledge:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self) -> None:
        service = KnowledgeService()
        result = await service.get_relevant_knowledge("any task description")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_list_type(self) -> None:
        service = KnowledgeService()
        result = await service.get_relevant_knowledge("search the web for AI news")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_task_description_returns_empty_list(self) -> None:
        service = KnowledgeService()
        result = await service.get_relevant_knowledge("")
        assert result == []


class TestKnowledgeServiceAddKnowledge:
    @pytest.mark.asyncio
    async def test_returns_knowledge_event(self) -> None:
        service = KnowledgeService()
        result = await service.add_knowledge(scope="testing", content="always write tests")
        assert isinstance(result, KnowledgeEvent)

    @pytest.mark.asyncio
    async def test_event_has_correct_scope(self) -> None:
        service = KnowledgeService()
        result = await service.add_knowledge(scope="python", content="use type hints")
        assert result.scope == "python"

    @pytest.mark.asyncio
    async def test_event_has_correct_content(self) -> None:
        service = KnowledgeService()
        result = await service.add_knowledge(scope="python", content="use type hints")
        assert result.content == "use type hints"

    @pytest.mark.asyncio
    async def test_event_type_is_knowledge(self) -> None:
        service = KnowledgeService()
        result = await service.add_knowledge(scope="domain", content="some knowledge")
        assert result.type == "knowledge"

    @pytest.mark.asyncio
    async def test_event_has_id_field(self) -> None:
        service = KnowledgeService()
        result = await service.add_knowledge(scope="scope1", content="content1")
        assert result.id is not None
        assert len(result.id) > 0
