<template>
  <div
    class="report-card w-full max-w-[600px] min-w-0 rounded-[16px] border border-[var(--border-main)] bg-[var(--background-card)] overflow-hidden shadow-sm cursor-pointer hover:shadow-md transition-shadow"
    @click="openReport"
  >
    <!-- Header -->
    <div
      class="flex items-start gap-3 p-4 hover:bg-[var(--fill-tsp-white-main)] transition-colors"
    >
      <div class="flex-shrink-0 w-10 h-10 rounded-lg bg-[#4285f4] flex items-center justify-center">
        <FileText class="w-5 h-5 text-white" />
      </div>
      <div class="flex-1 min-w-0">
        <h3 class="text-[15px] font-semibold text-[var(--text-primary)] line-clamp-2 leading-snug">
          {{ report.title }}
        </h3>
      </div>
      <!-- More Options Dropdown -->
      <Popover v-model:open="showMenu">
        <PopoverTrigger as-child>
          <button
            class="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-md hover:bg-[var(--fill-tsp-gray-main)]"
            @click.stop
          >
            <MoreHorizontal class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
        </PopoverTrigger>
        <PopoverContent
          :side-offset="8"
          align="end"
          class="w-56 p-1.5"
          @click.stop
        >
          <div class="flex flex-col">
            <!-- Preview -->
            <button
              class="flex items-center gap-3 px-3 py-2.5 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-lg transition-colors"
              @click="handlePreview"
            >
              <Sparkles class="w-5 h-5 text-[var(--icon-secondary)]" />
              Preview
            </button>

            <!-- Share -->
            <button
              class="flex items-center gap-3 px-3 py-2.5 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-lg transition-colors"
              @click="handleShare"
            >
              <Share2 class="w-5 h-5 text-[var(--icon-secondary)]" />
              Share
            </button>

            <!-- Download with submenu -->
            <Popover v-model:open="showDownloadMenu">
              <PopoverTrigger as-child>
                <button
                  class="flex items-center justify-between gap-3 px-3 py-2.5 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-lg transition-colors w-full"
                  @click.stop
                  @mouseenter="showDownloadMenu = true"
                >
                  <div class="flex items-center gap-3">
                    <Download class="w-5 h-5 text-[var(--icon-secondary)]" />
                    Download
                  </div>
                  <ChevronRight class="w-4 h-4 text-[var(--icon-tertiary)]" />
                </button>
              </PopoverTrigger>
              <PopoverContent
                side="right"
                :side-offset="4"
                align="start"
                class="w-48 p-1.5"
              >
                <div class="flex flex-col">
                  <button
                    class="flex items-center gap-3 px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-lg transition-colors"
                    @click="handleDownloadMarkdown"
                  >
                    <FileText class="w-4 h-4 text-[var(--icon-secondary)]" />
                    Markdown (.md)
                  </button>
                  <button
                    class="flex items-center gap-3 px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-lg transition-colors"
                    @click="handleDownloadPdf"
                  >
                    <FileDown class="w-4 h-4 text-[#ea4335]" />
                    PDF Document
                  </button>
                  <button
                    class="flex items-center gap-3 px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-lg transition-colors"
                    @click="handleDownloadDocx"
                  >
                    <FileType class="w-4 h-4 text-[#4285f4]" />
                    Word (.docx)
                  </button>
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </PopoverContent>
      </Popover>
    </div>

    <!-- Content Preview - Rendered Markdown -->
    <div class="px-4 pb-4" v-if="report.content">
      <!-- Preview rendered markdown content -->
      <div
        class="report-preview text-sm text-[var(--text-secondary)] leading-relaxed max-h-[320px] overflow-hidden relative"
        v-html="renderedPreview"
      ></div>
      <div class="h-8 bg-gradient-to-t from-[var(--background-card)] to-transparent -mt-8 relative pointer-events-none"></div>
    </div>

    <!-- Suggested Follow-ups Section -->
    <div v-if="suggestions && suggestions.length > 0" class="border-t border-[var(--border-main)]">
      <div class="px-4 pt-4 pb-2">
        <span class="text-sm text-[var(--text-tertiary)]">Suggested follow-ups</span>
      </div>
      <div class="flex flex-col">
        <div
          v-for="(suggestion, index) in suggestions"
          :key="index"
          class="group flex items-start gap-3 px-4 py-4 cursor-pointer border-t border-[var(--border-light)] transition-colors hover:bg-[var(--fill-tsp-white-light)]"
          @click.stop="selectSuggestion(suggestion)"
        >
          <div class="flex-shrink-0 mt-0.5">
            <div
              class="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--border-light)] bg-[var(--fill-tsp-white-main)]"
            >
              <component
                :is="getSuggestionIcon(index)"
                class="h-4 w-4 text-[var(--icon-tertiary)] transition-colors group-hover:text-[var(--icon-primary)]"
              />
            </div>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-base text-[var(--text-primary)] leading-relaxed font-medium">
              {{ suggestion }}
            </p>
          </div>
          <div class="flex-shrink-0 mt-1">
            <ArrowRight class="w-5 h-5 text-[var(--icon-tertiary)] transition-colors group-hover:text-[var(--icon-primary)]" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { saveAs } from 'file-saver';
import {
  FileText,
  MoreHorizontal,
  MessageSquare,
  ArrowRight,
  Sparkles,
  Share2,
  Download,
  ChevronRight,
  FileDown,
  FileType
} from 'lucide-vue-next';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { ReportData, ReportSection } from './types';

export type { ReportData, ReportSection };

const props = defineProps<{
  report: ReportData;
  suggestions?: string[];
}>();

const emit = defineEmits<{
  (e: 'open', report: ReportData): void;
  (e: 'selectSuggestion', suggestion: string): void;
  (e: 'share', report: ReportData): void;
  (e: 'download', report: ReportData, format: string): void;
  (e: 'saveToCloud', report: ReportData, service: string): void;
}>();

const showMenu = ref(false);
const showDownloadMenu = ref(false);

const getSuggestionIcon = (index: number) => {
  const icons = [MessageSquare, MessageSquare, FileText];
  return icons[index % icons.length];
};

// Render preview markdown content (limited to first few sections)
const renderedPreview = computed(() => {
  if (!props.report.content) return '';

  // Take first ~2500 chars or until we have enough content
  const lines = props.report.content.split('\n');
  let preview = '';
  let charCount = 0;

  for (const line of lines) {
    // Skip the title (h1)
    if (line.startsWith('# ')) continue;
    preview += line + '\n';
    charCount += line.length;
    if (charCount > 2500) break;
  }

  try {
    const html = marked.parse(preview, { breaks: true, gfm: true });
    return DOMPurify.sanitize(html as string);
  } catch {
    return preview;
  }
});

const _formatDate = (timestamp: number) => {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  });
};

const openReport = () => {
  emit('open', props.report);
};

const selectSuggestion = (suggestion: string) => {
  emit('selectSuggestion', suggestion);
};

// Generate sanitized filename
const getSafeFilename = (title: string) => {
  return (title || 'document')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
    .substring(0, 50);
};

// Menu action handlers
const handlePreview = () => {
  showMenu.value = false;
  emit('open', props.report);
};

const handleShare = () => {
  showMenu.value = false;
  emit('share', props.report);
};

const handleDownloadMarkdown = () => {
  showMenu.value = false;
  showDownloadMenu.value = false;
  if (!props.report.content) return;
  const filename = getSafeFilename(props.report.title) + '.md';
  const blob = new Blob([props.report.content], { type: 'text/markdown;charset=utf-8' });
  saveAs(blob, filename);
  emit('download', props.report, 'markdown');
};

const handleDownloadPdf = () => {
  showMenu.value = false;
  showDownloadMenu.value = false;
  emit('download', props.report, 'pdf');
};

const handleDownloadDocx = () => {
  showMenu.value = false;
  showDownloadMenu.value = false;
  emit('download', props.report, 'docx');
};

const _handleConvertToGoogleDocs = () => {
  showMenu.value = false;
  emit('saveToCloud', props.report, 'google-docs');
};

const _handleSaveToGoogleDrive = () => {
  showMenu.value = false;
  emit('saveToCloud', props.report, 'google-drive');
};

const _handleSaveToOneDrivePersonal = () => {
  showMenu.value = false;
  emit('saveToCloud', props.report, 'onedrive-personal');
};

const _handleSaveToOneDriveWork = () => {
  showMenu.value = false;
  emit('saveToCloud', props.report, 'onedrive-work');
};
</script>

<style scoped>
@reference "tailwindcss";

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Report preview markdown styling */
.report-preview {
  @apply text-[var(--text-secondary)];
}

.report-preview :deep(h2),
.report-preview :deep(h3),
.report-preview :deep(h4) {
  @apply text-[var(--text-primary)] font-semibold mt-4 mb-2;
}

.report-preview :deep(h2) {
  @apply text-[18px];
}

.report-preview :deep(h3) {
  @apply text-[16px];
}

.report-preview :deep(h4) {
  @apply text-[14px];
}

.report-preview :deep(p) {
  @apply my-2 leading-relaxed;
}

.report-preview :deep(strong) {
  @apply text-[var(--text-primary)] font-semibold;
}

.report-preview :deep(table) {
  @apply w-full border-collapse my-3 text-xs;
}

.report-preview :deep(th) {
  @apply bg-[var(--fill-tsp-white-main)] text-left px-2 py-1.5 text-[var(--text-tertiary)] font-medium border-b border-[var(--border-main)];
}

.report-preview :deep(td) {
  @apply px-2 py-1.5 text-[var(--text-secondary)] border-b border-[var(--border-main)];
}

.report-preview :deep(ul),
.report-preview :deep(ol) {
  @apply my-2 pl-5;
}

.report-preview :deep(li) {
  @apply my-1;
}

.report-preview :deep(code) {
  @apply bg-[var(--fill-tsp-white-main)] px-1 py-0.5 rounded text-xs;
}

.report-preview :deep(pre) {
  @apply bg-[var(--fill-tsp-white-main)] p-2 rounded my-2 overflow-hidden;
}

.report-preview :deep(a) {
  @apply text-[#1a73e8] no-underline hover:underline;
}
</style>
