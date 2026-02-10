import {
  TOOL_FUNCTION_ARG_MAP,
  TOOL_FUNCTION_MAP,
  TOOL_ICON_MAP,
  TOOL_NAME_MAP
} from '@/constants/tool';
import type { Component } from 'vue';

export interface ToolDisplayInput {
  name?: string;
  function?: string;
  args?: Record<string, unknown>;
  display_command?: string;
}

export interface ToolDisplayInfo {
  toolKey: string;
  displayName: string;
  actionLabel: string;
  resourceLabel: string;
  description: string;
  icon: Component | null;
}

const TOOL_NAME_ALIASES: Record<string, string> = {
  info: 'search',
  info_search_web: 'search',
  web_search: 'search',
  wide_research: 'wide_research',
  code_execute: 'code_executor',
  code_execute_python: 'code_executor',
  code_execute_javascript: 'code_executor',
  browser_agent: 'browser_agent',
  browsing: 'browser_agent'
};

const BROWSER_FUNCTIONS = new Set([
  'go_to_url',
  'click_element',
  'input_text',
  'scroll_down',
  'scroll_up',
  'go_back',
  'wait',
  'extract_content',
  'send_keys',
  'scroll_to_text',
  'get_dropdown_options',
  'select_dropdown_option'
]);

const DEFAULT_ACTION_BY_TOOL: Record<string, string> = {
  search: 'Searching',
  wide_research: 'Searching',
  browser: 'Browsing',
  browser_agent: 'Browsing',
  playwright: 'Browsing',
  file: 'Editing',
  shell: 'Running',
  code_executor: 'Running',
  code_dev: 'Analyzing',
  git: 'Checking',
  test_runner: 'Testing',
  mcp: 'Calling',
  export: 'Exporting',
  slides: 'Creating',
  workspace: 'Organizing',
  schedule: 'Scheduling',
  deep_scan: 'Analyzing',
  agent_mode: 'Switching',
  skill: 'Loading',
  repo_map: 'Mapping',
  message: 'Notifying',
  idle: 'Waiting',
  canvas: 'Designing',
};

function humanize(input: string): string {
  if (!input) return 'Tool';
  return input
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function truncate(value: string, max = 60): string {
  return value.length > max ? `${value.slice(0, max)}...` : value;
}

function formatUrl(url: string, maxLength = 60): string {
  try {
    const u = new URL(url);
    const display = `${u.hostname}${u.pathname}`;
    return display.length > maxLength ? `${display.slice(0, maxLength)}...` : display;
  } catch {
    return truncate(url, maxLength);
  }
}

function formatResource(argKey: string, args?: Record<string, unknown>): string {
  if (!argKey) return '';
  if (!args || args[argKey] === undefined || args[argKey] === null) return '';

  const rawValue = args[argKey];

  if (Array.isArray(rawValue)) {
    const joined = rawValue.map((item) => String(item)).join(', ');
    return truncate(joined, 70);
  }

  let value = String(rawValue);

  if (argKey === 'file' || argKey === 'file_path' || argKey === 'path') {
    value = value.replace(/^\/home\/ubuntu\//, '');
    value = value.replace(/^\/Users\/[^/]+\//, '');
    return truncate(value, 70);
  }

  if (argKey === 'url') {
    return formatUrl(value, 70);
  }

  if (argKey === 'command' || argKey === 'code' || argKey === 'input') {
    return truncate(value, 70);
  }

  if (argKey === 'query' || argKey === 'topic' || argKey === 'task' || argKey === 'text' || argKey === 'selector') {
    return truncate(value, 70);
  }

  return truncate(value, 70);
}

function isNumericOnly(value: string): boolean {
  return /^\d+$/.test(value.trim());
}

function normalizeToolDescription(
  actionLabel: string,
  resourceLabel: string,
  rawDescription?: string
): string {
  const trimmedRaw = rawDescription?.trim();

  // Browser click events often provide only an element index (e.g., "Clicking 16").
  // Keep the label user-friendly in chat chips by hiding bare indices.
  if (trimmedRaw && /^clicking\s+\d+$/i.test(trimmedRaw)) {
    return actionLabel;
  }

  if (actionLabel.toLowerCase() === 'clicking' && isNumericOnly(resourceLabel)) {
    return actionLabel;
  }

  if (trimmedRaw) {
    return truncate(trimmedRaw, 90);
  }

  if (resourceLabel) {
    return `${actionLabel} ${resourceLabel}`;
  }

  return actionLabel;
}

function inferToolKeyFromFunction(functionName: string): string {
  if (!functionName) return '';
  const func = functionName.toLowerCase();

  if (func.startsWith('browser_agent') || func === 'browsing') return 'browser_agent';
  if (func.startsWith('browser_') || func.startsWith('playwright_') || BROWSER_FUNCTIONS.has(func)) return 'browser';

  if (func.includes('search') || func === 'info_search_web') return func === 'wide_research' ? 'wide_research' : 'search';
  if (func.startsWith('wide_research')) return 'wide_research';

  if (func.startsWith('file_')) return 'file';
  if (func.startsWith('shell_')) return 'shell';
  if (func.startsWith('code_')) return 'code_executor';
  if (func.startsWith('git_')) return 'git';
  if (func.startsWith('test_')) return 'test_runner';
  if (func.startsWith('mcp_')) return 'mcp';
  if (func.startsWith('skill_')) return 'skill';
  if (func.startsWith('export')) return 'export';
  if (func.startsWith('slides_')) return 'slides';
  if (func.startsWith('workspace_')) return 'workspace';
  if (func.startsWith('schedule_')) return 'schedule';
  if (func.startsWith('deep_scan')) return 'deep_scan';
  if (func.startsWith('canvas_')) return 'canvas';
  if (func.startsWith('plan_') || func === 'plan') return 'plan';
  if (func.startsWith('agent_mode') || func === 'mode_switch') return 'agent_mode';
  if (func.startsWith('repo_map')) return 'repo_map';
  if (func.startsWith('message_')) return 'message';
  if (func.startsWith('idle')) return 'idle';

  return '';
}

function resolveToolKey(input: ToolDisplayInput): string {
  const rawName = (input.name || '').toLowerCase();
  if (rawName && TOOL_NAME_ALIASES[rawName]) return TOOL_NAME_ALIASES[rawName];
  if (rawName && TOOL_NAME_MAP[rawName]) return rawName;

  const funcKey = inferToolKeyFromFunction(input.function || '');
  if (funcKey) return funcKey;

  return rawName || (input.function || '') || 'tool';
}

/**
 * Extract a URL from tool args, if available.
 */
export function extractToolUrl(args?: Record<string, unknown>): string | null {
  if (!args) return null;
  const url = args.url || args.link || args.href;
  if (typeof url === 'string' && url.startsWith('http')) return url;
  return null;
}

/**
 * Get favicon URL for a domain using DuckDuckGo's favicon service.
 * DuckDuckGo always returns a fallback image for unknown domains,
 * avoiding 404 console errors that Google's service produces.
 */
export function getFaviconUrl(url: string): string | null {
  try {
    const u = new URL(url);
    return `https://icons.duckduckgo.com/ip3/${u.hostname}.ico`;
  } catch {
    return null;
  }
}

export function getToolDisplay(input: ToolDisplayInput): ToolDisplayInfo {
  const toolKey = resolveToolKey(input);
  const displayName = TOOL_NAME_MAP[toolKey] || humanize(toolKey);

  const functionName = input.function || '';
  const actionLabel = TOOL_FUNCTION_MAP[functionName] || DEFAULT_ACTION_BY_TOOL[toolKey] || 'Working';

  const argKey = TOOL_FUNCTION_ARG_MAP[functionName] || '';
  const resourceLabel = formatResource(argKey, input.args);

  const rawDescription = input.display_command;
  const description = normalizeToolDescription(actionLabel, resourceLabel, rawDescription);

  const icon = TOOL_ICON_MAP[toolKey] || TOOL_ICON_MAP[input.name || ''] || TOOL_ICON_MAP['idle'] || null;

  return {
    toolKey,
    displayName,
    actionLabel,
    resourceLabel,
    description,
    icon
  };
}
