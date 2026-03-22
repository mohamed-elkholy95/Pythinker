<template>
  <div class="project-sidebar">
    <!-- Card 1: Instructions -->
    <div class="sidebar-card">
      <div class="sidebar-section clickable" @click="$emit('edit-instructions')">
        <div class="sidebar-section-header">
          <span class="sidebar-section-title">Instructions</span>
          <ChevronRight :size="14" class="text-[var(--text-tertiary)]" />
        </div>
        <p class="sidebar-section-desc">
          {{
            project.instructions
              ? truncateText(project.instructions, 80)
              : "Add instructions to tailor Pythinker's responses"
          }}
        </p>
        <div v-if="project.instructions" class="sidebar-char-count">
          {{ project.instructions.length.toLocaleString() }} / 10,000 chars
        </div>
        <button
          class="sidebar-add-btn"
          @click.stop="$emit('edit-instructions')"
        >
          <Plus :size="14" />
          <span>{{ project.instructions ? 'Edit' : 'Add' }}</span>
        </button>
      </div>
    </div>

    <!-- Card 2: Files -->
    <div class="sidebar-card">
      <div class="sidebar-section">
        <div class="sidebar-section-header">
          <span class="sidebar-section-title">Files</span>
          <span v-if="project.file_ids.length > 0" class="sidebar-count-badge">
            {{ project.file_ids.length }}
          </span>
        </div>
        <div v-if="project.file_ids.length > 0" class="sidebar-file-list">
          <div
            v-for="(fid, idx) in project.file_ids"
            :key="fid"
            class="sidebar-file-item"
          >
            <component
              :is="getFileIcon(fileDetails[fid]?.content_type)"
              :size="14"
              class="text-[var(--text-tertiary)] shrink-0"
            />
            <div class="sidebar-file-info">
              <span class="sidebar-file-name">
                {{ fileDetails[fid]?.filename || fid.slice(0, 12) + '...' }}
              </span>
              <span v-if="fileDetails[fid]?.size" class="sidebar-file-size">
                {{ formatFileSize(fileDetails[fid].size) }}
              </span>
            </div>
            <button
              class="sidebar-remove-btn"
              title="Remove"
              @click.stop="$emit('remove-file', idx)"
            >
              <X :size="12" />
            </button>
          </div>
        </div>
        <p v-else class="sidebar-section-desc sidebar-empty-hint">
          No files attached yet.
        </p>
        <button class="sidebar-outline-btn" @click.stop="$emit('upload-file')">
          <Upload :size="14" />
          <span>Upload files</span>
        </button>
      </div>
    </div>

    <!-- Card 3: Skills -->
    <div class="sidebar-card">
      <div class="sidebar-section">
        <div class="sidebar-section-header">
          <span class="sidebar-section-title">Skills</span>
          <span v-if="project.skill_ids.length > 0" class="sidebar-count-badge">
            {{ project.skill_ids.length }}
          </span>
        </div>
        <div v-if="project.skill_ids.length > 0" class="sidebar-skill-list">
          <div
            v-for="(sid, idx) in project.skill_ids"
            :key="sid"
            class="sidebar-skill-item"
          >
            <Sparkles :size="14" class="text-[var(--accent-primary)] shrink-0" />
            <div class="sidebar-skill-info">
              <span class="sidebar-skill-name">
                {{ skillDetails[sid]?.name || sid }}
              </span>
              <span v-if="skillDetails[sid]?.description" class="sidebar-skill-desc">
                {{ truncateText(skillDetails[sid].description, 50) }}
              </span>
            </div>
            <button
              class="sidebar-remove-btn"
              title="Remove"
              @click.stop="$emit('remove-skill', idx)"
            >
              <X :size="12" />
            </button>
          </div>
        </div>
        <p v-else class="sidebar-section-desc sidebar-empty-hint">
          Add skills to enhance Pythinker's know-how.
        </p>
        <button class="sidebar-outline-btn" @click.stop="$emit('add-skills')">
          <Plus :size="14" />
          <span>Add</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Project } from '@/types/project'
import {
  ChevronRight,
  Plus,
  Upload,
  X,
  FileText,
  Image,
  FileCode,
  File,
  Sparkles,
} from 'lucide-vue-next'
import type { Component } from 'vue'

interface FileDetail {
  filename: string
  content_type?: string | null
  size?: number | null
}

interface SkillDetail {
  name: string
  description?: string
}

defineProps<{
  project: Project
  fileDetails: Record<string, FileDetail>
  skillDetails: Record<string, SkillDetail>
}>()

defineEmits<{
  'edit-instructions': []
  'upload-file': []
  'remove-file': [index: number]
  'add-skills': []
  'remove-skill': [index: number]
}>()

function truncateText(text: string, maxLen: number): string {
  return text.length > maxLen ? text.slice(0, maxLen).trimEnd() + '...' : text
}

function formatFileSize(bytes: number | null | undefined): string {
  if (!bytes) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  for (const unit of units) {
    if (size < 1024) return `${Math.round(size)} ${unit}`
    size /= 1024
  }
  return `${size.toFixed(1)} TB`
}

function getFileIcon(contentType?: string | null): Component {
  if (!contentType) return File
  if (contentType.startsWith('image/')) return Image
  if (contentType.includes('pdf') || contentType.includes('document'))
    return FileText
  if (
    contentType.includes('javascript') ||
    contentType.includes('python') ||
    contentType.includes('json') ||
    contentType.includes('text/')
  )
    return FileCode
  return File
}
</script>

<style scoped>
.project-sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 24px;
}

.sidebar-card {
  border-radius: 12px;
  border: 1px solid var(--border-main);
  overflow: hidden;
}

.sidebar-section {
  padding: 16px;
  padding-right: 12px;
}

.sidebar-section.clickable {
  cursor: pointer;
  transition: background 0.15s;
}

.sidebar-section.clickable:hover {
  background: var(--fill-tsp-gray-main);
}

.sidebar-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.sidebar-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.sidebar-count-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  background: var(--fill-tsp-gray-main);
  padding: 1px 6px;
  border-radius: 8px;
}

.sidebar-section-desc {
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-secondary);
  margin: 0 0 10px 0;
}

.sidebar-empty-hint {
  font-style: italic;
  color: var(--text-tertiary);
}

.sidebar-char-count {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}

.sidebar-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: transparent;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.sidebar-add-btn:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-hover, var(--border-main));
}

.sidebar-outline-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: transparent;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.15s;
}

.sidebar-outline-btn:hover {
  background: var(--fill-tsp-gray-main);
}

.sidebar-file-list,
.sidebar-skill-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.sidebar-file-item,
.sidebar-skill-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 6px;
  transition: background 0.15s;
}

.sidebar-file-item:hover,
.sidebar-skill-item:hover {
  background: var(--fill-tsp-gray-main);
}

.sidebar-file-info,
.sidebar-skill-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.sidebar-file-name,
.sidebar-skill-name {
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-file-size {
  font-size: 11px;
  color: var(--text-tertiary);
}

.sidebar-skill-desc {
  font-size: 11px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-remove-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s, background 0.12s;
  flex-shrink: 0;
}

.sidebar-file-item:hover .sidebar-remove-btn,
.sidebar-skill-item:hover .sidebar-remove-btn {
  opacity: 1;
}

.sidebar-remove-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-error, #ef4444);
}

@media (min-width: 768px) {
  .project-sidebar {
    grid-column: 2;
    grid-row: 1 / 4;
    position: sticky;
    top: 160px;
    align-self: start;
    padding-bottom: 32px;
    margin-top: 0;
  }
}
</style>
