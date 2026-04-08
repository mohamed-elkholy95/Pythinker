<template>
  <!-- Single stable wrapper prevents __vnode null error when Vue patches
       the v-for list while inner v-if branches are switching message types -->
  <div class="chat-message-wrapper">
  <div v-if="message.type === 'user'" class="chat-message-entry user-message-row flex w-full flex-col items-end justify-end gap-1 group mt-2">
    <div class="user-message-inner flex max-w-[85%] flex-col gap-1 items-end">
      <div
        class="user-message-bubble relative flex items-center rounded-[18px] overflow-hidden bg-[var(--background-white-main)] px-4 py-3 border border-[var(--border-main)]"
      >
        <div class="flex items-center gap-2 w-full">
          <div
            class="message-markdown markdown-content flex-1 min-w-0"
            :class="{ 'message-markdown-collapsed': shouldCollapseMessageContent }"
          >
            <TiptapMessageViewer :content="messageContent.content ?? ''" :sources="props.sources" />
          </div>
          <span
            v-if="message.type === 'user' && messageContent?.agentModeUpgrade"
            class="shrink-0 rounded-md bg-green-100 dark:bg-green-900/30 px-1.5 py-0.5 text-[10px] font-medium text-green-700 dark:text-green-300 self-start mt-0.5"
          >
            Agent
          </span>
        </div>
        <div v-if="showMessageExpandControl" class="message-collapse-overlay">
          <button class="message-expand-btn" @click="toggleMessageExpand">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m6 9 6 6 6-6"></path>
            </svg>
            <span>Expand</span>
          </button>
        </div>
      </div>
      <div class="user-message-actions flex items-center justify-end gap-1 visible sm:invisible sm:group-hover:visible">
        <button
          @click="handleCopyUserMessage"
          class="p-2 rounded-lg text-[var(--icon-secondary)] hover:bg-[var(--fill-tsp-gray-main)] hover:text-[var(--icon-primary)] border border-transparent hover:border-[var(--border-main)] transition-colors"
          :title="copied ? 'Copied!' : 'Copy message'"
        >
          <Check v-if="copied" :size="16" class="text-green-500" />
          <Copy v-else :size="16" />
        </button>
        <div
          class="transition text-[11px] text-[var(--text-tertiary)]"
          :title="formatTimestampTooltip(message.content.timestamp)"
        >
          {{ relativeTime(message.content.timestamp) }}
        </div>
      </div>
    </div>
  </div>
  <template v-else-if="message.type === 'assistant'">
    <div
      v-if="props.renderAsSummaryCard"
      class="chat-message-entry assistant-summary-card-block flex flex-col gap-1 w-full group mt-2"
    >
      <div
        v-if="props.showAssistantHeader !== false"
        class="assistant-header-row assistant-header-summary flex items-center justify-between group"
      >
        <div class="assistant-brand flex items-center">
          <img src="/icon.svg" alt="Pythinker" class="assistant-brand-icon w-5 h-5" />
          <PythinkerTextIcon :width="120" :height="24" />
        </div>
        <div class="flex items-center gap-[2px]">
          <div
            v-if="messageContent?.confidence"
            class="flex items-center gap-1 px-1.5 py-0.5 rounded-[4px] text-[9px] font-bold tracking-wide mr-2 opacity-80"
            :class="{
              'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300': messageContent.confidence === 'high',
              'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400': messageContent.confidence === 'moderate',
              'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400': messageContent.confidence === 'low'
            }"
            :title="`Confidence: ${messageContent.confidence.charAt(0).toUpperCase() + messageContent.confidence.slice(1)}`"
          >
            {{ messageContent.confidence.toUpperCase() }}
          </div>
          <div
            class="assistant-time transition text-[11px] text-[var(--text-tertiary)]"
            :title="formatTimestampTooltip(message.content.timestamp)"
          >
            {{ relativeTime(message.content.timestamp) }}
          </div>
        </div>
      </div>

      <div class="assistant-summary-card-content">
        <TiptapMessageViewer :content="assistantDisplayContent ?? ''" :compact="true" :sources="props.sources" />
      </div>
    </div>
    <div
      v-else
      :class="[
        'chat-message-entry flex flex-col gap-1 w-full group',
        isAssistantSummaryCompact ? 'assistant-summary-layout' : '',
        props.showAssistantHeader === false ? 'mt-0.5' : 'mt-2'
      ]"
    >
      <div
        v-if="props.showAssistantHeader !== false"
        class="assistant-header-row flex items-center justify-between group"
        :class="{ 'assistant-header-summary': isAssistantSummaryCompact }"
      >
        <div class="assistant-brand flex items-center">
          <img src="/icon.svg" alt="Pythinker" class="assistant-brand-icon w-5 h-5" />
          <PythinkerTextIcon :width="120" :height="24" />
        </div>
        <div class="flex items-center gap-[2px]">
          <div
            v-if="messageContent?.confidence"
            class="flex items-center gap-1 px-1.5 py-0.5 rounded-[4px] text-[9px] font-bold tracking-wide mr-2 opacity-80"
            :class="{
              'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300': messageContent.confidence === 'high',
              'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400': messageContent.confidence === 'moderate',
              'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400': messageContent.confidence === 'low'
            }"
            :title="`Confidence: ${messageContent.confidence.charAt(0).toUpperCase() + messageContent.confidence.slice(1)}`"
          >
            {{ messageContent.confidence.toUpperCase() }}
          </div>
          <div
            class="assistant-time transition text-[11px] text-[var(--text-tertiary)]"
            :title="formatTimestampTooltip(message.content.timestamp)"
          >
            {{ relativeTime(message.content.timestamp) }}
          </div>
        </div>
      </div>
      

      <div
        class="assistant-message-content relative w-full max-w-full p-0 m-0 text-[15.5px] leading-[1.6] text-[var(--text-primary)] [&_pre:not(.shiki)]:!bg-[var(--fill-tsp-white-light)] [&_pre:not(.shiki)]:text-[var(--text-primary)]"
        :class="{ 'assistant-summary-shell': isAssistantSummaryCompact }"
      >
        <div class="my-[1px]">
          <div
            class="message-markdown markdown-content assistant-message-text py-[3px] break-words"
            :class="{
              'message-markdown-collapsed': shouldCollapseMessageContent,
              'assistant-summary-compact': isAssistantSummaryCompact,
            }"
          >
            <TiptapMessageViewer
              :content="parsedAmbiguity.cleanedContent ?? ''"
              :compact="isAssistantSummaryCompact"
              :sources="props.sources"
            />
            
            <!-- Quick-Reply Chips for Ambiguity Resolution -->
            <div v-if="parsedAmbiguity.chips.length > 0 && !isTaskRunning" class="mt-4 flex flex-wrap gap-2">
              <button
                v-for="chip in parsedAmbiguity.chips"
                :key="chip"
                class="inline-flex items-center justify-center rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-4 py-1.5 text-[13.5px] font-medium border border-blue-200 dark:border-blue-800 hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors"
                @click="emit('selectSuggestion', chip)"
              >
                {{ chip }}
              </button>
            </div>
          </div>
        </div>
        <div v-if="showMessageExpandControl" class="message-collapse-overlay">
          <button class="message-expand-btn" @click="toggleMessageExpand">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m6 9 6 6 6-6"></path>
            </svg>
            <span>Expand</span>
          </button>
        </div>
      </div>
      <TaskCompletedFooter v-if="props.showAssistantCompletionFooter" :showRating="false" />
    </div>
  </template>
  <div v-else-if="message.type === 'tool'" class="chat-message-entry standalone-tool-row mt-1">
    <!-- Skill invoke: render as mini-step aligned with step flow -->
    <div v-if="toolContent.function === 'skill_invoke'" class="step-compact step-compact--has-connector">
      <div class="step-compact-header step-compact-header--skill" style="pointer-events: none;">
        <div v-if="toolContent.status === 'calling'" class="step-compact-icon step-compact-icon--running">
          <span class="step-running-dot" aria-hidden="true"></span>
        </div>
        <div v-else class="step-compact-icon step-compact-icon--done">
          <CheckIcon :size="10" :stroke-width="2.5" />
        </div>
        <span class="step-compact-title step-compact-title--skill">
          {{ toolContent.name === 'skill_invoke' ? 'Pythinker is working' : (toolContent.display_command || 'Working') }}
        </span>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
          class="step-compact-chevron rotate-180">
          <path d="m6 9 6 6 6-6"></path>
        </svg>
      </div>
      <div class="step-compact-body step-compact-body--open">
        <div class="step-compact-tools">
          <ToolUse
            :tool="toolContent"
            :is-active="true"
            :show-fast-search-inline="false"
            @click="handleToolClick(toolContent)"
          />
        </div>
      </div>
    </div>
    <!-- Regular standalone tool -->
    <div v-else class="standalone-tool-pill">
      <ToolUse
        :tool="toolContent"
        :is-active="true"
        :show-fast-search-inline="isStandaloneToolFastSearch(toolContent)"
        @click="handleToolClick(toolContent)"
      />
    </div>
  </div>
  <div
    v-else-if="message.type === 'step'"
    class="chat-message-entry step-message-compact"
  >
    <!-- Finalization step: professional card with sub-stage progression -->
    <FinalizationStepCard
      v-if="stepContent.step_type === 'finalization'"
      :step="stepContent"
      :show-top-connector="showStepTopConnector"
      :show-bottom-connector="showStepBottomConnector"
    />
    <!-- Compact inline step (Pythinker-style: icon + title + chevron in one row) -->
    <div v-else class="step-compact" :class="{ 'step-compact--has-connector': showStepBottomConnector }">
      <!-- Step Header (clickable) -->
      <div class="step-compact-header" @click="handleStepToggle">
        <!-- Status icon -->
        <div v-if="stepContent.status === 'completed' || stepContent.status === 'skipped'"
          class="step-compact-icon step-compact-icon--done">
          <CheckIcon :size="10" :stroke-width="2.5" />
        </div>
        <div v-else-if="stepContent.status === 'running' || stepContent.status === 'started'"
          class="step-compact-icon step-compact-icon--running">
          <span class="step-running-dot" aria-hidden="true"></span>
        </div>
        <div v-else-if="stepContent.status === 'failed' || stepContent.status === 'blocked'"
          class="step-compact-icon step-compact-icon--failed">
          <XIcon :size="10" :stroke-width="2.5" />
        </div>
        <div v-else class="step-compact-icon step-compact-icon--pending"></div>

        <!-- Title -->
        <span class="step-compact-title" :title="stepContent.description">
          {{ stepContent.description }}
        </span>

        <!-- Chevron -->
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
          class="step-compact-chevron"
          :class="{ 'rotate-180': isStepExpanded }">
          <path d="m6 9 6 6 6-6"></path>
        </svg>

        <!-- Timestamp (visible like Pythinker) -->
        <span
          class="step-compact-time"
          :title="formatTimestampTooltip(message.content.timestamp)"
        >
          {{ relativeTime(message.content.timestamp) }}
        </span>
      </div>

      <!-- Collapsible tools -->
      <div
        class="step-compact-body"
        :class="isStepExpanded ? 'step-compact-body--open' : 'step-compact-body--closed'"
      >
        <div class="step-compact-tools">
          <ToolUse
            v-for="group in groupedTools"
            :key="group.groupKey"
            :tool="group.tool"
            :group-count="group.count"
            :is-active="group.containsActive"
            :is-task-running="group.containsActive && stepContent.status === 'running'"
            :show-fast-search-inline="false"
            @click="handleToolClick(group.tool)"
          />
          <div v-if="showStepThinking" class="step-thinking-nested">
            <ThinkingIndicator :showText="true" />
          </div>
        </div>
      </div>
    </div>
  </div>
  <PhaseGroup
    v-else-if="message.type === 'phase'"
    :phase="message.content as import('../types/message').PhaseContent"
    :activeThinkingStepId="activeThinkingStepId"
    :isLoading="isLoading"
    @toolClick="handleToolClick"
  />
  <!-- Assistant attachments: inline chart/image previews -->
  <AttachmentsInlineGrid
    v-else-if="message.type === 'attachments' && attachmentsContent.role === 'assistant'"
    :attachments="attachmentsContent.attachments"
    @openFile="handleReportFileOpen"
    @showAllFiles="$emit('showAllFiles')"
  />
  <!-- User attachments: keep existing right-aligned file cards -->
  <AttachmentsMessage v-else-if="message.type === 'attachments'" :content="attachmentsContent" @fileClick="handleReportFileOpen"/>
  <div v-else-if="message.type === 'report'" class="report-message-layout flex flex-col w-full mt-5">
    <!-- Main Report Card -->
    <ReportCard
      :report="reportData"
      :suggestions="suggestions"
      @open="handleReportOpen"
      @selectSuggestion="handleSelectSuggestion"
    />
    <!-- File Attachments Grid (Manus-style) -->
    <div
      v-if="reportData.attachments && reportData.attachments.length > 0"
      class="w-full grid md:grid-cols-[repeat(auto-fill,minmax(240px,1fr))] grid-cols-1 gap-2 max-w-[568px] mt-3"
    >
      <div
        v-for="file in reportData.attachments.slice(0, 3)"
        :key="file.file_id"
        class="flex items-center gap-1.5 p-2 pr-2.5 w-full min-w-[240px] group/attach relative overflow-hidden cursor-pointer rounded-[12px] border-[0.5px] border-[var(--border-dark)] bg-[var(--background-menu-white)] hover:bg-[var(--background-tsp-menu-white)] max-w-full"
        @click="handleReportFileOpen(file)"
      >
        <div class="flex justify-center items-center w-8 h-8 rounded-md">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M3.55566 26.8889C3.55566 28.6071 4.94856 30 6.66678 30H25.3334C27.0517 30 28.4446 28.6071 28.4446 26.8889V9.77778L20.6668 2H6.66678C4.94856 2 3.55566 3.39289 3.55566 5.11111V26.8889Z" fill="#4D81E8" />
            <path d="M20.6685 6.66647C20.6685 8.38469 22.0613 9.77759 23.7796 9.77759H28.4462L20.6685 1.99981V6.66647Z" fill="#9CC3F4" />
            <path opacity="0.9" d="M10.1685 18.2363H21.8351" stroke="white" stroke-width="1.75" stroke-linecap="square" />
            <path opacity="0.9" d="M10.1685 14.3472H16.9737" stroke="white" stroke-width="1.75" stroke-linecap="square" />
            <path opacity="0.9" d="M10.1685 21.8333H21.8351" stroke="white" stroke-width="1.75" stroke-linecap="square" />
          </svg>
        </div>
        <div class="flex flex-col gap-0.5 flex-1 min-w-0">
          <div class="text-sm text-[var(--text-primary)] truncate flex-1 min-w-0" :title="file.filename">{{ file.filename }}</div>
          <div class="text-xs text-[var(--text-tertiary)] truncate">{{ getFileTypeLabel(file) }} · {{ formatBytes(file.size) }}</div>
        </div>
      </div>
      <div
        class="h-[55px] ps-4 pe-1.5 w-full cursor-pointer flex items-center justify-center gap-1.5 rounded-[12px] border-[0.5px] border-[var(--border-dark)] bg-[var(--background-menu-white)] hover:bg-[var(--background-tsp-menu-white)]"
        @click="$emit('showAllFiles')"
      >
        <FileSearch :size="16" class="text-[var(--icon-secondary)]" />
        <span class="text-sm text-[var(--icon-secondary)]">View all files in this task</span>
      </div>
    </div>
    <!-- Task Completed Footer - shown below everything -->
    <TaskCompletedFooter @rate="handleReportRate" />
  </div>
  <!-- Deep Research Card removed — progress tracked by TaskProgressBar -->
  <!-- Skill Delivery Card -->
  <div v-else-if="message.type === 'skill_delivery'" class="report-message-layout flex flex-col w-full mt-2">
    <SkillDeliveryCard :skill="skillDeliveryContent" />
    <TaskCompletedFooter @rate="handleReportRate" />
  </div>
  </div><!-- /chat-message-wrapper -->
</template>

<script setup lang="ts">
import PythinkerTextIcon from './icons/PythinkerTextIcon.vue';
import { Message, MessageContent, AttachmentsContent, ReportContent, SkillDeliveryContent, type SourceCitation } from '../types/message';
import { useAmbiguityParser } from '../composables/useAmbiguityParser';
import ToolUse from './ToolUse.vue';
import PhaseGroup from './PhaseGroup.vue';
import { CheckIcon, Copy, Check, XIcon, FileSearch } from 'lucide-vue-next';
import { computed, ref, watch, onUnmounted } from 'vue';
import { ToolContent, StepContent } from '../types/message';
import { useRelativeTime } from '../composables/useTime';

import AttachmentsMessage from './AttachmentsMessage.vue';
import { ReportCard, TaskCompletedFooter, AttachmentsInlineGrid } from './report';
import TiptapMessageViewer from './TiptapMessageViewer.vue';
import type { ReasoningStage } from '@/types/reasoning';
import type { ReportData } from './report';
import type { FileInfo } from '../api/file';
import SkillDeliveryCard from './SkillDeliveryCard.vue';
import ThinkingIndicator from './ui/ThinkingIndicator.vue';
import FinalizationStepCard from './FinalizationStepCard.vue';
import { copyToClipboard } from '../utils/dom';
import { isStructuredSummaryAssistantMessage } from '@/utils/assistantMessageLayout';
import { groupConsecutiveTools } from '../composables/useToolGrouping';
import { normalizeTimestampSeconds } from '../utils/time';
import { stripLeakedToolCallMarkup } from '@/utils/messageSanitizer';


const props = defineProps<{
  message: Message;
  sessionId?: string;
  suggestions?: string[];
  activeThinkingStepId?: string;
  showStepLeadingConnector?: boolean;
  showStepConnector?: boolean;
  showAssistantHeader?: boolean;
  renderAsSummaryCard?: boolean;
  showAssistantCompletionFooter?: boolean;
  /** Citation sources from the nearest report — enables popup cards on [N] badges */
  sources?: SourceCitation[];
  /** True when the session is a fast search task (not deep research). Controls inline search results. */
  isFastSearchSession?: boolean;
  activeReasoningState?: ReasoningStage;
  isLoading?: boolean;
  /** Live streaming thinking text from the agent */
  thinkingText?: string;
  /** When false, hides the "Pythinker is working" header for consecutive skill_invoke tools */
  showSkillHeader?: boolean;
}>();

const emit = defineEmits<{
  (e: 'toolClick', tool: ToolContent): void;
  (e: 'reportOpen', report: ReportData): void;
  (e: 'reportFileOpen', file: FileInfo): void;
  (e: 'showAllFiles'): void;
  (e: 'reportRate', reportId: string, rating: number, feedback?: string): void;
  (e: 'selectSuggestion', suggestion: string): void;
}>();

const handleToolClick = (tool: ToolContent) => {
  emit('toolClick', tool);
};

const handleReportOpen = (report: ReportData) => {
  emit('reportOpen', report);
};

const handleReportFileOpen = (file: FileInfo) => {
  emit('reportFileOpen', file);
};

const getFileTypeLabel = (file: FileInfo): string => {
  const ext = file.filename?.split('.').pop()?.toLowerCase() || '';
  const map: Record<string, string> = {
    md: 'Markdown', txt: 'Text', pdf: 'PDF', json: 'JSON', csv: 'CSV',
    zip: 'Archive', py: 'Python', js: 'JavaScript', ts: 'TypeScript',
    html: 'HTML', css: 'CSS', png: 'Image', jpg: 'Image', svg: 'SVG',
  };
  return map[ext] || 'File';
};

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

const handleReportRate = (rating: number, feedback?: string) => {
  let id = '';
  if (props.message.type === 'report') {
    id = (props.message.content as ReportContent).id;
  } else if (props.message.type === 'skill_delivery') {
    id = (props.message.content as SkillDeliveryContent).package_id;
  }
  emit('reportRate', id, rating, feedback);
};

const handleSelectSuggestion = (suggestion: string) => {
  emit('selectSuggestion', suggestion);
};

/** Standalone tool messages: show fast-search inline only for fast search sessions, not deep research. */
const FAST_SEARCH_FUNCTIONS = new Set(['info_search_web', 'web_search']);
function isStandaloneToolFastSearch(tool: ToolContent): boolean {
  if (!props.isFastSearchSession) return false;
  const fn = (tool.function || '').toLowerCase();
  return FAST_SEARCH_FUNCTIONS.has(fn);
}

// For backward compatibility, provide the original computed properties
const stepContent = computed(() => props.message.content as StepContent);
const messageContent = computed(() => props.message.content as MessageContent);
const assistantDisplayContent = computed(() => {
  if (props.message.type !== 'assistant') {
    return messageContent.value?.content ?? ''
  }
  return stripLeakedToolCallMarkup(messageContent.value?.content ?? '')
});

const parsedAmbiguity = useAmbiguityParser(assistantDisplayContent);
const isTaskRunning = computed(() => props.activeReasoningState && props.activeReasoningState !== 'idle' && props.activeReasoningState !== 'completed');
const toolContent = computed(() => props.message.content as ToolContent);
const attachmentsContent = computed(() => props.message.content as AttachmentsContent);
const reportContent = computed(() => props.message.content as ReportContent);
const skillDeliveryContent = computed(() => props.message.content as SkillDeliveryContent);

// Collapse consecutive identical tool operations into groups with count badges
const groupedTools = computed(() => {
  if (props.message.type !== 'step') return [];
  return groupConsecutiveTools(stepContent.value.tools ?? []);
});

// Show thinking indicator inside this step when it's the active thinking step
const showStepThinking = computed(() => {
  if (props.message.type !== 'step') return false;
  return stepContent.value.id === props.activeThinkingStepId;
});

const isAssistantSummaryCompact = computed(() => {
  if (props.message.type !== 'assistant') return false;
  return isStructuredSummaryAssistantMessage(assistantDisplayContent.value);
});

// Convert ReportContent to ReportData for the component
const reportData = computed<ReportData>(() => {
  const content = reportContent.value;
  return {
    id: content.id,
    title: content.title,
    content: content.content,
    lastModified: content.lastModified,
    fileCount: content.fileCount,
    sections: content.sections,
    attachments: content.attachments,
    sources: content.sources,
  };
});

// Control step expand/collapse state
const isStepExpanded = ref(false);
const stepUserToggled = ref(false);

const showStepTopConnector = computed(() => {
  if (props.message.type !== 'step') return false;
  return !!props.showStepLeadingConnector;
});

const showStepBottomConnector = computed(() => {
  if (props.message.type !== 'step') return false;
  return !!props.showStepConnector;
});

// Control long-message expand/collapse state
const LONG_MESSAGE_CHAR_THRESHOLD = 700;
const LONG_MESSAGE_LINE_THRESHOLD = 10;
const isMessageExpanded = ref(true);
const messageText = computed(() => {
  if (props.message.type !== 'user') {
    return '';
  }
  return messageContent.value?.content ?? '';
});
const isLongMessage = computed(() => {
  const text = messageText.value.trim();
  if (!text) return false;
  const lineCount = text.split(/\r?\n/).length;
  return text.length > LONG_MESSAGE_CHAR_THRESHOLD || lineCount > LONG_MESSAGE_LINE_THRESHOLD;
});
const shouldCollapseMessageContent = computed(() => props.message.type === 'user' && isLongMessage.value && !isMessageExpanded.value);
const showMessageExpandControl = computed(() => props.message.type === 'user' && shouldCollapseMessageContent.value);

const { relativeTime } = useRelativeTime();

const formatTimestampTooltip = (timestamp: number): string => {
  const normalizedTimestamp = normalizeTimestampSeconds(timestamp);
  if (normalizedTimestamp === null) {
    return '';
  }

  const date = new Date(normalizedTimestamp * 1000);
  if (Number.isNaN(date.getTime())) {
    return '';
  }

  return date.toLocaleString('en-US', {
    month: '2-digit',
    day: '2-digit',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
};

// Clipboard copy state for user message actions
const copied = ref(false);
let copyResetTimer: ReturnType<typeof setTimeout> | null = null;

// Copy user message to clipboard
const handleCopyUserMessage = async () => {
  const content = messageContent.value?.content;
  if (content) {
    const success = await copyToClipboard(content);
    if (!success) return;

    copied.value = true;
    if (copyResetTimer) {
      clearTimeout(copyResetTimer);
    }
    copyResetTimer = setTimeout(() => {
      copied.value = false;
    }, 1500);
  }
};

onUnmounted(() => {
  if (copyResetTimer) {
    clearTimeout(copyResetTimer);
    copyResetTimer = null;
  }
});

const handleStepToggle = () => {
  stepUserToggled.value = true;
  isStepExpanded.value = !isStepExpanded.value;
};

const toggleMessageExpand = () => {
  isMessageExpanded.value = !isMessageExpanded.value;
};

const initializeMessageExpansion = () => {
  isMessageExpanded.value = !isLongMessage.value;
};

watch(
  () => props.message.id,
  () => {
    initializeMessageExpansion();
  },
  { immediate: true }
);

watch(
  () => [stepContent.value?.id, stepContent.value?.status, props.activeThinkingStepId] as const,
  ([stepId, status, thinkingId]: readonly [string | undefined, string | undefined, string | undefined]) => {
    if (stepUserToggled.value) return;
    const isActiveStep = Boolean(stepId) && thinkingId === stepId;
    isStepExpanded.value = isActiveStep || status === 'running';
  },
  { immediate: true }
);

</script>

<style>
/* ══════════════════════════════════════════════════
   Chat message entry animation (compact, snappy)
   ══════════════════════════════════════════════════ */
.chat-message-entry {
  animation: chat-message-enter 0.25s ease-out both;
}

@keyframes chat-message-enter {
  from {
    opacity: 0;
    transform: translateY(3px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ══════════════════════════════════════════════════
   User Message
   ══════════════════════════════════════════════════ */
.user-message-bubble {
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: box-shadow 0.15s ease;
}

/* ══════════════════════════════════════════════════
   Assistant Header — Compact
   ══════════════════════════════════════════════════ */
.assistant-header-row {
  min-height: 28px;
}

.assistant-brand {
  gap: 6px;
}

.assistant-brand-icon {
  width: 18px;
  height: 18px;
}

.assistant-time {
  opacity: 0;
  transition: opacity 0.15s ease;
}

.assistant-header-row:hover .assistant-time {
  opacity: 0.82;
}

.assistant-message-text {
  font-size: 15px;
  line-height: 1.55;
  color: var(--text-primary);
  font-weight: 400;
}

.assistant-summary-layout {
  gap: 0;
}

.assistant-summary-card-block {
  max-width: 704px;
}

.assistant-summary-card-content {
  width: 100%;
  max-width: 704px;
  margin: 4px 0 14px;
  padding: 0;
}

.assistant-header-summary,
.assistant-summary-shell {
  max-width: 704px;
}

.assistant-header-summary {
  min-height: 28px;
  margin-bottom: 0;
}

.assistant-header-summary .assistant-time {
  opacity: 0;
}

.assistant-summary-compact {
  font-size: 14.9px;
  line-height: 1.22;
  letter-spacing: -0.002em;
  text-wrap: pretty;
  white-space: normal !important;
}

.assistant-summary-compact :deep(p) {
  margin: 0;
}

.assistant-summary-compact :deep(p + p) {
  margin-top: 2px;
}

.assistant-summary-compact :deep(p:last-child) {
  margin-bottom: 0;
}

.assistant-summary-compact :deep(strong) {
  font-weight: 700;
  color: var(--text-primary);
}

.assistant-summary-compact :deep(ul),
.assistant-summary-compact :deep(ol) {
  margin: 1px 0;
  padding-left: 1.2em;
}

.assistant-summary-compact :deep(li) {
  margin: 0;
  line-height: 1.2;
}

/* Markdown lists inside assistant messages */
.assistant-message-text :deep(ul),
.assistant-message-text :deep(ol) {
  margin: 8px 0;
  padding-left: 1.5em;
}
.assistant-message-text :deep(ul) {
  list-style-type: disc;
}
.assistant-message-text :deep(ol) {
  list-style-type: decimal;
}
.assistant-message-text :deep(li) {
  margin: 4px 0;
  line-height: 1.55;
}
.assistant-message-text :deep(li strong) {
  font-weight: 600;
  color: var(--text-primary);
}

/* ══════════════════════════════════════════════════
   Standalone Tool — skill_invoke renders as mini-step,
   regular tools get indented into step flow
   ══════════════════════════════════════════════════ */
.standalone-tool-row {
  /* No padding — skill_invoke uses step-compact layout */
}

.standalone-tool-pill {
  padding-left: 38px;
}

.step-compact-header--skill {
  cursor: default;
}

.step-compact-title--skill {
  font-weight: 500;
  color: var(--text-secondary);
}

/* ══════════════════════════════════════════════════
   Report Layout
   ══════════════════════════════════════════════════ */
.report-message-layout {
  max-width: 100%;
}

/* ══════════════════════════════════════════════════
   Step Messages — Compact Pythinker-style
   ══════════════════════════════════════════════════ */
.step-message-compact {
  position: relative;
  margin-top: 4px;
}

.step-message-compact:first-child {
  margin-top: 0;
}

.step-compact {
  display: flex;
  flex-direction: column;
  position: relative;
}

/* Dotted timeline connector between consecutive steps.
   Extends from below current icon to the top of the next step's icon.
   Icon center = padding(6px) + half-icon(10px) = 16px from top.
   So line starts at 26px (icon bottom) and extends past the container
   bottom by margin(4px) + next-icon-top(6px) = ~10px overflow needed. */
.step-compact--has-connector::after {
  content: '';
  position: absolute;
  left: 20px;
  top: 26px;
  bottom: -10px;
  width: 0;
  border-left: 1.5px dashed var(--border-dark);
  pointer-events: none;
  z-index: 0;
}

/* ── Compact header: icon + title + chevron ── */
.step-compact-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 10px;
  cursor: pointer;
  user-select: none;
  transition: background 0.12s ease;
}

.step-compact-header:hover {
  background: var(--fill-tsp-white-main);
}

/* Status icons — inline circles */
.step-compact-icon {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s ease;
  position: relative;
  z-index: 1;
}

.step-compact-icon--done {
  background: #b0b0b0;
  color: #fff;
}

.step-compact-icon--running {
  background: var(--fill-tsp-white-dark);
  position: relative;
}

.step-compact-icon--failed {
  background: #fee2e2;
  color: #ef4444;
}

.step-compact-icon--pending {
  background: var(--fill-tsp-gray-main);
  border: 1px dashed var(--border-dark);
}

.step-running-dot {
  position: relative;
  width: 4px;
  height: 4px;
  border-radius: 9999px;
  background: #8c8c8c;
  animation: step-dot-pulse 1.2s ease-in-out infinite;
}

.step-running-dot::after {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: 9999px;
  border: 1.5px solid rgba(140, 140, 140, 0.4);
  animation: step-dot-ripple 1.2s ease-out infinite;
}

/* Title text — bold like Pythinker step headers */
.step-compact-title {
  flex: 1;
  min-width: 0;
  font-size: 14.5px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Chevron */
.step-compact-chevron {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--text-tertiary);
  transition: transform 0.2s ease;
}

/* Timestamp — visible on right like Pythinker */
.step-compact-time {
  font-size: 12px;
  color: var(--text-tertiary);
  flex-shrink: 0;
  white-space: nowrap;
  margin-left: 4px;
}

/* ── Collapsible body ── */
.step-compact-body {
  overflow: hidden;
  transition: max-height 0.15s ease-in-out, opacity 0.15s ease-in-out;
}

.step-compact-body--open {
  max-height: 100000px;
  opacity: 1;
}

.step-compact-body--closed {
  max-height: 0;
  opacity: 0;
}

.step-compact-tools {
  padding: 6px 0 6px 38px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.step-thinking-nested {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

/* ══════════════════════════════════════════════════
   Dark Mode Overrides
   ══════════════════════════════════════════════════ */
:global(.dark) .user-message-bubble {
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

:global(.dark) .assistant-message-text {
  color: #d5dbe4;
}

:global(.dark) .step-compact-title {
  color: #d5dae2;
}

:global(.dark) .step-compact-icon--done {
  background: #808080;
  color: #fff;
}

:global(.dark) .step-compact-icon--running {
  background: rgba(255, 255, 255, 0.08);
}

:global(.dark) .step-compact-icon--failed {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
}

:global(.dark) .step-compact-icon--pending {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.15);
}

:global(.dark) .step-compact-header:hover {
  background: rgba(255, 255, 255, 0.04);
}

:global(.dark) .step-compact--has-connector::after {
  border-color: rgba(255, 255, 255, 0.12);
}

:global(.dark) .step-running-dot {
  background: rgba(255, 255, 255, 0.82);
}

:global(.dark) .step-running-dot::after {
  border-color: rgba(255, 255, 255, 0.5);
}

/* ══════════════════════════════════════════════════
   Step Animations
   ══════════════════════════════════════════════════ */
.step-compact-icon--running {
  animation: step-pulse 1.5s ease-in-out infinite;
}

@keyframes step-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(140, 140, 140, 0);
  }
  50% {
    box-shadow: 0 0 0 3px rgba(140, 140, 140, 0.15);
  }
}

@keyframes step-dot-pulse {
  0%,
  100% {
    transform: scale(0.78);
    opacity: 0.72;
  }
  50% {
    transform: scale(1.03);
    opacity: 1;
  }
}

@keyframes step-dot-ripple {
  0% {
    transform: scale(0.45);
    opacity: 0.75;
  }
  100% {
    transform: scale(1.7);
    opacity: 0;
  }
}

/* Shiki code block styling */
.shiki-wrapper {
  margin: 1em 0;
  border-radius: 8px;
  overflow: hidden;
  background: var(--bolt-elements-messages-code-background, #f6f8fa);
  border: 1px solid var(--border-dark, #e1e4e8);
}

:global(.dark) .shiki-wrapper {
  background: var(--code-block-bg);
  border-color: var(--code-block-border);
}

.shiki-wrapper :deep(pre) {
  margin: 0;
  padding: 12px 16px;
  overflow-x: auto;
  background: transparent !important;
}

.shiki-wrapper :deep(code) {
  font-family: 'SF Mono', Menlo, Monaco, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
}

/* Pending state while code is being highlighted */
.shiki-pending {
  margin: 1em 0;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  background: var(--bolt-elements-messages-code-background, #f6f8fa);
  border: 1px solid var(--border-dark, #e1e4e8);
  font-family: 'SF Mono', Menlo, Monaco, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
}

:global(.dark) .shiki-pending {
  background: var(--code-block-bg);
  border-color: var(--code-block-border);
}

.message-markdown {
  position: relative;
  width: 100%;
}

.message-markdown-collapsed {
  max-height: 300px;
  overflow: hidden;
}

.message-collapse-overlay {
  position: absolute;
  inset-inline: 0;
  bottom: 0;
  display: flex;
  justify-content: center;
  align-items: flex-end;
  padding: 28px 12px 10px;
  background: linear-gradient(to top, var(--background-white-main) 35%, transparent);
}

.message-expand-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border-main);
  border-radius: 9999px;
  padding: 6px 12px;
  background: var(--background-white-main);
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
}

.message-expand-btn:hover {
  background: var(--fill-tsp-gray-main);
}

:global(.dark) .message-collapse-overlay {
  background: linear-gradient(to top, rgba(24, 24, 27, 0.95) 35%, transparent);
}

:global(.dark) .message-expand-btn {
  background: rgba(39, 39, 42, 0.95);
}
</style>
