/**
 * Composable for Konva-based timeline visualization
 *
 * Integrates with useTimeline for playback state and provides
 * computed positions and interactions for Konva rendering
 */
import { ref, computed, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import type { AgentSSEEvent } from '@/types/event'
import { useTimeline, type TimelineState } from '@/composables/useTimeline'
import { getEventColor, getCurrentThemeMode, type ThemeMode } from '@/utils/themeColors'

export interface TimelineMarker {
  id: string
  x: number
  y: number
  timestamp: number
  eventType: string
  color: string
  isActive: boolean
  isHovered: boolean
  event: AgentSSEEvent
}

export interface TimelineDimensions {
  width: number
  height: number
  trackHeight: number
  markerRadius: number
  scrubberWidth: number
  padding: {
    left: number
    right: number
    top: number
    bottom: number
  }
}

export interface KonvaTimelineState {
  // From useTimeline
  timeline: TimelineState

  // Marker positions
  markers: Ref<TimelineMarker[]>
  scrubberX: Ref<number>

  // Interaction state
  isDragging: Ref<boolean>
  hoveredMarkerId: Ref<string | null>

  // Dimensions
  dimensions: Ref<TimelineDimensions>

  // Methods
  setDimensions: (width: number, height: number) => void
  handleScrubberDrag: (x: number) => void
  handleMarkerHover: (markerId: string | null) => void
  handleMarkerClick: (markerId: string) => void
  startDrag: () => void
  endDrag: () => void

  // Animation
  animationFrame: Ref<number>
  startAnimation: () => void
  stopAnimation: () => void
}

const DEFAULT_DIMENSIONS: TimelineDimensions = {
  width: 800,
  height: 60,
  trackHeight: 4,
  markerRadius: 6,
  scrubberWidth: 2,
  padding: {
    left: 20,
    right: 20,
    top: 20,
    bottom: 20,
  },
}

/**
 * Composable for Konva timeline visualization
 */
export function useKonvaTimeline(
  events: Ref<AgentSSEEvent[]>,
  options: {
    autoLive?: boolean
    dimensions?: Partial<TimelineDimensions>
  } = {}
): KonvaTimelineState {
  const { autoLive = true, dimensions: initialDimensions } = options

  // Get the base timeline state
  const timeline = useTimeline(events, { autoLive })

  // Merge dimensions with defaults
  const dimensions = ref<TimelineDimensions>({
    ...DEFAULT_DIMENSIONS,
    ...initialDimensions,
    padding: {
      ...DEFAULT_DIMENSIONS.padding,
      ...initialDimensions?.padding,
    },
  })

  // Interaction state
  const isDragging = ref(false)
  const hoveredMarkerId = ref<string | null>(null)
  const animationFrame = ref(0)

  // Track area dimensions
  const trackWidth = computed(() =>
    dimensions.value.width - dimensions.value.padding.left - dimensions.value.padding.right
  )

  const trackY = computed(() =>
    dimensions.value.height / 2
  )

  // Get theme mode for colors
  const themeMode = ref<ThemeMode>(getCurrentThemeMode())

  // Compute marker positions
  const markers = computed<TimelineMarker[]>(() => {
    if (events.value.length === 0 || timeline.duration.value === 0) {
      return []
    }

    const startTime = Math.min(...events.value.map((e) => e.data.timestamp || 0))

    return events.value.map((event, index) => {
      const eventTime = event.data.timestamp || 0
      const relativeTime = eventTime - startTime
      const progress = relativeTime / timeline.duration.value

      const x = dimensions.value.padding.left + progress * trackWidth.value
      const y = trackY.value

      const isActive = index === timeline.currentIndex.value
      // Use type-safe property access for optional tool_call_id
      const eventData = event.data as { tool_call_id?: string }
      const markerId = eventData.tool_call_id || `marker-${index}`
      const isHovered = hoveredMarkerId.value === markerId

      return {
        id: markerId,
        x,
        y,
        timestamp: eventTime,
        eventType: event.event || 'default',
        color: getEventColor(event.event || 'default', themeMode.value),
        isActive,
        isHovered,
        event,
      }
    })
  })

  // Compute scrubber position
  const scrubberX = computed(() => {
    const progress = timeline.progress.value / 100
    return dimensions.value.padding.left + progress * trackWidth.value
  })

  // Set dimensions (called on resize)
  const setDimensions = (width: number, height: number) => {
    dimensions.value = {
      ...dimensions.value,
      width,
      height,
    }
  }

  // Handle scrubber drag
  const handleScrubberDrag = (x: number) => {
    // Clamp x to track bounds
    const minX = dimensions.value.padding.left
    const maxX = dimensions.value.padding.left + trackWidth.value
    const clampedX = Math.max(minX, Math.min(maxX, x))

    // Calculate progress from x position
    const progress = ((clampedX - minX) / trackWidth.value) * 100
    timeline.seekByProgress(progress)
  }

  // Handle marker hover
  const handleMarkerHover = (markerId: string | null) => {
    hoveredMarkerId.value = markerId
  }

  // Handle marker click
  const handleMarkerClick = (markerId: string) => {
    const markerIndex = markers.value.findIndex((m) => m.id === markerId)
    if (markerIndex >= 0) {
      timeline.seek(markerIndex)
    }
  }

  // Drag state management
  const startDrag = () => {
    isDragging.value = true
    timeline.pause()
    startAnimation() // Ensure animation loop is running while dragging
  }

  const endDrag = () => {
    isDragging.value = false
    // Animation loop will self-stop on next frame since isDragging is false
  }

  // Animation loop — only runs when timeline is playing or scrubber is dragging
  let rafId: number | null = null

  const animate = () => {
    // Only continue the loop when there's actual animation work to do
    const needsAnimation = timeline.isPlaying.value || isDragging.value
    if (!needsAnimation) {
      rafId = null
      return
    }
    animationFrame.value++
    rafId = requestAnimationFrame(animate)
  }

  const startAnimation = () => {
    if (!rafId) {
      rafId = requestAnimationFrame(animate)
    }
  }

  const stopAnimation = () => {
    if (rafId) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
  }

  // Watch for theme changes
  if (typeof document !== 'undefined') {
    const observer = new MutationObserver(() => {
      themeMode.value = getCurrentThemeMode()
    })

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    })

    onUnmounted(() => {
      observer.disconnect()
      stopAnimation()
    })
  }

  return {
    timeline,
    markers,
    scrubberX,
    isDragging,
    hoveredMarkerId,
    dimensions,
    setDimensions,
    handleScrubberDrag,
    handleMarkerHover,
    handleMarkerClick,
    startDrag,
    endDrag,
    animationFrame,
    startAnimation,
    stopAnimation,
  }
}

/**
 * Get track configuration for Konva rendering
 */
export function getTrackConfig(dimensions: TimelineDimensions, colors: { track: string }) {
  return {
    x: dimensions.padding.left,
    y: dimensions.height / 2 - dimensions.trackHeight / 2,
    width: dimensions.width - dimensions.padding.left - dimensions.padding.right,
    height: dimensions.trackHeight,
    fill: colors.track,
    cornerRadius: dimensions.trackHeight / 2,
  }
}

/**
 * Get scrubber configuration for Konva rendering
 */
export function getScrubberConfig(
  x: number,
  dimensions: TimelineDimensions,
  colors: { scrubber: string }
) {
  const handleRadius = 8
  const handleY = dimensions.height / 2

  return {
    line: {
      points: [x, dimensions.padding.top, x, dimensions.height - dimensions.padding.bottom],
      stroke: colors.scrubber,
      strokeWidth: dimensions.scrubberWidth,
    },
    handle: {
      x,
      y: handleY,
      radius: handleRadius,
      fill: colors.scrubber,
      shadowColor: 'rgba(0, 0, 0, 0.2)',
      shadowBlur: 4,
      shadowOffset: { x: 0, y: 2 },
      shadowOpacity: 0.3,
    },
  }
}

/**
 * Get marker configuration for Konva rendering
 */
export function getMarkerConfig(
  marker: TimelineMarker,
  dimensions: TimelineDimensions
) {
  const baseRadius = dimensions.markerRadius
  const radius = marker.isActive ? baseRadius * 1.3 : marker.isHovered ? baseRadius * 1.15 : baseRadius

  return {
    x: marker.x,
    y: marker.y,
    radius,
    fill: marker.color,
    stroke: marker.isActive ? '#ffffff' : undefined,
    strokeWidth: marker.isActive ? 2 : 0,
    shadowColor: 'rgba(0, 0, 0, 0.15)',
    shadowBlur: marker.isActive ? 6 : 3,
    shadowOffset: { x: 0, y: 1 },
    shadowOpacity: 0.4,
  }
}
