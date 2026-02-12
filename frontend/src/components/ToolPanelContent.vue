<template>
  <div class="bg-[var(--background-white-main)] sm:bg-[var(--background-white-main)] sm:rounded-[20px] shadow-[0px_10px_30px_rgba(15,23,42,0.08)] border border-[var(--border-light)] flex h-full w-full">
    <div class="flex-1 min-w-0 p-4 flex flex-col h-full">
      <!-- Frame Header: Pythinker's Computer + window controls -->
      <div class="flex items-center gap-2 w-full">
        <div class="text-[var(--text-primary)] text-[15px] font-semibold flex-1">{{ $t("Pythinker's Computer") }}</div>
        <div class="flex items-center gap-1">
          <button
            v-if="!!props.sessionId"
            class="w-7 h-7 rounded-md inline-flex items-center justify-center cursor-pointer border border-transparent hover:bg-[var(--fill-tsp-gray-main)] hover:border-[var(--border-light)]"
            @click="takeOver"
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
        class="relative flex flex-col rounded-[14px] overflow-hidden bg-[var(--background-white-main)] border border-[var(--border-light)] shadow-[0px_6px_24px_rgba(15,23,42,0.06)] flex-1 min-h-0 mt-[16px]">

        <!-- Content Header: Centered operation label + View mode tabs -->
        <div
          v-if="contentConfig"
          class="panel-content-header h-[36px] flex items-center justify-center px-3 w-full bg-[var(--background-white-main)] border-b border-[var(--border-light)] rounded-t-[14px] relative">

          <!-- Left: Activity indicator (absolute positioned) -->
          <div v-if="isWriting" class="absolute left-3 flex items-center gap-2">
            <div class="flex items-center gap-1.5">
              <div class="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></div>
              <span class="text-xs text-blue-500 font-medium">Writing</span>
            </div>
          </div>

          <!-- Center: Operation label or resource -->
          <div class="text-[var(--text-tertiary)] text-sm font-medium truncate max-w-[300px]">
            {{ contentHeaderLabel }}
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
        </div>

        <!-- Content Area: Dynamic content rendering -->
        <div class="flex-1 min-h-0 min-w-0 w-full overflow-hidden relative">
          <!-- Streaming Report (live summary composition — highest priority) -->
          <StreamingReportView
            v-if="isSummaryPhase || summaryStreamText"
            :text="summaryStreamText || ''"
            :is-final="!isSummaryStreaming"
          />

          <!-- Replay mode: static screenshots (only when no richer tool view is available) -->
          <div
            v-else-if="isReplayMode && !!replayScreenshotUrl && !hasRichToolView"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <ScreenshotReplayViewer
              :src="replayScreenshotUrl || ''"
              :metadata="replayMetadata || null"
            />
          </div>

          <!-- Replay mode loading: screenshots not yet fetched (only when no richer tool view) -->
          <div
            v-else-if="isReplayMode && !replayScreenshotUrl && !hasRichToolView"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <LoadingState
              label="Loading replay"
              :is-active="true"
              animation="globe"
            />
          </div>

          <!-- VNC View (via backend proxy - works from browser) — skip for completed sessions -->
          <div
            v-else-if="currentViewType === 'vnc' && !isReplayMode"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <!-- Placeholder for loading/text-only operations -->
            <LoadingState
              v-if="showVncPlaceholder"
              :label="vncPlaceholderLabel || 'Loading'"
              :detail="vncPlaceholderDetail"
              :is-active="isActiveOperation"
              :animation="vncPlaceholderAnimation || 'globe'"
            />

            <!-- VNC Viewer when enabled -->
            <LiveViewer
              v-else-if="vncEnabled"
              :key="'vnc-main-' + (sessionId || 'none')"
              :session-id="sessionId || ''"
              :enabled="vncEnabled"
              :view-only="true"
              @connected="onVNCConnected"
              @disconnected="onVNCDisconnected"
            />

            <!-- Inactive state when no session -->
            <InactiveState
              v-else
              message="Pythinker's computer is inactive"
            />

            <!-- VNC URL bar overlay - shows current URL during browser operations -->
            <div v-if="showVncUrlBar" class="vnc-url-bar">
              <div class="vnc-url-status">
                <Loader2 v-if="isActiveOperation" :size="12" class="vnc-url-spinner" />
                <Check v-else :size="12" />
              </div>
              <span class="vnc-url-text">{{ vncUrlBarText }}</span>
            </div>

            <!-- Take over button — visible whenever session is active -->
            <button
              v-if="!isShare && !!props.sessionId && !showVncPlaceholder"
              @click="takeOver"
              class="absolute right-3 bottom-3 z-10 min-w-10 h-10 flex items-center justify-center rounded-full bg-[var(--background-white-main)] text-[var(--text-primary)] border border-[var(--border-main)] shadow-lg cursor-pointer hover:bg-[var(--text-brand)] hover:px-4 hover:text-white group transition-all duration-300">
              <TakeOverIcon />
              <span class="text-sm max-w-0 overflow-hidden whitespace-nowrap opacity-0 transition-all duration-300 group-hover:max-w-[200px] group-hover:opacity-100 group-hover:ml-1">
                {{ $t('Take Over') }}
              </span>
            </button>
          </div>

          <!-- Terminal View -->
          <TerminalContentView
            v-else-if="currentViewType === 'terminal'"
            :content="terminalContent"
            :content-type="terminalContentType"
            :is-live="isActiveOperation"
            :is-writing="isWriting"
            :auto-scroll="true"
            @new-content="onNewTerminalContent"
          />

          <!-- Editor View -->
          <EditorContentView
            v-else-if="currentViewType === 'editor'"
            :content="editorContent"
            :filename="fileName"
            :is-writing="isWriting"
            :is-loading="isEditorLoading"
          />

          <!-- Search View -->
          <SearchContentView
            v-else-if="currentViewType === 'search'"
            :results="searchResults"
            :is-searching="isSearching"
            :query="searchQuery"
            :explicit-results="searchResultsExplicit"
            @browseUrl="handleBrowseUrl"
          />

          <!-- Generic/MCP View -->
          <GenericContentView
            v-else-if="currentViewType === 'generic'"
            :tool-name="toolContent?.name"
            :function-name="toolContent?.function"
            :args="toolContent?.args"
            :result="toolContent?.content?.result"
            :content="toolContent?.content"
            :is-executing="isActiveOperation"
          />

          <!-- Wide Research View (parallel multi-source search) -->
          <WideResearchOverlay
            v-else-if="currentViewType === 'wide_research'"
            :state="wideResearchState"
            :always-show="true"
          />

          <!-- VNC fallback when session exists but no dedicated view — skip for completed sessions -->
          <div
            v-else-if="sessionId && !isReplayMode"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <LiveViewer
              :key="'vnc-fallback-' + (sessionId || 'none')"
              :session-id="sessionId"
              :enabled="true"
              :view-only="true"
              @connected="onVNCConnected"
              @disconnected="onVNCDisconnected"
            />
          </div>

          <!-- Fallback: render GenericContentView when no session -->
          <GenericContentView
            v-else
            :tool-name="toolContent?.name"
            :function-name="toolContent?.function"
            :args="toolContent?.args"
            :result="toolContent?.content?.result"
            :content="toolContent?.content"
            :is-executing="isActiveOperation"
          />
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
import { toRef, computed, watch, ref, onMounted, onUnmounted } from 'vue';
import { Minimize2, MonitorUp, X, Loader2, Check } from 'lucide-vue-next';
import type { ToolContent } from '@/types/message';
import type { PlanEventData } from '@/types/event';
import { useContentConfig } from '@/composables/useContentConfig';
import { useStreamingPresentationState } from '@/composables/useStreamingPresentationState';
import { getToolDisplay } from '@/utils/toolDisplay';
import { viewFile, viewShellSession, browseUrl } from '@/api/agent';
import TimelineControls from '@/components/timeline/TimelineControls.vue';
import TakeOverIcon from '@/components/icons/TakeOverIcon.vue';
import TaskProgressBar from '@/components/TaskProgressBar.vue';

// Content views
import LiveViewer from '@/components/LiveViewer.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';
import InactiveState from '@/components/toolViews/shared/InactiveState.vue';
import TerminalContentView from '@/components/toolViews/TerminalContentView.vue';
import EditorContentView from '@/components/toolViews/EditorContentView.vue';
import SearchContentView from '@/components/toolViews/SearchContentView.vue';
import GenericContentView from '@/components/toolViews/GenericContentView.vue';
import StreamingReportView from '@/components/toolViews/StreamingReportView.vue';
import WideResearchOverlay from '@/components/WideResearchOverlay.vue';
import ScreenshotReplayViewer from '@/components/ScreenshotReplayViewer.vue';
import { useWideResearchGlobal } from '@/composables/useWideResearch';
import { normalizeSearchResults } from '@/utils/searchResults';
import type { SearchResultsEnvelope, SearchResultsPayload } from '@/types/search';
import type { ScreenshotMetadata } from '@/types/screenshot';

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
  if (forceBrowserView.value) return 'vnc';
  if (shouldShowArtifactEditor.value) return 'editor';
  return computedViewType.value;
});

// Tool state
const toolName = computed(() => props.toolContent?.name || '');
const toolFunction = computed(() => props.toolContent?.function || '');
const toolStatus = computed(() => props.toolContent?.status || '');

// Artifact tools (report outputs saved via code executor)
const isArtifactTool = computed(() => {
  return toolName.value === 'code_executor' && (
    toolFunction.value === 'code_save_artifact' ||
    toolFunction.value === 'code_read_artifact'
  );
});

const artifactInlineContent = computed(() => {
  if (!isArtifactTool.value) return '';
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

/**
 * Tool subtitle - Pythinker-style standardized format: "Verb Resource"
 * @see docs/guides/TOOL_STANDARDIZATION.md
 */
const toolSubtitle = computed(() => toolDisplay.value?.description || '');

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
    if (currentViewType.value === 'vnc') {
      return 'vnc';
    }
    return 'generic';
  }),
  isSessionComplete: computed(() => false),
  replayScreenshotUrl: computed(() => props.replayScreenshotUrl || ''),
  previewText: computed(() => props.summaryStreamText || '')
});

const isSummaryPhase = computed(() => streamingPresentation.isSummaryPhase.value);

const activityHeadline = computed(() => {
  if (isSummaryPhase.value) return streamingPresentation.headline.value;
  if (toolDisplay.value?.displayName) return `Pythinker is using ${toolDisplay.value.displayName}`;
  if (props.isThinking) return streamingPresentation.headline.value;
  return '';
});

const activitySubtitle = computed(() => {
  if (isSummaryPhase.value) return '';
  return toolSubtitle.value;
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

const showVncPlaceholder = computed(() => {
  if (forceBrowserView.value) return false;
  if (!props.sessionId) return true;
  if (vncDisconnected.value) return true;
  return false;
});

const vncPlaceholderLabel = computed(() => {
  if (!props.sessionId) return 'No live session';
  if (vncDisconnected.value) return 'Reconnecting';
  return 'Connecting';
});

const vncPlaceholderDetail = computed(() => {
  if (!props.sessionId) return 'Open a session to view the screen.';
  if (vncDisconnected.value) return 'Waiting for the live stream.';
  return '';
});

// Animation type for VNC placeholder
const vncPlaceholderAnimation = computed<'globe' | 'check' | 'spinner'>(() => {
  return 'globe';
});

const vncEnabled = computed(() => {
  return !!props.sessionId && !showVncPlaceholder.value;
});

// Whether the current tool has a rich native view (editor, terminal, search)
// that is more informative than a VNC screenshot replay
const hasRichToolView = computed(() => {
  const vt = currentViewType.value;
  return vt === 'editor' || vt === 'terminal' || vt === 'search' || vt === 'wide_research';
});

// ============ VNC URL Bar Overlay ============
const BROWSER_TOOL_PREFIXES = ['browser', 'playwright', 'browsing'];
const isBrowserTool = (name: string) =>
  BROWSER_TOOL_PREFIXES.some(prefix => name.startsWith(prefix));

const showVncUrlBar = computed(() => {
  if (showVncPlaceholder.value) return false;
  return isBrowserTool(toolName.value) && !!toolDisplay.value?.resourceLabel;
});

const vncUrlBarText = computed(() => {
  return toolDisplay.value?.resourceLabel || '';
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

// Start auto-refresh timer for shell
const startAutoRefresh = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
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
    loadShellContent();
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
const vncDisconnected = ref(false);

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
      const argContent = typeof props.toolContent?.args?.content === 'string'
        ? props.toolContent?.args?.content
        : '';
      return argContent || getToolContentText() || fileContent.value;
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

const takeOver = () => {
  if (!props.sessionId) return;

  // Agent keeps working during takeover — no pause
  window.dispatchEvent(new CustomEvent('takeover', {
    detail: { sessionId: props.sessionId, active: true }
  }));
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

const onVNCConnected = () => {
  vncDisconnected.value = false;
};
const onVNCDisconnected = () => {
  vncDisconnected.value = true;
};

const onNewTerminalContent = () => {
  markNewOutput();
};

/**
 * Handle browse URL request from search results
 * Navigates the browser directly to the clicked URL
 * Switches to browser/VNC view immediately and listens to SSE events
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
.panel-content-header {
  box-shadow: inset 0 1px 0 0 var(--border-white);
}

.vnc-url-bar {
  position: absolute;
  top: 8px;
  left: 8px;
  right: 8px;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.vnc-url-status {
  flex-shrink: 0;
  color: white;
  opacity: 0.7;
  display: flex;
  align-items: center;
}

.vnc-url-spinner {
  animation: vnc-spin 1s linear infinite;
}

@keyframes vnc-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.vnc-url-text {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.85);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-sans);
}
</style>
