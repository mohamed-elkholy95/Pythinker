<template>
  <div class="agent-settings">
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon">
          <Bot class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Browser Automation</h4>
          <p class="section-desc">Configure how the AI interacts with web browsers</p>
        </div>
      </div>

      <!-- Browser Max Steps -->
      <div class="setting-block">
        <div class="setting-row-header">
          <div class="setting-label-group">
            <Footprints class="w-4 h-4 text-[var(--icon-tertiary)]" />
            <div class="setting-text">
              <span class="setting-label">{{ t('Browser Max Steps') }}</span>
              <span class="setting-hint">Maximum actions the agent can take (5-100)</span>
            </div>
          </div>
          <span class="setting-value-badge">{{ localSettings.browser_agent_max_steps }}</span>
        </div>
        <div class="slider-container">
          <input
            type="range"
            :min="5"
            :max="100"
            :step="5"
            v-model.number="localSettings.browser_agent_max_steps"
            @change="saveSettings"
            class="settings-slider"
          />
          <div class="slider-markers">
            <span>5</span>
            <span>25</span>
            <span>50</span>
            <span>75</span>
            <span>100</span>
          </div>
        </div>
      </div>

      <!-- Browser Timeout -->
      <div class="setting-block">
        <div class="setting-row-header">
          <div class="setting-label-group">
            <Timer class="w-4 h-4 text-[var(--icon-tertiary)]" />
            <div class="setting-text">
              <span class="setting-label">{{ t('Browser Timeout (seconds)') }}</span>
              <span class="setting-hint">Maximum time for browser operations</span>
            </div>
          </div>
        </div>
        <div class="input-row">
          <div class="input-container">
            <input
              type="number"
              v-model.number="localSettings.browser_agent_timeout"
              @change="saveSettings"
              min="60"
              max="600"
              step="30"
              class="settings-input"
            />
            <span class="input-suffix">seconds</span>
          </div>
          <div class="timeout-presets">
            <button
              v-for="preset in timeoutPresets"
              :key="preset.value"
              @click="setTimeout(preset.value)"
              class="preset-btn"
              :class="{ 'preset-active': localSettings.browser_agent_timeout === preset.value }"
            >
              {{ preset.label }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Vision Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon section-icon-vision">
          <Eye class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Visual Intelligence</h4>
          <p class="section-desc">Enable screenshot analysis for smarter automation</p>
        </div>
      </div>

      <div class="vision-toggle-card" :class="{ 'vision-enabled': localSettings.browser_agent_use_vision }">
        <div class="vision-content">
          <div class="vision-icon-wrapper">
            <ScanEye class="w-6 h-6" />
          </div>
          <div class="vision-info">
            <h5 class="vision-title">{{ t('Use Vision') }}</h5>
            <p class="vision-desc">
              {{ localSettings.browser_agent_use_vision
                ? 'Vision is enabled. The AI can analyze screenshots to understand page content.'
                : 'Enable to allow the AI to analyze screenshots during browser automation.'
              }}
            </p>
          </div>
        </div>
        <button
          @click="toggleVision"
          class="toggle-switch"
          :class="{ 'toggle-active': localSettings.browser_agent_use_vision }"
        >
          <span class="toggle-thumb"></span>
        </button>
      </div>

      <div class="vision-features" v-if="localSettings.browser_agent_use_vision">
        <div class="feature-item">
          <CheckCircle2 class="w-4 h-4 text-[var(--function-success)]" />
          <span>Visual element detection</span>
        </div>
        <div class="feature-item">
          <CheckCircle2 class="w-4 h-4 text-[var(--function-success)]" />
          <span>Layout understanding</span>
        </div>
        <div class="feature-item">
          <CheckCircle2 class="w-4 h-4 text-[var(--function-success)]" />
          <span>Content verification</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Bot,
  Footprints,
  Timer,
  Eye,
  ScanEye,
  CheckCircle2
} from 'lucide-vue-next'
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

// Timeout presets
const timeoutPresets = [
  { label: '1m', value: 60 },
  { label: '3m', value: 180 },
  { label: '5m', value: 300 },
  { label: '10m', value: 600 },
]

// Load settings on mount
onMounted(async () => {
  try {
    const settings = await getSettings()
    localSettings.value = { ...localSettings.value, ...settings }
  } catch (error) {
    console.error('Failed to load settings:', error)
  }
})

// Set timeout from preset
const setTimeout = (value: number) => {
  localSettings.value.browser_agent_timeout = value
  saveSettings()
}

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

<style scoped>
.agent-settings {
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

.section-icon-vision {
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
  margin-bottom: 16px;
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
  min-width: 40px;
  text-align: center;
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

.slider-markers {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-tertiary);
  padding: 0 2px;
}

.input-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.input-container {
  position: relative;
  width: 160px;
}

.settings-input {
  width: 100%;
  height: 40px;
  padding: 0 70px 0 14px;
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

.timeout-presets {
  display: flex;
  gap: 6px;
}

.preset-btn {
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.preset-btn:hover {
  background: var(--fill-tsp-white-dark);
  border-color: var(--border-main);
}

.preset-active {
  background: var(--fill-blue);
  color: var(--text-brand);
  border-color: transparent;
}

/* Vision Toggle Card */
.vision-toggle-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  transition: all 0.3s ease;
}

.vision-enabled {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.05) 0%, rgba(168, 85, 247, 0.02) 100%);
  border-color: rgba(168, 85, 247, 0.2);
}

.vision-content {
  display: flex;
  align-items: center;
  gap: 14px;
}

.vision-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  background: rgba(168, 85, 247, 0.1);
  border-radius: 12px;
  color: #a855f7;
  flex-shrink: 0;
}

.vision-info {
  flex: 1;
}

.vision-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.vision-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.4;
  max-width: 280px;
}

.toggle-switch {
  position: relative;
  width: 48px;
  height: 28px;
  background: var(--fill-tsp-gray-dark);
  border-radius: 14px;
  transition: all 0.3s ease;
  flex-shrink: 0;
}

.toggle-active {
  background: #a855f7;
}

.toggle-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 22px;
  height: 22px;
  background: #fff;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
  transition: transform 0.3s ease;
}

.toggle-active .toggle-thumb {
  transform: translateX(20px);
}

/* Vision Features */
.vision-features {
  display: flex;
  gap: 16px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-light);
  animation: fadeIn 0.3s ease-out;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
