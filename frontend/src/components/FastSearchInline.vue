<template>
  <div
    class="fast-search-inline"
    :class="{
      'fast-search-inline--searching': isSearching,
      'fast-search-inline--empty': !isSearching && results.length === 0,
    }"
  >
    <!-- 1) Header: Query + status (Searching / N results / No results) -->
    <div class="fast-search-header">
      <div class="fast-search-header-main">
        <Search class="fast-search-header-icon" :size="14" />
        <span class="fast-search-query-label">{{ t('Search') }}:</span>
        <span class="fast-search-query-value">"{{ query || t('query') }}"</span>
      </div>
      <div class="fast-search-header-status">
        <Loader2
          v-if="isSearching"
          class="fast-search-spinner"
          :size="12"
        />
        <span v-if="isSearching" class="fast-search-status-label">{{ progressLabel }}</span>
        <span
          v-else-if="results.length > 0"
          class="fast-search-status-pill"
        >
          {{ filteredResults.length }} {{ t('results') }} • {{ t('Sources') }}: {{ t('Web') }}
        </span>
        <span
          v-else-if="explicitEmpty"
          class="fast-search-status-pill fast-search-status-pill--empty"
        >
          0 {{ t('results') }}
        </span>
      </div>
    </div>

    <!-- Tabs: All | Docs | GitHub | Community -->
    <div v-if="!isSearching && results.length > 0" class="fast-search-tabs">
      <button
        v-for="tab in sourceTabs"
        :key="tab.id"
        class="fast-search-tab"
        :class="{ 'fast-search-tab--active': activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 6) Loading: skeleton cards + progress labels -->
    <div v-if="isSearching" class="fast-search-loading">
      <div class="fast-search-skeleton-cards">
        <div v-for="i in 4" :key="i" class="fast-search-skeleton-card">
          <div class="fast-search-skeleton-card-icon" />
          <div class="fast-search-skeleton-card-body">
            <div class="fast-search-skeleton-card-title" />
            <div class="fast-search-skeleton-card-domain" />
            <div class="fast-search-skeleton-card-snippet" />
          </div>
        </div>
      </div>
    </div>

    <!-- 5) Agent picks panel + 2) Result cards (two-column when space allows) -->
    <div v-else-if="filteredResults.length > 0" class="fast-search-body">
      <div class="fast-search-results-column">
        <TransitionGroup name="fast-search-card" tag="div" class="fast-search-cards">
          <div
            v-for="(result, index) in filteredResults"
            :key="result.link || index"
            class="fast-search-card"
          >
            <div class="fast-search-card-main" @click="handleOpen(result)">
              <div class="fast-search-card-icon">
                <img
                  v-if="!faviconErrors[result.link]"
                  :src="getFavicon(result.link)"
                  alt=""
                  class="fast-search-card-favicon"
                  @error="handleFaviconError(result.link)"
                />
                <span v-else class="fast-search-card-favicon-fallback">
                  {{ getIconLetter(result) }}
                </span>
              </div>
              <div class="fast-search-card-content">
                <h4 class="fast-search-card-title">{{ result.title }}</h4>
                <div class="fast-search-card-domain-row">
                  <span class="fast-search-card-domain">{{ getDomainPath(result.link) }}</span>
                </div>
                <p v-if="result.snippet" class="fast-search-card-snippet">
                  {{ formatSnippet(result.snippet) }}
                </p>
                <div class="fast-search-card-badges">
                  <span
                    v-for="badge in getBadges(result)"
                    :key="badge"
                    class="fast-search-badge"
                    :class="`fast-search-badge--${badge.type}`"
                  >
                    {{ badge.label }}
                  </span>
                </div>
              </div>
            </div>
            <div class="fast-search-card-actions">
              <button
                class="fast-search-action-btn fast-search-action-btn--primary"
                @click.stop="handleOpen(result)"
              >
                <ExternalLink :size="12" />
                {{ t('Open') }}
              </button>
            </div>
            <!-- 3) "Why this result" expandable -->
            <div
              v-if="getWhyThisResult(result).length > 0"
              class="fast-search-card-why"
            >
              <button
                class="fast-search-why-toggle"
                :aria-expanded="expandedWhyId === (result.link || index)"
                @click.stop="toggleWhy(result.link, index)"
              >
                {{ t('Why this result?') }}
                <ChevronDown
                  class="fast-search-why-chevron"
                  :size="12"
                  :class="{ 'fast-search-why-chevron--open': expandedWhyId === (result.link || String(index)) }"
                />
              </button>
              <div
                v-show="expandedWhyId === (result.link || String(index))"
                class="fast-search-why-content"
              >
                <ul>
                  <li v-for="(reason, i) in getWhyThisResult(result)" :key="i">{{ reason }}</li>
                </ul>
              </div>
            </div>
          </div>
        </TransitionGroup>
      </div>
      <!-- Agent picks panel -->
      <div class="fast-search-picks-column">
        <div class="fast-search-picks">
          <h4 class="fast-search-picks-title">{{ t('Agent picks') }}</h4>
          <div v-if="filteredResults.length > 0" class="fast-search-pick-main">
            <span class="fast-search-pick-label">{{ t('Best pick') }}</span>
            <button
              class="fast-search-pick-action"
              @click="handleOpen(filteredResults[0])"
            >
              {{ filteredResults[0].title }}
            </button>
          </div>
          <div class="fast-search-pick-actions">
            <span class="fast-search-pick-label">{{ t('Next actions') }}</span>
            <button
              class="fast-search-pick-chip"
              @click="handleOpen(filteredResults[0])"
            >
              <ExternalLink :size="12" />
              {{ t('Open overview') }}
            </button>
            <button
              v-if="filteredResults.length > 1"
              class="fast-search-pick-chip"
              @click="handleOpen(filteredResults[1])"
            >
              <ExternalLink :size="12" />
              {{ t('Compare sources') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state: header shows "0 results" only, no verbose empty block -->
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import { Search, Loader2, ExternalLink, ChevronDown } from 'lucide-vue-next';
import { getFaviconUrl } from '@/utils/toolDisplay';
import type { SearchResultItem } from '@/types/search';

const props = withDefaults(
  defineProps<{
    results: SearchResultItem[];
    query?: string;
    isSearching?: boolean;
    explicitEmpty?: boolean;
  }>(),
  {
    query: '',
    isSearching: false,
    explicitEmpty: false,
  }
);

const emit = defineEmits<{
  (e: 'browseUrl', url: string): void;
  (e: 'broadenQuery'): void;
}>();

const { t } = useI18n();
const faviconErrors = ref<Record<string, boolean>>({});
const expandedWhyId = ref<string | number | null>(null);
const activeTab = ref<'all' | 'docs' | 'github' | 'community'>('all');
const progressLabel = ref('');

const progressLabels = computed(() => [
  t('Searching web…'),
  t('Ranking results…'),
  t('Generating follow-ups…'),
]);

let progressInterval: ReturnType<typeof setInterval> | null = null;

watch(
  () => props.isSearching,
  (searching) => {
    if (progressInterval) {
      clearInterval(progressInterval);
      progressInterval = null;
    }
    if (searching) {
      progressLabel.value = progressLabels.value[0];
      let i = 0;
      progressInterval = setInterval(() => {
        i = (i + 1) % progressLabels.value.length;
        progressLabel.value = progressLabels.value[i];
      }, 1500);
    }
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  if (progressInterval) clearInterval(progressInterval);
});

const sourceTabs = [
  { id: 'all' as const, label: t('All') },
  { id: 'docs' as const, label: t('Docs') },
  { id: 'github' as const, label: t('GitHub') },
  { id: 'community' as const, label: t('Community') },
];

function inferSourceType(link: string): 'docs' | 'github' | 'community' | null {
  try {
    const url = new URL(link);
    const h = url.hostname.toLowerCase();
    if (h.includes('github.com') || h.includes('gitlab.com')) return 'github';
    if (
      h.includes('docs.') ||
      h.includes('/docs') ||
      h.includes('developer.') ||
      h.includes('documentation')
    )
      return 'docs';
    if (
      h.includes('reddit.com') ||
      h.includes('stackoverflow.com') ||
      h.includes('medium.com') ||
      h.includes('dev.to')
    )
      return 'community';
    return null;
  } catch {
    return null;
  }
}

function getBadges(result: SearchResultItem): { type: string; label: string }[] {
  const badges: { type: string; label: string }[] = [];
  try {
    const url = new URL(result.link);
    const h = url.hostname.toLowerCase();
    if (
      h.includes('claude.com') ||
      h.includes('anthropic.com') ||
      h.includes('docs.') ||
      h.includes('developer.')
    ) {
      badges.push({ type: 'official', label: t('Official') });
    }
    if (h.includes('github.com')) badges.push({ type: 'github', label: 'GitHub' });
    if (h.includes('docs.') || h.includes('documentation'))
      badges.push({ type: 'docs', label: t('Docs') });
    if (
      h.includes('reddit.com') ||
      h.includes('stackoverflow.com') ||
      h.includes('medium.com')
    ) {
      badges.push({ type: 'community', label: t('Community') });
    }
  } catch {
    // ignore
  }
  return badges;
}

function getWhyThisResult(result: SearchResultItem): string[] {
  const reasons: string[] = [];
  try {
    const url = new URL(result.link);
    const h = url.hostname.toLowerCase();
    if (
      h.includes('claude.com') ||
      h.includes('anthropic.com') ||
      h.includes('docs.')
    ) {
      reasons.push(t('Official documentation'));
    }
    if (result.snippet && props.query) {
      const qTerms = props.query.toLowerCase().split(/\s+/).filter(Boolean);
      const matchCount = qTerms.filter((t) =>
        (result.title + ' ' + result.snippet).toLowerCase().includes(t)
      ).length;
      if (matchCount > 0) {
        reasons.push(
          t('Matches: {terms}', { terms: qTerms.slice(0, 3).join(', ') })
        );
      }
    }
    if (h.includes('github.com')) reasons.push(t('Source code repository'));
  } catch {
    // ignore
  }
  return reasons;
}

const filteredResults = computed(() => {
  if (activeTab.value === 'all') return props.results;
  return props.results.filter((r) => inferSourceType(r.link) === activeTab.value);
});

function getFavicon(link: string): string {
  return getFaviconUrl(link) ?? '';
}

function getIconLetter(result: SearchResultItem): string {
  if (!result.link && !result.title) return '?';
  try {
    const url = new URL(result.link);
    const hostname = url.hostname.replace('www.', '');
    if (hostname.includes('wikipedia')) return 'W';
    if (hostname.includes('github')) return 'G';
    if (hostname.includes('stackoverflow')) return 'S';
    return hostname.charAt(0).toUpperCase();
  } catch {
    return result.title?.charAt(0).toUpperCase() || '?';
  }
}

function getDomainPath(link: string): string {
  try {
    const url = new URL(link);
    const host = url.hostname.replace('www.', '');
    const path = url.pathname === '/' ? '' : url.pathname.slice(0, 50);
    return path ? `${host}${path}` : host;
  } catch {
    return link.slice(0, 50);
  }
}

function formatSnippet(snippet: string): string {
  if (!snippet) return '';
  const cleaned = snippet.replace(/\s+/g, ' ').trim();
  return cleaned.length > 140 ? cleaned.slice(0, 140).trim() + '…' : cleaned;
}

function handleFaviconError(link: string) {
  faviconErrors.value[link] = true;
}

function handleOpen(result: SearchResultItem) {
  if (result.link) {
    emit('browseUrl', result.link);
    window.open(result.link, '_blank', 'noopener,noreferrer');
  }
}

function toggleWhy(link: string, index: number) {
  const key = link || index;
  expandedWhyId.value = expandedWhyId.value === key ? null : key;
}

</script>

<style scoped>
.fast-search-inline {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-top: 8px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.fast-search-inline:hover {
  border-color: var(--border-main);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.fast-search-inline--searching {
  border-color: rgba(59, 130, 246, 0.35);
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.12);
}

.fast-search-inline--empty {
  min-height: 160px;
}

/* Header */
.fast-search-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-light);
  background: var(--fill-tsp-gray-main);
}

.fast-search-header-main {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.fast-search-header-icon {
  flex-shrink: 0;
  color: var(--icon-secondary);
}

.fast-search-query-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.fast-search-query-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.fast-search-header-status {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.fast-search-spinner {
  color: var(--text-brand);
  animation: fast-search-spin 1s linear infinite;
}

.fast-search-status-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-brand);
}

.fast-search-status-pill {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--fill-tsp-white-dark);
  padding: 4px 10px;
  border-radius: 999px;
}

.fast-search-status-pill--empty {
  color: var(--text-tertiary);
}

/* Tabs */
.fast-search-tabs {
  display: flex;
  gap: 2px;
  padding: 6px 14px;
  border-bottom: 1px solid var(--border-light);
  background: var(--fill-tsp-gray-main);
}

.fast-search-tab {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  background: none;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.fast-search-tab:hover {
  color: var(--text-secondary);
  background: var(--fill-tsp-white-main);
}

.fast-search-tab--active {
  color: var(--text-primary);
  background: var(--fill-tsp-white-main);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}

/* Loading */
.fast-search-loading {
  padding: 12px 14px;
}

.fast-search-skeleton-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.fast-search-skeleton-card {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  background: var(--fill-tsp-gray-main);
}

.fast-search-skeleton-card-icon {
  width: 28px;
  height: 28px;
  min-width: 28px;
  border-radius: 8px;
  background: var(--fill-tsp-white-dark);
  animation: fast-search-pulse 1.5s ease-in-out infinite;
}

.fast-search-skeleton-card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fast-search-skeleton-card-title {
  height: 14px;
  width: 70%;
  border-radius: 4px;
  background: var(--fill-tsp-white-dark);
  animation: fast-search-pulse 1.5s ease-in-out infinite;
}

.fast-search-skeleton-card-domain {
  height: 10px;
  width: 40%;
  border-radius: 4px;
  background: var(--fill-tsp-white-dark);
  animation: fast-search-pulse 1.5s ease-in-out infinite;
  animation-delay: 0.1s;
}

.fast-search-skeleton-card-snippet {
  height: 10px;
  width: 95%;
  border-radius: 4px;
  background: var(--fill-tsp-white-dark);
  animation: fast-search-pulse 1.5s ease-in-out infinite;
  animation-delay: 0.15s;
}

/* Body: results + agent picks */
.fast-search-body {
  display: grid;
  grid-template-columns: 1fr minmax(180px, 220px);
  gap: 0;
  min-height: 200px;
}

@media (max-width: 520px) {
  .fast-search-body {
    grid-template-columns: 1fr;
  }
}

.fast-search-results-column {
  overflow-y: auto;
  max-height: 360px;
}

.fast-search-cards {
  display: flex;
  flex-direction: column;
}

.fast-search-card {
  border-bottom: 1px solid var(--border-light);
  padding: 12px 14px;
  transition: background-color 0.15s ease;
}

.fast-search-card:last-child {
  border-bottom: none;
}

.fast-search-card:hover {
  background: var(--fill-tsp-gray-main);
}

.fast-search-card-main {
  display: flex;
  gap: 12px;
  cursor: pointer;
  align-items: flex-start;
}

.fast-search-card-icon {
  width: 28px;
  height: 28px;
  min-width: 28px;
  border-radius: 8px;
  background: var(--fill-tsp-white-dark);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.fast-search-card-favicon {
  width: 16px;
  height: 16px;
  object-fit: contain;
}

.fast-search-card-favicon-fallback {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
}

.fast-search-card-content {
  flex: 1;
  min-width: 0;
}

.fast-search-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.35;
  margin: 0 0 4px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.fast-search-card-domain-row {
  margin-bottom: 6px;
}

.fast-search-card-domain {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: ui-monospace, monospace;
}

.fast-search-card-snippet {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.45;
  margin: 0 0 8px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.fast-search-card-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.fast-search-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.fast-search-badge--official {
  background: rgba(34, 197, 94, 0.15);
  color: #16a34a;
}

.fast-search-badge--docs {
  background: rgba(0, 0, 0, 0.15);
  color: #0a0a0a;
}

.fast-search-badge--github {
  background: rgba(0, 0, 0, 0.08);
  color: var(--text-primary);
}

.fast-search-badge--community {
  background: rgba(139, 92, 246, 0.15);
  color: #6d28d9;
}

.fast-search-card-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-light);
}

.fast-search-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  transition: all 0.15s ease;
}

.fast-search-action-btn--primary {
  background: var(--text-primary);
  color: var(--text-onblack);
}

.fast-search-action-btn--primary:hover {
  opacity: 0.9;
}

/* Why this result */
.fast-search-card-why {
  margin-top: 8px;
}

.fast-search-why-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 0;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
}

.fast-search-why-toggle:hover {
  color: var(--text-secondary);
}

.fast-search-why-chevron {
  transition: transform 0.2s ease;
}

.fast-search-why-chevron--open {
  transform: rotate(180deg);
}

.fast-search-why-content {
  padding: 8px 12px;
  margin-top: 4px;
  border-radius: 6px;
  background: var(--fill-tsp-gray-main);
  font-size: 12px;
  color: var(--text-secondary);
}

.fast-search-why-content ul {
  margin: 0;
  padding-left: 16px;
}

.fast-search-why-content li {
  margin: 2px 0;
}

/* Agent picks panel */
.fast-search-picks-column {
  border-left: 1px solid var(--border-light);
  background: var(--fill-tsp-gray-main);
  padding: 12px 14px;
}

@media (max-width: 520px) {
  .fast-search-picks-column {
    border-left: none;
    border-top: 1px solid var(--border-light);
  }
}

.fast-search-picks {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.fast-search-picks-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 4px 0;
}

.fast-search-pick-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary);
  margin-bottom: 4px;
}

.fast-search-pick-main {
  display: flex;
  flex-direction: column;
}

.fast-search-pick-action {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-brand);
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  padding: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.fast-search-pick-action:hover {
  text-decoration: underline;
}

.fast-search-pick-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.fast-search-pick-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
}

.fast-search-pick-chip:hover {
  border-color: var(--border-main);
  color: var(--text-primary);
}

/* Card transition */
.fast-search-card-enter-active {
  transition: all 0.25s ease-out;
}

.fast-search-card-enter-from {
  opacity: 0;
  transform: translateY(-6px);
}

</style>

<style>
@keyframes fast-search-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes fast-search-pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.9; }
}
</style>
