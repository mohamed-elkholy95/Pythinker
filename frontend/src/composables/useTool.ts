import { computed, Ref } from 'vue';
import type { ToolContent } from '../types/message';
import { useI18n } from 'vue-i18n';
import { TOOL_ICON_MAP, TOOL_NAME_MAP, TOOL_FUNCTION_MAP, TOOL_FUNCTION_ARG_MAP } from '../constants/tool';

export interface ToolInfo {
  icon: any;
  name: string;
  /** Full human-readable description (Manus-style) */
  description: string;
  /** @deprecated Use description instead */
  function: string;
  /** @deprecated Use description instead */
  functionArg: string;
}

/**
 * Format URL for display: "https://example.com/very/long/path" -> "example.com/very/lon..."
 */
function formatUrl(url: string, maxLength = 50): string {
  try {
    const u = new URL(url);
    const display = u.hostname + u.pathname;
    return display.length > maxLength ? display.slice(0, maxLength) + '...' : display;
  } catch {
    return url.length > maxLength ? url.slice(0, maxLength) + '...' : url;
  }
}

/**
 * Truncate string with ellipsis
 */
function truncate(str: string, max: number): string {
  const s = String(str);
  return s.length > max ? s.slice(0, max) + '...' : s;
}

/**
 * Generate human-readable description for tool call (Manus-style)
 * Examples:
 * - "Search for OpenRouter free tier LLM models available for agent tasks"
 * - "Navigate to OpenRouter pricing page to get detailed pricing information"
 * - "Read the full markdown content of the OpenRouter free models page"
 */
function generateDescription(_toolName: string, functionName: string, args: any): string {
  const argKey = TOOL_FUNCTION_ARG_MAP[functionName];
  const argValue = args?.[argKey] || '';

  // Search tools - use full query
  if (functionName.includes('search') || functionName === 'info_search_web') {
    const query = args?.query || args?.topic || '';
    return `Search for ${query}`;
  }

  // Browser navigation
  if (functionName === 'browser_navigate' || functionName === 'go_to_url') {
    const url = args?.url || '';
    const formattedUrl = formatUrl(url, 60);
    return `Navigate to ${formattedUrl}`;
  }

  // Browser view/read
  if (functionName === 'browser_view' || functionName === 'browser_get_content') {
    return 'Read the current page content';
  }

  // Browser click
  if (functionName === 'browser_click' || functionName === 'click_element') {
    const element = args?.index !== undefined ? `element ${args.index}` : (args?.selector || 'element');
    return `Click on ${element}`;
  }

  // Browser input/type
  if (functionName === 'browser_input' || functionName === 'input_text') {
    const text = truncate(args?.text || '', 40);
    return `Type "${text}"`;
  }

  // Browser scroll
  if (functionName.includes('scroll')) {
    const direction = functionName.includes('down') ? 'down' : (functionName.includes('up') ? 'up' : '');
    return `Scroll ${direction} to see more content`;
  }

  // File read
  if (functionName === 'file_read') {
    const file = (args?.file || '').replace(/^\/home\/ubuntu\//, '');
    return `Read the full content of ${file}`;
  }

  // File write
  if (functionName === 'file_write') {
    const file = (args?.file || '').replace(/^\/home\/ubuntu\//, '');
    return `Save content to ${file}`;
  }

  // File edit/replace
  if (functionName === 'file_str_replace') {
    const file = (args?.file || '').replace(/^\/home\/ubuntu\//, '');
    return `Edit ${file}`;
  }

  // Shell exec
  if (functionName === 'shell_exec') {
    const command = truncate(args?.command || '', 60);
    return command;
  }

  // Git operations
  if (functionName.startsWith('git_')) {
    const operation = functionName.replace('git_', '');
    const repoPath = args?.repo_path || args?.path || '';
    const repoName = repoPath.split('/').pop() || 'repository';

    if (operation === 'clone') {
      return `Clone repository from ${args?.url || ''}`;
    }
    if (operation === 'status') {
      return `Check git status of ${repoName}`;
    }
    if (operation === 'diff') {
      return `View changes in ${repoName}`;
    }
    return `Git ${operation} on ${repoName}`;
  }

  // Code execution
  if (functionName.includes('code_execute') || functionName === 'code_run_file') {
    const filePath = args?.file_path;
    if (filePath) {
      const fileName = filePath.split('/').pop();
      return `Run ${fileName}`;
    }
    const language = args?.language || 'code';
    return `Execute ${language} code`;
  }

  // Test runner
  if (functionName.startsWith('test_')) {
    const testPath = args?.test_path || args?.file_path || args?.suite_name || '';
    const testName = testPath.split('/').pop() || 'tests';
    return `Run tests: ${testName}`;
  }

  // MCP tools
  if (functionName.startsWith('mcp_')) {
    const mcpToolName = functionName.replace(/^mcp_/, '').replace(/_/g, ' ');
    return `Using extension: ${mcpToolName}`;
  }

  // Message tools
  if (functionName === 'message_notify_user') {
    return truncate(args?.text || 'Notification', 60);
  }
  if (functionName === 'message_ask_user') {
    return truncate(args?.text || 'Question', 60);
  }

  // Wide research
  if (functionName === 'wide_research') {
    const topic = args?.topic || '';
    return `Deep research on "${topic}"`;
  }

  // Fallback: verb + arg
  const verb = TOOL_FUNCTION_MAP[functionName] || functionName;
  const arg = typeof argValue === 'string' ? truncate(argValue, 40) : '';
  return arg ? `${verb} ${arg}` : verb;
}

export function useToolInfo(tool?: Ref<ToolContent | undefined>) {
  const { t } = useI18n();

  const toolInfo = computed<ToolInfo | null>(() => {
    if (!tool || !tool.value) return null;

    const toolValue = tool.value;

    // Use display_command from backend if available (Manus-style)
    let description = toolValue.display_command || '';

    // If no display_command, generate one
    if (!description) {
      description = generateDescription(toolValue.name, toolValue.function, toolValue.args);
    }

    // Get icon and name
    let icon = TOOL_ICON_MAP[toolValue.name];
    let name = TOOL_NAME_MAP[toolValue.name] || '';

    // Handle MCP tools specially
    if (toolValue.function.startsWith('mcp_')) {
      icon = TOOL_ICON_MAP['mcp'];
      name = TOOL_NAME_MAP['mcp'] || 'Extension';
    }

    // Legacy support: extract verb and arg for backward compatibility
    const argKey = TOOL_FUNCTION_ARG_MAP[toolValue.function];
    let functionArg = toolValue.args?.[argKey] || '';

    // Format based on argument type
    if (argKey === 'file') {
      functionArg = String(functionArg).replace(/^\/home\/ubuntu\//, '');
    } else if (argKey === 'url') {
      functionArg = formatUrl(String(functionArg));
    } else if (typeof functionArg === 'string' && functionArg.length > 50) {
      functionArg = truncate(functionArg, 50);
    }

    return {
      icon: icon || null,
      name: t(name),
      description: description,
      // Legacy fields for backward compatibility
      function: t(TOOL_FUNCTION_MAP[toolValue.function] || toolValue.function),
      functionArg: String(functionArg)
    };
  });

  return {
    toolInfo
  };
}
