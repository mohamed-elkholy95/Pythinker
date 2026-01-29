<template>
  <div
    class="report-card"
    @click="openReport"
  >
    <!-- Header -->
    <div class="report-header">
      <div class="report-icon">
        <FileText class="w-5 h-5 text-white" />
      </div>
      <div class="flex-1 min-w-0">
        <h3 class="report-title">
          {{ report.title }}
        </h3>
      </div>
      <!-- More Options Dropdown -->
      <Popover v-model:open="showMenu">
        <PopoverTrigger as-child>
          <button
            class="report-menu-btn"
            @click.stop
          >
            <MoreHorizontal class="w-4 h-4" />
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
    <div class="report-content" v-if="report.content">
      <div
        class="report-preview"
        v-html="renderedPreview"
      ></div>
      <div class="report-fade"></div>
    </div>

    <!-- Suggested Follow-ups Section -->
    <div v-if="suggestions && suggestions.length > 0" class="suggestions-section">
      <div class="suggestions-header">
        <span>Suggested follow-ups</span>
      </div>
      <div class="suggestions-list">
        <div
          v-for="(suggestion, index) in suggestions"
          :key="index"
          class="suggestion-item"
          @click.stop="selectSuggestion(suggestion)"
        >
          <div class="suggestion-icon-wrap">
            <component
              :is="getSuggestionIcon(index)"
              class="suggestion-icon"
            />
          </div>
          <div class="flex-1 min-w-0">
            <p class="suggestion-text">
              {{ suggestion }}
            </p>
          </div>
          <div class="suggestion-arrow">
            <ArrowRight class="w-4 h-4" />
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

/* ===== CARD CONTAINER ===== */
.report-card {
  width: 100%;
  max-width: 600px;
  min-width: 0;
  border-radius: 16px;
  overflow: hidden;
  cursor: pointer;
  background: var(--background-card);
  border: 1px solid var(--bolt-elements-borderColor);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.report-card:hover {
  border-color: var(--bolt-elements-borderColorActive);
  transform: translateY(-2px);
}

/* ===== HEADER ===== */
.report-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  transition: background-color 0.15s ease;
}

.report-card:hover .report-header {
  background: var(--bolt-elements-item-backgroundActive);
}

.report-icon {
  flex-shrink: 0;
  width: 42px;
  height: 42px;
  border-radius: 10px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
}

.report-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.report-menu-btn {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--icon-tertiary);
  transition: all 0.15s ease;
  opacity: 0;
}

.report-card:hover .report-menu-btn {
  opacity: 1;
}

.report-menu-btn:hover {
  background: var(--bolt-elements-item-backgroundActive);
  color: var(--icon-secondary);
}

/* ===== CONTENT ===== */
.report-content {
  padding: 0 16px 16px;
  position: relative;
}

.report-fade {
  height: 32px;
  background: linear-gradient(to top, var(--background-card) 0%, transparent 100%);
  margin-top: -32px;
  position: relative;
  pointer-events: none;
}

/* ===== SUGGESTIONS ===== */
.suggestions-section {
  border-top: 1px solid var(--bolt-elements-borderColor);
}

.suggestions-header {
  padding: 14px 16px 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.suggestions-list {
  display: flex;
  flex-direction: column;
}

.suggestion-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  cursor: pointer;
  border-top: 1px solid var(--bolt-elements-borderColor);
  transition: all 0.15s ease;
}

.suggestion-item:hover {
  background: var(--bolt-elements-item-backgroundAccent);
}

.suggestion-icon-wrap {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--bolt-elements-bg-depth-4);
  border: 1px solid var(--bolt-elements-borderColor);
  transition: all 0.15s ease;
}

.suggestion-item:hover .suggestion-icon-wrap {
  background: var(--bolt-elements-item-backgroundAccent);
  border-color: var(--bolt-elements-borderColorActive);
}

.suggestion-icon {
  width: 14px;
  height: 14px;
  color: var(--icon-tertiary);
  transition: color 0.15s ease;
}

.suggestion-item:hover .suggestion-icon {
  color: #3b82f6;
}

.suggestion-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 1.5;
}

.suggestion-arrow {
  flex-shrink: 0;
  margin-top: 4px;
  color: var(--icon-tertiary);
  opacity: 0;
  transform: translateX(-4px);
  transition: all 0.2s ease;
}

.suggestion-item:hover .suggestion-arrow {
  opacity: 1;
  transform: translateX(0);
  color: #3b82f6;
}

/* ===== LINE CLAMP ===== */
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ===== REPORT PREVIEW MARKDOWN ===== */
.report-preview {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  max-height: 320px;
  overflow: hidden;
  position: relative;
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
