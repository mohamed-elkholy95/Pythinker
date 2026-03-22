<template>
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
import type { SearchResultItem } from '@/types/search'

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
    searchResults?: SearchResultItem[]
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

function processToolEvent(event: ToolEventData): void {
  sandboxViewerRef.value?.processToolEvent(event)
}

defineExpose({
  processToolEvent,
})
</script>

<style scoped>
/* Ensure full coverage */
:deep(.terminal-view),
:deep(.editor-view),
:deep(.search-view) {
  height: 100%;
  width: 100%;
}
</style>
