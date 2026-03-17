import type { ToolContent } from '../types/message';
import { TOOL_FUNCTION_ARG_MAP } from '../constants/tool';

export interface GroupedTool {
  /** Last tool in group (latest state, used for display) */
  tool: ToolContent;
  /** All tools in group */
  tools: ToolContent[];
  /** Group size (1 = ungrouped) */
  count: number;
  /** True if group contains the last tool in the step */
  containsActive: boolean;
  /** First tool's tool_call_id (stable key for v-for) */
  groupKey: string;
}

function getPrimaryArgValue(tool: ToolContent): string {
  const argKey = TOOL_FUNCTION_ARG_MAP[tool.function || ''];
  if (!argKey || !tool.args) return '';
  const val = tool.args[argKey];
  return val != null ? String(val) : '';
}

/**
 * Groups consecutive tools that share the same function AND same primary argument value.
 * Single O(n) pass — safe for 30+ tool lists.
 *
 * The representative tool for each group is the LAST one (most recent state).
 * The groupKey is the FIRST tool's tool_call_id (stable across streaming updates).
 */
export function groupConsecutiveTools(tools: ToolContent[]): GroupedTool[] {
  if (tools.length === 0) return [];

  const groups: GroupedTool[] = [];
  let currentGroup: GroupedTool | null = null;
  let currentFn = '';
  let currentArgVal = '';

  for (const tool of tools) {
    const fn = tool.function || '';
    const argVal = getPrimaryArgValue(tool);

    if (currentGroup && currentFn === fn && currentArgVal === argVal) {
      // Extend current group — update representative to latest tool
      currentGroup.tools.push(tool);
      currentGroup.tool = tool;
      currentGroup.count++;
    } else {
      // Start a new group
      currentGroup = {
        tool,
        tools: [tool],
        count: 1,
        containsActive: false,
        groupKey: tool.tool_call_id || `group-${groups.length}`,
      };
      groups.push(currentGroup);
      currentFn = fn;
      currentArgVal = argVal;
    }
  }

  // The last group contains the active (most recent) tool
  if (groups.length > 0) {
    groups[groups.length - 1].containsActive = true;
  }

  return groups;
}
