<template>
  <div v-if="message.type === 'user'" class="flex w-full flex-col items-end justify-end gap-1 group mt-3">
    <div class="flex items-end">
      <div class="flex items-center justify-end gap-[2px] invisible group-hover:visible">
        <div class="float-right transition text-[12px] text-[var(--text-tertiary)] invisible group-hover:visible">
          {{ relativeTime(message.content.timestamp) }}
        </div>
      </div>
    </div>
    <div class="flex max-w-[90%] relative flex-col gap-2 items-end">
      <div
        class="relative flex items-center rounded-[12px] overflow-hidden bg-[var(--bolt-elements-bg-depth-2)] p-3 ltr:rounded-br-none rtl:rounded-bl-none border border-[var(--bolt-elements-borderColor)]"
        v-html="renderMarkdown(messageContent.content)">
      </div>
      <!-- Copy button - appears on hover in bottom right corner -->
      <button
        @click="handleCopyUserMessage"
        class="absolute bottom-2 right-2 p-1.5 rounded-md bg-[var(--background-white-main)] border border-[var(--border-main)] shadow-sm opacity-0 group-hover:opacity-100 transition-opacity duration-200 hover:bg-[var(--fill-tsp-gray-main)]"
        :title="copied ? 'Copied!' : 'Copy message'"
      >
        <Check v-if="copied" :size="14" class="text-green-500" />
        <Copy v-else :size="14" class="text-[var(--icon-secondary)]" />
      </button>
    </div>
  </div>
  <div v-else-if="message.type === 'assistant'" class="flex flex-col gap-2 w-full group mt-3">
    <div class="flex items-center justify-between h-7 group">
      <div class="flex items-center gap-[6px]">
        <Bot :size="20" class="w-5 h-5 text-[var(--text-primary)]" :stroke-width="2.5" />
        <PythinkerTextIcon :width="80" :height="20" />
      </div>
      <div class="flex items-center gap-[2px] invisible group-hover:visible">
        <div class="transition text-[12px] text-[var(--text-tertiary)] invisible group-hover:visible">
          {{ relativeTime(message.content.timestamp) }}
        </div>
      </div>
    </div>
    <div
      class="max-w-none p-0 m-0 prose prose-sm sm:prose-base dark:prose-invert [&_pre:not(.shiki)]:!bg-[var(--bolt-elements-messages-code-background)] [&_pre:not(.shiki)]:text-[var(--bolt-elements-messages-inlineCode-text)] text-base text-[var(--text-primary)]"
      v-html="renderMarkdown(messageContent.content)"></div>
  </div>
  <ToolUse v-else-if="message.type === 'tool'" :tool="toolContent" :is-active="true" @click="handleToolClick(toolContent)" />
  <div v-else-if="message.type === 'step'" class="flex flex-col mt-2">
    <!-- Step Header -->
    <div class="w-full flex gap-2 justify-between group/header text-[var(--text-primary)]">
      <div class="flex flex-row gap-[10px] items-start flex-1 min-w-0 cursor-pointer" @click="handleStepToggle">
        <!-- Status indicator -->
        <div v-if="stepContent.status === 'completed'"
          class="w-[18px] h-[18px] flex-shrink-0 flex items-center justify-center rounded-full bg-[var(--text-tertiary)] mt-[2px]">
          <CheckIcon class="text-white" :size="12" :stroke-width="3" />
        </div>
        <div v-else-if="stepContent.status === 'running'"
          class="w-[18px] h-[18px] flex-shrink-0 flex items-center justify-center rounded-full border-2 border-[var(--text-tertiary)] mt-[2px] step-running">
        </div>
        <div v-else
          class="w-[18px] h-[18px] flex-shrink-0 flex items-center justify-center rounded-full border border-[var(--border-dark)] mt-[2px]">
        </div>
        <!-- Step title and chevron -->
        <div class="flex-1 min-w-0 flex items-start gap-1">
          <div class="flex-1 min-w-0 text-[15px] font-medium leading-snug markdown-content"
            v-html="stepContent.description ? renderMarkdown(stepContent.description) : ''">
          </div>
          <span class="flex-shrink-0 flex mt-[2px]">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
              class="transition-transform duration-200 text-[var(--text-tertiary)]"
              :class="{ 'rotate-180': !isExpanded }">
              <path d="m6 9 6 6 6-6"></path>
            </svg>
          </span>
        </div>
      </div>
      <div class="flex-shrink-0 transition text-[12px] text-[var(--text-tertiary)] invisible group-hover/header:visible">
        {{ relativeTime(message.content.timestamp) }}
      </div>
    </div>
    <!-- Tools list with timeline -->
    <div class="flex" v-show="isExpanded">
      <div class="w-[28px] relative flex-shrink-0">
        <div class="border-l border-dashed border-[var(--border-dark)] absolute start-[8px] top-0 bottom-0"></div>
      </div>
      <div class="flex flex-col gap-[10px] flex-1 min-w-0 overflow-hidden pt-3 pb-1">
        <ToolUse
          v-for="(tool, index) in stepContent.tools"
          :key="tool.tool_call_id"
          :tool="tool"
          :is-active="index === stepContent.tools.length - 1"
          @click="handleToolClick(tool)"
        />
      </div>
    </div>
  </div>
  <AttachmentsMessage v-else-if="message.type === 'attachments'" :content="attachmentsContent" @fileClick="handleReportFileOpen"/>
  <div v-else-if="message.type === 'report'" class="flex flex-col w-full mt-3">
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
</template>

<script setup lang="ts">
import PythinkerTextIcon from './icons/PythinkerTextIcon.vue';
import { Message, MessageContent, AttachmentsContent, ReportContent, DeepResearchContent } from '../types/message';
import ToolUse from './ToolUse.vue';
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
import { useShiki } from '@/composables/useShiki';


const props = defineProps<{
  message: Message;
  sessionId?: string;
  suggestions?: string[];
}>();

const emit = defineEmits<{
  (e: 'toolClick', tool: ToolContent): void;
  (e: 'reportOpen', report: ReportData): void;
  (e: 'reportFileOpen', file: FileInfo): void;
  (e: 'showAllFiles'): void;
  (e: 'reportRate', rating: number): void;
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

const handleReportRate = (rating: number) => {
  emit('reportRate', rating);
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

// Control content expand/collapse state
const isExpanded = ref(true);
const userToggled = ref(false);

const { relativeTime } = useRelativeTime();

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
  } catch (error) {
    console.error('Failed to highlight code block:', error);
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
  userToggled.value = true;
  isExpanded.value = !isExpanded.value;
};

watch(
  () => stepContent.value?.status,
  (status) => {
    if (status === 'completed' && !userToggled.value) {
      isExpanded.value = false;
    }
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
.duration-300 {
  animation-duration: .3s;
}

.duration-300 {
  transition-duration: .3s;
}

/* Pulse animation for running step indicator */
.step-running {
  animation: step-pulse 1.5s ease-in-out infinite;
}

@keyframes step-pulse {
  0%, 100% {
    border-color: var(--text-tertiary);
    opacity: 0.6;
  }
  50% {
    border-color: var(--text-primary);
    opacity: 1;
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
</style>
