<template>
  <div class="panel">
    <div class="panel-header">
      <div class="panel-header-left">
        <span class="panel-title">Files</span>
        <ChevronRight :size="16" class="panel-chevron" />
      </div>
    </div>
    <p class="panel-description">Start by attaching files to your project.</p>
    <div v-if="files.length > 0" class="panel-items">
      <div v-for="file in files.slice(0, 3)" :key="file.file_id" class="panel-item">
        <FileText :size="12" class="panel-item-icon" />
        <span class="panel-item-name">{{ file.filename }}</span>
      </div>
      <span v-if="files.length > 3" class="panel-more">+{{ files.length - 3 }} more</span>
    </div>
    <button class="panel-upload-btn" type="button" @click="triggerUpload">
      <Upload :size="14" />
      <span>Upload files</span>
    </button>
    <input
      ref="fileInputRef"
      type="file"
      multiple
      class="hidden"
      @change="handleFileSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ChevronRight, FileText, Upload } from 'lucide-vue-next'
import { uploadFile } from '@/api/file'
import type { FileInfo } from '@/api/file'

const files = ref<FileInfo[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

function triggerUpload() {
  fileInputRef.value?.click()
}

async function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return

  for (const file of Array.from(input.files)) {
    try {
      const uploaded = await uploadFile(file)
      files.value.push(uploaded)
    } catch {
      // TODO: toast notification on upload failure
    }
  }

  // Reset input so same file can be re-selected
  input.value = ''
}
</script>

<style scoped>
.panel {
  border-radius: 12px;
  border: 1px solid var(--border-light);
  padding: 16px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.panel-header-left {
  display: flex;
  align-items: center;
  gap: 4px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.panel-chevron {
  color: var(--text-tertiary);
}

.panel-description {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0 0 12px;
  line-height: 1.5;
}

.panel-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.panel-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.panel-item-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.panel-item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-more {
  font-size: 12px;
  color: var(--text-tertiary);
}

.panel-upload-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  background: transparent;
  border: 1px solid var(--border-light);
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 8px;
  transition: all 0.15s ease;
}

.panel-upload-btn:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-main);
}
</style>
