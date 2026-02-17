<script setup lang="ts">
import ToolPanelContent from '../ToolPanelContent.vue'
import type { ToolContent } from '@/types/message'
import type { PlanEventData } from '@/types/event'
import type { ScreenshotMetadata } from '@/types/screenshot'

defineProps<{
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
</script>

<template>
  <ToolPanelContent
    :embedded="false"
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
    class="h-full"
    @hide="emit('hide')"
    @jump-to-real-time="emit('jumpToRealTime')"
    @step-forward="emit('stepForward')"
    @step-backward="emit('stepBackward')"
    @seek-by-progress="(p: number) => emit('seekByProgress', p)"
  />
</template>
