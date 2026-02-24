<template>
  <div
    class="flex h-full w-full"
    :class="{ 'bg-[var(--background-white-main)] sm:bg-[var(--background-white-main)] sm:rounded-[20px] shadow-[0px_10px_30px_rgba(15,23,42,0.08)] border border-[var(--border-light)]': !embedded }"
  >
    <div :class="['flex-1 min-w-0 flex flex-col h-full', embedded ? 'px-3 pb-3' : 'p-4']">
      <!-- Frame Header: Pythinker's Computer + window controls (hidden in embedded/workspace mode) -->
      <div v-if="!embedded" class="flex items-center gap-2 w-full">
        <div class="text-[var(--text-primary)] text-[15px] font-semibold flex-1">{{ $t("Pythinker's Computer") }}</div>
        <div class="flex items-center gap-1">
          <button
            v-if="!!props.sessionId"
            class="w-7 h-7 rounded-md inline-flex items-center justify-center cursor-pointer border border-transparent hover:bg-[var(--fill-tsp-gray-main)] hover:border-[var(--border-light)] disabled:opacity-40 disabled:cursor-not-allowed"
            @click="takeOver"
            :disabled="takeoverLoading"
            aria-label="Open takeover"
          >
            <MonitorUp class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
          <button
            class="w-7 h-7 rounded-md inline-flex items-center justify-center cursor-pointer border border-transparent hover:bg-[var(--fill-tsp-gray-main)] hover:border-[var(--border-light)]"
            @click="hide"
            aria-label="Minimize"
          >
            <Minimize2 class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
          <button
            class="w-7 h-7 rounded-md inline-flex items-center justify-center cursor-pointer border border-transparent hover:bg-[var(--fill-tsp-gray-main)] hover:border-[var(--border-light)]"
            @click="hide"
            aria-label="Close"
          >
            <X class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
        </div>
      </div>

      <!-- Activity Bar: unified streaming presentation status -->
      <div v-if="activityHeadline" class="flex items-center gap-2 mt-2 text-[13px] text-[var(--text-tertiary)] overflow-hidden">
        <Loader2
          v-if="showActivitySpinner"
          :size="18"
          class="flex-shrink-0 text-[var(--icon-secondary)]"
          :class="{ 'animate-spin': isSummaryStreaming }"
          style="min-width: 18px; min-height: 18px;"
        />
        <component
          v-else-if="toolDisplay?.icon"
          :is="toolDisplay.icon"
          :size="18"
          class="flex-shrink-0 text-[var(--icon-secondary)]"
          style="min-width: 18px; min-height: 18px;"
        />
        <span class="flex-shrink-0 whitespace-nowrap">{{ activityHeadline }}</span>
        <span v-if="activitySubtitle" class="text-[var(--text-quaternary)] flex-shrink-0">|</span>
        <span v-if="activitySubtitle" class="truncate min-w-0">{{ activitySubtitle }}</span>
      </div>

      <!-- Confirmation banner removed -->

      <!-- Content Container with rounded frame -->
      <div
        :class="[
          'relative flex flex-col overflow-hidden bg-[var(--background-white-main)] flex-1 min-h-0',
          embedded
            ? 'rounded-[10px] border border-[var(--border-light)] mt-2'
            : 'rounded-[14px] border border-[var(--border-light)] shadow-[0px_6px_24px_var(--shadow-XS)] mt-[16px]'
        ]">

        <!-- Content Header: Centered operation label + View mode tabs.
             Hidden only when this component is embedded without a forced view mode. -->
        <div
          v-if="contentConfig && (!embedded || forceViewType)"
          class="panel-content-header h-[36px] flex items-center justify-center px-3 w-full bg-[var(--background-white-main)] border-b border-[var(--border-light)] rounded-t-[14px] relative">

          <!-- Left: Activity indicator (absolute positioned) -->
          <div v-if="isWriting" class="absolute left-3 flex items-center gap-2">
            <div class="flex items-center gap-1.5">
              <div class="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></div>
              <span class="text-xs text-blue-500 font-medium">Writing</span>
            </div>
          </div>

          <!-- Center: Operation label or resource -->
          <div class="text-[var(--text-tertiary)] text-sm font-medium max-w-[300px] flex items-center justify-center gap-1.5 min-w-0">
            <BarChart3
              v-if="currentViewType === 'chart'"
              :size="14"
              class="flex-shrink-0 text-[var(--text-tertiary)]"
            />
            <span class="truncate">{{ contentHeaderLabel }}</span>
          </div>

          <!-- Right: View mode tabs (absolute positioned) -->
          <div v-if="contentConfig.showTabs" class="absolute right-3 flex items-center gap-1 bg-[var(--fill-tsp-gray-main)] rounded-lg p-0.5">
            <button
              v-for="(label, idx) in contentConfig.tabLabels"
              :key="idx"
              @click="setViewModeByIndex(idx)"
              class="px-2 py-1 text-xs rounded-md transition-colors relative"
              :class="viewModeIndex === idx ? 'bg-[var(--background-white-main)] text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'"
            >
              {{ label }}
              <span v-if="hasNewOutput && idx === 1 && viewModeIndex !== 1" class="absolute -top-0.5 -right-0.5 w-2 h-2 bg-blue-500 rounded-full"></span>
            </button>
          </div>

          <!-- Right: HTML Code/Preview tabs (inline in panel header) -->
          <div v-else-if="currentViewType === 'editor' && isHtmlFile" class="absolute right-3 flex items-center gap-1 bg-[var(--fill-tsp-gray-main)] rounded-lg p-0.5">
            <button
              @click="editorViewMode = 'preview'"
              class="px-2 py-1 text-xs rounded-md transition-colors"
              :class="editorViewMode === 'preview'
                ? 'bg-[var(--background-white-main)] text-[var(--text-primary)] shadow-sm'
                : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'"
            >
              Preview
            </button>
            <button
              @click="editorViewMode = 'code'"
              class="px-2 py-1 text-xs rounded-md transition-colors"
              :class="editorViewMode === 'code'
                ? 'bg-[var(--background-white-main)] text-[var(--text-primary)] shadow-sm'
                : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'"
            >
              Code
            </button>
          </div>

          <!-- Right: Chart mode controls (inline in panel header) -->
          <div v-else-if="currentViewType === 'chart'" class="absolute right-3 flex items-center gap-2">
            <div class="flex items-center gap-1 p-0.5 rounded-md bg-[var(--background-gray-light)]">
              <button
                @click="chartViewMode = 'interactive'"
                class="px-2 py-1 text-xs rounded-md transition-colors"
                :class="chartViewMode === 'interactive'
                  ? 'bg-white dark:bg-[var(--code-block-bg)] text-[var(--text-primary)] shadow-sm'
                  : 'text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'"
                :disabled="!chartCanShowInteractive"
              >
                Interactive
              </button>
              <button
                @click="chartViewMode = 'static'"
                class="px-2 py-1 text-xs rounded-md transition-colors"
                :class="chartViewMode === 'static'
                  ? 'bg-white dark:bg-[var(--code-block-bg)] text-[var(--text-primary)] shadow-sm'
                  : 'text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'"
              >
                Static
              </button>
            </div>
            <span
              class="text-xs px-2 py-0.5 rounded bg-[var(--background-gray-light)] text-[var(--text-tertiary)]"
              title="Chart type"
            >
              {{ chartTypeBadge }}
            </span>
          </div>
        </div>

        <!-- Content Area: Dynamic content rendering -->
        <div class="flex-1 min-h-0 min-w-0 w-full overflow-hidden relative isolate">
          <!-- Persistent browser background — always mounted when session is active.
               Tool-specific views overlay on top so the browser stays connected
               and instantly available when switching back (no reconnection delay). -->
          <div
            v-if="showPersistentBrowser"
            class="absolute inset-0 bg-[var(--background-white-main)] flex flex-col items-stretch overflow-hidden"
            style="z-index: -1"
          >
            <!-- URL bar - top-anchored status bar, pushed above browser to not cover headers -->
            <Transition name="url-bar">
              <div v-if="showLivePreviewUrlBar" class="live-preview-url-bar">
                <div class="live-preview-url-status">
                  <Loader2 v-if="isActiveOperation" :size="10" class="live-preview-url-spinner" />
                  <Check v-else :size="10" />
                </div>
                <span class="live-preview-url-text">{{ livePreviewUrlBarText }}</span>
              </div>
            </Transition>

            <div class="flex-1 w-full min-h-0 relative">
              <LiveViewer
                :key="'live-preview-persistent-' + (sessionId || 'none')"
                :session-id="sessionId || ''"
                :enabled="true"
                :view-only="true"
                :is-canvas-mode="isCanvasMode"
                :show-controls="showBrowserControls"
                :is-session-complete="isSessionComplete"
                :replay-screenshot-url="props.replayScreenshotUrl || ''"
                @connected="onLivePreviewConnected"
                @disconnected="onLivePreviewDisconnected"
              />

              <!-- Reconnecting overlay -->
              <Transition name="fade">
                <LoadingState
                  v-if="livePreviewDisconnected && !!sessionId"
                  class="absolute inset-0 z-10 bg-[var(--background-white-main)]/90"
                  :label="livePreviewPlaceholderLabel || 'Reconnecting'"
                  :detail="livePreviewPlaceholderDetail"
                  :is-active="true"
                  animation="globe"
                />
              </Transition>
            </div>

            <!-- Take over button -->
            <button
              v-if="!isShare && !!props.sessionId"
              @click="takeOver"
              :disabled="takeoverLoading"
              class="takeover-btn absolute right-3 bottom-3 z-10 min-w-10 h-10 flex items-center justify-center rounded-full bg-[var(--background-white-main)] text-[var(--text-primary)] border border-[var(--border-main)] shadow-lg cursor-pointer hover:bg-[var(--text-brand)] hover:px-4 hover:text-[var(--text-onblack)] group transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <TakeOverIcon />
              <span class="text-sm max-w-0 overflow-hidden whitespace-nowrap opacity-0 transition-all duration-300 group-hover:max-w-[200px] group-hover:opacity-100 group-hover:ml-1">
                {{ $t('Take Over') }}
              </span>
            </button>
          </div>

          <!-- Streaming Report (live summary composition — highest priority) -->
          <div
            v-if="isSummaryPhase || summaryStreamText"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <StreamingReportView
              :text="summaryStreamText || ''"
              :is-final="!isSummaryStreaming"
            />
          </div>

          <!-- Unified Streaming View (tool execution streaming — second highest priority) -->
          <div
            v-else-if="shouldShowUnifiedStreaming"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <UnifiedStreamingView
              :text="toolContent.streaming_content || ''"
              :content-type="streamingContentType"
              :is-final="toolStatus === 'called'"
              :language="streamingLanguage"
              :tool-content="toolContent"
            />
          </div>

          <!-- Replay mode (user-navigated): when user stepped through the timeline
               (!realTime), show the browser screenshot for browser-type tools or
               unknown tools. Terminal, editor, search, and chart views show their
               own dedicated content — the screenshot would incorrectly show the
               browser state (e.g. Google) for a shell/terminal tool. -->
          <div
            v-else-if="isReplayMode && !realTime && !!replayScreenshotUrl && (currentViewType === 'live_preview' || !currentViewType)"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <ScreenshotReplayViewer
              :src="replayScreenshotUrl || ''"
              :metadata="replayMetadata || null"
            />
          </div>

          <!-- Replay mode loading (user-navigated): waiting for screenshot blob.
               Only shown for browser-type or unknown tools (same guard as above). -->
          <div
            v-else-if="isReplayMode && !realTime && !replayScreenshotUrl && (currentViewType === 'live_preview' || !currentViewType)"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <LoadingState
              label="Loading replay"
              :is-active="true"
              animation="globe"
            />
          </div>

          <!-- Live preview: persistent browser in background shows through (no overlay needed) -->
          <template v-else-if="currentViewType === 'live_preview' && showPersistentBrowser" />

          <!-- Live preview fallback: persistent browser gone but no replay yet — show last tool result -->
          <div v-else-if="currentViewType === 'live_preview'" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
            <GenericContentView
              :tool-name="toolContent?.name"
              :function-name="toolContent?.function"
              :args="toolContent?.args"
              :result="toolContent?.content?.result"
              :content="toolContent?.content"
              :is-executing="false"
            />
          </div>

          <!-- Terminal View -->
          <div v-else-if="currentViewType === 'terminal'" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
            <TerminalContentView
              :content="terminalContent"
              :content-type="terminalContentType"
              :is-live="isActiveOperation"
              :is-writing="isWriting"
              :auto-scroll="true"
              @new-content="onNewTerminalContent"
            />
          </div>

          <!-- Editor View -->
          <div v-else-if="currentViewType === 'editor'" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
            <EditorContentView
              :content="editorContent"
              :filename="fileName"
              :is-writing="isWriting"
              :is-loading="isEditorLoading"
              :view-mode="isHtmlFile ? editorViewMode : 'code'"
              :is-html-file="isHtmlFile"
            />
          </div>

          <!-- Search View -->
          <div v-else-if="currentViewType === 'search'" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
            <SearchContentView
              :results="searchResults"
              :is-searching="isSearching"
              :query="searchQuery"
              :explicit-results="searchResultsExplicit"
              @browseUrl="handleBrowseUrl"
            />
          </div>

          <!-- Chart View -->
          <div v-else-if="currentViewType === 'chart'" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
            <ChartToolView
              :session-id="sessionId || ''"
              :chart-content="toolContent"
              :live="isActiveOperation"
              :view-mode="chartViewMode"
              :show-header-controls="true"
              @update:viewMode="chartViewMode = $event"
            />
          </div>

          <!-- Generic/MCP View -->
          <div v-else-if="currentViewType === 'generic'" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
            <GenericContentView
              :tool-name="toolContent?.name"
              :function-name="toolContent?.function"
              :args="toolContent?.args"
              :result="toolContent?.content?.result"
              :content="toolContent?.content"
              :is-executing="isActiveOperation"
            />
          </div>

          <!-- Wide Research View (parallel multi-source search) -->
          <div v-else-if="currentViewType === 'wide_research'" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
            <WideResearchOverlay
              :state="wideResearchState"
              :always-show="true"
            />
          </div>

          <!-- Replay mode (auto-settled): session ended and no tool overlay matched above.
               This covers browser-type tools where the replay screenshot IS the content,
               or when the panel has no tool-specific view to display. -->
          <div
            v-else-if="isReplayMode && !!replayScreenshotUrl"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <ScreenshotReplayViewer
              :src="replayScreenshotUrl || ''"
              :metadata="replayMetadata || null"
            />
          </div>

          <!-- Replay mode loading (auto-settled): waiting for screenshot blob -->
          <div
            v-else-if="isReplayMode && !replayScreenshotUrl"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <LoadingState
              label="Loading replay"
              :is-active="true"
              animation="globe"
            />
          </div>

          <!-- Fallback: render GenericContentView when no persistent browser and no dedicated view -->
          <div v-else-if="!showPersistentBrowser" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
            <GenericContentView
              :tool-name="toolContent?.name"
              :function-name="toolContent?.function"
              :args="toolContent?.args"
              :result="toolContent?.content?.result"
              :content="toolContent?.content"
              :is-executing="isActiveOperation"
            />
          </div>
        </div>

        <!-- Timeline Controls — only render when timeline data exists -->
        <div v-if="showTimeline" class="mt-auto">
          <TimelineControls
            :progress="timelineProgress ?? 0"
            :current-timestamp="timelineTimestamp"
            :is-live="realTime"
            :is-replay-mode="!!isReplayMode"
            :can-step-forward="!!timelineCanStepForward"
            :can-step-backward="!!timelineCanStepBackward"
            :show-timestamp-on-interact="true"
            :screenshots="replayScreenshots"
            @jump-to-live="jumpToRealTime"
            @step-forward="handleStepForward"
            @step-backward="handleStepBackward"
            @seek-by-progress="handleSeekByProgress"
          />
        </div>
      </div>

      <!-- Task Progress Bar - outside content container, at bottom -->
      <div
        v-if="plan && plan.steps.length > 0"
        class="relative z-10 mt-3"
      >
        <TaskProgressBar
          :plan="plan"
          :isLoading="isLoading"
          :isThinking="isThinking"
          :showThumbnail="false"
          :defaultExpanded="false"
          :compact="true"
          :currentTool="currentToolForProgress"
          :toolContent="toolContent"
          :hideExpandedHeader="true"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, toRef, computed, watch, ref, onMounted, onUnmounted } from 'vue';
import { Minimize2, MonitorUp, X, Loader2, Check, BarChart3 } from 'lucide-vue-next';
import type { ToolContent } from '@/types/message';
import type { PlanEventData } from '@/types/event';
import { useContentConfig } from '@/composables/useContentConfig';
import { useStreamingPresentationState } from '@/composables/useStreamingPresentationState';
import { getToolDisplay, extractToolUrl } from '@/utils/toolDisplay';
import { viewFile, viewShellSession, browseUrl, startTakeover } from '@/api/agent';
import TimelineControls from '@/components/timeline/TimelineControls.vue';
import TakeOverIcon from '@/components/icons/TakeOverIcon.vue';
import TaskProgressBar from '@/components/TaskProgressBar.vue';

// Content views are async to avoid loading heavy dependencies until needed.
const LiveViewer = defineAsyncComponent(() => import('@/components/LiveViewer.vue'));
const LoadingState = defineAsyncComponent(() => import('@/components/toolViews/shared/LoadingState.vue'));
const TerminalContentView = defineAsyncComponent(() => import('@/components/toolViews/TerminalContentView.vue'));
const EditorContentView = defineAsyncComponent(() => import('@/components/toolViews/EditorContentView.vue'));
const SearchContentView = defineAsyncComponent(() => import('@/components/toolViews/SearchContentView.vue'));
const ChartToolView = defineAsyncComponent(() => import('@/components/toolViews/ChartToolViewEnhanced.vue'));
const GenericContentView = defineAsyncComponent(() => import('@/components/toolViews/GenericContentView.vue'));
const StreamingReportView = defineAsyncComponent(() => import('@/components/toolViews/StreamingReportView.vue'));
const UnifiedStreamingView = defineAsyncComponent(() => import('@/components/toolViews/UnifiedStreamingView.vue'));
const WideResearchOverlay = defineAsyncComponent(() => import('@/components/WideResearchOverlay.vue'));
const ScreenshotReplayViewer = defineAsyncComponent(() => import('@/components/ScreenshotReplayViewer.vue'));
import { useWideResearchGlobal } from '@/composables/useWideResearch';
import { normalizeSearchResults } from '@/utils/searchResults';
import { isCanvasDomainTool } from '@/utils/viewRouting';
import type { SearchResultsEnvelope, SearchResultsPayload } from '@/types/search';
import type { ScreenshotMetadata } from '@/types/screenshot';
import { detectContentType, detectLanguage, type StreamingContentType } from '@/types/streaming';

import type { ContentViewType } from '@/constants/tool';

const props = defineProps<{
  sessionId?: string;
  realTime: boolean;
  toolContent: ToolContent;
  live: boolean;
  isShare: boolean;
  showTimeline?: boolean;
  timelineProgress?: number;
  timelineTimestamp?: number;
  timelineCanStepForward?: boolean;
  timelineCanStepBackward?: boolean;
  plan?: PlanEventData;
  isLoading?: boolean;
  isThinking?: boolean;
  isReplayMode?: boolean;
  replayScreenshotUrl?: string;
  replayMetadata?: ScreenshotMetadata | null;
  replayScreenshots?: ScreenshotMetadata[];
  summaryStreamText?: string;
  isSummaryStreaming?: boolean;
  /** When true, hides the frame header and outer card styling (used inside WorkspacePanel) */
  embedded?: boolean;
  /** Override the auto-detected content view type (used for workspace tab switching) */
  forceViewType?: ContentViewType;
}>();

// Computed for TaskProgressBar current tool
const currentToolForProgress = computed(() => {
  if (!props.toolContent) return null;
  const display = getToolDisplay({
    name: props.toolContent.name,
    function: props.toolContent.function,
    args: props.toolContent.args,
    display_command: props.toolContent.display_command
  });
  return {
    name: display.displayName,
    function: display.actionLabel,
    functionArg: display.resourceLabel,
    status: props.toolContent.status,
    icon: display.icon
  };
});


// Wide research state
const { overlayState: wideResearchState } = useWideResearchGlobal();

// Get content config for unified tabs
const {
  contentConfig,
  viewModeIndex,
  currentViewType: computedViewType,
  hasNewOutput,
  setViewModeByIndex,
  markNewOutput
} = useContentConfig(toRef(props, 'toolContent'));

// Override view type when browsing from search results
const forceBrowserView = ref(false);
const shouldShowArtifactEditor = computed(() => {
  if (!isArtifactTool.value) return false;
  return !!artifactInlineContent.value || !!resolvedFilePath.value;
});

const currentViewType = computed(() => {
  if (props.forceViewType) return props.forceViewType;
  if (forceBrowserView.value) return 'live_preview';
  if (shouldShowArtifactEditor.value) return 'editor';
  return computedViewType.value;
});

// Tool state
const toolName = computed(() => props.toolContent?.name || '');
const toolFunction = computed(() => props.toolContent?.function || '');
const toolStatus = computed(() => props.toolContent?.status || '');
const isCanvasMode = computed(() => isCanvasDomainTool(props.toolContent));
/** Show floating browser controls only in Canvas mode or standalone (non-embedded) */
const showBrowserControls = computed(() => {
  if (!props.embedded) return true;
  // In workspace embedded mode, only show controls when Canvas tab is active
  return !!props.forceViewType;
});
const chartViewMode = ref<'interactive' | 'static'>('interactive');

// HTML file detection and editor view mode (Code / Preview)
const HTML_PREVIEW_EXTENSIONS = new Set(['.html', '.htm', '.svg']);
const isHtmlFile = computed(() => {
  const name = fileName.value.toLowerCase();
  if (!name) return false;
  const dotIdx = name.lastIndexOf('.');
  if (dotIdx < 0) return false;
  return HTML_PREVIEW_EXTENSIONS.has(name.slice(dotIdx));
});
const editorViewMode = ref<'code' | 'preview'>('preview');

const chartPayload = computed(() => {
  return (props.toolContent?.content || {}) as Record<string, unknown>;
});

const chartCanShowInteractive = computed(() => {
  if (currentViewType.value !== 'chart') return false;
  const htmlFileId = chartPayload.value.html_file_id;
  const jsonFileId = chartPayload.value.plotly_json_file_id;
  const hasHtml = typeof htmlFileId === 'string' && htmlFileId.length > 0;
  const hasJson = typeof jsonFileId === 'string' && jsonFileId.length > 0;
  return hasHtml || hasJson;
});

const chartTypeBadge = computed(() => {
  const chartType = chartPayload.value.chart_type;
  if (typeof chartType !== 'string' || !chartType) return 'Chart';
  return chartType
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
});

// Unified streaming detection
const shouldShowUnifiedStreaming = computed(() => {
  // Only show streaming for live sessions with streaming content
  if (!props.live || !props.toolContent?.streaming_content) return false;
  // Don't interfere with summary streaming
  if (isSummaryPhase.value || props.summaryStreamText) return false;
  // Search tools stream the query string (not JSON results) — let SearchContentView handle them
  if (streamingContentType.value === 'search') return false;
  return true;
});

const streamingContentType = computed((): StreamingContentType => {
  if (!props.toolContent) return 'text';
  return detectContentType(props.toolContent.function);
});

const streamingLanguage = computed(() => {
  if (!props.toolContent) return 'text';
  // Detect from file path if available
  const filePath = props.toolContent.args?.file || props.toolContent.args?.path || props.toolContent.file_path;
  if (typeof filePath === 'string') {
    return detectLanguage(filePath);
  }
  // Detect from function name
  const fn = props.toolContent.function;
  if (fn.includes('python')) return 'python';
  if (fn.includes('javascript')) return 'javascript';
  if (fn.includes('bash') || fn.includes('shell')) return 'bash';
  return 'text';
});

// Artifact tools (report outputs saved via code executor)
const isArtifactTool = computed(() => {
  return toolName.value === 'code_executor' && (
    toolFunction.value === 'code_save_artifact' ||
    toolFunction.value === 'code_read_artifact'
  );
});

const artifactInlineContent = computed(() => {
  if (!isArtifactTool.value) return '';
  // Prefer streaming_content (from tool_stream event) for instant preview
  if (props.toolContent?.streaming_content) return props.toolContent.streaming_content;
  const argContent = props.toolContent?.args?.content;
  if (typeof argContent === 'string' && argContent.length > 0) return argContent;
  const payload = props.toolContent?.content as { content?: unknown } | undefined;
  if (payload && typeof payload.content === 'string') return payload.content;
  return '';
});

const artifactFilePath = computed(() => {
  if (!isArtifactTool.value) return '';
  if (props.toolContent?.file_path) return String(props.toolContent.file_path);
  const payload = props.toolContent?.content as { path?: unknown } | undefined;
  if (payload && typeof payload.path === 'string') return payload.path;
  return '';
});

const resolvedFilePath = computed(() => {
  if (toolName.value === 'file') {
    return String(props.toolContent?.args?.file || props.toolContent?.file_path || '');
  }
  if (isArtifactTool.value) {
    return artifactFilePath.value;
  }
  return '';
});

const toolDisplay = computed(() => {
  if (!props.toolContent) return null;
  return getToolDisplay({
    name: props.toolContent.name,
    function: props.toolContent.function,
    args: props.toolContent.args,
    display_command: props.toolContent.display_command
  });
});

// Activity detection
const isActiveOperation = computed(() => {
  return toolStatus.value === 'calling' || toolStatus.value === 'running';
});

// File operations
const isFileWriting = computed(() => {
  return toolFunction.value === 'file_write' && toolStatus.value === 'calling';
});

const isArtifactWriting = computed(() => {
  return isArtifactTool.value && toolFunction.value === 'code_save_artifact' && toolStatus.value === 'calling';
});

const isWriting = computed(() => isFileWriting.value || isArtifactWriting.value);

const isSearching = computed(() => {
  // Unified search detection - all search operations under one status
  const isSearchTool = toolDisplay.value?.toolKey === 'search' || toolDisplay.value?.toolKey === 'wide_research';
  return isSearchTool && toolStatus.value === 'calling';
});

watch(
  () => props.toolContent?.tool_call_id,
  () => {
    chartViewMode.value = 'interactive';
    editorViewMode.value = 'preview';
  },
  { immediate: true }
);

watch(
  chartCanShowInteractive,
  (canShowInteractive) => {
    if (!canShowInteractive && chartViewMode.value === 'interactive') {
      chartViewMode.value = 'static';
    }
  },
  { immediate: true }
);

/**
 * Tool subtitle - Pythinker-style standardized format: "Verb Resource"
 * @see docs/guides/TOOL_STANDARDIZATION.md
 */
const toolSubtitle = computed(() => toolDisplay.value?.description || '');

const cleanActivitySubtitle = (value: string): string => {
  return value
    .replace(/\s+\|\s*(?:undefined|null|none|nan)\s*$/i, '')
    .replace(/\s+(?:undefined|null|none|nan)\s*$/i, '')
    .replace(/^\s*(?:undefined|null|none|nan)\s*\|\s*/i, '')
    .replace(/\s{2,}/g, ' ')
    .replace(/\s+\|\s*$/, '')
    .trim();
};

const streamingPresentation = useStreamingPresentationState({
  isInitializing: computed(() => false),
  isSummaryStreaming: computed(() => !!props.isSummaryStreaming),
  summaryStreamText: computed(() => props.summaryStreamText || ''),
  isThinking: computed(() => !!props.isThinking),
  isActiveOperation: computed(() => isActiveOperation.value),
  toolDisplayName: computed(() => toolDisplay.value?.displayName || ''),
  toolDescription: computed(() => toolSubtitle.value || ''),
  baseViewType: computed(() => {
    if (currentViewType.value === 'terminal' || currentViewType.value === 'editor' || currentViewType.value === 'search') {
      return currentViewType.value;
    }
    if (currentViewType.value === 'live_preview') {
      return 'live_preview';
    }
    return 'generic';
  }),
  isSessionComplete: computed(() => !props.isLoading && !!props.replayScreenshotUrl),
  replayScreenshotUrl: computed(() => props.replayScreenshotUrl || ''),
  previewText: computed(() => props.summaryStreamText || '')
});

const isSummaryPhase = computed(() => streamingPresentation.isSummaryPhase.value);
const isSessionComplete = computed(() => !props.isLoading && !!props.replayScreenshotUrl);

const activityHeadline = computed(() => {
  if (isSummaryPhase.value) return streamingPresentation.headline.value;
  if (toolDisplay.value?.displayName) {
    // Distinguish active vs completed tools so the headline reflects reality
    if (isActiveOperation.value) return `Pythinker is using ${toolDisplay.value.displayName}`;
    return `Used ${toolDisplay.value.displayName}`;
  }
  if (props.isThinking) return streamingPresentation.headline.value;
  return '';
});

const activitySubtitle = computed(() => {
  if (isSummaryPhase.value) return '';
  return cleanActivitySubtitle(toolSubtitle.value);
});

const showActivitySpinner = computed(() => isSummaryPhase.value || (!!props.isThinking && !toolDisplay.value));

// Content header label - consistent, user-friendly tool name
const contentHeaderLabel = computed(() => {
  if (currentViewType.value === 'editor') {
    const nameArg = props.toolContent?.args?.filename;
    if (typeof nameArg === 'string' && nameArg) return nameArg;
    if (resolvedFilePath.value) {
      const parts = resolvedFilePath.value.split('/');
      const name = parts[parts.length - 1] || '';
      if (name) return name;
    }
  }
  return toolDisplay.value?.displayName || '';
});

const showLivePreviewPlaceholder = computed(() => {
  if (forceBrowserView.value) return false;
  if (!props.sessionId) return true;
  // NOTE: livePreviewDisconnected is handled as an overlay now,
  // not a replacement — keeping LiveViewer mounted allows its
  // internal reconnect logic to work instead of deadlocking.
  return false;
});

const livePreviewPlaceholderLabel = computed(() => {
  if (!props.sessionId) return 'No live session';
  if (livePreviewDisconnected.value) return 'Reconnecting';
  return 'Connecting';
});

const livePreviewPlaceholderDetail = computed(() => {
  if (!props.sessionId) return 'Open a session to view the screen.';
  if (livePreviewDisconnected.value) return 'Waiting for the live stream.';
  return '';
});

/** Keep the browser CDP stream mounted when a session is active.
 * Tool-specific views (editor, terminal, etc.) overlay on top, so the
 * browser is instantly available when switching back — no reconnection. */
const showPersistentBrowser = computed(() => {
  // Keep browser mounted until replay mode takes over.
  // Previously this also checked !isSessionComplete — but that caused a blank flash
  // between session completion and screenshot load (the persistent browser hid while
  // the replay viewer wasn't ready yet). LiveViewer already handles the frozen state
  // via its :is-session-complete prop.
  return !!props.sessionId && !props.isReplayMode
})

// ============ URL Bar Overlay ============
const BROWSER_TOOL_PREFIXES = ['browser', 'playwright', 'browsing'];
const isBrowserTool = (name: string) =>
  BROWSER_TOOL_PREFIXES.some(prefix => name.startsWith(prefix));

const resolvedBrowserUrl = computed(() => {
  // Prefer explicit URL from tool args (e.g. go_to_url → args.url)
  const explicitUrl = extractToolUrl(props.toolContent?.args);
  if (explicitUrl) return explicitUrl;
  // Fall back to resourceLabel only if it looks like a URL (not a bare number/index)
  const label = toolDisplay.value?.resourceLabel || '';
  if (label && /[./]/.test(label)) return label;
  return '';
});

const showLivePreviewUrlBar = computed(() => {
  if (showLivePreviewPlaceholder.value) return false;
  return isBrowserTool(toolName.value) && !!resolvedBrowserUrl.value;
});

const livePreviewUrlBarText = computed(() => {
  const url = resolvedBrowserUrl.value;
  if (!url) return '';
  // Format the URL for display (strip protocol, truncate)
  try {
    const u = new URL(url);
    const display = `${u.hostname}${u.pathname}`;
    return display.length > 60 ? `${display.slice(0, 60)}...` : display;
  } catch {
    return url.length > 60 ? `${url.slice(0, 60)}...` : url;
  }
});

// ============ Terminal Content ============
const shellOutput = ref('');
const refreshTimer = ref<number | null>(null);

const terminalContentType = computed<'shell' | 'file' | 'browser' | 'code' | 'generic'>(() => {
  if (toolName.value === 'shell') return 'shell';
  if (toolName.value === 'code_executor' || toolName.value === 'code_execute') return 'code';
  if (toolName.value === 'file') return 'file';
  if (toolName.value === 'browser' || toolName.value === 'browser_agent') return 'browser';
  return 'generic';
});

const terminalContent = computed(() => {
  // Shell/Code executor output
  if (toolName.value === 'shell' || toolName.value === 'code_executor' || toolName.value === 'code_execute') {
    if (shellOutput.value) return shellOutput.value;

    // Get command from multiple sources - prefer args.command for shell tools
    const argsCommand = props.toolContent?.args?.command;
    const directCommand = props.toolContent?.command;
    const command = argsCommand || directCommand;

    const stdout = props.toolContent?.stdout;
    const stderr = props.toolContent?.stderr;
    const exitCode = props.toolContent?.exit_code;

    // Build output - always show command if available (even during execution)
    let output = '';
    if (command) {
      output += `$ ${command}\n`;
    }
    if (stdout) {
      output += `${stdout}\n`;
    }
    if (stderr) {
      output += `[stderr]\n${stderr}\n`;
    }
    if (exitCode !== undefined && exitCode !== null) {
      output += `[exit code: ${exitCode}]\n`;
    }

    // Return if we have any output
    if (output.trim()) {
      return output.trimEnd();
    }

    const content = props.toolContent?.content;
    if (!content) {
      // During execution, show a message indicating the command is running
      if (isActiveOperation.value && command) {
        return `$ ${command}\n[executing...]`;
      }
      // For code execution, show streaming code preview if available
      if (isActiveOperation.value && props.toolContent?.streaming_content) {
        return props.toolContent.streaming_content;
      }
      return '';
    }

    // Shell console output (array format) - use ANSI colors
    if (content.console && Array.isArray(content.console)) {
      return formatShellOutput(content.console);
    }

    // String console output
    if (typeof content.console === 'string') return content.console;

    // Code executor output
    if (content.stdout) return content.stdout + (content.stderr ? '\n[stderr]\n' + content.stderr : '');

    return '';
  }

  // File content
  if (toolName.value === 'file') {
    if (isFileWriting.value) {
      return props.toolContent?.args?.content || props.toolContent?.content?.content || '';
    }
    return props.toolContent?.content?.content || '';
  }

  // Browser content
  if (toolName.value === 'browser' || toolName.value === 'browser_agent') {
    return props.toolContent?.content?.content || '';
  }

  // Generic
  const content = props.toolContent?.content;
  if (!content) return '';
  if (typeof content === 'string') return content;
  return JSON.stringify(content, null, 2);
});

// ANSI escape codes for terminal colors
const ANSI_GREEN = '\x1b[32m';
const ANSI_RESET = '\x1b[0m';

// Format shell output with ANSI color codes for prompt
const formatShellOutput = (console: Array<{ ps1?: string; command?: string; output?: string }>) => {
  let output = '';
  for (const e of console) {
    // Green prompt (ANSI escape code)
    if (e.ps1) {
      output += `${ANSI_GREEN}${e.ps1}${ANSI_RESET} `;
    }
    if (e.command) {
      output += `${e.command}\n`;
    }
    if (e.output) {
      output += `${e.output}\n`;
    }
  }
  return output;
};

// Load shell content via API
const loadShellContent = async () => {
  const shellSessionId = props.toolContent?.args?.id;
  if (!props.live || !shellSessionId || !props.sessionId) {
    // Use content from props
    const content = props.toolContent?.content;
    if (content?.console && Array.isArray(content.console)) {
      shellOutput.value = formatShellOutput(content.console);
    }
    return;
  }

  try {
    const response = await viewShellSession(props.sessionId, shellSessionId);
    if (response?.console) {
      shellOutput.value = formatShellOutput(response.console);
    }
  } catch {
    // Shell content load failed - UI shows last known content
  }
};

// Start auto-refresh timer for shell (only when streaming not available)
const startAutoRefresh = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
  }
  // Skip polling if unified streaming is active
  if (shouldShowUnifiedStreaming.value) {
    return;
  }
  if (props.live && (toolName.value === 'shell' || toolName.value === 'code_executor' || toolName.value === 'code_execute')) {
    refreshTimer.value = setInterval(loadShellContent, 5000);
  }
};

const stopAutoRefresh = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
    refreshTimer.value = null;
  }
};

// Watch for tool changes
watch(() => props.toolContent, () => {
  if (toolName.value === 'shell' || toolName.value === 'code_executor' || toolName.value === 'code_execute') {
    // Skip loading if streaming is active
    if (!shouldShowUnifiedStreaming.value) {
      loadShellContent();
    }
  }
});

// Watch for streaming state changes to toggle polling
watch(shouldShowUnifiedStreaming, (isStreaming) => {
  if (isStreaming) {
    // Stop polling when streaming becomes active
    stopAutoRefresh();
  } else {
    // Resume polling when streaming stops
    startAutoRefresh();
  }
});

// Reset forceBrowserView when tool changes (new tool selected)
watch(() => props.toolContent?.tool_call_id, () => {
  forceBrowserView.value = false;
});

watch(() => props.live, (live) => {
  if (live) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
});

onMounted(() => {
  if (toolName.value === 'shell' || toolName.value === 'code_executor' || toolName.value === 'code_execute') {
    loadShellContent();
  }
  startAutoRefresh();
});

onUnmounted(() => {
  stopAutoRefresh();
});

// ============ Editor Content ============
const fileContent = ref('');
const originalContent = ref('');
const livePreviewDisconnected = ref(false);

const getToolContentText = () => {
  const content = props.toolContent?.content;
  if (!content) return '';
  if (typeof content === 'string') return content;
  if (typeof (content as { content?: unknown }).content === 'string') {
    return (content as { content: string }).content;
  }
  return '';
};

const fileName = computed(() => {
  const file = props.toolContent?.args?.file;
  if (file) return String(file).split('/').pop() || '';
  const filename = props.toolContent?.args?.filename;
  if (typeof filename === 'string' && filename) return filename;
  if (resolvedFilePath.value) {
    const parts = resolvedFilePath.value.split('/');
    return parts[parts.length - 1] || '';
  }
  return '';
});

const editorContent = computed(() => {
  if (isArtifactTool.value) {
    return fileContent.value || artifactInlineContent.value || '';
  }

  // For file view modes
  if (toolName.value !== 'file') return '';

  // Modified view (primary)
  if (viewModeIndex.value === 0) {
    if (isFileWriting.value) {
      // Prefer streaming_content (from tool_stream event) for instant preview
      const streamContent = props.toolContent?.streaming_content || '';
      const argContent = typeof props.toolContent?.args?.content === 'string'
        ? props.toolContent?.args?.content
        : '';
      return streamContent || argContent || getToolContentText() || fileContent.value;
    }
    return fileContent.value || getToolContentText() || '';
  }

  // Original view (secondary)
  if (viewModeIndex.value === 1) {
    return originalContent.value || fileContent.value;
  }

  // Diff view (tertiary)
  if (viewModeIndex.value === 2) {
    if (props.toolContent?.diff) {
      return props.toolContent.diff;
    }
    return buildSimpleDiff(originalContent.value, fileContent.value);
  }

  return fileContent.value;
});

const isEditorLoading = computed(() => {
  if (!(toolName.value === 'file' || isArtifactTool.value)) return false;
  if (!isWriting.value) return false;
  return editorContent.value.trim().length === 0;
});

const buildSimpleDiff = (original: string, modified: string): string => {
  if (!original && !modified) return "";
  if (!original) return `+ ${modified}`;
  if (!modified) return `- ${original}`;

  const originalLines = original.split('\n');
  const modifiedLines = modified.split('\n');
  const maxLines = Math.max(originalLines.length, modifiedLines.length);
  const out: string[] = [];

  for (let i = 0; i < maxLines; i += 1) {
    const a = originalLines[i];
    const b = modifiedLines[i];
    if (a === b) {
      out.push(`  ${a ?? ''}`);
    } else {
      if (a !== undefined) out.push(`- ${a}`);
      if (b !== undefined) out.push(`+ ${b}`);
    }
  }

  return out.join('\n');
};

// Load file content
const loadFileContent = async () => {
  const filePath = resolvedFilePath.value;

  // During file_write, show streaming content
  if (toolName.value === 'file' && isFileWriting.value) {
    const argContent = typeof props.toolContent?.args?.content === 'string'
      ? props.toolContent?.args?.content
      : '';
    const streamingContent = getToolContentText() || argContent || '';
    if (fileContent.value && fileContent.value !== streamingContent) {
      originalContent.value = fileContent.value;
    }
    fileContent.value = streamingContent;
    return;
  }

  // Artifact preview (report files saved via code executor)
  if (isArtifactTool.value) {
    const inlineContent = artifactInlineContent.value;
    if (inlineContent) {
      fileContent.value = inlineContent;
    }
    if (!props.live || !filePath || !props.sessionId) return;
    if (!filePath.startsWith('/')) return;

    try {
      const response = await viewFile(props.sessionId, filePath);
      fileContent.value = response.content;
    } catch {
      // File content load failed - UI shows last known content
    }
    return;
  }

  if (!props.live) {
    const nextContent = getToolContentText() || '';
    if (fileContent.value && fileContent.value !== nextContent) {
      originalContent.value = fileContent.value;
    }
    fileContent.value = nextContent;
    return;
  }

  if (!filePath || !props.sessionId) return;

  try {
    const response = await viewFile(props.sessionId, filePath);
    const nextContent = response.content;
    if (fileContent.value && fileContent.value !== nextContent) {
      originalContent.value = fileContent.value;
    }
    fileContent.value = nextContent;
  } catch {
    // File content load failed - UI shows last known content
  }
};

// Watch file changes
watch(() => props.toolContent?.args?.file, (newFile) => {
  if (newFile && toolName.value === 'file') {
    loadFileContent();
  }
});

watch(() => props.toolContent?.status, () => {
  if (toolName.value === 'file') {
    loadFileContent();
  }
});

watch(() => props.toolContent?.args?.content, () => {
  if (toolName.value === 'file' && isFileWriting.value) {
    loadFileContent();
  }
});

// Artifact content updates
watch(() => props.toolContent?.file_path, () => {
  if (isArtifactTool.value) {
    loadFileContent();
  }
});

watch(() => props.toolContent?.args?.content, () => {
  if (isArtifactTool.value) {
    loadFileContent();
  }
});

watch(() => toolFunction.value, () => {
  if (isArtifactTool.value) {
    loadFileContent();
  }
});

onMounted(() => {
  if (toolName.value === 'file' || isArtifactTool.value) {
    loadFileContent();
  }
});

// Confirmation state watcher removed

// ============ Search Content ============
const searchResultsNormalized = computed(() => {
  return normalizeSearchResults(
    props.toolContent?.content as SearchResultsEnvelope | SearchResultsPayload | undefined
  );
});

const searchResults = computed(() => searchResultsNormalized.value.results);

const searchResultsExplicit = computed(() => searchResultsNormalized.value.explicit);

const searchQuery = computed(() => {
  const args = props.toolContent?.args || {};
  return (
    args.query ||
    args.topic ||
    args.url ||
    args.text ||
    args.input ||
    args.task ||
    ''
  );
});

// ============ Event Handlers ============
const emit = defineEmits<{
  (e: 'jumpToRealTime'): void,
  (e: 'hide'): void
  (e: 'stepForward'): void
  (e: 'stepBackward'): void
  (e: 'seekByProgress', progress: number): void
}>();

const hide = () => {
  emit('hide');
};

const takeoverLoading = ref(false);

const takeOver = async () => {
  if (!props.sessionId || takeoverLoading.value) return;

  takeoverLoading.value = true;
  try {
    // Pause agent first via takeover API
    const status = await startTakeover(props.sessionId, 'manual');

    // Only enter takeover UI when backend confirms agent is paused
    if (status.takeover_state !== 'takeover_active') return;

    window.dispatchEvent(new CustomEvent('takeover', {
      detail: { sessionId: props.sessionId, active: true }
    }));
  } catch {
    // Takeover start failed — agent was not paused, don't enter takeover mode
  } finally {
    takeoverLoading.value = false;
  }
};

const jumpToRealTime = () => {
  forceBrowserView.value = false; // Reset forced view so live tool determines view type
  emit('jumpToRealTime');
};

const handleStepForward = () => {
  emit('stepForward');
};

const handleStepBackward = () => {
  emit('stepBackward');
};

const handleSeekByProgress = (progress: number) => {
  emit('seekByProgress', progress);
};

const onLivePreviewConnected = () => {
  livePreviewDisconnected.value = false;
};
const onLivePreviewDisconnected = () => {
  livePreviewDisconnected.value = true;
};

const onNewTerminalContent = () => {
  markNewOutput();
};

/**
 * Handle browse URL request from search results
 * Navigates the browser directly to the clicked URL
 * Switches to browser/live-preview view immediately and listens to SSE events
 */
const handleBrowseUrl = async (url: string) => {
  if (!props.sessionId || !url) return;

  try {
    // Immediately switch to browser view
    forceBrowserView.value = true;

    // Subscribe to SSE events from the browse endpoint
    await browseUrl(props.sessionId, url, {
      onToolEvent: () => {
        // The SandboxViewer will automatically show the browser content
        // as it's already connected via CDP screencast
      },
      onMessage: () => {
        // Message received from browse - no action needed
      },
      onClose: () => {
        // Keep browser view active after navigation completes
      },
      onError: () => {
        // On error, optionally revert to previous view
        // forceBrowserView.value = false;
      }
    });
  } catch {
    forceBrowserView.value = false;
  }
};

</script>

<style scoped>
/* Reconnecting overlay fade transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.panel-content-header {
  box-shadow: inset 0 1px 0 0 var(--border-white);
}

/* URL bar — top-anchored, pill style that pushes browser down. */
.live-preview-url-bar {
  margin: 10px auto;
  flex-shrink: 0;
  z-index: 5;
  display: inline-flex;
  align-items: center;
  width: fit-content;
  max-width: calc(100% - 16px);
  gap: 5px;
  padding: 4px 9px 4px 7px;
  border-radius: 6px;
  background: rgba(15, 15, 18, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(12px) saturate(160%);
  -webkit-backdrop-filter: blur(12px) saturate(160%);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
}

.live-preview-url-status {
  flex-shrink: 0;
  color: rgba(255, 255, 255, 0.55);
  display: flex;
  align-items: center;
  line-height: 1;
}

.live-preview-url-spinner {
  animation: live-preview-spin 0.9s linear infinite;
}

@keyframes live-preview-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.live-preview-url-text {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.78);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-sans);
  letter-spacing: 0.01em;
}

/* Slide-down / fade-up transition */
.url-bar-enter-active {
  transition: opacity 0.18s ease, transform 0.18s ease, margin-top 0.18s ease;
}
.url-bar-leave-active {
  transition: opacity 0.14s ease, transform 0.14s ease, margin-top 0.14s ease;
}
.url-bar-enter-from,
.url-bar-leave-to {
  opacity: 0;
  margin-top: -30px;
}
</style>
