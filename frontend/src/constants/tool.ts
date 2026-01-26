/**
 * Tool function mapping - Manus-style verb labels
 */
export const TOOL_FUNCTION_MAP: {[key: string]: string} = {
  // Shell tools
  "shell_exec": "Running",
  "shell_view": "Viewing output",
  "shell_wait": "Waiting",
  "shell_write_to_process": "Writing to process",
  "shell_kill_process": "Terminating",

  // File tools
  "file_read": "Reading",
  "file_write": "Creating file",
  "file_str_replace": "Editing",
  "file_find_in_content": "Searching in",
  "file_find_by_name": "Finding",

  // Browser tools
  "browser_get_content": "Fetching",
  "browser_view": "Viewing",
  "browser_navigate": "Browsing",
  "browser_restart": "Restarting",
  "browser_click": "Clicking",
  "browser_input": "Typing",
  "browser_move_mouse": "Moving mouse",
  "browser_press_key": "Pressing",
  "browser_select_option": "Selecting",
  "browser_scroll_up": "Scrolling up",
  "browser_scroll_down": "Scrolling down",
  "browser_console_exec": "Executing JS",
  "browser_console_view": "Viewing console",

  // Browser Agent tools
  "browser_agent_run": "Running task",
  "browser_agent_extract": "Extracting",

  // Search tools
  "info_search_web": "Searching",

  // Message tools
  "message_notify_user": "Notifying",
  "message_ask_user": "Asking",

  // Idle tool
  "idle_standby": "Standing by",

  // Agent mode tool
  "agent_start_task": "Starting task",

  // Code execution tools
  "code_execute": "Executing code",
  "code_execute_python": "Running Python",
  "code_execute_javascript": "Running JavaScript"
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
  "browser_console_exec": "code",
  "browser_console_view": "console",
  "info_search_web": "query",
  "message_notify_user": "message",
  "message_ask_user": "question",
  "browser_agent_run": "task",
  "browser_agent_extract": "extraction_goal",
  "idle_standby": "reason",
  "agent_start_task": "task",
  "code_execute": "code",
  "code_execute_python": "code",
  "code_execute_javascript": "code"
};

/**
 * Tool name mapping
 */
export const TOOL_NAME_MAP: {[key: string]: string} = {
  "shell": "Terminal",
  "file": "File",
  "browser": "Browser",
  "browser_agent": "Browser Agent",
  "info": "Information",
  "message": "Message",
  "mcp": "MCP Tool",
  "idle": "Standby",
  "agent_mode": "Agent Mode",
  "code_executor": "Code Execution"
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
 * Tool icon mapping
 */
export const TOOL_ICON_MAP: {[key: string]: any} = {
  "shell": ShellIcon,
  "file": EditIcon,
  "browser": BrowserIcon,
  "browser_agent": GlobeIcon,
  "search": SearchIcon,
  "info": SearchIcon,  // Search/info tools use search icon
  "message": "",
  "mcp": SearchIcon,  // Using search icon temporarily, can create dedicated MCP icon later
  "idle": IdleIcon,
  "agent_mode": AgentModeIcon,
  "code_executor": PythonIcon
};

import ShellToolView from '@/components/toolViews/ShellToolView.vue';
import FileToolView from '@/components/toolViews/FileToolView.vue';
import SearchToolView from '@/components/toolViews/SearchToolView.vue';
import BrowserToolView from '@/components/toolViews/BrowserToolView.vue';
import McpToolView from '@/components/toolViews/McpToolView.vue';

/**
 * Mapping from tool names to components
 */
export const TOOL_COMPONENT_MAP: {[key: string]: any} = {
  "shell": ShellToolView,
  "file": FileToolView,
  "search": SearchToolView,
  "browser": BrowserToolView,
  "browser_agent": BrowserToolView,  // Uses browser view to show VNC
  "mcp": McpToolView,
  "code_executor": ShellToolView  // Code execution output shown in terminal view
};
