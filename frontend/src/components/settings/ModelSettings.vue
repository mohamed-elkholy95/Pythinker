<template>
  <div class="model-settings">
    <!-- Provider & Model Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon">
          <Sparkles class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">AI Configuration</h4>
          <p class="section-desc">Select your AI provider and model for conversations</p>
        </div>
      </div>

      <!-- LLM Provider -->
      <div class="setting-row">
        <div class="setting-label-group">
          <Server class="w-4 h-4 text-[var(--icon-tertiary)]" />
          <div class="setting-text">
            <span class="setting-label">{{ t('LLM Provider') }}</span>
            <span class="setting-hint">Choose your preferred AI service</span>
          </div>
        </div>
        <Select v-model="localSettings.llm_provider" @update:modelValue="onProviderChange">
          <SelectTrigger class="settings-select">
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
      <div class="setting-row">
        <div class="setting-label-group">
          <Cpu class="w-4 h-4 text-[var(--icon-tertiary)]" />
          <div class="setting-text">
            <span class="setting-label">{{ t('Model') }}</span>
            <span class="setting-hint">Select the AI model to use</span>
          </div>
        </div>
        <Select v-model="localSettings.model_name" @update:modelValue="saveSettings">
          <SelectTrigger class="settings-select">
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
    </div>

    <!-- Parameters Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon section-icon-secondary">
          <SlidersHorizontal class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Model Parameters</h4>
          <p class="section-desc">Fine-tune the AI response behavior</p>
        </div>
      </div>

      <!-- Temperature Slider -->
      <div class="setting-block">
        <div class="setting-row-header">
          <div class="setting-label-group">
            <Thermometer class="w-4 h-4 text-[var(--icon-tertiary)]" />
            <div class="setting-text">
              <label class="setting-label" for="model-temperature">{{ t('Temperature') }}</label>
              <span class="setting-hint">Controls randomness in responses</span>
            </div>
          </div>
          <span class="setting-value-badge">{{ localSettings.temperature.toFixed(1) }}</span>
        </div>
        <div class="slider-container">
          <input
            type="range"
            id="model-temperature"
            name="temperature"
            min="0"
            max="2"
            step="0.1"
            v-model.number="localSettings.temperature"
            @change="saveSettings"
            class="settings-slider"
            :aria-valuetext="`${localSettings.temperature.toFixed(1)} - ${localSettings.temperature <= 0.3 ? 'Precise' : localSettings.temperature >= 1.5 ? 'Creative' : 'Balanced'}`"
          />
          <div class="slider-labels">
            <span>{{ t('Precise') }}</span>
            <span>{{ t('Creative') }}</span>
          </div>
        </div>
      </div>

      <!-- Max Tokens -->
      <div class="setting-block">
        <div class="setting-row-header">
          <div class="setting-label-group">
            <Hash class="w-4 h-4 text-[var(--icon-tertiary)]" />
            <div class="setting-text">
              <label class="setting-label" for="model-max-tokens">{{ t('Max Tokens') }}</label>
              <span class="setting-hint">Maximum response length (1000-32000)</span>
            </div>
          </div>
        </div>
        <div class="input-container">
          <input
            type="number"
            id="model-max-tokens"
            name="max_tokens"
            v-model.number="localSettings.max_tokens"
            @change="saveSettings"
            min="1000"
            max="32000"
            step="1"
            class="settings-input"
          />
          <span class="input-suffix">tokens</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { showErrorToast } from '@/utils/toast'
import {
  Sparkles,
  Server,
  Cpu,
  SlidersHorizontal,
  Thermometer,
  Hash
} from 'lucide-vue-next'
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
  response_verbosity_preference: 'adaptive',
  clarification_policy: 'auto',
  quality_floor_enforced: true,
  skill_auto_trigger_enabled: false,
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
  } catch {
    // Settings load failed - using defaults
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
  } catch {
    showErrorToast(t('Failed to save settings'))
  }
}
</script>

<style scoped>
.model-settings {
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

.section-icon-secondary {
  background: rgba(168, 85, 247, 0.1);
  color: #a855f7;
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

.setting-row:not(:last-child) {
  border-bottom: 1px solid var(--border-light);
}

.setting-block {
  padding: 12px 0;
}

.setting-block:not(:last-child) {
  border-bottom: 1px solid var(--border-light);
}

.setting-row-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
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

.setting-value-badge {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-brand);
  background: var(--fill-blue);
  padding: 4px 10px;
  border-radius: 6px;
}

.settings-select {
  width: 200px;
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

.provider-badge {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}

.provider-openai {
  background: linear-gradient(135deg, #10a37f 0%, #1a7f64 100%);
}

.provider-anthropic {
  background: linear-gradient(135deg, #d97757 0%, #c4624a 100%);
}

.provider-google {
  background: linear-gradient(135deg, #4285f4 0%, #3367d6 100%);
}

.provider-azure {
  background: linear-gradient(135deg, #0078d4 0%, #005a9e 100%);
}

.provider-default {
  background: var(--fill-tsp-gray-dark);
}

.slider-container {
  padding: 0 4px;
}

.settings-slider {
  width: 100%;
  height: 6px;
  background: var(--fill-tsp-white-dark);
  border-radius: 3px;
  appearance: none;
  cursor: pointer;
  margin-bottom: 8px;
}

.settings-slider::-webkit-slider-thumb {
  appearance: none;
  width: 18px;
  height: 18px;
  background: var(--text-brand);
  border-radius: 50%;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.3);
  transition: transform 0.15s ease;
}

.settings-slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.settings-slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  background: var(--text-brand);
  border-radius: 50%;
  cursor: pointer;
  border: none;
  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.3);
}

.slider-labels {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-tertiary);
}

.input-container {
  position: relative;
  width: 200px;
}

.settings-input {
  width: 100%;
  height: 40px;
  padding: 0 60px 0 14px;
  border-radius: 10px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  transition: all 0.2s ease;
}

.settings-input:hover {
  border-color: var(--border-dark);
}

.settings-input:focus {
  outline: none;
  border-color: var(--text-brand);
  box-shadow: 0 0 0 3px var(--fill-blue);
}

.input-suffix {
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 12px;
  color: var(--text-tertiary);
  pointer-events: none;
}
</style>
