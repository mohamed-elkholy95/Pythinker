<template>
  <div class="search-settings">
    <!-- Active Search Configuration (from server env) -->
    <div class="active-config-banner">
      <div class="active-config-dot" />
      <div class="active-config-info">
        <span class="active-config-label">Active Search Engine</span>
        <span class="active-config-value">
          {{ capitalize(serverConfig.search_provider) }}
          <template v-if="serverConfig.search_provider_chain.length > 1">
            <span class="active-config-sep">&middot;</span>
            <span class="active-config-chain">
              Chain: {{ serverConfig.search_provider_chain.join(' → ') }}
            </span>
          </template>
        </span>
      </div>
    </div>

    <!-- Mismatch warning -->
    <div v-if="hasSearchMismatch" class="mismatch-warning">
      <TriangleAlert class="w-4 h-4 flex-shrink-0" />
      <div class="mismatch-content">
        <span class="mismatch-title">Configuration mismatch</span>
        <span class="mismatch-text">
          Your saved preference ({{ capitalize(localSettings.search_provider) }}) differs from the server's
          active search engine ({{ capitalize(serverConfig.search_provider) }}). Update <code>.env</code>
          <code>SEARCH_PROVIDER</code> and restart.
        </span>
      </div>
    </div>

    <!-- Search Provider Selection -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon">
          <Search class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Search Provider</h4>
          <p class="section-desc">Choose which search engine the AI uses for web queries</p>
        </div>
      </div>

      <!-- Provider Selector -->
      <div class="setting-row">
        <div class="setting-label-group">
          <Globe class="w-4 h-4 text-[var(--icon-tertiary)]" />
          <div class="setting-text">
            <span class="setting-label">Primary Provider</span>
            <span class="setting-hint">The first engine tried for every search</span>
          </div>
        </div>
        <Select v-model="localSettings.search_provider" @update:modelValue="onProviderChange">
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
                <div class="search-provider-icon" :class="`provider-${provider.id}`">
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

      <!-- Selected Provider Info Card -->
      <Transition name="fade">
        <div v-if="selectedProviderInfo" class="provider-info-card">
          <div class="provider-info-icon" :class="`provider-${localSettings.search_provider}`">
            <component :is="getProviderIcon(localSettings.search_provider)" class="w-5 h-5" />
          </div>
          <div class="provider-info-content">
            <h5 class="provider-info-name">{{ selectedProviderInfo.name }}</h5>
            <p class="provider-info-desc">{{ providerDescription }}</p>
            <div class="provider-info-tags">
              <span
                class="info-tag"
                :class="isKeyConfigured(localSettings.search_provider) ? 'tag-success' : (selectedProviderInfo.requires_api_key ? 'tag-warning' : 'tag-success')"
              >
                <template v-if="!selectedProviderInfo.requires_api_key">
                  No API Key Required
                </template>
                <template v-else-if="isKeyConfigured(localSettings.search_provider)">
                  API Key Configured
                </template>
                <template v-else>
                  API Key Missing
                </template>
              </span>
            </div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- Fallback Chain Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon section-icon-chain">
          <ArrowRightLeft class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Fallback Chain</h4>
          <p class="section-desc">When the primary provider fails, these engines are tried in order</p>
        </div>
      </div>

      <div class="chain-list">
        <div
          v-for="(provider, index) in serverConfig.search_provider_chain"
          :key="provider"
          class="chain-item"
        >
          <div class="chain-rank">{{ index + 1 }}</div>
          <div class="chain-provider-icon" :class="`provider-${provider}`">
            <component :is="getProviderIcon(provider)" class="w-3.5 h-3.5" />
          </div>
          <span class="chain-name">{{ capitalize(provider) }}</span>
          <span
            class="chain-status"
            :class="isKeyConfigured(provider) || !requiresKey(provider) ? 'chain-status-ready' : 'chain-status-missing'"
          >
            {{ isKeyConfigured(provider) || !requiresKey(provider) ? 'Ready' : 'No key' }}
          </span>
          <ArrowRight v-if="index < serverConfig.search_provider_chain.length - 1" class="w-3.5 h-3.5 text-[var(--icon-tertiary)] flex-shrink-0" />
        </div>
      </div>

      <div v-if="serverConfig.search_provider_chain.length === 0" class="chain-empty">
        <span class="chain-empty-text">No fallback chain configured. Set <code>SEARCH_PROVIDER_CHAIN</code> in <code>.env</code></span>
      </div>
    </div>

    <!-- API Key Status Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon section-icon-keys">
          <KeyRound class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">API Key Status</h4>
          <p class="section-desc">Keys detected from server environment (<code>.env</code>)</p>
        </div>
      </div>

      <div class="key-grid">
        <div
          v-for="provider in keyStatusProviders"
          :key="provider.id"
          class="key-status-item"
          :class="{ 'key-configured': provider.configured }"
        >
          <div class="key-status-dot" :class="provider.configured ? 'dot-green' : 'dot-gray'" />
          <span class="key-status-name">{{ provider.label }}</span>
          <span class="key-status-badge" :class="provider.configured ? 'badge-active' : 'badge-inactive'">
            {{ provider.configured ? 'Active' : 'Not set' }}
          </span>
        </div>
      </div>
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
  Cloud,
  ArrowRightLeft,
  ArrowRight,
  KeyRound,
  TriangleAlert,
} from 'lucide-vue-next'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  getSettings,
  updateSettings,
  getProviders,
  getServerConfig,
  type UserSettings,
  type ProvidersInfo,
  type ServerConfig,
} from '@/api/settings'
import { showErrorToast } from '@/utils/toast'

const { t } = useI18n()

// ── State ────────────────────────────────────────────────────────────
const localSettings = ref<UserSettings>({
  llm_provider: 'openai',
  model_name: 'gpt-4',
  api_base: '',
  temperature: 0.7,
  max_tokens: 8000,
  search_provider: 'duckduckgo',
  browser_agent_max_steps: 25,
  browser_agent_timeout: 300,
  browser_agent_use_vision: true,
  response_verbosity_preference: 'adaptive',
  clarification_policy: 'auto',
  quality_floor_enforced: true,
  skill_auto_trigger_enabled: false,
})

const serverConfig = ref<ServerConfig>({
  model_name: '',
  api_base: '',
  temperature: 0.6,
  max_tokens: 8192,
  llm_provider: 'auto',
  search_provider: '',
  search_provider_chain: [],
  configured_search_keys: [],
})

const providers = ref<ProvidersInfo>({
  llm_providers: [],
  search_providers: [],
})

// ── Provider metadata ────────────────────────────────────────────────
const providerDescriptions: Record<string, string> = {
  bing: 'Microsoft Bing Search API with comprehensive web results',
  google: 'Google Custom Search for precise and relevant results',
  duckduckgo: 'Privacy-focused search engine — no API key needed',
  brave: 'Independent search with privacy-preserving features',
  tavily: 'AI-powered search designed specifically for LLM applications',
  serper: 'Google Search results via Serper.dev API (2,500 free/mo)',
  exa: 'Semantic search optimized for meaning-based retrieval',
  jina: 'LLM-native web search via Jina Search Foundation',
}

const providerRequiresKey: Record<string, boolean> = {
  duckduckgo: false,
  bing: false,
  google: true,
  brave: true,
  tavily: true,
  serper: true,
  exa: true,
  jina: true,
}

const getProviderIcon = (providerId: string): Component => {
  const icons: Record<string, Component> = {
    bing: Globe,
    google: Search,
    duckduckgo: Shield,
    brave: Shield,
    tavily: Zap,
    serper: Search,
    exa: Cloud,
    jina: Search,
  }
  return icons[providerId] || Cloud
}

// ── Computed ─────────────────────────────────────────────────────────
const selectedProviderInfo = computed(() =>
  providers.value.search_providers.find(p => p.id === localSettings.value.search_provider),
)

const providerDescription = computed(() =>
  providerDescriptions[localSettings.value.search_provider] || '',
)

const hasSearchMismatch = computed(() => {
  if (!serverConfig.value.search_provider) return false
  return localSettings.value.search_provider !== serverConfig.value.search_provider
})

const keyStatusProviders = computed(() => {
  const keyProviders = [
    { id: 'tavily', label: 'Tavily' },
    { id: 'serper', label: 'Serper' },
    { id: 'brave', label: 'Brave' },
    { id: 'exa', label: 'Exa' },
    { id: 'jina', label: 'Jina' },
    { id: 'google', label: 'Google' },
  ]
  return keyProviders.map(p => ({
    ...p,
    configured: serverConfig.value.configured_search_keys.includes(p.id),
  }))
})

// ── Helpers ──────────────────────────────────────────────────────────
const capitalize = (s: string) => s ? s.charAt(0).toUpperCase() + s.slice(1) : ''

const isKeyConfigured = (providerId: string): boolean =>
  serverConfig.value.configured_search_keys.includes(providerId)

const requiresKey = (providerId: string): boolean =>
  providerRequiresKey[providerId] ?? true

// ── Lifecycle ────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const [settings, providersInfo, srvConfig] = await Promise.all([
      getSettings(),
      getProviders(),
      getServerConfig(),
    ])
    localSettings.value = { ...localSettings.value, ...settings }
    providers.value = providersInfo
    serverConfig.value = srvConfig
  } catch {
    // Settings load failed - using defaults
  }
})

// ── Actions ──────────────────────────────────────────────────────────
const onProviderChange = async (value: string) => {
  localSettings.value.search_provider = value
  try {
    await updateSettings({
      search_provider: value,
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
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── Active Config Banner ───────────────────────────────────── */
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

.active-config-sep {
  margin: 0 4px;
  color: var(--text-tertiary);
}

.active-config-chain {
  font-weight: 400;
  color: var(--text-secondary);
  font-size: 12px;
}

/* ── Mismatch Warning ───────────────────────────────────────── */
.mismatch-warning {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px 16px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-radius: 12px;
  color: #b45309;
}

.mismatch-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mismatch-title {
  font-size: 13px;
  font-weight: 600;
}

.mismatch-text {
  font-size: 12px;
  color: #92400e;
  line-height: 1.5;
}

.mismatch-text code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  background: rgba(245, 158, 11, 0.12);
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
}

/* ── Section Cards ──────────────────────────────────────────── */
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

.section-icon-chain {
  background: rgba(168, 85, 247, 0.1);
  color: #a855f7;
}

.section-icon-keys {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}

.section-info {
  flex: 1;
}

.section-info code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  background: var(--fill-tsp-white-dark);
  padding: 1px 5px;
  border-radius: 4px;
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

/* ── Setting Row ────────────────────────────────────────────── */
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

/* ── Select Option ──────────────────────────────────────────── */
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

/* ── Provider Icons ─────────────────────────────────────────── */
.search-provider-icon,
.chain-provider-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  color: #fff;
  flex-shrink: 0;
}

.search-provider-icon {
  width: 28px;
  height: 28px;
}

.chain-provider-icon {
  width: 26px;
  height: 26px;
}

.provider-bing { background: linear-gradient(135deg, #00809d 0%, #006a82 100%); }
.provider-google { background: linear-gradient(135deg, #4285f4 0%, #3367d6 100%); }
.provider-duckduckgo { background: linear-gradient(135deg, #de5833 0%, #c74a29 100%); }
.provider-brave { background: linear-gradient(135deg, #fb542b 0%, #e04422 100%); }
.provider-tavily { background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%); }
.provider-serper { background: linear-gradient(135deg, #4285f4 0%, #2b6cb0 100%); }
.provider-exa { background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%); }
.provider-jina { background: linear-gradient(135deg, #14b8a6 0%, #0f766e 100%); }

/* ── Provider Info Card ─────────────────────────────────────── */
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
  background: rgba(239, 68, 68, 0.08);
  color: #dc2626;
}

/* ── Fallback Chain ─────────────────────────────────────────── */
.chain-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chain-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  border-radius: 10px;
}

.chain-rank {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-brand);
  background: var(--fill-blue);
  flex-shrink: 0;
}

.chain-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.chain-status {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 5px;
}

.chain-status-ready {
  background: rgba(34, 197, 94, 0.1);
  color: var(--function-success);
}

.chain-status-missing {
  background: rgba(239, 68, 68, 0.08);
  color: #dc2626;
}

.chain-empty {
  padding: 16px;
  text-align: center;
}

.chain-empty-text {
  font-size: 13px;
  color: var(--text-tertiary);
}

.chain-empty-text code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  background: var(--fill-tsp-white-dark);
  padding: 1px 5px;
  border-radius: 4px;
}

/* ── API Key Status Grid ────────────────────────────────────── */
.key-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

@media (max-width: 500px) {
  .key-grid {
    grid-template-columns: 1fr;
  }
}

.key-status-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  transition: all 0.2s ease;
}

.key-configured {
  border-color: rgba(34, 197, 94, 0.2);
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.04) 0%, transparent 100%);
}

.key-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-green {
  background: #22c55e;
  box-shadow: 0 0 4px rgba(34, 197, 94, 0.4);
}

.dot-gray {
  background: var(--border-dark);
}

.key-status-name {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.key-status-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 5px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.badge-active {
  background: rgba(34, 197, 94, 0.1);
  color: var(--function-success);
}

.badge-inactive {
  background: var(--fill-tsp-white-dark);
  color: var(--text-tertiary);
}

/* ── Transitions ────────────────────────────────────────────── */
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
