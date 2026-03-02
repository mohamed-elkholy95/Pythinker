import type { SearchResultItem } from './search';

export interface ToolContentBase {
  [key: string]: unknown;
}

export interface BrowserToolContent extends ToolContentBase {
  screenshot?: string | null;
  content?: string | null;
}

export interface SearchToolContent extends ToolContentBase {
  results: SearchResultItem[];
  query?: string;
  date_range?: string | null;
  total_results?: number;
  provider?: string | null;
  search_depth?: string | null;
  credits_used?: number | null;
  intent_tier?: string | null;
}

export interface ShellToolContent extends ToolContentBase {
  console: unknown;
  stdout?: string;
  stderr?: string;
  exit_code?: number;
}

export interface FileToolContent extends ToolContentBase {
  content: string;
}

export interface McpToolContent extends ToolContentBase {
  result: unknown;
}

export interface BrowserAgentToolContent extends ToolContentBase {
  result: unknown;
  steps_taken?: number;
}

export interface GitToolContent extends ToolContentBase {
  operation: string;
  output?: string | null;
  repo_path?: string | null;
  branch?: string | null;
  commits?: Array<Record<string, unknown>> | null;
  diff_content?: string | null;
}

export interface CodeExecutorToolContent extends ToolContentBase {
  language: string;
  code?: string | null;
  output?: string | null;
  error?: string | null;
  exit_code?: number | null;
  execution_time_ms?: number | null;
  artifacts?: Array<Record<string, unknown>> | null;
}

export interface PlaywrightToolContent extends ToolContentBase {
  browser_type?: string | null;
  url?: string | null;
  screenshot?: string | null;
  content?: string | null;
}

export interface TestRunnerToolContent extends ToolContentBase {
  framework?: string | null;
  total_tests?: number;
  passed?: number;
  failed?: number;
  skipped?: number;
  output?: string | null;
  duration_ms?: number | null;
}

export interface SkillToolContent extends ToolContentBase {
  skill_id?: string | null;
  skill_name?: string | null;
  operation: string;
  result?: unknown;
  status?: string | null;
}

export interface ExportToolContent extends ToolContentBase {
  format?: string | null;
  filename?: string | null;
  size_bytes?: number | null;
  path?: string | null;
}

export interface SlidesToolContent extends ToolContentBase {
  title?: string | null;
  slide_count?: number;
  format?: string | null;
  path?: string | null;
}

export interface WorkspaceToolContent extends ToolContentBase {
  action: string;
  workspace_type?: string | null;
  files_count?: number;
  structure?: Record<string, unknown> | null;
}

export interface ScheduleToolContent extends ToolContentBase {
  action: string;
  schedule_id?: string | null;
  schedule_time?: string | null;
  status?: string | null;
}

export interface DeepScanToolContent extends ToolContentBase {
  scan_type?: string | null;
  findings_count?: number;
  summary?: string | null;
  details?: Array<Record<string, unknown>> | null;
}

export interface AgentModeToolContent extends ToolContentBase {
  mode: string;
  previous_mode?: string | null;
  reason?: string | null;
}

export interface CodeDevToolContent extends ToolContentBase {
  operation: string;
  file_path?: string | null;
  result?: string | null;
  suggestions?: string[] | null;
}

export interface CanvasToolContent extends ToolContentBase {
  operation: string;
  project_id?: string | null;
  project_name?: string | null;
  element_count?: number;
  image_urls?: string[] | null;
}

export interface PlanToolContent extends ToolContentBase {
  operation: string;
  plan_id?: string | null;
  steps_count?: number;
}

export interface RepoMapToolContent extends ToolContentBase {
  repo_path?: string | null;
  files_count?: number;
  structure?: Record<string, unknown> | null;
}

export interface ChartToolContent extends ToolContentBase {
  chart_type: string;
  title: string;
  html_file_id?: string | null;
  png_file_id?: string | null;
  html_filename?: string | null;
  png_filename?: string | null;
  html_size?: number;
  data_points?: number;
  series_count?: number;
  execution_time_ms?: number | null;
  error?: string | null;
}

export interface DealItem {
  store: string;
  price: number | null;
  original_price: number | null;
  discount_percent: number | null;
  product_name: string;
  url: string;
  score: number | null;
  in_stock: boolean | null;
  coupon_code: string | null;
  image_url: string | null;
}

export interface CouponItem {
  code: string;
  description: string;
  store: string;
  expiry: string | null;
  verified: boolean;
  source: string;
}

export interface StoreError {
  store: string;
  error: string;
}

export type DealEmptyReason = 'no_matches' | 'all_store_failures' | 'search_unavailable';

export interface DealToolContent extends ToolContentBase {
  deals: DealItem[];
  coupons: CouponItem[];
  query: string;
  best_deal_index: number | null;
  searched_stores?: string[];
  store_errors?: StoreError[];
  empty_reason?: DealEmptyReason;
  stores_attempted?: number;
  stores_with_results?: number;
}

// ── Deal Progress (live view checkpoint_data) ──

export type DealStoreStatusKind = 'pending' | 'found' | 'failed' | 'empty';

export interface StoreStatus {
  store: string;
  status: DealStoreStatusKind;
  result_count: number;
}

export interface DealProgressData {
  store_statuses: StoreStatus[];
  partial_deals: Partial<DealItem>[];
  query: string;
}

export type ToolContentPayload =
  | BrowserToolContent
  | SearchToolContent
  | ShellToolContent
  | FileToolContent
  | McpToolContent
  | BrowserAgentToolContent
  | GitToolContent
  | CodeExecutorToolContent
  | PlaywrightToolContent
  | TestRunnerToolContent
  | SkillToolContent
  | ExportToolContent
  | SlidesToolContent
  | WorkspaceToolContent
  | ScheduleToolContent
  | DeepScanToolContent
  | AgentModeToolContent
  | CodeDevToolContent
  | CanvasToolContent
  | PlanToolContent
  | RepoMapToolContent
  | ChartToolContent
  | DealToolContent;
