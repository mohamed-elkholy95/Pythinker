<template>
  <div class="pb-[32px] last:pb-0 border-b border-[var(--border-light)] last-of-type:border-transparent w-full">
    <div class="text-[13px] font-medium text-[var(--text-tertiary)] mb-1 w-full">{{ t('Agent Behavior') }}</div>

    <!-- Browser Agent Max Steps -->
    <div class="mb-[24px] w-full">
      <div class="text-sm font-medium text-[var(--text-primary)] mb-[12px]">{{ t('Browser Max Steps') }}</div>
      <input
        type="number"
        v-model.number="localSettings.browser_agent_max_steps"
        @change="saveSettings"
        min="5"
        max="100"
        step="5"
        class="w-[280px] h-[36px] px-3 rounded-lg border border-[var(--border-main)] bg-transparent text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--Button-primary-black)]"
      />
      <div class="text-xs text-[var(--text-tertiary)] mt-1">
        {{ t('Maximum steps for browser automation (5-100)') }}
      </div>
    </div>

    <!-- Browser Agent Timeout -->
    <div class="mb-[24px] w-full">
      <div class="text-sm font-medium text-[var(--text-primary)] mb-[12px]">{{ t('Browser Timeout (seconds)') }}</div>
      <input
        type="number"
        v-model.number="localSettings.browser_agent_timeout"
        @change="saveSettings"
        min="60"
        max="600"
        step="30"
        class="w-[280px] h-[36px] px-3 rounded-lg border border-[var(--border-main)] bg-transparent text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--Button-primary-black)]"
      />
      <div class="text-xs text-[var(--text-tertiary)] mt-1">
        {{ t('Timeout for browser operations in seconds (60-600)') }}
      </div>
    </div>

    <!-- Use Vision Toggle -->
    <div class="mb-[24px] w-full">
      <div class="flex items-center justify-between w-[280px]">
        <div>
          <div class="text-sm font-medium text-[var(--text-primary)]">{{ t('Use Vision') }}</div>
          <div class="text-xs text-[var(--text-tertiary)] mt-1">
            {{ t('Enable screenshot analysis for browser automation') }}
          </div>
        </div>
        <button
          @click="toggleVision"
          :class="[
            'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
            localSettings.browser_agent_use_vision
              ? 'bg-[var(--Button-primary-black)]'
              : 'bg-[var(--fill-tsp-gray-dark)]'
          ]"
        >
          <span
            :class="[
              'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
              localSettings.browser_agent_use_vision ? 'translate-x-6' : 'translate-x-1'
            ]"
          />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSettings, updateSettings, type UserSettings } from '@/api/settings'

const { t } = useI18n()

// Local settings state
const localSettings = ref<UserSettings>({
  llm_provider: 'openai',
  model_name: 'gpt-4',
  temperature: 0.7,
  max_tokens: 8000,
  search_provider: 'bing',
  browser_agent_max_steps: 25,
  browser_agent_timeout: 300,
  browser_agent_use_vision: true,
})

// Load settings on mount
onMounted(async () => {
  try {
    const settings = await getSettings()
    localSettings.value = { ...localSettings.value, ...settings }
  } catch (error) {
    console.error('Failed to load settings:', error)
  }
})

// Toggle vision setting
const toggleVision = async () => {
  localSettings.value.browser_agent_use_vision = !localSettings.value.browser_agent_use_vision
  await saveSettings()
}

// Save settings
const saveSettings = async () => {
  try {
    await updateSettings({
      browser_agent_max_steps: localSettings.value.browser_agent_max_steps,
      browser_agent_timeout: localSettings.value.browser_agent_timeout,
      browser_agent_use_vision: localSettings.value.browser_agent_use_vision,
    })
  } catch (error) {
    console.error('Failed to save settings:', error)
  }
}
</script>
