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
  "browser_get_content": "Searching",  // Fetching URL content
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
  "browser_scroll": "Scrolling",
  "browser_wait": "Waiting",
  "browser_back": "Navigating",
  "browser_forward": "Navigating",
  "browser_console_exec": "Executing",
  "browser_console_view": "Viewing",

  // === BROWSER AGENT (autonomous browsing) ===
  "browser_agent_run": "Browsing",
  "browser_agent_extract": "Extracting",
  "browsing": "Browsing",

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
  "playwright_navigate": "Browsing",
  "playwright_click": "Clicking",
  "playwright_fill": "Typing",
  "playwright_select": "Selecting",
  "playwright_screenshot": "Capturing",
  "playwright_pdf": "Exporting",
  "playwright_get_content": "Reading",
  "playwright_wait_for": "Waiting",
  "playwright_get_cookies": "Reading",
  "playwright_set_cookies": "Setting",

  // === SEARCH (unified) ===
  "search": "Searching",
  "web_search": "Searching",
  "info_search_web": "Searching",
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
  "code_run_file": "Running",
  "code_install_packages": "Installing",
  "code_list_artifacts": "Listing",
  "code_read_artifact": "Reading",

  // === TEST RUNNER ===
  "test_run": "Testing",
  "test_run_file": "Testing",
  "test_run_suite": "Testing",

  // === MCP ===
  "mcp_call_tool": "Calling",
  "mcp_list_resources": "Listing",
  "mcp_read_resource": "Reading",
  "mcp_server_status": "Checking",

  // === COMMUNICATION ===
  "message_notify_user": "Notifying",
  "message_ask_user": "Asking",

  // === IDLE ===
  "idle_standby": "Waiting",
  "idle": "Waiting",

  // === AGENT/SKILL ===
  "agent_start_task": "Starting",
  "skill_invoke": "Loading",
  "skill_create": "Creating",
  "skill_list": "Listing",

  // === EXPORT ===
  "export_pdf": "Exporting",
  "export_csv": "Exporting",
  "export_json": "Exporting",
  "export": "Exporting",

  // === SLIDES ===
  "slides_create": "Creating",
  "slides_add_slide": "Adding",
  "slides_export": "Exporting",

  // === WORKSPACE ===
  "workspace_create": "Creating",
  "workspace_organize": "Organizing",
  "workspace_list": "Listing",

  // === SCHEDULE ===
  "schedule_create": "Scheduling",
  "schedule_list": "Listing",
  "schedule_cancel": "Canceling",

  // === DEEP SCAN ===
  "deep_scan": "Analyzing",
  "deep_scan_analyze": "Analyzing",

  // === AGENT MODE ===
  "agent_mode_switch": "Switching",
  "mode_switch": "Switching",

  // === CODE DEV ===
  "code_dev_analyze": "Analyzing",
  "code_dev_refactor": "Refactoring",

  // === PLAN ===
  "plan_create": "Planning",
  "plan_update": "Updating",
  "plan_get": "Reading",

  // === REPO MAP ===
  "repo_map": "Mapping",
  "repo_map_generate": "Mapping"
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
  "browser_get_content": "url",
  "browser_view": "page",
  "browser_navigate": "url",
  "browser_restart": "url",
  "browser_click": "element",
  "browser_input": "text",
  "browser_move_mouse": "position",
  "browser_press_key": "key",
  "browser_select_option": "option",
  "browser_scroll_up": "page",
  "browser_scroll_down": "page",
  "browser_scroll": "direction",
  "browser_wait": "selector",
  "browser_back": "page",
  "browser_forward": "page",
  "browser_console_exec": "code",
  "browser_console_view": "console",

  // Playwright
  "playwright_navigate": "url",
  "playwright_click": "selector",
  "playwright_fill": "text",
  "playwright_select": "value",
  "playwright_screenshot": "filename",
  "playwright_pdf": "filename",
  "playwright_get_content": "selector",
  "playwright_wait_for": "selector",
  "playwright_get_cookies": "cookies",
  "playwright_set_cookies": "cookies",

  // Browser Agent
  "browser_agent_run": "task",
  "browser_agent_extract": "extraction_goal",
  "browsing": "task",
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
  "git_status": "repo_path",
  "git_diff": "repo_path",
  "git_log": "repo_path",
  "git_branches": "repo_path",

  // Code Executor
  "code_execute": "code",
  "code_execute_python": "code",
  "code_execute_javascript": "code",
  "code_run_file": "file_path",
  "code_install_packages": "packages",
  "code_list_artifacts": "artifacts",
  "code_read_artifact": "artifact_id",

  // Test Runner
  "test_run": "test_path",
  "test_run_file": "file_path",
  "test_run_suite": "suite_name",

  // MCP
  "mcp_call_tool": "tool_name",
  "mcp_list_resources": "server_name",
  "mcp_read_resource": "resource_uri",
  "mcp_server_status": "server_name",

  // Message
  "message_notify_user": "message",
  "message_ask_user": "question",

  // Idle
  "idle_standby": "reason",
  "idle": "reason",

  // Skills
  "agent_start_task": "task",
  "skill_invoke": "skill_name",
  "skill_create": "name",
  "skill_list": "category",

  // Export
  "export_pdf": "filename",
  "export_csv": "filename",
  "export_json": "filename",
  "export": "format",

  // Slides
  "slides_create": "title",
  "slides_add_slide": "content",
  "slides_export": "filename",

  // Workspace
  "workspace_create": "name",
  "workspace_organize": "type",
  "workspace_list": "filter",

  // Schedule
  "schedule_create": "time",
  "schedule_list": "filter",
  "schedule_cancel": "schedule_id",

  // Deep Scan
  "deep_scan": "target",
  "deep_scan_analyze": "target",

  // Agent Mode
  "agent_mode_switch": "mode",
  "mode_switch": "mode",

  // Code Dev
  "code_dev_analyze": "file_path",
  "code_dev_refactor": "file_path",

  // Plan
  "plan_create": "goal",
  "plan_update": "plan_id",
  "plan_get": "plan_id",

  // Repo Map
  "repo_map": "repo_path",
  "repo_map_generate": "repo_path"
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
  "browsing": "Web Pilot",
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

  // === SYSTEM ===
  "agent_mode": "Mode Switch",
  "plan": "Planner",
  "repo_map": "Codebase Map",
  "idle": "Standby"
};

import SearchIcon from '../components/icons/SearchIcon.vue';
import EditIcon from '../components/icons/EditIcon.vue';
import BrowserIcon from '../components/icons/BrowserIcon.vue';
import ShellIcon from '../components/icons/ShellIcon.vue';
import GlobeIcon from '../components/icons/GlobeIcon.vue';
import IdleIcon from '../components/icons/IdleIcon.vue';
import AgentModeIcon from '../components/icons/AgentModeIcon.vue';
import PythonIcon from '../components/icons/PythonIcon.vue';
import { GitBranch, Play, Download, Presentation, FolderTree, Calendar, Scan, Wand2, FileCode, Map, Wrench, MessageCircle, TestTube } from 'lucide-vue-next';

/**
 * Tool icon mapping - Consistent visual identity for each tool
 *
 * ICON GUIDELINES:
 * - Use custom icons for core tools (Terminal, Browser, Editor, Search)
 * - Use Lucide icons for secondary tools
 * - Icons should be immediately recognizable
 * - Maintain consistent 16-21px sizing
 */
export const TOOL_ICON_MAP: {[key: string]: any} = {
  // === CORE TOOLS ===
  "shell": ShellIcon,
  "file": EditIcon,
  "browser": BrowserIcon,
  "browser_agent": GlobeIcon,
  "browsing": GlobeIcon,
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
  "code_executor": PythonIcon,
  "code_execute": PythonIcon,  // Alias
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
export type ContentViewType = 'vnc' | 'terminal' | 'editor' | 'search' | 'generic' | 'wide_research' | 'git' | 'test' | 'skill' | 'export' | 'slides' | 'workspace' | 'schedule' | 'scan';
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
  browsing: {
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
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  // Alias for code_executor (backend sends this name)
  code_execute: {
    primaryView: 'terminal',
    secondaryView: 'vnc',
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
    primaryView: 'git',
    secondaryView: 'terminal',
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
    primaryView: 'test',
    secondaryView: 'terminal',
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
    primaryView: 'skill',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  skill_invoke: {
    primaryView: 'skill',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  skill_creator: {
    primaryView: 'skill',
    secondaryView: 'editor',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === EXPORT ===
  export: {
    primaryView: 'export',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === SLIDES ===
  slides: {
    primaryView: 'slides',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === WORKSPACE ===
  workspace: {
    primaryView: 'workspace',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === SCHEDULE ===
  schedule: {
    primaryView: 'schedule',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },

  // === DEEP SCAN ===
  deep_scan_analyzer: {
    primaryView: 'scan',
    secondaryView: 'terminal',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  deep_scan: {
    primaryView: 'scan',
    secondaryView: 'terminal',
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
    primaryView: 'workspace',
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
};

/**
 * Functions that show a text placeholder instead of VNC
 * (operations that don't require visual output - HTTP-based, not browser UI)
 */
export const TEXT_ONLY_FUNCTIONS = new Set([
  'search',  // Fetches HTML via HTTP, no browser UI needed
  'browser_get_content',  // Legacy support
  'wide_research'  // Wide research uses HTTP-based parallel search (API-based)
  // Note: web_search CAN use browser when search_prefer_browser is enabled (visible in VNC)
  // Note: browser_agent_extract DOES use browser visually for extraction
]);
