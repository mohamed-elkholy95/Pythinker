/**
 * Theme color extraction utility for Konva canvas components
 *
 * Extracts CSS variable values for use in canvas-based graphics
 * where CSS variables cannot be used directly
 */
import { ref, onMounted, onUnmounted } from 'vue'

/**
 * Default color palette for light/dark themes
 */
export const THEME_COLORS = {
  light: {
    primary: '#000000',
    secondary: '#262626',
    success: '#22c55e',
    warning: '#f59e0b',
    error: '#ef4444',
    background: '#ffffff',
    surface: '#f9fafb',
    border: '#e5e7eb',
    text: {
      primary: '#1f2937',
      secondary: '#4b5563',
      tertiary: '#9ca3af',
    },
    timeline: {
      track: '#e5e7eb',
      marker: '#000000',
      markerHover: '#0a0a0a',
      scrubber: '#1f2937',
      activeMarker: '#22c55e',
      errorMarker: '#ef4444',
    },
  },
  dark: {
    primary: '#ffffff',
    secondary: '#e5e5e5',
    success: '#3fb950',
    warning: '#d29922',
    error: '#f85149',
    background: '#0d1117',
    surface: '#161b22',
    border: '#30363d',
    text: {
      primary: '#e6edf3',
      secondary: '#8b949e',
      tertiary: '#6e7681',
    },
    timeline: {
      track: '#21262d',
      marker: '#ffffff',
      markerHover: '#e5e5e5',
      scrubber: '#e6edf3',
      activeMarker: '#3fb950',
      errorMarker: '#f85149',
    },
  },
} as const

export type ThemeMode = 'light' | 'dark'
export type ThemeColors = (typeof THEME_COLORS)['light'] | (typeof THEME_COLORS)['dark']

/**
 * Get current theme mode from document
 */
export function getCurrentThemeMode(): ThemeMode {
  if (typeof document === 'undefined') return 'light'
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

/**
 * Get colors for current theme
 */
export function getThemeColors(mode?: ThemeMode): ThemeColors {
  const themeMode = mode ?? getCurrentThemeMode()
  return THEME_COLORS[themeMode]
}

/**
 * Extract CSS variable value from document
 */
export function getCssVariableValue(variableName: string): string {
  if (typeof document === 'undefined') return ''
  const style = getComputedStyle(document.documentElement)
  return style.getPropertyValue(variableName).trim()
}

/**
 * Composable for reactive theme colors
 *
 * Returns theme colors that automatically update when theme changes
 */
export function useThemeColors() {
  const themeMode = ref<ThemeMode>(getCurrentThemeMode())
  const colors = ref<ThemeColors>(getThemeColors(themeMode.value))
  let observer: MutationObserver | null = null

  const updateTheme = () => {
    const newMode = getCurrentThemeMode()
    if (newMode !== themeMode.value) {
      themeMode.value = newMode
      colors.value = getThemeColors(newMode)
    }
  }

  onMounted(() => {
    if (typeof document === 'undefined') return

    observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.attributeName === 'class') {
          updateTheme()
        }
      }
    })

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    })
  })

  onUnmounted(() => {
    observer?.disconnect()
  })

  return {
    themeMode,
    colors,
    updateTheme,
  }
}

/**
 * Convert hex color to Konva-compatible format
 * Konva accepts hex, rgb, rgba, and named colors
 */
export function toKonvaColor(color: string, opacity?: number): string {
  if (opacity !== undefined && opacity < 1) {
    // Convert hex to rgba
    const hex = color.replace('#', '')
    const r = parseInt(hex.slice(0, 2), 16)
    const g = parseInt(hex.slice(2, 4), 16)
    const b = parseInt(hex.slice(4, 6), 16)
    return `rgba(${r}, ${g}, ${b}, ${opacity})`
  }
  return color
}

/**
 * Get contrasting text color for a background color
 */
export function getContrastColor(hexColor: string): string {
  const hex = hexColor.replace('#', '')
  const r = parseInt(hex.slice(0, 2), 16)
  const g = parseInt(hex.slice(2, 4), 16)
  const b = parseInt(hex.slice(4, 6), 16)

  // Calculate relative luminance
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

  return luminance > 0.5 ? '#1f2937' : '#ffffff'
}

/**
 * Event type to color mapping for timeline markers
 */
export function getEventColor(eventType: string, themeMode: ThemeMode = 'light'): string {
  const colors = THEME_COLORS[themeMode]

  const eventColors: Record<string, string> = {
    // Tool events
    tool_start: colors.primary,
    tool_end: colors.success,
    tool_error: colors.error,

    // Step events
    step_start: colors.secondary,
    step_end: colors.success,

    // Message events
    message: colors.text.primary,
    user_message: colors.primary,
    assistant_message: colors.secondary,

    // Status events
    error: colors.error,
    warning: colors.warning,
    success: colors.success,

    // Default
    default: colors.timeline.marker,
  }

  return eventColors[eventType] || eventColors.default
}
