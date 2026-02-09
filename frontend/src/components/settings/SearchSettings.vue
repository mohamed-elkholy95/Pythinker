<template>
  <div class="search-settings">
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon">
          <Search class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Search Engine</h4>
          <p class="section-desc">Configure how the AI searches the web for information</p>
        </div>
      </div>

      <!-- Search Provider -->
      <div class="setting-row">
        <div class="setting-label-group">
          <Globe class="w-4 h-4 text-[var(--icon-tertiary)]" />
          <div class="setting-text">
            <span class="setting-label">{{ t('Search Provider') }}</span>
            <span class="setting-hint">Choose your web search service</span>
          </div>
        </div>
        <Select v-model="localSettings.search_provider" @update:modelValue="saveSettings">
          <SelectTrigger class="settings-select">
            <SelectValue :placeholder="t('Select search provider')" />
          </SelectTrigger>
          <SelectContent :side-offset="5">
            <SelectItem
              v-for="provider in providers.search_providers"
              :key="provider.id"
              :value="provider.id"
            >
              <div class="select-option">
                <div class="search-provider-icon" :class="getProviderClass(provider.id)">
                  <component :is="getProviderIcon(provider.id)" class="w-3.5 h-3.5" />
                </div>
                <div class="select-option-content">
                  <span class="select-option-name">{{ provider.name }}</span>
                  <span v-if="provider.requires_api_key" class="select-option-badge">API Key</span>
                </div>
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <!-- Provider Info Card -->
      <Transition name="fade">
        <div class="provider-info-card" v-if="selectedProviderInfo">
          <div class="provider-info-icon" :class="getProviderClass(localSettings.search_provider)">
            <component :is="getProviderIcon(localSettings.search_provider)" class="w-5 h-5" />
          </div>
          <div class="provider-info-content">
            <h5 class="provider-info-name">{{ selectedProviderInfo.name }}</h5>
            <p class="provider-info-desc">{{ providerDescription }}</p>
            <div class="provider-info-tags">
              <span class="info-tag" :class="selectedProviderInfo.requires_api_key ? 'tag-warning' : 'tag-success'">
                {{ selectedProviderInfo.requires_api_key ? 'Requires API Key' : 'No API Key Required' }}
              </span>
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Search,
  Globe,
  Shield,
  Zap,
  Cloud
} from 'lucide-vue-next'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { getSettings, updateSettings, getProviders, type UserSettings, type ProvidersInfo } from '@/api/settings'
import { showErrorToast } from '@/utils/toast'

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
  deep_research_auto_run: false,
  response_verbosity_preference: 'adaptive',
  clarification_policy: 'auto',
  quality_floor_enforced: true,
})

// Providers info
const providers = ref<ProvidersInfo>({
  llm_providers: [],
  search_providers: [],
})

// Provider descriptions
const providerDescriptions: Record<string, string> = {
  bing: 'Microsoft Bing Search API with comprehensive web results',
  google: 'Google Custom Search for precise and relevant results',
  duckduckgo: 'Privacy-focused search that doesn\'t track you',
  brave: 'Independent search with privacy-preserving features',
  baidu: 'Chinese-language search optimized for local content',
  tavily: 'AI-powered search designed for LLM applications',
  serper: 'Google Search results via Serper.dev API (2500 free/mo)',
}

// Provider icons mapping
const getProviderIcon = (providerId: string) => {
  const icons: Record<string, Component> = {
    bing: Globe,
    google: Search,
    duckduckgo: Shield,
    brave: Shield,
    baidu: Globe,
    tavily: Zap,
    serper: Search,
  }
  return icons[providerId] || Cloud
}

// Get provider class for styling
const getProviderClass = (providerId: string) => {
  const classes: Record<string, string> = {
    bing: 'provider-bing',
    google: 'provider-google',
    duckduckgo: 'provider-duckduckgo',
    brave: 'provider-brave',
    baidu: 'provider-baidu',
    tavily: 'provider-tavily',
    serper: 'provider-serper',
  }
  return classes[providerId] || 'provider-default'
}

const selectedProviderInfo = computed(() => {
  return providers.value.search_providers.find(p => p.id === localSettings.value.search_provider)
})

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
  } catch {
    // Settings load failed - using defaults
  }
})

// Save settings
const saveSettings = async (value: string) => {
  localSettings.value.search_provider = value
  try {
    await updateSettings({
      search_provider: localSettings.value.search_provider,
    })
  } catch {
    showErrorToast(t('Failed to save settings'))
  }
}
</script>

<style scoped>
.search-settings {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.section-card {
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 20px;
}

.section-header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-light);
}

.section-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: var(--fill-blue);
  border-radius: 10px;
  color: var(--text-brand);
  flex-shrink: 0;
}

.section-info {
  flex: 1;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.section-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
}

.setting-label-group {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex: 1;
}

.setting-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.setting-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.setting-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.settings-select {
  width: 220px;
  height: 40px;
  border-radius: 10px;
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  font-size: 14px;
  transition: all 0.2s ease;
}

.settings-select:hover {
  border-color: var(--border-dark);
}

.select-option {
  display: flex;
  align-items: center;
  gap: 10px;
}

.select-option-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.select-option-name {
  font-size: 14px;
}

.select-option-badge {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-tertiary);
  background: var(--fill-tsp-white-dark);
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}

.search-provider-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  color: #fff;
  flex-shrink: 0;
}

.provider-bing { background: linear-gradient(135deg, #00809d 0%, #006a82 100%); }
.provider-google { background: linear-gradient(135deg, #4285f4 0%, #3367d6 100%); }
.provider-duckduckgo { background: linear-gradient(135deg, #de5833 0%, #c74a29 100%); }
.provider-brave { background: linear-gradient(135deg, #fb542b 0%, #e04422 100%); }
.provider-baidu { background: linear-gradient(135deg, #2932e1 0%, #1f26b8 100%); }
.provider-tavily { background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%); }
.provider-serper { background: linear-gradient(135deg, #4285f4 0%, #2b6cb0 100%); }
.provider-default { background: var(--fill-tsp-gray-dark); }

/* Provider Info Card */
.provider-info-card {
  display: flex;
  gap: 16px;
  padding: 16px;
  margin-top: 16px;
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  border-radius: 12px;
}

.provider-info-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  color: #fff;
  flex-shrink: 0;
}

.provider-info-content {
  flex: 1;
  min-width: 0;
}

.provider-info-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.provider-info-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
  margin-bottom: 10px;
}

.provider-info-tags {
  display: flex;
  gap: 8px;
}

.info-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 6px;
}

.tag-success {
  background: rgba(34, 197, 94, 0.1);
  color: var(--function-success);
}

.tag-warning {
  background: var(--function-warning-tsp);
  color: var(--function-warning);
}

/* Fade transition */
.fade-enter-active,
.fade-leave-active {
  transition: all 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
