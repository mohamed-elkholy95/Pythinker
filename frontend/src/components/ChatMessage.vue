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
  <ToolUse v-else-if="message.type === 'tool'" :tool="toolContent" @click="handleToolClick(toolContent)" />
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
        <ToolUse v-for="(tool, index) in stepContent.tools" :key="index" :tool="tool" @click="handleToolClick(tool)" />
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
</template>

<script setup lang="ts">
import PythinkerTextIcon from './icons/PythinkerTextIcon.vue';
import { Message, MessageContent, AttachmentsContent, ReportContent } from '../types/message';
import ToolUse from './ToolUse.vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { CheckIcon } from 'lucide-vue-next';
import { computed, ref, watch } from 'vue';
import { ToolContent, StepContent } from '../types/message';
import { useRelativeTime } from '../composables/useTime';
import { Bot } from 'lucide-vue-next';
import AttachmentsMessage from './AttachmentsMessage.vue';
import { ReportCard, AttachmentsInlineGrid, TaskCompletedFooter } from './report';
import type { ReportData } from './report';
import type { FileInfo } from '../api/file';


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

// For backward compatibility, provide the original computed properties
const stepContent = computed(() => props.message.content as StepContent);
const messageContent = computed(() => props.message.content as MessageContent);
const toolContent = computed(() => props.message.content as ToolContent);
const attachmentsContent = computed(() => props.message.content as AttachmentsContent);
const reportContent = computed(() => props.message.content as ReportContent);

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

// Render Markdown to HTML and sanitize
const renderMarkdown = (text: string) => {
  if (typeof text !== 'string') return '';
  const html = marked(text) as string;
  return DOMPurify.sanitize(html);
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
</style>
