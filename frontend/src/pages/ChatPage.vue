<template>
  <SimpleBar ref="simpleBarRef" @scroll="handleScroll">
    <div ref="chatContainerRef" class="relative flex flex-col h-full flex-1 min-w-0 px-5">
      <div ref="observerRef"
        class="sm:min-w-[390px] flex flex-row items-center justify-between pt-3 pb-1 gap-1 sticky top-0 z-10 bg-[var(--background-gray-main)] flex-shrink-0">
        <div class="flex items-center flex-1">
          <div class="relative flex items-center">
            <div @click="toggleLeftPanel" v-if="!isLeftPanelShow"
              class="flex h-7 w-7 items-center justify-center cursor-pointer rounded-md hover:bg-[var(--fill-tsp-gray-main)]">
              <PanelLeft class="size-5 text-[var(--icon-secondary)]" />
            </div>
          </div>
        </div>
        <div class="max-w-full sm:max-w-[768px] sm:min-w-[390px] flex w-full flex-col gap-[4px] overflow-hidden">
          <div
            class="text-[var(--text-primary)] text-lg font-medium w-full flex flex-row items-center justify-between flex-1 min-w-0 gap-2">
            <div class="flex flex-row items-center gap-[6px] flex-1 min-w-0">
              <span class="whitespace-nowrap text-ellipsis overflow-hidden">
                {{ title }}
              </span>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <span class="relative flex-shrink-0" aria-expanded="false" aria-haspopup="dialog">
                <Popover>
                  <PopoverTrigger>
                    <button
                      class="h-8 px-3 rounded-[100px] inline-flex items-center gap-1 clickable outline outline-1 outline-offset-[-1px] outline-[var(--border-btn-main)] hover:bg-[var(--fill-tsp-white-light)] me-1.5">
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
                class="p-[5px] flex items-center justify-center hover:bg-[var(--fill-tsp-white-dark)] rounded-lg cursor-pointer">
                <FileSearch class="text-[var(--icon-secondary)]" :size="18" />
              </button>
            </div>
          </div>
          <div class="w-full flex justify-between items-center">
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
            @selectSuggestion="handleSuggestionSelect" />

          <!-- Loading/Thinking indicators - only show when no tool is actively being called -->
          <!-- Streaming thinking indicator with text -->
          <StreamingThinkingIndicator
            v-if="isLoading && (isThinkingStreaming || thinkingText) && lastTool?.status !== 'calling'"
            :text="thinkingText"
            :maxLines="8"
          />
          <!-- Static thinking indicator (no streaming text) -->
          <div v-else-if="isLoading && isThinking && lastTool?.status !== 'calling'" class="flex flex-col">
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
                <span class="text-sm font-medium text-black dark:text-white">Thinking</span>
              </div>
            </div>
          </div>
          <LoadingIndicator v-else-if="isLoading" :text="$t('Loading')" />

          <!-- Suggestions - only show standalone when last message is not a report -->
          <Suggestions
            v-if="suggestions.length > 0 && !isLoading && !hasReportMessage"
            :suggestions="suggestions"
            @select="handleSuggestionSelect"
          />
        </div>

        <div class="flex flex-col bg-[var(--background-gray-main)] sticky bottom-0">
          <button @click="handleFollow" v-if="!follow"
            class="flex items-center justify-center w-[36px] h-[36px] rounded-full bg-[var(--background-white-main)] hover:bg-[var(--background-gray-main)] clickable border border-[var(--border-main)] shadow-[0px_5px_16px_0px_var(--shadow-S),0px_0px_1.25px_0px_var(--shadow-S)] absolute -top-20 left-1/2 -translate-x-1/2">
            <ArrowDown class="text-[var(--icon-primary)]" :size="20" />
          </button>
          <!-- Task Progress Bar - shown above ChatBox when ToolPanel is closed -->
          <TaskProgressBar
            v-if="!isToolPanelOpen && plan && plan.steps.length > 0"
            :plan="plan"
            :isLoading="isLoading"
            :isThinking="isThinking"
            :showThumbnail="shouldShowThumbnail"
            :thumbnailUrl="currentThumbnailUrl"
            :currentTool="currentToolInfo"
            :toolContent="lastNoMessageTool"
            :sessionId="sessionId"
            :liveVnc="shouldEnableVnc"
            @openPanel="handleOpenPanel"
            class="mb-2"
          />
          <ChatBox v-model="inputMessage" :rows="1" @submit="handleSubmit" :isRunning="isLoading" @stop="handleStop"
            :attachments="attachments" />
        </div>
      </div>
    </div>
    <ToolPanel ref="toolPanel" :size="toolPanelSize" :sessionId="sessionId" :realTime="realTime"
      :isShare="false"
      :plan="plan"
      :isLoading="isLoading"
      :isThinking="isThinking"
      :showThumbnail="shouldShowPanelThumbnail"
      :thumbnailUrl="currentThumbnailUrl"
      :currentTool="currentToolInfo"
      :liveVnc="shouldEnableVnc"
      @jumpToRealTime="jumpToRealTime"
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
} from '../types/event';
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
import ThinkingIndicator from '@/components/ui/ThinkingIndicator.vue';
import StreamingThinkingIndicator from '@/components/ui/StreamingThinkingIndicator.vue';
import TaskProgressBar from '@/components/TaskProgressBar.vue';
import { ReportModal } from '@/components/report';
import FilePanelContent from '@/components/FilePanelContent.vue';
import type { ReportData } from '@/components/report';
import { useReport, extractSectionsFromMarkdown } from '@/composables/useReport';
import { Dialog, DialogContent } from '@/components/ui/dialog';

const router = useRouter()
const { t } = useI18n()
const { toggleLeftPanel, isLeftPanelShow } = useLeftPanel()
const { showSessionFileList } = useSessionFileList()
const { hideFilePanel, showFilePanel } = useFilePanel()
const { isReportModalOpen, currentReport, openReport, closeReport } = useReport()

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
  filePreviewOpen: false,
  filePreviewFile: null as FileInfo | null,
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
  filePreviewOpen,
  filePreviewFile,
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

const getLastStep = (): StepContent | undefined => {
  return messages.value.filter(message => message.type === 'step').pop()?.content as StepContent;
}

// Check if there's a report message (suggestions should appear inside it)
const hasReportMessage = computed(() => {
  return messages.value.some(message => message.type === 'report');
});

// Track if ToolPanel is open (for TaskProgressBar positioning)
const isToolPanelOpen = ref(false);

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
const COMPUTER_TOOLS = ['browser', 'shell', 'file', 'browser_agent'];

// Check if current tool is a computer tool and panel is closed
const shouldShowThumbnail = computed(() => {
  if (!lastNoMessageTool.value) return false;
  if (isToolPanelOpen.value) return false;
  if (!COMPUTER_TOOLS.includes(lastNoMessageTool.value.name)) return false;
  return isLoading.value || isPlanCompleted.value;
});

const shouldShowPanelThumbnail = computed(() => {
  if (!lastNoMessageTool.value) return false;
  if (!COMPUTER_TOOLS.includes(lastNoMessageTool.value.name)) return false;
  return isLoading.value || isPlanCompleted.value;
});

const isPlanCompleted = computed(() => {
  return !!plan.value?.steps?.length && plan.value.steps.every(step => step.status === 'completed');
});

const shouldEnableVnc = computed(() => {
  if (!lastNoMessageTool.value) return false;
  if (!COMPUTER_TOOLS.includes(lastNoMessageTool.value.name)) return false;
  return realTime.value && (isLoading.value || isPlanCompleted.value);
});

// Get current thumbnail URL from tool content
const currentThumbnailUrl = computed(() => {
  const tool = lastNoMessageTool.value;
  if (!tool?.content?.screenshot) return '';
  return tool.content.screenshot;
});

// Get current tool info for display
const currentToolInfo = computed(() => {
  const tool = lastNoMessageTool.value;
  if (!tool) return null;

  // Import the mapping from tool constants
  const TOOL_FUNCTION_MAP: Record<string, string> = {
    'browser_get_content': 'Fetching',
    'browser_view': 'Viewing',
    'browser_navigate': 'Browsing',
    'browser_click': 'Clicking',
    'browser_input': 'Typing',
    'shell_exec': 'Running',
    'file_read': 'Reading',
    'file_write': 'Creating file',
    'info_search_web': 'Searching',
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
    functionArg
  };
});

// Handle opening the panel from TaskProgressBar
const handleOpenPanel = () => {
  userClosedPanel.value = false;
  if (lastNoMessageTool.value) {
    toolPanel.value?.showToolPanel(lastNoMessageTool.value, isLiveTool(lastNoMessageTool.value));
  }
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
    // Only auto-open if user hasn't explicitly closed the panel
    if (realTime.value && !userClosedPanel.value) {
      toolPanel.value?.showToolPanel(toolContent, true);
    }
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
  }
}

// Handle error event
const handleErrorEvent = (errorData: ErrorEventData) => {
  isLoading.value = false;
  messages.value.push({
    type: 'assistant',
    content: {
      content: errorData.error,
      timestamp: errorData.timestamp
    } as MessageContent,
  });
}

// Handle title event
const handleTitleEvent = (titleData: TitleEventData) => {
  title.value = titleData.title;
}

// Handle plan event
const handlePlanEvent = (planData: PlanEventData) => {
  // Clear thinking text when plan arrives
  thinkingText.value = '';
  isThinkingStreaming.value = false;
  plan.value = planData;
}

// Handle stream event (thinking text streaming)
const handleStreamEvent = (streamData: StreamEventData) => {
  if (streamData.is_final) {
    isThinkingStreaming.value = false;
  } else {
    isThinkingStreaming.value = true;
    thinkingText.value += streamData.content;
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
      attachments: reportData.attachments,
      timestamp: reportData.timestamp
    } as ReportContent,
  });
}

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

  if (event.event === 'message') {
    handleMessageEvent(event.data as MessageEventData);
    // Clear suggestions when new message arrives
    suggestions.value = [];
  } else if (event.event === 'tool') {
    handleToolEvent(event.data as ToolEventData);
  } else if (event.event === 'step') {
    handleStepEvent(event.data as StepEventData);
  } else if (event.event === 'done') {
    //isLoading.value = false;
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

  // Reset user panel preference when starting new chat with a message
  if (message) {
    userClosedPanel.value = false;
  }

  // Automatically enable follow mode when sending message
  follow.value = true;

  // Clear input field
  inputMessage.value = '';
  isLoading.value = true;

  try {
    // Use the split event handler function and store the cancel function
    cancelCurrentChat.value = await agentApi.chatWithSession(
      sessionId.value,
      message,
      lastEventId.value,
      files.map((file: FileInfo) => ({file_id : file.file_id, 
                                        filename : file.filename})),
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
          // Clear the cancel function when connection is closed normally
          if (cancelCurrentChat.value) {
            cancelCurrentChat.value = null;
          }
        },
        onError: (error) => {
          console.error('Chat error:', error);
          isLoading.value = false;
          isThinking.value = false;
          thinkingText.value = '';
          isThinkingStreaming.value = false;
          // Clear the cancel function when there's an error
          if (cancelCurrentChat.value) {
            cancelCurrentChat.value = null;
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
  toolPanel.value?.hideToolPanel();
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

const handleToolClick = (tool: ToolContent) => {
  realTime.value = false;
  if (sessionId.value) {
    toolPanel.value?.showToolPanel(tool, isLiveTool(tool));
  }
}

const jumpToRealTime = () => {
  realTime.value = true;
  if (lastNoMessageTool.value) {
    toolPanel.value?.showToolPanel(lastNoMessageTool.value, isLiveTool(lastNoMessageTool.value));
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
  }
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
</style>
