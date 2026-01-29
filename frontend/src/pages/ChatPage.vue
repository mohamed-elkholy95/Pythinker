<template>
  <SimpleBar ref="simpleBarRef" @scroll="handleScroll">
    <div ref="chatContainerRef" class="relative flex flex-col h-full flex-1 min-w-0 px-5">
      <div ref="observerRef"
        class="chat-header sm:min-w-[390px] flex flex-row items-center justify-between py-3 gap-2 sticky top-0 z-10 flex-shrink-0">
        <div class="flex items-center flex-1">
          <div class="relative flex items-center">
            <div @click="toggleLeftPanel" v-if="!isLeftPanelShow"
              class="flex h-8 w-8 items-center justify-center cursor-pointer rounded-lg hover:bg-[var(--fill-tsp-gray-main)] transition-colors">
              <PanelLeft class="size-5 text-[var(--icon-secondary)]" />
            </div>
          </div>
        </div>
        <div class="max-w-full sm:max-w-[768px] sm:min-w-[390px] flex w-full flex-col overflow-hidden">
          <div
            class="text-[var(--text-primary)] text-base font-medium w-full flex flex-row items-center justify-between flex-1 min-w-0 gap-3">
            <div class="flex flex-row items-center gap-2 flex-1 min-w-0">
              <span class="whitespace-nowrap text-ellipsis overflow-hidden leading-relaxed">
                {{ title }}
              </span>
            </div>
            <div class="flex items-center gap-1 flex-shrink-0">
              <span class="relative flex-shrink-0" aria-expanded="false" aria-haspopup="dialog">
                <Popover>
                  <PopoverTrigger>
                    <button
                      class="h-8 px-3 rounded-lg inline-flex items-center gap-1.5 clickable border border-[var(--border-main)] hover:border-[var(--border-dark)] hover:bg-[var(--fill-tsp-white-main)] transition-all">
                      <ShareIcon color="var(--icon-secondary)" />
                      <span class="text-[var(--text-secondary)] text-sm font-medium">{{ t('Share') }}</span>
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
        </div>
        <div class="flex-1"></div>
      </div>
      <div class="mx-auto w-full max-w-full sm:max-w-[768px] sm:min-w-[390px] flex flex-col flex-1 min-h-[calc(100vh-60px)]">
        <div class="flex flex-col w-full gap-[12px] pb-[80px] pt-[12px] flex-1">
          <ChatMessage v-for="(message, index) in messages" :key="index" :message="message"
            :suggestions="message.type === 'report' ? suggestions : undefined"
            @toolClick="handleToolClick"
            @reportOpen="handleReportOpen"
            @reportFileOpen="handleReportFileOpen"
            @showAllFiles="handleFileListShow"
            @reportRate="handleReportRate"
            @selectSuggestion="handleSuggestionSelect"
            @deepResearchRun="handleDeepResearchRun"
            @deepResearchSkip="handleDeepResearchSkip"
            @toggleAutoRun="handleToggleAutoRun" />

          <!-- Loading/Thinking indicators - only show when no tool is actively being called -->
          <!-- Morphing shape thinking indicator - only shown when chat is actively thinking -->
          <div v-if="isLoading && (isThinkingStreaming || isThinking) && lastTool?.status !== 'calling'" class="flex flex-col">
            <div class="flex">
              <div class="w-[24px] relative h-4">
                <div class="border-l border-dashed border-[var(--border-dark)] absolute start-[8px] top-0 bottom-0"></div>
              </div>
              <div class="flex-1"></div>
            </div>
            <div class="flex items-center">
              <div class="w-[24px] flex items-center justify-center" style="padding-left: 3px;">
                <div class="thinking-shape-wrapper">
                  <ThinkingIndicator :showText="false" />
                </div>
              </div>
              <div class="flex-1 min-w-0">
                <span class="thinking-text-shimmer text-sm font-normal">Thinking</span>
              </div>
            </div>
          </div>
          <LoadingIndicator v-else-if="isLoading" :text="$t('Loading')" />

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

          <!-- Suggestions - only show standalone when last message is not a report -->
          <Suggestions
            v-if="suggestions.length > 0 && !isLoading && !hasReportMessage"
            :suggestions="suggestions"
            @select="handleSuggestionSelect"
          />
        </div>

        <div class="flex flex-col sticky bottom-0">
          <button @click="handleFollow" v-if="!follow"
            class="flex items-center justify-center w-[36px] h-[36px] rounded-full bg-[var(--background-white-main)] hover:bg-[var(--background-gray-main)] clickable border border-[var(--border-main)] shadow-[0px_5px_16px_0px_var(--shadow-S),0px_0px_1.25px_0px_var(--shadow-S)] absolute -top-20 left-1/2 -translate-x-1/2">
            <ArrowDown class="text-[var(--icon-primary)]" :size="20" />
          </button>
          <!-- Planning Progress Indicator - shows instant feedback before plan is ready -->
          <div
            v-if="!isToolPanelOpen && planningProgress && (!plan || plan.steps.length === 0)"
            class="planning-progress-indicator mb-2 bg-white dark:bg-[#2a2a2a] rounded-lg border border-gray-200 dark:border-[#3a3a3a] px-4 py-2.5 flex items-center gap-3 shadow-sm"
          >
            <div class="flex-shrink-0">
              <ThinkingIndicator :showText="false" />
            </div>
            <div class="flex-1 min-w-0">
              <span class="planning-text-shimmer text-[15px] font-medium">
                {{ currentPlanningMessage }}
              </span>
            </div>
          </div>

          <!-- Task Progress Bar - shown above ChatBox when ToolPanel is closed -->
          <TaskProgressBar
            v-if="!isToolPanelOpen && (plan?.steps?.length > 0 || lastNoMessageTool || isInitializing)"
            :plan="plan"
            :isLoading="isLoading"
            :isThinking="isThinking"
            :showThumbnail="shouldShowThumbnail"
            :sessionId="sessionId"
            :currentTool="currentToolInfo"
            :toolContent="lastNoMessageTool"
            :isInitializing="isInitializing"
            @openPanel="handleOpenPanel"
            @requestRefresh="handleThumbnailRefresh"
            class="mb-2"
          />
          <ChatBox v-model="inputMessage" :rows="1" @submit="handleSubmit" :isRunning="isLoading" @stop="handleStop"
            :attachments="attachments" @fileClick="handleAttachmentFileClick" />
        </div>
      </div>
    </div>
    <ToolPanel ref="toolPanel" :size="toolPanelSize" :sessionId="sessionId" :realTime="realTime"
      :isShare="false"
      :plan="plan"
      :isLoading="isLoading"
      :isThinking="isThinking"
      @jumpToRealTime="jumpToRealTime"
      :showTimeline="showTimelineControls"
      :timelineProgress="toolTimelineProgress"
      :timelineTimestamp="toolTimelineTimestamp"
      :timelineCanStepForward="toolTimelineCanStepForward"
      :timelineCanStepBackward="toolTimelineCanStepBackward"
      @timelineStepForward="handleTimelineStepForward"
      @timelineStepBackward="handleTimelineStepBackward"
      @timelineSeek="handleTimelineSeek"
      @panelStateChange="handlePanelStateChange" />
  </SimpleBar>

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
import { useRouter, onBeforeRouteUpdate } from 'vue-router';
import { useI18n } from 'vue-i18n';
import ChatBox from '../components/ChatBox.vue';
import ChatMessage from '../components/ChatMessage.vue';
import * as agentApi from '../api/agent';
import { Message, MessageContent, ToolContent, StepContent, AttachmentsContent, ReportContent } from '../types/message';
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
} from '../types/event';
import type { DeepResearchContent } from '../types/message';
import Suggestions from '../components/Suggestions.vue';
import ToolPanel from '../components/ToolPanel.vue'
import { ArrowDown, FileSearch, PanelLeft, Lock, Globe, Link, Check } from 'lucide-vue-next';
import ShareIcon from '@/components/icons/ShareIcon.vue';
import { showErrorToast, showSuccessToast } from '../utils/toast';
import type { FileInfo } from '../api/file';
import { useLeftPanel } from '../composables/useLeftPanel'
import { useSessionFileList } from '../composables/useSessionFileList'
import { useFilePanel } from '../composables/useFilePanel'
import { copyToClipboard } from '../utils/dom'
import { SessionStatus } from '../types/response';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import LoadingIndicator from '@/components/ui/LoadingIndicator.vue';
import TaskProgressBar from '@/components/TaskProgressBar.vue';
import { ReportModal } from '@/components/report';
import FilePanelContent from '@/components/FilePanelContent.vue';
import type { ReportData } from '@/components/report';
import { useReport, extractSectionsFromMarkdown } from '@/composables/useReport';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import ThinkingIndicator from '@/components/ui/ThinkingIndicator.vue';
import { useSessionStatus } from '@/composables/useSessionStatus';

const router = useRouter()
const { t } = useI18n()
const { toggleLeftPanel, isLeftPanelShow } = useLeftPanel()
const { showSessionFileList } = useSessionFileList()
const { hideFilePanel } = useFilePanel()
const { isReportModalOpen, currentReport, openReport, closeReport } = useReport()
const { emitStatusChange } = useSessionStatus()

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
  agentMode: 'discuss' as 'discuss' | 'agent', // Current agent mode
  isThinking: false, // True when agent is actively thinking/processing
  seenEventIds: new Set<string>(), // Track seen event IDs to prevent duplicates
  thinkingText: '', // Accumulated streaming thinking text
  isThinkingStreaming: false, // True when streaming thinking is in progress
  lastEventTime: 0, // Timestamp of last received event (for stale detection)
  isStale: false, // True when agent appears unresponsive (no events for 60s)
  filePreviewOpen: false,
  filePreviewFile: null as FileInfo | null,
  toolTimeline: [] as ToolContent[],
  panelToolId: undefined as string | undefined,
  isInitializing: false, // True when starting up the sandbox environment
  planningProgress: null as { phase: string; message: string; percent: number } | null, // Planning progress
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
  agentMode,
  isThinking,
  seenEventIds,
  thinkingText,
  isThinkingStreaming,
  lastEventTime,
  isStale,
  filePreviewOpen,
  filePreviewFile,
  toolTimeline,
  panelToolId,
  isInitializing,
  planningProgress,
} = toRefs(state);

// Non-state refs that don't need reset
const toolPanel = ref<InstanceType<typeof ToolPanel>>()
const simpleBarRef = ref<InstanceType<typeof SimpleBar>>();
const observerRef = ref<HTMLDivElement>();
const chatContainerRef = ref<HTMLDivElement>();

// Reset all refs to their initial values
const resetState = () => {
  // Cancel any existing chat connection
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
  }

  // Reset reactive state to initial values
  Object.assign(state, createInitialState());
};

// Watch message changes and automatically scroll to bottom
watch(messages, async () => {
  await nextTick();
  if (follow.value) {
    simpleBarRef.value?.scrollToBottom();
  }
}, { deep: true });

// Scroll to bottom when agent starts (loading begins) or plan updates
watch([isLoading, plan], async () => {
  await nextTick();
  if (follow.value) {
    simpleBarRef.value?.scrollToBottom();
  }
}, { deep: true });

// Scroll to bottom when streaming thinking text updates
watch(thinkingText, async () => {
  await nextTick();
  if (follow.value && isThinkingStreaming.value) {
    simpleBarRef.value?.scrollToBottom();
  }
});

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
    console.warn(`Agent connection appears stale. No events for ${Math.round(timeSinceLastEvent / 1000)}s`);
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

// Check if there's a report message (suggestions should appear inside it)
const hasReportMessage = computed(() => {
  return messages.value.some(message => message.type === 'report');
});

// Track if user has explicitly closed the panel (don't auto-reopen)
const userClosedPanel = ref(false);

// Handle tool panel state changes
const handlePanelStateChange = (isOpen: boolean, userAction: boolean = false) => {
  isToolPanelOpen.value = isOpen;
  // If user explicitly closed the panel, remember this preference
  if (!isOpen && userAction) {
    userClosedPanel.value = true;
  }
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

  // Import the mapping from tool constants
  const TOOL_FUNCTION_MAP: Record<string, string> = {
    'browser_get_content': 'Browser',
    'browser_view': 'Browser',
    'browser_navigate': 'Browser',
    'browser_click': 'Browser',
    'browser_input': 'Browser',
    'shell_exec': 'Terminal',
    'file_read': 'File Reader',
    'file_write': 'File Editor',
    'info_search_web': 'Search Engine',
  };

  const TOOL_FUNCTION_ARG_MAP: Record<string, string> = {
    'browser_get_content': 'url',
    'browser_navigate': 'url',
    'shell_exec': 'command',
    'file_read': 'file',
    'file_write': 'file',
    'info_search_web': 'query',
  };

  const argKey = TOOL_FUNCTION_ARG_MAP[tool.function] || '';
  let functionArg = argKey && tool.args ? tool.args[argKey] : '';

  // Truncate long arguments
  if (functionArg && functionArg.length > 50) {
    functionArg = functionArg.substring(0, 47) + '...';
  }

  return {
    name: tool.name,
    function: TOOL_FUNCTION_MAP[tool.function] || tool.function,
    functionArg,
    status: tool.status
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

const showTimelineControls = computed(() => toolTimelineIndex.value >= 0);

// Handle opening the panel from TaskProgressBar
const handleOpenPanel = () => {
  userClosedPanel.value = false;
  if (lastNoMessageTool.value) {
    toolPanel.value?.showToolPanel(lastNoMessageTool.value, isLiveTool(lastNoMessageTool.value));
    panelToolId.value = lastNoMessageTool.value.tool_call_id;
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

// Handle message event
const handleMessageEvent = (messageData: MessageEventData) => {
  // Assistant message means agent finished thinking
  if (messageData.role === 'assistant') {
    isThinking.value = false;
  }

  // Prevent duplicate user messages (same content appearing consecutively)
  if (messageData.role === 'user' && messages.value.length > 0) {
    const lastMessage = messages.value[messages.value.length - 1];
    if (lastMessage.type === 'user') {
      const lastContent = lastMessage.content as MessageContent;
      if (lastContent.content === messageData.content) {
        console.debug('Skipping duplicate user message:', messageData.content?.slice(0, 50));
        return;
      }
    }
  }

  messages.value.push({
    type: messageData.role,
    content: {
      ...messageData
    } as MessageContent,
  });

  if (messageData.attachments?.length > 0) {
    messages.value.push({
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
      lastStep.tools.push(toolContent);
    } else {
      messages.value.push({
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
    }
    // Panel no longer auto-opens - user must click thumbnail or button to open
  }
}

// Handle step event
const handleStepEvent = (stepData: StepEventData) => {
  const lastStep = getLastStep();
  if (stepData.status === 'running') {
    isThinking.value = true;
    messages.value.push({
      type: 'step',
      content: {
        ...stepData,
        tools: []
      } as StepContent,
    });
  } else if (stepData.status === 'completed') {
    isThinking.value = false;
    if (lastStep) {
      lastStep.status = stepData.status;
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

// Handle stream event (thinking text streaming)
const handleStreamEvent = (streamData: StreamEventData) => {
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
  console.log(`Agent mode changed to: ${modeData.mode}`, modeData.reason);
}

// Handle suggestion event
const handleSuggestionEvent = (suggestionData: SuggestionEventData) => {
  suggestions.value = suggestionData.suggestions;
}

// Handle report event
const handleReportEvent = (reportData: ReportEventData) => {
  const sections = extractSectionsFromMarkdown(reportData.content);
  messages.value.push({
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
      status: data.status,
      queries: data.queries,
      completed_count: data.completed_queries,
      total_count: data.total_queries,
      auto_run: data.auto_run
    } as DeepResearchContent;
  } else {
    // Create new message
    messages.value.push({
      type: 'deep_research',
      content: {
        research_id: data.research_id,
        status: data.status,
        queries: data.queries || [],
        completed_count: data.completed_queries,
        total_count: data.total_queries,
        auto_run: data.auto_run,
        timestamp: data.timestamp
      } as DeepResearchContent
    });
  }
};

// Handle deep research run (approve)
const handleDeepResearchRun = async (_researchId: string) => {
  if (!sessionId.value) return;
  try {
    await agentApi.approveDeepResearch(sessionId.value);
  } catch (error) {
    console.error('Error approving deep research:', error);
    showErrorToast(t('Failed to start research'));
  }
};

// Handle deep research skip
const handleDeepResearchSkip = async (_researchId: string, queryId?: string) => {
  if (!sessionId.value) return;
  try {
    await agentApi.skipDeepResearchQuery(sessionId.value, queryId);
  } catch (error) {
    console.error('Error skipping deep research query:', error);
    showErrorToast(t('Failed to skip query'));
  }
};

// Handle toggle auto-run preference
const handleToggleAutoRun = () => {
  // TODO: Implement settings persistence
  console.log('Toggle auto-run preference');
};

// Handle suggestion selection (user clicks a suggestion)
const handleSuggestionSelect = (suggestion: string) => {
  inputMessage.value = suggestion;
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
const handleReportRate = (rating: number) => {
  console.log('Report rated:', rating);
  // TODO: Send rating to backend
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

// Main event handler function
const handleEvent = (event: AgentSSEEvent) => {
  // Deduplicate events based on event_id to prevent duplicate messages
  const eventId = event.data?.event_id;
  if (eventId && seenEventIds.value.has(eventId)) {
    console.debug('Skipping duplicate event:', eventId);
    return;
  }
  if (eventId) {
    seenEventIds.value.add(eventId);
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
  } else if (event.event === 'done') {
    isLoading.value = false;
    isThinking.value = false;
    // Notify sidebar that session is no longer running
    if (sessionId.value) {
      emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
    }
  } else if (event.event === 'wait') {
    // TODO: handle wait event
  } else if (event.event === 'error') {
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
  }
  lastEventId.value = event.data.event_id;
}

const handleSubmit = () => {
  chat(inputMessage.value, attachments.value);
}

// Track last sent message to prevent duplicate submissions
let lastSentMessage = '';
let lastSentTime = 0;

const chat = async (message: string = '', files: FileInfo[] = []) => {
  if (!sessionId.value) return;

  // Prevent duplicate message submission within 2 seconds
  const now = Date.now();
  if (message && message === lastSentMessage && now - lastSentTime < 2000) {
    console.debug('Preventing duplicate message submission');
    return;
  }
  if (message) {
    lastSentMessage = message;
    lastSentTime = now;
  }

  // Cancel any existing chat connection before starting a new one
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }

  // Automatically enable follow mode when sending message
  follow.value = true;

  // Clear input field
  inputMessage.value = '';
  isLoading.value = true;

  // Set initialization state when starting a new chat
  // (when there are no messages or only 1 message which is the user's first message)
  if (message && (messages.value.length === 0 || (messages.value.length === 1 && messages.value[0].type === 'user'))) {
    isInitializing.value = true;
  }

  try {
    // Use the split event handler function and store the cancel function
    cancelCurrentChat.value = await agentApi.chatWithSession(
      sessionId.value,
      message,
      lastEventId.value,
      files.map((file: FileInfo) => ({
        file_id: file.file_id,
        filename: file.filename,
        content_type: file.content_type,
        size: file.size,
        upload_date: file.upload_date
      })),
      {
        onOpen: () => {
          console.log('Chat opened');
          isLoading.value = true;
        },
        onMessage: ({ event, data }) => {
          handleEvent({
            event: event as AgentSSEEvent['event'],
            data: data as AgentSSEEvent['data']
          });
        },
        onClose: () => {
          console.log('Chat closed');
          isLoading.value = false;
          isThinking.value = false;
          thinkingText.value = '';
          isThinkingStreaming.value = false;
          isInitializing.value = false;
          planningProgress.value = null;
          stopPlanningMessageCycle();
          // Clear the cancel function when connection is closed normally
          if (cancelCurrentChat.value) {
            cancelCurrentChat.value = null;
          }
          // Notify sidebar that session is no longer running
          if (sessionId.value) {
            emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
          }
        },
        onError: (error) => {
          console.error('Chat error:', error);
          isLoading.value = false;
          isThinking.value = false;
          thinkingText.value = '';
          isThinkingStreaming.value = false;
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
      }
    );
  } catch (error) {
    console.error('Chat error:', error);
    isLoading.value = false;
    cancelCurrentChat.value = null;
  }
}

const restoreSession = async () => {
  if (!sessionId.value) {
    showErrorToast(t('Session not found'));
    return;
  }
  const session = await agentApi.getSession(sessionId.value);
  // Initialize share mode based on session state
  shareMode.value = session.is_shared ? 'public' : 'private';
  realTime.value = false;
  for (const event of session.events) {
    handleEvent(event);
  }
  realTime.value = true;
  if (session.status === SessionStatus.RUNNING || session.status === SessionStatus.PENDING) {
    await chat();
  }
  agentApi.clearUnreadMessageCount(sessionId.value);
}



onBeforeRouteUpdate((to, _, next) => {
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
onMounted(() => {
  hideFilePanel();
  const routeParams = router.currentRoute.value.params;
  if (routeParams.sessionId) {
    // If sessionId is included in URL, use it directly
    sessionId.value = String(routeParams.sessionId) as string;
    // Get initial message from history.state
    const message = history.state?.message;
    const files: FileInfo[] = history.state?.files;
    history.replaceState({}, document.title);
    if (message) {
      chat(message, files);
    } else {
      restoreSession();
    }
  }


});

onUnmounted(() => {
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
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
  if (!toolTimelineCanStepForward.value) return;
  showToolFromTimeline(toolTimelineIndex.value + 1);
}

const handleTimelineStepBackward = () => {
  if (!toolTimelineCanStepBackward.value) return;
  showToolFromTimeline(toolTimelineIndex.value - 1);
}

const handleTimelineSeek = (progress: number) => {
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
  simpleBarRef.value?.scrollToBottom();
}

const handleScroll = (_: Event) => {
  follow.value = simpleBarRef.value?.isScrolledToBottom() ?? false;
}

const handleStop = () => {
  if (sessionId.value) {
    agentApi.stopSession(sessionId.value);
    // Notify sidebar that session is no longer running
    emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
  }
  // Reset loading states
  isLoading.value = false;
  isThinking.value = false;
  isStale.value = false;
  thinkingText.value = '';
  isThinkingStreaming.value = false;
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
  } catch (error) {
    console.error('Error changing share mode:', error);
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
  } catch (error) {
    console.error('Error sharing session:', error);
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
  } catch (error) {
    console.error('Error copying share link:', error);
    showErrorToast(t('Failed to copy link'));
  }
}
</script>

<style scoped>
/* ===== CHAT HEADER ===== */
.chat-header {
  background: var(--background-white-main);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.chat-header::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--border-main) 10%,
    var(--border-main) 90%,
    transparent 100%
  );
  opacity: 0.6;
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
