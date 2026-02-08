<template>
  <div class="canvas-mini-preview">
    <div class="preview-header">
      <Palette :size="16" class="text-[var(--icon-secondary)]" />
      <span class="preview-title">{{ projectName || 'Canvas Project' }}</span>
    </div>
    <div class="preview-body">
      <div class="preview-info">
        <span class="preview-operation">{{ operationLabel }}</span>
        <span v-if="elementCount > 0" class="preview-count">{{ elementCount }} element{{ elementCount !== 1 ? 's' : '' }}</span>
      </div>
      <router-link
        v-if="projectId"
        :to="`/chat/canvas/${projectId}`"
        class="preview-link"
      >
        Open in Editor
        <ExternalLink :size="12" />
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Palette, ExternalLink } from 'lucide-vue-next'

const props = defineProps<{
  projectId?: string | null
  projectName?: string | null
  operation?: string
  elementCount?: number
}>()

const operationLabel = computed(() => {
  const opMap: Record<string, string> = {
    canvas_create_project: 'Creating project',
    canvas_add_element: 'Adding element',
    canvas_modify_element: 'Modifying element',
    canvas_delete_elements: 'Deleting elements',
    canvas_generate_image: 'Generating image',
    canvas_arrange_layer: 'Arranging layers',
    canvas_export: 'Exporting',
    canvas_get_state: 'Reading state',
  }
  if (!props.operation) return 'Working on canvas'
  const normalized = props.operation.startsWith('canvas_')
    ? props.operation
    : `canvas_${props.operation}`
  return opMap[normalized] || props.operation
})
</script>

<style scoped>
.canvas-mini-preview {
  padding: 12px;
  border-radius: 10px;
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
}
.preview-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.preview-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.preview-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.preview-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.preview-operation {
  font-size: 12px;
  color: var(--text-secondary);
}
.preview-count {
  font-size: 11px;
  color: var(--text-tertiary);
}
.preview-link {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-link, #3b82f6);
  text-decoration: none;
}
.preview-link:hover {
  text-decoration: underline;
}
</style>
