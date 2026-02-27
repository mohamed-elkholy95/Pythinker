"""Canonical tool name registry — single source of truth for all 107 tool identifiers.

Replaces magic strings scattered across base.py, execution.py, dynamic_toolset.py,
and tool_efficiency_monitor.py with a type-safe enum. Every tool name used in the
system MUST be defined here.

Usage:
    from app.domain.models.tool_name import ToolName

    if tool_name == ToolName.FILE_READ:
        ...

    # Classification queries
    ToolName.FILE_READ.is_read_only   # True
    ToolName.SHELL_EXEC.is_action     # True
    ToolName.is_safe_parallel(ToolName.FILE_READ)  # True
    ToolName.for_phase("planning")    # frozenset of ToolNames
"""

from __future__ import annotations

from enum import Enum
from typing import ClassVar


class ToolName(str, Enum):
    """Exhaustive enumeration of every tool in the Pythinker agent toolset.

    Inherits from ``str`` so the enum value can be compared directly with raw
    strings for backward compatibility (``ToolName.FILE_READ == "file_read"``).
    """

    # ── File operations (6 actual tools) ────────────────────────────
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_STR_REPLACE = "file_str_replace"
    FILE_FIND_BY_NAME = "file_find_by_name"
    FILE_FIND_IN_CONTENT = "file_find_in_content"
    FILE_VIEW = "file_view"

    # ── Shell operations (5 tools) ──────────────────────────────────
    SHELL_EXEC = "shell_exec"
    SHELL_VIEW = "shell_view"
    SHELL_WAIT = "shell_wait"
    SHELL_WRITE_TO_PROCESS = "shell_write_to_process"
    SHELL_KILL_PROCESS = "shell_kill_process"

    # ── Browser operations (1 tool — BrowserTool) ───────────────────
    SEARCH = "search"

    # ── Browser agent operations (2 tools) ──────────────────────────
    BROWSER_AGENT_RUN = "browser_agent_run"
    BROWSER_AGENT_EXTRACT = "browser_agent_extract"

    # ── Playwright operations (21 tools) ────────────────────────────
    PLAYWRIGHT_LAUNCH = "playwright_launch"
    PLAYWRIGHT_NAVIGATE = "playwright_navigate"
    PLAYWRIGHT_FILL = "playwright_fill"
    PLAYWRIGHT_TYPE = "playwright_type"
    PLAYWRIGHT_SELECT_OPTION = "playwright_select_option"
    PLAYWRIGHT_PRESS_KEY = "playwright_press_key"
    PLAYWRIGHT_EVALUATE = "playwright_evaluate"
    PLAYWRIGHT_GET_CONTENT = "playwright_get_content"
    PLAYWRIGHT_SCREENSHOT = "playwright_screenshot"
    PLAYWRIGHT_PDF = "playwright_pdf"
    PLAYWRIGHT_GET_COOKIES = "playwright_get_cookies"
    PLAYWRIGHT_SET_COOKIES = "playwright_set_cookies"
    PLAYWRIGHT_WAIT_FOR_SELECTOR = "playwright_wait_for_selector"
    PLAYWRIGHT_INTERCEPT_REQUESTS = "playwright_intercept_requests"
    PLAYWRIGHT_DETECT_PROTECTION = "playwright_detect_protection"
    PLAYWRIGHT_CLOUDFLARE_BYPASS = "playwright_cloudflare_bypass"
    PLAYWRIGHT_LOGIN_WITH_2FA = "playwright_login_with_2fa"
    PLAYWRIGHT_FILL_2FA_CODE = "playwright_fill_2fa_code"
    PLAYWRIGHT_SOLVE_RECAPTCHA = "playwright_solve_recaptcha"
    PLAYWRIGHT_STEALTH_NAVIGATE = "playwright_stealth_navigate"

    # ── Search operations (2 tools) ─────────────────────────────────
    INFO_SEARCH_WEB = "info_search_web"
    WIDE_RESEARCH = "wide_research"

    # ── Code executor operations (7 tools) ──────────────────────────
    CODE_EXECUTE = "code_execute"
    CODE_EXECUTE_PYTHON = "code_execute_python"
    CODE_EXECUTE_JAVASCRIPT = "code_execute_javascript"
    CODE_LIST_ARTIFACTS = "code_list_artifacts"
    CODE_READ_ARTIFACT = "code_read_artifact"
    CODE_CLEANUP_WORKSPACE = "code_cleanup_workspace"
    CODE_SAVE_ARTIFACT = "code_save_artifact"

    # ── Code dev operations (4 tools) ───────────────────────────────
    CODE_FORMAT = "code_format"
    CODE_LINT = "code_lint"
    CODE_ANALYZE = "code_analyze"
    CODE_SEARCH = "code_search"

    # ── Workspace operations (5 tools) ──────────────────────────────
    WORKSPACE_INIT = "workspace_init"
    WORKSPACE_INFO = "workspace_info"
    WORKSPACE_TREE = "workspace_tree"
    WORKSPACE_CLEAN = "workspace_clean"
    WORKSPACE_EXISTS = "workspace_exists"

    # ── Message operations (2 tools) ────────────────────────────────
    MESSAGE_ASK_USER = "message_ask_user"
    MESSAGE_NOTIFY_USER = "message_notify_user"

    # ── MCP operations (3 tools) ────────────────────────────────────
    MCP_HEALTH_CHECK = "mcp_health_check"
    MCP_RESOURCES = "mcp_resources"
    MCP_TOOL_SCHEMAS = "mcp_tool_schemas"

    # ── Test operations (3 tools) ───────────────────────────────────
    TEST_RUN = "test_run"
    TEST_LIST = "test_list"
    TEST_COVERAGE = "test_coverage"

    # ── Export operations (4 tools) ──────────────────────────────────
    EXPORT_ORGANIZE = "export_organize"
    EXPORT_ARCHIVE = "export_archive"
    EXPORT_REPORT = "export_report"
    EXPORT_LIST = "export_list"

    # ── Scraping operations (3 tools) ───────────────────────────────
    SCRAPE_STRUCTURED = "scrape_structured"
    SCRAPE_BATCH = "scrape_batch"
    ADAPTIVE_SCRAPE = "adaptive_scrape"

    # ── Canvas operations (8 tools) ─────────────────────────────────
    CANVAS_CREATE_PROJECT = "canvas_create_project"
    CANVAS_GET_STATE = "canvas_get_state"
    CANVAS_ADD_ELEMENT = "canvas_add_element"
    CANVAS_MODIFY_ELEMENT = "canvas_modify_element"
    CANVAS_DELETE_ELEMENTS = "canvas_delete_elements"
    CANVAS_ARRANGE_LAYER = "canvas_arrange_layer"
    CANVAS_EXPORT = "canvas_export"
    CANVAS_GENERATE_IMAGE = "canvas_generate_image"

    # ── Git operations (5 tools) ────────────────────────────────────
    GIT_CLONE = "git_clone"
    GIT_STATUS = "git_status"
    GIT_LOG = "git_log"
    GIT_DIFF = "git_diff"
    GIT_BRANCHES = "git_branches"

    # ── Slides operations (3 tools) ─────────────────────────────────
    SLIDES_CREATE = "slides_create"
    SLIDES_ADD_CHART = "slides_add_chart"
    SLIDES_EXPORT = "slides_export"

    # ── Chart operations (1 tool) ───────────────────────────────────
    CHART_CREATE = "chart_create"

    # ── Deep scan operations (5 tools) ──────────────────────────────
    DEEP_SCAN_PROJECT = "deep_scan_project"
    DEEP_SCAN_CODE = "deep_scan_code"
    DEEP_SCAN_DEPENDENCIES = "deep_scan_dependencies"
    DEEP_SCAN_SECURITY = "deep_scan_security"
    DEEP_SCAN_QUALITY = "deep_scan_quality"

    # ── Knowledge base operations (2 tools) ─────────────────────────
    KB_QUERY = "kb_query"
    KB_LIST = "kb_list"

    # ── Skill operations (3 tools) ──────────────────────────────────
    SKILL_CREATE = "skill_create"
    SKILL_LIST_USER = "skill_list_user"
    SKILL_DELETE = "skill_delete"

    # ── Scheduling operations (4 tools) ─────────────────────────────
    AGENT_SCHEDULE_TASK = "agent_schedule_task"
    AGENT_LIST_SCHEDULED_TASKS = "agent_list_scheduled_tasks"
    AGENT_CANCEL_SCHEDULED_TASK = "agent_cancel_scheduled_task"
    AGENT_START_TASK = "agent_start_task"

    # ── Utility operations (1 tool) ─────────────────────────────────
    IDLE = "idle"

    # ── Legacy aliases (referenced in base.py phase groups) ─────────
    # These are kept for backward compat with string comparisons in
    # PHASE_TOOL_GROUPS / SAFE_PARALLEL_TOOLS that reference names not
    # registered as @tool decorators but used as filter keys.
    FILE_SEARCH = "file_search"
    FILE_FIND = "file_find"
    FILE_LIST = "file_list"
    FILE_LIST_DIRECTORY = "file_list_directory"
    BROWSER_VIEW = "browser_view"
    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_GET_CONTENT = "browser_get_content"
    BROWSER_SCREENSHOT = "browser_screenshot"
    BROWSER_CLICK = "browser_click"
    BROWSER_INPUT = "browser_input"
    BROWSER_MOVE_MOUSE = "browser_move_mouse"
    BROWSER_PRESS_KEY = "browser_press_key"
    BROWSER_SELECT_OPTION = "browser_select_option"
    BROWSER_SCROLL_UP = "browser_scroll_up"
    BROWSER_SCROLL_DOWN = "browser_scroll_down"
    BROWSER_CONSOLE_EXEC = "browser_console_exec"
    BROWSER_CONSOLE_VIEW = "browser_console_view"
    BROWSER_RESTART = "browser_restart"
    WEB_SEARCH = "web_search"
    MCP_LIST_RESOURCES = "mcp_list_resources"
    MCP_READ_RESOURCE = "mcp_read_resource"
    MCP_SERVER_STATUS = "mcp_server_status"
    MCP_CALL_TOOL = "mcp_call_tool"
    FILE_CREATE = "file_create"
    FILE_DELETE = "file_delete"
    FILE_RENAME = "file_rename"
    FILE_MOVE = "file_move"
    CODE_CREATE_ARTIFACT = "code_create_artifact"
    CODE_UPDATE_ARTIFACT = "code_update_artifact"
    EXPORT = "export"

    # ─────────────────────────────────────────────────────────────────
    # Classification sets (ClassVar — not enum members)
    # ─────────────────────────────────────────────────────────────────

    _READ_ONLY: ClassVar[frozenset[ToolName]]
    _ACTION: ClassVar[frozenset[ToolName]]
    _SAFE_PARALLEL: ClassVar[frozenset[ToolName]]
    _SEARCH: ClassVar[frozenset[ToolName]]
    _NETWORK: ClassVar[frozenset[ToolName]]
    _VIEW: ClassVar[frozenset[ToolName]]
    _PHASE_PLANNING: ClassVar[frozenset[ToolName]]
    _PHASE_VERIFYING: ClassVar[frozenset[ToolName]]

    # MCP prefix patterns for dynamic tools
    _SAFE_MCP_PREFIXES: ClassVar[tuple[str, ...]]
    _ACTION_MCP_PREFIXES: ClassVar[tuple[str, ...]]

    # ── Instance properties ─────────────────────────────────────────

    @property
    def is_read_only(self) -> bool:
        """Tool performs no side effects (reads, views, searches)."""
        return self in self._READ_ONLY

    @property
    def is_action(self) -> bool:
        """Tool performs side effects (writes, executions, user interaction)."""
        return self in self._ACTION

    @property
    def is_safe_parallel(self) -> bool:
        """Tool can safely execute in parallel with others."""
        return self in self._SAFE_PARALLEL

    @property
    def is_search(self) -> bool:
        """Tool performs web or content search."""
        return self in self._SEARCH

    @property
    def is_network(self) -> bool:
        """Tool requires network access (for retry logic)."""
        return self in self._NETWORK

    @property
    def is_view(self) -> bool:
        """Tool produces viewable/multimodal content."""
        return self in self._VIEW

    # ── Class methods ───────────────────────────────────────────────

    @classmethod
    def for_phase(cls, phase: str) -> frozenset[ToolName] | None:
        """Return the set of tools allowed in a given execution phase.

        Returns ``None`` for phases where all tools are available (e.g. 'executing').
        """
        phase_map: dict[str, frozenset[ToolName] | None] = {
            "planning": cls._PHASE_PLANNING,
            "executing": None,  # All tools available
            "verifying": cls._PHASE_VERIFYING,
        }
        return phase_map.get(phase)

    @classmethod
    def read_only_tools(cls) -> frozenset[ToolName]:
        """All read-only tools."""
        return cls._READ_ONLY

    @classmethod
    def action_tools(cls) -> frozenset[ToolName]:
        """All action/write tools."""
        return cls._ACTION

    @classmethod
    def safe_parallel_tools(cls) -> frozenset[ToolName]:
        """All tools safe for concurrent execution."""
        return cls._SAFE_PARALLEL

    @classmethod
    def search_tools(cls) -> frozenset[ToolName]:
        """All search-related tools."""
        return cls._SEARCH

    @classmethod
    def is_safe_mcp_tool(cls, tool_name: str) -> bool:
        """Check if a dynamic MCP tool name is safe for parallel execution."""
        return tool_name.startswith(cls._SAFE_MCP_PREFIXES)

    @classmethod
    def is_action_mcp_tool(cls, tool_name: str) -> bool:
        """Check if a dynamic MCP tool name is an action tool."""
        return tool_name.startswith(cls._ACTION_MCP_PREFIXES)

    @classmethod
    def is_read_tool(cls, tool_name: str) -> bool:
        """Check if a tool name (string) represents a read-only tool.

        Handles both enum members and dynamic MCP tool names.
        """
        try:
            return cls(tool_name).is_read_only
        except ValueError:
            # Dynamic MCP tool or unknown — check prefixes
            return cls.is_safe_mcp_tool(tool_name)

    @classmethod
    def is_action_tool_name(cls, tool_name: str) -> bool:
        """Check if a tool name (string) represents an action tool.

        Handles both enum members and dynamic MCP tool names.
        """
        try:
            return cls(tool_name).is_action
        except ValueError:
            # Dynamic MCP tool or unknown — check prefixes
            return cls.is_action_mcp_tool(tool_name)


# ─────────────────────────────────────────────────────────────────────
# Classification set definitions (must be after class body)
# ─────────────────────────────────────────────────────────────────────

ToolName._READ_ONLY = frozenset(
    {
        # File reads
        ToolName.FILE_READ,
        ToolName.FILE_SEARCH,
        ToolName.FILE_FIND,
        ToolName.FILE_FIND_BY_NAME,
        ToolName.FILE_FIND_IN_CONTENT,
        ToolName.FILE_LIST,
        ToolName.FILE_LIST_DIRECTORY,
        ToolName.FILE_VIEW,
        # Browser reads (view-only, no navigation side effects)
        ToolName.BROWSER_VIEW,
        ToolName.BROWSER_CONSOLE_VIEW,
        ToolName.BROWSER_SCREENSHOT,
        ToolName.BROWSER_AGENT_EXTRACT,
        # Playwright reads
        ToolName.PLAYWRIGHT_GET_CONTENT,
        ToolName.PLAYWRIGHT_SCREENSHOT,
        ToolName.PLAYWRIGHT_PDF,
        ToolName.PLAYWRIGHT_GET_COOKIES,
        ToolName.PLAYWRIGHT_DETECT_PROTECTION,
        ToolName.PLAYWRIGHT_WAIT_FOR_SELECTOR,
        # Search operations
        ToolName.SEARCH,
        ToolName.INFO_SEARCH_WEB,
        ToolName.WEB_SEARCH,
        ToolName.WIDE_RESEARCH,
        # Code reads
        ToolName.CODE_LIST_ARTIFACTS,
        ToolName.CODE_READ_ARTIFACT,
        ToolName.CODE_ANALYZE,
        ToolName.CODE_SEARCH,
        # Workspace reads
        ToolName.WORKSPACE_INFO,
        ToolName.WORKSPACE_TREE,
        ToolName.WORKSPACE_EXISTS,
        # Shell reads
        ToolName.SHELL_VIEW,
        # MCP reads
        ToolName.MCP_RESOURCES,
        ToolName.MCP_TOOL_SCHEMAS,
        ToolName.MCP_HEALTH_CHECK,
        ToolName.MCP_LIST_RESOURCES,
        ToolName.MCP_READ_RESOURCE,
        ToolName.MCP_SERVER_STATUS,
        # Test (reads: listing only)
        ToolName.TEST_LIST,
        # Export reads
        ToolName.EXPORT_LIST,
        # Git reads
        ToolName.GIT_STATUS,
        ToolName.GIT_LOG,
        ToolName.GIT_DIFF,
        ToolName.GIT_BRANCHES,
        # Deep scan (analysis, no modifications)
        ToolName.DEEP_SCAN_PROJECT,
        ToolName.DEEP_SCAN_CODE,
        ToolName.DEEP_SCAN_DEPENDENCIES,
        ToolName.DEEP_SCAN_SECURITY,
        ToolName.DEEP_SCAN_QUALITY,
        # Knowledge base reads
        ToolName.KB_QUERY,
        ToolName.KB_LIST,
        # Canvas reads
        ToolName.CANVAS_GET_STATE,
        # Skill reads
        ToolName.SKILL_LIST_USER,
        # Schedule reads
        ToolName.AGENT_LIST_SCHEDULED_TASKS,
        # Idle
        ToolName.IDLE,
    }
)

ToolName._ACTION = frozenset(
    {
        # File writes
        ToolName.FILE_WRITE,
        ToolName.FILE_CREATE,
        ToolName.FILE_DELETE,
        ToolName.FILE_RENAME,
        ToolName.FILE_MOVE,
        ToolName.FILE_STR_REPLACE,
        # Browser actions (side effects: navigation, clicks, state changes)
        ToolName.BROWSER_NAVIGATE,
        ToolName.BROWSER_GET_CONTENT,
        ToolName.BROWSER_CLICK,
        ToolName.BROWSER_INPUT,
        ToolName.BROWSER_MOVE_MOUSE,
        ToolName.BROWSER_PRESS_KEY,
        ToolName.BROWSER_SELECT_OPTION,
        ToolName.BROWSER_SCROLL_UP,
        ToolName.BROWSER_SCROLL_DOWN,
        ToolName.BROWSER_CONSOLE_EXEC,
        ToolName.BROWSER_RESTART,
        ToolName.BROWSER_AGENT_RUN,
        # Playwright actions
        ToolName.PLAYWRIGHT_LAUNCH,
        ToolName.PLAYWRIGHT_NAVIGATE,
        ToolName.PLAYWRIGHT_FILL,
        ToolName.PLAYWRIGHT_TYPE,
        ToolName.PLAYWRIGHT_SELECT_OPTION,
        ToolName.PLAYWRIGHT_PRESS_KEY,
        ToolName.PLAYWRIGHT_EVALUATE,
        ToolName.PLAYWRIGHT_SET_COOKIES,
        ToolName.PLAYWRIGHT_INTERCEPT_REQUESTS,
        ToolName.PLAYWRIGHT_CLOUDFLARE_BYPASS,
        ToolName.PLAYWRIGHT_LOGIN_WITH_2FA,
        ToolName.PLAYWRIGHT_FILL_2FA_CODE,
        ToolName.PLAYWRIGHT_SOLVE_RECAPTCHA,
        ToolName.PLAYWRIGHT_STEALTH_NAVIGATE,
        # Code execution
        ToolName.CODE_EXECUTE,
        ToolName.CODE_EXECUTE_PYTHON,
        ToolName.CODE_EXECUTE_JAVASCRIPT,
        ToolName.CODE_CREATE_ARTIFACT,
        ToolName.CODE_UPDATE_ARTIFACT,
        ToolName.CODE_CLEANUP_WORKSPACE,
        ToolName.CODE_SAVE_ARTIFACT,
        ToolName.CODE_FORMAT,
        ToolName.CODE_LINT,
        # Shell execution
        ToolName.SHELL_EXEC,
        ToolName.SHELL_WAIT,
        ToolName.SHELL_WRITE_TO_PROCESS,
        ToolName.SHELL_KILL_PROCESS,
        # Workspace actions
        ToolName.WORKSPACE_INIT,
        ToolName.WORKSPACE_CLEAN,
        # User interaction
        ToolName.MESSAGE_ASK_USER,
        ToolName.MESSAGE_NOTIFY_USER,
        # MCP actions
        ToolName.MCP_CALL_TOOL,
        # Test execution (modifies environment state)
        ToolName.TEST_RUN,
        ToolName.TEST_COVERAGE,
        # Export actions
        ToolName.EXPORT,
        ToolName.EXPORT_ORGANIZE,
        ToolName.EXPORT_ARCHIVE,
        ToolName.EXPORT_REPORT,
        # Scraping
        ToolName.SCRAPE_STRUCTURED,
        ToolName.SCRAPE_BATCH,
        ToolName.ADAPTIVE_SCRAPE,
        # Canvas actions
        ToolName.CANVAS_CREATE_PROJECT,
        ToolName.CANVAS_ADD_ELEMENT,
        ToolName.CANVAS_MODIFY_ELEMENT,
        ToolName.CANVAS_DELETE_ELEMENTS,
        ToolName.CANVAS_ARRANGE_LAYER,
        ToolName.CANVAS_EXPORT,
        ToolName.CANVAS_GENERATE_IMAGE,
        # Git actions
        ToolName.GIT_CLONE,
        # Slides actions
        ToolName.SLIDES_CREATE,
        ToolName.SLIDES_ADD_CHART,
        ToolName.SLIDES_EXPORT,
        # Chart
        ToolName.CHART_CREATE,
        # Skill actions
        ToolName.SKILL_CREATE,
        ToolName.SKILL_DELETE,
        # Schedule actions
        ToolName.AGENT_SCHEDULE_TASK,
        ToolName.AGENT_CANCEL_SCHEDULED_TASK,
        ToolName.AGENT_START_TASK,
    }
)

ToolName._SAFE_PARALLEL = frozenset(
    {
        ToolName.FILE_READ,
        ToolName.FILE_SEARCH,
        ToolName.FILE_LIST_DIRECTORY,
        ToolName.BROWSER_VIEW,
        ToolName.CODE_LIST_ARTIFACTS,
        ToolName.CODE_READ_ARTIFACT,
        ToolName.MCP_LIST_RESOURCES,
        ToolName.MCP_READ_RESOURCE,
        ToolName.MCP_SERVER_STATUS,
        ToolName.MCP_RESOURCES,
        ToolName.MCP_HEALTH_CHECK,
    }
)

ToolName._SEARCH = frozenset(
    {
        ToolName.INFO_SEARCH_WEB,
        ToolName.WEB_SEARCH,
        ToolName.WIDE_RESEARCH,
        ToolName.SEARCH,
    }
)

ToolName._NETWORK = frozenset(
    {
        ToolName.INFO_SEARCH_WEB,
        ToolName.BROWSER_GET_CONTENT,
        ToolName.BROWSER_NAVIGATE,
        ToolName.MCP_CALL_TOOL,
        ToolName.WIDE_RESEARCH,
        ToolName.SEARCH,
        ToolName.SCRAPE_STRUCTURED,
        ToolName.SCRAPE_BATCH,
        ToolName.ADAPTIVE_SCRAPE,
        ToolName.PLAYWRIGHT_NAVIGATE,
        ToolName.PLAYWRIGHT_STEALTH_NAVIGATE,
    }
)

ToolName._VIEW = frozenset(
    {
        ToolName.FILE_VIEW,
        ToolName.BROWSER_VIEW,
        ToolName.BROWSER_GET_CONTENT,
        ToolName.BROWSER_AGENT_EXTRACT,
        ToolName.PLAYWRIGHT_GET_CONTENT,
        ToolName.PLAYWRIGHT_SCREENSHOT,
    }
)

ToolName._PHASE_PLANNING = frozenset(
    {
        ToolName.FILE_READ,
        ToolName.FILE_LIST,
        ToolName.FILE_LIST_DIRECTORY,
        ToolName.FILE_SEARCH,
        ToolName.FILE_FIND,
        ToolName.FILE_FIND_BY_NAME,
        ToolName.FILE_FIND_IN_CONTENT,
        ToolName.INFO_SEARCH_WEB,
        ToolName.WIDE_RESEARCH,
        ToolName.BROWSER_NAVIGATE,
        ToolName.BROWSER_VIEW,
        ToolName.BROWSER_GET_CONTENT,
        ToolName.WORKSPACE_INFO,
        ToolName.WORKSPACE_TREE,
        ToolName.SHELL_EXEC,
        ToolName.SHELL_VIEW,
        ToolName.MESSAGE_ASK_USER,
        ToolName.MESSAGE_NOTIFY_USER,
        ToolName.CODE_LIST_ARTIFACTS,
        ToolName.CODE_READ_ARTIFACT,
    }
)

ToolName._PHASE_VERIFYING = frozenset(
    {
        ToolName.FILE_READ,
        ToolName.FILE_LIST,
        ToolName.FILE_LIST_DIRECTORY,
        ToolName.FILE_SEARCH,
        ToolName.SHELL_EXEC,
        ToolName.SHELL_VIEW,
        ToolName.BROWSER_NAVIGATE,
        ToolName.BROWSER_VIEW,
        ToolName.BROWSER_GET_CONTENT,
        ToolName.TEST_RUN,
        ToolName.TEST_LIST,
        ToolName.TEST_COVERAGE,
        ToolName.CODE_EXECUTE,
        ToolName.CODE_LIST_ARTIFACTS,
        ToolName.CODE_READ_ARTIFACT,
        ToolName.MESSAGE_ASK_USER,
    }
)

ToolName._SAFE_MCP_PREFIXES = (
    "mcp_get_",
    "mcp_list_",
    "mcp_search_",
    "mcp_read_",
    "mcp_fetch_",
)

ToolName._ACTION_MCP_PREFIXES = (
    "mcp_create_",
    "mcp_update_",
    "mcp_delete_",
    "mcp_write_",
    "mcp_execute_",
)
