<template>
  <div class="attachments-inline-grid w-full max-w-[520px] min-w-0 mt-3 flex flex-col gap-2">

    <!-- Section 1: Charts / images — up to 2, side-by-side -->
    <div
      v-if="displayedChartFiles.length > 0"
      class="grid gap-2"
      :class="displayedChartFiles.length === 1 ? 'grid-cols-1' : 'grid-cols-2'"
    >
      <div
        v-for="file in displayedChartFiles"
        :key="file.file_id"
        class="chart-preview-card relative rounded-xl overflow-hidden border border-[var(--border-light)] cursor-pointer hover:border-[var(--border-brand)] hover:shadow-sm transition-all group"
        role="button"
        tabindex="0"
        :aria-label="isChartPng(file) ? `Open interactive chart: ${file.filename}` : file.filename"
        @click="isChartPng(file) ? openChartInteractive(file) : openFile(file)"
        @keydown.enter="isChartPng(file) ? openChartInteractive(file) : openFile(file)"
        @keydown.space.prevent="isChartPng(file) ? openChartInteractive(file) : openFile(file)"
      >
        <img
          :src="getFileUrl(file)"
          :alt="file.filename"
          class="w-full h-auto max-h-[220px] object-contain bg-white dark:bg-[var(--code-block-bg)]"
        />
        <!-- "View Interactive" badge — only for chart PNGs that have a paired HTML -->
        <div
          v-if="isChartPng(file)"
          class="absolute inset-0 bg-black/0 group-hover:bg-black/5 group-focus:bg-black/5 transition-colors flex items-center justify-center"
        >
          <div class="opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-blue-600 dark:bg-blue-500 text-white shadow-md">
            <BarChart3 :size="13" />
            <span class="text-xs font-medium">View Interactive</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Section 2: Regular files — up to 2, side-by-side -->
    <div
      v-if="displayedRegularFiles.length > 0"
      class="grid gap-2"
      :class="displayedRegularFiles.length === 1 ? 'grid-cols-1' : 'grid-cols-2'"
    >
      <div
        v-for="file in displayedRegularFiles"
        :key="file.file_id"
        class="file-card flex items-center gap-3 px-3 py-2.5 rounded-xl bg-[var(--background-card)] border border-[var(--border-light)] cursor-pointer hover:border-[var(--border-main)] hover:shadow-sm transition-all min-w-0"
        @click="openFile(file)"
      >
        <div class="flex-shrink-0 w-9 h-9 flex items-center justify-center">
          <FileTypeIcon :filename="file.filename" :size="36" />
        </div>
        <div class="flex flex-col min-w-0 flex-1">
          <span class="text-sm text-[var(--text-primary)] truncate font-medium leading-tight" :title="file.filename">
            {{ file.filename }}
          </span>
          <span class="text-xs text-[var(--text-tertiary)]">
            {{ getFileTypeLabel(file.filename) }} · {{ formatFileSize(file.size) }}
          </span>
        </div>
      </div>
    </div>

    <!-- Section 3: View all files — shown when there are more files than displayed -->
    <button
      v-if="hasMoreFiles"
      class="file-card w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-[var(--background-card)] border border-[var(--border-light)] cursor-pointer hover:border-[var(--border-main)] hover:shadow-sm transition-all"
      @click="showAllFiles"
    >
      <FolderOpen class="w-4 h-4 text-[var(--icon-secondary)]" />
      <span class="text-sm text-[var(--text-secondary)]">{{ $t('View all files in this task') }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FolderOpen, BarChart3 } from 'lucide-vue-next'
import type { FileInfo } from '@/api/file'
import { fileApi } from '@/api/file'
import { isChartPngFile, isInteractiveChartFile, getChartHtmlFile } from '@/utils/fileType'
import FileTypeIcon from '@/components/FileTypeIcon.vue'

const MAX_REGULAR_FILES = 4

const props = defineProps<{
  attachments: FileInfo[]
  maxDisplayedFiles?: number
}>()

const emit = defineEmits<{
  (e: 'openFile', file: FileInfo): void
  (e: 'showAllFiles'): void
}>()

// Deduplicate by filename first, file_id as fallback
const uniqueAttachments = computed(() => {
  const seenFilenames = new Set<string>()
  const seenFileIds = new Set<string>()
  return props.attachments.filter(file => {
    if (file.filename) {
      if (seenFilenames.has(file.filename)) return false
      seenFilenames.add(file.filename)
      return true
    }
    if (file.file_id) {
      if (seenFileIds.has(file.file_id)) return false
      seenFileIds.add(file.file_id)
      return true
    }
    return true
  })
})

const IMAGE_EXTS = new Set([
  'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'ico', 'tiff', 'tif', 'heic', 'heif',
])

const isImageFile = (f: FileInfo) => {
  const ext = f.filename.split('.').pop()?.toLowerCase() ?? ''
  return IMAGE_EXTS.has(ext)
}

// Visual files (charts + images) — shown as inline previews
const chartFiles = computed(() =>
  uniqueAttachments.value.filter(f => isChartPngFile(f.filename, f.metadata) || isImageFile(f))
)

// Regular files — exclude visuals and their paired interactive HTML counterparts
const regularFiles = computed(() => {
  const chartHtmlFilenames = new Set(
    uniqueAttachments.value
      .filter(f => isChartPngFile(f.filename, f.metadata))
      .map(png => getChartHtmlFile(png, uniqueAttachments.value))
      .filter(Boolean)
      .map(f => f!.filename)
  )
  return uniqueAttachments.value.filter(
    f => !isChartPngFile(f.filename, f.metadata) &&
         !isImageFile(f) &&
         !isInteractiveChartFile(f.metadata) &&
         !chartHtmlFilenames.has(f.filename)
  )
})

const MAX_VISUAL_FILES = 4

// Only show first 2 visual files inline
const displayedChartFiles = computed(() =>
  chartFiles.value.slice(0, MAX_VISUAL_FILES)
)

// Only show first 2 regular files inline
const displayedRegularFiles = computed(() =>
  regularFiles.value.slice(0, MAX_REGULAR_FILES)
)

// Show "View all files" when any section is truncated
const hasMoreFiles = computed(() =>
  regularFiles.value.length > MAX_REGULAR_FILES ||
  chartFiles.value.length > MAX_VISUAL_FILES
)

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const getFileTypeLabel = (filename: string) => {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const typeMap: Record<string, string> = {
    md: 'Markdown', txt: 'Text', pdf: 'PDF',
    doc: 'Document', docx: 'Document',
    js: 'Code', ts: 'Code', jsx: 'Code', tsx: 'Code', vue: 'Code',
    py: 'Code', java: 'Code', go: 'Code', rs: 'Code',
    json: 'JSON', html: 'HTML', css: 'CSS',
    zip: 'Archive', tar: 'Archive', gz: 'Archive',
    png: 'Image', jpg: 'Image', jpeg: 'Image',
    gif: 'Image', svg: 'Image', webp: 'Image',
    xls: 'Spreadsheet', xlsx: 'Spreadsheet', csv: 'Spreadsheet',
  }
  return typeMap[ext] || ext.toUpperCase()
}

const openFile = (file: FileInfo) => emit('openFile', file)
const showAllFiles = () => emit('showAllFiles')

const isChartPng = (file: FileInfo) => isChartPngFile(file.filename, file.metadata)

const getFileUrl = (file: FileInfo) => fileApi.getFileUrl(file.file_id)

const openChartInteractive = (pngFile: FileInfo) => {
  const htmlFile = getChartHtmlFile(pngFile, props.attachments)
  if (htmlFile) {
    emit('openFile', htmlFile)
  } else {
    emit('openFile', pngFile)
  }
}
</script>

<style scoped>
.file-card {
  min-height: 52px;
}
</style>
