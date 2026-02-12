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
