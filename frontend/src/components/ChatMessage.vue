<template>
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
          <PythinkerTextIcon :width="94" :height="24" />
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
        <TiptapMessageViewer :content="messageContent.content ?? ''" :compact="true" :sources="props.sources" />
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
          <PythinkerTextIcon :width="94" :height="24" />
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
  <div v-else-if="message.type === 'tool'" class="chat-message-entry mt-2">
    <ToolUse
      :tool="toolContent"
      :is-active="true"
      :show-fast-search-inline="isStandaloneToolFastSearch(toolContent)"
      @click="handleToolClick(toolContent)"
    />
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
    <!-- Compact inline step (Manus-style: icon + title + chevron in one row) -->
    <div v-else class="step-compact">
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

        <!-- Timestamp (visible like Manus) -->
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
  <AttachmentsMessage v-else-if="message.type === 'attachments'" :content="attachmentsContent" @fileClick="handleReportFileOpen"/>
  <div v-else-if="message.type === 'report'" class="report-message-layout flex flex-col w-full mt-2">
    <!-- Main Report Card -->
    <ReportCard
      :report="reportData"
      :suggestions="suggestions"
      @open="handleReportOpen"
      @selectSuggestion="handleSelectSuggestion"
    />
    <!-- Attachments shown separately below the report card (excluding the report's own .md file) -->
    <AttachmentsInlineGrid
      v-if="reportSupplementaryAttachments.length > 0"
      :attachments="reportSupplementaryAttachments"
      @openFile="handleReportFileOpen"
      @showAllFiles="handleShowAllFiles"
    />
    <!-- Task Completed Footer - shown below everything -->
    <TaskCompletedFooter @rate="handleReportRate" />
  </div>
  <!-- Deep Research Card removed — progress tracked by TaskProgressBar -->
  <!-- Skill Delivery Card -->
  <div v-else-if="message.type === 'skill_delivery'" class="report-message-layout flex flex-col w-full mt-2">
    <SkillDeliveryCard :skill="skillDeliveryContent" />
    <TaskCompletedFooter @rate="handleReportRate" />
  </div>
</template>

<script setup lang="ts">
import PythinkerTextIcon from './icons/PythinkerTextIcon.vue';
import { Message, MessageContent, AttachmentsContent, ReportContent, SkillDeliveryContent, type SourceCitation } from '../types/message';
import { useAmbiguityParser } from '../composables/useAmbiguityParser';
import ToolUse from './ToolUse.vue';
import PhaseGroup from './PhaseGroup.vue';
import { CheckIcon, Copy, Check, XIcon } from 'lucide-vue-next';
import { computed, ref, watch, onUnmounted } from 'vue';
import { ToolContent, StepContent } from '../types/message';
import { useRelativeTime } from '../composables/useTime';

import AttachmentsMessage from './AttachmentsMessage.vue';
import { ReportCard, AttachmentsInlineGrid, TaskCompletedFooter } from './report';
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
  /** Live streaming thinking text from the agent */
  thinkingText?: string;
}>();

const emit = defineEmits<{
  (e: 'toolClick', tool: ToolContent): void;
  (e: 'reportOpen', report: ReportData): void;
  (e: 'reportFileOpen', file: FileInfo): void;
  (e: 'showAllFiles'): void;
  (e: 'reportRate', rating: number, feedback?: string): void;
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

const handleShowAllFiles = () => {
  emit('showAllFiles');
};

const handleReportRate = (rating: number, feedback?: string) => {
  emit('reportRate', rating, feedback);
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

const parsedAmbiguity = useAmbiguityParser(computed(() => messageContent.value?.content ?? ''));
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
  return isStructuredSummaryAssistantMessage(messageContent.value?.content ?? '');
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

// Filter out the report's own .md file from the attachment grid — it duplicates
// the report card content (created by _ensure_report_file on the backend).
const reportSupplementaryAttachments = computed(() => {
  const atts = reportData.value.attachments;
  if (!atts || atts.length === 0) return [];
  const reportId = reportData.value.id;
  return atts.filter((file) => {
    const fname = file.filename || file.file_path?.split('/').pop() || '';
    // Pattern: report-{uuid}.md — exact match for the auto-generated report file
    return !fname.startsWith(`report-${reportId}`) || !fname.endsWith('.md');
  });
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
  return isStepExpanded.value || !!props.showStepConnector;
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
   Report Layout
   ══════════════════════════════════════════════════ */
.report-message-layout {
  max-width: 100%;
}

/* ══════════════════════════════════════════════════
   Step Messages — Compact Manus-style
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

/* Status icons — inline circles matching Manus */
.step-compact-icon {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.step-compact-icon--done {
  background: #22c55e;
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

/* Title text — bold like Manus step headers */
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

/* Timestamp — visible on right like Manus */
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
  background: #22c55e;
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
