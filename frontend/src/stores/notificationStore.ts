import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export type NotificationPriority = 'low' | 'medium' | 'high' | 'immediate'

export interface NotificationEntry {
  key: string
  text: string
  priority: NotificationPriority
  foldable: boolean
  title?: string
  createdAt: number
}

const priorityOrder: Record<NotificationPriority, number> = {
  immediate: 0,
  high: 1,
  medium: 2,
  low: 3,
}

export const useNotificationStore = defineStore('notifications', () => {
  const notifications = ref<NotificationEntry[]>([])
  const timers = new Map<string, ReturnType<typeof setTimeout>>()

  const clearTimer = (key: string): void => {
    const timer = timers.get(key)
    if (!timer) return
    clearTimeout(timer)
    timers.delete(key)
  }

  const scheduleDismissal = (key: string, durationMs: number): void => {
    clearTimer(key)
    if (durationMs <= 0) return
    const timer = setTimeout(() => {
      dismiss(key)
    }, durationMs)
    timers.set(key, timer)
  }

  const sortedNotifications = computed(() =>
    [...notifications.value].sort((left, right) => {
      const priorityDelta = priorityOrder[left.priority] - priorityOrder[right.priority]
      if (priorityDelta !== 0) {
        return priorityDelta
      }
      return left.createdAt - right.createdAt
    }),
  )

  const mergeNotification = (existing: NotificationEntry, incoming: Omit<NotificationEntry, 'createdAt'>): NotificationEntry => ({
    ...existing,
    ...incoming,
    createdAt: existing.createdAt,
  })

  const notify = (
    key: string,
    text: string,
    priority: NotificationPriority,
    options: { foldable?: boolean; title?: string; durationMs?: number } = {},
  ): string => {
    const entry: Omit<NotificationEntry, 'createdAt'> = {
      key,
      text,
      priority,
      foldable: options.foldable ?? false,
      title: options.title,
    }

    const existingIndex = notifications.value.findIndex((notification) => notification.key === key)
    if (existingIndex !== -1) {
      notifications.value[existingIndex] = mergeNotification(notifications.value[existingIndex]!, entry)
      scheduleDismissal(key, options.durationMs ?? 3000)
      return key
    }

    notifications.value = [...notifications.value, { ...entry, createdAt: Date.now() }]
    scheduleDismissal(key, options.durationMs ?? 3000)
    return key
  }

  const dismiss = (key: string): void => {
    clearTimer(key)
    notifications.value = notifications.value.filter((notification) => notification.key !== key)
  }

  const clearAll = (): void => {
    for (const key of timers.keys()) {
      clearTimer(key)
    }
    notifications.value = []
  }

  return {
    notifications: sortedNotifications,
    notify,
    dismiss,
    clearAll,
  }
})
