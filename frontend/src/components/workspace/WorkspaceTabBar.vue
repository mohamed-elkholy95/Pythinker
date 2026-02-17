<template>
  <div class="workspace-tab-bar">
    <!-- Left: Workspace mode tabs -->
    <div class="tab-group">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="tab-btn"
        :class="{ active: modelValue === tab.id }"
        :title="tab.label"
        @click="$emit('update:modelValue', tab.id)"
      >
        <component :is="tab.icon" :size="16" />
        <span v-if="modelValue === tab.id" class="tab-label">{{ tab.label }}</span>
        <!-- Notification dot -->
        <span v-if="tab.hasNotification" class="notification-dot" />
      </button>
    </div>

    <!-- Right: Action buttons -->
    <div class="action-group">
      <button
        v-if="showMore"
        class="action-btn"
        title="More options"
        @click="$emit('more')"
      >
        <MoreHorizontal :size="16" />
      </button>
      <button
        v-if="showShare"
        class="action-btn share-btn"
        @click="$emit('share')"
      >
        <ExternalLink :size="14" />
        <span>Share</span>
      </button>
      <button
        class="action-btn close-btn"
        title="Close panel"
        @click="$emit('close')"
      >
        <X :size="16" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Monitor,
  FileText,
  TerminalSquare,
  Palette,
  FolderOpen,
  Settings,
  MoreHorizontal,
  ExternalLink,
  X,
} from 'lucide-vue-next'
import type { Component } from 'vue'

export type WorkspaceTab = 'preview' | 'editor' | 'console' | 'canvas' | 'files' | 'settings'

interface TabDefinition {
  id: WorkspaceTab
  label: string
  icon: Component
  hasNotification: boolean
}

const props = withDefaults(
  defineProps<{
    modelValue: WorkspaceTab
    showMore?: boolean
    showShare?: boolean
    /** Which tabs have new unread content */
    notifications?: WorkspaceTab[]
  }>(),
  {
    showMore: false,
    showShare: false,
    notifications: () => [],
  },
)

defineEmits<{
  (e: 'update:modelValue', tab: WorkspaceTab): void
  (e: 'more'): void
  (e: 'share'): void
  (e: 'close'): void
}>()

const tabs = computed<TabDefinition[]>(() => [
  { id: 'preview', label: 'Live', icon: Monitor, hasNotification: props.notifications.includes('preview') },
  { id: 'editor', label: 'Editor', icon: FileText, hasNotification: props.notifications.includes('editor') },
  { id: 'console', label: 'Console', icon: TerminalSquare, hasNotification: props.notifications.includes('console') },
  { id: 'canvas', label: 'Canvas', icon: Palette, hasNotification: props.notifications.includes('canvas') },
  { id: 'files', label: 'Files', icon: FolderOpen, hasNotification: props.notifications.includes('files') },
  { id: 'settings', label: 'Settings', icon: Settings, hasNotification: false },
])
</script>

<style scoped>
.workspace-tab-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 44px;
  padding: 0 12px;
  border-bottom: 1px solid var(--border-light, #e5e5e5);
  background: var(--background-white-main, #ffffff);
  flex-shrink: 0;
}

.tab-group {
  display: flex;
  align-items: center;
  gap: 2px;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--icon-tertiary, #999);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s ease;
  position: relative;
}

.tab-btn:hover {
  color: var(--text-secondary, #666);
  background: var(--fill-tsp-gray-main, #f5f5f5);
}

.tab-btn.active {
  color: var(--text-primary, #1a1a1a);
  background: var(--background-white-main, #fff);
  border-color: var(--border-light, #e5e5e5);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.tab-label {
  white-space: nowrap;
}

.notification-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--function-info, #3b82f6);
}

.action-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 30px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--icon-tertiary, #999);
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.15s ease;
}

.action-btn:hover {
  color: var(--text-secondary, #666);
  background: var(--fill-tsp-gray-main, #f5f5f5);
}

.share-btn {
  border-color: var(--border-light, #e5e5e5);
  color: var(--text-secondary, #666);
}

.share-btn:hover {
  border-color: var(--border-hover, #d0d0d0);
}

.close-btn:hover {
  color: var(--text-primary, #1a1a1a);
}
</style>
