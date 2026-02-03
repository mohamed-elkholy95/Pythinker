import { computed, Ref } from 'vue';
import type { ToolContent } from '../types/message';
import { useI18n } from 'vue-i18n';
import { TOOL_ICON_MAP, TOOL_NAME_MAP, TOOL_FUNCTION_MAP, TOOL_FUNCTION_ARG_MAP } from '../constants/tool';

export interface ToolInfo {
  icon: any;
  name: string;
  function: string;
  functionArg: string;
}

/**
 * Format URL for display: "https://example.com/very/long/path" -> "example.com/very/lon..."
 * Manus-style URL formatting
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

export function useToolInfo(tool?: Ref<ToolContent | undefined>) {
  const { t } = useI18n();

  const toolInfo = computed<ToolInfo | null>(() => {
    if (!tool || !tool.value) return null;

    // MCP tool
    if (tool.value.function.startsWith('mcp_')) {
      const mcpToolName = tool.value.function.replace(/^mcp_/, '');
      let functionArg = '';

      const args = tool.value.args;
      if (args && Object.keys(args).length > 0) {
        const firstKey = Object.keys(args)[0];
        const firstValue = args[firstKey];
        if (typeof firstValue === 'string' && firstValue.length < 50) {
          functionArg = firstValue;
        } else if (firstValue !== undefined) {
          functionArg = JSON.stringify(firstValue).substring(0, 30) + '...';
        }
      }

      return {
        icon: TOOL_ICON_MAP['mcp'] || null,
        name: t(TOOL_NAME_MAP['mcp'] || 'MCP Tool'),
        function: mcpToolName,
        functionArg: functionArg
      };
    }

    const argKey = TOOL_FUNCTION_ARG_MAP[tool.value.function];
    let functionArg = tool.value.args[argKey] || '';

    // Format based on argument type - Manus-style standardization
    if (argKey === 'file') {
      // File path: remove /home/ubuntu/ prefix
      functionArg = String(functionArg).replace(/^\/home\/ubuntu\//, '');
    } else if (argKey === 'url') {
      // URL: format as domain + partial path
      functionArg = formatUrl(String(functionArg));
    } else if (argKey === 'command') {
      // Command: truncate to 40 chars
      functionArg = truncate(String(functionArg), 40);
    } else if (argKey === 'query' || argKey === 'topic') {
      // Search query/topic: truncate to 50 chars
      functionArg = truncate(String(functionArg), 50);
    } else if (typeof functionArg === 'string' && functionArg.length > 50) {
      // Generic truncation for other strings
      functionArg = truncate(functionArg, 50);
    }

    return {
      icon: TOOL_ICON_MAP[tool.value.name] || null,
      name: t(TOOL_NAME_MAP[tool.value.name] || ''),
      function: t(TOOL_FUNCTION_MAP[tool.value.function] || tool.value.function),
      functionArg: String(functionArg)
    };
  });

  return {
    toolInfo
  };
} 