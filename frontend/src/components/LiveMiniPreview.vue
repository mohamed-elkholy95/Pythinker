<template>
  <div
    class="live-mini-preview"
    :class="sizeClass"
    @click="emit('click')"
  >
    <!-- Initializing state - sandbox environment starting up -->
    <div v-if="isInitializing" class="init-preview">
      <div class="init-container">
        <!-- Animated monitor icon with boot sequence effect -->
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
      <!-- Subtle grid pattern background -->
      <div class="init-grid"></div>
    </div>

    <!-- Wide Research view (parallel multi-source search) -->
    <WideResearchMiniPreview
      v-else-if="isWideResearch && wideResearchState"
      :state="wideResearchState"
      :is-active="isActive"
    />

    <!-- Summary / Report preview — renders actual markdown content scaled down -->
    <div v-else-if="isSummaryPhase" class="content-preview streaming-preview">
      <div class="streaming-mini-window">
        <div class="streaming-mini-header">
          <span class="streaming-mini-title">{{ streamingPresentation.headline.value }}</span>
        </div>
        <div class="streaming-mini-body report-mini-body">
          <div class="report-mini-content markdown-body-mini" v-html="miniReportHtml"></div>
        </div>
      </div>
      <div v-if="isSummaryStreaming" class="activity-indicator"></div>
    </div>

    <!-- Terminal view (shell, code_executor) -->
    <div v-else-if="presentationViewType === 'terminal' && contentPreview" class="content-preview terminal-preview">
      <div class="terminal-window">
        <div class="terminal-header">
          <span class="terminal-title">{{ terminalTitle }}</span>
        </div>
        <div class="terminal-body">
          <div class="terminal-accent"></div>
          <div class="terminal-content-area">
            <pre class="preview-text terminal-text" v-html="styledTerminalContent"></pre>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Terminal tool running without content yet - show live preview -->
    <div v-else-if="presentationViewType === 'terminal' && isActive && sessionId && enabled" class="live-preview-container">
      <LiveViewer
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="true"
        :compact-loading="true"
        :show-controls="false"
      />
    </div>

    <!-- Search results view (search, info tools) -->
    <div v-else-if="presentationViewType === 'search'" class="content-preview search-preview">
      <div class="search-window">
        <div class="search-header">
          <Search :size="10" class="search-header-icon" />
          <span class="search-title">{{ truncate(searchQuery || 'Search', 20) }}</span>
        </div>
        <div class="search-body">
          <div class="search-content-area">
            <div v-if="searchResults.length > 0" class="search-results-mini">
              <div v-for="(result, idx) in searchResults.slice(0, 3)" :key="idx" class="search-result-item">
                <img
                  v-if="!faviconErrors[result.url || result.link]"
                  :src="getFavicon(result.url || result.link)"
                  alt=""
                  class="result-favicon"
                  @error="onFaviconError(result.url || result.link)"
                />
                <span v-else class="result-favicon-fallback">{{ getIconLetterFromUrl(result.url || result.link, result.title) }}</span>
                <div class="result-text">
                  <span class="result-title">{{ truncate(result.title || result.name || 'Result', 25) }}</span>
                  <span v-if="result.snippet" class="result-snippet">{{ truncate(result.snippet, 40) }}</span>
                </div>
              </div>
              <div v-if="searchResults.length > 3" class="results-more">
                +{{ searchResults.length - 3 }} more results
              </div>
            </div>
            <div v-else-if="isActive" class="search-loading">
              <div class="loading-dots">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
              </div>
              <span class="loading-text">Searching...</span>
            </div>
            <div v-else class="search-empty">
              <Search :size="14" class="empty-search-icon" />
              <span>No results</span>
            </div>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Editor view (file tools) -->
    <div v-else-if="presentationViewType === 'editor' && contentPreview" class="content-preview file-preview">
      <div class="file-window">
        <div class="file-header">
          <span class="file-title">{{ fileName }}</span>
        </div>
        <div class="file-body">
          <div class="file-accent"></div>
          <div class="file-content-area">
            <pre class="preview-text">{{ contentPreview }}</pre>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Chart view (chart tool creates images, not visible via live preview) -->
    <div v-else-if="presentationViewType === 'chart'" class="content-preview chart-preview">
      <div class="chart-mini-window">
        <div class="chart-mini-header">
          <BarChart3 :size="10" class="chart-header-icon" />
          <span class="chart-mini-title">{{ chartTitle }}</span>
        </div>
        <div class="chart-mini-body">
          <img
            v-if="chartPngUrl"
            :src="chartPngUrl"
            alt="Chart"
            class="chart-mini-image"
          />
          <div v-else-if="isActive" class="chart-generating">
            <div class="chart-bars-mini">
              <div class="bar-mini bar-mini-1"></div>
              <div class="bar-mini bar-mini-2"></div>
              <div class="bar-mini bar-mini-3"></div>
            </div>
            <span class="chart-gen-text">Generating...</span>
          </div>
          <div v-else class="chart-empty">
            <BarChart3 :size="14" class="empty-chart-icon" />
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Live preview (only with active tool context) -->
    <div v-else-if="shouldShowLivePreview" class="live-preview-container">
      <LiveViewer
        ref="liveViewerRef"
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="true"
        :compact-loading="true"
        :show-controls="false"
      />
    </div>

    <!-- Session complete fallback (replay final frame) -->
    <div v-else-if="shouldShowFinalScreenshot" class="final-screenshot-preview">
      <img
        v-if="finalScreenshotUrl && !finalScreenshotLoadError"
        :src="finalScreenshotUrl"
        alt="Final session state"
        class="final-screenshot-image"
        @error="handleFinalScreenshotError"
      />
      <div v-else class="final-screenshot-placeholder">
        <Monitor class="placeholder-icon" />
        <span class="placeholder-text">Session Complete</span>
      </div>
    </div>

    <!-- Generic tool indicator (fallback when no session or unknown tool) -->
    <div v-else class="tool-preview">
      <div class="tool-preview-content">
        <component :is="toolIcon" class="tool-preview-icon" />
        <span class="tool-preview-label">{{ toolLabel }}</span>
        <div v-if="showInitializingDots" class="loading-dots init-loading-dots" aria-hidden="true">
          <span class="dot"></span>
          <span class="dot"></span>
          <span class="dot"></span>
        </div>
      </div>
      <div v-if="isActive" class="activity-pulse"></div>
    </div>

    <!-- Hover overlay -->
    <div class="hover-overlay">
      <Monitor class="hover-icon" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, toRef, watch } from 'vue';
import { Monitor, Terminal, FileText, Globe, Code, Wrench, Search, GitBranch, TestTube, Wand2, Download, Presentation, FolderTree, Calendar, Scan, BarChart3 } from 'lucide-vue-next';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import LiveViewer from '@/components/LiveViewer.vue';
import WideResearchMiniPreview from '@/components/WideResearchMiniPreview.vue';
import { useContentConfig } from '@/composables/useContentConfig';
import { useStreamingPresentationState } from '@/composables/useStreamingPresentationState';
import { useWideResearchGlobal } from '@/composables/useWideResearch';
import { resolveLivePreviewViewType } from '@/utils/livePreviewSelection';
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
  replayScreenshotUrl: ''
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

const presentationViewType = computed(() => resolveLivePreviewViewType({
  baseViewType: currentViewType.value,
  sessionId: props.sessionId,
  enabled: props.enabled,
  isReplayMode: !!props.isSessionComplete,
  hasReplayScreenshot: !!props.replayScreenshotUrl,
  isSessionComplete: !!props.isSessionComplete,
}));

const baseViewTypeForPresentation = computed(() => {
  if (
    presentationViewType.value === 'terminal' ||
    presentationViewType.value === 'editor' ||
    presentationViewType.value === 'search'
  ) {
    return presentationViewType.value;
  }
  if (presentationViewType.value === 'live_preview') {
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
  toolDisplayName: computed(() => toolDisplay.value?.displayName || props.toolName || ''),
  toolDescription: computed(() => toolDisplay.value?.description || ''),
  baseViewType: computed(() => baseViewTypeForPresentation.value),
  isSessionComplete: computed(() => !!props.isSessionComplete),
  replayScreenshotUrl: computed(() => props.replayScreenshotUrl || ''),
  previewText: computed(() => props.contentPreview || '')
});

const isSummaryPhase = computed(() => streamingPresentation.isSummaryPhase.value);

// Render actual markdown for the mini report preview (same content as main StreamingReportView)
const miniReportHtml = computed(() => {
  const text = props.finalReportText || props.summaryStreamText || '';
  if (!text) return '';
  const raw = marked.parse(text, { async: false, breaks: true, gfm: true }) as string;
  return DOMPurify.sanitize(raw);
});

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

  // Never show live preview for completed sessions — use final screenshot instead
  if (props.isSessionComplete && !props.isActive) {
    return false;
  }

  // Once live preview has been shown, keep it visible while the session is active
  // to prevent flicker during brief gaps between tool calls.
  if (livePreviewHasBeenShown.value && props.isActive) {
    return true;
  }

  // Avoid opening a live preview feed before the agent emits any concrete tool context.
  if (!effectiveToolContent.value) {
    return false;
  }

  return props.isActive || presentationViewType.value === 'live_preview';
});

// Mark live preview as shown once it becomes visible (watcher avoids side effects in computed)
watch(shouldShowLivePreview, (show) => {
  if (show) livePreviewHasBeenShown.value = true;
});

const finalScreenshotLoadError = ref(false);

const finalScreenshotUrl = computed(() => props.replayScreenshotUrl || '');

watch(finalScreenshotUrl, () => {
  finalScreenshotLoadError.value = false;
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

const handleFinalScreenshotError = () => {
  finalScreenshotLoadError.value = true;
};

// Wide research state
const { miniState: wideResearchState, isActive: wideResearchActive } = useWideResearchGlobal();

// Check if this is a wide research tool
const isWideResearch = computed(() => {
  const toolName = props.toolName?.toLowerCase() || '';
  const toolFunc = props.toolFunction?.toLowerCase() || '';
  return (toolName.includes('wide_research') || toolFunc.includes('wide_research')) && wideResearchActive.value;
});

// Helper to truncate text
const truncate = (text: string, maxLength: number): string => {
  if (!text) return '';
  return text.length > maxLength ? text.slice(0, maxLength - 3) + '...' : text;
};

// Get favicon URL for a given link using shared utility
const getFavicon = (link: string): string => getFaviconUrl(link) ?? '';

// Track favicon errors per URL and cache failures globally
const faviconErrors: Record<string, boolean> = reactive({});

const onFaviconError = (url: string) => {
  faviconErrors[url] = true;
  markFaviconFailed(url);
};

// Extract filename from path
const fileName = computed(() => {
  if (!props.filePath) return 'File';
  const parts = props.filePath.split('/');
  const name = parts[parts.length - 1] || 'File';
  // Truncate long names
  return name.length > 20 ? name.slice(0, 17) + '...' : name;
});

// Chart mini-preview data
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

// Terminal title from content or default
const terminalTitle = computed(() => {
  // Try to extract a meaningful title from the terminal session name
  const preview = props.contentPreview || '';
  // Look for common shell session names in first line
  const match = preview.match(/^setup_env|^[a-z_]+@[a-z]+:/i);
  if (match) return match[0].replace(/:$/, '');
  return 'Terminal';
});

// Style terminal content with green prompts (ubuntu@sandbox:~ $)
const styledTerminalContent = computed(() => {
  const content = props.contentPreview || '';
  // Escape HTML first
  const escaped = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Style shell prompts in green (matches patterns like "ubuntu@sandbox:~ $" or "user@host:/path $")
  const styled = escaped.replace(
    /^(\s*)([a-z_][a-z0-9_-]*@[a-z0-9_-]+:[^$#]*[$#])/gim,
    '$1<span class="shell-prompt">$2</span>'
  );

  return styled;
});

// Get appropriate icon for fallback
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

// Get label for fallback
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
</script>

<style scoped>
.live-mini-preview {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-2);
  border: 1px solid var(--bolt-elements-borderColor);
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px var(--shadow-XS);
  aspect-ratio: 16 / 10;
}

.live-mini-preview:hover {
  transform: scale(1.02);
  border-color: var(--bolt-elements-borderColorActive);
  box-shadow: 0 4px 16px var(--shadow-S);
}

/* Size variants */
.size-sm { width: 96px; }
.size-md { width: 144px; }
.size-lg { width: 176px; }

@media (max-width: 640px) {
  .size-sm { width: 72px; }
  .size-md { width: 112px; }
  .size-lg { width: 136px; }
}

/* Live Preview Container */
.live-preview-container {
  position: absolute;
  inset: 0;
  background: var(--bolt-elements-bg-depth-2);
}

.final-screenshot-preview {
  position: absolute;
  inset: 0;
  background: var(--bolt-elements-bg-depth-1);
  overflow: hidden;
}

.final-screenshot-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: var(--bolt-elements-bg-depth-2);
}

.final-screenshot-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--bolt-elements-textTertiary);
  background: var(--bolt-elements-bg-depth-2);
}

.placeholder-icon {
  width: 18px;
  height: 18px;
}

.placeholder-text {
  font-size: 8px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

/* Content Preview (File/Terminal) */
.content-preview {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 2;
}

.file-preview {
  background: var(--bolt-elements-bg-depth-1);
  z-index: 3;
}

/* Decorated file window */
.file-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bolt-elements-bg-depth-1);
  border-radius: 6px;
  overflow: hidden;
}

.file-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  background: var(--bolt-elements-bg-depth-2);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
}

.file-title {
  font-size: 8px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.file-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.file-accent {
  width: 2px;
  background: var(--bolt-elements-item-contentAccent);
  flex-shrink: 0;
}

.file-content-area {
  flex: 1;
  padding: 4px 6px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-1);
}

.terminal-preview {
  background: var(--bolt-elements-bg-depth-1);
}

/* ===== Search Preview ===== */
.search-preview {
  background: var(--bolt-elements-bg-depth-2);
}

.search-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bolt-elements-bg-depth-2);
  border-radius: 6px;
  overflow: hidden;
}

.search-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 3px 6px;
  background: var(--bolt-elements-bg-depth-3);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
}

.search-header-icon {
  color: var(--bolt-elements-textPrimary);
  flex-shrink: 0;
}

.search-title {
  font-size: 7px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 85%;
}

.search-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.search-content-area {
  flex: 1;
  padding: 3px 4px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-2);
}

.search-results-mini {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.search-result-item {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  padding: 3px 4px;
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  overflow: hidden;
}

.search-result-item:last-child {
  border-bottom: none;
}

.result-favicon {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  margin-top: 1px;
  border-radius: 2px;
}

.result-favicon-fallback {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  margin-top: 1px;
  border-radius: 2px;
  background: var(--fill-tsp-gray-main, #e5e7eb);
  color: var(--text-tertiary, #9ca3af);
  font-size: 7px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.result-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  flex: 1;
}

.result-title {
  font-size: 6px;
  font-weight: 600;
  color: var(--bolt-elements-textPrimary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  line-height: 1.3;
}

.result-snippet {
  font-size: 5px;
  color: var(--bolt-elements-textSecondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  line-height: 1.2;
}

.results-more {
  font-size: 5px;
  color: var(--bolt-elements-textTertiary);
  text-align: center;
  padding: 2px 0;
}

.search-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 4px;
}

.loading-dots {
  display: flex;
  gap: 3px;
}

.loading-dots .dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--bolt-elements-textPrimary);
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dots .dot:nth-child(1) { animation-delay: -0.32s; }
.loading-dots .dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.loading-text {
  font-size: 6px;
  color: var(--bolt-elements-textSecondary);
}

.search-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 3px;
  font-size: 6px;
  color: var(--bolt-elements-textTertiary);
}

.empty-search-icon {
  color: var(--bolt-elements-textTertiary);
}

/* Decorated terminal window */
.terminal-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bolt-elements-bg-depth-1);
  border-radius: 6px;
  overflow: hidden;
}

.terminal-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  background: var(--bolt-elements-bg-depth-2);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
}

.terminal-title {
  font-size: 8px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
}

.terminal-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.terminal-accent {
  width: 2px;
  background: linear-gradient(180deg, #f97316 0%, #ea580c 100%);
  flex-shrink: 0;
}

.terminal-content-area {
  flex: 1;
  padding: 4px 6px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-1);
}

.terminal-content-area.terminal-running {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.running-icon {
  width: 16px;
  height: 16px;
  color: #f97316;
  animation: pulse 1.5s ease-in-out infinite;
}

.running-text {
  font-size: 7px;
  font-weight: 500;
  color: var(--bolt-elements-textSecondary);
}

.preview-text {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  font-size: 6px;
  line-height: 1.4;
  color: var(--bolt-elements-textPrimary);
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.terminal-text {
  color: var(--bolt-elements-textPrimary);
  font-size: 5px;
  line-height: 1.3;
}

/* Green shell prompt (ubuntu@sandbox:~ $) */
.terminal-text :deep(.shell-prompt) {
  color: #16a34a;
  font-weight: 500;
}

/* Activity indicator */
.activity-indicator {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 6px;
  height: 6px;
  background: var(--bolt-elements-item-contentAccent);
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

/* Streaming mini preview */
.streaming-preview {
  background: var(--bolt-elements-bg-depth-1);
}

.streaming-mini-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-radius: 6px;
  overflow: hidden;
}

.streaming-mini-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  background: var(--bolt-elements-bg-depth-2);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
}

.streaming-mini-title {
  font-size: 7px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
}

.streaming-mini-body {
  flex: 1;
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}

/* Mini report — scaled-down rendered markdown matching the main panel */
.report-mini-body {
  padding: 3px 5px;
  overflow: hidden;
}

.report-mini-content {
  transform-origin: top left;
  transform: scale(0.38);
  width: 263%;  /* 100% / 0.38 to fill container at scaled size */
  pointer-events: none;
}

.markdown-body-mini {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  word-wrap: break-word;
}

.markdown-body-mini :deep(h1) {
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border-light);
}

.markdown-body-mini :deep(h2) {
  font-size: 16px;
  font-weight: 600;
  margin: 12px 0 6px;
}

.markdown-body-mini :deep(h3) {
  font-size: 14px;
  font-weight: 600;
  margin: 10px 0 4px;
}

.markdown-body-mini :deep(p) {
  margin: 0 0 6px;
}

.markdown-body-mini :deep(ul),
.markdown-body-mini :deep(ol) {
  margin: 0 0 6px;
  padding-left: 16px;
}

.markdown-body-mini :deep(li) {
  margin: 0 0 2px;
}

.markdown-body-mini :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 6px 0;
  font-size: 12px;
}

.markdown-body-mini :deep(th),
.markdown-body-mini :deep(td) {
  padding: 3px 6px;
  border: 1px solid var(--border-light);
  text-align: left;
}

.markdown-body-mini :deep(th) {
  background: var(--bolt-elements-bg-depth-2);
  font-weight: 600;
}

.markdown-body-mini :deep(blockquote) {
  border-left: 2px solid var(--border-main);
  padding-left: 8px;
  color: var(--text-secondary);
  margin: 6px 0;
}

.markdown-body-mini :deep(code) {
  background: var(--bolt-elements-bg-depth-2);
  padding: 1px 3px;
  border-radius: 2px;
  font-size: 12px;
}

.markdown-body-mini :deep(hr) {
  border: none;
  border-top: 1px solid var(--border-light);
  margin: 8px 0;
}

.markdown-body-mini :deep(strong) {
  font-weight: 600;
}

/* Tool Preview (fallback) */
.tool-preview {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bolt-elements-bg-depth-2);
}

.tool-preview-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.tool-preview-icon {
  width: 24px;
  height: 24px;
  color: var(--bolt-elements-textSecondary);
}

.tool-preview-label {
  font-size: 10px;
  font-weight: 500;
  color: var(--bolt-elements-textSecondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.init-loading-dots .dot {
  background: var(--bolt-elements-textSecondary);
}

.activity-pulse {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 8px;
  height: 8px;
  background: var(--bolt-elements-item-contentAccent);
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.6);
}

@keyframes pulse {
  0%, 100% { opacity: 0.6; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* ===== Chart Preview ===== */
.chart-preview {
  background: var(--bolt-elements-bg-depth-2);
}

.chart-mini-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bolt-elements-bg-depth-2);
  border-radius: 6px;
  overflow: hidden;
}

.chart-mini-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 3px 6px;
  background: var(--bolt-elements-bg-depth-3);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
}

.chart-header-icon {
  color: var(--text-brand, #636EFA);
  flex-shrink: 0;
}

.chart-mini-title {
  font-size: 7px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 85%;
}

.chart-mini-body {
  display: flex;
  flex: 1;
  min-height: 0;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 2px;
}

.chart-mini-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 2px;
}

.chart-generating {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.chart-bars-mini {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 24px;
}

.bar-mini {
  width: 6px;
  background: var(--text-brand, #636EFA);
  border-radius: 2px 2px 0 0;
  animation: bar-grow-mini 1.5s ease-in-out infinite;
}

.bar-mini-1 { animation-delay: 0s; }
.bar-mini-2 { animation-delay: 0.2s; }
.bar-mini-3 { animation-delay: 0.4s; }

.chart-gen-text {
  font-size: 7px;
  color: var(--bolt-elements-textSecondary);
}

.empty-chart-icon {
  color: var(--bolt-elements-textTertiary);
  opacity: 0.5;
}

@keyframes bar-grow-mini {
  0%, 100% { height: 30%; opacity: 0.6; }
  50% { height: 80%; opacity: 1; }
}

/* ===== Initialization State ===== */
.init-preview {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bolt-elements-bg-depth-2);
  overflow: hidden;
}

.init-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  z-index: 2;
}

.init-monitor {
  position: relative;
}

.monitor-frame {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.monitor-screen {
  width: 28px;
  height: 20px;
  background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
  border-radius: 3px;
  border: 2px solid #475569;
  position: relative;
  overflow: hidden;
  box-shadow:
    inset 0 0 8px rgba(59, 130, 246, 0.15),
    0 2px 8px rgba(0, 0, 0, 0.15);
}

.scan-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 2px;
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
  0% { top: -2px; opacity: 0; }
  10% { opacity: 1; }
  90% { opacity: 1; }
  100% { top: calc(100% + 2px); opacity: 0; }
}

.boot-dots {
  position: absolute;
  bottom: 3px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 3px;
}

.boot-dot {
  width: 3px;
  height: 3px;
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
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0);
  }
  50% {
    opacity: 1;
    transform: scale(1);
    box-shadow: 0 0 4px 1px rgba(59, 130, 246, 0.4);
  }
}

.monitor-stand {
  width: 8px;
  height: 4px;
  background: linear-gradient(180deg, #64748b 0%, #475569 100%);
  border-radius: 0 0 2px 2px;
  margin-top: -1px;
}

.init-label {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', ui-monospace, monospace;
  font-size: 8px;
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

.init-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(71, 85, 105, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(71, 85, 105, 0.03) 1px, transparent 1px);
  background-size: 8px 8px;
  pointer-events: none;
}

/* Hover overlay */
.hover-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(2px);
  opacity: 0;
  transition: opacity 0.2s ease;
  z-index: 10;
}

.live-mini-preview:hover .hover-overlay {
  opacity: 1;
}

.hover-icon {
  width: 20px;
  height: 20px;
  color: white;
}
</style>
