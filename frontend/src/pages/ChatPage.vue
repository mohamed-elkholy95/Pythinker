<template>
  <SimpleBar ref="simpleBarRef" @scroll="handleScroll">
    <div id="manus-chat-box" ref="chatContainerRef" class="relative flex flex-col h-full flex-1 flex-shrink-0 min-w-0 bg-[var(--background-gray-main)]">
      <div ref="observerRef"
        class="chat-header flex flex-row items-center pt-3 pb-1 gap-1 ps-[16px] pe-[24px] sticky top-0 z-10 flex-shrink-0 bg-[var(--background-gray-main)]">
        <!-- Left side - panel toggle -->
        <div class="flex items-center justify-start" style="width: calc((100% - min(768px, 100%)) / 2);">
          <button
            class="sm:hidden h-8 w-8 inline-flex items-center justify-center rounded-lg hover:bg-[var(--fill-tsp-gray-main)] transition-colors"
            @click="toggleLeftPanel"
            aria-label="Open sidebar"
          >
            <Menu :size="20" class="text-[var(--icon-secondary)]" />
          </button>
        </div>
        <!-- Center content - matches chat content width -->
        <div class="max-w-full sm:max-w-[768px] sm:min-w-[400px] w-full flex items-center justify-between gap-3">
          <!-- Left: Title -->
          <div class="flex items-center gap-2 flex-1 min-w-0">
            <button class="chat-model-pill" type="button" aria-label="Current chat title">
              <span class="chat-title-text">
                {{ title }}
              </span>
              <ChevronRight class="chat-title-chevron" :size="16" />
            </button>
          </div>
          <!-- Right: Buttons -->
          <div class="flex items-center gap-1 flex-shrink-0">
              <span class="relative flex-shrink-0" aria-expanded="false" aria-haspopup="dialog">
                <Popover>
                  <PopoverTrigger>
                    <button
                      class="h-7 min-w-[56px] px-2 rounded-[8px] inline-flex items-center gap-1.5 clickable border border-[var(--border-main)] hover:border-[var(--border-dark)] hover:bg-[var(--fill-tsp-white-main)] transition-all">
                      <ShareIcon color="var(--icon-secondary)" />
                      <span class="text-[var(--text-secondary)] text-[13px] font-medium leading-[18px]">{{ t('Share') }}</span>
                    </button>
                  </PopoverTrigger>
                  <PopoverContent>
                    <div
                      class="w-[400px] flex flex-col rounded-2xl bg-[var(--background-menu-white)] shadow-[0px_8px_32px_0px_var(--shadow-S),0px_0px_0px_1px_var(--border-light)]"
                      style="max-width: calc(-16px + 100vw);">
                      <div class="flex flex-col pt-[12px] px-[16px] pb-[16px]">
                        <!-- Private mode option -->
                        <div @click="handleShareModeChange('private')"
                          :class="{'pointer-events-none opacity-50': sharingLoading}"
                          class="flex items-center gap-[10px] px-[8px] -mx-[8px] py-[8px] rounded-[8px] clickable hover:bg-[var(--fill-tsp-white-main)]">
                          <div
                            :class="shareMode === 'private' ? 'bg-[var(--Button-primary-black)]' : 'bg-[var(--fill-tsp-white-dark)]'"
                            class="w-[32px] h-[32px] rounded-[8px] flex items-center justify-center">
                            <Lock :size="16" :stroke="shareMode === 'private' ? 'var(--text-onblack)' : 'var(--icon-primary)'" :stroke-width="2" /></div>
                          <div class="flex flex-col flex-1 min-w-0">
                            <div class="text-sm font-medium text-[var(--text-primary)]">{{ t('Private Only') }}</div>
                            <div class="text-[13px] text-[var(--text-tertiary)]">{{ t('Only visible to you') }}</div>
                          </div><Check :size="20" :class="shareMode === 'private' ? 'ml-auto' : 'ml-auto invisible'" :color="shareMode === 'private' ? 'var(--icon-primary)' : 'var(--icon-tertiary)'" />
                        </div>
                        <!-- Public mode option -->
                        <div @click="handleShareModeChange('public')"
                          :class="{'pointer-events-none opacity-50': sharingLoading}"
                          class="flex items-center gap-[10px] px-[8px] -mx-[8px] py-[8px] rounded-[8px] clickable hover:bg-[var(--fill-tsp-white-main)]">
                          <div
                            :class="shareMode === 'public' ? 'bg-[var(--Button-primary-black)]' : 'bg-[var(--fill-tsp-white-dark)]'"
                            class="w-[32px] h-[32px] rounded-[8px] flex items-center justify-center">
                            <Globe :size="16" :stroke="shareMode === 'public' ? 'var(--text-onblack)' : 'var(--icon-primary)'" :stroke-width="2" /></div>
                          <div class="flex flex-col flex-1 min-w-0">
                            <div class="text-sm font-medium text-[var(--text-primary)]">{{ t('Public Access') }}</div>
                            <div class="text-[13px] text-[var(--text-tertiary)]">{{ t('Anyone with the link can view') }}</div>
                          </div><Check :size="20" :class="shareMode === 'public' ? 'ml-auto' : 'ml-auto invisible'" :color="shareMode === 'public' ? 'var(--icon-primary)' : 'var(--icon-tertiary)'" />
                        </div>
                        <div class="border-t border-[var(--border-main)] mt-[4px]"></div>
                        
                        <!-- Show instant share button when in private mode -->
                        <div v-if="shareMode === 'private'">
                          <button @click.stop="handleInstantShare"
                            :disabled="sharingLoading"
                            class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] h-[36px] px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 mt-[16px] w-full disabled:opacity-50 disabled:cursor-not-allowed"
                            data-tabindex="" tabindex="-1">
                            <div v-if="sharingLoading" class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                            <Link v-else :size="16" stroke="currentColor" :stroke-width="2" />
                            {{ sharingLoading ? t('Sharing...') : t('Share Instantly') }}
                          </button>
                        </div>
                        
                        <!-- Show copy link button when in public mode -->
                        <div v-else>
                          <button @click.stop="handleCopyLink"
                            :class="linkCopied ? 'inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors active:opacity-80 bg-[var(--Button-primary-white)] text-[var(--text-primary)] hover:opacity-70 active:hover-60 h-[36px] px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 mt-[16px] w-full border border-[var(--border-btn-main)] shadow-none' : 'inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] h-[36px] px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 mt-[16px] w-full'"
                            data-tabindex="" tabindex="-1">
                            <Link v-if="!linkCopied" :size="16" stroke="currentColor" :stroke-width="2" />
                            <Check v-else :size="16" color="var(--text-primary)" />
                            {{ linkCopied ? t('Link Copied') : t('Copy Link') }}
                          </button>
                        </div>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
              </span>
              <button @click="handleFileListShow"
                class="h-8 w-8 flex items-center justify-center hover:bg-[var(--fill-tsp-gray-main)] rounded-lg cursor-pointer transition-colors">
                <FileSearch class="text-[var(--icon-secondary)]" :size="18" />
              </button>
          </div>
        </div>
        <!-- Right side - spacer -->
        <div class="flex-1"></div>
      </div>
      <div
        class="mx-auto w-full max-w-full px-5 sm:max-w-[768px] sm:min-w-[400px] flex flex-col flex-1"
        :class="{ 'chat-content-with-pinned-dock': shouldPinComposerToBottom }"
      >
        <div
          class="flex flex-col w-full pb-[80px] pt-[24px] flex-1"
          :class="{
            'chat-messages-with-pinned-dock': shouldPinComposerToBottom,
            'chat-messages-with-thumbnail-dock': shouldPinComposerToBottom && showThumbnailDockSpacer,
          }"
        >
          <ChatMessage v-for="(message, index) in messages" :key="message.id" :message="message"
            :activeThinkingStepId="activeThinkingStepId"
            :showStepLeadingConnector="shouldShowStepLeadingConnector(index)"
            :showStepConnector="shouldShowStepConnector(index)"
            :showAssistantHeader="shouldShowAssistantHeader(index)"
            @toolClick="handleToolClick"
            @reportOpen="handleReportOpen"
            @reportFileOpen="handleReportFileOpen"
            @showAllFiles="handleFileListShow"
            @reportRate="handleReportRate"
            @selectSuggestion="handleSuggestionSelect"
            @deepResearchRun="handleDeepResearchRun"
            @deepResearchSkip="handleDeepResearchSkip"
            @toggleAutoRun="handleToggleAutoRun" />
          <SessionWarmupMessage
            v-if="showSessionWarmupMessage"
            :state="warmupState"
            @retry="handleRetryInitialize"
          />

          <!-- Loading/Thinking indicators - fallback for discuss mode (no active step) -->
          <div v-if="showFloatingThinkingIndicator" class="flex items-center gap-2 pl-1">
            <ThinkingIndicator :showText="true" />
          </div>
          <LoadingIndicator v-else-if="!showSessionWarmupMessage && isLoading && !activeThinkingStepId && !hasRunningStep" :text="$t('Loading')" />

          <!-- Waiting for user reply indicator -->
          <WaitingForReply v-if="isWaitingForReply" />

          <!-- Long-running task notice -->
          <div v-if="isStale" class="flex items-center gap-2 px-4 py-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl mx-4 mb-2">
            <div class="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
            <div class="flex-1 min-w-0">
              <span class="text-sm text-blue-700 dark:text-blue-300">
                {{ $t('Taking longer than usual...') }}
              </span>
              <span v-if="currentToolInfo" class="text-xs text-blue-500 dark:text-blue-400 ml-1">
                ({{ currentToolInfo.name }})
              </span>
            </div>
            <button
              @click="handleStop"
              class="flex-shrink-0 px-3 py-1 text-xs font-medium text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-800/50 hover:bg-blue-200 dark:hover:bg-blue-800 rounded-lg transition-colors"
            >
              {{ $t('Stop') }}
            </button>
          </div>

          <!-- Suggestions - show in dedicated area after response is complete -->
          <Suggestions
            v-if="suggestions.length > 0 && isResponseSettled && !isLoading && !isThinking && !isSummaryStreaming"
            :suggestions="suggestions"
            @select="handleSuggestionSelect"
          />
        </div>

        <div
          ref="chatBottomDockRef"
          class="chat-bottom-dock flex flex-col sticky bottom-0"
          :class="{ 'chat-bottom-dock-fixed': shouldPinComposerToBottom }"
          :style="chatBottomDockStyle"
        >
          <button
            @click="handleFollow"
            v-if="!follow"
            class="flex items-center justify-center w-[36px] h-[36px] rounded-full bg-[var(--background-menu-white)] hover:bg-[var(--background-gray-main)] clickable border border-[var(--border-main)] shadow-[0px_5px_16px_0px_var(--shadow-S),0px_0px_1.25px_0px_var(--shadow-S)] absolute -top-[56px] end-0 z-30"
          >
            <ArrowDown class="text-[var(--icon-primary)]" :size="20" />
          </button>
          <!-- Planning Progress Indicator - shows instant feedback before plan is ready -->
          <div
            v-if="!showSessionWarmupMessage && !isToolPanelOpen && planningProgress && (!plan || plan.steps.length === 0)"
            class="planning-progress-indicator mb-2 bg-white dark:bg-[#2a2a2a] rounded-lg border border-gray-200 dark:border-[#3a3a3a] px-4 py-2.5 shadow-sm"
          >
            <!-- Content row -->
            <div class="flex items-center gap-3">
              <div class="planning-thinking flex-shrink-0">
                <ThinkingIndicator :showText="false" />
              </div>
              <div class="flex-1 min-w-0">
                <span class="planning-text-shimmer text-[15px] font-medium">
                  {{ currentPlanningMessage }}
                </span>
              </div>
            </div>
          </div>

          <!-- Task Progress Bar - shown above ChatBox when ToolPanel is closed -->
          <TaskProgressBar
            v-if="showTaskProgressBar"
            :plan="plan"
            :isLoading="isLoading"
            :isThinking="isThinking"
            :showThumbnail="shouldShowThumbnail"
            :sessionId="sessionId"
            :currentTool="currentToolInfo"
            :toolContent="lastNoMessageTool"
            :isInitializing="isInitializing || isSandboxInitializing"
            :isSummaryStreaming="isSummaryStreaming"
            :summaryStreamText="summaryStreamText"
            :isSessionComplete="isSessionComplete"
            :replayScreenshotUrl="replay.currentScreenshotUrl.value"
            @openPanel="handleOpenPanel"
            @requestRefresh="handleThumbnailRefresh"
            class="mb-2"
          />
          <ChatBox
            v-model="inputMessage"
            :rows="1"
            @submit="handleSubmit"
            :isRunning="isLoading"
            :isBlocked="isSandboxInitializing"
            @stop="handleStop"
            :attachments="attachments"
            @fileClick="handleAttachmentFileClick"
            expand-direction="up"
          />
        </div>
      </div>
      <!-- Wide Research Overlay -->
      <WideResearchOverlay
        :state="researchWorkflow.wideOverlayState.value"
        :phase="researchWorkflow.activePhase.value"
      />
    </div>
    <ToolPanel ref="toolPanel" :size="toolPanelSize" :sessionId="sessionId" :realTime="realTime"
      :isShare="false"
      :plan="plan"
      :isLoading="isLoading"
      :isThinking="isThinking"
      :summaryStreamText="summaryStreamText"
      :isSummaryStreaming="isSummaryStreaming"
      @jumpToRealTime="jumpToRealTime"
      :showTimeline="showTimelineControls"
      :timelineProgress="effectiveTimelineProgress"
      :timelineTimestamp="effectiveTimelineTimestamp"
      :timelineCanStepForward="effectiveCanStepForward"
      :timelineCanStepBackward="effectiveCanStepBackward"
      :isReplayMode="isReplayMode"
      :replayScreenshotUrl="replay.currentScreenshotUrl.value"
      :replayMetadata="replay.currentScreenshot.value"
      :replayScreenshots="replay.screenshots.value"
      @timelineStepForward="handleTimelineStepForward"
      @timelineStepBackward="handleTimelineStepBackward"
      @timelineSeek="handleTimelineSeek"
      @panelStateChange="handlePanelStateChange" />
  </SimpleBar>

  <!-- Connectors Dialog -->
  <ConnectorsDialog />

  <!-- Report Modal -->
  <ReportModal
    v-model:open="isReportModalOpen"
    :report="currentReport"
    :showToc="true"
    @close="closeReport"
    @download="handleReportDownload"
  />
  <Dialog v-model:open="filePreviewOpen">
    <DialogContent
      :hideCloseButton="true"
      :title="filePreviewFile?.filename || 'File preview'"
      description="View file preview"
      class="p-0 flex flex-col overflow-hidden transition-all duration-200 bg-[var(--background-white-main)] w-[95vw] max-w-[1100px] h-[85vh] max-h-[900px]"
    >
      <FilePanelContent
        v-if="filePreviewFile"
        :file="filePreviewFile"
        @hide="closeFilePreview"
      />
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import SimpleBar from '../components/SimpleBar.vue';
import { ref, computed, onMounted, watch, nextTick, onUnmounted, reactive, toRefs } from 'vue';
import { useRouter, onBeforeRouteUpdate, onBeforeRouteLeave } from 'vue-router';
import { useDocumentVisibility } from '@vueuse/core';
import { useI18n } from 'vue-i18n';
import ChatBox from '../components/ChatBox.vue';
import ChatMessage from '../components/ChatMessage.vue';
import * as agentApi from '../api/agent';
import { Message, MessageContent, ToolContent, StepContent, AttachmentsContent, ReportContent, SkillDeliveryContent } from '../types/message';
import { waitForSessionReady } from '@/utils/sessionReady';
import {
  StepEventData,
  ToolEventData,
  MessageEventData,
  ErrorEventData,
  TitleEventData,
  PlanEventData,
  AgentSSEEvent,
  ModeChangeEventData,
  SuggestionEventData,
  ReportEventData,
  StreamEventData,
  ProgressEventData,
  DeepResearchEventData,
  WideResearchEventData,
  PhaseTransitionEventData,
  CheckpointSavedEventData,
  SkillDeliveryEventData,
  SkillActivationEventData,
  CanvasUpdateEventData,
} from '../types/event';
import type { DeepResearchContent } from '../types/message';
import Suggestions from '../components/Suggestions.vue';
import ToolPanel from '../components/ToolPanel.vue'
import { ArrowDown, FileSearch, Lock, Globe, Link, Check, ChevronRight, Menu } from 'lucide-vue-next';
import ShareIcon from '@/components/icons/ShareIcon.vue';
import { showErrorToast, showSuccessToast, showInfoToast } from '../utils/toast';
import type { FileInfo } from '../api/file';
import { useLeftPanel } from '../composables/useLeftPanel'
import { useSessionFileList } from '../composables/useSessionFileList'
import { useFilePanel } from '../composables/useFilePanel'
import { copyToClipboard } from '../utils/dom'
import { SessionStatus } from '../types/response';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import LoadingIndicator from '@/components/ui/LoadingIndicator.vue';
import TaskProgressBar from '@/components/TaskProgressBar.vue';
import SessionWarmupMessage from '@/components/SessionWarmupMessage.vue';
import { ReportModal } from '@/components/report';
import FilePanelContent from '@/components/FilePanelContent.vue';
import type { ReportData } from '@/components/report';
import { useReport, extractSectionsFromMarkdown } from '@/composables/useReport';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import ThinkingIndicator from '@/components/ui/ThinkingIndicator.vue';
import WaitingForReply from '@/components/WaitingForReply.vue';
import WideResearchOverlay from '@/components/WideResearchOverlay.vue';
import { useSessionStatus } from '@/composables/useSessionStatus';
import { getToolDisplay } from '@/utils/toolDisplay';
import { useSkills } from '@/composables/useSkills';
import { useDeepResearch } from '@/composables/useDeepResearch';
import { useResearchWorkflow } from '@/composables/useResearchWorkflow';
import ConnectorsDialog from '@/components/connectors/ConnectorsDialog.vue';
import { useConnectorDialog } from '@/composables/useConnectorDialog';
import { useScreenshotReplay } from '@/composables/useScreenshotReplay';
import { shouldStopSessionOnExit } from '@/utils/sessionLifecycle';

const router = useRouter()
const { t } = useI18n()
const { toggleLeftPanel } = useLeftPanel()
const { showSessionFileList } = useSessionFileList()
const { hideFilePanel } = useFilePanel()
const { isReportModalOpen, currentReport, openReport, closeReport } = useReport()
const { emitStatusChange } = useSessionStatus()
const { getEffectiveSkillIds, clearSelectedSkills, lockSkillsForSession, clearSessionSkills, selectSkill } = useSkills()
const { toggleAutoRun } = useDeepResearch()
const researchWorkflow = useResearchWorkflow()
// ConnectorDialog composable — dialog manages its own visibility
useConnectorDialog()

// Create initial state factory
const createInitialState = () => ({
  inputMessage: '',
  isLoading: false,
  sessionId: undefined as string | undefined,
  messages: [] as Message[],
  toolPanelSize: 0,
  realTime: true,
  follow: true,
  title: t('New Chat'),
  plan: undefined as PlanEventData | undefined,
  lastNoMessageTool: undefined as ToolContent | undefined,
  lastMessageTool: undefined as ToolContent | undefined,
  lastTool: undefined as ToolContent | undefined,
  lastEventId: undefined as string | undefined,
  cancelCurrentChat: null as (() => void) | null,
  attachments: [] as FileInfo[],
  shareMode: 'private' as 'private' | 'public', // Default to private mode
  linkCopied: false,
  sharingLoading: false, // Loading state for share operations
  suggestions: [] as string[], // End-of-response suggestions
  isResponseSettled: false, // True only after done/wait/error (response lifecycle ended)
  agentMode: 'discuss' as 'discuss' | 'agent', // Current agent mode
  isThinking: false, // True when agent is actively thinking/processing
  seenEventIds: new Set<string>(), // Track seen event IDs to prevent duplicates
  thinkingText: '', // Accumulated streaming thinking text
  isThinkingStreaming: false, // True when streaming thinking is in progress
  summaryStreamText: '', // Accumulated streaming summary text
  isSummaryStreaming: false, // True when summary is streaming live
  lastEventTime: 0, // Timestamp of last received event (for stale detection)
  isStale: false, // True when agent appears unresponsive (no events for 60s)
  filePreviewOpen: false,
  filePreviewFile: null as FileInfo | null,
  toolTimeline: [] as ToolContent[],
  panelToolId: undefined as string | undefined,
  isInitializing: false, // True when starting up the sandbox environment
  planningProgress: null as { phase: string; message: string; percent: number } | null, // Planning progress
  isWaitingForReply: false, // True when agent is waiting for user input
  followUpAnchorEventId: undefined as string | undefined, // Event ID to anchor follow-up context to
  pendingFollowUpSuggestion: undefined as string | undefined, // Suggestion waiting to be sent
});

// Create reactive state
const state = reactive(createInitialState());

// Destructure refs from reactive state
const {
  inputMessage,
  isLoading,
  sessionId,
  messages,
  toolPanelSize,
  realTime,
  follow,
  title,
  plan,
  lastNoMessageTool,
  lastTool,
  lastEventId,
  cancelCurrentChat,
  attachments,
  shareMode,
  linkCopied,
  sharingLoading,
  suggestions,
  isResponseSettled,
  agentMode,
  isThinking,
  seenEventIds,
  thinkingText,
  isThinkingStreaming,
  summaryStreamText,
  isSummaryStreaming,
  lastEventTime,
  isStale,
  filePreviewOpen,
  filePreviewFile,
  toolTimeline,
  panelToolId,
  isInitializing,
  planningProgress,
  isWaitingForReply,
  followUpAnchorEventId,
  pendingFollowUpSuggestion,
} = toRefs(state);

// Screenshot replay for completed sessions.
// Must be initialized after sessionId ref is created to avoid TDZ runtime errors.
const replay = useScreenshotReplay(computed(() => sessionId.value))

const hasScreenshotReplay = computed(() => replay.hasScreenshots.value)

const isSessionComplete = computed(() => {
  return !!sessionStatus.value &&
    [SessionStatus.COMPLETED, SessionStatus.FAILED].includes(sessionStatus.value)
})

// Replay mode: session is completed/failed and has replay data
const isReplayMode = computed(() => {
  const ended = !isLoading.value && isSessionComplete.value
  return !!ended && hasScreenshotReplay.value
})

const isScreenshotReplayMode = computed(() => isReplayMode.value)

// Message ID counter for generating unique keys (avoids crypto overhead)
let messageIdCounter = 0;
const generateMessageId = () => `msg_${Date.now()}_${++messageIdCounter}`;

// Phase 5: Event ID set size limit to prevent unbounded memory growth
const MAX_SEEN_EVENT_IDS = 1000;

/**
 * Add an event ID to the seen set with automatic cleanup.
 * Uses LRU-like eviction by clearing oldest half when limit is reached.
 * This prevents the Set from growing unboundedly during long sessions.
 */
const addSeenEventId = (eventId: string) => {
  // Check if cleanup is needed before adding
  if (seenEventIds.value.size >= MAX_SEEN_EVENT_IDS) {
    // Clear the oldest half by converting to array and keeping recent entries
    const entries = Array.from(seenEventIds.value);
    const keepCount = Math.floor(MAX_SEEN_EVENT_IDS / 2);
    seenEventIds.value.clear();
    // Keep the most recent entries (at the end of the array)
    for (let i = entries.length - keepCount; i < entries.length; i++) {
      if (entries[i]) seenEventIds.value.add(entries[i]);
    }
    console.debug(`Cleaned up seenEventIds: kept ${keepCount} of ${entries.length}`);
  }
  seenEventIds.value.add(eventId);
};

// Non-state refs that don't need reset
const toolPanel = ref<InstanceType<typeof ToolPanel>>()
const simpleBarRef = ref<InstanceType<typeof SimpleBar>>();
const observerRef = ref<HTMLDivElement>();
const chatContainerRef = ref<HTMLDivElement>();
const chatBottomDockRef = ref<HTMLDivElement>();
const chatBottomDockStyle = ref<Record<string, string>>({});
let chatContainerResizeObserver: ResizeObserver | null = null;

// Track session status
const sessionStatus = ref<SessionStatus | undefined>(undefined);
const isSandboxInitializing = computed(() => sessionStatus.value === SessionStatus.INITIALIZING);
const isWaitingForSessionReady = ref(false);
const pendingInitialMessage = ref<{ message: string; files: FileInfo[] } | null>(null);
const sessionInitTimedOut = ref(false);
const skipNextRouteReset = ref(false);

interface PendingSessionCreateState {
  pendingSessionCreate: boolean;
  mode?: 'agent' | 'discuss';
  message?: string;
  skills?: string[];
  files?: FileInfo[];
}

interface SessionTitleHintDetail {
  sessionId: string;
  title: string;
  status?: SessionStatus;
}

const emitSessionTitleHint = (detail: SessionTitleHintDetail) => {
  const normalizedTitle = detail.title?.trim();
  if (!detail.sessionId || !normalizedTitle) return;

  window.dispatchEvent(new CustomEvent<SessionTitleHintDetail>('pythinker:session-title-hint', {
    detail: {
      sessionId: detail.sessionId,
      title: normalizedTitle,
      status: detail.status,
    },
  }));
}

const hasUserMessages = computed(() =>
  messages.value.some((message) => message.type === 'user')
);

const hasAgentStartedResponding = computed(() =>
  messages.value.some((message) =>
    message.type === 'assistant' ||
    message.type === 'tool' ||
    message.type === 'step' ||
    message.type === 'report' ||
    message.type === 'deep_research' ||
    message.type === 'skill_delivery'
  )
);

const shouldPinComposerToBottom = computed(() =>
  isLoading.value || hasAgentStartedResponding.value || messages.value.length > 0
);

const updateChatBottomDockStyle = () => {
  if (!shouldPinComposerToBottom.value) {
    chatBottomDockStyle.value = {};
    return;
  }

  const chatContainer = chatContainerRef.value;
  if (!chatContainer) return;

  const rect = chatContainer.getBoundingClientRect();
  const horizontalPadding = 20;
  const maxDockWidth = 768;
  const availableWidth = Math.max(rect.width - horizontalPadding * 2, 280);
  const dockWidth = Math.min(maxDockWidth, availableWidth);
  const dockLeft = rect.left + (rect.width - dockWidth) / 2;

  chatBottomDockStyle.value = {
    left: `${Math.max(dockLeft, horizontalPadding)}px`,
    width: `${dockWidth}px`,
  };
};

const showSessionWarmupMessage = computed(() => {
  const hasPrompt = hasUserMessages.value || !!pendingInitialMessage.value?.message?.trim();
  if (!hasPrompt) return false;
  if (hasAgentStartedResponding.value) return false;
  if (sessionInitTimedOut.value) return true;

  return (
    isLoading.value ||
    isSandboxInitializing.value ||
    isWaitingForSessionReady.value ||
    isInitializing.value
  );
});

const warmupState = computed<'initializing' | 'thinking' | 'timed_out'>(() => {
  if (sessionInitTimedOut.value) return 'timed_out';
  if (isSandboxInitializing.value || isWaitingForSessionReady.value || isInitializing.value) {
    return 'initializing';
  }
  return 'thinking';
});

// Track active canvas project from canvas_update SSE events
const activeCanvasProjectId = ref<string | null>(null);

const refreshSessionStatus = async (targetSessionId?: string) => {
  const activeSessionId = targetSessionId ?? sessionId.value;
  if (!activeSessionId) {
    sessionStatus.value = undefined;
    return;
  }

  try {
    const session = await agentApi.getSession(activeSessionId);
    sessionStatus.value = session.status as SessionStatus;
    if (sessionStatus.value !== SessionStatus.INITIALIZING) {
      sessionInitTimedOut.value = false;
    }
  } catch {
    // Session status fetch failed - non-critical
  }
};

const maybeSendPendingInitialMessage = () => {
  const pending = pendingInitialMessage.value;
  if (pending && sessionStatus.value !== SessionStatus.INITIALIZING) {
    pendingInitialMessage.value = null;
    // Initial prompt is already rendered optimistically while session warms up.
    // Skip inserting a second optimistic bubble when it is actually sent.
    chat(pending.message, pending.files, { skipOptimistic: true });
  }
};

const getPendingSessionCreateState = (): PendingSessionCreateState | null => {
  const state = history.state as PendingSessionCreateState | null;
  if (!state?.pendingSessionCreate) return null;
  return state;
};

const initializePendingSession = async () => {
  const routeSessionId = router.currentRoute.value.params.sessionId;
  if (routeSessionId !== 'new') return false;

  const pendingState = getPendingSessionCreateState();
  if (!pendingState) return false;

  const pendingMessage = (pendingState.message || '').trim();
  const pendingFiles = Array.isArray(pendingState.files) ? pendingState.files : [];
  const pendingSkills = Array.isArray(pendingState.skills) ? pendingState.skills : [];
  const mode = pendingState.mode === 'discuss' ? 'discuss' : 'agent';

  // Show immediate chat view feedback while backend session is being created.
  if (pendingMessage || pendingFiles.length > 0) {
    addOptimisticUserMessage(pendingMessage, pendingFiles);
    isInitializing.value = true;
    isLoading.value = true;
    isResponseSettled.value = false;
  }

  try {
    const session = await agentApi.createSession(mode);
    sessionId.value = session.session_id;
    if (pendingMessage) {
      emitSessionTitleHint({
        sessionId: session.session_id,
        title: pendingMessage,
        status: session.status,
      });
    }

    skipNextRouteReset.value = true;
    await router.replace({ path: `/chat/${session.session_id}` });

    if (pendingMessage || pendingFiles.length > 0) {
      // Apply selected skills right before sending the first message.
      for (const skillId of pendingSkills) {
        selectSkill(skillId);
      }
      pendingInitialMessage.value = { message: pendingMessage, files: pendingFiles };
      await refreshSessionStatus(session.session_id);
      await waitForSessionIfInitializing();
      maybeSendPendingInitialMessage();
    } else {
      await refreshSessionStatus(session.session_id);
      await restoreSession();
    }
  } catch {
    isLoading.value = false;
    isInitializing.value = false;
    pendingInitialMessage.value = null;
    showErrorToast(t('Failed to create session, please try again later'));
  }

  return true;
};

const waitForSessionIfInitializing = async () => {
  if (!sessionId.value || isWaitingForSessionReady.value) return;
  if (sessionStatus.value !== SessionStatus.INITIALIZING) return;

  const targetSessionId = sessionId.value;
  isWaitingForSessionReady.value = true;
  sessionInitTimedOut.value = false;
  try {
    const result = await waitForSessionReady(targetSessionId, agentApi.getSession, {
      pollIntervalMs: 500,
      maxWaitMs: 30000,
    });
    if (sessionId.value === targetSessionId) {
      sessionStatus.value = result.status;
      sessionInitTimedOut.value = result.timedOut && result.status === SessionStatus.INITIALIZING;
      if (!sessionInitTimedOut.value) {
        maybeSendPendingInitialMessage();
      }
    }
  } finally {
    isWaitingForSessionReady.value = false;
  }
};

const handleRetryInitialize = async () => {
  sessionInitTimedOut.value = false;
  await refreshSessionStatus();
  await waitForSessionIfInitializing();
  maybeSendPendingInitialMessage();
};

watch(sessionStatus, (status) => {
  if (status !== SessionStatus.INITIALIZING) {
    sessionInitTimedOut.value = false;
  }
});

// Watch sessionId changes to update status
watch(sessionId, async (newSessionId) => {
  // Clear session-level skills when switching sessions
  clearSessionSkills();

  await refreshSessionStatus(newSessionId);
  await waitForSessionIfInitializing();
}, { immediate: true });

// Centralized sessionStorage cleanup for session-specific data
const cleanupSessionStorage = (sessionId: string) => {
  sessionStorage.removeItem(`pythinker-last-event-${sessionId}`);
  sessionStorage.removeItem(`pythinker-stopped-${sessionId}`);
};

// Reset all refs to their initial values
const resetState = () => {
  // Cancel any existing chat connection
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
  }

  // Clean up sessionStorage for old session
  if (sessionId.value) {
    cleanupSessionStorage(sessionId.value);
  }

  researchWorkflow.reset();

  // Reset reactive state to initial values
  Object.assign(state, createInitialState());
};

// Watch message length changes for scroll (avoids deep watching which re-triggers on nested changes)
watch(
  () => messages.value.length,
  async () => {
    await nextTick();
    if (follow.value) {
      simpleBarRef.value?.scrollToBottom();
    }
  }
);

// Scroll to bottom when agent starts (loading begins) or plan step count changes
watch(
  [isLoading, () => plan.value?.steps?.length ?? 0],
  async () => {
    await nextTick();
    if (follow.value) {
      simpleBarRef.value?.scrollToBottom();
    }
  }
);

// Scroll to bottom when streaming thinking text updates
watch(thinkingText, async () => {
  await nextTick();
  if (follow.value && isThinkingStreaming.value) {
    simpleBarRef.value?.scrollToBottom();
  }
});

watch(
  [shouldPinComposerToBottom, toolPanelSize],
  async () => {
    await nextTick();
    updateChatBottomDockStyle();
  },
  { immediate: true }
);

watch(filePreviewOpen, (isOpen) => {
  if (!isOpen) {
    filePreviewFile.value = null;
  }
});

// ===== Agent Connection Health Monitoring =====
const STALE_TIMEOUT_MS = 120000; // 2 minutes without events = taking longer than usual
const STALE_CHECK_INTERVAL_MS = 10000; // Check every 10 seconds
let staleCheckInterval: ReturnType<typeof setInterval> | null = null;

// Update last event time when any event is received
const updateLastEventTime = () => {
  lastEventTime.value = Date.now();
  isStale.value = false;
};

// Check if connection appears stale
const checkStaleConnection = () => {
  if (!isLoading.value) {
    isStale.value = false;
    return;
  }

  const timeSinceLastEvent = Date.now() - lastEventTime.value;
  if (timeSinceLastEvent > STALE_TIMEOUT_MS && lastEventTime.value > 0) {
    isStale.value = true;
  }
};

// Track if ToolPanel is open (needed for VNC thumbnail management)
const isToolPanelOpen = ref(false);

// Handler for TaskProgressBar's requestRefresh event (no-op with live VNC preview)
const handleThumbnailRefresh = () => {
  // With live VNC preview, no refresh is needed - it's always up to date
};

// Start stale detection when loading starts
watch(isLoading, (loading) => {
  if (loading) {
    updateLastEventTime();
    if (!staleCheckInterval) {
      staleCheckInterval = setInterval(checkStaleConnection, STALE_CHECK_INTERVAL_MS);
    }
  } else {
    isStale.value = false;
    if (staleCheckInterval) {
      clearInterval(staleCheckInterval);
      staleCheckInterval = null;
    }
  }
});

// Cleanup on unmount
onUnmounted(() => {
  if (staleCheckInterval) {
    clearInterval(staleCheckInterval);
    staleCheckInterval = null;
  }
  stopPlanningMessageCycle();
});

const getLastStep = (): StepContent | undefined => {
  return messages.value.filter(message => message.type === 'step').pop()?.content as StepContent;
}

const shouldShowStepConnector = (messageIndex: number): boolean => {
  const currentMessage = messages.value[messageIndex];
  if (!currentMessage || currentMessage.type !== 'step') return false;

  for (let i = messageIndex + 1; i < messages.value.length; i += 1) {
    if (messages.value[i].type === 'step') {
      return true;
    }
  }

  return false;
};

const shouldShowStepLeadingConnector = (messageIndex: number): boolean => {
  const currentMessage = messages.value[messageIndex];
  if (!currentMessage || currentMessage.type !== 'step') return false;

  for (let i = messageIndex - 1; i >= 0; i -= 1) {
    if (messages.value[i].type === 'step') {
      return true;
    }
  }

  return false;
};

const shouldShowAssistantHeader = (messageIndex: number): boolean => {
  const currentMessage = messages.value[messageIndex];
  if (!currentMessage || currentMessage.type !== 'assistant') return false;

  const previousMessage = messages.value[messageIndex - 1];
  if (!previousMessage) return true;

  if (previousMessage.type === 'assistant' || previousMessage.type === 'tool' || previousMessage.type === 'step') {
    return false;
  }

  return true;
};

const addOptimisticUserMessage = (message: string, files: FileInfo[] = []) => {
  const normalizedMessage = message.trim();
  if (!normalizedMessage && files.length === 0) return;
  const nowInSeconds = Math.floor(Date.now() / 1000);

  if (normalizedMessage && messages.value.length > 0) {
    for (let i = messages.value.length - 1; i >= 0; i -= 1) {
      if (messages.value[i].type !== 'user') continue;
      const lastUserContent = messages.value[i].content as MessageContent;
      if (
        lastUserContent.content === normalizedMessage &&
        nowInSeconds - lastUserContent.timestamp <= 10
      ) {
        return;
      }
      break;
    }
  }

  if (normalizedMessage) {
    messages.value.push({
      id: generateMessageId(),
      type: 'user',
      content: {
        content: normalizedMessage,
        timestamp: nowInSeconds,
      } as MessageContent,
    });
  }

  if (files.length > 0) {
    messages.value.push({
      id: generateMessageId(),
      type: 'attachments',
      content: {
        role: 'user',
        attachments: files,
        timestamp: nowInSeconds,
      } as AttachmentsContent,
    });
  }
};

const currentRunningStepId = computed<string | undefined>(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const message = messages.value[i];
    if (message.type !== 'step') continue;
    const step = message.content as StepContent;
    if (step.status === 'running') return step.id;
  }
  return undefined;
});

const hasRunningStep = computed(() => !!currentRunningStepId.value);
const hasThinkingSignal = computed(() => isThinkingStreaming.value || isThinking.value);
const hasActiveToolCall = computed(() => lastTool.value?.status === 'calling');

// Identify the active step that should show the thinking indicator inside it.
// This is bound to actual runtime state: running step + thinking signal + no active tool call.
const activeThinkingStepId = computed<string | undefined>(() => {
  if (!isLoading.value) return undefined;
  if (!hasThinkingSignal.value) return undefined;
  if (hasActiveToolCall.value) return undefined;
  return currentRunningStepId.value;
});

// Show standalone thinking indicator only when not inside an active running step.
const showFloatingThinkingIndicator = computed(() => {
  if (showSessionWarmupMessage.value) return false;
  if (!isLoading.value) return false;
  if (!hasThinkingSignal.value) return false;
  if (hasActiveToolCall.value) return false;
  if (hasRunningStep.value) return false;
  return true;
});

const showTaskProgressBar = computed(() =>
  !showSessionWarmupMessage.value &&
  !isToolPanelOpen.value &&
  (!!plan.value?.steps?.length || !!lastNoMessageTool.value || isInitializing.value || isSandboxInitializing.value)
);

// Add extra bottom scroll room when mini VNC thumbnail is rendered with the task progress bar.
const showThumbnailDockSpacer = computed(() => showTaskProgressBar.value && shouldShowThumbnail.value);

// Handle tool panel state changes
const handlePanelStateChange = (isOpen: boolean) => {
  isToolPanelOpen.value = isOpen;
};

// Computer-related tools that should show thumbnail
const COMPUTER_TOOLS = ['browser', 'shell', 'file', 'browser_agent', 'code_executor'];
const isComputerTool = (tool?: ToolContent | null) => {
  if (!tool) return false;
  return COMPUTER_TOOLS.includes(tool.name);
};

// Always show thumbnail when panel is closed and there's activity
const shouldShowThumbnail = computed(() => {
  if (isToolPanelOpen.value) return false;
  if (!sessionId.value) return false;
  // Show live VNC thumbnail when there's an active plan, loading, or tool activity
  return !!plan.value?.steps?.length || isLoading.value || isPlanCompleted.value || !!lastNoMessageTool.value;
});

const isPlanCompleted = computed(() => {
  return !!plan.value?.steps?.length && plan.value.steps.every(step => step.status === 'completed');
});


// Get current tool info for display
const currentToolInfo = computed(() => {
  const tool = lastNoMessageTool.value;
  if (!tool) return null;
  const display = getToolDisplay({
    name: tool.name,
    function: tool.function,
    args: tool.args,
    display_command: tool.display_command
  });

  return {
    name: display.displayName,
    function: display.actionLabel,
    functionArg: display.resourceLabel,
    status: tool.status,
    icon: display.icon
  };
});

const toolTimelineIndex = computed(() => {
  if (!panelToolId.value) return -1;
  return toolTimeline.value.findIndex(tool => tool.tool_call_id === panelToolId.value);
});

const toolTimelineProgress = computed(() => {
  const total = toolTimeline.value.length;
  if (total <= 1 || toolTimelineIndex.value < 0) return 0;
  return (toolTimelineIndex.value / (total - 1)) * 100;
});

const toolTimelineTimestamp = computed(() => {
  if (toolTimelineIndex.value >= 0) {
    return toolTimeline.value[toolTimelineIndex.value].timestamp;
  }
  return lastNoMessageTool.value?.timestamp;
});

const toolTimelineCanStepForward = computed(() => {
  const total = toolTimeline.value.length;
  return toolTimelineIndex.value >= 0 && toolTimelineIndex.value < total - 1;
});

const toolTimelineCanStepBackward = computed(() => toolTimelineIndex.value > 0);

const showTimelineControls = computed(() => {
  return isScreenshotReplayMode.value || toolTimelineIndex.value >= 0
});

// Effective timeline values — replay mode overrides tool timeline
const effectiveTimelineProgress = computed(() =>
  isScreenshotReplayMode.value ? replay.progress.value : toolTimelineProgress.value
);
const effectiveTimelineTimestamp = computed(() =>
  isScreenshotReplayMode.value ? replay.currentTimestamp.value : toolTimelineTimestamp.value
);
const effectiveCanStepForward = computed(() =>
  isScreenshotReplayMode.value ? replay.canStepForward.value : toolTimelineCanStepForward.value
);
const effectiveCanStepBackward = computed(() =>
  isScreenshotReplayMode.value ? replay.canStepBackward.value : toolTimelineCanStepBackward.value
);

// Handle opening the panel from TaskProgressBar
const handleOpenPanel = () => {
  if (lastNoMessageTool.value) {
    toolPanel.value?.showToolPanel(lastNoMessageTool.value, isLiveTool(lastNoMessageTool.value));
    panelToolId.value = lastNoMessageTool.value.tool_call_id;
  } else if (sessionId.value) {
    // Allow opening panel even without tool content - show live sandbox view
    const placeholderTool: ToolContent = {
      tool_call_id: `placeholder-${Date.now()}`,
      name: 'browser',
      function: 'browser_view',
      args: {},
      status: 'completed',
      timestamp: Date.now(),
    };
    toolPanel.value?.showToolPanel(placeholderTool, true);
    panelToolId.value = placeholderTool.tool_call_id;
  }
};

const upsertToolTimeline = (toolContent: ToolContent) => {
  if (!isComputerTool(toolContent)) return;
  const existingIndex = toolTimeline.value.findIndex(tool => tool.tool_call_id === toolContent.tool_call_id);
  if (existingIndex >= 0) {
    Object.assign(toolTimeline.value[existingIndex], toolContent);
    return;
  }
  toolTimeline.value.push(toolContent);
};

const maybeAppendAssistantMessageToStep = (messageData: MessageEventData): boolean => {
  if (messageData.role !== 'assistant') return false;

  const text = (messageData.content || '').trim();
  if (!text) return false;

  // Long messages with markdown structure (bullets, bold) are standalone summaries,
  // not step narrations — render them as top-level chat messages.
  if (text.length > 200 && (text.includes('- **') || text.includes('* **'))) {
    return false;
  }

  const lastMessage = messages.value[messages.value.length - 1];
  if (!lastMessage || lastMessage.type !== 'step') return false;

  const lastStep = lastMessage.content as StepContent;
  if (!lastStep || (lastStep.status !== 'running' && lastStep.status !== 'completed')) {
    return false;
  }

  const lastTool = lastStep.tools[lastStep.tools.length - 1];
  if (lastTool?.name === 'message' && String(lastTool.args?.text || '') === text) {
    return true;
  }

  lastStep.tools.push({
    tool_call_id: `inline-message-${messageData.timestamp}-${lastStep.tools.length}`,
    name: 'message',
    function: 'message',
    args: { text },
    status: 'called',
    timestamp: messageData.timestamp,
  });

  return true;
};

// Handle message event
const handleMessageEvent = (messageData: MessageEventData) => {
  // Assistant message means agent finished thinking
  if (messageData.role === 'assistant') {
    isThinking.value = false;
    // Track anchor event ID for follow-up suggestions
    followUpAnchorEventId.value = messageData.event_id;
  }

  // Clear summary streaming overlay — message takes over
  summaryStreamText.value = '';
  isSummaryStreaming.value = false;

  // Keep per-step narration nested inside the active step thread.
  if (maybeAppendAssistantMessageToStep(messageData)) {
    return;
  }

  // Prevent duplicate user messages - check against LAST user message (not just last message)
  // This handles cases where tool/step events appear between duplicate user messages
  if (messageData.role === 'user' && messages.value.length > 0) {
    const incomingContent = (messageData.content || '').trim();
    // Find the last user message in the array
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].type === 'user') {
        const lastUserContent = messages.value[i].content as MessageContent;
        if ((lastUserContent.content || '').trim() === incomingContent) {
          console.debug('Skipping duplicate user message:', messageData.content?.slice(0, 50));
          return;
        }
        break; // Only check the most recent user message
      }
    }
  }

  // Prevent duplicate assistant messages with same content
  if (messageData.role === 'assistant' && messages.value.length > 0) {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].type === 'assistant') {
        const lastAssistantContent = messages.value[i].content as MessageContent;
        if (lastAssistantContent.content === messageData.content) {
          console.debug('Skipping duplicate assistant message:', messageData.content?.slice(0, 50));
          return;
        }
        break; // Only check the most recent assistant message
      }
    }
  }

  messages.value.push({
    id: generateMessageId(),
    type: messageData.role,
    content: {
      ...messageData
    } as MessageContent,
  });

  if (messageData.attachments?.length > 0) {
    messages.value.push({
      id: generateMessageId(),
      type: 'attachments',
      content: {
        ...messageData
      } as AttachmentsContent,
    });
  }
}

// Handle tool event
const handleToolEvent = (toolData: ToolEventData) => {
  // Tool being called means agent is actively working
  if (toolData.status === 'calling' || toolData.status === 'running') {
    isThinking.value = true;
  }

  const lastStep = getLastStep();
  const toolContent: ToolContent = {
    ...toolData
  }
  if (lastTool.value && lastTool.value.tool_call_id === toolContent.tool_call_id) {
    Object.assign(lastTool.value, toolContent);
  } else {
    if (lastStep?.status === 'running') {
      // Check if tool already exists in this step (avoid duplicates from SSE reconnection)
      const existingTool = lastStep.tools.find(t => t.tool_call_id === toolContent.tool_call_id);
      if (existingTool) {
        Object.assign(existingTool, toolContent);
      } else {
        lastStep.tools.push(toolContent);
      }
    } else {
      messages.value.push({
        id: generateMessageId(),
        type: 'tool',
        content: toolContent,
      });
    }
    lastTool.value = toolContent;
  }
  if (toolContent.name !== 'message') {
    lastNoMessageTool.value = toolContent;
    upsertToolTimeline(toolContent);
    if (realTime.value) {
      panelToolId.value = toolContent.tool_call_id;
      if (isToolPanelOpen.value) {
        // Auto-switch panel content when panel is open and new tool starts
        toolPanel.value?.showToolPanel(toolContent, isLiveTool(toolContent));
      }
    }
  }
}

// Handle phase event - creates/updates phase message groups
const handlePhaseEvent = (phaseData: import('../types/event').AgentPhaseEventData) => {
  if (phaseData.status === 'started') {
    messages.value.push({
      id: generateMessageId(),
      type: 'phase',
      content: {
        phase_id: phaseData.phase_id,
        phase_type: phaseData.phase_type,
        label: phaseData.label,
        status: phaseData.status,
        order: phaseData.order,
        icon: phaseData.icon,
        color: phaseData.color,
        total_phases: phaseData.total_phases,
        steps: [],
        timestamp: phaseData.timestamp || Date.now(),
      } as import('../types/message').PhaseContent,
    })
  } else if (phaseData.status === 'completed' || phaseData.status === 'skipped') {
    // Find and update the phase message
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const msg = messages.value[i]
      if (msg.type === 'phase') {
        const pc = msg.content as import('../types/message').PhaseContent
        if (pc.phase_id === phaseData.phase_id) {
          pc.status = phaseData.status
          if (phaseData.skip_reason) pc.skip_reason = phaseData.skip_reason
          break
        }
      }
    }
  }
}

// Find the current active phase message (if any)
const findActivePhaseMessage = (phaseId: string | undefined) => {
  if (!phaseId) return null
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const msg = messages.value[i]
    if (msg.type === 'phase') {
      const pc = msg.content as import('../types/message').PhaseContent
      if (pc.phase_id === phaseId) return pc
    }
  }
  return null
}

// Handle step event
const handleStepEvent = (stepData: StepEventData) => {
  const lastStep = getLastStep();
  if (stepData.status === 'running') {
    isThinking.value = true;
    const stepContent: StepContent = {
      ...stepData,
      tools: [],
      phase_id: stepData.phase_id,
      step_type: stepData.step_type,
    }

    // Try to nest step inside its phase group
    const phaseContent = findActivePhaseMessage(stepData.phase_id)
    if (phaseContent) {
      phaseContent.steps.push(stepContent)
    }

    // Always push as top-level message too (for timeline rendering)
    messages.value.push({
      id: generateMessageId(),
      type: 'step',
      content: stepContent,
    });
  } else if (stepData.status === 'completed') {
    isThinking.value = false;
    // Find the matching step by ID and update its status
    const matchingStep = messages.value
      .filter(m => m.type === 'step')
      .map(m => m.content as StepContent)
      .find(s => s.id === stepData.id);
    if (matchingStep) {
      matchingStep.status = stepData.status;
    } else if (lastStep) {
      // Fallback: update last step if no ID match
      lastStep.status = stepData.status;
    }
    // Also update in phase
    if (stepData.phase_id) {
      const phaseContent = findActivePhaseMessage(stepData.phase_id)
      if (phaseContent) {
        const phaseStep = phaseContent.steps.find(s => s.id === stepData.id)
        if (phaseStep) phaseStep.status = stepData.status
      }
    }
  } else if (stepData.status === 'failed') {
    isThinking.value = false;
    isLoading.value = false;
    // Notify sidebar that session is no longer running
    if (sessionId.value) {
      emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
    }
  }
}

// Handle error event
const handleErrorEvent = (errorData: ErrorEventData) => {
  isLoading.value = false;
  isThinking.value = false;
  messages.value.push({
    id: generateMessageId(),
    type: 'assistant',
    content: {
      content: errorData.error,
      timestamp: errorData.timestamp
    } as MessageContent,
  });
  // Notify sidebar that session is no longer running
  if (sessionId.value) {
    emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
  }
}

// Handle title event
const handleTitleEvent = (titleData: TitleEventData) => {
  title.value = titleData.title;
  if (sessionId.value && titleData.title?.trim()) {
    emitSessionTitleHint({
      sessionId: sessionId.value,
      title: titleData.title,
      status: sessionStatus.value,
    });
  }
}

// Handle plan event
const handlePlanEvent = (planData: PlanEventData) => {
  // Clear thinking text and planning progress when plan arrives
  thinkingText.value = '';
  isThinkingStreaming.value = false;
  planningProgress.value = null;  // Clear progress - plan is ready
  stopPlanningMessageCycle();
  plan.value = planData;
}

// Handle stream event (thinking text streaming or summary streaming)
const handleStreamEvent = (streamData: StreamEventData) => {
  researchWorkflow.handleStreamEvent(streamData);
  if (streamData.phase === 'reflection') {
    syncDeepResearchMessageMetadata();
  }
  const phase = streamData.phase || 'thinking';

  if (phase === 'summarizing') {
    if (streamData.is_final) {
      isSummaryStreaming.value = false;
      // Keep text visible briefly — cleared when ReportEvent arrives
    } else {
      isSummaryStreaming.value = true;
      summaryStreamText.value += streamData.content;
    }
    return;
  }

  // Default: thinking phase (existing behavior)
  if (streamData.is_final) {
    isThinkingStreaming.value = false;
    thinkingText.value = '';
  } else {
    isThinkingStreaming.value = true;
    thinkingText.value += streamData.content;
  }
}

// ===== Planning Messages - Interesting rotating phrases =====
const PLANNING_MESSAGES = [
  "Analyzing task complexity...",
  "Mapping out the approach...",
  "Crafting the perfect strategy...",
  "Connecting the dots...",
  "Architecting the solution...",
  "Weighing the options...",
  "Charting the course...",
  "Piecing together the puzzle...",
  "Calibrating the plan...",
  "Orchestrating the steps...",
  "Fine-tuning the approach...",
  "Exploring possibilities...",
  "Building the roadmap...",
  "Designing the workflow...",
  "Structuring the execution...",
];

const planningMessageIndex = ref(0);
let planningMessageInterval: ReturnType<typeof setInterval> | null = null;

// Cycle through planning messages for visual interest
const startPlanningMessageCycle = () => {
  if (planningMessageInterval) return;
  planningMessageIndex.value = Math.floor(Math.random() * PLANNING_MESSAGES.length);
  planningMessageInterval = setInterval(() => {
    planningMessageIndex.value = (planningMessageIndex.value + 1) % PLANNING_MESSAGES.length;
  }, 2500);
};

const stopPlanningMessageCycle = () => {
  if (planningMessageInterval) {
    clearInterval(planningMessageInterval);
    planningMessageInterval = null;
  }
};

// Computed: current planning message (cycles through interesting phrases)
const currentPlanningMessage = computed(() => {
  return PLANNING_MESSAGES[planningMessageIndex.value];
});

// Handle progress event (instant feedback during planning)
const handleProgressEvent = (progressData: ProgressEventData) => {
  // Start message cycling if not already running
  startPlanningMessageCycle();

  // Update planning progress for UI
  planningProgress.value = {
    phase: progressData.phase,
    message: progressData.message,
    percent: progressData.progress_percent || 0
  };

  // Clear initialization state on first progress event
  if (isInitializing.value) {
    isInitializing.value = false;
  }

  // Clear progress when planning is complete (plan event will follow)
  if (progressData.phase === 'finalizing' && progressData.progress_percent && progressData.progress_percent >= 80) {
    // Keep progress visible until plan arrives
  }
}

// Handle mode change event
const handleModeChangeEvent = (modeData: ModeChangeEventData) => {
  agentMode.value = modeData.mode;
}

// Handle suggestion event
const handleSuggestionEvent = (suggestionData: SuggestionEventData) => {
  suggestions.value = suggestionData.suggestions;
  if (suggestionData.anchor_event_id) {
    followUpAnchorEventId.value = suggestionData.anchor_event_id;
  }
}

const SUGGESTION_STOPWORDS = new Set([
  'about', 'after', 'again', 'also', 'been', 'before', 'being', 'between', 'could', 'does',
  'from', 'have', 'into', 'just', 'make', 'more', 'most', 'only', 'over', 'same',
  'that', 'than', 'their', 'them', 'then', 'there', 'they', 'this', 'what', 'when',
  'where', 'which', 'while', 'will', 'with', 'would', 'your'
]);

const extractTopicHint = (text: string): string | null => {
  const cleaned = text
    .toLowerCase()
    .replace(/[`*_#>[\](){}.,!?;:"']/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (!cleaned) return null;

  const tokens = cleaned
    .split(' ')
    .filter(token => token.length >= 4 && !SUGGESTION_STOPWORDS.has(token));

  if (tokens.length === 0) return null;
  return tokens.slice(0, 3).join(' ');
};

const buildCompletionFallbackSuggestions = (): string[] => {
  let assistantContext = '';
  let latestUserMessage = '';

  for (let i = messages.value.length - 1; i >= 0; i--) {
    const message = messages.value[i];
    if (message.type === 'assistant') {
      if (!assistantContext) {
        assistantContext = (message.content as MessageContent).content || '';
      }
      continue;
    }
    if (message.type === 'report') {
      if (!assistantContext) {
        const reportContent = message.content as ReportContent;
        assistantContext = `${reportContent.title || ''} ${reportContent.content || ''}`;
      }
      continue;
    }
    if (message.type === 'user') {
      latestUserMessage = ((message.content as MessageContent).content || '').trim();
      break;
    }
  }

  const contextText = `${latestUserMessage} ${assistantContext}`.toLowerCase();
  const topicHint = extractTopicHint(`${latestUserMessage} ${assistantContext}`);

  if (contextText.includes('pirate') || /\barrr+\b/.test(contextText)) {
    return [
      "Tell me a pirate story.",
      "What's your favorite pirate saying?",
      "How do pirates find treasure?",
    ];
  }

  if (topicHint) {
    return [
      `Can you expand on ${topicHint} with an example?`,
      `What are the best next steps for ${topicHint}?`,
      `What trade-offs should I consider for ${topicHint}?`,
    ];
  }

  return [
    "Can you explain this in more detail?",
    "What are the best next steps?",
    "Can you give me a practical example?",
  ];
};

const ensureCompletionSuggestions = () => {
  if (suggestions.value.length > 0) return;
  suggestions.value = buildCompletionFallbackSuggestions();

  // Find anchor event ID from latest assistant or report message
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const message = messages.value[i];
    if (message.type === 'assistant') {
      const content = message.content as MessageContent;
      if (content.event_id) {
        followUpAnchorEventId.value = content.event_id;
        break;
      }
    }
    if (message.type === 'report') {
      const content = message.content as ReportContent;
      if (content.event_id) {
        followUpAnchorEventId.value = content.event_id;
        break;
      }
    }
  }
};

// Handle report event
const handleReportEvent = (reportData: ReportEventData) => {
  // Clear summary streaming overlay — report card takes over
  summaryStreamText.value = '';
  isSummaryStreaming.value = false;

  // Track anchor event ID for follow-up suggestions
  followUpAnchorEventId.value = reportData.event_id;

  const sections = extractSectionsFromMarkdown(reportData.content);
  messages.value.push({
    id: generateMessageId(),
    type: 'report',
    content: {
      id: reportData.id,
      title: reportData.title,
      content: reportData.content,
      lastModified: reportData.timestamp * 1000,
      fileCount: reportData.attachments?.length || 0,
      sections,
      sources: reportData.sources,
      attachments: reportData.attachments,
      timestamp: reportData.timestamp
    } as ReportContent,
  });
}

// Handle deep research event
const handleDeepResearchEvent = (data: DeepResearchEventData) => {
  const workflowState = researchWorkflow.handleDeepResearchEvent(data);

  // Find existing deep research message
  const idx = messages.value.findIndex(
    m => m.type === 'deep_research' &&
         (m.content as DeepResearchContent).research_id === data.research_id
  );

  if (idx >= 0) {
    // Update existing message
    const existingContent = messages.value[idx].content as DeepResearchContent;
    messages.value[idx].content = {
      ...existingContent,
      status: workflowState.status,
      queries: data.queries,
      completed_count: data.completed_queries,
      total_count: data.total_queries,
      auto_run: data.auto_run,
      phase: workflowState.phase ?? undefined,
      phase_label: workflowState.phase_label ?? undefined,
      latest_reflection: workflowState.latest_reflection,
      checkpoints: workflowState.checkpoints,
    } as DeepResearchContent;
  } else {
    // Create new message
    messages.value.push({
      id: generateMessageId(),
      type: 'deep_research',
      content: {
        research_id: data.research_id,
        status: workflowState.status,
        queries: data.queries || [],
        completed_count: data.completed_queries,
        total_count: data.total_queries,
        auto_run: data.auto_run,
        phase: workflowState.phase ?? undefined,
        phase_label: workflowState.phase_label ?? undefined,
        latest_reflection: workflowState.latest_reflection,
        checkpoints: workflowState.checkpoints,
        timestamp: data.timestamp
      } as DeepResearchContent
    });
  }
};

const syncDeepResearchMessageMetadata = (researchId?: string) => {
  const findTargetIndex = (): number => {
    if (researchId) {
      return messages.value.findIndex(
        (message) =>
          message.type === 'deep_research' &&
          (message.content as DeepResearchContent).research_id === researchId,
      );
    }

    for (let i = messages.value.length - 1; i >= 0; i -= 1) {
      if (messages.value[i].type === 'deep_research') return i;
    }
    return -1;
  };

  const idx = findTargetIndex();
  if (idx < 0) return;

  const current = messages.value[idx].content as DeepResearchContent;
  const workflowState = researchWorkflow.getDeepResearchState(current.research_id, current.status);
  messages.value[idx].content = {
    ...current,
    phase: workflowState.phase ?? undefined,
    phase_label: workflowState.phase_label ?? undefined,
    latest_reflection: workflowState.latest_reflection,
    checkpoints: workflowState.checkpoints,
  } as DeepResearchContent;
};

const handlePhaseTransitionEvent = (data: PhaseTransitionEventData) => {
  researchWorkflow.handlePhaseTransitionEvent(data);
  syncDeepResearchMessageMetadata(data.research_id);
};

const handleCheckpointSavedEvent = (data: CheckpointSavedEventData) => {
  researchWorkflow.handleCheckpointSavedEvent(data);
  syncDeepResearchMessageMetadata(data.research_id);
};

// Handle deep research run (approve)
const handleDeepResearchRun = async (_researchId: string) => {
  if (!sessionId.value) return;
  try {
    await agentApi.approveDeepResearch(sessionId.value);
  } catch {
    showErrorToast(t('Failed to start research'));
  }
};

// Handle deep research skip
const handleDeepResearchSkip = async (_researchId: string, queryId?: string) => {
  if (!sessionId.value) return;
  try {
    await agentApi.skipDeepResearchQuery(sessionId.value, queryId);
  } catch {
    showErrorToast(t('Failed to skip query'));
  }
};

// Handle toggle auto-run preference
const handleToggleAutoRun = () => {
  toggleAutoRun();
};

// Handle wide research SSE events
const handleWideResearchEvent = (data: WideResearchEventData) => {
  researchWorkflow.handleWideResearchEvent(data);
};

// Handle skill delivery events
const handleSkillDeliveryEvent = (data: SkillDeliveryEventData) => {
  showInfoToast(`Skill "${data.name}" package ready`);
  messages.value.push({
    id: generateMessageId(),
    type: 'skill_delivery',
    content: {
      package_id: data.package_id,
      name: data.name,
      description: data.description,
      version: data.version,
      icon: data.icon,
      category: data.category,
      author: data.author,
      file_tree: data.file_tree,
      files: data.files,
      file_id: data.file_id,
      skill_id: data.skill_id,
      timestamp: data.timestamp,
    } as SkillDeliveryContent,
  });
};

// Handle skill activation events
const handleSkillActivationEvent = (data: SkillActivationEventData) => {
  if (data.skill_names.length > 0) {
    showInfoToast(`Skills activated: ${data.skill_names.join(', ')}`);
  }
  // Lock activated skills for the session so they persist across messages
  if (data.skill_ids?.length > 0) {
    lockSkillsForSession(data.skill_ids);
  }
};

// Handle canvas update events
const handleCanvasUpdateEvent = (data: CanvasUpdateEventData) => {
  activeCanvasProjectId.value = data.project_id;
};

// Handle suggestion selection (user clicks a suggestion)
const handleSuggestionSelect = (suggestion: string) => {
  inputMessage.value = suggestion;
  pendingFollowUpSuggestion.value = suggestion; // Track that this came from a suggestion
  suggestions.value = []; // Clear suggestions after selection
  handleSubmit();
}

// Handle report open (from ChatMessage)
const handleReportOpen = (report: ReportData) => {
  openReport(report);
}

const closeFilePreview = () => {
  filePreviewOpen.value = false;
  filePreviewFile.value = null;
};

// Handle report file open
const handleReportFileOpen = (file: FileInfo) => {
  hideFilePanel();
  filePreviewFile.value = file;
  filePreviewOpen.value = true;
}

// Handle attached file click (open in modal)
const handleAttachmentFileClick = (file: FileInfo) => {
  hideFilePanel();
  filePreviewFile.value = file;
  filePreviewOpen.value = true;
}

// Handle report rate
const handleReportRate = async (rating: number, feedback?: string) => {
  if (!sessionId.value || !currentReport.value) return;
  try {
    await agentApi.submitRating(sessionId.value, currentReport.value.id, rating, feedback);
    showSuccessToast(t('Rating submitted'));
  } catch {
    showErrorToast(t('Failed to submit rating'));
  }
}

// Handle report download
const handleReportDownload = () => {
  if (!currentReport.value) return;

  const blob = new Blob([currentReport.value.content], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${currentReport.value.title.replace(/[^a-zA-Z0-9]/g, '_')}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ===== Event Batching for Performance =====
// Batch rapid SSE events and process them together to reduce re-renders
let eventBatchQueue: AgentSSEEvent[] = [];
let batchFrameId: number | null = null;

const flushEventBatch = () => {
  batchFrameId = null;
  const eventsToProcess = eventBatchQueue;
  eventBatchQueue = [];

  for (const event of eventsToProcess) {
    processEvent(event);
  }
};

const queueEvent = (event: AgentSSEEvent) => {
  eventBatchQueue.push(event);

  // Schedule batch processing on next animation frame if not already scheduled
  if (batchFrameId === null) {
    batchFrameId = requestAnimationFrame(flushEventBatch);
  }
};

// Process a single event (extracted from handleEvent for batching)
const processEvent = (event: AgentSSEEvent) => {
  // Deduplicate events based on event_id to prevent duplicate messages
  const eventId = event.data?.event_id;
  if (eventId && seenEventIds.value.has(eventId)) {
    console.debug('Skipping duplicate event:', eventId);
    return;
  }
  if (eventId) {
    // Phase 5: Use addSeenEventId for automatic cleanup when set grows too large
    addSeenEventId(eventId);
  }

  // End initialization phase when first event arrives
  if (isInitializing.value) {
    isInitializing.value = false;
  }

  // Update last event time for stale connection detection
  updateLastEventTime();

  if (event.event === 'message') {
    handleMessageEvent(event.data as MessageEventData);
    // Clear suggestions when new message arrives
    suggestions.value = [];
  } else if (event.event === 'tool') {
    handleToolEvent(event.data as ToolEventData);
  } else if (event.event === 'step') {
    handleStepEvent(event.data as StepEventData);
  } else if (event.event === 'phase') {
    handlePhaseEvent(event.data as import('../types/event').AgentPhaseEventData);
  } else if (event.event === 'done') {
    ensureCompletionSuggestions();
    isResponseSettled.value = true;
    isLoading.value = false;
    isThinking.value = false;
    isWaitingForReply.value = false;
    // Notify sidebar that session is no longer running
    if (sessionId.value) {
      emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
    }
    // Load screenshots for replay mode (seamless live → replay transition)
    sessionStatus.value = SessionStatus.COMPLETED;
    replay.loadScreenshots();
  } else if (event.event === 'wait') {
    isResponseSettled.value = true;
    // Agent is waiting for user input - show waiting indicator
    isWaitingForReply.value = true;
    isLoading.value = false;
    isThinking.value = false;
  } else if (event.event === 'error') {
    isResponseSettled.value = true;
    handleErrorEvent(event.data as ErrorEventData);
  } else if (event.event === 'title') {
    handleTitleEvent(event.data as TitleEventData);
  } else if (event.event === 'plan') {
    handlePlanEvent(event.data as PlanEventData);
  } else if (event.event === 'mode_change') {
    handleModeChangeEvent(event.data as ModeChangeEventData);
  } else if (event.event === 'suggestion') {
    handleSuggestionEvent(event.data as SuggestionEventData);
  } else if (event.event === 'report') {
    handleReportEvent(event.data as ReportEventData);
  } else if (event.event === 'stream') {
    handleStreamEvent(event.data as StreamEventData);
  } else if (event.event === 'progress') {
    handleProgressEvent(event.data as ProgressEventData);
  } else if (event.event === 'deep_research') {
    handleDeepResearchEvent(event.data as DeepResearchEventData);
  } else if (event.event === 'wide_research') {
    handleWideResearchEvent(event.data as WideResearchEventData);
  } else if (event.event === 'phase_transition') {
    handlePhaseTransitionEvent(event.data as PhaseTransitionEventData);
  } else if (event.event === 'checkpoint_saved') {
    handleCheckpointSavedEvent(event.data as CheckpointSavedEventData);
  } else if (event.event === 'skill_delivery') {
    handleSkillDeliveryEvent(event.data as SkillDeliveryEventData);
  } else if (event.event === 'skill_activation') {
    handleSkillActivationEvent(event.data as SkillActivationEventData);
  } else if (event.event === 'canvas_update') {
    handleCanvasUpdateEvent(event.data as CanvasUpdateEventData);
  }
  lastEventId.value = event.data.event_id;
  // Persist lastEventId to sessionStorage for proper event resumption on page refresh
  if (event.data.event_id && sessionId.value) {
    sessionStorage.setItem(`pythinker-last-event-${sessionId.value}`, event.data.event_id);
  }
}

// Public event handler - queues events for batched processing
const handleEvent = (event: AgentSSEEvent) => {
  queueEvent(event);
};

const handleSubmit = () => {
  chat(inputMessage.value, attachments.value);
}

// Track last sent message to prevent duplicate submissions
let lastSentMessage = '';
let lastSentTime = 0;

const chat = async (
  message: string = '',
  files: FileInfo[] = [],
  options?: { skipOptimistic?: boolean }
) => {
  if (!sessionId.value) return;
  const normalizedMessage = message.trim();

  // Prevent duplicate message submission within 2 seconds
  const now = Date.now();
  if (normalizedMessage && normalizedMessage === lastSentMessage && now - lastSentTime < 2000) {
    console.debug('Preventing duplicate message submission');
    return;
  }
  if (normalizedMessage) {
    lastSentMessage = normalizedMessage;
    lastSentTime = now;
  }

  // Build follow-up context if this message came from a suggestion click
  const followUp = pendingFollowUpSuggestion.value && followUpAnchorEventId.value
    ? {
        selected_suggestion: pendingFollowUpSuggestion.value,
        anchor_event_id: followUpAnchorEventId.value,
        source: 'suggestion_click' as const,
      }
    : null;

  // Clear pending follow-up state after building the context
  pendingFollowUpSuggestion.value = undefined;

  // Cancel any existing chat connection before starting a new one
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }

  // Automatically enable follow mode when sending message
  follow.value = true;

  if (!options?.skipOptimistic && (normalizedMessage || files.length > 0)) {
    addOptimisticUserMessage(normalizedMessage, files);
  }

  // Clear input field and per-message skill picks (session skills persist)
  inputMessage.value = '';
  clearSelectedSkills();
  suggestions.value = [];
  isResponseSettled.value = false;
  isLoading.value = true;
  isWaitingForReply.value = false;

  // Set initialization state when starting a new chat
  // (when there are no messages or only 1 message which is the user's first message)
  if (normalizedMessage && !hasAgentStartedResponding.value) {
    isInitializing.value = true;
  }

  try {
    // Use the split event handler function and store the cancel function
    cancelCurrentChat.value = await agentApi.chatWithSession(
      sessionId.value,
      normalizedMessage,
      lastEventId.value,
      files.map((file: FileInfo) => ({
        file_id: file.file_id,
        filename: file.filename,
        content_type: file.content_type,
        size: file.size,
        upload_date: file.upload_date
      })),
      getEffectiveSkillIds(), // session + per-message skills
      undefined, // options
      {
        onOpen: () => {
          isLoading.value = true;
        },
        onMessage: ({ event, data }) => {
          handleEvent({
            event: event as AgentSSEEvent['event'],
            data: data as AgentSSEEvent['data']
          });
        },
        onClose: () => {
          isResponseSettled.value = true;
          isLoading.value = false;
          isThinking.value = false;
          thinkingText.value = '';
          isThinkingStreaming.value = false;
          summaryStreamText.value = '';
          isSummaryStreaming.value = false;
          isInitializing.value = false;
          planningProgress.value = null;
          stopPlanningMessageCycle();
          // Clear the cancel function when connection is closed normally
          if (cancelCurrentChat.value) {
            cancelCurrentChat.value = null;
          }
          // Note: Status change is handled by DoneEvent (line 1662)
          // Don't set COMPLETED here - onClose fires for stops, errors, and refreshes too
        },
        onError: () => {
          isResponseSettled.value = true;
          isLoading.value = false;
          isThinking.value = false;
          thinkingText.value = '';
          isThinkingStreaming.value = false;
          summaryStreamText.value = '';
          isSummaryStreaming.value = false;
          isInitializing.value = false;
          planningProgress.value = null;
          stopPlanningMessageCycle();
          // Clear the cancel function when there's an error
          if (cancelCurrentChat.value) {
            cancelCurrentChat.value = null;
          }
          // Notify sidebar that session is no longer running
          if (sessionId.value) {
            emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
          }
        }
      },
      followUp
    );
  } catch {
    isLoading.value = false;
    cancelCurrentChat.value = null;
  }
}

const restoreSession = async () => {
  if (!sessionId.value) {
    showErrorToast(t('Session not found'));
    return;
  }

  // Load lastEventId from sessionStorage for proper event resumption
  const savedEventId = sessionStorage.getItem(`pythinker-last-event-${sessionId.value}`);
  if (savedEventId) {
    lastEventId.value = savedEventId;
    console.log('[RESTORE] Loaded lastEventId from sessionStorage:', savedEventId);
  }

  const session = await agentApi.getSession(sessionId.value);
  sessionStatus.value = session.status as SessionStatus;
  console.log('[RESTORE] Session:', sessionId.value, 'Status:', sessionStatus.value, 'LastEventId:', lastEventId.value);

  // Initialize share mode based on session state
  shareMode.value = session.is_shared ? 'public' : 'private';
  realTime.value = false;
  for (const event of session.events) {
    handleEvent(event);
  }
  realTime.value = true;
  if (sessionStatus.value === SessionStatus.INITIALIZING) {
    await waitForSessionIfInitializing();
  }
  if (sessionStatus.value === SessionStatus.RUNNING || sessionStatus.value === SessionStatus.PENDING) {
    // Check if this session was manually stopped (prevents auto-resume on page refresh)
    // Using sessionStorage: persists on refresh, cleared on tab close
    const stoppedKey = `pythinker-stopped-${sessionId.value}`;
    const wasManuallyStopped = sessionStorage.getItem(stoppedKey);

    if (wasManuallyStopped) {
      console.log('[RESTORE] Session was manually stopped, not auto-resuming');
      sessionStorage.removeItem(stoppedKey);
      // Trust the stop flag - user explicitly stopped this session
      // Don't resume even if backend says RUNNING (backend stop might be async)
      return;
    }

    // No stop flag - safe to auto-resume
    console.log('[RESTORE] No stop flag, auto-resuming session');
    await chat();
  } else if (sessionStatus.value === SessionStatus.COMPLETED || sessionStatus.value === SessionStatus.FAILED) {
    // Load screenshots for replay mode
    replay.loadScreenshots()
  }
  agentApi.clearUnreadMessageCount(sessionId.value);
}



onBeforeRouteUpdate(async (to, from, next) => {
  if (skipNextRouteReset.value) {
    skipNextRouteReset.value = false;
    if (to.params.sessionId) {
      sessionId.value = String(to.params.sessionId);
    }
    next();
    return;
  }

  // Stop the current session if it's still running to release sandbox/browser resources
  const prevSessionId = from.params.sessionId as string | undefined;
  if (prevSessionId && shouldStopSessionOnExit(sessionStatus.value)) {
    try {
      await agentApi.stopSession(prevSessionId);
      emitStatusChange(prevSessionId, SessionStatus.COMPLETED);
    } catch {
      // Non-critical — backend safety net will clean up
    }
  }

  toolPanel.value?.clearContent();  // Clear tool panel content when switching sessions
  hideFilePanel();
  resetState();
  if (to.params.sessionId) {
    messages.value = [];
    sessionId.value = String(to.params.sessionId) as string;
    restoreSession();
  }
  next();
})

// Initialize active conversation
// Handle insert message event from settings (e.g., "Build with Pythinker" button)
const handleInsertMessage = (event: Event) => {
  const detail = (event as CustomEvent<{ message: string; skillId?: string }>).detail;
  inputMessage.value = detail.message;
  // Auto-select the skill if provided
  if (detail.skillId) {
    selectSkill(detail.skillId);
  }
};

onMounted(async () => {
  hideFilePanel();
  // Listen for message insert event from settings dialog
  window.addEventListener('pythinker:insert-chat-message', handleInsertMessage);
  window.addEventListener('resize', updateChatBottomDockStyle);

  if (typeof ResizeObserver !== 'undefined' && chatContainerRef.value) {
    chatContainerResizeObserver = new ResizeObserver(() => {
      updateChatBottomDockStyle();
    });
    chatContainerResizeObserver.observe(chatContainerRef.value);
  }
  await nextTick();
  updateChatBottomDockStyle();

  if (await initializePendingSession()) {
    return;
  }

  const routeParams = router.currentRoute.value.params;
  if (routeParams.sessionId) {
    if (routeParams.sessionId === 'new') {
      await router.replace('/chat');
      return;
    }
    // If sessionId is included in URL, use it directly
    sessionId.value = String(routeParams.sessionId) as string;
    // Get initial message from history.state
    const message = history.state?.message;
    const files: FileInfo[] = history.state?.files || [];
    history.replaceState({}, document.title);
    if (message) {
      addOptimisticUserMessage(message, files);
      isInitializing.value = true;
      pendingInitialMessage.value = { message, files };
      await refreshSessionStatus(sessionId.value);
      await waitForSessionIfInitializing();
      maybeSendPendingInitialMessage();
    } else {
      await restoreSession();
    }
  }
});

// ======================================================================
// Tab visibility: sync session status when user returns to tab
// ======================================================================
const documentVisibility = useDocumentVisibility();

watch(documentVisibility, async (newVisibility) => {
  if (newVisibility !== 'visible' || !sessionId.value) return;

  // Only check if session was active when we left
  const activeStatuses = [SessionStatus.RUNNING, SessionStatus.INITIALIZING, SessionStatus.PENDING];
  if (!activeStatuses.includes(sessionStatus.value)) return;

  try {
    const status = await agentApi.getSessionStatus(sessionId.value);
    if (status.status !== sessionStatus.value) {
      console.log('[VISIBILITY] Session status changed while away:', sessionStatus.value, '->', status.status);
      sessionStatus.value = status.status as SessionStatus;

      // If session completed/failed while tab was hidden, load final state
      if (status.status === 'completed' || status.status === 'failed') {
        replay.loadScreenshots();
      }
    }
  } catch {
    // Session may have been deleted — clear state
    console.log('[VISIBILITY] Session status check failed, session may no longer exist');
  }
});

// Keep session runtime alive when navigating away from chat.
// Sandbox teardown is handled by explicit stop/delete/new-task flows.
onBeforeRouteLeave(async (_to, _from, next) => {
  next();
});

onUnmounted(() => {
  window.removeEventListener('pythinker:insert-chat-message', handleInsertMessage);
  window.removeEventListener('resize', updateChatBottomDockStyle);
  if (chatContainerResizeObserver) {
    chatContainerResizeObserver.disconnect();
    chatContainerResizeObserver = null;
  }
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }
  // Cancel any pending event batch processing
  if (batchFrameId !== null) {
    cancelAnimationFrame(batchFrameId);
    batchFrameId = null;
  }
})

const isLastNoMessageTool = (tool: ToolContent) => {
  return tool.tool_call_id === lastNoMessageTool.value?.tool_call_id;
}

const isLiveTool = (tool: ToolContent) => {
  if (tool.status === 'calling') {
    return true;
  }
  if (!isLastNoMessageTool(tool)) {
    return false;
  }
  if (tool.timestamp > Date.now() - 5 * 60 * 1000) {
    return true;
  }
  return false;
}

const showToolFromTimeline = (index: number) => {
  if (toolTimeline.value.length === 0) return;
  const clampedIndex = Math.max(0, Math.min(index, toolTimeline.value.length - 1));
  const tool = toolTimeline.value[clampedIndex];
  if (!tool) return;
  realTime.value = false;
  panelToolId.value = tool.tool_call_id;
  toolPanel.value?.showToolPanel(tool, isLiveTool(tool));
}

const handleTimelineStepForward = () => {
  if (isScreenshotReplayMode.value) { replay.stepForward(); return; }
  if (!toolTimelineCanStepForward.value) return;
  showToolFromTimeline(toolTimelineIndex.value + 1);
}

const handleTimelineStepBackward = () => {
  if (isScreenshotReplayMode.value) { replay.stepBackward(); return; }
  if (!toolTimelineCanStepBackward.value) return;
  showToolFromTimeline(toolTimelineIndex.value - 1);
}

const handleTimelineSeek = (progress: number) => {
  if (isScreenshotReplayMode.value) { replay.seekByProgress(progress); return; }
  if (toolTimeline.value.length === 0) return;
  const maxIndex = toolTimeline.value.length - 1;
  const targetIndex = Math.round((progress / 100) * maxIndex);
  showToolFromTimeline(targetIndex);
}

const handleToolClick = (tool: ToolContent) => {
  realTime.value = false;
  if (sessionId.value) {
    toolPanel.value?.showToolPanel(tool, isLiveTool(tool));
    panelToolId.value = tool.tool_call_id;
  }
}

const jumpToRealTime = () => {
  realTime.value = true;
  if (lastNoMessageTool.value) {
    toolPanel.value?.showToolPanel(lastNoMessageTool.value, isLiveTool(lastNoMessageTool.value));
    panelToolId.value = lastNoMessageTool.value.tool_call_id;
  }
}

const handleFollow = () => {
  follow.value = true;
  simpleBarRef.value?.scrollToBottom('smooth');
}

const handleScroll = (_: Event) => {
  follow.value = simpleBarRef.value?.isScrolledToBottom() ?? false;
}

const handleStop = () => {
  // Cancel the SSE stream FIRST to prevent any reconnect/resume logic
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }
  if (sessionId.value) {
    // Mark this session as manually stopped to prevent auto-resume on page refresh
    // Using sessionStorage: persists on refresh, cleared on tab close (better than localStorage)
    sessionStorage.setItem(`pythinker-stopped-${sessionId.value}`, 'true');
    // Clear lastEventId from sessionStorage since session is stopped (use centralized cleanup)
    cleanupSessionStorage(sessionId.value);
    agentApi.stopSession(sessionId.value);
    // Notify sidebar that session is no longer running
    emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
  }
  // Reset loading states
  isResponseSettled.value = true;
  isLoading.value = false;
  isThinking.value = false;
  isStale.value = false;
  thinkingText.value = '';
  isThinkingStreaming.value = false;
  summaryStreamText.value = '';
  isSummaryStreaming.value = false;
  isInitializing.value = false;
  planningProgress.value = null;
  stopPlanningMessageCycle();
}

const handleFileListShow = () => {
  showSessionFileList()
}

// Share functionality handlers
const handleShareModeChange = async (mode: 'private' | 'public') => {
  if (!sessionId.value || sharingLoading.value) return;
  
  // If mode is same as current, no need to call API
  if (shareMode.value === mode) {
    linkCopied.value = false;
    return;
  }
  
  try {
    sharingLoading.value = true;
    
    if (mode === 'public') {
      await agentApi.shareSession(sessionId.value);
    } else {
      await agentApi.unshareSession(sessionId.value);
    }
    
    shareMode.value = mode;
    linkCopied.value = false;
  } catch {
    showErrorToast(t('Failed to change sharing settings'));
  } finally {
    sharingLoading.value = false;
  }
}

const handleInstantShare = async () => {
  if (!sessionId.value) return;
  
  try {
    sharingLoading.value = true;
    await agentApi.shareSession(sessionId.value);
    shareMode.value = 'public';
    linkCopied.value = false;
  } catch {
    showErrorToast(t('Failed to share session'));
  } finally {
    sharingLoading.value = false;
  }
}

const handleCopyLink = async () => {
  if (!sessionId.value) return;
  
  const shareUrl = `${window.location.origin}/share/${sessionId.value}`;
  
  try {
    const success = await copyToClipboard(shareUrl);
    
    if (success) {
      linkCopied.value = true;
      setTimeout(() => {
        linkCopied.value = false;
      }, 3000);
      showSuccessToast(t('Link copied to clipboard'));
    } else {
      showErrorToast(t('Failed to copy link'));
    }
  } catch {
    showErrorToast(t('Failed to copy link'));
  }
}
</script>

<style scoped>
/* ===== CHAT HEADER ===== */
.chat-header {
  background-color: var(--background-gray-main);
}

.chat-model-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  height: 32px;
  border-radius: 8px;
  padding: 0 8px;
  transition: background-color 0.15s ease;
}

.chat-model-pill:hover {
  background: var(--fill-tsp-white-main);
}

.chat-title-text {
  color: var(--text-primary);
  font-size: 16px;
  line-height: 20px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.01em;
}

.chat-title-chevron {
  color: var(--text-tertiary);
  transform: rotate(90deg);
  flex-shrink: 0;
}

.chat-bottom-dock {
  padding-top: 8px;
  z-index: 20;
}

.chat-content-with-pinned-dock {
  padding-bottom: calc(8px + env(safe-area-inset-bottom));
}

.chat-messages-with-pinned-dock {
  padding-bottom: calc(196px + env(safe-area-inset-bottom));
}

.chat-messages-with-thumbnail-dock {
  padding-bottom: calc(296px + env(safe-area-inset-bottom));
}

.chat-bottom-dock-fixed {
  position: fixed;
  bottom: 0;
  z-index: 40;
  max-width: calc(100vw - 40px);
  padding-bottom: calc(12px + env(safe-area-inset-bottom));
}

:deep(.dark) .chat-bottom-dock,
.dark .chat-bottom-dock,
:deep(.dark) .chat-bottom-dock-fixed,
.dark .chat-bottom-dock-fixed {
  background: transparent;
}

@media (max-width: 640px) {
  .chat-messages-with-pinned-dock {
    padding-bottom: calc(212px + env(safe-area-inset-bottom));
  }

  .chat-messages-with-thumbnail-dock {
    padding-bottom: calc(312px + env(safe-area-inset-bottom));
  }
}

/* 120-degree diagonal shimmer text effect */
.thinking-text-shimmer {
  background: linear-gradient(
    120deg,
    #1f2937 0%,
    #1f2937 40%,
    #9ca3af 50%,
    #1f2937 60%,
    #1f2937 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: text-shimmer 2s ease-in-out infinite;
}

/* Dark mode */
:deep(.dark) .thinking-text-shimmer,
.dark .thinking-text-shimmer {
  background: linear-gradient(
    120deg,
    #e5e7eb 0%,
    #e5e7eb 40%,
    #6b7280 50%,
    #e5e7eb 60%,
    #e5e7eb 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

@keyframes text-shimmer {
  0% {
    background-position: 100% 0%;
  }
  100% {
    background-position: 0% 100%;
  }
}

/* ===== PLANNING PROGRESS SHIMMER ===== */
.planning-progress-indicator {
  transition: all 0.3s ease;
  background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.planning-thinking :deep(.thinking-lamp) {
  width: 20px;
  height: 24px;
}

.planning-percent {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  height: 24px;
  border-radius: 999px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-light);
}

.planning-text-shimmer {
  background: linear-gradient(
    120deg,
    #6b7280 0%,
    #6b7280 35%,
    #d1d5db 50%,
    #6b7280 65%,
    #6b7280 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: planning-shimmer 2.5s ease-in-out infinite;
}

/* Dark mode - planning shimmer (silver) */
:deep(.dark) .planning-text-shimmer,
.dark .planning-text-shimmer {
  background: linear-gradient(
    120deg,
    #9ca3af 0%,
    #9ca3af 35%,
    #f3f4f6 50%,
    #9ca3af 65%,
    #9ca3af 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

:deep(.dark) .planning-progress-indicator,
.dark .planning-progress-indicator {
  background: linear-gradient(180deg, #1f2937 0%, #111827 100%);
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.35);
}

@keyframes planning-shimmer {
  0% {
    background-position: 100% 50%;
  }
  50% {
    background-position: 0% 50%;
  }
  100% {
    background-position: 100% 50%;
  }
}

</style>
