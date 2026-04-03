import {
  FUNCTION_ICON_MAP,
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

export interface ToolLiveLabelInput {
  current_step?: string;
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
  terminal: 'shell',
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
  chart: 'Creating chart',
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

function normalizeLiveLabel(value: string): string {
  return truncate(cleanDisplayText(value.trim()), 90);
}

function isPlaceholderValue(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return normalized === 'undefined' || normalized === 'null' || normalized === 'none' || normalized === 'nan';
}

export function cleanDisplayText(value: string): string {
  return value
    .replace(/^\s*(?:undefined|null|none|nan)\s*$/i, '')
    .replace(/\s+\|\s*(?:undefined|null|none|nan)\s*$/i, '')
    .replace(/\s+(?:undefined|null|none|nan)\s*$/i, '')
    .replace(/^\s*(?:undefined|null|none|nan)\s*\|\s*/i, '')
    .replace(/\s{2,}/g, ' ')
    .replace(/\s+\|\s+/g, ' | ')
    .replace(/\s+\|\s*$/g, '')
    .trim();
}

/**
 * Prefer the concrete runtime step text when available, then fall back to
 * the human-readable display command. Returns an empty string when neither
 * is useful.
 */
export function getToolLiveLabel(input: ToolLiveLabelInput): string {
  const currentStep = normalizeLiveLabel(input.current_step ?? '');
  if (currentStep) return currentStep;

  const displayCommand = normalizeLiveLabel(input.display_command ?? '');
  if (displayCommand) return displayCommand;

  return '';
}

/**
 * Strip non-ASCII characters from path-like or URL-like strings.
 * Some LLM providers (e.g. MiniMax M2.7) inject CJK characters into
 * tool call arguments meant to be file paths, URLs, or resource IDs,
 * producing garbled display text like "ev保存://trs-162a26da4366".
 */
function sanitizePathLike(value: string): string {
  // eslint-disable-next-line no-control-regex
  return value.replace(/[^\x00-\x7F]+/g, '').replace(/\/{3,}/g, '//').replace(/\s{2,}/g, ' ').trim();
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
    const joined = rawValue
      .map((item) => String(item).trim())
      .filter((item) => item.length > 0 && !isPlaceholderValue(item))
      .join(', ');
    if (!joined) return '';
    return truncate(joined, 70);
  }

  let value = String(rawValue).trim();
  if (!value || isPlaceholderValue(value)) return '';
  value = cleanDisplayText(value);
  if (!value) return '';

  if (argKey === 'file' || argKey === 'file_path' || argKey === 'path') {
    value = sanitizePathLike(value);
    value = value.replace(/^\/home\/ubuntu\//, '');
    value = value.replace(/^\/Users\/[^/]+\//, '');
    return truncate(value, 70);
  }

  if (argKey === 'url') {
    return formatUrl(sanitizePathLike(value), 70);
  }

  if (argKey === 'uri') {
    return truncate(sanitizePathLike(value), 70);
  }

  if (argKey === 'skill_name') {
    return `"${truncate(value, 66)}"`;
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
  const trimmedRaw = cleanDisplayText(rawDescription?.trim() || '');

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

  if (func === 'terminal' || func.startsWith('terminal_')) return 'shell';
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

// ── Favicon persistent cache ────────────────────────────────────────────
// Persists failed hostnames to localStorage so the same domain never
// triggers a 404 console error more than once across sessions.

const FAVICON_STORAGE_KEY = 'pythinker:failed-favicons';
const FAVICON_CACHE_EXPIRY_MS = 7 * 24 * 60 * 60 * 1000; // 7 days
const FAVICON_MAX_ENTRIES = 500;

/** In-memory mirror of the localStorage cache. hostname → failure timestamp. */
const failedFaviconHosts = new Map<string, number>();
let _faviconCacheInitialized = false;

function _initFaviconCache(): void {
  if (_faviconCacheInitialized) return;
  _faviconCacheInitialized = true;
  try {
    const raw = localStorage.getItem(FAVICON_STORAGE_KEY);
    if (!raw) return;
    const entries: Record<string, number> = JSON.parse(raw);
    const now = Date.now();
    for (const [host, ts] of Object.entries(entries)) {
      if (now - ts < FAVICON_CACHE_EXPIRY_MS) {
        failedFaviconHosts.set(host, ts);
      }
    }
  } catch { /* corrupt/missing storage — start fresh */ }
}

function _persistFaviconCache(): void {
  try {
    // Evict oldest entries if over limit
    const entries = [...failedFaviconHosts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, FAVICON_MAX_ENTRIES);
    const obj: Record<string, number> = {};
    for (const [host, ts] of entries) obj[host] = ts;
    localStorage.setItem(FAVICON_STORAGE_KEY, JSON.stringify(obj));
  } catch { /* storage full or disabled — degrade gracefully */ }
}

// Batch persist: debounce writes so rapid failures don't hammer localStorage
let _persistTimer: ReturnType<typeof setTimeout> | null = null;
function _schedulePersist(): void {
  if (_persistTimer) return;
  _persistTimer = setTimeout(() => {
    _persistTimer = null;
    _persistFaviconCache();
  }, 1000);
}

/** Normalize a URL to its bare hostname (no www. prefix). */
export function normalizeHostname(url: string): string | null {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

/**
 * Pre-filter hostnames unlikely to have favicons.
 * Skips: IP addresses, localhost, single-label hosts, internal TLDs.
 */
function _isUnlikelyToHaveFavicon(hostname: string): boolean {
  // IPv4
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(hostname)) return true;
  // IPv6 (bracketed or raw)
  if (hostname.startsWith('[') || hostname.includes(':')) return true;
  // localhost / single-label (no dot)
  if (!hostname.includes('.')) return true;
  // Internal/private TLDs
  if (/\.(local|internal|localhost|test|invalid|example)$/i.test(hostname)) return true;
  return false;
}

/** Check whether a hostname is known to have a failed favicon. */
export function isFaviconFailed(url: string): boolean {
  _initFaviconCache();
  const hostname = normalizeHostname(url);
  if (!hostname) return true;
  if (_isUnlikelyToHaveFavicon(hostname)) return true;
  return failedFaviconHosts.has(hostname);
}

/**
 * Get favicon URL for a domain using DuckDuckGo's favicon service.
 * Returns null if the hostname is pre-filtered or previously failed,
 * preventing the browser from making a request that would 404.
 */
export function getFaviconUrl(url: string): string | null {
  _initFaviconCache();
  const hostname = normalizeHostname(url);
  if (!hostname) return null;
  if (_isUnlikelyToHaveFavicon(hostname)) return null;
  if (failedFaviconHosts.has(hostname)) return null;
  return `https://icons.duckduckgo.com/ip3/${hostname}.ico`;
}

/**
 * Mark a URL's hostname as having a failed favicon.
 * Persists to localStorage so the failure survives page reloads.
 */
export function markFaviconFailed(url: string): void {
  _initFaviconCache();
  const hostname = normalizeHostname(url);
  if (!hostname) return;
  failedFaviconHosts.set(hostname, Date.now());
  _schedulePersist();
}

/** Well-known domain → letter mappings for favicon fallbacks. */
const ICON_LETTER_MAP: [test: string, letter: string][] = [
  ['wikipedia', 'W'],
  ['github', 'G'],
  ['stackoverflow', 'S'],
  ['reddit', 'R'],
  ['youtube', 'Y'],
  ['twitter', 'X'],
  ['x.com', 'X'],
  ['linkedin', 'in'],
  ['medium', 'M'],
];

/** Get a short letter icon for a URL (for favicon fallbacks). */
export function getIconLetterFromUrl(url: string, title?: string): string {
  try {
    const hostname = new URL(url).hostname.replace(/^www\./, '');
    for (const [test, letter] of ICON_LETTER_MAP) {
      if (hostname.includes(test)) return letter;
    }
    return hostname.charAt(0).toUpperCase();
  } catch {
    return title?.charAt(0).toUpperCase() || '?';
  }
}

export function getToolDisplay(input: ToolDisplayInput): ToolDisplayInfo {
  const toolKey = resolveToolKey(input);
  const displayName = TOOL_NAME_MAP[toolKey] || humanize(toolKey);

  const functionName = input.function || '';
  const isBrowserFamilyTool =
    toolKey === 'browser'
    || toolKey === 'browser_agent'
    || toolKey === 'playwright'
    || functionName.startsWith('browser_')
    || functionName.startsWith('playwright_')
    || BROWSER_FUNCTIONS.has(functionName)
    || displayName.toLowerCase().includes('browser');
  const actionLabel =
    TOOL_FUNCTION_MAP[functionName]
    || DEFAULT_ACTION_BY_TOOL[toolKey]
    || (isBrowserFamilyTool ? 'Browsing' : 'Working');

  const argKey = TOOL_FUNCTION_ARG_MAP[functionName] || '';
  const resourceLabel = formatResource(argKey, input.args);

  const rawDescription = input.display_command;
  const description = normalizeToolDescription(actionLabel, resourceLabel, rawDescription);

  const icon = FUNCTION_ICON_MAP[functionName] || TOOL_ICON_MAP[toolKey] || TOOL_ICON_MAP[input.name || ''] || TOOL_ICON_MAP['idle'] || null;

  return {
    toolKey,
    displayName,
    actionLabel,
    resourceLabel,
    description,
    icon
  };
}
