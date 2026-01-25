<template>
  <div class="pb-[32px] last:pb-0 border-b border-[var(--border-light)] last-of-type:border-transparent w-full">
    <div class="text-[13px] font-medium text-[var(--text-tertiary)] mb-1 w-full">{{ t('AI Model') }}</div>

    <!-- LLM Provider Selection -->
    <div class="mb-[24px] w-full">
      <div class="text-sm font-medium text-[var(--text-primary)] mb-[12px]">{{ t('LLM Provider') }}</div>
      <Select v-model="localSettings.llm_provider" @update:modelValue="onProviderChange">
        <SelectTrigger class="w-[280px] h-[36px]">
          <SelectValue :placeholder="t('Select provider')" />
        </SelectTrigger>
        <SelectContent :side-offset="5">
          <SelectItem
            v-for="provider in providers.llm_providers"
            :key="provider.id"
            :value="provider.id"
          >
            {{ provider.name }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <!-- Model Selection -->
    <div class="mb-[24px] w-full">
      <div class="text-sm font-medium text-[var(--text-primary)] mb-[12px]">{{ t('Model') }}</div>
      <Select v-model="localSettings.model_name" @update:modelValue="saveSettings">
        <SelectTrigger class="w-[280px] h-[36px]">
          <SelectValue :placeholder="t('Select model')" />
        </SelectTrigger>
        <SelectContent :side-offset="5">
          <SelectItem
            v-for="model in availableModels"
            :key="model"
            :value="model"
          >
            {{ model }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <!-- Temperature Slider -->
    <div class="mb-[24px] w-full">
      <div class="flex items-center justify-between mb-[12px]">
        <div class="text-sm font-medium text-[var(--text-primary)]">{{ t('Temperature') }}</div>
        <span class="text-sm text-[var(--text-tertiary)]">{{ localSettings.temperature.toFixed(1) }}</span>
      </div>
      <input
        type="range"
        min="0"
        max="2"
        step="0.1"
        v-model.number="localSettings.temperature"
        @change="saveSettings"
        class="w-[280px] h-2 bg-[var(--fill-tsp-gray-main)] rounded-lg appearance-none cursor-pointer"
      />
      <div class="flex justify-between w-[280px] text-xs text-[var(--text-tertiary)] mt-1">
        <span>{{ t('Precise') }}</span>
        <span>{{ t('Creative') }}</span>
      </div>
    </div>

    <!-- Max Tokens -->
    <div class="mb-[24px] w-full">
      <div class="text-sm font-medium text-[var(--text-primary)] mb-[12px]">{{ t('Max Tokens') }}</div>
      <input
        type="number"
        v-model.number="localSettings.max_tokens"
        @change="saveSettings"
        min="1000"
        max="32000"
        step="1000"
        class="w-[280px] h-[36px] px-3 rounded-lg border border-[var(--border-main)] bg-transparent text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--Button-primary-black)]"
      />
      <div class="text-xs text-[var(--text-tertiary)] mt-1">
        {{ t('Maximum response length (1000-32000)') }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { getSettings, updateSettings, getProviders, type UserSettings, type ProvidersInfo } from '@/api/settings'

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

// Providers info
const providers = ref<ProvidersInfo>({
  llm_providers: [],
  search_providers: [],
})

// Available models for selected provider
const availableModels = computed(() => {
  const provider = providers.value.llm_providers.find(p => p.id === localSettings.value.llm_provider)
  return provider?.models || []
})

// Load settings and providers on mount
onMounted(async () => {
  try {
    const [settings, providersInfo] = await Promise.all([
      getSettings(),
      getProviders(),
    ])
    localSettings.value = { ...localSettings.value, ...settings }
    providers.value = providersInfo
  } catch (error) {
    console.error('Failed to load settings:', error)
  }
})

// Handle provider change
const onProviderChange = (provider: string) => {
  localSettings.value.llm_provider = provider
  // Reset model to first available for new provider
  const providerInfo = providers.value.llm_providers.find(p => p.id === provider)
  if (providerInfo && providerInfo.models.length > 0) {
    localSettings.value.model_name = providerInfo.models[0]
  }
  saveSettings()
}

// Save settings
const saveSettings = async () => {
  try {
    await updateSettings({
      llm_provider: localSettings.value.llm_provider,
      model_name: localSettings.value.model_name,
      temperature: localSettings.value.temperature,
      max_tokens: localSettings.value.max_tokens,
    })
  } catch (error) {
    console.error('Failed to save settings:', error)
  }
}
</script>
