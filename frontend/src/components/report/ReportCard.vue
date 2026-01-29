<template>
  <div
    class="report-card"
    @click="openReport"
  >
    <!-- Header Bar -->
    <div class="report-header-bar">
      <div class="header-left">
        <div class="report-icon-small">
          <FileText class="w-4 h-4 text-white" />
        </div>
        <span class="header-title">{{ report.title }}</span>
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

    <!-- Document Content Area with Left Border Accent -->
    <div class="document-content">
      <div class="content-inner">
        <!-- Metadata: Author and Date stacked -->
        <div class="document-meta">
          <div class="meta-item">
            <span class="meta-label">Author:</span>
            <span class="meta-value">{{ report.author || 'Pythinker AI' }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Date:</span>
            <span class="meta-value">{{ formatDateLong(report.lastModified) }}</span>
          </div>
        </div>

        <!-- Content Preview using Tiptap -->
        <div class="content-preview-container">
          <TiptapReportEditor
            v-if="report.content"
            :content="processedContent"
            :compact="true"
          />
          <div class="content-fade"></div>
        </div>
      </div>
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
import { saveAs } from 'file-saver';
import {
  FileText,
  MoreHorizontal,
  MessageSquare,
  ArrowRight,
  MousePointer2,
  Share2,
  Download,
  ChevronRight
} from 'lucide-vue-next';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import TiptapReportEditor from './TiptapReportEditor.vue';
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

// Process content for preview - limit to first ~1500 chars for compact card
const processedContent = computed(() => {
  if (!props.report.content) return '';

  const lines = props.report.content.split('\n');
  let preview = '';
  let charCount = 0;

  for (const line of lines) {
    // Skip the title (h1) - shown in header
    if (line.startsWith('# ')) continue;
    preview += line + '\n';
    charCount += line.length;
    if (charCount > 1500) break;
  }

  return preview;
});

const formatDate = (timestamp: number) => {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
};

const formatDateLong = (timestamp: number) => {
  const date = new Date(timestamp);
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
  max-width: 520px;
  min-width: 0;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.report-card:hover {
  border-color: var(--bolt-elements-borderColorActive);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

/* ===== HEADER BAR ===== */
.report-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-light);
  background: var(--fill-tsp-gray-main);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.report-icon-small {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border-radius: 5px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.report-menu-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
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

/* ===== DOCUMENT CONTENT ===== */
.document-content {
  padding: 14px 16px;
  position: relative;
}

.content-inner {
  padding-left: 14px;
  border-left: 3px solid #3b82f6;
}

.document-meta {
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin-bottom: 12px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  line-height: 1.5;
}

.meta-label {
  font-weight: 600;
  color: var(--text-primary);
}

.meta-value {
  color: var(--text-secondary);
}

/* ===== CONTENT PREVIEW ===== */
.content-preview-container {
  position: relative;
  max-height: 180px;
  overflow: hidden;
}

.content-fade {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 60px;
  background: linear-gradient(to top, var(--background-white-main) 0%, transparent 100%);
  pointer-events: none;
}

/* ===== SUGGESTIONS ===== */
.suggestions-section {
  border-top: 1px solid var(--border-main);
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
  border-top: 1px solid var(--border-light);
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
  border: 1px solid var(--border-light);
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
