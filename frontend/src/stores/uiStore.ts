/**
 * UI store — manages panel visibility, settings dialog, and theme.
 *
 * Consolidates state from useLeftPanel, useSettingsDialog, and useFilePanel
 * into a single Pinia store. The composables become thin facades.
 */
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { FileInfo } from '../api/file'

const LEFT_PANEL_STATE_KEY = 'pythinker-left-panel-state'

function readLeftPanelFromStorage(): boolean {
  try {
    if (typeof localStorage === 'undefined') return false
    const saved = localStorage.getItem(LEFT_PANEL_STATE_KEY)
    return saved ? JSON.parse(saved) : false
  } catch {
    return false
  }
}

export const useUIStore = defineStore('ui', () => {
  // ── Left Panel State ─────────────────────────────────────────────
  const isLeftPanelShow = ref(readLeftPanelFromStorage())

  // Persist to localStorage on change
  watch(isLeftPanelShow, (newValue) => {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(LEFT_PANEL_STATE_KEY, JSON.stringify(newValue))
      }
    } catch {
      // Silently ignore storage errors
    }
  })

  function toggleLeftPanel() {
    isLeftPanelShow.value = !isLeftPanelShow.value
  }

  function setLeftPanel(visible: boolean) {
    isLeftPanelShow.value = visible
  }

  function showLeftPanel() {
    isLeftPanelShow.value = true
  }

  function hideLeftPanel() {
    isLeftPanelShow.value = false
  }

  // ── Right Panel / Tool Panel State ───────────────────────────────
  const isRightPanelOpen = ref(false)

  function toggleRightPanel() {
    isRightPanelOpen.value = !isRightPanelOpen.value
  }

  function setRightPanel(visible: boolean) {
    isRightPanelOpen.value = visible
  }

  // ── Settings Dialog State ────────────────────────────────────────
  const isSettingsDialogOpen = ref(false)
  const settingsDefaultTab = ref<string>('')

  function openSettingsDialog(tabId?: string) {
    if (tabId) {
      settingsDefaultTab.value = tabId
    }
    isSettingsDialogOpen.value = true
  }

  function closeSettingsDialog() {
    isSettingsDialogOpen.value = false
  }

  function toggleSettingsDialog() {
    isSettingsDialogOpen.value = !isSettingsDialogOpen.value
  }

  function setSettingsDefaultTab(tabId: string) {
    settingsDefaultTab.value = tabId
  }

  // ── Panel Dismissal Tracking ─────────────────────────────────────
  /** True when user manually closed the tool panel during the current agent run. */
  const userDismissedPanel = ref(false)

  function setUserDismissedPanel(dismissed: boolean) {
    userDismissedPanel.value = dismissed
  }

  function resetDismissed() {
    userDismissedPanel.value = false
  }

  // ── File Preview State ───────────────────────────────────────────
  const filePreviewOpen = ref(false)
  const filePreviewFile = ref<FileInfo | null>(null)

  function showFilePreview(file: FileInfo) {
    filePreviewFile.value = file
    filePreviewOpen.value = true
  }

  function hideFilePreview() {
    filePreviewOpen.value = false
    filePreviewFile.value = null
  }

  return {
    // Left panel
    isLeftPanelShow,
    toggleLeftPanel,
    setLeftPanel,
    showLeftPanel,
    hideLeftPanel,
    // Right panel
    isRightPanelOpen,
    toggleRightPanel,
    setRightPanel,
    // Settings dialog
    isSettingsDialogOpen,
    settingsDefaultTab,
    openSettingsDialog,
    closeSettingsDialog,
    toggleSettingsDialog,
    setSettingsDefaultTab,
    // Panel dismissal
    userDismissedPanel,
    setUserDismissedPanel,
    resetDismissed,
    // File preview
    filePreviewOpen,
    filePreviewFile,
    showFilePreview,
    hideFilePreview,
  }
})
