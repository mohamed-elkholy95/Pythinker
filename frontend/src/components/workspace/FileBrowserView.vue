<template>
  <div class="file-browser">
    <!-- Header -->
    <div class="browser-header">
      <div class="breadcrumb">
        <FolderOpen :size="16" class="breadcrumb-icon" />
        <span class="breadcrumb-path">{{ currentPath || '/workspace' }}</span>
      </div>
      <div class="header-actions">
        <button class="action-btn" @click="refreshFiles" title="Refresh">
          <RefreshCw :size="14" />
        </button>
      </div>
    </div>

    <!-- File Tree -->
    <div class="file-tree-container">
      <div v-if="loading" class="loading-state">
        <Loader2 :size="20" class="animate-spin" />
        <span>Loading workspace files...</span>
      </div>

      <div v-else-if="error" class="error-state">
        <AlertCircle :size="20" />
        <span>{{ error }}</span>
      </div>

      <div v-else-if="files.length === 0" class="empty-state">
        <Folder :size="32" class="empty-icon" />
        <span class="empty-title">No files yet</span>
        <span class="empty-subtitle">Files created by the agent will appear here</span>
      </div>

      <div v-else class="file-list">
        <!-- Folders first -->
        <div
          v-for="item in sortedFiles.filter(f => f.type === 'directory')"
          :key="item.path"
          class="file-item folder-item"
          @click="handleFolderClick(item)"
        >
          <Folder :size="16" class="file-icon" />
          <span class="file-name">{{ item.name }}</span>
          <ChevronRight :size="14" class="chevron" />
        </div>

        <!-- Then files -->
        <div
          v-for="item in sortedFiles.filter(f => f.type === 'file')"
          :key="item.path"
          class="file-item"
          @click="handleFileClick(item)"
        >
          <component :is="getFileIcon(item.name)" :size="16" class="file-icon" />
          <span class="file-name">{{ item.name }}</span>
          <span class="file-size">{{ formatFileSize(item.size) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  FolderOpen,
  Folder,
  File,
  FileText,
  FileCode,
  FileImage,
  FileJson,
  RefreshCw,
  Loader2,
  AlertCircle,
  ChevronRight,
} from 'lucide-vue-next'

interface FileItem {
  name: string
  path: string
  type: 'file' | 'directory'
  size?: number
  modified?: string
}

const props = defineProps<{
  sessionId?: string
  workspaceRoot?: string
}>()

const emit = defineEmits<{
  (e: 'file-select', file: FileItem): void
}>()

// State
const files = ref<FileItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const currentPath = ref<string>('')

// Computed
const sortedFiles = computed(() => {
  return [...files.value].sort((a, b) => {
    // Directories first, then alphabetical
    if (a.type !== b.type) {
      return a.type === 'directory' ? -1 : 1
    }
    return a.name.localeCompare(b.name)
  })
})

// Methods
function getFileIcon(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase()

  switch (ext) {
    case 'js':
    case 'ts':
    case 'jsx':
    case 'tsx':
    case 'py':
    case 'java':
    case 'cpp':
    case 'c':
    case 'go':
    case 'rs':
      return FileCode
    case 'json':
    case 'yaml':
    case 'yml':
    case 'toml':
      return FileJson
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
    case 'svg':
    case 'webp':
      return FileImage
    case 'md':
    case 'txt':
    case 'log':
      return FileText
    default:
      return File
  }
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

async function loadFiles() {
  if (!props.sessionId) {
    files.value = getMockFiles()
    return
  }

  loading.value = true
  error.value = null

  try {
    // TODO: Implement actual API call to fetch workspace files
    // const response = await fetch(`/api/v1/workspace/sessions/${props.sessionId}/files`)
    // files.value = await response.json()

    // Mock data for now
    await new Promise(resolve => setTimeout(resolve, 500))
    files.value = getMockFiles()
  } catch (err) {
    error.value = 'Failed to load workspace files'
    console.error('Error loading files:', err)
  } finally {
    loading.value = false
  }
}

function getMockFiles(): FileItem[] {
  return [
    { name: 'src', path: '/workspace/src', type: 'directory' },
    { name: 'data', path: '/workspace/data', type: 'directory' },
    { name: 'outputs', path: '/workspace/outputs', type: 'directory' },
    { name: 'main.py', path: '/workspace/main.py', type: 'file', size: 2048 },
    { name: 'config.json', path: '/workspace/config.json', type: 'file', size: 512 },
    { name: 'README.md', path: '/workspace/README.md', type: 'file', size: 1024 },
  ]
}

function handleFolderClick(folder: FileItem) {
  currentPath.value = folder.path
  // TODO: Load folder contents
}

function handleFileClick(file: FileItem) {
  emit('file-select', file)
}

function refreshFiles() {
  loadFiles()
}

// Lifecycle
onMounted(() => {
  loadFiles()
})

watch(() => props.sessionId, () => {
  loadFiles()
})
</script>

<style scoped>
.file-browser {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background-white-main, #ffffff);
  font-family: var(--font-sans);
}

.browser-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-light, #e5e5e5);
  background: var(--background-white-main, #fff);
  flex-shrink: 0;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary, #666);
  font-size: 13px;
  font-weight: 500;
}

.breadcrumb-icon {
  color: var(--icon-tertiary, #999);
}

.breadcrumb-path {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  color: var(--text-primary, #1a1a1a);
}

.header-actions {
  display: flex;
  gap: 4px;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--icon-tertiary, #999);
  cursor: pointer;
  transition: all 0.15s ease;
}

.action-btn:hover {
  background: var(--fill-tsp-gray-main, #f5f5f5);
  border-color: var(--border-light, #e5e5e5);
  color: var(--icon-secondary, #666);
}

.file-tree-container {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 100%;
  color: var(--text-tertiary, #999);
  font-size: 14px;
}

.error-state {
  color: var(--function-error, #ef4444);
}

.empty-icon {
  color: var(--icon-quaternary, #ccc);
  margin-bottom: 8px;
}

.empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary, #666);
}

.empty-subtitle {
  font-size: 13px;
  color: var(--text-tertiary, #999);
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.12s ease;
  font-size: 13px;
}

.file-item:hover {
  background: var(--fill-tsp-gray-main, #f5f5f5);
}

.file-item.folder-item {
  font-weight: 500;
}

.file-icon {
  flex-shrink: 0;
  color: var(--icon-tertiary, #999);
}

.folder-item .file-icon {
  color: var(--function-info, #3b82f6);
}

.file-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary, #1a1a1a);
}

.file-size {
  flex-shrink: 0;
  font-size: 12px;
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  color: var(--text-quaternary, #ccc);
}

.chevron {
  flex-shrink: 0;
  color: var(--icon-quaternary, #ccc);
  opacity: 0;
  transition: opacity 0.12s ease;
}

.folder-item:hover .chevron {
  opacity: 1;
}

/* Scrollbar styling */
.file-tree-container::-webkit-scrollbar {
  width: 8px;
}

.file-tree-container::-webkit-scrollbar-track {
  background: transparent;
}

.file-tree-container::-webkit-scrollbar-thumb {
  background: var(--border-light, #e5e5e5);
  border-radius: 4px;
}

.file-tree-container::-webkit-scrollbar-thumb:hover {
  background: var(--border-hover, #d0d0d0);
}
</style>
