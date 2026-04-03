import { computed } from 'vue'

import { useNotificationStore, type NotificationPriority } from '@/stores/notificationStore'

export type { NotificationPriority }

export function useNotifications() {
  const store = useNotificationStore()

  const notify = (
    key: string,
    text: string,
    priority: NotificationPriority,
    options: { foldable?: boolean; title?: string; durationMs?: number } = {},
  ): string => store.notify(key, text, priority, options)

  const dismiss = (key: string): void => {
    store.dismiss(key)
  }

  return {
    notifications: computed(() => store.notifications),
    notify,
    dismiss,
    clearAll: store.clearAll,
  }
}

