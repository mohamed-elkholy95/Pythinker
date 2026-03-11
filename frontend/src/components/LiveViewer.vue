<template>
  <div
    class="live-viewer-root"
    :class="liveViewerClasses"
    :data-live-viewer-mode="viewerMode"
    :data-surface-live="isSurfaceLive || undefined"
  >
    <!-- Terminal View -->
    <TerminalContentView
      v-if="currentViewType === 'terminal' && terminalContent"
      :content="terminalContent"
      content-type="shell"
      :is-live="isActive"
      auto-scroll
    />

    <!-- Editor View -->
    <EditorContentView
      v-else-if="currentViewType === 'editor' && editorContent"
      :content="editorContent"
      :file-path="editorFilePath"
      :is-live="isActive"
      content-type="file"
    />

    <!-- Search View -->
    <SearchContentView
      v-else-if="currentViewType === 'search' && searchResults"
      :results="searchResults"
      :query="searchQuery"
      :is-active="isActive"
    />

    <!-- Browser/CDP View (default live preview) -->
    <SandboxViewer
      v-else-if="shouldShowBrowser"
      ref="sandboxViewerRef"
      :key="`cdp-${sessionId}`"
      :session-id="sessionId"
      :enabled="enabled"
      :view-only="viewOnly"
      :quality="quality"
      :max-fps="maxFps"
      :show-stats="showStats"
      :is-canvas-mode="isCanvasMode"
      :show-controls="showControls"
      :is-session-complete="isSessionComplete"
      :replay-screenshot-url="replayScreenshotUrl"
      @connected="emit('connected')"
      @disconnected="(reason?: string) => emit('disconnected', reason)"
      @error="(error: string) => emit('error', error)"
    />

    <!-- Fallback empty state -->
    <InactiveState
      v-else
      message="No content to display"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import SandboxViewer from '@/components/SandboxViewer.vue'
import TerminalContentView from '@/components/toolViews/TerminalContentView.vue'
import EditorContentView from '@/components/toolViews/EditorContentView.vue'
import SearchContentView from '@/components/toolViews/SearchContentView.vue'
import InactiveState from '@/components/toolViews/shared/InactiveState.vue'
import { useContentConfig } from '@/composables/useContentConfig'
import type { ToolEventData } from '@/types/event'
import type { ToolContent } from '@/types/message'

const props = withDefaults(
  defineProps<{
    sessionId?: string
    enabled?: boolean
    viewOnly?: boolean
    quality?: number
    maxFps?: number
    showStats?: boolean
    compactLoading?: boolean
    /** True when viewing canvas/chart content (shows agent action overlay toggle) */
    isCanvasMode?: boolean
    /** Whether to show floating controls (zoom, annotations). Hidden in workspace Live mode. */
    showControls?: boolean
    /** Current tool content for view type detection */
    toolContent?: ToolContent
    /** Whether tool is actively running */
    isActive?: boolean
    /** When true, shows frozen replay screenshot instead of live stream */
    isSessionComplete?: boolean
    /** URL of the final screenshot to show when session is complete */
    replayScreenshotUrl?: string
    /** Terminal output content */
    terminalContent?: string
    /** Editor/file content */
    editorContent?: string
    /** File path for editor */
    editorFilePath?: string
    /** Search results */
    searchResults?: Array<{ title?: string; name?: string; url?: string; link?: string; snippet?: string }>
    /** Search query */
    searchQuery?: string
  }>(),
  {
    sessionId: '',
    enabled: true,
    viewOnly: true,
    quality: 70,
    maxFps: 15,
    showStats: false,
    compactLoading: false,
    isCanvasMode: false,
    showControls: true,
    toolContent: undefined,
    isActive: false,
    terminalContent: '',
    editorContent: '',
    editorFilePath: '',
    searchResults: () => [],
    searchQuery: '',
    isSessionComplete: false,
    replayScreenshotUrl: ''
  }
)

const emit = defineEmits<{
  connected: []
  disconnected: [reason?: string]
  error: [error: string]
  credentialsRequired: []
}>()

const sandboxViewerRef = ref<InstanceType<typeof SandboxViewer> | null>(null)

// Use content config to determine view type
const { currentViewType } = useContentConfig(toRef(() => props.toolContent))

// Determine when to show browser view
const shouldShowBrowser = computed(() => {
  // Show browser for live_preview type or when no specific view type is determined
  if (!currentViewType.value || currentViewType.value === 'live_preview') {
    return props.enabled && props.sessionId
  }

  // For chart type, show browser if canvas mode is enabled
  if (currentViewType.value === 'chart') {
    return props.enabled && props.sessionId && props.isCanvasMode
  }

  // For other types with no content, fall back to browser if active
  if (currentViewType.value === 'terminal' && !props.terminalContent && props.isActive) {
    return props.enabled && props.sessionId
  }

  if (currentViewType.value === 'editor' && !props.editorContent && props.isActive) {
    return props.enabled && props.sessionId
  }

  return false
})

const viewerMode = computed(() => {
  if (currentViewType.value === 'terminal' && props.terminalContent) return 'terminal'
  if (currentViewType.value === 'editor' && props.editorContent) return 'editor'
  if (currentViewType.value === 'search' && props.searchResults?.length) return 'search'
  if (shouldShowBrowser.value) return 'browser'
  return 'empty'
})

/** True when a terminal/editor content view is actively streaming — used for CSS surface decorations. */
const isSurfaceLive = computed(() => {
  const isContentView = viewerMode.value === 'terminal' || viewerMode.value === 'editor'
  return isContentView && !!props.isActive
})

const liveViewerClasses = computed(() => ({
  'live-viewer-root--active': !!props.isActive,
  'live-viewer-root--terminal': viewerMode.value === 'terminal',
  'live-viewer-root--editor': viewerMode.value === 'editor',
  'live-viewer-root--search': viewerMode.value === 'search',
  'live-viewer-root--browser': viewerMode.value === 'browser',
  'live-viewer-root--empty': viewerMode.value === 'empty',
}))

function processToolEvent(event: ToolEventData): void {
  sandboxViewerRef.value?.processToolEvent(event)
}

defineExpose({
  processToolEvent,
})
</script>

<style scoped>
.live-viewer-root {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, color-mix(in srgb, var(--fill-tsp-white-dark) 72%, transparent), transparent 48%),
    linear-gradient(180deg, color-mix(in srgb, var(--background-menu-white) 96%, transparent), var(--background-menu-white));
}

.live-viewer-root::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--border-white) 80%, transparent), transparent 22%),
    radial-gradient(circle at top right, color-mix(in srgb, var(--fill-tsp-white-main) 70%, transparent), transparent 34%);
  opacity: 0.95;
  z-index: 0;
}

.live-viewer-root > * {
  position: relative;
  z-index: 1;
}

.live-viewer-root--terminal,
.live-viewer-root--editor {
  background:
    radial-gradient(circle at top left, color-mix(in srgb, var(--fill-tsp-white-dark) 90%, transparent), transparent 42%),
    linear-gradient(180deg, color-mix(in srgb, var(--background-menu-white) 82%, var(--background-main)), var(--background-menu-white));
}

.live-viewer-root--browser {
  background:
    radial-gradient(circle at top center, color-mix(in srgb, var(--fill-tsp-white-main) 80%, transparent), transparent 38%),
    linear-gradient(180deg, color-mix(in srgb, var(--background-menu-white) 88%, var(--background-main)), var(--background-menu-white));
}

/* Active surface decoration — subtle live indicator for terminal/editor */
.live-viewer-root[data-surface-live="true"]::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 2;
  border: 1.5px solid color-mix(in srgb, var(--status-running) 22%, transparent);
  border-radius: inherit;
  animation: surface-live-pulse 2.5s ease-in-out infinite;
}

@keyframes surface-live-pulse {
  0%, 100% {
    border-color: color-mix(in srgb, var(--status-running) 22%, transparent);
  }
  50% {
    border-color: color-mix(in srgb, var(--status-running) 38%, transparent);
  }
}

/* Ensure full coverage */
:deep(.terminal-view),
:deep(.editor-view),
:deep(.search-view) {
  height: 100%;
  width: 100%;
}
</style>
