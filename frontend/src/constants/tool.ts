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

  // === SEARCH (unified) ===
  "search": "Searching",
  "web_search": "Searching",
  "info_search_web": "Searching",
  "wide_research": "Searching",

  // === COMMUNICATION ===
  "message_notify_user": "Notifying",
  "message_ask_user": "Asking",

  // === IDLE ===
  "idle_standby": "Waiting",

  // === AGENT/SKILL ===
  "agent_start_task": "Starting",
  "skill_invoke": "Loading",

  // === CODE EXECUTION ===
  "code_execute": "Executing",
  "code_execute_python": "Running",
  "code_execute_javascript": "Running"
};

/**
 * Display name mapping for tool function parameters
 */
export const TOOL_FUNCTION_ARG_MAP: {[key: string]: string} = {
  "shell_exec": "command",
  "shell_view": "shell",
  "shell_wait": "shell",
  "shell_write_to_process": "input",
  "shell_kill_process": "shell",
  "file_read": "file",
  "file_write": "file",
  "file_str_replace": "file",
  "file_find_in_content": "file",
  "file_find_by_name": "path",
  "search": "url",  // Renamed from browser_get_content
  "browser_get_content": "url",  // Legacy support
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
  "browser_console_exec": "code",
  "browser_console_view": "console",
  "web_search": "query",  // Renamed from info_search_web
  "info_search_web": "query",  // Legacy support
  "message_notify_user": "message",
  "message_ask_user": "question",
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
  "idle_standby": "reason",
  "agent_start_task": "task",
  "skill_invoke": "skill_name",
  "code_execute": "code",
  "code_execute_python": "code",
  "code_execute_javascript": "code",
  "wide_research": "topic"
};

/**
 * Tool name mapping - unified search display like Manus
 */
export const TOOL_NAME_MAP: {[key: string]: string} = {
  "shell": "Terminal",
  "file": "Editor",
  "browser": "Browser",
  "browser_agent": "Web Pilot",
  "browsing": "Web Pilot",
  "search": "Search",        // Unified search tool name
  "info": "Search",          // Consolidated: info -> Search
  "web_search": "Search",    // Consolidated: web_search -> Search
  "message": "Message",
  "mcp": "MCP Tool",
  "idle": "Standby",
  "agent_mode": "Agent Mode",
  "skill": "Skill",
  "code_executor": "Code Execution",
  "wide_research": "Search"  // Wide research is also a form of search
};

import SearchIcon from '../components/icons/SearchIcon.vue';
import EditIcon from '../components/icons/EditIcon.vue';
import BrowserIcon from '../components/icons/BrowserIcon.vue';
import ShellIcon from '../components/icons/ShellIcon.vue';
import GlobeIcon from '../components/icons/GlobeIcon.vue';
import IdleIcon from '../components/icons/IdleIcon.vue';
import AgentModeIcon from '../components/icons/AgentModeIcon.vue';
import PythonIcon from '../components/icons/PythonIcon.vue';

/**
 * Tool icon mapping - unified search icons like Manus
 */
export const TOOL_ICON_MAP: {[key: string]: any} = {
  "shell": ShellIcon,
  "file": EditIcon,
  "browser": BrowserIcon,
  "browser_agent": GlobeIcon,
  "browsing": GlobeIcon,  // browser-use autonomous browsing
  "search": SearchIcon,   // Unified search icon
  "info": SearchIcon,     // Search/info tools use search icon
  "web_search": SearchIcon,  // Web search uses search icon
  "skill": SearchIcon,
  "message": "",
  "mcp": SearchIcon,  // Using search icon temporarily, can create dedicated MCP icon later
  "idle": IdleIcon,
  "agent_mode": AgentModeIcon,
  "code_executor": PythonIcon,
  "wide_research": SearchIcon  // Wide research is search, use SearchIcon
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
  shell: {
    primaryView: 'terminal',  // Show terminal output directly
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false  // No toggle buttons
  },
  browser: {
    primaryView: 'vnc',  // Show browser in VNC
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
  code_executor: {
    primaryView: 'terminal',  // Show code output directly
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  file: {
    primaryView: 'editor',
    secondaryView: 'editor',
    tertiaryView: 'editor',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  search: {
    primaryView: 'search',  // Show search results directly (Manus-style)
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  info: {
    primaryView: 'search',  // Show search results directly (Manus-style)
    secondaryView: 'vnc',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  mcp: {
    primaryView: 'generic',
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  wide_research: {
    primaryView: 'search',  // Show search results directly (unified search experience)
    secondaryView: 'vnc',   // Can show browser as fallback
    tabLabels: [],
    defaultView: 'primary',
    showTabs: false
  },
  // Alias for web_search tool
  web_search: {
    primaryView: 'search',
    secondaryView: 'vnc',
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
