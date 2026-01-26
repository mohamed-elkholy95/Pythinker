<template>
  <div class="pb-[32px] last:pb-0 border-b border-[var(--border-light)] last-of-type:border-transparent w-full">
    <div class="text-[13px] font-medium text-[var(--text-tertiary)] mb-1 w-full">{{ t('Search') }}</div>

    <!-- Search Provider Selection -->
    <div class="mb-[24px] w-full">
      <div class="text-sm font-medium text-[var(--text-primary)] mb-[12px]">{{ t('Search Provider') }}</div>
      <Select v-model="localSettings.search_provider" @update:modelValue="saveSettings">
        <SelectTrigger class="w-[280px] h-[36px]">
          <SelectValue :placeholder="t('Select search provider')" />
        </SelectTrigger>
        <SelectContent :side-offset="5">
          <SelectItem
            v-for="provider in providers.search_providers"
            :key="provider.id"
            :value="provider.id"
          >
            <div class="flex items-center gap-2">
              <span>{{ provider.name }}</span>
              <span v-if="provider.requires_api_key" class="text-xs text-[var(--text-tertiary)]">({{ t('API key required') }})</span>
            </div>
          </SelectItem>
        </SelectContent>
      </Select>
      <div class="text-xs text-[var(--text-tertiary)] mt-2">
        {{ providerDescription }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
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

// Provider descriptions
const providerDescriptions: Record<string, string> = {
  bing: 'Microsoft Bing Search API - No API key required',
  google: 'Google Custom Search API - Requires API key and search engine ID',
  duckduckgo: 'Privacy-focused search - No API key required',
  brave: 'Brave Search API - Requires API key',
  searxng: 'Self-hosted metasearch engine - No API key required',
  whoogle: 'Google proxy search - No API key required',
  baidu: 'Baidu Search for Chinese content - No API key required',
  tavily: 'AI-powered search API - Requires API key',
}

const providerDescription = computed(() => {
  return providerDescriptions[localSettings.value.search_provider] || ''
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

// Save settings
const saveSettings = async (value: string) => {
  localSettings.value.search_provider = value
  try {
    await updateSettings({
      search_provider: localSettings.value.search_provider,
    })
  } catch (error) {
    console.error('Failed to save settings:', error)
  }
}
</script>
