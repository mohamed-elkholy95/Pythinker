<template>
  <div
    class="report-card w-[600px] rounded-[16px] border border-[var(--border-main)] bg-[var(--background-card)] overflow-hidden shadow-sm cursor-pointer hover:shadow-md transition-shadow"
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

    <!-- Attached Files Preview -->
    <div v-if="report.attachments && report.attachments.length > 0" class="px-4 pb-4">
      <div class="grid grid-cols-2 gap-2">
        <div
          v-for="file in displayedAttachments"
          :key="file.file_id"
          class="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-[var(--fill-tsp-white-main)] border border-[var(--border-main)] cursor-pointer hover:bg-[var(--fill-tsp-white-dark)] transition-colors"
          @click.stop="openFile(file)"
        >
          <div
            class="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
            :class="getFileIconBgClass(file.filename)"
          >
            <component :is="getFileIcon(file.filename)" class="w-5 h-5 text-white" />
          </div>
          <div class="flex flex-col min-w-0 flex-1">
            <span class="text-sm text-[var(--text-primary)] truncate font-medium">
              {{ file.filename }}
            </span>
            <span class="text-xs text-[var(--text-tertiary)]">
              {{ getFileTypeLabel(file.filename) }} · {{ formatFileSize(file.size) }}
            </span>
          </div>
        </div>

        <!-- View all files button - inline in grid -->
        <button
          v-if="report.attachments.length > maxDisplayedFiles"
          class="flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-[var(--fill-tsp-white-main)] border border-[var(--border-main)] cursor-pointer hover:bg-[var(--fill-tsp-white-dark)] transition-colors"
          @click.stop="showAllFiles"
        >
          <FolderOpen class="w-4 h-4 text-[var(--icon-secondary)]" />
          <span class="text-sm text-[var(--text-secondary)]">
            View all files in this task
          </span>
        </button>
      </div>
    </div>

    <!-- Footer with Task Completed -->
    <div class="flex items-center justify-between px-4 py-3 border-t border-[var(--border-main)] bg-[var(--fill-tsp-white-main)]">
      <div class="flex items-center gap-2 flex-shrink-0">
        <Check class="w-4 h-4 text-[var(--function-success)]" />
        <span class="text-sm text-[var(--function-success)] font-medium whitespace-nowrap">Task completed</span>
      </div>
      <div class="flex items-center gap-1 flex-shrink-0">
        <span class="text-xs text-[var(--text-tertiary)] mr-2 whitespace-nowrap">How was this result?</span>
        <div class="flex items-center">
          <button
            v-for="i in 5"
            :key="i"
            class="w-6 h-6 flex items-center justify-center group"
            @click.stop="rate(i)"
            @mouseenter="hoverRating = i"
            @mouseleave="hoverRating = 0"
          >
            <Star
              class="w-4 h-4 transition-colors"
              :class="i <= (hoverRating || rating) ? 'text-yellow-400 fill-yellow-400' : 'text-[var(--icon-tertiary)] group-hover:text-yellow-300'"
            />
          </button>
        </div>
      </div>
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
          class="flex items-start gap-3 px-4 py-3 cursor-pointer hover:bg-[var(--fill-tsp-white-main)] transition-colors group"
          @click.stop="selectSuggestion(suggestion)"
        >
          <div class="flex-shrink-0 mt-0.5">
            <Lightbulb class="w-5 h-5 text-[var(--icon-tertiary)]" />
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-sm text-[var(--text-secondary)] leading-relaxed">
              {{ suggestion }}
            </p>
          </div>
          <div class="flex-shrink-0">
            <ArrowRight class="w-5 h-5 text-[var(--icon-tertiary)] group-hover:text-[var(--icon-secondary)]" />
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
  Check,
  Star,
  FolderOpen,
  FileCode,
  FileArchive,
  FileImage,
  File,
  Lightbulb,
  ArrowRight,
  Sparkles,
  Share2,
  Download,
  ChevronRight,
  FileDown,
  FileType
} from 'lucide-vue-next';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { FileInfo } from '@/api/file';
import type { ReportData, ReportSection } from './types';

export type { ReportData, ReportSection };

const props = defineProps<{
  report: ReportData;
  suggestions?: string[];
}>();

const emit = defineEmits<{
  (e: 'open', report: ReportData): void;
  (e: 'openFile', file: FileInfo): void;
  (e: 'showAllFiles'): void;
  (e: 'rate', rating: number): void;
  (e: 'selectSuggestion', suggestion: string): void;
  (e: 'share', report: ReportData): void;
  (e: 'download', report: ReportData, format: string): void;
  (e: 'saveToCloud', report: ReportData, service: string): void;
}>();

const rating = ref(0);
const hoverRating = ref(0);
const maxDisplayedFiles = 4;
const showMenu = ref(false);
const showDownloadMenu = ref(false);
const showHeaderDownload = ref(false);

const displayedAttachments = computed(() => {
  // Show up to maxDisplayedFiles, but leave room for "View all" button if there are more
  const attachments = props.report.attachments || [];
  if (attachments.length > maxDisplayedFiles) {
    return attachments.slice(0, maxDisplayedFiles - 1);
  }
  return attachments.slice(0, maxDisplayedFiles);
});

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

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const getFileIcon = (filename: string) => {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (['md', 'txt', 'doc', 'docx', 'pdf'].includes(ext)) return FileText;
  if (['js', 'ts', 'py', 'json', 'html', 'css', 'vue', 'jsx', 'tsx'].includes(ext)) return FileCode;
  if (['zip', 'tar', 'gz', 'rar', '7z'].includes(ext)) return FileArchive;
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)) return FileImage;
  return File;
};

const getFileIconBgClass = (filename: string) => {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  // Code files - blue
  if (['js', 'ts', 'py', 'json', 'html', 'css', 'vue', 'jsx', 'tsx', 'java', 'go', 'rs'].includes(ext)) {
    return 'bg-[#4285f4]';
  }
  // Markdown/Document files - teal/blue
  if (['md', 'txt'].includes(ext)) {
    return 'bg-[#4285f4]';
  }
  // Office documents - blue
  if (['doc', 'docx', 'pdf'].includes(ext)) {
    return 'bg-[#4285f4]';
  }
  // Archive files - orange/red
  if (['zip', 'tar', 'gz', 'rar', '7z'].includes(ext)) {
    return 'bg-[#EA4335]';
  }
  // Image files - green
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)) {
    return 'bg-[#10B981]';
  }
  // Default - gray
  return 'bg-[#6B7280]';
};

const getFileTypeLabel = (filename: string) => {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const typeMap: Record<string, string> = {
    md: 'Markdown',
    txt: 'Text',
    pdf: 'PDF',
    doc: 'Document',
    docx: 'Document',
    js: 'Code',
    ts: 'Code',
    jsx: 'Code',
    tsx: 'Code',
    vue: 'Code',
    py: 'Code',
    java: 'Code',
    go: 'Code',
    rs: 'Code',
    json: 'JSON',
    html: 'HTML',
    css: 'CSS',
    zip: 'Archive',
    tar: 'Archive',
    gz: 'Archive',
    png: 'Image',
    jpg: 'Image',
    jpeg: 'Image',
    gif: 'Image',
    svg: 'Image',
    webp: 'Image',
  };
  return typeMap[ext] || ext.toUpperCase();
};

const openReport = () => {
  emit('open', props.report);
};

const openFile = (file: FileInfo) => {
  emit('openFile', file);
};

const showAllFiles = () => {
  emit('showAllFiles');
};

const rate = (value: number) => {
  rating.value = value;
  emit('rate', value);
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

const handleConvertToGoogleDocs = () => {
  showMenu.value = false;
  emit('saveToCloud', props.report, 'google-docs');
};

const handleSaveToGoogleDrive = () => {
  showMenu.value = false;
  emit('saveToCloud', props.report, 'google-drive');
};

const handleSaveToOneDrivePersonal = () => {
  showMenu.value = false;
  emit('saveToCloud', props.report, 'onedrive-personal');
};

const handleSaveToOneDriveWork = () => {
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
