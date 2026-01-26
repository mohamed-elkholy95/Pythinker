<template>
  <div class="attachments-inline-grid w-full max-w-[600px] min-w-0 mt-3">
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
      <div
        v-for="file in displayedAttachments"
        :key="file.file_id"
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

      <!-- View all files button - inline in grid -->
      <button
        v-if="attachments.length > maxDisplayedFiles"
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
} from 'lucide-vue-next';
import type { FileInfo } from '@/api/file';

const props = defineProps<{
  attachments: FileInfo[];
  maxDisplayedFiles?: number;
}>();

const emit = defineEmits<{
  (e: 'openFile', file: FileInfo): void;
  (e: 'showAllFiles'): void;
}>();

const maxDisplayedFiles = props.maxDisplayedFiles ?? 4;

const displayedAttachments = computed(() => {
  if (props.attachments.length > maxDisplayedFiles) {
    return props.attachments.slice(0, maxDisplayedFiles - 1);
  }
  return props.attachments.slice(0, maxDisplayedFiles);
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
</script>

<style scoped>
.file-card {
  min-height: 52px;
}
</style>
