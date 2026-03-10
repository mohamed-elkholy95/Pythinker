<template>
  <div class="browser-chrome">
    <!-- Left: Device toggle (hidden in live view where it has no effect) -->
    <div v-if="showDeviceToggle" class="device-toggle">
      <button
        class="device-btn"
        :class="{ active: device === 'desktop' }"
        title="Desktop view"
        @click="$emit('update:device', 'desktop')"
      >
        <Monitor :size="14" />
      </button>
      <button
        class="device-btn"
        :class="{ active: device === 'mobile' }"
        title="Mobile view"
        @click="$emit('update:device', 'mobile')"
      >
        <Smartphone :size="14" />
      </button>
    </div>

    <!-- Center: URL bar -->
    <div class="url-bar">
      <button class="url-home-btn" title="Home" @click="$emit('navigate-home')">
        <Home :size="13" />
      </button>
      <div class="url-path">
        <span class="url-text">{{ displayUrl }}</span>
      </div>
      <button
        class="url-action-btn"
        title="Open in new tab"
        @click="$emit('open-external')"
      >
        <ExternalLink :size="13" />
      </button>
      <button
        class="url-action-btn"
        title="Refresh"
        @click="$emit('refresh')"
      >
        <RotateCw :size="13" />
      </button>
    </div>

    <!-- Right: Actions -->
    <div class="chrome-actions">
      <button
        v-if="showEdit"
        class="edit-btn"
        @click="$emit('edit')"
      >
        <Sparkles :size="13" />
        <span>Edit</span>
      </button>
      <button
        class="chrome-action-btn"
        :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
        @click="$emit('toggle-fullscreen')"
      >
        <Maximize2 v-if="!isFullscreen" :size="14" />
        <Minimize2 v-else :size="14" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Monitor,
  Smartphone,
  Home,
  ExternalLink,
  RotateCw,
  Sparkles,
  Maximize2,
  Minimize2,
} from 'lucide-vue-next'

export type DeviceMode = 'desktop' | 'mobile'

const props = withDefaults(
  defineProps<{
    /** Current URL or path to display */
    url?: string
    /** Current device preview mode */
    device?: DeviceMode
    /** Whether the panel is in fullscreen mode */
    isFullscreen?: boolean
    /** Whether to show the Edit button */
    showEdit?: boolean
    /** Whether to show the desktop/mobile device toggle */
    showDeviceToggle?: boolean
  }>(),
  {
    url: '/',
    device: 'desktop',
    isFullscreen: false,
    showEdit: false,
    showDeviceToggle: true,
  },
)

defineEmits<{
  (e: 'update:device', device: DeviceMode): void
  (e: 'navigate-home'): void
  (e: 'open-external'): void
  (e: 'refresh'): void
  (e: 'edit'): void
  (e: 'toggle-fullscreen'): void
}>()

const displayUrl = computed(() => {
  if (!props.url) return '/'
  try {
    const u = new URL(props.url)
    return u.pathname + u.search
  } catch {
    return props.url
  }
})
</script>

<style scoped>
.browser-chrome {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 10px;
  background: var(--background-white-main, #ffffff);
  border-bottom: 1px solid var(--border-light, #e5e5e5);
  flex-shrink: 0;
}

/* Device toggle */
.device-toggle {
  display: flex;
  align-items: center;
  gap: 1px;
  padding: 2px;
  background: var(--fill-tsp-gray-main, #f5f5f5);
  border-radius: 8px;
  border: 1px solid var(--border-light, #e5e5e5);
}

.device-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--icon-tertiary, #999);
  cursor: pointer;
  transition: all 0.15s ease;
}

.device-btn:hover {
  color: var(--text-secondary, #666);
}

.device-btn.active {
  background: var(--background-white-main, #fff);
  color: var(--text-primary, #1a1a1a);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

/* URL bar */
.url-bar {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  height: 30px;
  padding: 0 4px;
  background: var(--fill-tsp-gray-main, #f5f5f5);
  border: 1px solid var(--border-light, #e5e5e5);
  border-radius: 10px;
  gap: 2px;
}

.url-home-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--icon-secondary, #666);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s ease;
}

.url-home-btn:hover {
  background: var(--background-white-main, #fff);
  color: var(--text-primary, #1a1a1a);
}

.url-path {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.url-text {
  display: block;
  font-size: 13px;
  color: var(--text-tertiary, #999);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.url-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--icon-tertiary, #999);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s ease;
}

.url-action-btn:hover {
  color: var(--text-secondary, #666);
  background: var(--background-white-main, #fff);
}

/* Chrome actions */
.chrome-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.edit-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 12px;
  border: 1px solid var(--border-light, #e5e5e5);
  border-radius: 10px;
  background: var(--background-white-main, #fff);
  color: var(--text-primary, #1a1a1a);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s ease;
}

.edit-btn:hover {
  border-color: var(--border-hover, #d0d0d0);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.chrome-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--icon-tertiary, #999);
  cursor: pointer;
  transition: all 0.15s ease;
}

.chrome-action-btn:hover {
  color: var(--text-secondary, #666);
  background: var(--fill-tsp-gray-main, #f5f5f5);
}
</style>
