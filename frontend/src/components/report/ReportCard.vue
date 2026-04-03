<template>
  <div
    class="report-card"
    @click="openReport"
  >
    <!-- Header Bar -->
    <div class="report-header-bar">
      <div class="header-left">
        <div class="report-icon-small">
          <svg class="report-doc-icon" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M3.55566 26.8889C3.55566 28.6071 4.94856 30 6.66678 30H25.3334C27.0517 30 28.4446 28.6071 28.4446 26.8889V9.77778L20.6668 2H6.66678C4.94856 2 3.55566 3.39289 3.55566 5.11111V26.8889Z" fill="#4D81E8"></path>
            <path d="M20.6685 6.66647C20.6685 8.38469 22.0613 9.77759 23.7796 9.77759H28.4462L20.6685 1.99981V6.66647Z" fill="#9CC3F4"></path>
            <path opacity="0.9" d="M10.1685 18.2363H21.8351" stroke="white" stroke-width="1.75" stroke-linecap="square" stroke-linejoin="round"></path>
            <path opacity="0.9" d="M10.1685 14.3472H12.1129" stroke="white" stroke-width="1.75" stroke-linecap="square" stroke-linejoin="round"></path>
            <path opacity="0.9" d="M15.0293 14.3472H16.9737" stroke="white" stroke-width="1.75" stroke-linecap="square" stroke-linejoin="round"></path>
            <path opacity="0.9" d="M10.1685 21.8333H21.8351" stroke="white" stroke-width="1.75" stroke-linecap="square" stroke-linejoin="round"></path>
          </svg>
        </div>
        <span class="header-title">{{ report.title }}</span>
      </div>
      <!-- More Options Dropdown -->
      <Popover v-model:open="showMenu">
        <PopoverTrigger as-child>
          <button
            class="report-menu-btn"
            aria-label="Report options"
            @click.stop
          >
            <MoreHorizontal class="w-4 h-4" />
          </button>
        </PopoverTrigger>
        <PopoverContent
          :side-offset="4"
          align="end"
          class="menu-popover"
          :style="{ width: '110px', minWidth: 'unset' }"
          @click.stop
        >
          <div class="menu-list">
            <!-- Preview -->
            <button class="menu-item" @click="handlePreview">
              <MousePointer2 class="menu-icon" />
              <span>Preview</span>
            </button>

            <!-- Share -->
            <button class="menu-item" @click="handleShare">
              <Share2 class="menu-icon" />
              <span>Share</span>
            </button>

            <div class="menu-divider" />

            <!-- Download with submenu -->
            <Popover v-model:open="showDownloadMenu">
              <PopoverTrigger as-child>
                <button
                  class="menu-item menu-item-expandable"
                  @click.stop
                  @mouseenter="showDownloadMenu = true"
                >
                  <Download class="menu-icon" />
                  <span>Download</span>
                  <ChevronRight class="menu-chevron" />
                </button>
              </PopoverTrigger>
              <PopoverContent
                side="right"
                :side-offset="2"
                align="start"
                class="submenu-popover"
                :style="{ width: '100px', minWidth: 'unset' }"
              >
                <div class="menu-list">
                  <button class="menu-item" @click="handleDownloadMarkdown">
                    <div class="file-icon file-icon-md">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="8" y1="10" x2="16" y2="10" />
                        <line x1="8" y1="14" x2="14" y2="14" />
                      </svg>
                    </div>
                    <span>Markdown</span>
                  </button>
                  <button class="menu-item" @click="handleDownloadPdf">
                    <div class="file-icon file-icon-pdf">
                      <span class="file-icon-text">A</span>
                    </div>
                    <span>PDF</span>
                  </button>
                  <button class="menu-item" @click="handleDownloadDocx">
                    <div class="file-icon file-icon-docx">
                      <span class="file-icon-text">W</span>
                    </div>
                    <span>Docx</span>
                  </button>
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </PopoverContent>
      </Popover>
    </div>

    <!-- Scaled Content Preview (Manus-style 16:9 aspect with 0.75 scale) -->
    <div class="size-full relative aspect-[16/9] px-[16px] py-[8px] pointer-events-none">
      <div class="scale-[0.75] origin-top-left w-[133.33%] h-[133.33%]">
        <TiptapReportEditor
          v-if="report.content"
          class="report-markdown-preview"
          :content="processedContent"
          :compact="true"
          :hideMainTitleInCompact="true"
          :sources="report.sources"
        />
      </div>
      <div
        class="pointer-events-none absolute left-0 right-0 bottom-0 h-[118px]"
        style="background: linear-gradient(rgba(255, 255, 255, 0) 0%, var(--background-menu-white) 100%)"
      ></div>
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
          <p class="suggestion-text">
            {{ suggestion }}
          </p>
          <ArrowRight class="suggestion-arrow" :size="16" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { saveAs } from 'file-saver';
import {
  MoreHorizontal,
  MessageCircle,
  Puzzle,
  Briefcase,
  ArrowRight,
  MousePointer2,
  Share2,
  Download,
  ChevronRight
} from 'lucide-vue-next';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import TiptapReportEditor from './TiptapReportEditor.vue';
import type { ReportData, ReportSection } from './types';
import {
  collapseDuplicateReportBlocks,
  stripLegacyPreviouslyCalledMarkers,
} from './reportContentNormalizer';

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
const normalizedReportContent = computed(() =>
  collapseDuplicateReportBlocks(stripLegacyPreviouslyCalledMarkers(props.report.content || '')),
);

const getSuggestionIcon = (index: number) => {
  const icons = [Puzzle, MessageCircle, MessageCircle, Briefcase];
  return icons[index % icons.length];
};

// Process content for preview - keep card rendering lightweight
const processedContent = computed(() => {
  if (!normalizedReportContent.value) return '';

  // Prepend Author/Date metadata (matching Manus design)
  const metaLines: string[] = [];
  const author = props.report.author || 'Pythinker';
  metaLines.push(`**Author:** ${author}`);
  const dateStr = _formatDateLong(props.report.lastModified);
  if (dateStr !== 'Unknown') metaLines.push(`**Date:** ${dateStr}`);
  const metaBlock = metaLines.join('\n');

  const normalized = normalizedReportContent.value.replace(/^\n+/, '').trim();
  const withMeta = `${metaBlock}\n\n${normalized}`;
  if (withMeta.length <= 1900) return withMeta;

  // Find a safe cut point at a paragraph/section boundary to avoid
  // bisecting markdown structures (tables, code fences, lists) which
  // would produce malformed markdown that renders as raw text.
  const limit = 1900;
  let cutAt = limit;

  // Prefer cutting at a blank line (paragraph boundary)
  const lastBlankLine = normalized.lastIndexOf('\n\n', limit);
  if (lastBlankLine > limit * 0.5) {
    cutAt = lastBlankLine;
  } else {
    // Fall back to the last single newline (line boundary)
    const lastNewline = normalized.lastIndexOf('\n', limit);
    if (lastNewline > limit * 0.5) {
      cutAt = lastNewline;
    }
  }

  return withMeta.slice(0, cutAt);
});

const _formatDateLong = (timestamp: number | string | undefined) => {
  if (timestamp == null) return 'Unknown';
  // Handle ISO string timestamps from backend
  const ms = typeof timestamp === 'string' ? new Date(timestamp).getTime() : timestamp;
  if (!Number.isFinite(ms) || ms <= 0) return 'Unknown';
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return 'Unknown';
  return date.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric'
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
  if (!normalizedReportContent.value) return;
  const filename = getSafeFilename(props.report.title) + '.md';
  const blob = new Blob([normalizedReportContent.value], { type: 'text/markdown;charset=utf-8' });
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

// Cloud save handlers reserved for future integration (Google Docs, Google Drive, OneDrive)
</script>

<style scoped>
@reference "tailwindcss";

/* ===== CARD CONTAINER ===== */
.report-card {
  width: 100%;
  max-width: 568px;
  min-width: 0;
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  background: var(--background-menu-white);
  border: 0.5px solid var(--border-dark);
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.report-card:hover {
  box-shadow: 0 4px 20px 0 rgba(0, 0, 0, 0.06);
}

/* ===== HEADER BAR ===== */
.report-header-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 12px;
  border-bottom: 1px solid var(--border-main);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.report-icon-small {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.report-doc-icon {
  width: 24px;
  height: 24px;
}

.header-title {
  font-family: var(--font-content);
  font-size: 14px;
  line-height: 20px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.report-menu-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  color: var(--icon-secondary);
  transition: all 0.15s ease;
}

.report-menu-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

/* ===== CONTENT PREVIEW (scaled 0.75, inline Tailwind handles layout) ===== */
.report-markdown-preview {
  width: 100%;
  font-family: var(--font-content);
}

.report-markdown-preview :deep(.prose-compact) {
  color: var(--text-primary);
  font-size: 16px;
  line-height: 1.5;
}

.report-markdown-preview :deep(.prose-compact h1),
.report-markdown-preview :deep(.prose-compact h2),
.report-markdown-preview :deep(.prose-compact h3) {
  font-family: var(--font-content);
  font-weight: 600;
  line-height: 1.3;
}

.report-markdown-preview :deep(.prose-compact h1) {
  font-size: 1.875em;
  margin-top: 2em;
  margin-bottom: 4px;
}

.report-markdown-preview :deep(.prose-compact h2) {
  font-size: 1.5em;
  margin-top: 1.4em;
  margin-bottom: 1px;
}

.report-markdown-preview :deep(.prose-compact p) {
  margin-top: 1px;
  margin-bottom: 1px;
}

.report-markdown-preview :deep(.prose-compact blockquote) {
  border-left: none;
  margin-left: 0;
  padding-left: 0;
}

/* ===== SUGGESTIONS ===== */
.suggestions-section {
  border-top: 1px solid #d8dbe0;
  margin-top: 14px;
  padding: 0;
}

.suggestions-header {
  padding: 16px 0 8px;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: #7b8088;
}

.suggestions-list {
  display: flex;
  flex-direction: column;
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 2px;
  cursor: pointer;
  border-bottom: 1px solid #d8dbe0;
  transition: background 0.15s ease, color 0.15s ease;
}

.suggestion-item:hover {
  background: rgba(15, 23, 42, 0.03);
}

.suggestion-icon-wrap {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: transparent;
  border: none;
}

.suggestion-icon {
  width: 30px;
  height: 30px;
  color: #888b90;
  stroke-width: 1.7;
}

.suggestion-text {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: 22px;
  font-weight: 500;
  color: #595c60;
  line-height: 1.35;
  letter-spacing: -0.01em;
}

.suggestion-arrow {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  color: #a3a6ab;
  opacity: 1;
  transition: color 0.15s ease;
  stroke-width: 1.7;
}

.suggestion-item:hover .suggestion-arrow {
  color: #8d9198;
}

/* ── Dark mode: suggestions section ── */
:global(.dark) .suggestions-section {
  border-top-color: var(--border-main);
}

:global(.dark) .suggestions-header {
  color: var(--text-secondary);
}

:global(.dark) .suggestion-item {
  border-bottom-color: var(--border-main);
}

:global(.dark) .suggestion-item:hover {
  background: rgba(255, 255, 255, 0.04);
}

:global(.dark) .suggestion-text {
  color: var(--text-primary);
}

:global(.dark) .suggestion-icon {
  color: var(--text-tertiary);
}

:global(.dark) .suggestion-arrow {
  color: var(--text-tertiary);
}

:global(.dark) .suggestion-item:hover .suggestion-arrow {
  color: var(--text-secondary);
}

@media (max-width: 900px) {
  .suggestions-header {
    font-size: 16px;
  }

  .suggestion-icon {
    width: 22px;
    height: 22px;
  }

  .suggestion-text {
    font-size: 18px;
  }

  .suggestion-arrow {
    width: 24px;
    height: 24px;
  }
}

/* ===== MENU POPOVER ===== */
:deep(.menu-popover),
:deep(.submenu-popover) {
  padding: 4px !important;
  background: var(--background-white-main) !important;
  border: 1px solid var(--border-light) !important;
  border-radius: 8px !important;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1) !important;
}

.menu-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 450;
  color: var(--text-primary);
  border-radius: 5px;
  transition: background 0.15s ease;
  white-space: nowrap;
  text-align: left;
}

.menu-item:hover {
  background: var(--fill-tsp-gray-main);
}

.menu-item-expandable {
  justify-content: flex-start;
}

.menu-item-expandable span {
  flex: 1;
}

.menu-icon {
  width: 14px;
  height: 14px;
  color: var(--icon-secondary);
  flex-shrink: 0;
}

.menu-chevron {
  width: 12px;
  height: 12px;
  color: var(--icon-tertiary);
  flex-shrink: 0;
  margin-left: auto;
}

.menu-divider {
  height: 1px;
  background: var(--border-light);
  margin: 3px 0;
}

/* ===== FILE TYPE ICONS ===== */
.file-icon {
  width: 18px;
  height: 22px;
  border-radius: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
}

.file-icon::before {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  width: 5px;
  height: 5px;
  background: var(--background-white-main);
  border-bottom-left-radius: 1px;
}

.file-icon-md {
  background: #4285f4;
  color: white;
}

.file-icon-md svg {
  width: 10px;
  height: 10px;
}

.file-icon-pdf {
  background: #ea4335;
}

.file-icon-docx {
  background: #4285f4;
}

.file-icon-text {
  font-size: 9px;
  font-weight: 700;
  color: white;
  line-height: 1;
}
</style>
