/**
 * Tests for useRightPanel composable
 * Tests tool and file panel visibility and content management
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockToolContent } from '../mocks/api'

describe('useRightPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
  })

  it('should initialize with panel hidden', async () => {
    const { useRightPanel } = await import('@/composables/useRightPanel')
    const { isShow } = useRightPanel()
    expect(isShow.value).toBe(false)
  })

  it('should show tool panel with content', async () => {
    const { useRightPanel } = await import('@/composables/useRightPanel')
    const { isShow, toolContent, panelType, showTool } = useRightPanel()

    showTool(mockToolContent)

    expect(isShow.value).toBe(true)
    expect(panelType.value).toBe('tool')
    expect(toolContent.value).toEqual(mockToolContent)
  })

  it('should set live mode when specified', async () => {
    const { useRightPanel } = await import('@/composables/useRightPanel')
    const { live, showTool } = useRightPanel()

    showTool(mockToolContent, true)
    expect(live.value).toBe(true)

    showTool(mockToolContent, false)
    expect(live.value).toBe(false)
  })

  it('should show file panel with file info', async () => {
    const { useRightPanel } = await import('@/composables/useRightPanel')
    const { isShow, fileInfo, panelType, showFile } = useRightPanel()

    const mockFile = {
      filename: 'test.txt',
      path: '/home/ubuntu/test.txt',
      size: 1024,
      mtime: Date.now()
    }

    showFile(mockFile)

    expect(isShow.value).toBe(true)
    expect(panelType.value).toBe('file')
    expect(fileInfo.value).toEqual(mockFile)
  })

  it('should hide panel', async () => {
    const { useRightPanel } = await import('@/composables/useRightPanel')
    const { isShow, showTool, hide } = useRightPanel()

    showTool(mockToolContent)
    expect(isShow.value).toBe(true)

    hide()
    expect(isShow.value).toBe(false)
  })

  it('should switch between tool and file panels', async () => {
    const { useRightPanel } = await import('@/composables/useRightPanel')
    const { panelType, showTool, showFile } = useRightPanel()

    const mockFile = {
      filename: 'test.txt',
      path: '/home/ubuntu/test.txt',
      size: 1024,
      mtime: Date.now()
    }

    showTool(mockToolContent)
    expect(panelType.value).toBe('tool')

    showFile(mockFile)
    expect(panelType.value).toBe('file')

    showTool(mockToolContent)
    expect(panelType.value).toBe('tool')
  })

  it('should share state across multiple instances', async () => {
    const { useRightPanel } = await import('@/composables/useRightPanel')
    const instance1 = useRightPanel()
    const instance2 = useRightPanel()

    instance1.showTool(mockToolContent)
    expect(instance2.isShow.value).toBe(true)
    expect(instance2.toolContent.value).toEqual(mockToolContent)

    instance2.hide()
    expect(instance1.isShow.value).toBe(false)
  })

  it('should default live to false when not specified', async () => {
    const { useRightPanel } = await import('@/composables/useRightPanel')
    const { live, showTool } = useRightPanel()

    showTool(mockToolContent)
    expect(live.value).toBe(false)
  })
})
