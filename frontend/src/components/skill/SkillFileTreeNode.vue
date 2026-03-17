<template>
  <div class="tree-node">
    <!-- Folder -->
    <div
      v-if="isFolder"
      class="node-row folder-row"
      :style="{ paddingLeft: `${depth * 16 + 8}px` }"
      @click="toggleExpand"
    >
      <ChevronRight
        :size="14"
        class="expand-icon"
        :class="{ expanded: isExpanded }"
      />
      <Folder :size="16" class="icon folder-icon" />
      <span class="node-name">{{ name }}</span>
    </div>

    <!-- File -->
    <div
      v-else
      class="node-row file-row"
      :class="{ selected: isSelected }"
      :style="{ paddingLeft: `${depth * 16 + 28}px` }"
      @click="handleClick"
    >
      <component :is="fileIcon" :size="16" class="icon file-icon" />
      <span class="node-name">{{ name }}</span>
    </div>

    <!-- Children (if folder and expanded) -->
    <template v-if="isFolder && isExpanded">
      <SkillFileTreeNode
        v-for="(childItem, childKey) in item"
        :key="childKey"
        :name="String(childKey)"
        :item="childItem"
        :depth="depth + 1"
        :selected-path="selectedPath"
        @select="$emit('select', $event)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  ChevronRight,
  Folder,
  File,
  FileText,
  FileCode,
  FileJson,
} from 'lucide-vue-next'
import type { SkillPackageFileTree } from '@/types/message'

interface Props {
  name: string
  item: SkillPackageFileTree | { type: 'file'; path: string; size: number }
  depth: number
  selectedPath?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'select', path: string): void
}>()

const isExpanded = ref(props.depth < 2) // Auto-expand first 2 levels

const isFolder = computed(() => {
  if (!props.item || typeof props.item !== 'object') return false
  return !('type' in props.item && props.item.type === 'file')
})

const isSelected = computed(() => {
  if (isFolder.value) return false
  const fileItem = props.item as { type: 'file'; path: string; size: number }
  return fileItem.path === props.selectedPath
})

const filePath = computed(() => {
  if (isFolder.value) return ''
  const fileItem = props.item as { type: 'file'; path: string; size: number }
  return fileItem.path
})

// File icon based on extension
const fileIcon = computed(() => {
  const ext = props.name.split('.').pop()?.toLowerCase()
  switch (ext) {
    case 'md':
      return FileText
    case 'py':
    case 'js':
    case 'ts':
    case 'vue':
      return FileCode
    case 'json':
      return FileJson
    default:
      return File
  }
})

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const handleClick = () => {
  if (!isFolder.value) {
    emit('select', filePath.value)
  }
}
</script>

<style scoped>
.tree-node {
  user-select: none;
}

.node-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.node-row:hover {
  background: var(--bolt-elements-bg-depth-3);
}

.folder-row {
  font-weight: 500;
}

.file-row.selected {
  background: var(--bolt-elements-item-backgroundAccent);
}

.file-row.selected .node-name {
  color: var(--bolt-elements-item-contentAccent);
}

.expand-icon {
  flex-shrink: 0;
  color: var(--bolt-elements-textTertiary);
  transition: transform 0.15s ease;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.icon {
  flex-shrink: 0;
}

.folder-icon {
  color: #f59e0b;
}

.file-icon {
  color: var(--bolt-elements-textSecondary);
}

.node-name {
  font-size: 13px;
  color: var(--bolt-elements-textPrimary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
