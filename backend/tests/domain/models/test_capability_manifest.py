"""Tests for CapabilityManifest domain model."""

from app.domain.models.capability_manifest import (
    CapabilityManifest,
    ModelCapabilities,
    SandboxState,
)


class TestModelCapabilities:
    def test_defaults(self) -> None:
        m = ModelCapabilities(name="gpt-4o")
        assert m.supports_vision is False
        assert m.supports_thinking is False
        assert m.max_tokens == 4096


class TestSandboxState:
    def test_defaults(self) -> None:
        s = SandboxState()
        assert s.active is False
        assert s.sandbox_id is None


class TestCapabilityManifest:
    def test_defaults(self) -> None:
        cm = CapabilityManifest(session_id="s-1")
        assert cm.active_skills == []
        assert cm.mcp_servers == []
        assert cm.tool_categories == set()
        assert cm.max_concurrent_delegates == 3
        assert cm.model.name == "default"
        assert cm.sandbox.active is False

    def test_to_prompt_block_minimal(self) -> None:
        cm = CapabilityManifest(session_id="s-1")
        block = cm.to_prompt_block()
        assert "<capability_manifest>" in block
        assert "s-1" in block

    def test_to_prompt_block_with_skills(self) -> None:
        cm = CapabilityManifest(
            session_id="s-1",
            active_skills=["seo", "deal_finder"],
        )
        block = cm.to_prompt_block()
        assert "seo" in block
        assert "deal_finder" in block

    def test_to_prompt_block_with_tools(self) -> None:
        cm = CapabilityManifest(
            session_id="s-1",
            tool_categories={"browser", "file", "shell"},
        )
        block = cm.to_prompt_block()
        assert "browser" in block

    def test_to_prompt_block_sandbox(self) -> None:
        cm = CapabilityManifest(
            session_id="s-1",
            sandbox=SandboxState(active=True, sandbox_id="box-1"),
        )
        block = cm.to_prompt_block()
        assert "sandbox" in block.lower()

    def test_full_manifest(self) -> None:
        cm = CapabilityManifest(
            session_id="s-1",
            active_skills=["research"],
            mcp_servers=["mcp-1"],
            tool_categories={"browser"},
            model=ModelCapabilities(name="claude-3-5-sonnet", supports_vision=True, max_tokens=8192),
            sandbox=SandboxState(active=True),
            max_concurrent_delegates=5,
        )
        assert cm.model.supports_vision is True
        assert cm.max_concurrent_delegates == 5
        block = cm.to_prompt_block()
        assert "claude-3-5-sonnet" in block
