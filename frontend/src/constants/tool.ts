/**
 * Tool function mapping - Manus-style verb labels
 *
 * STANDARDIZATION RULES:
 * - All verbs use present continuous tense (-ing)
 * - Single word verbs when possible
 * - Format: [icon] Verb Resource
 *
 * @see docs/guides/TOOL_STANDARDIZATION.md
 */
export const TOOL_FUNCTION_MAP: {[key: string]: string} = {
  // === SHELL/TERMINAL ===
  "shell_exec": "Running",
  "shell_view": "Viewing",
  "shell_wait": "Waiting",
  "shell_write_to_process": "Writing",
  "shell_kill_process": "Stopping",

  // === FILE/EDITOR ===
  "file_read": "Reading",
  "file_write": "Creating",
  "file_str_replace": "Editing",
  "file_find_in_content": "Searching",
  "file_find_by_name": "Finding",
  "file_view": "Viewing",

  // === BROWSER ===
  "search": "Searching",             // BrowserTool: fast text-only content fetch
  "browser_view": "Viewing",
  "browser_navigate": "Browsing",
  "browser_restart": "Restarting",
  "browser_click": "Clicking",
  "browser_input": "Typing",
  "browser_move_mouse": "Moving",
  "browser_press_key": "Pressing",
  "browser_select_option": "Selecting",
  "browser_scroll_up": "Scrolling",
  "browser_scroll_down": "Scrolling",
  "browser_console_exec": "Executing",
  "browser_console_view": "Viewing",

  // === BROWSER AGENT (autonomous browsing) ===
  "browser_agent_run": "Browsing",
  "browser_agent_extract": "Extracting",

  // === BROWSER-USE INTERNAL ACTIONS ===
  "go_to_url": "Opening",
  "click_element": "Clicking",
  "input_text": "Typing",
  "scroll_down": "Scrolling",
  "scroll_up": "Scrolling",
  "go_back": "Navigating",
  "wait": "Waiting",
  "extract_content": "Reading",
  "done": "Completed",
  "send_keys": "Pressing",
  "scroll_to_text": "Finding",
  "get_dropdown_options": "Checking",
  "select_dropdown_option": "Selecting",

  // === PLAYWRIGHT ===
  "playwright_launch": "Launching",
  "playwright_navigate": "Browsing",
  "playwright_click": "Clicking",
  "playwright_fill": "Typing",
  "playwright_type": "Typing",
  "playwright_select_option": "Selecting",
  "playwright_screenshot": "Capturing",
  "playwright_pdf": "Exporting",
  "playwright_get_content": "Reading",
  "playwright_wait_for_selector": "Waiting",
  "playwright_get_cookies": "Reading",
  "playwright_set_cookies": "Setting",
  "playwright_evaluate": "Executing",
  "playwright_stealth_navigate": "Browsing",
  "playwright_detect_protection": "Detecting",
  "playwright_intercept_requests": "Intercepting",
  "playwright_solve_recaptcha": "Solving",
  "playwright_cloudflare_bypass": "Bypassing",
  "playwright_fill_2fa_code": "Authenticating",
  "playwright_login_with_2fa": "Authenticating",

  // === SEARCH (unified) ===
  "info_search_web": "Searching",
  "web_search": "Searching",
  "wide_research": "Searching",

  // === GIT ===
  "git_clone": "Cloning",
  "git_status": "Checking",
  "git_diff": "Comparing",
  "git_log": "Reading",
  "git_branches": "Listing",

  // === CODE EXECUTOR ===
  "code_execute": "Executing",
  "code_execute_python": "Running",
  "code_execute_javascript": "Running",
  "code_list_artifacts": "Listing",
  "code_read_artifact": "Reading",
  "code_cleanup_workspace": "Cleaning",
  "code_save_artifact": "Saving",

  // === CODE DEV ===
  "code_format": "Formatting",
  "code_lint": "Linting",
  "code_analyze": "Analyzing",
  "code_search": "Searching",

  // === TEST RUNNER ===
  "test_run": "Testing",
  "test_list": "Listing",
  "test_coverage": "Analyzing",

  // === MCP ===
  "mcp_call_tool": "Calling",
  "mcp_list_resources": "Listing",
  "mcp_read_resource": "Reading",
  "mcp_server_status": "Checking",
  "mcp_tool_schemas": "Listing",
  "mcp_resources": "Listing",
  "mcp_health_check": "Checking",

  // === COMMUNICATION ===
  "message_notify_user": "Notifying",
  "message_ask_user": "Asking",

  // === IDLE ===
  "idle": "Waiting",

  // === AGENT MODE ===
  "agent_start_task": "Starting",

  // === SKILL ===
  "skill_invoke": "Loading",
  "skill_create": "Creating",
  "skill_list_user": "Listing",
  "skill_list": "Listing",
  "skill_delete": "Deleting",

  // === EXPORT ===
  "export_organize": "Organizing",
  "export_archive": "Archiving",
  "export_report": "Exporting",
  "export_list": "Listing",

  // === SLIDES ===
  "slides_create": "Creating",
  "slides_add_chart": "Adding",
  "slides_export": "Exporting",

  // === WORKSPACE ===
  "workspace_init": "Creating",
  "workspace_info": "Checking",
  "workspace_tree": "Viewing",
  "workspace_clean": "Cleaning",
  "workspace_exists": "Checking",

  // === SCHEDULE ===
  "agent_schedule_task": "Scheduling",
  "agent_cancel_scheduled_task": "Canceling",
  "agent_list_scheduled_tasks": "Listing",

  // === DEEP SCAN ===
  "deep_scan_code": "Analyzing",
  "deep_scan_security": "Scanning",
  "deep_scan_quality": "Analyzing",
  "deep_scan_dependencies": "Analyzing",
  "deep_scan_project": "Scanning",

  // === REPO MAP ===
  "repo_map": "Mapping",

  // === CANVAS ===
  "canvas_create_project": "Creating",
  "canvas_get_state": "Reading",
  "canvas_add_element": "Adding",
  "canvas_modify_element": "Modifying",
  "canvas_delete_elements": "Deleting",
  "canvas_generate_image": "Generating",
  "canvas_arrange_layer": "Arranging",
  "canvas_export": "Exporting",
};

/**
 * Display name mapping for tool function parameters
 */
export const TOOL_FUNCTION_ARG_MAP: {[key: string]: string} = {
  // Shell
  "shell_exec": "command",
  "shell_view": "shell",
  "shell_wait": "shell",
  "shell_write_to_process": "input",
  "shell_kill_process": "shell",

  // File
  "file_read": "file",
  "file_write": "file",
  "file_str_replace": "file",
  "file_find_in_content": "file",
  "file_find_by_name": "path",
  "file_view": "file",

  // Browser
  "search": "url",
  "browser_view": "page",
  "browser_navigate": "url",
  "browser_restart": "url",
  "browser_click": "index",
  "browser_input": "text",
  "browser_move_mouse": "coordinate_x",
  "browser_press_key": "key",
  "browser_select_option": "option",
  "browser_scroll_up": "page",
  "browser_scroll_down": "page",
  "browser_console_exec": "javascript",
  "browser_console_view": "console",

  // Playwright
  "playwright_launch": "browser_type",
  "playwright_navigate": "url",
  "playwright_click": "selector",
  "playwright_fill": "value",
  "playwright_type": "text",
  "playwright_select_option": "value",
  "playwright_screenshot": "path",
  "playwright_pdf": "path",
  "playwright_get_content": "selector",
  "playwright_wait_for_selector": "selector",
  "playwright_get_cookies": "url",
  "playwright_set_cookies": "cookies",
  "playwright_evaluate": "expression",
  "playwright_stealth_navigate": "url",
  "playwright_detect_protection": "url",
  "playwright_intercept_requests": "url_patterns",
  "playwright_cloudflare_bypass": "url",
  "playwright_login_with_2fa": "url",

  // Browser Agent
  "browser_agent_run": "task",
  "browser_agent_extract": "extraction_goal",
  "go_to_url": "url",
  "click_element": "element",
  "input_text": "text",
  "scroll_down": "page",
  "scroll_up": "page",
  "go_back": "page",
  "wait": "duration",
  "extract_content": "selector",
  "done": "result",
  "send_keys": "keys",
  "scroll_to_text": "text",
  "get_dropdown_options": "selector",
  "select_dropdown_option": "option",

  // Search
  "web_search": "query",
  "info_search_web": "query",
  "wide_research": "topic",

  // Git
  "git_clone": "url",
  "git_status": "path",
  "git_diff": "path",
  "git_log": "path",
  "git_branches": "path",

  // Code Executor
  "code_execute": "code",
  "code_execute_python": "code",
  "code_execute_javascript": "code",
  "code_list_artifacts": "working_dir",
  "code_read_artifact": "filename",
  "code_cleanup_workspace": "working_dir",
  "code_save_artifact": "filename",

  // Code Dev
  "code_format": "file",
  "code_lint": "file",
  "code_analyze": "file",
  "code_search": "query",

  // Test Runner
  "test_run": "path",
  "test_list": "path",
  "test_coverage": "path",

  // MCP
  "mcp_call_tool": "tool_name",
  "mcp_list_resources": "server_name",
  "mcp_read_resource": "uri",
  "mcp_server_status": "server_name",
  "mcp_tool_schemas": "server_name",
  "mcp_resources": "server_name",
  "mcp_health_check": "server_name",

  // Message
  "message_notify_user": "text",
  "message_ask_user": "text",

  // Idle
  "idle": "reason",

  // Agent Mode
  "agent_start_task": "task_description",

  // Skill
  "skill_invoke": "skill_name",
  "skill_create": "id",
  "skill_list_user": "category",
  "skill_list": "category",
  "skill_delete": "skill_id",

  // Export
  "export_organize": "source_dir",
  "export_archive": "source_dir",
  "export_report": "source_dir",
  "export_list": "source_dir",

  // Slides
  "slides_create": "title",
  "slides_add_chart": "chart_type",
  "slides_export": "format",

  // Workspace
  "workspace_init": "name",
  "workspace_info": "path",
  "workspace_tree": "path",
  "workspace_clean": "path",
  "workspace_exists": "path",

  // Schedule
  "agent_schedule_task": "task_description",
  "agent_cancel_scheduled_task": "task_id",

  // Deep Scan
  "deep_scan_code": "path",
  "deep_scan_security": "path",
  "deep_scan_quality": "path",
  "deep_scan_dependencies": "path",
  "deep_scan_project": "path",

  // Repo Map
  "repo_map": "path",

  // Canvas
  "canvas_create_project": "name",
  "canvas_get_state": "project_id",
  "canvas_add_element": "element_type",
  "canvas_modify_element": "element_id",
  "canvas_delete_elements": "element_ids",
  "canvas_generate_image": "prompt",
  "canvas_arrange_layer": "element_id",
  "canvas_export": "format",
};

/**
 * Tool name mapping - User-friendly display names
 *
 * DESIGN PRINCIPLES:
 * - Use familiar, intuitive names (e.g., "Terminal" not "Shell")
 * - Keep names short (1-2 words max)
 * - Use title case consistently
 * - Group related tools under same category name
 */
export const TOOL_NAME_MAP: {[key: string]: string} = {
  // === CORE TOOLS ===
  "shell": "Terminal",
  "file": "Editor",
  "browser": "Browser",
  "browser_agent": "Web Pilot",
  "playwright": "Browser",

  // === SEARCH ===
  "search": "Search",
  "info": "Search",
  "info_search_web": "Search",
  "web_search": "Search",
  "wide_research": "Deep Research",

  // === COMMUNICATION ===
  "message": "Assistant",

  // === VERSION CONTROL ===
  "git": "Git",

  // === CODE TOOLS ===
  "code_executor": "Code Runner",
  "code_execute": "Code Runner",  // Alias
  "code_dev": "Code Editor",

  // === TESTING ===
  "test_runner": "Test Runner",

  // === INTEGRATIONS ===
  "mcp": "Extension",

  // === AUTOMATION ===
  "skill": "Skill",
  "skill_invoke": "Skill",
  "skill_creator": "Skill Builder",

  // === OUTPUT ===
  "export": "Export",
  "slides": "Slides",

  // === ORGANIZATION ===
  "workspace": "Workspace",
  "schedule": "Scheduler",

  // === ANALYSIS ===
  "deep_scan_analyzer": "Analyzer",
  "deep_scan": "Analyzer",

  // === CANVAS ===
  "canvas": "Canvas",

  // === SYSTEM ===
  "agent_mode": "Mode Switch",
  "plan": "Planner",
  "repo_map": "Codebase Map",
  "idle": "Standby"
};

import type { Component } from 'vue';
import SearchIcon from '../components/icons/SearchIcon.vue';
import EditIcon from '../components/icons/EditIcon.vue';
import BrowserIcon from '../components/icons/BrowserIcon.vue';
import ShellIcon from '../components/icons/ShellIcon.vue';
import GlobeIcon from '../components/icons/GlobeIcon.vue';
import IdleIcon from '../components/icons/IdleIcon.vue';
import AgentModeIcon from '../components/icons/AgentModeIcon.vue';
import { GitBranch, Play, Download, Presentation, FolderTree, Calendar, Scan, Wand2, FileCode, Map, Wrench, MessageCircle, TestTube, Terminal, Palette } from 'lucide-vue-next';

/**
 * Tool icon mapping - Consistent visual identity for each tool
 *
 * ICON GUIDELINES:
 * - Use custom icons for core tools (Terminal, Browser, Editor, Search)
 * - Use Lucide icons for secondary tools
 * - Icons should be immediately recognizable
 * - Maintain consistent 16-21px sizing
 */
export const TOOL_ICON_MAP: Record<string, Component> = {
  // === CORE TOOLS ===
  "shell": ShellIcon,
  "file": EditIcon,
  "browser": BrowserIcon,
  "browser_agent": GlobeIcon,
  "playwright": BrowserIcon,

  // === SEARCH ===
  "search": SearchIcon,
  "info": SearchIcon,
  "info_search_web": SearchIcon,
  "web_search": SearchIcon,
  "wide_research": SearchIcon,

  // === VERSION CONTROL ===
  "git": GitBranch,

  // === CODE TOOLS ===
  "code_executor": Terminal,
  "code_execute": Terminal,  // Alias
  "code_dev": FileCode,

  // === TESTING ===
  "test_runner": TestTube,

  // === INTEGRATIONS ===
  "mcp": Wrench,

  // === AUTOMATION ===
  "skill": Wand2,
  "skill_invoke": Wand2,
  "skill_creator": Wand2,

  // === OUTPUT ===
  "export": Download,
  "slides": Presentation,

  // === ORGANIZATION ===
  "workspace": FolderTree,
  "schedule": Calendar,

  // === ANALYSIS ===
  "deep_scan_analyzer": Scan,
  "deep_scan": Scan,

  // === CANVAS ===
  "canvas": Palette,

  // === SYSTEM ===
  "agent_mode": AgentModeIcon,
  "plan": Play,
  "repo_map": Map,
  "message": MessageCircle,
  "idle": IdleIcon
};

/**
 * Content view types for the unified tool panel
 */
export type ContentViewType = 'vnc' | 'terminal' | 'editor' | 'search' | 'generic' | 'wide_research';
export type ViewMode = 'primary' | 'secondary' | 'tertiary';

export interface ContentConfig {
  primaryView: ContentViewType;
  secondaryView?: ContentViewType;
  tertiaryView?: ContentViewType;
  tabLabels: string[];  // e.g., ['Screen', 'Output'] or ['Modified', 'Original', 'Diff']
  defaultView: ViewMode;
  showTabs: boolean;
}

/**
 * Content configuration for each tool type
 * Defines which views are available and how tabs are displayed
 */
export const TOOL_CONTENT_CONFIG: Record<string, ContentConfig> = {
  // === SHELL/TERMINAL ===
  shell: {
    primaryView: 'terminal',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === BROWSER ===
  browser: {
    primaryView: 'vnc',
    secondaryView: 'terminal',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  browser_agent: {
    primaryView: 'vnc',
    secondaryView: 'terminal',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  playwright: {
    primaryView: 'vnc',
    secondaryView: 'terminal',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === CODE ===
  code_executor: {
    primaryView: 'terminal',
    secondaryView: 'editor',
    tertiaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  // Alias for code_executor (backend sends this name)
  code_execute: {
    primaryView: 'terminal',
    secondaryView: 'editor',
    tertiaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  code_dev: {
    primaryView: 'editor',
    secondaryView: 'terminal',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === FILE ===
  file: {
    primaryView: 'editor',
    secondaryView: 'editor',
    tertiaryView: 'editor',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === GIT ===
  git: {
    primaryView: 'terminal',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === SEARCH ===
  search: {
    primaryView: 'search',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  info: {
    primaryView: 'search',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  info_search_web: {
    primaryView: 'search',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  wide_research: {
    primaryView: 'search',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  web_search: {
    primaryView: 'search',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === TEST ===
  test_runner: {
    primaryView: 'terminal',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === CANVAS ===
  canvas: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === MCP ===
  mcp: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === SKILL ===
  skill: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  skill_invoke: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  skill_creator: {
    primaryView: 'generic',
    secondaryView: 'editor',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === EXPORT ===
  export: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === SLIDES ===
  slides: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === WORKSPACE ===
  workspace: {
    primaryView: 'terminal',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === SCHEDULE ===
  schedule: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === DEEP SCAN ===
  deep_scan_analyzer: {
    primaryView: 'terminal',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  deep_scan: {
    primaryView: 'terminal',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === AGENT MODE ===
  agent_mode: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === PLAN ===
  plan: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === REPO MAP ===
  repo_map: {
    primaryView: 'terminal',
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === MESSAGE ===
  message: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === IDLE ===
  idle: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  }
};

/**
 * Function-specific view overrides
 * Some functions should default to a different view than their tool's default
 */
export const FUNCTION_VIEW_OVERRIDES: Record<string, ViewMode> = {
  // Browser agent extraction - show output by default
  browser_agent_extract: 'secondary',
  // Artifact operations - show editor preview
  code_save_artifact: 'secondary',
  code_read_artifact: 'secondary',
};

/**
 * Functions that show a text placeholder instead of VNC.
 * Empty — all browser operations now show live VNC since navigate_for_display()
 * runs concurrently with HTTP fetch, giving the user visual feedback.
 */
export const TEXT_ONLY_FUNCTIONS = new Set<string>([]);
