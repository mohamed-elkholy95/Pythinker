import { ref, onMounted } from 'vue'
import { getSettings, updateSettings } from '@/api/settings'

/**
 * Composable for managing deep research settings
 */
export function useDeepResearch() {
  const autoRun = ref(false)
  const loading = ref(false)

  /**
   * Load the auto-run setting from user settings
   */
  const loadSettings = async () => {
    try {
      loading.value = true
      const settings = await getSettings()
      autoRun.value = settings.deep_research_auto_run ?? false
    } catch {
      autoRun.value = false
    } finally {
      loading.value = false
    }
  }

  /**
   * Toggle the auto-run setting
   */
  const toggleAutoRun = async () => {
    try {
      loading.value = true
      const newValue = !autoRun.value
      await updateSettings({ deep_research_auto_run: newValue })
      autoRun.value = newValue
    } catch {
      // Settings update failed — keep current value
    } finally {
      loading.value = false
    }
  }

  /**
   * Set the auto-run setting to a specific value
   */
  const setAutoRun = async (value: boolean) => {
    if (autoRun.value === value) return

    try {
      loading.value = true
      await updateSettings({ deep_research_auto_run: value })
      autoRun.value = value
    } catch {
      // Settings update failed — keep current value
    } finally {
      loading.value = false
    }
  }

  // Load settings on mount
  onMounted(() => {
    loadSettings()
  })

  return {
    autoRun,
    loading,
    loadSettings,
    toggleAutoRun,
    setAutoRun
  }
}
