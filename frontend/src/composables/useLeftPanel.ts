import { storeToRefs } from 'pinia'
import { useUIStore } from '../stores/uiStore'
import type { LeftPanelState } from '../types/panel'

/**
 * Thin facade over the UI store's left panel state.
 * All state lives in the Pinia store — this composable provides a
 * convenient destructuring API that matches the original interface.
 */
export function useLeftPanel(): LeftPanelState {
  const uiStore = useUIStore()
  const { isLeftPanelShow } = storeToRefs(uiStore)

  return {
    isLeftPanelShow,
    toggleLeftPanel: uiStore.toggleLeftPanel,
    setLeftPanel: uiStore.setLeftPanel,
    showLeftPanel: uiStore.showLeftPanel,
    hideLeftPanel: uiStore.hideLeftPanel,
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

  const uiStore = useUIStore()
  const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`)

  // Store the user's last desktop preference so we can restore it
  let desktopPreference = uiStore.isLeftPanelShow

  const handleBreakpointChange = (e: MediaQueryListEvent | MediaQueryList) => {
    if (e.matches) {
      // Entering mobile — remember preference and collapse
      desktopPreference = uiStore.isLeftPanelShow
      uiStore.setLeftPanel(false)
    } else {
      // Returning to desktop — restore user's preference
      uiStore.setLeftPanel(desktopPreference)
    }
  }

  // Apply immediately on mount
  handleBreakpointChange(mql)

  // Listen for future changes
  mql.addEventListener('change', handleBreakpointChange)

  // Store cleanup function for teardown / re-invocation
  _responsiveCleanup = () => mql.removeEventListener('change', handleBreakpointChange)
}
