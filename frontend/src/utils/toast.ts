import { useNotificationStore } from '@/stores/notificationStore'
import type { NotificationPriority } from '@/composables/useNotifications'

interface ToastOptions {
  message: string
  title?: string
  type?: 'error' | 'info' | 'success' | 'progress'
  duration?: number
  key?: string
  foldable?: boolean
}

const buildKey = (options: ToastOptions): string => {
  if (options.key) {
    return options.key
  }
  if (options.title) {
    return `${options.type ?? 'info'}:${options.title}`
  }
  return `${options.type ?? 'info'}:${options.message}`
}

const typeToPriority = (type: ToastOptions['type'] | undefined): NotificationPriority => {
  switch (type) {
    case 'error':
      return 'high'
    case 'success':
      return 'medium'
    case 'progress':
      return 'immediate'
    case 'info':
    default:
      return 'low'
  }
}

export function showToast(options: ToastOptions | string): void {
  const config: ToastOptions = typeof options === 'string' ? { message: options } : options
  const notifications = useNotificationStore()
  notifications.notify(buildKey(config), config.message, typeToPriority(config.type), {
    foldable: config.foldable ?? false,
    title: config.title,
    durationMs: config.duration ?? 3000,
  })
}

export function showErrorToast(message: string, duration?: number): void {
  showToast({ message, type: 'error', duration, foldable: true })
}

export function showInfoToast(message: string, duration?: number): void {
  showToast({ message, type: 'info', duration, foldable: true })
}

export function showSuccessToast(message: string, duration?: number): void {
  showToast({ message, type: 'success', duration, foldable: true })
}

export function showProgressToast(title: string, message: string, duration?: number): void {
  showToast({ title, message, type: 'progress', duration: duration ?? 8000, key: `progress:${title}`, foldable: true })
}

declare global {
  interface Window {
    toast: {
      show: typeof showToast
      error: typeof showErrorToast
      info: typeof showInfoToast
      success: typeof showSuccessToast
      progress: typeof showProgressToast
    }
  }
}

if (typeof window !== 'undefined') {
  window.toast = {
    show: showToast,
    error: showErrorToast,
    info: showInfoToast,
    success: showSuccessToast,
    progress: showProgressToast,
  }
}
