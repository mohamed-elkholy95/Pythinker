<template>
  <div class="search-list">
    <!-- Header -->
    <div class="search-header">Search</div>

    <!-- Primary provider -->
    <div class="search-item">
      <div class="item-icon" :class="`provider-${serverConfig.search_provider}`">
        <component :is="getProviderIcon(serverConfig.search_provider)" class="w-3.5 h-3.5" />
      </div>
      <div class="item-content">
        <span class="item-title">{{ capitalize(serverConfig.search_provider) }} — Primary</span>
        <span class="item-desc">{{ providerDescriptions[serverConfig.search_provider] || 'Active search engine' }}</span>
      </div>
    </div>

    <!-- Fallback chain providers (skip the first if it matches primary) -->
    <template v-for="(provider, index) in fallbackProviders" :key="provider">
      <div class="search-item">
        <div class="item-icon" :class="`provider-${provider}`">
          <component :is="getProviderIcon(provider)" class="w-3.5 h-3.5" />
        </div>
        <div class="item-content">
          <span class="item-title">{{ capitalize(provider) }} — Fallback {{ index + 1 }}</span>
          <span class="item-desc">{{ providerDescriptions[provider] || 'Fallback search engine' }}</span>
        </div>
      </div>
    </template>

    <!-- API Keys section -->
    <div class="search-item keys-header-item">
      <div class="item-icon icon-keys">
        <KeyRound class="w-3.5 h-3.5" />
      </div>
      <div class="item-content">
        <span class="item-title">API Keys</span>
        <span class="item-desc">
          {{ configuredKeysCount }} of {{ keyStatusProviders.length }} providers configured via <code>.env</code>
        </span>
      </div>
    </div>

    <div
      v-for="provider in keyStatusProviders"
      :key="provider.id"
      class="search-item key-item"
    >
      <div class="item-icon" :class="`provider-${provider.id}`">
        <component :is="getProviderIcon(provider.id)" class="w-3.5 h-3.5" />
      </div>
      <div class="item-content">
        <span class="item-title">{{ provider.label }}</span>
        <span class="item-desc">{{ provider.configured ? 'API key active' : 'Not configured' }}</span>
      </div>
      <div class="key-dot" :class="provider.configured ? 'dot-active' : 'dot-inactive'" />
    </div>

    <!-- Env footer -->
    <div class="search-footer">
      Managed by <code>.env</code> — update <code>SEARCH_PROVIDER</code> to change
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import { ref, computed, onMounted } from 'vue'
import {
  Search,
  Globe,
  Shield,
  Zap,
  Cloud,
  KeyRound,
} from 'lucide-vue-next'
import {
  getServerConfig,
  type ServerConfig,
} from '@/api/settings'

// ── State (read-only from server) ────────────────────────────────────
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
const fallbackProviders = computed(() => {
  const chain = serverConfig.value.search_provider_chain
  // Skip the first entry if it's the same as the primary
  if (chain.length > 0 && chain[0] === serverConfig.value.search_provider) {
    return chain.slice(1)
  }
  return chain
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

const configuredKeysCount = computed(() =>
  keyStatusProviders.value.filter(p => p.configured).length,
)

// ── Helpers ──────────────────────────────────────────────────────────
const capitalize = (s: string) => s ? s.charAt(0).toUpperCase() + s.slice(1) : ''

// ── Lifecycle ────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const srvConfig = await getServerConfig()
    serverConfig.value = srvConfig
  } catch {
    // Settings load failed - using defaults
  }
})
</script>

<style scoped>
.search-list {
  width: 100%;
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  overflow: hidden;
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── Header ────────────────────────────────────────────────── */
.search-header {
  text-align: center;
  padding: 14px 20px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-light);
}

/* ── List Item ─────────────────────────────────────────────── */
.search-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-light);
}

.search-item:last-of-type {
  border-bottom: none;
}

.keys-header-item {
  margin-top: 4px;
  border-top: 1px solid var(--border-light);
}

.key-item {
  padding: 10px 20px 10px 32px;
}

/* ── Item Icon ─────────────────────────────────────────────── */
.item-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #fff;
  flex-shrink: 0;
  margin-top: 1px;
}

.icon-keys {
  background: linear-gradient(135deg, #64748b 0%, #475569 100%);
}

/* ── Item Content ──────────────────────────────────────────── */
.item-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}

.item-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.item-desc code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  background: var(--fill-tsp-white-dark);
  padding: 1px 4px;
  border-radius: 3px;
}

/* ── Key Status Dot ────────────────────────────────────────── */
.key-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 8px;
}

.dot-active {
  background: #22c55e;
  box-shadow: 0 0 4px rgba(34, 197, 94, 0.4);
}

.dot-inactive {
  background: var(--border-dark);
}

/* ── Provider Colors ───────────────────────────────────────── */
.provider-bing { background: linear-gradient(135deg, #00809d 0%, #006a82 100%); }
.provider-google { background: linear-gradient(135deg, #4285f4 0%, #3367d6 100%); }
.provider-duckduckgo { background: linear-gradient(135deg, #de5833 0%, #c74a29 100%); }
.provider-brave { background: linear-gradient(135deg, #fb542b 0%, #e04422 100%); }
.provider-tavily { background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%); }
.provider-serper { background: linear-gradient(135deg, #4285f4 0%, #2b6cb0 100%); }
.provider-exa { background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%); }
.provider-jina { background: linear-gradient(135deg, #14b8a6 0%, #0f766e 100%); }

/* ── Footer ────────────────────────────────────────────────── */
.search-footer {
  padding: 12px 20px;
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: center;
  border-top: 1px solid var(--border-light);
}

.search-footer code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  background: var(--fill-tsp-white-dark);
  padding: 1px 4px;
  border-radius: 3px;
  font-weight: 600;
}
</style>
