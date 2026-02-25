"""Tool capability descriptors for the tool registry.

Each tool in the system has a ``ToolCapability`` that describes its operational
characteristics: risk level, parallelization safety, phase restrictions, and
concurrency limits.  Used by ``DynamicToolsetManager`` and the tool registry
for informed scheduling and filtering.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.domain.models.tool_name import ToolName


class RiskLevel(str, Enum):
    """Operational risk classification for tool execution."""

    SAFE = "safe"  # Read-only, no side effects
    LOW = "low"  # Minor side effects (e.g., file write to sandbox)
    MEDIUM = "medium"  # Moderate side effects (e.g., shell exec, browser action)
    HIGH = "high"  # Significant side effects (e.g., file delete, process kill)
    CRITICAL = "critical"  # Requires confirmation (e.g., payment, destructive ops)


class ToolCapability(BaseModel):
    """Describes the operational characteristics of a single tool.

    Attributes:
        name: Canonical tool identifier from the ToolName enum.
        parallelizable: Whether the tool can execute concurrently with others.
        risk_level: Operational risk classification.
        phase_restrictions: Phases in which this tool is available.
            Empty list means available in all phases.
        max_concurrent: Maximum concurrent invocations of this specific tool.
        cacheable: Whether results can be cached.
        cache_ttl_seconds: Cache TTL when cacheable (0 = no caching).
        network_dependent: Whether the tool requires network access.
        idempotent: Whether repeated calls produce the same result.
    """

    name: ToolName
    parallelizable: bool = False
    risk_level: RiskLevel = RiskLevel.SAFE
    phase_restrictions: list[str] = Field(default_factory=list)
    max_concurrent: int = 1
    cacheable: bool = False
    cache_ttl_seconds: int = 0
    network_dependent: bool = False
    idempotent: bool = False

    model_config = {"frozen": True}


# ─────────────────────────────────────────────────────────────────────
# Pre-built capability registry for all known tools
# ─────────────────────────────────────────────────────────────────────

TOOL_CAPABILITIES: dict[ToolName, ToolCapability] = {
    # ── File operations ─────────────────────────────────────────────
    ToolName.FILE_READ: ToolCapability(
        name=ToolName.FILE_READ,
        parallelizable=True,
        risk_level=RiskLevel.SAFE,
        cacheable=True,
        cache_ttl_seconds=300,
        idempotent=True,
    ),
    ToolName.FILE_WRITE: ToolCapability(
        name=ToolName.FILE_WRITE,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.FILE_STR_REPLACE: ToolCapability(
        name=ToolName.FILE_STR_REPLACE,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.FILE_SEARCH: ToolCapability(
        name=ToolName.FILE_SEARCH,
        parallelizable=True,
        risk_level=RiskLevel.SAFE,
        cacheable=True,
        cache_ttl_seconds=300,
        idempotent=True,
    ),
    ToolName.FILE_FIND: ToolCapability(
        name=ToolName.FILE_FIND,
        risk_level=RiskLevel.SAFE,
        cacheable=True,
        cache_ttl_seconds=300,
        idempotent=True,
    ),
    ToolName.FILE_FIND_BY_NAME: ToolCapability(
        name=ToolName.FILE_FIND_BY_NAME,
        risk_level=RiskLevel.SAFE,
        cacheable=True,
        cache_ttl_seconds=300,
        idempotent=True,
    ),
    ToolName.FILE_FIND_IN_CONTENT: ToolCapability(
        name=ToolName.FILE_FIND_IN_CONTENT,
        risk_level=RiskLevel.SAFE,
        cacheable=True,
        cache_ttl_seconds=300,
        idempotent=True,
    ),
    ToolName.FILE_LIST: ToolCapability(
        name=ToolName.FILE_LIST,
        risk_level=RiskLevel.SAFE,
        cacheable=True,
        cache_ttl_seconds=300,
        idempotent=True,
    ),
    ToolName.FILE_LIST_DIRECTORY: ToolCapability(
        name=ToolName.FILE_LIST_DIRECTORY,
        parallelizable=True,
        risk_level=RiskLevel.SAFE,
        cacheable=True,
        cache_ttl_seconds=300,
        idempotent=True,
    ),
    ToolName.FILE_VIEW: ToolCapability(
        name=ToolName.FILE_VIEW,
        risk_level=RiskLevel.SAFE,
        cacheable=True,
        cache_ttl_seconds=300,
        idempotent=True,
    ),
    ToolName.FILE_CREATE: ToolCapability(
        name=ToolName.FILE_CREATE,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.FILE_DELETE: ToolCapability(
        name=ToolName.FILE_DELETE,
        risk_level=RiskLevel.HIGH,
    ),
    ToolName.FILE_RENAME: ToolCapability(
        name=ToolName.FILE_RENAME,
        risk_level=RiskLevel.MEDIUM,
    ),
    ToolName.FILE_MOVE: ToolCapability(
        name=ToolName.FILE_MOVE,
        risk_level=RiskLevel.MEDIUM,
    ),
    # ── Shell operations ────────────────────────────────────────────
    ToolName.SHELL_EXEC: ToolCapability(
        name=ToolName.SHELL_EXEC,
        risk_level=RiskLevel.MEDIUM,
        max_concurrent=2,
    ),
    ToolName.SHELL_VIEW: ToolCapability(
        name=ToolName.SHELL_VIEW,
        risk_level=RiskLevel.SAFE,
        idempotent=True,
    ),
    ToolName.SHELL_WAIT: ToolCapability(
        name=ToolName.SHELL_WAIT,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.SHELL_WRITE_TO_PROCESS: ToolCapability(
        name=ToolName.SHELL_WRITE_TO_PROCESS,
        risk_level=RiskLevel.MEDIUM,
    ),
    ToolName.SHELL_KILL_PROCESS: ToolCapability(
        name=ToolName.SHELL_KILL_PROCESS,
        risk_level=RiskLevel.HIGH,
    ),
    # ── Browser operations ──────────────────────────────────────────
    ToolName.SEARCH: ToolCapability(
        name=ToolName.SEARCH,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        cacheable=True,
        cache_ttl_seconds=1800,
    ),
    ToolName.BROWSER_VIEW: ToolCapability(
        name=ToolName.BROWSER_VIEW,
        parallelizable=True,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        idempotent=True,
    ),
    ToolName.BROWSER_NAVIGATE: ToolCapability(
        name=ToolName.BROWSER_NAVIGATE,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
    ),
    ToolName.BROWSER_GET_CONTENT: ToolCapability(
        name=ToolName.BROWSER_GET_CONTENT,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        cacheable=True,
        cache_ttl_seconds=600,
    ),
    ToolName.BROWSER_RESTART: ToolCapability(
        name=ToolName.BROWSER_RESTART,
        risk_level=RiskLevel.MEDIUM,
    ),
    ToolName.BROWSER_CLICK: ToolCapability(
        name=ToolName.BROWSER_CLICK,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.BROWSER_INPUT: ToolCapability(
        name=ToolName.BROWSER_INPUT,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.BROWSER_MOVE_MOUSE: ToolCapability(
        name=ToolName.BROWSER_MOVE_MOUSE,
        risk_level=RiskLevel.SAFE,
    ),
    ToolName.BROWSER_PRESS_KEY: ToolCapability(
        name=ToolName.BROWSER_PRESS_KEY,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.BROWSER_SELECT_OPTION: ToolCapability(
        name=ToolName.BROWSER_SELECT_OPTION,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.BROWSER_SCROLL_UP: ToolCapability(
        name=ToolName.BROWSER_SCROLL_UP,
        risk_level=RiskLevel.SAFE,
    ),
    ToolName.BROWSER_SCROLL_DOWN: ToolCapability(
        name=ToolName.BROWSER_SCROLL_DOWN,
        risk_level=RiskLevel.SAFE,
    ),
    ToolName.BROWSER_CONSOLE_EXEC: ToolCapability(
        name=ToolName.BROWSER_CONSOLE_EXEC,
        risk_level=RiskLevel.MEDIUM,
    ),
    ToolName.BROWSER_CONSOLE_VIEW: ToolCapability(
        name=ToolName.BROWSER_CONSOLE_VIEW,
        risk_level=RiskLevel.SAFE,
        idempotent=True,
    ),
    ToolName.BROWSER_SCREENSHOT: ToolCapability(
        name=ToolName.BROWSER_SCREENSHOT,
        risk_level=RiskLevel.SAFE,
        idempotent=True,
    ),
    # ── Browser agent ───────────────────────────────────────────────
    ToolName.BROWSER_AGENT_RUN: ToolCapability(
        name=ToolName.BROWSER_AGENT_RUN,
        risk_level=RiskLevel.MEDIUM,
        network_dependent=True,
    ),
    ToolName.BROWSER_AGENT_EXTRACT: ToolCapability(
        name=ToolName.BROWSER_AGENT_EXTRACT,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        cacheable=True,
        cache_ttl_seconds=600,
    ),
    # ── Search operations ───────────────────────────────────────────
    ToolName.INFO_SEARCH_WEB: ToolCapability(
        name=ToolName.INFO_SEARCH_WEB,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        cacheable=True,
        cache_ttl_seconds=1800,
    ),
    ToolName.WEB_SEARCH: ToolCapability(
        name=ToolName.WEB_SEARCH,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        cacheable=True,
        cache_ttl_seconds=1800,
    ),
    ToolName.WIDE_RESEARCH: ToolCapability(
        name=ToolName.WIDE_RESEARCH,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        cacheable=True,
        cache_ttl_seconds=1800,
    ),
    # ── Code executor ───────────────────────────────────────────────
    ToolName.CODE_EXECUTE: ToolCapability(
        name=ToolName.CODE_EXECUTE,
        risk_level=RiskLevel.MEDIUM,
    ),
    ToolName.CODE_EXECUTE_PYTHON: ToolCapability(
        name=ToolName.CODE_EXECUTE_PYTHON,
        risk_level=RiskLevel.MEDIUM,
    ),
    ToolName.CODE_EXECUTE_JAVASCRIPT: ToolCapability(
        name=ToolName.CODE_EXECUTE_JAVASCRIPT,
        risk_level=RiskLevel.MEDIUM,
    ),
    ToolName.CODE_LIST_ARTIFACTS: ToolCapability(
        name=ToolName.CODE_LIST_ARTIFACTS,
        parallelizable=True,
        risk_level=RiskLevel.SAFE,
        idempotent=True,
    ),
    ToolName.CODE_READ_ARTIFACT: ToolCapability(
        name=ToolName.CODE_READ_ARTIFACT,
        parallelizable=True,
        risk_level=RiskLevel.SAFE,
        idempotent=True,
    ),
    ToolName.CODE_CLEANUP_WORKSPACE: ToolCapability(
        name=ToolName.CODE_CLEANUP_WORKSPACE,
        risk_level=RiskLevel.HIGH,
    ),
    ToolName.CODE_SAVE_ARTIFACT: ToolCapability(
        name=ToolName.CODE_SAVE_ARTIFACT,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.CODE_CREATE_ARTIFACT: ToolCapability(
        name=ToolName.CODE_CREATE_ARTIFACT,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.CODE_UPDATE_ARTIFACT: ToolCapability(
        name=ToolName.CODE_UPDATE_ARTIFACT,
        risk_level=RiskLevel.LOW,
    ),
    # ── Code dev ────────────────────────────────────────────────────
    ToolName.CODE_FORMAT: ToolCapability(
        name=ToolName.CODE_FORMAT,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.CODE_LINT: ToolCapability(
        name=ToolName.CODE_LINT,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.CODE_ANALYZE: ToolCapability(
        name=ToolName.CODE_ANALYZE,
        risk_level=RiskLevel.SAFE,
        idempotent=True,
    ),
    ToolName.CODE_SEARCH: ToolCapability(
        name=ToolName.CODE_SEARCH,
        risk_level=RiskLevel.SAFE,
        idempotent=True,
    ),
    # ── Workspace ───────────────────────────────────────────────────
    ToolName.WORKSPACE_INFO: ToolCapability(
        name=ToolName.WORKSPACE_INFO,
        risk_level=RiskLevel.SAFE,
        idempotent=True,
    ),
    ToolName.WORKSPACE_TREE: ToolCapability(
        name=ToolName.WORKSPACE_TREE,
        risk_level=RiskLevel.SAFE,
        idempotent=True,
    ),
    # ── Message ─────────────────────────────────────────────────────
    ToolName.MESSAGE_ASK_USER: ToolCapability(
        name=ToolName.MESSAGE_ASK_USER,
        risk_level=RiskLevel.LOW,
    ),
    ToolName.MESSAGE_NOTIFY_USER: ToolCapability(
        name=ToolName.MESSAGE_NOTIFY_USER,
        risk_level=RiskLevel.LOW,
    ),
    # ── MCP ─────────────────────────────────────────────────────────
    ToolName.MCP_LIST_RESOURCES: ToolCapability(
        name=ToolName.MCP_LIST_RESOURCES,
        parallelizable=True,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        idempotent=True,
    ),
    ToolName.MCP_READ_RESOURCE: ToolCapability(
        name=ToolName.MCP_READ_RESOURCE,
        parallelizable=True,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        idempotent=True,
    ),
    ToolName.MCP_SERVER_STATUS: ToolCapability(
        name=ToolName.MCP_SERVER_STATUS,
        parallelizable=True,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        idempotent=True,
    ),
    ToolName.MCP_CALL_TOOL: ToolCapability(
        name=ToolName.MCP_CALL_TOOL,
        risk_level=RiskLevel.MEDIUM,
        network_dependent=True,
    ),
    # ── Test ────────────────────────────────────────────────────────
    ToolName.TEST_RUN: ToolCapability(
        name=ToolName.TEST_RUN,
        risk_level=RiskLevel.SAFE,
        phase_restrictions=["verifying"],
    ),
    ToolName.TEST_LIST: ToolCapability(
        name=ToolName.TEST_LIST,
        risk_level=RiskLevel.SAFE,
        phase_restrictions=["verifying"],
        idempotent=True,
    ),
    # ── Export ──────────────────────────────────────────────────────
    ToolName.EXPORT: ToolCapability(
        name=ToolName.EXPORT,
        risk_level=RiskLevel.LOW,
    ),
    # ── Scraping ────────────────────────────────────────────────────
    ToolName.SCRAPE_STRUCTURED: ToolCapability(
        name=ToolName.SCRAPE_STRUCTURED,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        cacheable=True,
        cache_ttl_seconds=1800,
    ),
    ToolName.SCRAPE_BATCH: ToolCapability(
        name=ToolName.SCRAPE_BATCH,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
        cacheable=True,
        cache_ttl_seconds=1800,
    ),
    ToolName.ADAPTIVE_SCRAPE: ToolCapability(
        name=ToolName.ADAPTIVE_SCRAPE,
        risk_level=RiskLevel.SAFE,
        network_dependent=True,
    ),
}


def get_capability(tool_name: ToolName | str) -> ToolCapability | None:
    """Look up the capability descriptor for a tool.

    Returns ``None`` for unknown tools (e.g. dynamic MCP tools not in the
    static registry).
    """
    if isinstance(tool_name, str):
        try:
            tool_name = ToolName(tool_name)
        except ValueError:
            return None
    return TOOL_CAPABILITIES.get(tool_name)
