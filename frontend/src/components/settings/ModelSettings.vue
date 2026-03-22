<template>
  <div class="model-settings">
    <!-- Active Model Banner -->
    <div class="active-config-banner">
      <div class="active-config-dot" />
      <div class="active-config-info">
        <span class="active-config-label">Active Model</span>
        <span class="active-config-value">
          {{ displayModelName || 'Loading...' }}
        </span>
      </div>
    </div>

    <!-- Model & Parameters Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon">
          <Sparkles class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">AI Configuration</h4>
          <p class="section-desc">Current model and response behavior settings</p>
        </div>
      </div>

      <!-- Model -->
      <div class="setting-row">
        <div class="setting-label-group">
          <Cpu class="w-4 h-4 text-[var(--icon-tertiary)]" />
          <div class="setting-text">
            <span class="setting-label">{{ t('Model') }}</span>
            <span class="setting-hint">Active AI model</span>
          </div>
        </div>
        <div class="readonly-value">
          {{ displayModelName || 'Not configured' }}
        </div>
      </div>

      <!-- Temperature -->
      <div class="setting-row">
        <div class="setting-label-group">
          <Thermometer class="w-4 h-4 text-[var(--icon-tertiary)]" />
          <div class="setting-text">
            <span class="setting-label">{{ t('Temperature') }}</span>
            <span class="setting-hint">Controls randomness in responses</span>
          </div>
        </div>
        <span class="setting-value-badge">
          {{ serverConfig.temperature.toFixed(1) }}
          <span class="value-label">{{ serverConfig.temperature <= 0.3 ? 'Precise' : serverConfig.temperature >= 1.5 ? 'Creative' : 'Balanced' }}</span>
        </span>
      </div>

      <!-- Max Tokens -->
      <div class="setting-row">
        <div class="setting-label-group">
          <Hash class="w-4 h-4 text-[var(--icon-tertiary)]" />
          <div class="setting-text">
            <span class="setting-label">{{ t('Max Tokens') }}</span>
            <span class="setting-hint">Maximum response length</span>
          </div>
        </div>
        <span class="setting-value-badge">
          {{ serverConfig.max_tokens.toLocaleString() }}
          <span class="value-label">tokens</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Sparkles,
  Cpu,
  Thermometer,
  Hash,
} from 'lucide-vue-next'
import { getServerConfig, type ServerConfig } from '@/api/settings'

const { t } = useI18n()

const serverConfig = ref<ServerConfig>({
  model_name: '',
  model_display_name: '',
  api_base: '',
  temperature: 0.6,
  max_tokens: 8192,
  llm_provider: 'auto',
  search_provider: '',
  search_provider_chain: [],
  configured_search_keys: [],
})

const displayModelName = computed(() => {
  return serverConfig.value.model_display_name?.trim() || serverConfig.value.model_name || ''
})

onMounted(async () => {
  try {
    serverConfig.value = await getServerConfig()
  } catch {
    // Settings load failed - using defaults
  }
})
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

/* ── Active Configuration Banner ────────────────────────────── */
.active-config-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(59, 130, 246, 0.06) 100%);
  border: 1px solid rgba(16, 185, 129, 0.2);
  border-radius: 12px;
}

.active-config-dot {
  width: 8px;
  height: 8px;
  background: #10b981;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.4);
  animation: pulse-dot 2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.active-config-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.active-config-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #10b981;
}

.active-config-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

/* ── Section Card ──────────────────────────────────────────── */
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

/* ── Setting Rows ───────────────────────────────────────────── */
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

/* ── Read-only Value Display ───────────────────────────────── */
.readonly-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  background: var(--fill-tsp-white-dark);
  padding: 8px 14px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Value Label (unit/descriptor inside badge) ────────────── */
.value-label {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-tertiary);
  margin-left: 4px;
}
</style>
