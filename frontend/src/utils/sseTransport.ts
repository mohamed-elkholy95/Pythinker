const ENABLED_VALUES = new Set(['1', 'true', 'yes', 'on'])
const DISABLED_VALUES = new Set(['0', 'false', 'no', 'off'])
const EVENTSOURCE_RESUME_STORAGE_KEY = 'pythinker:sse-eventsource-resume'

const readStorageValue = (key: string): string => {
  if (typeof window === 'undefined') {
    return ''
  }

  if (typeof window.localStorage === 'undefined' || typeof window.localStorage.getItem !== 'function') {
    return ''
  }

  try {
    return String(window.localStorage.getItem(key) ?? '').toLowerCase()
  } catch {
    return ''
  }
}

export function isEventSourceResumeEnabled(): boolean {
  const envValue = String(import.meta.env.VITE_ENABLE_EVENTSOURCE_RESUME ?? 'true').toLowerCase()

  let enabledByDefault = true
  if (ENABLED_VALUES.has(envValue)) {
    enabledByDefault = true
  } else if (DISABLED_VALUES.has(envValue)) {
    enabledByDefault = false
  }

  if (typeof window === 'undefined') {
    return enabledByDefault
  }

  const storageValue = readStorageValue(EVENTSOURCE_RESUME_STORAGE_KEY)
  if (ENABLED_VALUES.has(storageValue)) {
    return true
  }
  if (DISABLED_VALUES.has(storageValue)) {
    return false
  }

  return enabledByDefault
}
