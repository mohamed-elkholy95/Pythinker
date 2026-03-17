import { ref, watch } from 'vue'
import type { LeftPanelState } from '../types/panel'

// Local storage key for left panel state
const LEFT_PANEL_STATE_KEY = 'pythinker-left-panel-state'

const canReadStorage = (): boolean =>
  typeof localStorage !== 'undefined' && typeof localStorage.getItem === 'function'

const canWriteStorage = (): boolean =>
  typeof localStorage !== 'undefined' && typeof localStorage.setItem === 'function'

// Read initial state from localStorage
const getInitialLeftPanelState = (): boolean => {
  try {
    if (!canReadStorage()) {
      return false
    }

    const saved = localStorage.getItem(LEFT_PANEL_STATE_KEY)
    return saved ? JSON.parse(saved) : false
  } catch (error) {
    console.error('Failed to read left panel state from localStorage:', error)
    return false
  }
}

// Global left panel state management
const isLeftPanelShow = ref(getInitialLeftPanelState())

// Save left panel state to localStorage
const saveLeftPanelState = (state: boolean) => {
  try {
    if (!canWriteStorage()) {
      return
    }

    localStorage.setItem(LEFT_PANEL_STATE_KEY, JSON.stringify(state))
  } catch (error) {
    console.error('Failed to save left panel state to localStorage:', error)
  }
}

// Watch for left panel state changes and save to localStorage
watch(isLeftPanelShow, (newValue) => {
  saveLeftPanelState(newValue)
}, { immediate: false })

export function useLeftPanel(): LeftPanelState {
  // Toggle left panel visibility
  const toggleLeftPanel = () => {
    isLeftPanelShow.value = !isLeftPanelShow.value
  }

  // Set left panel visibility
  const setLeftPanel = (visible: boolean) => {
    isLeftPanelShow.value = visible
  }

  // Show left panel
  const showLeftPanel = () => {
    isLeftPanelShow.value = true
  }

  // Hide left panel
  const hideLeftPanel = () => {
    isLeftPanelShow.value = false
  }

  return {
    isLeftPanelShow,
    toggleLeftPanel,
    setLeftPanel,
    showLeftPanel,
    hideLeftPanel
  }
}

/**
 * Responsive sidebar controller — auto-collapses on mobile viewports.
 *
 * Call once in a root component (e.g. App.vue or MainLayout).
 * Uses matchMedia for standards-compliant responsive behavior.
 *
 * MOBILE_BREAKPOINT matches the @media (max-width: 639px) used in LeftPanel.vue CSS.
 */
const MOBILE_BREAKPOINT = 639

// Idempotency guard: prevents listener stacking on HMR / accidental double invocation.
let _responsiveCleanup: (() => void) | null = null

export function useResponsiveLeftPanel(): void {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return

  // Remove previous listener if re-invoked (HMR / dev hot-reload)
  if (_responsiveCleanup) {
    _responsiveCleanup()
    _responsiveCleanup = null
  }

  const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`)

  // Store the user's last desktop preference so we can restore it
  let desktopPreference = isLeftPanelShow.value

  const handleBreakpointChange = (e: MediaQueryListEvent | MediaQueryList) => {
    if (e.matches) {
      // Entering mobile — remember preference and collapse
      desktopPreference = isLeftPanelShow.value
      isLeftPanelShow.value = false
    } else {
      // Returning to desktop — restore user's preference
      isLeftPanelShow.value = desktopPreference
    }
  }

  // Apply immediately on mount
  handleBreakpointChange(mql)

  // Listen for future changes
  mql.addEventListener('change', handleBreakpointChange)

  // Store cleanup function for teardown / re-invocation
  _responsiveCleanup = () => mql.removeEventListener('change', handleBreakpointChange)
}

