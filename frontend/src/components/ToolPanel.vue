<template>
  <div
    ref="toolPanelRef"
    v-if="visible"
    :class="{
      'h-full w-full top-0 ltr:right-0 rtl:left-0 z-50 fixed sm:sticky sm:top-0 sm:right-0 sm:h-[100vh] sm:ml-3 sm:py-3 sm:mr-4': isShow,
      'h-full overflow-hidden': !isShow
    }"
    :style="{ 'width': isShow ? `${parentSize/2}px` : '0px', 'opacity': isShow ? '1' : '0', 'transition': '0.2s ease-in-out' }">
    <div class="h-full flex flex-col" :style="{ 'width': isShow ? '100%' : '0px' }">
      <ToolPanelContent
        ref="toolPanelContentRef"
        v-if="isShow && toolContent"
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
        :plan="plan"
        :isLoading="isLoading"
        :isThinking="isThinking"
        :isReplayMode="panelProps.isReplayMode"
        :replayScreenshotUrl="panelProps.replayScreenshotUrl"
        :replayMetadata="panelProps.replayMetadata"
        :summaryStreamText="panelProps.summaryStreamText"
        :isSummaryStreaming="panelProps.isSummaryStreaming"
        @hide="() => hideToolPanel(true)"
        @jumpToRealTime="jumpToRealTime"
        @stepForward="handleTimelineStepForward"
        @stepBackward="handleTimelineStepBackward"
        @seekByProgress="handleTimelineSeek"
        class="flex-1 min-h-0"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import type { ToolContent } from '../types/message'
import type { PlanEventData } from '../types/event'
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
}>()

const panelProps = defineProps<{
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
  isReplayMode?: boolean
  replayScreenshotUrl?: string
  replayMetadata?: ScreenshotMetadata | null
  summaryStreamText?: string
  isSummaryStreaming?: boolean
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
