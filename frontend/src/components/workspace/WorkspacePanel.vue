<script setup lang="ts">
import { shallowRef, computed, watch } from 'vue'
import WorkspaceTabBar from './WorkspaceTabBar.vue'
import ToolPanelContent from '../ToolPanelContent.vue'
import FileBrowserView from './FileBrowserView.vue'
import type { WorkspaceMode } from './WorkspaceTabBar.vue'
import type { ToolContent } from '@/types/message'
import type { PlanEventData } from '@/types/event'
import type { ScreenshotMetadata } from '@/types/screenshot'
import type { ContentViewType } from '@/constants/tool'
import { isCanvasDomainTool, isChartDomainTool } from '@/utils/viewRouting'

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
// Mode State
// ---------------------------------------------------------------------------

const activeTab = shallowRef<WorkspaceMode>('live')
const userOverride = shallowRef(false)

/**
 * Automatically map the active tool to the workspace mode:
 * - Canvas mode for canvas/design/image/chart flows
 * - Live mode for everything else (browser, terminal, editor, search)
 */
const autoTab = computed<WorkspaceMode>(() => {
  if (isCanvasDomainTool(props.toolContent)) return 'canvas'
  return 'live'
})

// Auto-switch modes when the active tool changes (immediate to sync on mount)
watch(autoTab, (newTab) => {
  activeTab.value = newTab
  userOverride.value = false
}, { immediate: true })

// Notification dots on tabs with new unread content
const tabNotifications = computed<WorkspaceMode[]>(() => {
  if (autoTab.value !== activeTab.value && userOverride.value) {
    return [autoTab.value]
  }
  return []
})

/** Handle user manually clicking a workspace tab */
function onTabChange(tab: WorkspaceMode) {
  activeTab.value = tab
  userOverride.value = tab !== autoTab.value
}

// ---------------------------------------------------------------------------
// View Type Mapping (active mode controls rendered view)
// ---------------------------------------------------------------------------

const forceViewType = computed<ContentViewType | undefined>(() => {
  switch (activeTab.value) {
    case 'live':
      // Let useContentConfig auto-detect (terminal, editor, search, browser)
      return undefined
    case 'canvas':
      return isChartDomainTool(props.toolContent) ? 'chart' : 'live_preview'
    default:
      return undefined
  }
})

// ---------------------------------------------------------------------------
// Files Handler
// ---------------------------------------------------------------------------

function handleFileSelect(file: { path: string; name: string }) {
  console.log('File selected:', file)
  // TODO: Implement file viewing/editing logic
}
</script>

<template>
  <div class="workspace-shell">
    <!-- Workspace Tab Bar -->
    <WorkspaceTabBar
      :model-value="activeTab"
      :notifications="tabNotifications"
      @update:model-value="onTabChange"
      @close="emit('hide')"
    />

    <!-- Content Area: Dynamic based on active mode -->
    <div class="workspace-content">
      <!-- Files Mode -->
      <FileBrowserView
        v-if="activeTab === 'files'"
        :session-id="sessionId"
        @file-select="handleFileSelect"
      />

      <!-- Live / Canvas Mode — rendered via ToolPanelContent -->
      <ToolPanelContent
        v-else
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
        class="workspace-content-inner"
        @hide="emit('hide')"
        @jump-to-real-time="emit('jumpToRealTime')"
        @step-forward="emit('stepForward')"
        @step-backward="emit('stepBackward')"
        @seek-by-progress="(p: number) => emit('seekByProgress', p)"
      />
    </div>
  </div>
</template>

<style scoped>
.workspace-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  overflow: hidden;
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  border-radius: 16px;
  box-shadow:
    0 0 0 0.5px var(--border-light),
    0 8px 32px var(--shadow-XS),
    0 2px 8px var(--shadow-XS);
  contain: layout style;
}

@media (max-width: 639px) {
  .workspace-shell {
    border-radius: 0;
    border: none;
    box-shadow: none;
  }
}

.workspace-content {
  flex: 1;
  min-height: 0;
  position: relative;
}

.workspace-content-inner {
  height: 100%;
}
</style>
