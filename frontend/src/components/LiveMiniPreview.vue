<template>
  <div
    class="live-mini-preview"
    :class="sizeClass"
    @click="emit('click')"
  >
    <!-- ============================================================
         Scaled viewport — only for browser screencast / live views
         Renders at 355x284 then CSS-scaled to fit container
         ============================================================ -->
    <div v-if="useScaledViewport" class="mini-viewport">

      <!-- Initializing state -->
      <div v-if="isInitializing" class="vp-centered">
        <div class="init-monitor">
          <div class="monitor-frame">
            <div class="monitor-screen">
              <div class="scan-line"></div>
              <div class="boot-dots">
                <span class="boot-dot"></span>
                <span class="boot-dot"></span>
                <span class="boot-dot"></span>
              </div>
            </div>
            <div class="monitor-stand"></div>
          </div>
        </div>
        <span class="init-label">Initializing<span class="init-ellipsis"></span></span>
      </div>

      <!-- Wide Research view -->
      <WideResearchMiniPreview
        v-else-if="isWideResearch && wideResearchState"
        :state="wideResearchState"
        :is-active="isActive"
      />

      <!-- Terminal running without content — live preview -->
      <div v-else-if="currentViewType === 'terminal' && isActive && sessionId && enabled && !contentPreview" class="vp-live">
        <LiveViewer
          :session-id="sessionId"
          :enabled="enabled"
          :view-only="true"
          :compact-loading="true"
          :show-controls="false"
        />
      </div>

      <!-- Live preview (active or completed session without report) -->
      <div v-else-if="shouldShowLivePreview" class="vp-live">
        <LiveViewer
          ref="liveViewerRef"
          :session-id="sessionId"
          :enabled="enabled"
          :view-only="true"
          :compact-loading="true"
          :show-controls="false"
          :is-session-complete="isSessionComplete"
          :replay-screenshot-url="replayScreenshotUrl || ''"
        />
      </div>

      <!-- Fallback inside scaled viewport (shouldn't normally appear) -->
      <div v-else class="vp-centered">
        <component :is="toolIcon" :size="32" class="fallback-icon" />
        <span class="fallback-label">{{ toolLabel }}</span>
        <div v-if="isActive" class="activity-dot activity-dot-abs"></div>
      </div>

    </div>

    <!-- ============================================================
         Direct-render panels — text content at actual container size
         No scale transform, proper mini typography
         ============================================================ -->
    <div v-else class="dc-wrapper">

      <!-- Summary / report preview -->
      <div v-if="isSummaryPhase" class="dc-panel">
        <div class="dc-header">
          <span class="dc-header-title">{{ streamingPresentation.headline.value }}</span>
        </div>
        <div class="dc-body">
          <div v-if="reportPreviewText" class="dc-md-text">
            <div class="dc-mini-md" v-html="renderedMiniMarkdown"></div>
          </div>
          <div v-else class="dc-skeleton-lines">
            <div class="skeleton-line" v-for="n in 5" :key="n" :style="{ animationDelay: `${n * 0.15}s`, width: `${60 + (n * 7)}%` }"></div>
          </div>
        </div>
        <div v-if="isSummaryStreaming" class="activity-dot"></div>
      </div>

      <!-- Planning preview -->
      <div v-else-if="isPlanningPhase" class="dc-panel">
        <div class="dc-header">
          <span class="dc-header-title">{{ streamingPresentation.headline.value }}</span>
        </div>
        <div class="dc-body">
          <div v-if="props.planPresentationText" class="dc-md-text">
            <div class="dc-mini-md" v-html="renderedMiniMarkdown"></div>
          </div>
          <div v-else class="dc-skeleton-lines">
            <div class="skeleton-line" v-for="n in 5" :key="n" :style="{ animationDelay: `${n * 0.15}s`, width: `${60 + (n * 7)}%` }"></div>
          </div>
        </div>
        <div v-if="isPlanStreaming" class="activity-dot"></div>
      </div>

      <!-- Terminal view -->
      <div v-else-if="currentViewType === 'terminal' && contentPreview" class="dc-panel">
        <div class="dc-header">
          <span class="dc-header-title">{{ terminalTitle }}</span>
        </div>
        <div class="dc-body dc-body-terminal">
          <pre class="dc-terminal-text" v-html="styledTerminalContent"></pre>
        </div>
        <div v-if="isActive" class="activity-dot"></div>
      </div>

      <!-- Search results -->
      <div v-else-if="currentViewType === 'search'" class="dc-panel">
        <div class="dc-header">
          <span class="dc-header-title">{{ truncate(searchQuery || 'Search', 30) }}</span>
        </div>
        <div class="dc-body dc-body-search">
          <div v-if="searchResults.length > 0" class="search-results-list">
            <div v-for="(result, idx) in searchResults.slice(0, 4)" :key="idx" class="search-result-row">
              <img
                v-if="(result.url || result.link) && !faviconErrors[result.url ?? result.link ?? '']"
                :src="getFavicon(result.url ?? result.link ?? '')"
                alt=""
                class="sr-favicon"
                @error="onFaviconError(result.url ?? result.link ?? '')"
              />
              <span v-else class="sr-favicon-fallback">{{ getIconLetterFromUrl(result.url ?? result.link ?? '', result.title) }}</span>
              <div class="sr-text">
                <span class="sr-title">{{ truncate(result.title || result.name || 'Result', 40) }}</span>
                <span v-if="result.snippet" class="sr-snippet">{{ truncate(result.snippet, 60) }}</span>
              </div>
            </div>
          </div>
          <div v-else-if="isActive" class="dc-centered">
            <div class="loading-dots">
              <span class="dot"></span>
              <span class="dot"></span>
              <span class="dot"></span>
            </div>
            <span class="loading-label">Searching...</span>
          </div>
          <div v-else class="dc-centered">
            <Search :size="16" class="empty-icon" />
            <span class="empty-label">No results</span>
          </div>
        </div>
        <div v-if="isActive" class="activity-dot"></div>
      </div>

      <!-- Editor view -->
      <div v-else-if="currentViewType === 'editor' && contentPreview" class="dc-panel">
        <div class="dc-header">
          <span class="dc-header-title">{{ fileName }}</span>
        </div>
        <div class="dc-body dc-body-code">
          <pre class="dc-code-text">{{ contentPreview }}</pre>
        </div>
        <div v-if="isActive" class="activity-dot"></div>
      </div>

      <!-- Chart view -->
      <div v-else-if="currentViewType === 'chart'" class="dc-panel">
        <div class="dc-header">
          <BarChart3 :size="11" class="dc-header-icon" />
          <span class="dc-header-title">{{ chartTitle }}</span>
        </div>
        <div class="dc-body dc-body-chart">
          <img
            v-if="chartPngUrl"
            :src="chartPngUrl"
            alt="Chart"
            class="chart-image"
          />
          <div v-else-if="isActive" class="dc-centered">
            <div class="chart-bars">
              <div class="bar bar-1"></div>
              <div class="bar bar-2"></div>
              <div class="bar bar-3"></div>
            </div>
            <span class="loading-label">Generating...</span>
          </div>
          <div v-else class="dc-centered">
            <BarChart3 :size="20" class="empty-icon" />
          </div>
        </div>
        <div v-if="isActive" class="activity-dot"></div>
      </div>

      <!-- Session complete with report text -->
      <div v-else-if="shouldShowFinalScreenshot && reportPreviewText" class="dc-panel">
        <div class="dc-header">
          <span class="dc-header-title">Report</span>
        </div>
        <div class="dc-body">
          <div class="dc-md-text">
            <div class="dc-mini-md" v-html="renderedMiniMarkdown"></div>
          </div>
        </div>
      </div>

      <!-- Generic tool indicator (fallback) -->
      <div v-else class="dc-centered dc-centered-full">
        <component :is="toolIcon" :size="24" class="fallback-icon" />
        <span class="fallback-label">{{ toolLabel }}</span>
        <div v-if="showInitializingDots" class="loading-dots" aria-hidden="true">
          <span class="dot"></span>
          <span class="dot"></span>
          <span class="dot"></span>
        </div>
        <div v-if="isActive" class="activity-dot activity-dot-abs"></div>
      </div>

    </div>

    <!-- Hover expand button (outside viewport so it's not scaled) -->
    <button class="hover-expand-btn">
      <Monitor :size="16" class="expand-icon" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, toRef, watch } from 'vue';
import { Monitor, Terminal, FileText, Globe, Code, Wrench, Search, GitBranch, TestTube, Wand2, Download, Presentation, FolderTree, Calendar, Scan, BarChart3 } from 'lucide-vue-next';
import LiveViewer from '@/components/LiveViewer.vue';
import WideResearchMiniPreview from '@/components/WideResearchMiniPreview.vue';
import { useContentConfig } from '@/composables/useContentConfig';
import { useStreamingPresentationState } from '@/composables/useStreamingPresentationState';
import { useWideResearchGlobal } from '@/composables/useWideResearch';
import { getFaviconUrl, getToolDisplay, markFaviconFailed, getIconLetterFromUrl } from '@/utils/toolDisplay';
import { fileApi } from '@/api/file';
import type { ToolContent } from '@/types/message';
import type { ToolEventData } from '@/types/event';

const props = withDefaults(defineProps<{
  sessionId?: string;
  enabled?: boolean;
  size?: 'sm' | 'md' | 'lg';
  toolName?: string;
  toolFunction?: string;
  isActive?: boolean;
  /** Content to preview (file content, terminal output, etc.) */
  contentPreview?: string;
  /** File path for file operations */
  filePath?: string;
  /** Whether the sandbox environment is initializing */
  isInitializing?: boolean;
  /** Search results for search/info tools */
  searchResults?: Array<{ title?: string; name?: string; url?: string; link?: string; snippet?: string }>;
  /** Search query for search/info tools */
  searchQuery?: string;
  /** Full tool content for content config */
  toolContent?: ToolContent;
  /** Whether summary is currently streaming */
  isSummaryStreaming?: boolean;
  /** Buffered summary stream text */
  summaryStreamText?: string;
  /** Persisted final report content shown after summary streaming ends */
  finalReportText?: string;
  /** Whether session has completed and should show replay frame when idle */
  isSessionComplete?: boolean;
  /** Replay frame URL provided by parent composable */
  replayScreenshotUrl?: string;
  /** Plan presentation text for planning mini preview */
  planPresentationText?: string;
  /** Whether plan is actively streaming */
  isPlanStreaming?: boolean;
}>(), {
  enabled: true,
  size: 'md',
  toolName: '',
  toolFunction: '',
  isActive: false,
  contentPreview: '',
  filePath: '',
  isInitializing: false,
  searchResults: () => [],
  searchQuery: '',
  toolContent: undefined,
  isSummaryStreaming: false,
  summaryStreamText: '',
  finalReportText: '',
  isSessionComplete: false,
  replayScreenshotUrl: '',
  planPresentationText: '',
  isPlanStreaming: false
});

const emit = defineEmits<{
  click: [];
}>();

// ---------------------------------------------------------------------------
// Agent cursor forwarding — forward tool events to the LiveViewer so the
// Konva cursor overlay can track the agent's pointer during browsing.
// ---------------------------------------------------------------------------

const liveViewerRef = ref<{ processToolEvent?: (event: ToolEventData) => void } | null>(null);

let _lastForwardedKey = '';

function forwardToolEventToLiveViewer(): void {
  if (!props.sessionId || !liveViewerRef.value?.processToolEvent) return;

  const tool = props.toolContent;
  if (!tool?.tool_call_id || !tool.function || !tool.status) return;

  const args = tool.args || {};
  const eventKey = JSON.stringify([
    tool.tool_call_id,
    tool.status,
    tool.function,
    args.coordinate_x,
    args.coordinate_y,
    args.x,
    args.y,
  ]);
  if (eventKey === _lastForwardedKey) return;
  _lastForwardedKey = eventKey;

  liveViewerRef.value.processToolEvent({
    event_id: tool.event_id || tool.tool_call_id,
    timestamp: tool.timestamp || Math.floor(Date.now() / 1000),
    tool_call_id: tool.tool_call_id,
    name: tool.name,
    status: tool.status === 'interrupted' ? 'called' : tool.status,
    function: tool.function,
    args: tool.args || {},
  });
}

watch(liveViewerRef, () => {
  forwardToolEventToLiveViewer();
});

watch(
  () => [
    props.toolContent?.tool_call_id,
    props.toolContent?.status,
    props.toolContent?.args?.coordinate_x,
    props.toolContent?.args?.coordinate_y,
  ],
  () => {
    forwardToolEventToLiveViewer();
  },
);

// Build a minimal toolContent object if not provided
const effectiveToolContent = computed<ToolContent | undefined>(() => {
  if (props.toolContent) return props.toolContent;
  if (!props.toolName) return undefined;
  return {
    name: props.toolName,
    function: props.toolFunction,
    args: {},
    content: undefined,
    status: props.isActive ? 'calling' : 'completed'
  } as ToolContent;
});

const toolDisplay = computed(() => {
  if (!effectiveToolContent.value) return null;
  return getToolDisplay({
    name: effectiveToolContent.value.name,
    function: effectiveToolContent.value.function,
    args: effectiveToolContent.value.args,
    display_command: effectiveToolContent.value.display_command
  });
});

// Use content config to determine view type
const { currentViewType } = useContentConfig(toRef(() => effectiveToolContent.value));

const baseViewTypeForPresentation = computed(() => {
  if (currentViewType.value === 'terminal' || currentViewType.value === 'editor' || currentViewType.value === 'search') {
    return currentViewType.value;
  }
  if (currentViewType.value === 'live_preview') {
    return 'live_preview';
  }
  return 'generic';
});

const streamingPresentation = useStreamingPresentationState({
  isInitializing: computed(() => !!props.isInitializing),
  isSummaryStreaming: computed(() => !!props.isSummaryStreaming),
  summaryStreamText: computed(() => props.summaryStreamText || ''),
  finalReportText: computed(() => props.finalReportText || ''),
  isThinking: computed(() => false),
  isActiveOperation: computed(() => !!props.isActive),
  isPlanStreaming: computed(() => !!props.isPlanStreaming),
  planPresentationText: computed(() => props.planPresentationText || ''),
  toolDisplayName: computed(() => toolDisplay.value?.displayName || props.toolName || ''),
  toolDescription: computed(() => toolDisplay.value?.description || ''),
  baseViewType: computed(() => baseViewTypeForPresentation.value),
  isSessionComplete: computed(() => !!props.isSessionComplete),
  replayScreenshotUrl: computed(() => props.replayScreenshotUrl || ''),
  previewText: computed(() => props.contentPreview || '')
});

const isSummaryPhase = computed(() => streamingPresentation.isSummaryPhase.value);
const isPlanningPhase = computed(() => streamingPresentation.isPlanningPhase.value);

// Actual report text for the mini preview — prefer final over streaming
const reportPreviewText = computed(() => {
  const final = props.finalReportText || '';
  if (final.length > 0) return final;
  const stream = props.summaryStreamText || '';
  if (stream.length > 0) return stream;
  return '';
});

/**
 * Lightweight markdown → HTML for mini preview.
 * Renders headings, code blocks, bold, italic, lists, and horizontal rules.
 */
const renderedMiniMarkdown = computed(() => {
  const raw = isPlanningPhase.value ? (props.planPresentationText || '') : reportPreviewText.value;
  if (!raw) return '';

  const escaped = raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  const lines = escaped.split('\n');
  const html: string[] = [];
  let inCode = false;
  let codeLines: string[] = [];
  let codeLang = '';

  for (const line of lines) {
    if (line.startsWith('```')) {
      if (!inCode) {
        inCode = true;
        codeLang = line.slice(3).trim();
        codeLines = [];
      } else {
        if (codeLang === 'mermaid' || codeLang === 'chart' || codeLang === 'plotly') {
          inCode = false;
          codeLang = '';
          continue;
        }
        const langBadge = codeLang
          ? `<span class="mini-code-lang">${codeLang}</span>`
          : '';
        html.push(
          `<div class="mini-code-block">${langBadge}<pre>${codeLines.join('\n')}</pre></div>`
        );
        inCode = false;
        codeLang = '';
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (line.startsWith('### ')) {
      html.push(`<div class="mini-h3">${inlineFormat(line.slice(4))}</div>`);
    } else if (line.startsWith('## ')) {
      html.push(`<div class="mini-h2">${inlineFormat(line.slice(3))}</div>`);
    } else if (line.startsWith('# ')) {
      html.push(`<div class="mini-h1">${inlineFormat(line.slice(2))}</div>`);
    }
    else if (/^\|[\s:|-]+\|$/.test(line.trim())) {
      continue;
    }
    else if (/^\|.+\|$/.test(line.trim())) {
      const cells = line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim()).filter(Boolean);
      if (cells.length > 0) {
        html.push(`<div class="mini-p">${inlineFormat(cells.join(' · '))}</div>`);
      }
    }
    else if (/^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]/.test(line)) {
      continue;
    }
    else if (line.startsWith('> ')) {
      html.push(`<div class="mini-p">${inlineFormat(line.slice(2))}</div>`);
    }
    else if (/^[-*_]{3,}\s*$/.test(line)) {
      html.push('<hr class="mini-hr" />');
    }
    else if (/^\s*[-*+]\s/.test(line)) {
      html.push(`<div class="mini-li">${inlineFormat(line.replace(/^\s*[-*+]\s/, ''))}</div>`);
    }
    else if (/^\s*\d+\.\s/.test(line)) {
      html.push(`<div class="mini-li mini-li-num">${inlineFormat(line.replace(/^\s*\d+\.\s/, ''))}</div>`);
    }
    else if (line.trim() === '') {
      html.push('<div class="mini-spacer"></div>');
    }
    else {
      html.push(`<div class="mini-p">${inlineFormat(line)}</div>`);
    }
  }

  return html.join('');
});

/** Inline markdown: bold, italic, inline code */
function inlineFormat(text: string): string {
  return text
    .replace(/`([^`]+)`/g, '<code class="mini-inline-code">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>');
}

// Track whether the live preview has been shown at least once this session to prevent
// flicker when tool context briefly becomes empty between tool calls.
const livePreviewHasBeenShown = ref(false);

// Reset sticky flag when session changes or completes
watch(() => props.sessionId, () => { livePreviewHasBeenShown.value = false; });
watch(() => props.isSessionComplete, (complete) => {
  if (complete) livePreviewHasBeenShown.value = false;
});

const shouldShowLivePreview = computed(() => {
  if (!props.sessionId || !props.enabled || props.isInitializing || isSummaryPhase.value) {
    return false;
  }

  // For completed sessions, keep LiveViewer visible (mirrors main tool panel)
  // unless a report is available to show instead.
  if (props.isSessionComplete && !props.isActive) {
    return !reportPreviewText.value;
  }

  if (livePreviewHasBeenShown.value && props.isActive) {
    return true;
  }

  if (!effectiveToolContent.value) {
    return false;
  }

  return props.isActive || currentViewType.value === 'live_preview';
});

watch(shouldShowLivePreview, (show) => {
  if (show) livePreviewHasBeenShown.value = true;
});

const shouldShowFinalScreenshot = computed(() => {
  if (!props.sessionId || !props.enabled || props.isInitializing) {
    return false;
  }
  if (isSummaryPhase.value) {
    return false;
  }
  if (shouldShowLivePreview.value) {
    return false;
  }
  return Boolean(props.isSessionComplete && !props.isActive);
});

// Wide research state
const { miniState: wideResearchState, isActive: wideResearchActive } = useWideResearchGlobal();

const isWideResearch = computed(() => {
  const toolName = props.toolName?.toLowerCase() || '';
  const toolFunc = props.toolFunction?.toLowerCase() || '';
  return (toolName.includes('wide_research') || toolFunc.includes('wide_research')) && wideResearchActive.value;
});

const truncate = (text: string, maxLength: number): string => {
  if (!text) return '';
  return text.length > maxLength ? text.slice(0, maxLength - 3) + '...' : text;
};

const getFavicon = (link: string): string => getFaviconUrl(link) ?? '';

const faviconErrors: Record<string, boolean> = reactive({});

const onFaviconError = (url: string) => {
  faviconErrors[url] = true;
  markFaviconFailed(url);
};

const fileName = computed(() => {
  if (!props.filePath) return 'File';
  const parts = props.filePath.split('/');
  const name = parts[parts.length - 1] || 'File';
  return name.length > 20 ? name.slice(0, 17) + '...' : name;
});

const chartTitle = computed(() => {
  const content = effectiveToolContent.value?.content as Record<string, unknown> | undefined;
  return truncate(String(content?.title || 'Chart'), 20);
});

const chartPngUrl = computed(() => {
  const content = effectiveToolContent.value?.content as Record<string, unknown> | undefined;
  const pngFileId = content?.png_file_id as string | undefined;
  if (!pngFileId) return null;
  return fileApi.getFileUrl(pngFileId);
});

const terminalTitle = computed(() => {
  const preview = props.contentPreview || '';
  const match = preview.match(/^setup_env|^[a-z_]+@[a-z]+:/i);
  if (match) return match[0].replace(/:$/, '');
  return 'Terminal';
});

const styledTerminalContent = computed(() => {
  const content = props.contentPreview || '';
  const escaped = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  const styled = escaped.replace(
    /^(\s*)([a-z_][a-z0-9_-]*@[a-z0-9_-]+:[^$#]*[$#])/gim,
    '$1<span class="shell-prompt">$2</span>'
  );

  return styled;
});

const toolIcon = computed(() => {
  const name = props.toolName || '';
  const func = props.toolFunction || '';

  if (name.includes('browser') || name.includes('web')) return Globe;
  if (name.includes('playwright')) return Globe;
  if (name.includes('file') || func.includes('file')) return FileText;
  if (name.includes('shell') || func.includes('shell')) return Terminal;
  if (name.includes('search') || name.includes('info')) return Search;
  if (name.includes('code') || func.includes('code')) return Code;
  if (name.includes('mcp')) return Wrench;
  if (name.includes('git')) return GitBranch;
  if (name.includes('test')) return TestTube;
  if (name.includes('skill')) return Wand2;
  if (name.includes('export')) return Download;
  if (name.includes('slide')) return Presentation;
  if (name.includes('workspace') || name.includes('repo_map')) return FolderTree;
  if (name.includes('schedule')) return Calendar;
  if (name.includes('scan') || name.includes('analyz')) return Scan;
  return Monitor;
});

const toolLabel = computed(() => {
  if (showInitializingDots.value) return streamingPresentation.headline.value;
  if (toolDisplay.value?.displayName) return toolDisplay.value.displayName;
  return props.toolName || streamingPresentation.headline.value;
});

const showInitializingDots = computed(() => (
  Boolean(props.sessionId) &&
  props.enabled &&
  !props.isSessionComplete &&
  !isSummaryPhase.value &&
  !props.toolName &&
  !props.toolFunction
));

const sizeClass = computed(() => {
  switch (props.size) {
    case 'sm': return 'size-sm';
    case 'lg': return 'size-lg';
    default: return 'size-md';
  }
});

/**
 * Determines whether to use the scale-transformed viewport (for browser/live
 * views) or direct-render panels (for text content like reports, terminal, code).
 *
 * The scaled viewport renders at 355x284 then CSS-scales down — ideal for
 * browser screenshots. Text content renders directly at container size for
 * crisp, readable typography.
 */
const useScaledViewport = computed(() => {
  // Init state uses scaled viewport for the monitor animation
  if (props.isInitializing) return true;

  // Wide research has its own scaled mini component
  if (isWideResearch.value && wideResearchState.value) return true;

  // Terminal running without content — needs live browser view
  if (currentViewType.value === 'terminal' && props.isActive && props.sessionId && props.enabled && !props.contentPreview) {
    return true;
  }

  // Live preview (browser screencast)
  if (shouldShowLivePreview.value) return true;

  // Everything else (reports, plans, terminal text, search, editor, chart,
  // fallback) renders directly at container size
  return false;
});
</script>

<style scoped>
/* ===== Outer Card Container ===== */
.live-mini-preview {
  position: relative;
  border-radius: 10px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-1);
  border: 1px solid var(--bolt-elements-borderColor);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08), 0 1px 4px rgba(0, 0, 0, 0.04);
  max-width: 100%;
}

.live-mini-preview:hover {
  transform: scale(1.03);
}

/* Size variants (outer container dimensions) */
.size-sm { width: 240px; height: 170px; }
.size-md { width: 340px; height: 240px; }
.size-lg { width: 400px; height: 280px; }

@media (max-width: 640px) {
  .size-sm { width: 180px; height: 128px; }
  .size-md { width: 260px; height: 184px; }
  .size-lg { width: 320px; height: 226px; }
}

/* ===== Scale-Transform Viewport ===== */
.mini-viewport {
  position: absolute;
  top: 0;
  left: 0;
  width: 355px;
  height: 284px;
  transform-origin: 0 0;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-1);
}

/* Non-uniform scale: scaleX = width/355, scaleY = height/284 */
.size-sm .mini-viewport { transform: scale(0.676, 0.599); }
.size-md .mini-viewport { transform: scale(0.958, 0.845); }
.size-lg .mini-viewport { transform: scale(1.127, 0.986); }

@media (max-width: 640px) {
  .size-sm .mini-viewport { transform: scale(0.507, 0.451); }
  .size-md .mini-viewport { transform: scale(0.732, 0.648); }
  .size-lg .mini-viewport { transform: scale(0.901, 0.796); }
}

/* ===== Direct-Content Wrapper (text panels, no scaling) ===== */
.dc-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ===== Direct-Content Panel Layout ===== */
.dc-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  position: relative;
}

.dc-header {
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 0 8px;
  background: var(--bolt-elements-bg-depth-1);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
  position: relative;
}

/* Subtle accent top border — mirrors main tool panel header */
.dc-header::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--bolt-elements-item-contentAccent, #22c55e);
  border-radius: 10px 10px 0 0;
  opacity: 0.7;
}

.dc-header-title {
  max-width: 95%;
  font-size: 10px;
  font-weight: 600;
  color: var(--bolt-elements-textPrimary);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.1px;
}

.dc-header-icon {
  flex-shrink: 0;
  color: var(--bolt-elements-textTertiary);
}

.dc-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  margin: 4px;
  padding: 6px 8px;
  background: var(--bolt-elements-bg-depth-2);
  border-radius: 5px;
}

.dc-centered {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 6px;
}

.dc-centered-full {
  width: 100%;
  height: 100%;
}

/* ===== Search Results ===== */
.dc-body-search {
  padding: 4px 0;
}

.search-results-list {
  display: flex;
  flex-direction: column;
}

.search-result-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 5px 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

:global(.dark) .search-result-row {
  border-bottom-color: rgba(255, 255, 255, 0.06);
}

.search-result-row:last-child {
  border-bottom: none;
}

.sr-favicon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  margin-top: 1px;
  border-radius: 50%;
  border: 1px solid var(--bolt-elements-borderColor);
}

.sr-favicon-fallback {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  margin-top: 1px;
  border-radius: 50%;
  border: 1px solid var(--bolt-elements-borderColor);
  background: var(--bolt-elements-bg-depth-2);
  color: var(--bolt-elements-textTertiary);
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.sr-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.sr-title {
  font-size: 11px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.3;
}

.sr-snippet {
  font-size: 10px;
  color: var(--bolt-elements-textTertiary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.3;
  margin-top: 1px;
}

/* ===== Terminal ===== */
.dc-body-terminal {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
}

.dc-terminal-text {
  font-family: inherit;
  font-size: 9.5px;
  line-height: 1.45;
  color: var(--bolt-elements-textPrimary);
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.dc-terminal-text :deep(.shell-prompt) {
  color: #16a34a;
  font-weight: 500;
}

/* ===== Code / Editor ===== */
.dc-body-code {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
}

.dc-code-text {
  font-family: inherit;
  font-size: 9.5px;
  line-height: 1.45;
  color: var(--bolt-elements-textPrimary);
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

/* ===== Chart ===== */
.dc-body-chart {
  display: flex;
  align-items: center;
  justify-content: center;
}

.chart-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 4px;
}

.chart-bars {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 40px;
}

.bar {
  width: 12px;
  background: var(--bolt-elements-item-contentAccent);
  border-radius: 3px 3px 0 0;
  animation: bar-grow 1.5s ease-in-out infinite;
}

.bar-1 { animation-delay: 0s; }
.bar-2 { animation-delay: 0.2s; }
.bar-3 { animation-delay: 0.4s; }

@keyframes bar-grow {
  0%, 100% { height: 30%; opacity: 0.6; }
  50% { height: 80%; opacity: 1; }
}

/* ===== Live Preview ===== */
.vp-live {
  width: 100%;
  height: 100%;
}

/* ===== Centered Content (init, fallback — inside scaled viewport) ===== */
.vp-centered {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: var(--bolt-elements-bg-depth-1);
}

/* ===== Direct-Content Markdown Report ===== */
.dc-md-text {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.dc-md-text::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 16px;
  background: linear-gradient(to bottom, transparent, var(--bolt-elements-bg-depth-2));
  pointer-events: none;
}

.dc-mini-md {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 8.5px;
  line-height: 1.4;
  color: var(--bolt-elements-textPrimary);
  overflow: hidden;
  max-height: 100%;
}

.dc-mini-md .mini-h1 {
  font-size: 10px;
  font-weight: 700;
  color: var(--bolt-elements-textPrimary);
  margin: 0 0 2px;
  line-height: 1.2;
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  padding-bottom: 2px;
}

.dc-mini-md .mini-h2 {
  font-size: 9.5px;
  font-weight: 650;
  color: var(--bolt-elements-textPrimary);
  margin: 2px 0 1px;
  line-height: 1.25;
}

.dc-mini-md .mini-h3 {
  font-size: 9px;
  font-weight: 600;
  color: var(--bolt-elements-textSecondary);
  margin: 2px 0 1px;
  line-height: 1.25;
}

.dc-mini-md .mini-p {
  margin: 0;
  word-break: break-word;
}

.dc-mini-md .mini-li {
  padding-left: 7px;
  position: relative;
  margin: 0;
}

.dc-mini-md .mini-li::before {
  content: '\2022';
  position: absolute;
  left: 0;
  color: var(--bolt-elements-textTertiary);
  font-size: 8px;
}

.dc-mini-md .mini-li-num::before {
  content: '\2013';
}

.dc-mini-md .mini-spacer {
  height: 1px;
}

.dc-mini-md .mini-hr {
  border: none;
  height: 1px;
  background: var(--bolt-elements-borderColor);
  margin: 1px 0;
}

.dc-mini-md .mini-code-block {
  background: #24292e;
  border-radius: 3px;
  padding: 3px 5px;
  margin: 1px 0;
  position: relative;
  overflow: hidden;
}

:global(.dark) .dc-mini-md .mini-code-block {
  background: #161b22;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.dc-mini-md .mini-code-block pre {
  margin: 0;
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  font-size: 7px;
  line-height: 1.3;
  color: #e1e4e8;
  white-space: pre-wrap;
  word-break: break-all;
}

.dc-mini-md .mini-code-lang {
  position: absolute;
  top: 2px;
  right: 4px;
  font-size: 6px;
  font-weight: 600;
  color: #6a737d;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.dc-mini-md .mini-inline-code {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  font-size: 7.5px;
  background: rgba(175, 184, 193, 0.15);
  border-radius: 2px;
  padding: 0 2px;
}

:global(.dark) .dc-mini-md .mini-inline-code {
  background: rgba(255, 255, 255, 0.08);
}

.dc-mini-md strong {
  font-weight: 650;
}

.dc-mini-md em {
  font-style: italic;
  opacity: 0.85;
}

/* ===== Skeleton Lines ===== */
.dc-skeleton-lines {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skeleton-line {
  height: 5px;
  border-radius: 2px;
  background: var(--bolt-elements-borderColor);
  animation: line-appear 0.6s ease-out both;
}

@keyframes line-appear {
  from { width: 0; opacity: 0; }
  to { opacity: 0.6; }
}

/* ===== Loading Dots ===== */
.loading-dots {
  display: flex;
  gap: 5px;
}

.loading-dots .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bolt-elements-textSecondary);
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dots .dot:nth-child(1) { animation-delay: -0.32s; }
.loading-dots .dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.loading-label {
  font-size: 10px;
  color: var(--bolt-elements-textSecondary);
}

.empty-icon {
  color: var(--bolt-elements-textTertiary);
  opacity: 0.5;
}

.empty-label {
  font-size: 10px;
  color: var(--bolt-elements-textTertiary);
}

/* ===== Fallback ===== */
.fallback-icon {
  color: var(--bolt-elements-textSecondary);
}

.fallback-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--bolt-elements-textSecondary);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

/* ===== Activity Dot ===== */
.activity-dot {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 8px;
  height: 8px;
  background: var(--bolt-elements-item-contentAccent);
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

.activity-dot-abs {
  top: 10px;
  right: 10px;
}

@keyframes pulse {
  0%, 100% { opacity: 0.6; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* ===== Initializing ===== */
.init-monitor {
  position: relative;
}

.monitor-frame {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.monitor-screen {
  width: 48px;
  height: 34px;
  background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
  border-radius: 4px;
  border: 2px solid #475569;
  position: relative;
  overflow: hidden;
  box-shadow:
    inset 0 0 12px rgba(59, 130, 246, 0.15),
    0 2px 8px rgba(0, 0, 0, 0.15);
}

.scan-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(59, 130, 246, 0.4) 20%,
    rgba(59, 130, 246, 0.6) 50%,
    rgba(59, 130, 246, 0.4) 80%,
    transparent 100%
  );
  animation: scan 1.8s ease-in-out infinite;
}

@keyframes scan {
  0% { top: -3px; opacity: 0; }
  10% { opacity: 1; }
  90% { opacity: 1; }
  100% { top: calc(100% + 3px); opacity: 0; }
}

.boot-dots {
  position: absolute;
  bottom: 5px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 4px;
}

.boot-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--bolt-elements-item-contentAccent);
  animation: boot-pulse 1.2s ease-in-out infinite;
}

.boot-dot:nth-child(2) { animation-delay: 0.2s; }
.boot-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes boot-pulse {
  0%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

.monitor-stand {
  width: 12px;
  height: 6px;
  background: linear-gradient(180deg, #64748b 0%, #475569 100%);
  border-radius: 0 0 3px 3px;
  margin-top: -1px;
}

.init-label {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', ui-monospace, monospace;
  font-size: 13px;
  font-weight: 500;
  color: var(--bolt-elements-textSecondary);
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

.init-ellipsis::after {
  content: '';
  animation: ellipsis 1.5s steps(4, end) infinite;
}

@keyframes ellipsis {
  0% { content: ''; }
  25% { content: '.'; }
  50% { content: '..'; }
  75% { content: '...'; }
  100% { content: ''; }
}

/* ===== Hover Expand Button ===== */
.hover-expand-btn {
  position: absolute;
  bottom: 4px;
  right: 4px;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
  border: none;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s ease;
  z-index: 10;
  pointer-events: auto;
}

.live-mini-preview:hover .hover-expand-btn {
  opacity: 1;
}

.expand-icon {
  color: white;
}
</style>
