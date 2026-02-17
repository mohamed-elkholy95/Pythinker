<script setup lang="ts">
import { computed } from 'vue'
import {
  Monitor,
  Palette,
  FolderOpen,
  MoreHorizontal,
  ExternalLink,
  X,
} from 'lucide-vue-next'
import type { Component } from 'vue'

export type WorkspaceMode = 'live' | 'canvas' | 'files'

interface TabDefinition {
  id: WorkspaceMode
  label: string
  icon: Component
  hasNotification: boolean
}

const props = withDefaults(
  defineProps<{
    modelValue: WorkspaceMode
    showMore?: boolean
    showShare?: boolean
    /** Which modes have new unread content */
    notifications?: WorkspaceMode[]
  }>(),
  {
    showMore: false,
    showShare: false,
    notifications: () => [],
  },
)

defineEmits<{
  (e: 'update:modelValue', tab: WorkspaceMode): void
  (e: 'more'): void
  (e: 'share'): void
  (e: 'close'): void
}>()

const tabs = computed<TabDefinition[]>(() => [
  { id: 'live', label: 'Live', icon: Monitor, hasNotification: props.notifications.includes('live') },
  { id: 'canvas', label: 'Canvas', icon: Palette, hasNotification: props.notifications.includes('canvas') },
  { id: 'files', label: 'Files', icon: FolderOpen, hasNotification: props.notifications.includes('files') },
])
</script>

<template>
  <div class="workspace-tab-bar">
    <!-- Left: Segmented mode switcher -->
    <div class="mode-switcher">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="mode-btn"
        :class="{ active: modelValue === tab.id }"
        :title="tab.label"
        @click="$emit('update:modelValue', tab.id)"
      >
        <component :is="tab.icon" :size="14" :stroke-width="modelValue === tab.id ? 2 : 1.5" />
        <span class="mode-label">{{ tab.label }}</span>
        <!-- Notification pulse -->
        <span v-if="tab.hasNotification" class="notification-pulse" />
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
        <MoreHorizontal :size="15" />
      </button>
      <button
        v-if="showShare"
        class="action-btn share-btn"
        @click="$emit('share')"
      >
        <ExternalLink :size="13" />
        <span>Share</span>
      </button>
      <button
        class="action-btn close-btn"
        title="Close panel"
        @click="$emit('close')"
      >
        <X :size="15" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.workspace-tab-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 10px 0 12px;
  background: var(--background-white-main);
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-light);
}

/* ─── Segmented mode switcher ─── */
.mode-switcher {
  display: flex;
  align-items: center;
  gap: 1px;
  padding: 3px;
  border-radius: 10px;
  background: var(--fill-tsp-gray-main);
}

.mode-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 12px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0.01em;
  transition:
    color 0.18s ease,
    background 0.18s ease,
    box-shadow 0.18s ease;
  position: relative;
  white-space: nowrap;
  -webkit-user-select: none;
  user-select: none;
}

.mode-btn:hover:not(.active) {
  color: var(--text-secondary);
}

.mode-btn.active {
  color: var(--text-primary);
  background: var(--background-white-main);
  box-shadow:
    0 1px 3px var(--shadow-XS),
    0 0 0 0.5px var(--border-light);
}

.mode-label {
  line-height: 1;
}

/* ─── Notification pulse ─── */
.notification-pulse {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--function-info);
  box-shadow: 0 0 0 2px var(--fill-tsp-gray-main);
  animation: pulse-ring 2s ease-in-out infinite;
}

@keyframes pulse-ring {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ─── Action buttons ─── */
.action-group {
  display: flex;
  align-items: center;
  gap: 2px;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 28px;
  padding: 0 7px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--icon-tertiary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition:
    color 0.15s ease,
    background 0.15s ease;
}

.action-btn:hover {
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-main);
}

.share-btn {
  padding: 0 10px;
  border: 1px solid var(--border-light);
  color: var(--text-secondary);
  border-radius: 7px;
}

.share-btn:hover {
  border-color: var(--border-hover);
  background: var(--fill-tsp-gray-main);
}

.close-btn:hover {
  color: var(--text-primary);
}
</style>
