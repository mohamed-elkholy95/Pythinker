<template>
  <div
    ref="toolPanelRef"
    v-if="visible"
    :class="{
      'h-full w-full top-0 ltr:right-0 rtl:left-0 z-50 fixed sm:sticky sm:top-0 sm:right-0 sm:h-[100vh] sm:ml-3 sm:py-3 sm:mr-4': isShow,
      'h-full overflow-hidden': !isShow
    }"
    :style="{ 'width': isShow ? panelWidth : '0px', 'opacity': isShow ? '1' : '0', 'transition': '0.2s ease-in-out' }">
    <div class="h-full flex flex-col" :style="{ 'width': isShow ? '100%' : '0px' }">
      <ToolPanelContent
        ref="toolPanelContentRef"
        v-if="isShow && toolContent"
        :embedded="false"
        :sessionId="sessionId"
        :realTime="realTime"
        :toolContent="toolContent"
        :live="live"
        :isShare="isShare"
        :showTimeline="showTimeline"
        :timelineProgress="timelineProgress"
        :timelineTimestamp="timelineTimestamp"
        :timelineCanStepForward="timelineCanStepForward"
        :timelineCanStepBackward="timelineCanStepBackward"
        :toolTimeline="toolTimeline"
        :timelineCurrentStep="timelineCurrentStep"
        :timelineTotalSteps="timelineTotalSteps"
        :plan="plan"
        :isLoading="isLoading"
        :isThinking="isThinking"
        :isReplayMode="panelProps.isReplayMode"
        :replayScreenshotUrl="panelProps.replayScreenshotUrl"
        :replayMetadata="panelProps.replayMetadata"
        :replayScreenshots="panelProps.replayScreenshots"
        :summaryStreamText="panelProps.summaryStreamText"
        :finalReportText="panelProps.finalReportText"
        :isSummaryStreaming="panelProps.isSummaryStreaming"
        :planPresentationText="panelProps.planPresentationText"
        :isPlanStreaming="panelProps.isPlanStreaming"
        :activeCanvasUpdate="panelProps.activeCanvasUpdate"
        :sessionStartTime="panelProps.sessionStartTime"
        @hide="() => hideToolPanel(true)"
        @jumpToRealTime="jumpToRealTime"
        @stepForward="handleTimelineStepForward"
        @stepBackward="handleTimelineStepBackward"
        @seekByProgress="handleTimelineSeek"
        @switchToChat="emit('switchToChat')"
        @requestWidth="(w: number) => emit('requestWidth', w)"
        class="flex-1 min-h-0"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import type { ToolContent } from '../types/message'
import type { CanvasUpdateEventData, PlanEventData } from '../types/event'
import type { ScreenshotMetadata } from '../types/screenshot'
import ToolPanelContent from './ToolPanelContent.vue'
import { useResizeObserver } from '../composables/useResizeObserver'
import { eventBus } from '../utils/eventBus'
import { EVENT_SHOW_FILE_PANEL, EVENT_SHOW_TOOL_PANEL, EVENT_TOOL_PANEL_STATE_CHANGE } from '../constants/event'

const toolPanelRef = ref<HTMLElement>()
const { size: parentSize } = useResizeObserver(toolPanelRef, {
  target: 'parent',
  property: 'width'
})

// On viewports narrower than 1024px, the panel overlaps full screen.
const MOBILE_VIEWPORT_BREAKPOINT = 1024
const isTouchLikeViewport = () =>
  window.innerWidth < MOBILE_VIEWPORT_BREAKPOINT
const isMobile = ref(isTouchLikeViewport())
const onResize = () => { isMobile.value = isTouchLikeViewport() }
window.addEventListener('resize', onResize)
onUnmounted(() => window.removeEventListener('resize', onResize))

const MIN_PANEL_WIDTH_PX = 340
const MIN_CHAT_WIDTH_PX = 420

const panelWidth = computed(() => {
  if (isMobile.value) return '100%'

  const containerWidth = parentSize.value || window.innerWidth
  const maxPanelWidth = Math.max(MIN_PANEL_WIDTH_PX, containerWidth - MIN_CHAT_WIDTH_PX)
  const requestedWidth = panelProps.size && panelProps.size > 0 ? panelProps.size : containerWidth / 2
  const clampedWidth = Math.min(Math.max(requestedWidth, MIN_PANEL_WIDTH_PX), maxPanelWidth)

  return `${Math.round(clampedWidth)}px`
})

// Tool panel state
const isShow = ref(false)
const live = ref(false)
const toolContent = ref<ToolContent>()
const visible = ref(true)
const toolPanelContentRef = ref<InstanceType<typeof ToolPanelContent> | null>(null)

const emit = defineEmits<{
  (e: 'jumpToRealTime'): void
  (e: 'panelStateChange', isOpen: boolean, userAction: boolean): void
  (e: 'timelineStepForward'): void
  (e: 'timelineStepBackward'): void
  (e: 'timelineSeek', progress: number): void
  (e: 'switchToChat'): void
  (e: 'requestWidth', width: number): void
}>()

const panelProps = defineProps<{
  size?: number
  sessionId?: string
  realTime: boolean
  isShare: boolean
  plan?: PlanEventData
  isLoading?: boolean
  isThinking?: boolean
  showTimeline?: boolean
  timelineProgress?: number
  timelineTimestamp?: number
  timelineCanStepForward?: boolean
  timelineCanStepBackward?: boolean
  toolTimeline?: ToolContent[]
  timelineCurrentStep?: number
  timelineTotalSteps?: number
  isReplayMode?: boolean
  replayScreenshotUrl?: string
  replayMetadata?: ScreenshotMetadata | null
  replayScreenshots?: ScreenshotMetadata[]
  summaryStreamText?: string
  finalReportText?: string
  isSummaryStreaming?: boolean
  planPresentationText?: string
  isPlanStreaming?: boolean
  activeCanvasUpdate?: CanvasUpdateEventData | null
  /** Shared session start timestamp so all timers stay in sync. */
  sessionStartTime?: number
}>()

// Track if state change was from user action
const isUserAction = ref(false)

// Watch for isShow changes and emit events
watch(isShow, (newValue) => {
  eventBus.emit(EVENT_TOOL_PANEL_STATE_CHANGE, newValue)
  emit('panelStateChange', newValue, isUserAction.value)
  isUserAction.value = false // Reset after emitting
})

const showToolPanel = (content: ToolContent, isLive: boolean = false) => {
  eventBus.emit(EVENT_SHOW_TOOL_PANEL)
  visible.value = true
  toolContent.value = content
  isUserAction.value = false
  isShow.value = true
  live.value = isLive
}

const hideToolPanel = (userTriggered: boolean = false) => {
  isUserAction.value = userTriggered
  isShow.value = false
}

const clearContent = () => {
  toolContent.value = undefined
  live.value = false
  isShow.value = false
}

const jumpToRealTime = () => {
  emit('jumpToRealTime')
}

const handleTimelineStepForward = () => {
  emit('timelineStepForward')
}

const handleTimelineStepBackward = () => {
  emit('timelineStepBackward')
}

const handleTimelineSeek = (progress: number) => {
  emit('timelineSeek', progress)
}

onMounted(() => {
  eventBus.on(EVENT_SHOW_FILE_PANEL, () => {
    visible.value = false
    isShow.value = false
  })
})

onUnmounted(() => {
  eventBus.off(EVENT_SHOW_FILE_PANEL)
})

defineExpose({
  showToolPanel,
  hideToolPanel,
  clearContent,
  isShow
})
</script>
