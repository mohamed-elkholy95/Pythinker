<template>
  <div
    class="flex h-full w-full"
    :class="{ 'panel-outer-frame': !embedded }"
  >
    <div :class="['flex-1 min-w-0 flex flex-col h-full', embedded ? 'px-3 pb-3' : 'p-4']">
      <!-- Frame Header: Pythinker's Computer + activity + window controls -->
      <div v-if="!embedded" class="panel-frame-header">
        <div class="flex flex-col gap-0.5 flex-1 min-w-0">
          <div class="text-[var(--text-primary)] text-[15px] font-semibold leading-snug">{{ $t("Pythinker's Computer") }}</div>
          <div v-if="activityHeadline" class="panel-activity-line">
            <span
              v-if="showReportActivityIcon"
              class="panel-report-activity-icon"
              :class="{
                'panel-report-activity-icon-streaming': isSummaryStreaming,
                'panel-report-activity-icon-ready': !isSummaryStreaming,
              }"
              aria-hidden="true"
            >
              <FileText
                :size="13"
                class="panel-report-activity-glyph"
              />
              <span class="panel-report-activity-accent"></span>
            </span>
            <PencilLine
              v-else-if="showPlanActivityIcon"
              :size="13"
              class="flex-shrink-0 text-[var(--icon-secondary)]"
              :class="{ 'animate-pulse': isPlanStreaming }"
            />
            <Loader2
              v-else-if="showActivitySpinner"
              :size="13"
              class="flex-shrink-0 text-[var(--icon-secondary)]"
              :class="{ 'animate-spin': isSummaryStreaming }"
            />
            <component
              v-else-if="toolDisplay?.icon"
              :is="toolDisplay.icon"
              :size="13"
              class="flex-shrink-0 text-[var(--icon-secondary)]"
            />
            <span class="flex-shrink-0 whitespace-nowrap">{{ activityHeadline }}</span>
            <span v-if="activitySubtitle" class="panel-activity-separator">&middot;</span>
            <span v-if="activitySubtitle" class="truncate min-w-0 panel-activity-detail">{{ activitySubtitle }}</span>
          </div>
        </div>
        <div class="flex items-center gap-1">
          <button
            v-if="!!props.sessionId"
            class="panel-control-btn"
            @click="takeOver"
            :disabled="takeoverLoading"
            aria-label="Open takeover"
          >
            <MonitorUp class="w-4 h-4" />
          </button>
          <button
            class="panel-control-btn"
            @click="hide"
            aria-label="Minimize"
          >
            <Minimize2 class="w-4 h-4" />
          </button>
          <button
            class="panel-control-btn"
            @click="hide"
            aria-label="Close"
          >
            <X class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- Content Container with rounded frame -->
      <div
        :class="[
          'relative flex flex-col overflow-hidden bg-[var(--background-white-main)] flex-1 min-h-0',
          embedded
            ? 'rounded-[10px] border border-[var(--border-light)] mt-2'
            : 'panel-content-container rounded-[12px] border border-[var(--border-light)] shadow-[0px_4px_16px_var(--shadow-XS)] mt-2'
        ]">

        <!-- URL Status Bar (browser views — replaces content header) -->
        <div v-if="showUrlStatusBar" class="url-status-bar">
          <span class="url-status-text">{{ resolvedBrowserUrl || '/' }}</span>
        </div>

        <!-- Content Header: Centered operation label + View mode tabs.
             Hidden for browser views when URL bar is active, or embedded without forced view mode. -->
        <div
          v-if="(contentConfig || showReportPresentation || showPlanPresentation) && (!embedded || forceViewType) && !showUrlStatusBar"
          class="panel-content-header">

          <!-- Center: Context text (Manus-style — plain centered text, no icons) -->
          <div class="context-bar-label">
            <span>{{ contentHeaderLabel }}</span>
          </div>

          <!-- Right: View mode tabs — hidden during report presentation (report overlay covers the content area,
               so switching view modes would be confusing — the user is viewing the report, not the tool) -->
          <div v-if="contentConfig?.showTabs && !showReportPresentation" class="absolute right-3 flex items-center gap-1 bg-[var(--fill-tsp-gray-main)] rounded-lg p-0.5">
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

          <!-- Right: HTML Code/Preview tabs (inline in panel header) — hidden during report -->
          <div v-else-if="currentViewType === 'editor' && isHtmlFile && !showReportPresentation" class="absolute right-3 flex items-center gap-1 bg-[var(--fill-tsp-gray-main)] rounded-lg p-0.5">
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

          <!-- Right: Chart mode controls (inline in panel header) — hidden during report -->
          <div v-else-if="currentViewType === 'chart' && !showReportPresentation" class="absolute right-3 flex items-center gap-2">
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

          <!-- Connection status removed — Manus-style minimal content header -->
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
            <div class="flex-1 w-full min-h-0 relative">
              <LiveViewer
                ref="liveViewerRef"
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

            <!-- Take over button (Manus-style floating action) -->
            <button
              v-if="!isShare && !!props.sessionId"
              @click="takeOver"
              :disabled="takeoverLoading"
              class="takeover-fab"
            >
              <TakeOverIcon />
              <span class="takeover-fab-label">
                {{ $t('Take Over') }}
              </span>
            </button>
          </div>

          <!-- Content view crossfade transition — keyed by activeViewKey.
               When activeViewKey is null (live-preview pass-through), no wrapper
               renders and the persistent browser shows through unobstructed. -->
          <Transition name="panel-crossfade">
            <div
              v-if="activeViewKey"
              :key="activeViewKey"
              data-testid="panel-transition-shell"
              class="absolute inset-0"
            >
              <!-- Streaming Report — rendered inside EditorContentView (highest priority) -->
              <div
                v-if="showReportPresentation"
                data-testid="report-overlay"
                class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
              >
                <EditorContentView
                  :content="reportPresentationText"
                  filename="Report.md"
                  :is-writing="isSummaryStreaming"
                />
              </div>

              <!-- Planning Overlay — styled step cards instead of raw markdown -->
              <div
                v-else-if="planEditorContent.length > 0"
                data-testid="plan-overlay"
                class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
              >
                <PlanPresentationView
                  :plan="props.plan"
                  :streaming-text="planEditorContent"
                  :is-streaming="isPlanningTool || !!props.isPlanStreaming"
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

              <!-- Pre-reply loading skeleton: shown for chart/generic and unknown views
                   while the tool is actively calling and has no streaming content yet. -->
              <div
                v-else-if="showLiveViewSkeleton"
                class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
              >
                <div class="live-view-skeleton">
                  <div class="lv-skel-line lv-skel-line--xl" />
                  <div class="lv-skel-line lv-skel-line--lg" />
                  <div class="lv-skel-line lv-skel-line--sm" />
                  <div class="lv-skel-block" />
                  <div class="lv-skel-line lv-skel-line--md" />
                  <div class="lv-skel-line lv-skel-line--lg" />
                  <div class="lv-skel-line lv-skel-line--sm" />
                </div>
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

              <!-- Live preview fallback: persistent browser gone but no replay yet — show last tool result -->
              <div v-else-if="currentViewType === 'live_preview'" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
                <GenericContentView
                  :tool-name="toolContent?.name"
                  :function-name="toolContent?.function"
                  :args="toolContent?.args"
                  :status="toolStatus"
                  :result="toolContent?.content?.result"
                  :content="toolContent?.content"
                  :is-executing="false"
                />
              </div>

              <!-- Terminal View -->
              <div v-else-if="currentViewType === 'terminal'" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
                <!-- Live terminal: xterm.js with SSE streaming -->
                <TerminalLiveView
                  v-if="isTerminalLiveMode"
                  ref="terminalLiveRef"
                  :session-id="props.sessionId ?? ''"
                  :shell-session-id="terminalShellSessionId"
                  :command="terminalLiveCommand"
                />
                <!-- Static/completed terminal view -->
                <TerminalContentView
                  v-else
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

              <!-- Deal View -->
              <div v-else-if="currentViewType === 'deals'" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
                <DealContentView
                  :content="dealContent"
                  :is-searching="isDealSearching"
                  :progress-percent="toolContent?.progress_percent"
                  :current-step="toolContent?.current_step"
                  :checkpoint-data="dealCheckpointData"
                  :active-stores="dealActiveStores"
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

              <!-- Canvas View -->
              <div v-else-if="currentViewType === 'canvas' && resolvedCanvasProjectId" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
                <CanvasLiveView
                  :session-id="sessionId || ''"
                  :project-id="resolvedCanvasProjectId"
                  :live="isActiveOperation"
                  :refresh-token="canvasRefreshToken"
                  :latest-update="latestCanvasUpdate"
                  :sync-status="isActiveOperation ? 'live' : 'saved'"
                />
              </div>

              <!-- Generic/MCP View -->
              <div v-else-if="currentViewType === 'generic'" class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden">
                <GenericContentView
                  :tool-name="toolContent?.name"
                  :function-name="toolContent?.function"
                  :args="toolContent?.args"
                  :status="toolStatus"
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
                  :status="toolStatus"
                  :result="toolContent?.content?.result"
                  :content="toolContent?.content"
                  :is-executing="isActiveOperation"
                />
              </div>
            </div>
          </Transition>
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
            :tool-timeline="toolTimeline"
            :current-step="timelineCurrentStep"
            :total-steps="timelineTotalSteps"
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
import { Minimize2, MonitorUp, X, Loader2, FileText, PencilLine } from 'lucide-vue-next';
import type { ToolContent } from '@/types/message';
import type { CanvasUpdateEventData, PlanEventData, ToolEventData } from '@/types/event';
import { useContentConfig } from '@/composables/useContentConfig';
import { cleanDisplayText } from '@/utils/toolDisplay';
import { useCanvasLiveSync } from '@/composables/useCanvasLiveSync';
import { useStreamingPresentationState } from '@/composables/useStreamingPresentationState';
import { getToolDisplay, extractToolUrl } from '@/utils/toolDisplay';
import { viewFile, viewShellSession, browseUrl, startTakeover } from '@/api/agent';
import TimelineControls from '@/components/timeline/TimelineControls.vue';
import TakeOverIcon from '@/components/icons/TakeOverIcon.vue';
import TaskProgressBar from '@/components/TaskProgressBar.vue';

// Retry wrapper for dynamic imports — handles stale chunks after redeployment
function lazyRetry<T>(importFn: () => Promise<T>): () => Promise<T> {
  return () => importFn().catch((err: unknown) => {
    const msg = err instanceof Error ? err.message : '';
    if (msg.includes('dynamically imported module') || msg.includes('Failed to fetch')) {
      // Stale chunk: one-time page reload (guard prevents infinite loop)
      const key = 'vite-chunk-reload';
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, '1');
        window.location.reload();
        return new Promise<T>(() => {}); // suspends until reload completes
      }
      sessionStorage.removeItem(key);
    }
    throw err;
  });
}

// Content views are async to avoid loading heavy dependencies until needed.
const LiveViewer = defineAsyncComponent(lazyRetry(() => import('@/components/LiveViewer.vue')));
const LoadingState = defineAsyncComponent(lazyRetry(() => import('@/components/toolViews/shared/LoadingState.vue')));
const TerminalContentView = defineAsyncComponent(lazyRetry(() => import('@/components/toolViews/TerminalContentView.vue')));
const TerminalLiveView = defineAsyncComponent(lazyRetry(() => import('@/components/toolViews/TerminalLiveView.vue')));
const EditorContentView = defineAsyncComponent(lazyRetry(() => import('@/components/toolViews/EditorContentView.vue')));
const PlanPresentationView = defineAsyncComponent(lazyRetry(() => import('@/components/toolViews/PlanPresentationView.vue')));
const SearchContentView = defineAsyncComponent(lazyRetry(() => import('@/components/toolViews/SearchContentView.vue')));
const DealContentView = defineAsyncComponent(lazyRetry(() => import('@/components/toolViews/DealContentView.vue')));
const ChartToolView = defineAsyncComponent(lazyRetry(() => import('@/components/toolViews/ChartToolViewEnhanced.vue')));
const CanvasLiveView = defineAsyncComponent(lazyRetry(() => import('@/components/toolViews/CanvasLiveView.vue')));
const GenericContentView = defineAsyncComponent(lazyRetry(() => import('@/components/toolViews/GenericContentView.vue')));
const UnifiedStreamingView = defineAsyncComponent(lazyRetry(() => import('@/components/toolViews/UnifiedStreamingView.vue')));
const WideResearchOverlay = defineAsyncComponent(lazyRetry(() => import('@/components/WideResearchOverlay.vue')));
const ScreenshotReplayViewer = defineAsyncComponent(lazyRetry(() => import('@/components/ScreenshotReplayViewer.vue')));
import { useWideResearchGlobal } from '@/composables/useWideResearch';
import { useElapsedTimer } from '@/composables/useElapsedTimer';
import { useConnectionStore } from '@/stores/connectionStore';
import { normalizeSearchResults } from '@/utils/searchResults';
import { isCanvasDomainTool } from '@/utils/viewRouting';
import type { SearchResultsEnvelope, SearchResultsPayload } from '@/types/search';
import type { ScreenshotMetadata } from '@/types/screenshot';
import { detectContentType, detectLanguage, type StreamingContentType } from '@/types/streaming';
import { stripCmdMarkers, cleanPs1, cleanShellOutput } from '@/utils/shellSanitizer';

import type { ContentViewType } from '@/constants/tool';
import type { DealToolContent } from '@/types/toolContent';

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
  /** Tool timeline entries for scrubber markers and hover labels */
  toolTimeline?: ToolContent[];
  /** 1-based current step in the tool timeline */
  timelineCurrentStep?: number;
  /** Total steps in the tool timeline */
  timelineTotalSteps?: number;
  plan?: PlanEventData;
  isLoading?: boolean;
  isThinking?: boolean;
  isReplayMode?: boolean;
  replayScreenshotUrl?: string;
  replayMetadata?: ScreenshotMetadata | null;
  replayScreenshots?: ScreenshotMetadata[];
  summaryStreamText?: string;
  finalReportText?: string;
  isSummaryStreaming?: boolean;
  planPresentationText?: string;
  isPlanStreaming?: boolean;
  /** When true, hides the frame header and outer card styling (used in embedded/workspace mode) */
  embedded?: boolean;
  /** Override the auto-detected content view type (used for workspace tab switching) */
  forceViewType?: ContentViewType;
  /** Latest canvas update event from SSE so same-project updates still propagate. */
  activeCanvasUpdate?: CanvasUpdateEventData | null;
  /** Shared session start timestamp so all timers stay in sync. */
  sessionStartTime?: number;
}>();

// ── Elapsed timer + connection status for header ──────────────────
const headerTimer = useElapsedTimer()
const connectionStore = useConnectionStore()

// Start/stop timer based on loading state
watch(() => props.isLoading, (loading) => {
  if (loading) {
    headerTimer.start(props.sessionStartTime || undefined)
  } else {
    headerTimer.stop()
  }
}, { immediate: true })

/** Step progress derived from plan prop. */
const _stepInfo = computed(() => {
  if (!props.plan?.steps?.length) return null
  const steps = props.plan.steps
  const runningIdx = steps.findIndex(s => s.status === 'running')
  const current = runningIdx >= 0
    ? runningIdx + 1
    : steps.filter(s => s.status === 'completed').length
  return { current, total: steps.length }
})

/** Connection status dot color/pulse for header. */
const _connectionDot = computed(() => {
  const p = connectionStore.phase
  if (p === 'streaming') return { color: 'bg-emerald-500', pulse: false, label: '' }
  if (p === 'degraded') return { color: 'bg-amber-400', pulse: true, label: 'Slow' }
  if (p === 'reconnecting') return { color: 'bg-amber-400', pulse: true, label: '' }
  if (p === 'error') return { color: 'bg-red-500', pulse: false, label: '' }
  return null // idle/settled → hidden
})

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

// Auto-transition: search results → live browser after 5s, hold for ≥7s
const BROWSER_MIN_HOLD_MS = 7000;
let searchBrowseTimer: ReturnType<typeof setTimeout> | null = null;
let browserViewShownAt: number | null = null;
let browserHoldTimer: ReturnType<typeof setTimeout> | null = null;

function clearSearchBrowseTimer() {
  if (searchBrowseTimer) {
    clearTimeout(searchBrowseTimer);
    searchBrowseTimer = null;
  }
}

function clearBrowserHoldTimer() {
  if (browserHoldTimer) {
    clearTimeout(browserHoldTimer);
    browserHoldTimer = null;
  }
}

function showBrowserWithHold() {
  forceBrowserView.value = true;
  browserViewShownAt = Date.now();
}

function dismissBrowserView() {
  forceBrowserView.value = false;
  browserViewShownAt = null;
  clearBrowserHoldTimer();
}
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

const isViewingLatestTimelineStep = computed(() => {
  if (!props.timelineTotalSteps || props.timelineTotalSteps <= 0) return true;
  if (!props.timelineCurrentStep || props.timelineCurrentStep <= 0) return true;
  return props.timelineCurrentStep === props.timelineTotalSteps;
});

const showPersistedFinalReport = computed(() => {
  if (!props.finalReportText) return false;
  if (!props.isReplayMode) return true;
  return props.realTime || isViewingLatestTimelineStep.value;
});

const reportPresentationText = computed(() => {
  const persistedReportText = showPersistedFinalReport.value ? (props.finalReportText || '') : '';
  return persistedReportText || props.summaryStreamText || '';
});
const showReportPresentation = computed(() => {
  // When user navigated backward in timeline, show the tool at that position instead
  if (props.showTimeline && !props.realTime && !isViewingLatestTimelineStep.value) return false;
  // Show report in two cases:
  // 1. Actively streaming the summary (live writing)
  // 2. Session completed — the report is the last thing the agent produced
  if (!props.isSummaryStreaming && !showPersistedFinalReport.value) return false;
  return reportPresentationText.value.length > 0;
});
const showPlanPresentation = computed(() => {
  if (showReportPresentation.value) return false;
  if (props.showTimeline && !props.realTime && !isViewingLatestTimelineStep.value) return false;
  return (props.planPresentationText || '').length > 0;
});

/** Derive a stable key for the current content view — transitions fire only on key change.
 * Returns null for the live-preview pass-through (persistent browser visible, no overlay). */
const isPlanningTool = computed(() => props.toolContent?.name === 'planning');

/** Content for the plan editor overlay. Only returns content when the planning
 *  overlay should be visible (isPlanningTool active or planPresentationText set).
 *  Returns empty string when planning is done to prevent re-appearing during execution. */
const planEditorContent = computed(() => {
  // Real plan text from streaming or scaffold — always takes priority
  if (props.planPresentationText && props.planPresentationText.length > 0) {
    return props.planPresentationText;
  }
  // Only show plan steps or placeholder when the synthetic planning tool is active
  if (!isPlanningTool.value) return '';
  // Build from PlanEvent steps if available (arrives after planning completes)
  if (props.plan?.steps?.length) {
    const lines: string[] = [`# ${props.plan.title || 'Execution Plan'}\n`];
    if (props.plan.goal) lines.push(`> ${props.plan.goal}\n`);
    lines.push('---\n');
    for (let i = 0; i < props.plan.steps.length; i++) {
      const step = props.plan.steps[i];
      lines.push(`## Step ${i + 1} — ${step.action_verb || step.description?.substring(0, 50) || 'Execute'}\n`);
      if (step.description) lines.push(`${step.description}\n`);
      if (step.expected_output) lines.push(`> Expected output: ${step.expected_output}\n`);
      if (step.tool_hint) lines.push(`> Tools: ${step.tool_hint}\n`);
      lines.push('');
    }
    return lines.join('\n');
  }
  // Placeholder while waiting for data
  return '# Creating plan...\n\n> Analyzing your request and building an execution plan...';
});

const activeViewKey = computed((): string | null => {
  if (showReportPresentation.value) return 'report';
  if (showPlanPresentation.value) return 'plan';
  // Synthetic planning tool — force plan overlay even before text arrives,
  // so the stale browser from a previous session doesn't show through.
  if (isPlanningTool.value) return 'plan';
  if (shouldShowUnifiedStreaming.value) return 'streaming';
  if (showLiveViewSkeleton.value) return 'skeleton';

  if (props.isReplayMode && !props.realTime && !!props.replayScreenshotUrl && (currentViewType.value === 'live_preview' || !currentViewType.value)) {
    return 'replay-user';
  }
  if (props.isReplayMode && !props.realTime && !props.replayScreenshotUrl && (currentViewType.value === 'live_preview' || !currentViewType.value)) {
    return 'replay-user-loading';
  }

  // Pass-through: persistent browser visible, no overlay needed
  if (currentViewType.value === 'live_preview' && showPersistentBrowser.value) return null;
  if (currentViewType.value === 'live_preview') return 'live-preview-fallback';
  if (currentViewType.value === 'terminal') return 'terminal';
  if (currentViewType.value === 'editor') return 'editor';
  if (currentViewType.value === 'search') return 'search';
  if (currentViewType.value === 'deals') return 'deals';
  if (currentViewType.value === 'chart') return 'chart';
  if (currentViewType.value === 'canvas' && resolvedCanvasProjectId.value) return 'canvas';
  if (currentViewType.value === 'generic') return 'generic';
  if (currentViewType.value === 'wide_research') return 'wide-research';

  if (props.isReplayMode && !!props.replayScreenshotUrl) return 'replay-final';
  if (props.isReplayMode && !props.replayScreenshotUrl) return 'replay-final-loading';
  if (!showPersistentBrowser.value) return 'generic-fallback';

  return null;
});

// Tool state
const toolName = computed(() => props.toolContent?.name || '');
const toolFunction = computed(() => props.toolContent?.function || '');
const toolStatus = computed(() => props.toolContent?.status || '');
const isCanvasMode = computed(() => isCanvasDomainTool(props.toolContent));

// Canvas live view
const liveViewerRef = ref<{ processToolEvent?: (event: ToolEventData) => void } | null>(null);

interface BrowserAgentCheckpointData {
  action?: unknown;
  action_function?: unknown;
  step?: unknown;
  coordinate_x?: unknown;
  coordinate_y?: unknown;
  x?: unknown;
  y?: unknown;
  index?: unknown;
  url?: unknown;
}

const {
  latestCanvasUpdate,
  resolvedProjectId: resolvedCanvasProjectId,
  refreshToken: canvasRefreshToken,
} = useCanvasLiveSync({
  toolContent: toRef(props, 'toolContent'),
  activeCanvasUpdate: toRef(props, 'activeCanvasUpdate'),
});

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
  return typeof htmlFileId === 'string' && htmlFileId.length > 0;
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
  const isToolActive = toolStatus.value === 'calling' || toolStatus.value === 'running';
  return isToolActive && props.live;
});

/**
 * Show a pre-reply loading skeleton in the panel when the tool is actively
 * being called but no streaming content is available yet.
 * Excludes views that handle their own loading states or show live content.
 */
const showLiveViewSkeleton = computed(() => {
  if (!props.live) return false;
  if (!isActiveOperation.value) return false;
  if (shouldShowUnifiedStreaming.value) return false;
  if (isSummaryPhase.value || props.summaryStreamText) return false;
  if (showPlanPresentation.value) return false;
  // Synthetic planning tool — never show skeleton, the plan overlay will render
  if (props.toolContent?.name === 'planning') return false;
  if (props.isReplayMode) return false;
  // These views handle their own skeleton or show live content
  const noSkeleton = new Set(['search', 'live_preview', 'wide_research', 'terminal', 'editor', 'deals']);
  return !noSkeleton.has(currentViewType.value ?? '');
});

// Tool execution progress badge (from ToolProgressEvent)
const _shellProgress = computed(() => {
  if (!isActiveOperation.value) return '';
  const tc = props.toolContent;
  if (!tc?.elapsed_ms) return '';
  const seconds = Math.round(tc.elapsed_ms / 1000);
  const pct = tc.progress_percent;
  const step = tc.current_step;
  // Rich progress: show step description when available (deal_scraper, etc.)
  if (step) {
    return pct && pct > 0 ? `${step} (${pct}%, ${seconds}s)` : `${step} (${seconds}s)`;
  }
  // Fallback: generic progress for shell/other tools
  if (pct !== undefined && pct > 0) {
    return `Running ${seconds}s (${pct}%)`;
  }
  return `Running ${seconds}s`;
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

// When search completes (toolStatus leaves 'calling' on a search tool), start 5s auto-transition timer
watch(toolStatus, (status, prevStatus) => {
  if (prevStatus === 'calling' && status !== 'calling') {
    const isSearchTool = toolDisplay.value?.toolKey === 'search' || toolDisplay.value?.toolKey === 'wide_research';
    if (isSearchTool && currentViewType.value === 'search') {
      clearSearchBrowseTimer();
      searchBrowseTimer = setTimeout(() => {
        // Only transition if still on search view (user hasn't navigated away)
        if (currentViewType.value === 'search' && !forceBrowserView.value) {
          showBrowserWithHold();
        }
        searchBrowseTimer = null;
      }, 5000);
    }
  }
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
    if (canShowInteractive && chartViewMode.value === 'static') {
      // Promote to interactive when data becomes available
      chartViewMode.value = 'interactive';
    } else if (!canShowInteractive && chartViewMode.value === 'interactive') {
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

// Reuse shared placeholder-cleaning utility from toolDisplay.ts (DRY — "Reuse First" rule).
const cleanActivitySubtitle = cleanDisplayText;

const streamingPresentation = useStreamingPresentationState({
  isInitializing: computed(() => false),
  isSummaryStreaming: computed(() => !!props.isSummaryStreaming),
  summaryStreamText: computed(() => props.summaryStreamText || ''),
  finalReportText: computed(() => showPersistedFinalReport.value ? (props.finalReportText || '') : ''),
  isThinking: computed(() => !!props.isThinking),
  isActiveOperation: computed(() => isActiveOperation.value),
  isPlanStreaming: computed(() => !!props.isPlanStreaming),
  planPresentationText: computed(() => props.planPresentationText || ''),
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

// HMR/live restore can briefly pair a newer consumer with an older composable return shape.
// The composable's internal refs may be destroyed, so accessing .value on the returned
// computed refs can throw. Wrapping in try-catch is the only reliable guard since the
// ref objects themselves are truthy but their internal getters reference destroyed state.
const streamingHeadline = computed(() => { try { return streamingPresentation.headline?.value ?? ''; } catch { return ''; } });
const isSummaryPhase = computed(() => { try { return streamingPresentation.isSummaryPhase?.value ?? false; } catch { return false; } });
const isSessionComplete = computed(() => !props.isLoading && !!props.replayScreenshotUrl);

const isPlanningPhase = computed(() => { try { return streamingPresentation.isPlanningPhase?.value ?? false; } catch { return false; } });

const activityHeadline = computed(() => {
  if (isSummaryPhase.value) return streamingHeadline.value;
  if (isPlanningPhase.value) return streamingHeadline.value;
  if (toolDisplay.value?.displayName) {
    // Distinguish active vs completed tools so the headline reflects reality
    if (isActiveOperation.value) return `Pythinker is using ${toolDisplay.value.displayName}`;
    return `Used ${toolDisplay.value.displayName}`;
  }
  if (props.isThinking) return streamingHeadline.value;
  return '';
});

const activitySubtitle = computed(() => {
  if (isSummaryPhase.value) return '';
  return cleanActivitySubtitle(toolSubtitle.value);
});

const showReportActivityIcon = computed(() => isSummaryPhase.value);
const showPlanActivityIcon = computed(() => isPlanningPhase.value && !isSummaryPhase.value);

const showActivitySpinner = computed(() => !showReportActivityIcon.value && !showPlanActivityIcon.value && (!!props.isThinking && !toolDisplay.value));

// Content header label — unified context bar text (Manus-style)
const contentHeaderLabel = computed(() => {
  // Report streaming/display takes priority
  if (showReportPresentation.value) {
    if (props.isSummaryStreaming) return 'Writing report...';
    return 'Report';
  }
  if (showPlanPresentation.value) {
    if (props.isPlanStreaming) return 'Creating plan...';
    return 'Plan';
  }
  // Terminal: show working directory from PS1 prompt
  if (currentViewType.value === 'terminal') {
    const content = props.toolContent?.content;
    if (content?.console && Array.isArray(content.console) && content.console.length > 0) {
      const lastRecord = content.console[content.console.length - 1];
      const ps1 = lastRecord?.ps1;
      if (typeof ps1 === 'string' && ps1.trim()) {
        // Strip [CMD_BEGIN]/[CMD_END] markers from stored event data
        let cleanedPs1 = stripCmdMarkers(ps1).trim();
        if (cleanedPs1 && !cleanedPs1.endsWith('$')) cleanedPs1 += ' $';
        return cleanedPs1;
      }
    }
    const execDir = props.toolContent?.args?.exec_dir;
    if (typeof execDir === 'string' && execDir) {
      return execDir.replace(/^\/home\/ubuntu/, '~');
    }
    return 'Terminal';
  }
  // Editor: show filename
  if (currentViewType.value === 'editor') {
    const nameArg = props.toolContent?.args?.filename;
    if (typeof nameArg === 'string' && nameArg) return nameArg;
    if (resolvedFilePath.value) {
      const parts = resolvedFilePath.value.split('/');
      const name = parts[parts.length - 1] || '';
      if (name) return name;
    }
    return 'Editor';
  }
  // Search: show query
  if (currentViewType.value === 'search') {
    const q = searchQuery.value;
    if (typeof q === 'string' && q) return `Searching "${q}"`;
    return 'Search';
  }
  // Chart
  if (currentViewType.value === 'chart') {
    return 'Chart';
  }
  // Deals: show query
  if (currentViewType.value === 'deals') {
    const q = props.toolContent?.args?.query;
    if (typeof q === 'string' && q) return `Finding deals: "${q}"`;
    return 'Deal Finder';
  }
  // Canvas: show project name
  if (currentViewType.value === 'canvas') {
    const name = props.toolContent?.args?.name || props.toolContent?.args?.project_id;
    if (typeof name === 'string' && name) return name;
    return 'Canvas';
  }
  // Wide research
  if (currentViewType.value === 'wide_research') {
    const q = searchQuery.value;
    if (typeof q === 'string' && q) return `Researching "${q}"`;
    return 'Deep Research';
  }
  // Generic: tool display name
  return toolDisplay.value?.displayName || '';
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

let _lastForwardedToolEventKey = '';

const browserAgentCheckpoint = computed<BrowserAgentCheckpointData | null>(() => {
  const raw = props.toolContent?.checkpoint_data;
  if (!raw || typeof raw !== 'object') return null;
  return raw as BrowserAgentCheckpointData;
});

const liveViewerFunction = computed(() => {
  const checkpointFunction = browserAgentCheckpoint.value?.action_function;
  if (typeof checkpointFunction === 'string' && checkpointFunction.trim().length > 0) {
    return checkpointFunction;
  }
  return props.toolContent?.function || '';
});

const _numberFromUnknown = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  return undefined;
};

const _stringFromUnknown = (value: unknown): string | undefined => {
  if (typeof value === 'string' && value.trim().length > 0) return value;
  return undefined;
};

const liveViewerArgs = computed<Record<string, unknown>>(() => {
  const merged: Record<string, unknown> = { ...(props.toolContent?.args || {}) };
  const checkpoint = browserAgentCheckpoint.value;
  if (!checkpoint) return merged;

  const coordinateX = _numberFromUnknown(checkpoint.coordinate_x) ?? _numberFromUnknown(checkpoint.x);
  const coordinateY = _numberFromUnknown(checkpoint.coordinate_y) ?? _numberFromUnknown(checkpoint.y);
  const index = _numberFromUnknown(checkpoint.index);
  const url = _stringFromUnknown(checkpoint.url);
  const action = _stringFromUnknown(checkpoint.action);
  const step = _numberFromUnknown(checkpoint.step);

  if (coordinateX !== undefined) merged.coordinate_x = coordinateX;
  if (coordinateY !== undefined) merged.coordinate_y = coordinateY;
  if (index !== undefined) merged.index = index;
  if (url !== undefined) merged.url = url;
  if (action !== undefined) merged.action = action;
  if (step !== undefined) merged.step = step;

  return merged;
});

const forwardToolEventToLiveViewer = (): void => {
  if (!props.sessionId || !showPersistentBrowser.value || !liveViewerRef.value?.processToolEvent) return;

  const tool = props.toolContent;
  const functionName = liveViewerFunction.value;
  if (!tool?.tool_call_id || !functionName || !tool.status) return;

  const args = liveViewerArgs.value;
  const eventKey = JSON.stringify([
    tool.tool_call_id,
    tool.status,
    functionName,
    args.coordinate_x,
    args.coordinate_y,
    args.x,
    args.y,
    args.index,
    args.url,
    args.action,
    args.step,
  ]);
  if (eventKey === _lastForwardedToolEventKey) return;
  _lastForwardedToolEventKey = eventKey;

  liveViewerRef.value.processToolEvent({
    event_id: tool.event_id || tool.tool_call_id,
    timestamp: tool.timestamp || Math.floor(Date.now() / 1000),
    tool_call_id: tool.tool_call_id,
    name: tool.name,
    status: tool.status === 'interrupted' ? 'called' : tool.status,
    function: functionName,
    args,
  });
};

watch(
  () => props.sessionId,
  () => {
    _lastForwardedToolEventKey = '';
    forwardToolEventToLiveViewer();
  },
);

watch(liveViewerRef, () => {
  forwardToolEventToLiveViewer();
});

// ============ URL Bar Overlay ============
const resolvedBrowserUrl = computed(() => {
  // Prefer explicit URL from tool args (e.g. go_to_url → args.url)
  const explicitUrl = extractToolUrl(props.toolContent?.args);
  if (explicitUrl) return explicitUrl;
  // Fall back to resourceLabel only if it looks like a URL (not a bare number/index)
  const label = toolDisplay.value?.resourceLabel || '';
  if (label && /[./]/.test(label)) return label;
  return '';
});

const showUrlStatusBar = computed(() => {
  // X11 screencast now captures Chrome's full browser chrome (tabs + address bar),
  // so the frontend URL overlay is redundant and wastes vertical space.
  return false;
});


// ============ Terminal Content ============
const shellOutput = ref('');
const refreshTimer = ref<number | null>(null);

// ── Terminal Live Streaming (SSE → xterm.js via TerminalLiveView) ──
const terminalLiveRef = ref<InstanceType<typeof TerminalLiveView>>();
const terminalStreamWrittenLength = ref(0);

const isTerminalLiveMode = computed(() => {
  if (!isActiveOperation.value) return false;
  const tn = toolName.value;
  return tn === 'shell' || tn === 'code_executor' || tn === 'code_execute';
});

const terminalLiveCommand = computed(() => {
  const cmd = props.toolContent?.args?.command ?? props.toolContent?.command;
  return typeof cmd === 'string' ? cmd : undefined;
});

const terminalShellSessionId = computed(() =>
  String(props.toolContent?.args?.id ?? ''),
);

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

    const stdout = props.toolContent?.stdout ? stripCmdMarkers(props.toolContent.stdout) : undefined;
    const stderr = props.toolContent?.stderr ? stripCmdMarkers(props.toolContent.stderr) : undefined;
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
      // Live shell streaming: show command prefix + real-time output
      if (props.toolContent?.streaming_content) {
        const prefix = command ? `$ ${command}\n` : '';
        return `${prefix}${props.toolContent.streaming_content}`;
      }
      // During execution, show a message indicating the command is running
      if (isActiveOperation.value && command) {
        return `$ ${command}\n[executing...]`;
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
      const ps1 = cleanPs1(e.ps1);
      output += `${ANSI_GREEN}${ps1}${ANSI_RESET} `;
    }
    if (e.command) {
      output += `${e.command}\n`;
    }
    if (e.output) {
      const cleanOutput = cleanShellOutput(e.output, e.command);
      if (cleanOutput) {
        output += `${cleanOutput}\n`;
      }
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
  // Skip polling if unified streaming or terminal live streaming is active
  if (shouldShowUnifiedStreaming.value || isTerminalLiveMode.value) {
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
    // Skip loading if streaming or terminal live mode is active
    if (!shouldShowUnifiedStreaming.value && !isTerminalLiveMode.value) {
      loadShellContent();
    }
  }
});

watch(
  () => [
    props.sessionId,
    showPersistentBrowser.value,
    props.toolContent?.tool_call_id,
    props.toolContent?.status,
    props.toolContent?.function,
    props.toolContent?.args?.coordinate_x,
    props.toolContent?.args?.coordinate_y,
    props.toolContent?.args?.x,
    props.toolContent?.args?.y,
    props.toolContent?.args?.index,
    props.toolContent?.args?.url,
    props.toolContent?.checkpoint_data,
  ],
  () => {
    forwardToolEventToLiveViewer();
  },
  { immediate: true },
);

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

// ── Terminal live streaming watchers ──

// Replay buffered content once TerminalLiveView async component mounts
watch(terminalLiveRef, (ref) => {
  if (!ref) return;
  const content = props.toolContent?.streaming_content;
  if (content && terminalStreamWrittenLength.value === 0) {
    ref.writeData(content);
    terminalStreamWrittenLength.value = content.length;
  }
});

// Forward SSE terminal deltas to TerminalLiveView's xterm.js instance
watch(
  () => props.toolContent?.streaming_content,
  (newContent) => {
    if (!newContent || !terminalLiveRef.value) return;
    const delta = newContent.slice(terminalStreamWrittenLength.value);
    if (delta) {
      terminalLiveRef.value.writeData(delta);
      terminalStreamWrittenLength.value = newContent.length;
    }
  },
);

// Reset delta tracking when tool changes
watch(
  () => props.toolContent?.tool_call_id,
  () => {
    terminalStreamWrittenLength.value = 0;
  },
);

// Toggle polling: stop during live terminal streaming, resume on completion
watch(isTerminalLiveMode, (isLive, wasLive) => {
  if (isLive) {
    stopAutoRefresh();
  } else {
    // Write exit code when transitioning from live → completed
    if (wasLive && terminalLiveRef.value) {
      const exitCode = props.toolContent?.exit_code;
      if (exitCode !== undefined && exitCode !== null) {
        terminalLiveRef.value.writeComplete(exitCode);
      }
    }
    startAutoRefresh();
  }
});

// Reset forceBrowserView and cancel auto-transition when tool changes
watch(() => props.toolContent?.tool_call_id, () => {
  clearSearchBrowseTimer();

  // If browser view is held, defer the reset until the minimum hold expires
  if (forceBrowserView.value && browserViewShownAt) {
    const elapsed = Date.now() - browserViewShownAt;
    if (elapsed < BROWSER_MIN_HOLD_MS) {
      clearBrowserHoldTimer();
      browserHoldTimer = setTimeout(() => {
        dismissBrowserView();
      }, BROWSER_MIN_HOLD_MS - elapsed);
      return;
    }
  }

  dismissBrowserView();
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
  clearSearchBrowseTimer();
  clearBrowserHoldTimer();
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

// ============ Deal Content ============
const dealContent = computed((): DealToolContent | null => {
  const content = props.toolContent?.content as DealToolContent | undefined;
  if (content && Array.isArray(content.deals)) return content;
  return null;
});

const isDealSearching = computed(() => {
  const isDealTool = toolDisplay.value?.toolKey === 'deal_scraper';
  return isDealTool && toolStatus.value === 'calling';
});

// Default store domains that match adapter.py DEFAULT_STORES (DealFinder v1)
// Kept for reference — DealFinder v2 uses web-wide Shopping API search
// const DEFAULT_DEAL_STORES = [
//   'Amazon', 'Walmart', 'Best Buy', 'Target', 'eBay',
//   'Newegg', 'Costco', 'B&H Photo', 'Adorama', 'Micro Center',
// ];

const dealCheckpointData = computed(() => {
  const raw = props.toolContent?.checkpoint_data;
  if (!raw || typeof raw !== 'object') return null;
  return raw as import('@/types/toolContent').DealProgressData;
});

const dealActiveStores = computed((): string[] => {
  const args = props.toolContent?.args;
  if (args?.stores && Array.isArray(args.stores)) {
    return args.stores as string[];
  }
  // DealFinder v2: no explicit stores = web-wide Shopping API search
  // Return empty to let DealContentView show "All Stores" indicator
  return [];
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
  clearSearchBrowseTimer(); // User clicked manually, cancel auto-transition

  try {
    // Immediately switch to browser view with hold protection
    showBrowserWithHold();

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

/* Panel content crossfade transition */
.panel-crossfade-enter-active,
.panel-crossfade-leave-active {
  transition: opacity 180ms ease;
}

.panel-crossfade-enter-from,
.panel-crossfade-leave-to {
  opacity: 0;
}

.panel-crossfade-leave-active {
  position: absolute;
  inset: 0;
}

/* Pre-reply loading skeleton (chart, generic, and unknown views) */
.live-view-skeleton {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.lv-skel-line {
  height: 11px;
  border-radius: 6px;
  background: var(--fill-tsp-gray-main);
  animation: lv-pulse 1.5s ease-in-out infinite;
}

.lv-skel-line--xl   { width: 82%; }
.lv-skel-line--lg   { width: 66%; animation-delay: 0.08s; }
.lv-skel-line--md   { width: 48%; animation-delay: 0.16s; }
.lv-skel-line--sm   { width: 32%; animation-delay: 0.12s; }

.lv-skel-block {
  height: 72px;
  border-radius: 8px;
  background: var(--fill-tsp-gray-main);
  animation: lv-pulse 1.5s ease-in-out infinite;
  animation-delay: 0.04s;
  margin: 4px 0;
}

@keyframes lv-pulse {
  0%, 100% { opacity: 0.35; }
  50%       { opacity: 0.7; }
}

/* ===== PANEL OUTER FRAME ===== */
.panel-outer-frame {
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  border-radius: 18px;
  box-shadow:
    0 8px 32px rgba(15, 23, 42, 0.06),
    0 2px 8px rgba(15, 23, 42, 0.04);
}

:global(.dark) .panel-outer-frame {
  background: color-mix(in srgb, var(--background-white-main) 97%, rgb(0, 0, 0));
  border-color: rgba(255, 255, 255, 0.06);
  box-shadow:
    0 12px 48px rgba(0, 0, 0, 0.5),
    0 4px 16px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

/* ===== PANEL FRAME HEADER ===== */
.panel-frame-header {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 48px;
}

.panel-control-btn {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border: 1px solid transparent;
  background: transparent;
  color: var(--icon-tertiary);
  transition: all 0.15s ease;
}

.panel-control-btn:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-light);
  color: var(--icon-primary);
}

:global(.dark) .panel-control-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.08);
}

.panel-control-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

/* ===== URL STATUS BAR ===== */
.url-status-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px 20px;
  border-bottom: 1px solid var(--border-light);
  background: color-mix(in srgb, var(--fill-tsp-gray-main) 50%, transparent);
  flex-shrink: 0;
  border-radius: 12px 12px 0 0;
}

:global(.dark) .url-status-bar {
  background: rgba(255, 255, 255, 0.02);
  border-bottom-color: rgba(255, 255, 255, 0.05);
}

.url-status-text {
  font-size: 13px;
  font-weight: 400;
  letter-spacing: 0.01em;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

:global(.dark) .url-status-text {
  color: color-mix(in srgb, var(--text-tertiary) 70%, transparent);
}

/* ===== CONTENT HEADER (unified context bar — matches URL status bar) ===== */
.panel-content-header {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  width: 100%;
  height: 32px;
  padding: 0 12px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-light);
  border-radius: 12px 12px 0 0;
  background: color-mix(in srgb, var(--fill-tsp-gray-main) 50%, transparent);
}

:global(.dark) .panel-content-header {
  background: rgba(255, 255, 255, 0.02);
  border-bottom-color: rgba(255, 255, 255, 0.05);
}

.context-bar-label {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  max-width: 80%;
  min-width: 0;
  font-size: 13px;
  font-weight: 400;
  letter-spacing: 0.01em;
  color: var(--text-tertiary);
}

.context-bar-label > span {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

:global(.dark) .context-bar-label {
  color: color-mix(in srgb, var(--text-tertiary) 70%, transparent);
}

/* ===== CONTENT CONTAINER DARK MODE ===== */
:global(.dark) .panel-content-container {
  border-color: rgba(255, 255, 255, 0.05);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
}

/* ===== ACTIVITY LINE (subtitle below title) ===== */
.panel-activity-line {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text-tertiary);
  overflow: hidden;
  line-height: 1.3;
}

:global(.dark) .panel-activity-line {
  color: color-mix(in srgb, var(--text-tertiary) 80%, transparent);
}

.panel-report-activity-icon {
  position: relative;
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--text-brand);
  transition: transform 0.18s ease, color 0.18s ease;
}

.panel-activity-line:hover .panel-report-activity-icon {
  transform: translateY(-1px) scale(1.04);
}

.panel-report-activity-glyph {
  position: relative;
  z-index: 1;
}

.panel-report-activity-accent {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: 4px;
  height: 4px;
  border-radius: 9999px;
  background: currentColor;
  transform-origin: center;
}

.panel-report-activity-icon-streaming .panel-report-activity-glyph {
  animation: report-activity-page 1.7s ease-in-out infinite;
}

.panel-report-activity-icon-streaming .panel-report-activity-accent {
  animation: report-activity-pulse 1.7s ease-in-out infinite;
}

.panel-report-activity-icon-ready {
  color: var(--text-secondary);
}

.panel-report-activity-icon-ready .panel-report-activity-glyph {
  animation: report-activity-ready 2.4s ease-in-out infinite;
}

.panel-report-activity-icon-ready .panel-report-activity-accent {
  animation: report-activity-ready-pulse 2.4s ease-in-out infinite;
}

@keyframes report-activity-page {
  0%, 100% {
    transform: translateY(0) rotate(0deg);
  }
  35% {
    transform: translateY(-0.5px) rotate(-7deg);
  }
  65% {
    transform: translateY(0.5px) rotate(5deg);
  }
}

@keyframes report-activity-pulse {
  0%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
    box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 24%, transparent);
  }
  50% {
    transform: scale(1.15);
    opacity: 1;
    box-shadow: 0 0 0 5px color-mix(in srgb, currentColor 0%, transparent);
  }
}

@keyframes report-activity-ready {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-1px);
  }
}

@keyframes report-activity-ready-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.9;
  }
  50% {
    transform: scale(1.12);
    opacity: 1;
  }
}

.panel-activity-separator {
  color: var(--text-quaternary);
  opacity: 0.5;
  flex-shrink: 0;
}

.panel-activity-detail {
  color: var(--text-quaternary);
}

:global(.dark) .panel-activity-detail {
  color: color-mix(in srgb, var(--text-quaternary) 70%, transparent);
}

@media (prefers-reduced-motion: reduce) {
  .panel-report-activity-icon,
  .panel-report-activity-glyph,
  .panel-report-activity-accent {
    animation: none !important;
    transition: none;
  }
}

/* ===== TAKEOVER FAB (floating action button) ===== */
.takeover-fab {
  position: absolute;
  right: 14px;
  bottom: 14px;
  z-index: 10;
  min-width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--background-white-main) 85%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  color: var(--text-secondary);
  border: 1px solid var(--border-light);
  box-shadow:
    0 4px 16px rgba(0, 0, 0, 0.08),
    0 1px 4px rgba(0, 0, 0, 0.04);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

:global(.dark) .takeover-fab {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.3),
    0 1px 4px rgba(0, 0, 0, 0.2);
}

.takeover-fab:hover {
  border-radius: 21px;
  padding: 0 16px;
  background: var(--text-brand);
  color: var(--text-onblack);
  border-color: transparent;
  box-shadow:
    0 6px 24px rgba(0, 0, 0, 0.12),
    0 2px 8px rgba(0, 0, 0, 0.06);
}

:global(.dark) .takeover-fab:hover {
  box-shadow:
    0 6px 28px rgba(0, 0, 0, 0.4),
    0 2px 8px rgba(0, 0, 0, 0.3);
}

.takeover-fab:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.takeover-fab-label {
  font-size: 14px;
  max-width: 0;
  overflow: hidden;
  white-space: nowrap;
  opacity: 0;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.takeover-fab:hover .takeover-fab-label {
  max-width: 200px;
  opacity: 1;
  margin-left: 6px;
}
</style>
