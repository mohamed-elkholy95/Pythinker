/**
 * Tests for useDialog composable
 * Tests dialog state management for confirm and prompt dialogs
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock vue-i18n
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

describe('useDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
  })

  describe('Confirm Dialog', () => {
    it('should initialize with dialog hidden', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { dialogVisible } = useDialog()
      expect(dialogVisible.value).toBe(false)
    })

    it('should show confirm dialog with options', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { dialogVisible, dialogConfig, showConfirmDialog } = useDialog()

      showConfirmDialog({
        title: 'Test Title',
        content: 'Test Content',
        confirmText: 'OK',
        cancelText: 'No',
        confirmType: 'danger',
      })

      expect(dialogVisible.value).toBe(true)
      expect(dialogConfig.title).toBe('Test Title')
      expect(dialogConfig.content).toBe('Test Content')
      expect(dialogConfig.confirmText).toBe('OK')
      expect(dialogConfig.cancelText).toBe('No')
      expect(dialogConfig.confirmType).toBe('danger')
    })

    it('should use default values for optional options', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { dialogConfig, showConfirmDialog } = useDialog()

      showConfirmDialog({
        title: 'Test Title',
        content: 'Test Content',
      })

      expect(dialogConfig.confirmText).toBe('Confirm')
      expect(dialogConfig.cancelText).toBe('Cancel')
      expect(dialogConfig.confirmType).toBe('primary')
    })

    it('should call onConfirm callback and hide dialog', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { dialogVisible, showConfirmDialog, handleConfirm } = useDialog()

      const onConfirm = vi.fn()
      showConfirmDialog({
        title: 'Test',
        content: 'Test',
        onConfirm,
      })

      await handleConfirm()

      expect(onConfirm).toHaveBeenCalledTimes(1)
      expect(dialogVisible.value).toBe(false)
    })

    it('should call onCancel callback and hide dialog', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { dialogVisible, showConfirmDialog, handleCancel } = useDialog()

      const onCancel = vi.fn()
      showConfirmDialog({
        title: 'Test',
        content: 'Test',
        onCancel,
      })

      handleCancel()

      expect(onCancel).toHaveBeenCalledTimes(1)
      expect(dialogVisible.value).toBe(false)
    })

    it('should handle async onConfirm callback', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { showConfirmDialog, handleConfirm } = useDialog()

      const asyncConfirm = vi.fn().mockResolvedValue(undefined)
      showConfirmDialog({
        title: 'Test',
        content: 'Test',
        onConfirm: asyncConfirm,
      })

      await handleConfirm()

      expect(asyncConfirm).toHaveBeenCalledTimes(1)
    })

    it('should show delete session dialog with correct options', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { dialogConfig, showDeleteSessionDialog } = useDialog()

      const onConfirm = vi.fn()
      showDeleteSessionDialog(onConfirm)

      expect(dialogConfig.title).toBe('Are you sure you want to delete this session?')
      expect(dialogConfig.confirmType).toBe('danger')
      expect(dialogConfig.confirmText).toBe('Delete')
    })
  })

  describe('Prompt Dialog', () => {
    it('should initialize with prompt dialog hidden', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { promptDialogVisible } = useDialog()
      expect(promptDialogVisible.value).toBe(false)
    })

    it('should show prompt dialog with options', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { promptDialogVisible, promptDialogConfig, promptInputValue, showPromptDialog } = useDialog()

      showPromptDialog({
        title: 'Enter Name',
        placeholder: 'Your name',
        defaultValue: 'John',
      })

      expect(promptDialogVisible.value).toBe(true)
      expect(promptDialogConfig.title).toBe('Enter Name')
      expect(promptDialogConfig.placeholder).toBe('Your name')
      expect(promptInputValue.value).toBe('John')
    })

    it('should call onConfirm with input value', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { promptInputValue, showPromptDialog, handlePromptConfirm } = useDialog()

      const onConfirm = vi.fn()
      showPromptDialog({
        title: 'Enter Name',
        onConfirm,
      })

      promptInputValue.value = 'Test Value'
      await handlePromptConfirm()

      expect(onConfirm).toHaveBeenCalledWith('Test Value')
    })

    it('should call onCancel and hide prompt dialog', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { promptDialogVisible, showPromptDialog, handlePromptCancel } = useDialog()

      const onCancel = vi.fn()
      showPromptDialog({
        title: 'Enter Name',
        onCancel,
      })

      handlePromptCancel()

      expect(onCancel).toHaveBeenCalledTimes(1)
      expect(promptDialogVisible.value).toBe(false)
    })

    it('should use empty string for default values', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const { promptDialogConfig, showPromptDialog } = useDialog()

      showPromptDialog({
        title: 'Enter Name',
      })

      expect(promptDialogConfig.placeholder).toBe('')
      expect(promptDialogConfig.defaultValue).toBe('')
    })
  })

  describe('Shared State', () => {
    it('should share state across multiple instances', async () => {
      const { useDialog } = await import('@/composables/useDialog')
      const instance1 = useDialog()
      const instance2 = useDialog()

      instance1.showConfirmDialog({
        title: 'Test',
        content: 'Test',
      })

      expect(instance2.dialogVisible.value).toBe(true)
    })
  })
})
