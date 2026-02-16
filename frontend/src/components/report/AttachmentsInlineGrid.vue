<template>
  <div class="attachments-inline-grid w-full max-w-[280px] min-w-0 mt-3">
    <div class="grid grid-cols-1 gap-2">
      <template v-for="file in displayedAttachments" :key="file.file_id">
        <!-- Chart PNG files: render inline image preview -->
        <div
          v-if="isChartPng(file)"
          class="col-span-1 chart-preview-card relative rounded-md overflow-hidden border border-[var(--border-light)] cursor-pointer hover:border-[var(--border-brand)] hover:shadow-sm transition-all group"
          role="button"
          tabindex="0"
          :aria-label="`Open interactive chart: ${file.filename}`"
          @click="openChartInteractive(file)"
          @keydown.enter="openChartInteractive(file)"
          @keydown.space.prevent="openChartInteractive(file)"
        >
          <img
            :src="getFileUrl(file)"
            :alt="file.filename"
            class="w-full h-auto max-h-[220px] object-contain bg-white dark:bg-[var(--code-block-bg)]"
          />
          <div class="absolute inset-0 bg-black/0 group-hover:bg-black/5 group-focus:bg-black/5 transition-colors flex items-center justify-center">
            <div class="opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-blue-600 dark:bg-blue-500 text-white shadow-md">
              <BarChart3 :size="13" />
              <span class="text-xs font-medium">View Interactive</span>
            </div>
          </div>
        </div>

        <!-- Regular files: standard file card -->
        <div
          v-else
          class="file-card flex items-center gap-3 px-3 py-2.5 rounded-xl bg-[var(--background-card)] border border-[var(--border-light)] cursor-pointer hover:border-[var(--border-main)] hover:shadow-sm transition-all"
          @click="openFile(file)"
        >
          <div
            class="flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center"
            :class="getFileIconBgClass(file.filename)"
          >
            <component :is="getFileIcon(file.filename)" class="w-4 h-4 text-white" />
          </div>
          <div class="flex flex-col min-w-0 flex-1">
            <span class="text-sm text-[var(--text-primary)] truncate font-medium leading-tight">
              {{ file.filename }}
            </span>
            <span class="text-xs text-[var(--text-tertiary)]">
              {{ getFileTypeLabel(file.filename) }} · {{ formatFileSize(file.size) }}
            </span>
          </div>
        </div>
      </template>

      <!-- View all files button - inline in grid -->
      <button
        v-if="uniqueAttachments.length > maxDisplayedFiles"
        class="file-card flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-[var(--background-card)] border border-[var(--border-light)] cursor-pointer hover:border-[var(--border-main)] hover:shadow-sm transition-all"
        @click="showAllFiles"
      >
        <FolderOpen class="w-4 h-4 text-[var(--icon-secondary)]" />
        <span class="text-sm text-[var(--text-secondary)]">
          View all files in this task
        </span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import {
  FileText,
  FileCode,
  FileArchive,
  FileImage,
  File,
  FolderOpen,
  BarChart3,
} from 'lucide-vue-next';
import type { FileInfo } from '@/api/file';
import { fileApi } from '@/api/file';
import { isChartPngFile, getChartHtmlFile } from '@/utils/fileType';

const props = defineProps<{
  attachments: FileInfo[];
  maxDisplayedFiles?: number;
}>();

const emit = defineEmits<{
  (e: 'openFile', file: FileInfo): void;
  (e: 'showAllFiles'): void;
}>();

const maxDisplayedFiles = props.maxDisplayedFiles ?? 4;

// Deduplicate attachments by filename (preferred) or file_id to prevent showing duplicates
// Prefer filename because the same file synced multiple times may have different file_ids
const uniqueAttachments = computed(() => {
  const seenFilenames = new Set<string>();
  const seenFileIds = new Set<string>();
  return props.attachments.filter(file => {
    // Primary dedup by filename
    if (file.filename) {
      if (seenFilenames.has(file.filename)) return false;
      seenFilenames.add(file.filename);
      return true;
    }
    // Fallback to file_id if no filename
    if (file.file_id) {
      if (seenFileIds.has(file.file_id)) return false;
      seenFileIds.add(file.file_id);
      return true;
    }
    return true; // Keep if neither exists
  });
});

const displayedAttachments = computed(() => {
  if (uniqueAttachments.value.length > maxDisplayedFiles) {
    return uniqueAttachments.value.slice(0, maxDisplayedFiles - 1);
  }
  return uniqueAttachments.value.slice(0, maxDisplayedFiles);
});

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
  // Markdown/Document files - blue
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

const openFile = (file: FileInfo) => {
  emit('openFile', file);
};

const showAllFiles = () => {
  emit('showAllFiles');
};

// Chart detection and handling
const isChartPng = (file: FileInfo) => {
  return isChartPngFile(file.filename, file.metadata);
};

const getFileUrl = (file: FileInfo) => {
  return fileApi.getFileUrl(file.file_id);
};

const openChartInteractive = (pngFile: FileInfo) => {
  // Find corresponding HTML file
  const htmlFile = getChartHtmlFile(pngFile, props.attachments);
  if (htmlFile) {
    // Open HTML file in new tab
    const url = fileApi.getFileUrl(htmlFile.file_id);
    window.open(url, '_blank');
  } else {
    // Fallback: open PNG file normally
    emit('openFile', pngFile);
  }
};
</script>

<style scoped>
.file-card {
  min-height: 52px;
}
</style>
