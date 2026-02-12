<template>
  <div v-if="message.type === 'user'" class="user-message-row flex w-full flex-col items-end justify-end gap-1 group mt-3">
    <div class="user-message-inner flex max-w-[85%] flex-col gap-1 items-end">
      <div
        class="user-message-bubble relative flex items-center rounded-[20px] overflow-hidden bg-[var(--background-white-main)] px-5 py-3.5 border border-[var(--border-main)]"
      >
        <div
          class="message-markdown markdown-content w-full"
          :class="{ 'message-markdown-collapsed': shouldCollapseMessageContent }"
          v-html="renderMarkdown(messageContent.content)"
        />
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
      <div class="user-message-actions flex items-center justify-end gap-1 invisible group-hover:visible">
        <button
          @click="handleCopyUserMessage"
          class="p-1 rounded-md text-[var(--icon-tertiary)] hover:bg-[var(--fill-tsp-gray-main)] hover:text-[var(--icon-secondary)]"
          :title="copied ? 'Copied!' : 'Copy message'"
        >
          <Check v-if="copied" :size="13" class="text-green-500" />
          <Copy v-else :size="13" />
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
  <div
    v-else-if="message.type === 'assistant'"
    :class="[
      'flex flex-col gap-1 w-full group',
      props.showAssistantHeader === false ? 'mt-1' : 'mt-3'
    ]"
  >
    <div v-if="props.showAssistantHeader !== false" class="assistant-header-row flex items-center justify-between group">
      <div class="assistant-brand flex items-center">
        <Bot :size="20" class="assistant-brand-icon text-[var(--text-primary)]" :stroke-width="1.8" />
        <PythinkerTextIcon :width="94" :height="24" />
      </div>
      <div class="flex items-center gap-[2px]">
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
    >
      <div class="my-[1px]">
        <div
          class="message-markdown markdown-content assistant-message-text py-[3px] whitespace-pre-wrap break-words"
          :class="{ 'message-markdown-collapsed': shouldCollapseMessageContent }"
          v-html="renderMarkdown(messageContent.content)"
        />
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
  </div>
  <ToolUse v-else-if="message.type === 'tool'" :tool="toolContent" :is-active="true" @click="handleToolClick(toolContent)" />
  <div
    v-else-if="message.type === 'step'"
    class="step-message flex flex-col empty:pb-0"
  >
    <!-- Unified step layout with left rail for timeline -->
    <div class="step-inner flex">
      <!-- Left rail: Status indicator + Timeline line -->
      <div class="step-left-rail w-[24px] relative flex-shrink-0">
        <!-- Status indicator at top -->
        <div class="step-status-node w-4 flex items-center justify-center relative z-[1]" style="height: 26px;">
          <div v-if="stepContent.status === 'completed'"
            class="step-status-indicator step-icon-badge step-icon-completed w-4 h-4 flex items-center justify-center rounded-[15px]">
            <CheckIcon class="step-completed-check" :size="10" :stroke-width="2" />
          </div>
          <div v-else-if="stepContent.status === 'running'"
            class="step-status-indicator step-icon-badge step-icon-running w-4 h-4 flex items-center justify-center rounded-[15px] step-running">
            <span class="step-running-dot" aria-hidden="true"></span>
          </div>
          <div v-else
            class="step-status-indicator step-icon-badge step-icon-pending w-4 h-4 flex items-center justify-center rounded-[15px]">
          </div>
        </div>
        <!-- Timeline segments: top (to node) + bottom (from node) -->
        <div
          v-if="showStepTopConnector"
          class="step-connector-segment step-connector-top"
        ></div>
        <div
          v-if="showStepBottomConnector"
          class="step-connector-segment step-connector-bottom"
          :class="{ 'step-connector-extended': props.showStepConnector }"
        ></div>
      </div>
      
      <!-- Right content: Header + Tools -->
      <div class="step-right-content flex-1 min-w-0">
        <!-- Step Header (clickable) -->
        <div
          class="step-header text-sm w-full clickable flex justify-between items-center truncate text-[var(--text-primary)]"
          style="min-height: 26px;"
          @click="handleStepToggle"
        >
          <div class="step-title-wrap flex-1 min-w-0 flex items-center gap-2 truncate">
            <div
              class="step-title truncate font-medium"
              :title="stepContent.description"
              :aria-description="stepContent.description"
            >
              {{ stepContent.description }}
            </div>
            <span class="flex-shrink-0 flex">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                class="step-chevron transition-transform duration-300 w-4 h-4"
                :class="{ 'rotate-180': isStepExpanded }">
                <path d="m6 9 6 6 6-6"></path>
              </svg>
            </span>
          </div>
          <div
            class="step-timestamp transition text-[12px] text-[var(--text-tertiary)] invisible group-hover:visible flex-shrink-0"
            :title="formatTimestampTooltip(message.content.timestamp)"
          >
            {{ relativeTime(message.content.timestamp) }}
          </div>
        </div>
        
        <!-- Tools list -->
        <div
          class="step-tools-list flex flex-col gap-2 overflow-hidden transition-[max-height,opacity] duration-150 ease-in-out"
          :class="isStepExpanded ? 'max-h-[100000px] opacity-100' : 'max-h-0 opacity-0'"
        >
          <div class="step-tools-inner pt-2 flex flex-col gap-2">
            <ToolUse
              v-for="(tool, index) in stepContent.tools"
              :key="tool.tool_call_id"
              :tool="tool"
              :is-active="index === stepContent.tools.length - 1"
              :is-task-running="index === stepContent.tools.length - 1 && stepContent.status === 'running'"
              @click="handleToolClick(tool)"
            />
            <div v-if="showStepThinking" class="step-thinking-nested">
              <ThinkingIndicator :showText="true" />
            </div>
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
  <div v-else-if="message.type === 'report'" class="report-message-layout flex flex-col w-full mt-3">
    <!-- Main Report Card -->
    <ReportCard
      :report="reportData"
      :suggestions="suggestions"
      @open="handleReportOpen"
      @selectSuggestion="handleSelectSuggestion"
    />
    <!-- Attachments shown separately below the report card -->
    <AttachmentsInlineGrid
      v-if="reportData.attachments && reportData.attachments.length > 0"
      :attachments="reportData.attachments"
      @openFile="handleReportFileOpen"
      @showAllFiles="handleShowAllFiles"
    />
    <!-- Task Completed Footer - shown below everything -->
    <TaskCompletedFooter @rate="handleReportRate" />
  </div>
  <!-- Deep Research Card -->
  <DeepResearchCard
    v-else-if="message.type === 'deep_research'"
    :content="deepResearchContent"
    @run="handleDeepResearchRun"
    @skip="handleDeepResearchSkip"
    @toggle-auto-run="handleToggleAutoRun"
  />
  <!-- Skill Delivery Card -->
  <div v-else-if="message.type === 'skill_delivery'" class="report-message-layout flex flex-col w-full mt-3">
    <SkillDeliveryCard :skill="skillDeliveryContent" />
    <TaskCompletedFooter @rate="handleReportRate" />
  </div>
</template>

<script setup lang="ts">
import PythinkerTextIcon from './icons/PythinkerTextIcon.vue';
import { Message, MessageContent, AttachmentsContent, ReportContent, DeepResearchContent, SkillDeliveryContent } from '../types/message';
import ToolUse from './ToolUse.vue';
import PhaseGroup from './PhaseGroup.vue';
import { marked, Renderer } from 'marked';
import DOMPurify from 'dompurify';
import { CheckIcon, Copy, Check } from 'lucide-vue-next';
import { computed, ref, watch } from 'vue';
import { ToolContent, StepContent } from '../types/message';
import { useRelativeTime } from '../composables/useTime';
import { Bot } from 'lucide-vue-next';
import { useClipboard } from '@vueuse/core';
import AttachmentsMessage from './AttachmentsMessage.vue';
import { ReportCard, AttachmentsInlineGrid, TaskCompletedFooter } from './report';
import type { ReportData } from './report';
import type { FileInfo } from '../api/file';
import DeepResearchCard from './DeepResearchCard.vue';
import SkillDeliveryCard from './SkillDeliveryCard.vue';
import ThinkingIndicator from './ui/ThinkingIndicator.vue';
import { useShiki } from '@/composables/useShiki';


const props = defineProps<{
  message: Message;
  sessionId?: string;
  suggestions?: string[];
  activeThinkingStepId?: string;
  showStepLeadingConnector?: boolean;
  showStepConnector?: boolean;
  showAssistantHeader?: boolean;
}>();

const emit = defineEmits<{
  (e: 'toolClick', tool: ToolContent): void;
  (e: 'reportOpen', report: ReportData): void;
  (e: 'reportFileOpen', file: FileInfo): void;
  (e: 'showAllFiles'): void;
  (e: 'reportRate', rating: number, feedback?: string): void;
  (e: 'selectSuggestion', suggestion: string): void;
  (e: 'deepResearchRun', researchId: string): void;
  (e: 'deepResearchSkip', researchId: string, queryId?: string): void;
  (e: 'toggleAutoRun'): void;
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

const handleDeepResearchRun = (researchId: string) => {
  emit('deepResearchRun', researchId);
};

const handleDeepResearchSkip = (researchId: string, queryId?: string) => {
  emit('deepResearchSkip', researchId, queryId);
};

const handleToggleAutoRun = () => {
  emit('toggleAutoRun');
};

// For backward compatibility, provide the original computed properties
const stepContent = computed(() => props.message.content as StepContent);
const messageContent = computed(() => props.message.content as MessageContent);
const toolContent = computed(() => props.message.content as ToolContent);
const attachmentsContent = computed(() => props.message.content as AttachmentsContent);
const reportContent = computed(() => props.message.content as ReportContent);
const deepResearchContent = computed(() => props.message.content as DeepResearchContent);
const skillDeliveryContent = computed(() => props.message.content as SkillDeliveryContent);

// Show thinking indicator inside this step when it's the active thinking step
const showStepThinking = computed(() => {
  if (props.message.type !== 'step') return false;
  return stepContent.value.id === props.activeThinkingStepId;
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
    attachments: content.attachments
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
  return isStepExpanded.value || !!props.showStepConnector;
});

// Control long-message expand/collapse state
const LONG_MESSAGE_CHAR_THRESHOLD = 700;
const LONG_MESSAGE_LINE_THRESHOLD = 10;
const isMessageExpanded = ref(true);
const messageText = computed(() => {
  if (props.message.type !== 'user' && props.message.type !== 'assistant') {
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
const shouldCollapseMessageContent = computed(() => isLongMessage.value && !isMessageExpanded.value);
const showMessageExpandControl = computed(() => shouldCollapseMessageContent.value);

const { relativeTime } = useRelativeTime();

const formatTimestampTooltip = (timestamp: number): string => {
  const date = new Date(timestamp * 1000);
  return date.toLocaleString('en-US', {
    month: '2-digit',
    day: '2-digit',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
};

// Clipboard for copy functionality
const { copy, copied } = useClipboard();

// Copy user message to clipboard
const handleCopyUserMessage = () => {
  const content = messageContent.value?.content;
  if (content) {
    copy(content);
  }
};

// Shiki syntax highlighting
const { highlightDualTheme, normalizeLanguage } = useShiki();

// Cache for async-highlighted code blocks
const highlightedCodeCache = ref<Map<string, string>>(new Map());

// Generate a cache key for code blocks
function getCodeCacheKey(code: string, lang: string): string {
  return `${lang}:${code.slice(0, 50)}:${code.length}`;
}

// Async highlight code and update cache
async function highlightCodeBlock(code: string, lang: string): Promise<void> {
  const key = getCodeCacheKey(code, lang);
  if (highlightedCodeCache.value.has(key)) return;

  try {
    const highlighted = await highlightDualTheme(code, lang);
    highlightedCodeCache.value.set(key, highlighted);
  } catch {
    // Syntax highlighting failed - raw code will be shown
  }
}

// Create custom marked renderer with Shiki support
const createMarkedRenderer = () => {
  const renderer = new Renderer();

  // Override code block rendering
  renderer.code = function ({ text, lang }: { text: string; lang?: string }) {
    const language = normalizeLanguage(lang || 'text');
    const key = getCodeCacheKey(text, language);

    // Check if we have a cached highlighted version
    const cached = highlightedCodeCache.value.get(key);
    if (cached) {
      return `<div class="shiki-wrapper">${cached}</div>`;
    }

    // Schedule async highlighting for next render
    highlightCodeBlock(text, language);

    // Return placeholder that will be replaced on next render
    const escapedCode = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');

    return `<pre class="shiki-pending" data-lang="${language}"><code>${escapedCode}</code></pre>`;
  };

  return renderer;
};

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
  ([stepId, status, thinkingId]) => {
    if (stepUserToggled.value) return;
    const isActiveStep = Boolean(stepId) && thinkingId === stepId;
    isStepExpanded.value = isActiveStep || status === 'running';
  },
  { immediate: true }
);

// Memoized markdown rendering cache (WeakMap-like behavior using Map with limited size)
const markdownCache = new Map<string, string>();
const MAX_CACHE_SIZE = 100;

// Custom renderer with Shiki support
const markedRenderer = createMarkedRenderer();

// Render Markdown to HTML and sanitize (with memoization for performance)
const renderMarkdown = (text: string): string => {
  if (typeof text !== 'string') return '';

  // Create a cache key that includes highlighted code state
  const highlightedCount = highlightedCodeCache.value.size;
  const cacheKey = `${text}:${highlightedCount}`;

  // Check cache first
  const cached = markdownCache.get(cacheKey);
  if (cached !== undefined) {
    return cached;
  }

  // Render with custom renderer and sanitize
  const html = marked(text, { renderer: markedRenderer }) as string;
  const sanitized = DOMPurify.sanitize(html, {
    ADD_TAGS: ['span'],
    ADD_ATTR: ['style', 'class', 'data-lang'],
  });

  // Store in cache with size limit (evict oldest entries)
  if (markdownCache.size >= MAX_CACHE_SIZE) {
    const firstKey = markdownCache.keys().next().value;
    if (firstKey !== undefined) {
      markdownCache.delete(firstKey);
    }
  }
  markdownCache.set(cacheKey, sanitized);

  return sanitized;
};
</script>

<style>
/* ══════════════════════════════════════════════════
   User Message
   ══════════════════════════════════════════════════ */
.user-message-bubble {
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: box-shadow 0.15s ease;
}

/* ══════════════════════════════════════════════════
   Assistant Header
   ══════════════════════════════════════════════════ */
.assistant-header-row {
  min-height: 32px;
}

.assistant-brand {
  gap: 7px;
}

.assistant-brand-icon {
  width: 20px;
  height: 20px;
}

.assistant-time {
  opacity: 0;
  transition: opacity 0.15s ease;
}

.assistant-header-row:hover .assistant-time {
  opacity: 0.85;
}

.assistant-message-text {
  font-size: 15.5px;
  line-height: 1.6;
  color: var(--text-primary);
  font-weight: 400;
}

/* ══════════════════════════════════════════════════
   Report Layout
   ══════════════════════════════════════════════════ */
.report-message-layout {
  max-width: 100%;
}

/* ══════════════════════════════════════════════════
   Step Messages
   ══════════════════════════════════════════════════ */
.step-message {
  position: relative;
  margin-top: 12px;
}

.step-message:first-child {
  margin-top: 0;
}

.step-inner {
  display: flex;
  align-items: stretch;
}

/* Left rail - contains status node and timeline */
.step-left-rail {
  flex-shrink: 0;
  width: 24px;
}

/* Status node container */
.step-status-node {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 26px;
  flex-shrink: 0;
}

/* Status indicators */
.step-status-indicator {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.step-icon-completed {
  background: var(--text-disable);
  border: 0;
  border-radius: 15px;
}

.step-completed-check {
  color: var(--icon-white);
  width: 9px;
  height: 9px;
}

.step-icon-running {
  background: var(--fill-tsp-white-dark);
  border: 0;
  border-radius: 15px;
  position: relative;
  overflow: hidden;
}

.step-icon-pending {
  background: transparent;
  border: 0;
  border-radius: 15px;
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

/* Timeline connector segments (bottom of first node -> top of last node) */
.step-connector-segment {
  position: absolute;
  left: 8px;
  width: 0;
  border-left: 1px dashed var(--border-dark);
  pointer-events: none;
}

.step-connector-top {
  top: 0;
  height: 5px; /* Node top at (26 - 16) / 2 */
}

.step-connector-bottom {
  top: 21px; /* Node bottom: 5 + 16 */
  bottom: 0;
}

.step-connector-extended {
  bottom: -14px;
}

/* Right content */
.step-right-content {
  flex: 1;
  min-width: 0;
}

.step-header {
  color: var(--text-primary);
  padding: 0;
  cursor: pointer;
}

.step-title {
  font-size: 14px;
  line-height: 1.35;
  font-weight: 500;
  color: var(--text-primary);
  letter-spacing: 0;
}

.step-title :deep(p) {
  margin: 0;
}

.step-chevron {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
}

.step-timestamp {
  opacity: 0;
  transition: opacity 0.15s ease;
}

.step-header:hover .step-timestamp {
  opacity: 1;
}

.step-tools-list {
  overflow: hidden;
}

.step-tools-inner {
  padding-top: 8px;
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

:global(.dark) .step-title {
  color: #d5dae2;
}

:global(.dark) .assistant-message-text {
  color: #d5dbe4;
}

:global(.dark) .step-icon-completed {
  background: var(--fill-tsp-white-dark);
}

:global(.dark) .step-completed-check {
  color: var(--icon-white-tsp);
}

:global(.dark) .step-icon-running {
  background: var(--fill-tsp-white-dark);
}

:global(.dark) .step-icon-pending {
  background: var(--fill-tsp-white-dark);
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
.step-running {
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
  background: #1a1a2e;
  border-color: #30363d;
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
  background: #1a1a2e;
  border-color: #30363d;
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
