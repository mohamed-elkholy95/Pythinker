"""Integration tests for the full runtime pipeline with all middlewares."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.runtime.lead_agent_runtime import (
    LeadAgentRuntime,
    build_runtime_pipeline,
)
from app.domain.services.runtime.middleware import RuntimeContext


@pytest.mark.asyncio
class TestFullPipeline:
    async def test_full_pipeline_middleware_order(self) -> None:
        """Verify middlewares are assembled in the prescribed order."""
        pipeline = build_runtime_pipeline(
            session_id="s-1",
            agent_id="a-1",
            workspace_base="/sessions",
            memory_service=AsyncMock(),
            toolset_manager=MagicMock(),
        )
        names = [type(m).__name__ for m in pipeline._middlewares]

        # Core ordering: Workspace → Capability → Dangling → Quality → Clarification → Insight
        assert names.index("WorkspaceMiddleware") < names.index("CapabilityMiddleware")
        assert names.index("CapabilityMiddleware") < names.index("DanglingToolCallMiddleware")
        assert names.index("DanglingToolCallMiddleware") < names.index("QualityGateMiddleware")
        assert names.index("QualityGateMiddleware") < names.index("ClarificationMiddleware")
        assert names.index("ClarificationMiddleware") < names.index("InsightPromotionMiddleware")

    async def test_full_lifecycle(self) -> None:
        """Run a complete initialize → before_step → after_step → finalize lifecycle."""
        runtime = LeadAgentRuntime(
            session_id="s-1",
            agent_id="a-1",
            workspace_base="/sessions",
        )
        # Initialize — workspace and capability manifest should be populated
        ctx = await runtime.initialize()
        assert ctx.workspace.get("workspace") is not None
        assert "capability_manifest" in ctx.metadata

        # Before step — should not raise
        ctx.metadata["message_history"] = []
        ctx = await runtime.before_step(ctx)

        # After step — should not raise
        ctx = await runtime.after_step(ctx)

        # Finalize
        ctx = await runtime.finalize()
        assert ctx.session_id == "s-1"

    async def test_workspace_contract_flows_to_capability_manifest(self) -> None:
        """Both workspace and capability data should be available after initialize."""
        runtime = LeadAgentRuntime(
            session_id="s-1",
            agent_id="a-1",
            workspace_base="/sessions",
        )
        ctx = await runtime.initialize()
        assert "workspace_contract" in ctx.metadata
        assert "capability_manifest" in ctx.metadata

    async def test_optional_middlewares_excluded_when_none(self) -> None:
        """Without memory_service or skills_root, optional middlewares are absent."""
        pipeline = build_runtime_pipeline(
            session_id="s-1",
            agent_id="a-1",
        )
        names = [type(m).__name__ for m in pipeline._middlewares]
        assert "InsightPromotionMiddleware" not in names
        assert "SkillDiscoveryMiddleware" not in names

    async def test_skill_discovery_inserted_after_capability(self) -> None:
        """SkillDiscoveryMiddleware should be positioned between Capability and Dangling."""
        pipeline = build_runtime_pipeline(
            session_id="s-1",
            agent_id="a-1",
            skills_root="/tmp/skills",
        )
        names = [type(m).__name__ for m in pipeline._middlewares]
        assert "SkillDiscoveryMiddleware" in names
        assert names.index("CapabilityMiddleware") < names.index("SkillDiscoveryMiddleware")
        assert names.index("SkillDiscoveryMiddleware") < names.index("DanglingToolCallMiddleware")
