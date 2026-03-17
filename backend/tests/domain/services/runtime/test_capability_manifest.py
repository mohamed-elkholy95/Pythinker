"""Tests for CapabilityManifest model and CapabilityMiddleware."""

from __future__ import annotations

import pytest

from app.domain.models.capability_manifest import (
    CapabilityManifest,
    ModelCapabilities,
    SandboxState,
)
from app.domain.services.runtime.capability_middleware import CapabilityMiddleware
from app.domain.services.runtime.middleware import RuntimeContext

# ─────────────────────────── test_manifest_serializes ────────────────────────


@pytest.mark.asyncio
async def test_manifest_serializes() -> None:
    """CapabilityManifest survives a model_dump round-trip with all fields intact."""
    manifest = CapabilityManifest(
        session_id="sess-001",
        active_skills=["research", "coding"],
        mcp_servers=["filesystem", "github"],
        tool_categories={"browser", "file", "shell"},
        model=ModelCapabilities(
            name="gpt-4o",
            supports_vision=True,
            supports_thinking=False,
            max_tokens=8192,
        ),
        sandbox=SandboxState(active=True, sandbox_id="sandbox-abc"),
        max_concurrent_delegates=5,
    )

    dumped = manifest.model_dump()

    assert dumped["session_id"] == "sess-001"
    assert dumped["active_skills"] == ["research", "coding"]
    assert dumped["mcp_servers"] == ["filesystem", "github"]
    assert dumped["tool_categories"] == {"browser", "file", "shell"}
    assert dumped["model"]["name"] == "gpt-4o"
    assert dumped["model"]["supports_vision"] is True
    assert dumped["model"]["supports_thinking"] is False
    assert dumped["model"]["max_tokens"] == 8192
    assert dumped["sandbox"]["active"] is True
    assert dumped["sandbox"]["sandbox_id"] == "sandbox-abc"
    assert dumped["max_concurrent_delegates"] == 5


# ─────────────────────────── test_manifest_to_prompt_block ───────────────────


@pytest.mark.asyncio
async def test_manifest_to_prompt_block() -> None:
    """to_prompt_block returns an XML block containing all expected fields."""
    manifest = CapabilityManifest(
        session_id="sess-xml",
        active_skills=["research"],
        mcp_servers=["filesystem"],
        tool_categories={"browser"},
        model=ModelCapabilities(
            name="claude-3-5-sonnet",
            supports_vision=True,
            supports_thinking=True,
            max_tokens=4096,
        ),
        sandbox=SandboxState(active=True, sandbox_id="sbx-42"),
        max_concurrent_delegates=3,
    )

    block = manifest.to_prompt_block()

    assert "<capability_manifest>" in block
    assert "</capability_manifest>" in block
    assert "<session_id>sess-xml</session_id>" in block
    assert "research" in block
    assert "filesystem" in block
    assert "browser" in block
    assert 'name="claude-3-5-sonnet"' in block
    assert 'supports_vision="true"' in block
    assert 'supports_thinking="true"' in block
    assert 'max_tokens="4096"' in block
    assert 'active="true"' in block
    assert 'sandbox_id="sbx-42"' in block
    assert "<max_concurrent_delegates>3</max_concurrent_delegates>" in block


# ─────────────────────────── test_middleware_populates_manifest ───────────────


@pytest.mark.asyncio
async def test_middleware_populates_manifest() -> None:
    """CapabilityMiddleware.before_run stores a CapabilityManifest on ctx.metadata."""
    middleware = CapabilityMiddleware(
        active_skills=["coding"],
        mcp_servers=["github"],
        tool_categories={"shell"},
        model_name="kimi-for-coding",
        supports_vision=False,
        supports_thinking=False,
        max_tokens=2048,
        sandbox_active=True,
        sandbox_id="sbx-session-99",
        max_concurrent_delegates=2,
    )

    ctx = RuntimeContext(session_id="sess-mw-99", agent_id="agent-1")
    result = await middleware.before_run(ctx)

    assert "capability_manifest" in result.metadata
    manifest = result.metadata["capability_manifest"]
    assert isinstance(manifest, CapabilityManifest)
    assert manifest.session_id == "sess-mw-99"
    assert manifest.active_skills == ["coding"]
    assert manifest.mcp_servers == ["github"]
    assert manifest.tool_categories == {"shell"}
    assert manifest.model.name == "kimi-for-coding"
    assert manifest.model.max_tokens == 2048
    assert manifest.sandbox.active is True
    assert manifest.sandbox.sandbox_id == "sbx-session-99"
    assert manifest.max_concurrent_delegates == 2


@pytest.mark.asyncio
async def test_manifest_to_prompt_block_escapes_xml_special_characters() -> None:
    manifest = CapabilityManifest(
        session_id='sess<&>"',
        active_skills=["research&review", 'quote"check'],
        mcp_servers=["files<system>"],
        tool_categories={"browser&shell"},
        model=ModelCapabilities(
            name='gpt<&>"',
            supports_vision=True,
            supports_thinking=True,
            max_tokens=2048,
        ),
        sandbox=SandboxState(active=True, sandbox_id='sbx<&>"'),
        max_concurrent_delegates=2,
    )

    block = manifest.to_prompt_block()

    assert "<session_id>sess&lt;&amp;&gt;&quot;</session_id>" in block
    assert "<active_skills>research&amp;review, quote&quot;check</active_skills>" in block
    assert "<mcp_servers>files&lt;system&gt;</mcp_servers>" in block
    assert "<tool_categories>browser&amp;shell</tool_categories>" in block
    assert 'name="gpt&lt;&amp;&gt;&quot;"' in block
    assert 'sandbox_id="sbx&lt;&amp;&gt;&quot;"' in block
