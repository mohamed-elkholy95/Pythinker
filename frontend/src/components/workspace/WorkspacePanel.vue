<template>
  <div
    class="workspace-panel bg-[var(--background-white-main)] sm:bg-[var(--background-white-main)] sm:rounded-[20px] shadow-[0px_10px_30px_rgba(15,23,42,0.08)] border border-[var(--border-light)] flex flex-col h-full w-full overflow-hidden"
  >
    <!-- Workspace Tab Bar -->
    <WorkspaceTabBar
      :model-value="activeTab"
      :notifications="tabNotifications"
      @update:model-value="onTabChange"
      @close="emit('hide')"
    />

    <!-- Browser Chrome (Canvas mode only) -->
    <BrowserChrome
      v-if="activeTab === 'canvas' && !isChartDomainTool(toolContent)"
      :url="browserUrl"
      :device="deviceMode"
      :is-fullscreen="isFullscreen"
      @update:device="deviceMode = $event"
      @navigate-home="navigateHome"
      @open-external="openExternal"
      @refresh="refreshBrowser"
      @toggle-fullscreen="isFullscreen = !isFullscreen"
    />

    <!-- Embedded Content Panel -->
    <ToolPanelContent
      :embedded="true"
      :force-view-type="forceViewType"
      :session-id="sessionId"
      :real-time="realTime"
      :tool-content="toolContent"
      :live="live"
      :is-share="isShare"
      :show-timeline="showTimeline"
      :timeline-progress="timelineProgress"
      :timeline-timestamp="timelineTimestamp"
      :timeline-can-step-forward="timelineCanStepForward"
      :timeline-can-step-backward="timelineCanStepBackward"
      :plan="plan"
      :is-loading="isLoading"
      :is-thinking="isThinking"
      :is-replay-mode="isReplayMode"
      :replay-screenshot-url="replayScreenshotUrl"
      :replay-metadata="replayMetadata"
      :replay-screenshots="replayScreenshots"
      :summary-stream-text="summaryStreamText"
      :is-summary-streaming="isSummaryStreaming"
      @hide="emit('hide')"
      @jump-to-real-time="emit('jumpToRealTime')"
      @step-forward="emit('stepForward')"
      @step-backward="emit('stepBackward')"
      @seek-by-progress="(p: number) => emit('seekByProgress', p)"
      class="flex-1 min-h-0"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import WorkspaceTabBar from './WorkspaceTabBar.vue'
import BrowserChrome from './BrowserChrome.vue'
import ToolPanelContent from '../ToolPanelContent.vue'
import type { WorkspaceTab } from './WorkspaceTabBar.vue'
import type { DeviceMode } from './BrowserChrome.vue'
import type { ToolContent } from '@/types/message'
import type { PlanEventData } from '@/types/event'
import type { ScreenshotMetadata } from '@/types/screenshot'
import type { ContentViewType } from '@/constants/tool'
import { isCanvasDomainTool, isChartDomainTool, isLiveDomainTool } from '@/utils/viewRouting'

// ---------------------------------------------------------------------------
// Props & Emits (same interface as ToolPanelContent for drop-in replacement)
// ---------------------------------------------------------------------------

const props = defineProps<{
  sessionId?: string
  realTime: boolean
  toolContent: ToolContent
  live: boolean
  isShare: boolean
  showTimeline?: boolean
  timelineProgress?: number
  timelineTimestamp?: number
  timelineCanStepForward?: boolean
  timelineCanStepBackward?: boolean
  plan?: PlanEventData
  isLoading?: boolean
  isThinking?: boolean
  isReplayMode?: boolean
  replayScreenshotUrl?: string
  replayMetadata?: ScreenshotMetadata | null
  replayScreenshots?: ScreenshotMetadata[]
  summaryStreamText?: string
  isSummaryStreaming?: boolean
}>()

const emit = defineEmits<{
  (e: 'hide'): void
  (e: 'jumpToRealTime'): void
  (e: 'stepForward'): void
  (e: 'stepBackward'): void
  (e: 'seekByProgress', progress: number): void
}>()

// ---------------------------------------------------------------------------
// Tab State
// ---------------------------------------------------------------------------

const activeTab = ref<WorkspaceTab>('preview')
const deviceMode = ref<DeviceMode>('desktop')
const isFullscreen = ref(false)
const userOverride = ref(false)

/**
 * Automatically map the active tool to the workspace:
 * - Live tab for browser/terminal/editor flows
 * - Canvas tab for canvas/design/image/chart flows
 */
const autoTab = computed<WorkspaceTab>(() => {
  if (isCanvasDomainTool(props.toolContent)) return 'canvas'
  if (isLiveDomainTool(props.toolContent)) return 'preview'

  return 'preview'
})

// Auto-switch tabs when the active tool changes (immediate to sync on mount)
watch(autoTab, (newTab) => {
  activeTab.value = newTab
  userOverride.value = false
}, { immediate: true })

// Notification dots on tabs with new unread content
const tabNotifications = computed<WorkspaceTab[]>(() => {
  if (autoTab.value !== activeTab.value && userOverride.value) {
    return [autoTab.value]
  }
  return []
})

/** Handle user manually clicking a workspace tab */
function onTabChange(tab: WorkspaceTab) {
  activeTab.value = tab
  userOverride.value = tab !== autoTab.value
}

// ---------------------------------------------------------------------------
// View Type Mapping (active tab controls rendered view)
// ---------------------------------------------------------------------------

const forceViewType = computed<ContentViewType | undefined>(() => {
  switch (activeTab.value) {
    case 'preview':
      return 'live_preview'
    case 'editor':
      return 'editor'
    case 'console':
      return 'terminal'
    case 'canvas':
      return isChartDomainTool(props.toolContent) ? 'chart' : 'live_preview'
    default:
      return undefined
  }
})

// ---------------------------------------------------------------------------
// Browser Chrome
// ---------------------------------------------------------------------------

/** Extract the current URL from tool content for the URL bar */
const browserUrl = computed(() => {
  if (!props.toolContent) return '/'
  const args = props.toolContent.args || {}
  return String(args.url || args.goto_url || '/')
})

function navigateHome() {
  window.dispatchEvent(new CustomEvent('sandbox-navigate', {
    detail: { sessionId: props.sessionId, url: '/' },
  }))
}

function openExternal() {
  const url = browserUrl.value
  if (url && url !== '/') {
    window.open(url, '_blank', 'noopener')
  }
}

function refreshBrowser() {
  window.dispatchEvent(new CustomEvent('sandbox-refresh', {
    detail: { sessionId: props.sessionId },
  }))
}
</script>

<style scoped>
.workspace-panel {
  contain: layout style;
}
</style>
