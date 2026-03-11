<template>
  <div class="browser-chrome browser-chrome--deck">
    <div class="browser-chrome__left">
      <div class="browser-chrome__traffic-lights" aria-hidden="true">
        <span class="browser-chrome__traffic-light browser-chrome__traffic-light--close"></span>
        <span class="browser-chrome__traffic-light browser-chrome__traffic-light--minimize"></span>
        <span class="browser-chrome__traffic-light browser-chrome__traffic-light--expand"></span>
      </div>

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
    </div>

    <!-- Center: URL bar -->
    <div class="url-bar">
      <button class="url-home-btn" title="Home" @click="$emit('navigate-home')">
        <Home :size="13" />
      </button>
      <div class="url-path">
        <span class="browser-chrome__meta-badge">Live</span>
        <span class="url-host">{{ displayHost }}</span>
        <span class="url-divider"></span>
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

const displayHost = computed(() => {
  if (!props.url) return 'workspace'
  try {
    const u = new URL(props.url)
    return u.hostname || 'workspace'
  } catch {
    return 'workspace'
  }
})
</script>

<style scoped>
.browser-chrome {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 52px;
  padding: 10px 14px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--background-menu-white) 88%, transparent), var(--background-menu-white)),
    linear-gradient(90deg, color-mix(in srgb, var(--fill-tsp-white-main) 55%, transparent), transparent 45%);
  border-bottom: 1px solid color-mix(in srgb, var(--border-main) 85%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--border-white) 85%, transparent);
  flex-shrink: 0;
}

.browser-chrome__left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.browser-chrome__traffic-lights {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--fill-tsp-gray-main) 75%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-light) 85%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--border-white) 80%, transparent);
}

.browser-chrome__traffic-light {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.25);
}

.browser-chrome__traffic-light--close {
  background: color-mix(in srgb, var(--function-error) 82%, var(--background-menu-white));
}

.browser-chrome__traffic-light--minimize {
  background: color-mix(in srgb, var(--function-warning) 82%, var(--background-menu-white));
}

.browser-chrome__traffic-light--expand {
  background: color-mix(in srgb, var(--function-success) 82%, var(--background-menu-white));
}

/* Device toggle */
.device-toggle {
  display: flex;
  align-items: center;
  gap: 1px;
  padding: 3px;
  background: color-mix(in srgb, var(--fill-tsp-gray-main) 78%, transparent);
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--border-light) 90%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--border-white) 80%, transparent);
}

.device-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 28px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--icon-tertiary, #999);
  cursor: pointer;
  transition: all 0.2s ease;
}

.device-btn:hover {
  color: var(--text-secondary, #666);
  background: color-mix(in srgb, var(--fill-tsp-white-main) 85%, transparent);
}

.device-btn.active {
  background: color-mix(in srgb, var(--background-menu-white) 92%, transparent);
  color: var(--text-primary, #1a1a1a);
  box-shadow:
    0 6px 18px var(--shadow-XS),
    inset 0 1px 0 color-mix(in srgb, var(--border-white) 80%, transparent);
}

/* URL bar */
.url-bar {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  min-height: 36px;
  padding: 0 6px;
  background: color-mix(in srgb, var(--fill-tsp-gray-main) 82%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-light) 88%, transparent);
  border-radius: 16px;
  gap: 4px;
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--border-white) 85%, transparent);
}

.url-home-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--icon-secondary, #666);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.url-home-btn:hover {
  background: color-mix(in srgb, var(--background-menu-white) 90%, transparent);
  color: var(--text-primary, #1a1a1a);
}

.url-path {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  overflow: hidden;
}

.browser-chrome__meta-badge {
  flex-shrink: 0;
  padding: 4px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--status-running) 14%, transparent);
  color: var(--status-running);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.url-host {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.url-divider {
  flex-shrink: 0;
  width: 1px;
  height: 14px;
  background: color-mix(in srgb, var(--border-main) 72%, transparent);
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
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--icon-tertiary, #999);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.url-action-btn:hover {
  color: var(--text-secondary, #666);
  background: color-mix(in srgb, var(--background-menu-white) 88%, transparent);
}

/* Chrome actions */
.chrome-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.edit-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid color-mix(in srgb, var(--border-light) 88%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--background-menu-white) 92%, transparent);
  color: var(--text-primary, #1a1a1a);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s ease;
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--border-white) 85%, transparent);
}

.edit-btn:hover {
  border-color: var(--border-hover, #d0d0d0);
  box-shadow: 0 6px 18px var(--shadow-XS);
}

.chrome-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--icon-tertiary, #999);
  cursor: pointer;
  transition: all 0.2s ease;
}

.chrome-action-btn:hover {
  color: var(--text-secondary, #666);
  background: color-mix(in srgb, var(--fill-tsp-gray-main) 90%, transparent);
}
</style>
