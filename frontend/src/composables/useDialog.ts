import { ref, reactive, readonly } from 'vue'
import { useI18n } from 'vue-i18n'

// Dialog state
interface DialogState {
  title: string
  content: string
  confirmText: string
  cancelText: string
  confirmType: 'primary' | 'danger'
  onConfirm?: () => void | Promise<void>
  onCancel?: () => void
}

// Prompt dialog state
interface PromptDialogState {
  title: string
  placeholder: string
  defaultValue: string
  confirmText: string
  cancelText: string
  onConfirm?: (value: string) => void | Promise<void>
  onCancel?: () => void
}

// Global state
const dialogVisible = ref(false)
const dialogConfig = reactive<DialogState>({
  title: '',
  content: '',
  confirmText: '',
  cancelText: '',
  confirmType: 'primary',
  onConfirm: undefined,
  onCancel: undefined
})

// Prompt dialog state
const promptDialogVisible = ref(false)
const promptDialogConfig = reactive<PromptDialogState>({
  title: '',
  placeholder: '',
  defaultValue: '',
  confirmText: '',
  cancelText: '',
  onConfirm: undefined,
  onCancel: undefined
})
const promptInputValue = ref('')

export function useDialog() {
  const { t } = useI18n()

  // Handle confirm
  const handleConfirm = async () => {
    if (dialogConfig.onConfirm) {
      await dialogConfig.onConfirm()
    }
    dialogVisible.value = false
  }

  // Handle cancel
  const handleCancel = () => {
    if (dialogConfig.onCancel) {
      dialogConfig.onCancel()
    }
    dialogVisible.value = false
  }

  // Show general confirm dialog
  const showConfirmDialog = (options: {
    title: string
    content: string
    confirmText?: string
    cancelText?: string
    confirmType?: 'primary' | 'danger'
    onConfirm?: () => void | Promise<void>
    onCancel?: () => void
  }) => {
    Object.assign(dialogConfig, {
      title: options.title,
      content: options.content,
      confirmText: options.confirmText || t('Confirm'),
      cancelText: options.cancelText || t('Cancel'),
      confirmType: options.confirmType || 'primary',
      onConfirm: options.onConfirm,
      onCancel: options.onCancel
    })
    dialogVisible.value = true
  }

  // Show delete session dialog
  const showDeleteSessionDialog = (onConfirm?: () => void | Promise<void>) => {
    showConfirmDialog({
      title: t('Are you sure you want to delete this session?'),
      content: t('The chat history of this session cannot be recovered after deletion.'),
      confirmText: t('Delete'),
      cancelText: t('Cancel'),
      confirmType: 'danger',
      onConfirm
    })
  }

  // Show prompt dialog (input dialog)
  const showPromptDialog = (options: {
    title: string
    placeholder?: string
    defaultValue?: string
    confirmText?: string
    cancelText?: string
    onConfirm?: (value: string) => void | Promise<void>
    onCancel?: () => void
  }) => {
    Object.assign(promptDialogConfig, {
      title: options.title,
      placeholder: options.placeholder || '',
      defaultValue: options.defaultValue || '',
      confirmText: options.confirmText || t('Confirm'),
      cancelText: options.cancelText || t('Cancel'),
      onConfirm: options.onConfirm,
      onCancel: options.onCancel
    })
    promptInputValue.value = options.defaultValue || ''
    promptDialogVisible.value = true
  }

  // Handle prompt confirm
  const handlePromptConfirm = async () => {
    if (promptDialogConfig.onConfirm) {
      await promptDialogConfig.onConfirm(promptInputValue.value)
    }
    promptDialogVisible.value = false
  }

  // Handle prompt cancel
  const handlePromptCancel = () => {
    if (promptDialogConfig.onCancel) {
      promptDialogConfig.onCancel()
    }
    promptDialogVisible.value = false
  }

  return {
    dialogVisible: readonly(dialogVisible),
    dialogConfig: readonly(dialogConfig),
    handleConfirm,
    handleCancel,
    showConfirmDialog,
    showDeleteSessionDialog,
    // Prompt dialog
    promptDialogVisible: readonly(promptDialogVisible),
    promptDialogConfig: readonly(promptDialogConfig),
    promptInputValue,
    showPromptDialog,
    handlePromptConfirm,
    handlePromptCancel
  }
} 