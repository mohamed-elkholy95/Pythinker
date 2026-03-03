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
              <label class="setting-label" for="agent-browser-max-steps">{{ t('Browser Max Steps') }}</label>
              <span class="setting-hint">Maximum actions the agent can take (5-100)</span>
            </div>
          </div>
          <span class="setting-value-badge">{{ localSettings.browser_agent_max_steps }}</span>
        </div>
        <div class="slider-container">
          <input
            type="range"
            id="agent-browser-max-steps"
            name="browser_agent_max_steps"
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
              <label class="setting-label" for="agent-browser-timeout">{{ t('Browser Timeout (seconds)') }}</label>
              <span class="setting-hint">Maximum time for browser operations</span>
            </div>
          </div>
        </div>
        <div class="input-row">
          <div class="input-container">
            <input
              type="number"
              id="agent-browser-timeout"
              name="browser_agent_timeout"
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
              @click="setBrowserTimeoutPreset(preset.value)"
              class="preset-btn"
              :class="{ 'preset-active': localSettings.browser_agent_timeout === preset.value }"
            >
              {{ preset.label }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Telegram Setup Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon section-icon-telegram">
          <MessageSquare class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Telegram Agent Setup</h4>
          <p class="section-desc">Link your Telegram account and continue conversations from Telegram or web</p>
        </div>
      </div>

      <div class="telegram-steps">
        <div class="telegram-step">
          <span class="telegram-step-index">1</span>
          <div class="telegram-step-copy">
            <p class="telegram-step-title">Generate your one-time bind code</p>
            <p class="telegram-step-text">Click <strong>Link Account</strong> to open the bot and create your setup command.</p>
          </div>
        </div>
        <div class="telegram-step">
          <span class="telegram-step-index">2</span>
          <div class="telegram-step-copy">
            <p class="telegram-step-title">Send the bind command in Telegram</p>
            <p class="telegram-step-text">Your code expires in 30 minutes and can only be used by your signed-in account.</p>
          </div>
        </div>
        <div class="telegram-step">
          <span class="telegram-step-index">3</span>
          <div class="telegram-step-copy">
            <p class="telegram-step-title">Continue chat in your own task list</p>
            <p class="telegram-step-text">After linking, Telegram sessions are attached to your user and appear in your sidebar tasks.</p>
          </div>
        </div>
      </div>

      <div class="telegram-status-row">
        <div class="telegram-status-meta">
          <span class="telegram-status-label">Status</span>
          <span
            class="telegram-status-value"
            :class="{
              'telegram-status-value-linked': isTelegramLinked,
              'telegram-status-value-pending': !isTelegramLinked && !!bindCommand
            }"
          >
            <template v-if="isTelegramLinked">
              Connected
            </template>
            <template v-else-if="bindCommand">
              Activation pending
            </template>
            <template v-else>
              Not connected
            </template>
          </span>
          <span v-if="isTelegramLinked && telegramLinkedSender" class="telegram-status-sender">
            {{ telegramLinkedSender }}
          </span>
        </div>
        <div class="telegram-status-actions">
          <button
            class="telegram-inline-btn"
            :disabled="isRefreshing"
            @click="handleRefreshStatus"
          >
            <Loader2 v-if="isRefreshing" class="w-3.5 h-3.5 animate-spin" />
            <RefreshCw v-else class="w-3.5 h-3.5" />
            Refresh
          </button>
          <button v-if="isTelegramLinked"
            class="telegram-primary-btn telegram-primary-btn-linked"
            @click="openTelegramHistory"
          >
            <MessageSquare class="w-3.5 h-3.5" />
            Open Task List
          </button>
        </div>
      </div>

      <TelegramLinkCard
        v-if="!isTelegramLinked"
        :is-generating="isGenerating"
        :has-draft="Boolean(bindCommand)"
        :active-command="activeCommand"
        :is-copied="isCopied"
        :countdown="countdown"
        :feedback="channelConnectFeedback"
        :error="channelConnectError"
        primary-label="Link Account"
        @generate="generate"
        @copy="copyCommand"
        @open="openDeepLink"
      />

      <div v-if="isTelegramLinked && channelConnectFeedback" class="telegram-feedback">
        <Check class="w-3.5 h-3.5" />
        <span>{{ channelConnectFeedback }}</span>
      </div>
      <div v-if="isTelegramLinked && channelConnectError" class="telegram-error">
        <AlertCircle class="w-3.5 h-3.5" />
        <span>{{ channelConnectError }}</span>
      </div>
    </div>

    <!-- Response Behavior Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon">
          <Bot class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Response Behavior</h4>
          <p class="section-desc">Control answer length and clarification behavior</p>
        </div>
      </div>

      <div class="setting-block">
        <div class="setting-row-header">
          <div class="setting-label-group">
            <div class="setting-text">
              <label class="setting-label" for="agent-response-verbosity">Response Verbosity</label>
              <span class="setting-hint">Adaptive keeps answers short unless task risk/complexity is high</span>
            </div>
          </div>
        </div>
        <div class="input-container">
          <select
            id="agent-response-verbosity"
            name="response_verbosity_preference"
            v-model="localSettings.response_verbosity_preference"
            @change="saveSettings"
            class="settings-input"
          >
            <option value="adaptive">Adaptive</option>
            <option value="concise">Concise</option>
            <option value="detailed">Detailed</option>
          </select>
        </div>
      </div>

      <div class="setting-block">
        <div class="setting-row-header">
          <div class="setting-label-group">
            <div class="setting-text">
              <label class="setting-label" for="agent-clarification-policy">Clarification Policy</label>
              <span class="setting-hint">Choose when the agent pauses to ask follow-up questions</span>
            </div>
          </div>
        </div>
        <div class="input-container">
          <select
            id="agent-clarification-policy"
            name="clarification_policy"
            v-model="localSettings.clarification_policy"
            @change="saveSettings"
            class="settings-input"
          >
            <option value="auto">Auto</option>
            <option value="always">Always ask</option>
            <option value="never">Never ask</option>
          </select>
        </div>
      </div>

      <div class="vision-toggle-card" :class="{ 'vision-enabled': localSettings.quality_floor_enforced }">
        <div class="vision-content">
          <div class="vision-info">
            <h5 class="vision-title">Quality Floor</h5>
            <p class="vision-desc">
              Keep enabled to prevent concise output from dropping critical details.
            </p>
          </div>
        </div>
        <button
          @click="toggleQualityFloor"
          class="toggle-switch"
          :class="{ 'toggle-active': localSettings.quality_floor_enforced }"
        >
          <span class="toggle-thumb"></span>
        </button>
      </div>

      <div class="vision-toggle-card" :class="{ 'vision-enabled': localSettings.skill_auto_trigger_enabled }">
        <div class="vision-content">
          <div class="vision-info">
            <h5 class="vision-title">Skill Auto-Trigger</h5>
            <p class="vision-desc">
              Automatically activate matching skills from message text. Keep off for explicit-only activation.
            </p>
          </div>
        </div>
        <button
          @click="toggleSkillAutoTrigger"
          class="toggle-switch"
          :class="{ 'toggle-active': localSettings.skill_auto_trigger_enabled }"
        >
          <span class="toggle-thumb"></span>
        </button>
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
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showErrorToast } from '@/utils/toast'
import {
  Bot,
  Footprints,
  Timer,
  Eye,
  ScanEye,
  CheckCircle2,
  MessageSquare,
  RefreshCw,
  Loader2,
  Check,
  AlertCircle
} from 'lucide-vue-next'
import { getSettings, updateSettings, type UserSettings } from '@/api/settings'
import { useTelegramLink } from '@/composables/useTelegramLink'
import TelegramLinkCard from '@/components/telegram/TelegramLinkCard.vue'

const { t } = useI18n()
const router = useRouter()

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

// Timeout presets
const timeoutPresets = [
  { label: '1m', value: 60 },
  { label: '3m', value: 180 },
  { label: '5m', value: 300 },
  { label: '10m', value: 600 },
]

// ── Telegram composable ──
const {
  isTelegramLinked,
  isGenerating,
  bindCommand,
  activeCommand,
  isCopied,
  error: channelConnectError,
  feedback: channelConnectFeedback,
  countdown,
  senderDisplay,
  generate,
  copyCommand,
  openDeepLink,
  loadChannels,
} = useTelegramLink()

const isRefreshing = ref(false)

const telegramLinkedSender = computed(() => {
  const raw = senderDisplay.value
  return raw ? `as ${raw}` : ''
})

const loadAgentSettings = async () => {
  try {
    const settings = await getSettings()
    localSettings.value = { ...localSettings.value, ...settings }
  } catch {
    // Settings load failed - using defaults
  }
}

// Set timeout from preset
const setBrowserTimeoutPreset = (value: number) => {
  localSettings.value.browser_agent_timeout = value
  saveSettings()
}

// Toggle vision setting
const toggleVision = async () => {
  localSettings.value.browser_agent_use_vision = !localSettings.value.browser_agent_use_vision
  await saveSettings()
}

const toggleQualityFloor = async () => {
  localSettings.value.quality_floor_enforced = !localSettings.value.quality_floor_enforced
  await saveSettings()
}

const toggleSkillAutoTrigger = async () => {
  localSettings.value.skill_auto_trigger_enabled = !localSettings.value.skill_auto_trigger_enabled
  await saveSettings()
}

const handleRefreshStatus = async () => {
  isRefreshing.value = true
  try {
    await loadChannels()
  } finally {
    isRefreshing.value = false
  }
}

const openTelegramHistory = () => {
  void router.push('/chat/agents')
}

// Save settings
const saveSettings = async () => {
  try {
    await updateSettings({
      browser_agent_max_steps: localSettings.value.browser_agent_max_steps,
      browser_agent_timeout: localSettings.value.browser_agent_timeout,
      browser_agent_use_vision: localSettings.value.browser_agent_use_vision,
      response_verbosity_preference: localSettings.value.response_verbosity_preference,
      clarification_policy: localSettings.value.clarification_policy,
      quality_floor_enforced: localSettings.value.quality_floor_enforced,
      skill_auto_trigger_enabled: localSettings.value.skill_auto_trigger_enabled,
    })
  } catch {
    showErrorToast(t('Failed to save settings'))
  }
}

onMounted(async () => {
  await loadAgentSettings()
  await loadChannels()
})
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

.section-icon-telegram {
  background: rgba(0, 136, 204, 0.12);
  color: #0088cc;
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

.telegram-steps {
  display: grid;
  gap: 10px;
  margin-bottom: 14px;
}

.telegram-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
}

.telegram-step-index {
  width: 20px;
  height: 20px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-brand);
  background: var(--fill-blue);
  flex-shrink: 0;
  margin-top: 1px;
}

.telegram-step-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.telegram-step-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.telegram-step-text {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.4;
}

.telegram-status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.telegram-status-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.telegram-status-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
}

.telegram-status-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.telegram-status-value-linked {
  color: var(--function-success);
}

.telegram-status-value-pending {
  color: #f59e0b;
}

.telegram-status-sender {
  font-size: 12px;
  color: var(--text-tertiary);
}

.telegram-status-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.telegram-inline-btn,
.telegram-primary-btn {
  height: 34px;
  border-radius: 9px;
  font-size: 12px;
  font-weight: 600;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s ease;
}

.telegram-inline-btn {
  border: 1px solid var(--border-main);
  color: var(--text-secondary);
  background: var(--fill-tsp-white-main);
}

.telegram-inline-btn:hover {
  border-color: var(--border-dark);
  color: var(--text-primary);
}

.telegram-primary-btn {
  border: 1px solid transparent;
  color: #fff;
  background: #0088cc;
}

.telegram-primary-btn:hover {
  background: #0078b4;
}

.telegram-primary-btn-linked {
  background: var(--function-success);
}

.telegram-primary-btn-linked:hover {
  background: #0f9a6e;
}

.telegram-inline-btn:disabled,
.telegram-primary-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.telegram-code-panel {
  margin-top: 12px;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 12px;
  background: var(--background-white-main);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.telegram-code-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.telegram-code-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.telegram-code-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.telegram-code-value {
  flex: 1;
  min-width: 0;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: var(--fill-tsp-white-main);
  color: var(--text-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.5;
  padding: 8px 10px;
  overflow-x: auto;
}

.telegram-copy-btn {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.telegram-copy-btn:hover {
  border-color: var(--border-dark);
  color: var(--text-primary);
}

.telegram-countdown {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: fit-content;
  border-radius: 999px;
  border: 1px solid var(--border-light);
  background: var(--fill-tsp-white-main);
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  color: #f59e0b;
}

.telegram-feedback,
.telegram-error {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 11px;
  border-radius: 8px;
  font-size: 12px;
}

.telegram-feedback {
  color: var(--function-success);
  background: var(--function-success-tsp);
  border: 1px solid var(--function-success-border);
}

.telegram-error {
  color: var(--function-error);
  background: var(--function-error-tsp);
  border: 1px solid rgba(239, 68, 68, 0.22);
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
