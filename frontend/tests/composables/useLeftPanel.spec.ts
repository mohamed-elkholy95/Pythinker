/**
 * Tests for useLeftPanel composable
 * Tests panel visibility state management via the UI store facade
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { createMockLocalStorage } from '../mocks/api'

// Mock localStorage before importing the composable
const mockLocalStorage = createMockLocalStorage()
Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage,
  writable: true
})

const LEFT_PANEL_STATE_KEY = 'pythinker-left-panel-state'

describe('useLeftPanel', () => {
  const originalInnerWidth = window.innerWidth

  beforeEach(() => {
    vi.clearAllMocks()
    mockLocalStorage.clear()
    // Force mobile viewport so the default (no localStorage) is false
    Object.defineProperty(window, 'innerWidth', { value: 320, writable: true, configurable: true })
    // Create a fresh Pinia instance for each test
    setActivePinia(createPinia())
    // Reset the module to get fresh state
    vi.resetModules()
  })

  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', { value: originalInnerWidth, writable: true, configurable: true })
    vi.resetModules()
  })

  it('should return initial state as false when localStorage is empty', async () => {
    // Re-create Pinia after resetModules
    setActivePinia(createPinia())
    const { useLeftPanel } = await import('@/composables/useLeftPanel')
    const { isLeftPanelShow } = useLeftPanel()
    expect(isLeftPanelShow.value).toBe(false)
  })

  it('should return saved state from localStorage', async () => {
    mockLocalStorage.setItem(LEFT_PANEL_STATE_KEY, JSON.stringify(true))
    setActivePinia(createPinia())
    const { useLeftPanel } = await import('@/composables/useLeftPanel')
    const { isLeftPanelShow } = useLeftPanel()
    expect(isLeftPanelShow.value).toBe(true)
  })

  it('should toggle panel visibility', async () => {
    setActivePinia(createPinia())
    const { useLeftPanel } = await import('@/composables/useLeftPanel')
    const { isLeftPanelShow, toggleLeftPanel } = useLeftPanel()

    expect(isLeftPanelShow.value).toBe(false)

    toggleLeftPanel()
    expect(isLeftPanelShow.value).toBe(true)

    toggleLeftPanel()
    expect(isLeftPanelShow.value).toBe(false)
  })

  it('should set panel visibility directly', async () => {
    setActivePinia(createPinia())
    const { useLeftPanel } = await import('@/composables/useLeftPanel')
    const { isLeftPanelShow, setLeftPanel } = useLeftPanel()

    setLeftPanel(true)
    expect(isLeftPanelShow.value).toBe(true)

    setLeftPanel(false)
    expect(isLeftPanelShow.value).toBe(false)
  })

  it('should show panel', async () => {
    setActivePinia(createPinia())
    const { useLeftPanel } = await import('@/composables/useLeftPanel')
    const { isLeftPanelShow, showLeftPanel } = useLeftPanel()

    showLeftPanel()
    expect(isLeftPanelShow.value).toBe(true)
  })

  it('should hide panel', async () => {
    setActivePinia(createPinia())
    const { useLeftPanel } = await import('@/composables/useLeftPanel')
    const { isLeftPanelShow, showLeftPanel, hideLeftPanel } = useLeftPanel()

    showLeftPanel()
    expect(isLeftPanelShow.value).toBe(true)

    hideLeftPanel()
    expect(isLeftPanelShow.value).toBe(false)
  })

  it('should share state across multiple composable instances', async () => {
    setActivePinia(createPinia())
    const { useLeftPanel } = await import('@/composables/useLeftPanel')
    const instance1 = useLeftPanel()
    const instance2 = useLeftPanel()

    instance1.showLeftPanel()
    expect(instance2.isLeftPanelShow.value).toBe(true)

    instance2.hideLeftPanel()
    expect(instance1.isLeftPanelShow.value).toBe(false)
  })

  it('should handle invalid localStorage data gracefully', async () => {
    mockLocalStorage.setItem(LEFT_PANEL_STATE_KEY, 'invalid-json')
    setActivePinia(createPinia())

    // Should not throw and return default value
    const { useLeftPanel } = await import('@/composables/useLeftPanel')
    const { isLeftPanelShow } = useLeftPanel()
    expect(isLeftPanelShow.value).toBe(false)
  })
})
