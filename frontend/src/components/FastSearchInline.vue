<template>
  <div
    class="fsi"
    :class="{
      'fsi--searching': isSearching,
      'fsi--empty': !isSearching && results.length === 0,
    }"
  >
    <!-- Header: query + status -->
    <div class="fsi-header">
      <div class="fsi-header-left">
        <Search :size="13" class="fsi-header-icon" />
        <span class="fsi-header-label">{{ t('Search') }}:</span>
        <span class="fsi-header-query">"{{ query || t('query') }}"</span>
      </div>
      <div class="fsi-header-right">
        <Loader2 v-if="isSearching" :size="12" class="fsi-spinner" />
        <span v-if="isSearching" class="fsi-progress-label">{{ progressLabel }}</span>
        <span v-else-if="results.length > 0" class="fsi-count-pill">
          {{ results.length }} {{ t('results') }}
        </span>
        <span v-else-if="explicitEmpty" class="fsi-count-pill fsi-count-pill--empty">
          0 {{ t('results') }}
        </span>
      </div>
    </div>

    <!-- Skeleton grid during search -->
    <div v-if="isSearching" class="fsi-grid fsi-grid--skeleton">
      <div v-for="i in 4" :key="i" class="fsi-card fsi-card--skeleton">
        <div class="fsi-card-body">
          <div class="fsi-skel fsi-skel--title" />
          <div class="fsi-skel fsi-skel--title-mid" />
          <div class="fsi-skel fsi-skel--title-short" />
          <div class="fsi-skel fsi-skel--source" />
        </div>
        <div class="fsi-skel fsi-skel--thumb" />
      </div>
    </div>

    <!-- News card grid -->
    <div v-else-if="results.length > 0" class="fsi-content">
      <div class="fsi-grid">
        <button
          v-for="(result, index) in visibleResults"
          :key="result.link || index"
          class="fsi-card"
          @click="handleOpen(result)"
        >
          <div class="fsi-card-body">
            <p class="fsi-card-title">{{ result.title }}</p>
            <div class="fsi-card-source">
              <div class="fsi-source-icon">
                <img
                  v-if="!isFaviconError(result.link)"
                  :src="getFavicon(result.link)"
                  alt=""
                  class="fsi-source-favicon"
                  @error="handleFaviconError(result.link)"
                />
                <span v-else class="fsi-source-letter">{{ getIconLetter(result) }}</span>
              </div>
              <span class="fsi-source-name">{{ getDomain(result.link) }}</span>
            </div>
          </div>
          <div class="fsi-card-thumb" :style="getThumbStyle(result)">
            <img
              v-if="!thumbErrors[result.link]"
              :src="getThumbFaviconUrl(result.link)"
              alt=""
              class="fsi-thumb-img"
              @error="handleThumbError(result.link)"
            />
            <span v-else class="fsi-thumb-letter">{{ getIconLetter(result) }}</span>
          </div>
        </button>
      </div>

      <!-- Collapse/expand -->
      <button
        v-if="results.length > INITIAL_VISIBLE"
        class="fsi-see-more"
        @click.stop="isExpanded = !isExpanded"
      >
        <span>{{ isExpanded ? t('Show less') : t('See more news') }}</span>
        <ChevronDown
          :size="13"
          class="fsi-see-more-icon"
          :class="{ 'fsi-see-more-icon--open': isExpanded }"
        />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import { Search, Loader2, ChevronDown } from 'lucide-vue-next';
import { useFavicon } from '@/composables/useFavicon';
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

const INITIAL_VISIBLE = 4;

const isExpanded = ref(false);
const { getUrl: getFavicon, isError: isFaviconError, handleError: handleFaviconError, getLetter } = useFavicon();
const thumbErrors = ref<Record<string, boolean>>({});
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

const visibleResults = computed(() =>
  isExpanded.value ? props.results : props.results.slice(0, INITIAL_VISIBLE)
);

const THUMB_PALETTE = [
  ['#eef2ff', '#4f6ef7'],
  ['#fef2f2', '#dc2626'],
  ['#f0fdf4', '#16a34a'],
  ['#fffbeb', '#d97706'],
  ['#faf5ff', '#7c3aed'],
  ['#fdf2f8', '#be185d'],
  ['#f0fdfa', '#0f766e'],
  ['#fff7ed', '#ea580c'],
] as const;

function getThumbStyle(result: SearchResultItem): { background: string; color: string } {
  const domain = getDomain(result.link);
  let hash = 0;
  for (let i = 0; i < domain.length; i++) {
    hash = (hash * 31 + domain.charCodeAt(i)) & 0xff;
  }
  const [bg, fg] = THUMB_PALETTE[hash % THUMB_PALETTE.length];
  return { background: bg, color: fg };
}

function getThumbFaviconUrl(link: string): string {
  try {
    const hostname = new URL(link).hostname;
    return `https://www.google.com/s2/favicons?domain=${hostname}&sz=64`;
  } catch {
    return '';
  }
}

function handleThumbError(link: string) {
  thumbErrors.value[link] = true;
}

function getIconLetter(result: SearchResultItem): string {
  return getLetter(result.link, result.title);
}

function getDomain(link: string): string {
  try {
    return new URL(link).hostname.replace('www.', '');
  } catch {
    return link.slice(0, 30);
  }
}

function handleOpen(result: SearchResultItem) {
  if (result.link) {
    emit('browseUrl', result.link);
    window.open(result.link, '_blank', 'noopener,noreferrer');
  }
}
</script>

<style scoped>
/* ── Container ─────────────────────────────────── */
.fsi {
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
  margin-top: 8px;
  transition: border-color 0.2s ease;
}

.fsi--searching {
  border-color: rgba(59, 130, 246, 0.3);
}

/* ── Header ────────────────────────────────────── */
.fsi-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 9px 14px;
  border-bottom: 1px solid var(--border-light);
  background: var(--fill-tsp-gray-main);
}

.fsi-header-left {
  display: flex;
  align-items: center;
  gap: 5px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.fsi-header-icon {
  color: var(--icon-secondary);
  flex-shrink: 0;
}

.fsi-header-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.fsi-header-query {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.fsi-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.fsi-spinner {
  color: var(--text-brand);
  animation: fsi-spin 1s linear infinite;
}

.fsi-progress-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-brand);
}

.fsi-count-pill {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--fill-tsp-white-dark);
  padding: 3px 9px;
  border-radius: 999px;
}

.fsi-count-pill--empty {
  color: var(--text-tertiary);
}

/* ── 2-column news grid ────────────────────────── */
/* gap:1px + background on grid creates hairline dividers between cells */
.fsi-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--border-light);
}

/* ── Card ──────────────────────────────────────── */
.fsi-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 14px;
  background: var(--background-white-main);
  border: none;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.fsi-card:hover {
  background: var(--fill-tsp-gray-main);
}

/* Skeleton card: no hover, no pointer */
.fsi-card--skeleton {
  cursor: default;
  pointer-events: none;
}

.fsi-card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
}

.fsi-card-title {
  font-size: 14.5px;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 1.45;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  letter-spacing: -0.01em;
}

/* ── Source row ────────────────────────────────── */
.fsi-card-source {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: auto;
}

.fsi-source-icon {
  width: 16px;
  height: 16px;
  min-width: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  overflow: hidden;
  background: var(--fill-tsp-gray-dark, #e5e7eb);
}

.fsi-source-favicon {
  width: 14px;
  height: 14px;
  object-fit: contain;
}

.fsi-source-letter {
  font-size: 8px;
  font-weight: 700;
  color: var(--text-tertiary);
  line-height: 1;
}

.fsi-source-name {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Thumbnail ─────────────────────────────────── */
.fsi-card-thumb {
  width: 96px;
  height: 80px;
  min-width: 96px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.fsi-thumb-img {
  width: 46px;
  height: 46px;
  object-fit: contain;
  border-radius: 6px;
}

.fsi-thumb-letter {
  font-size: 28px;
  font-weight: 800;
  opacity: 0.45;
  line-height: 1;
  font-family: var(--font-sans);
}

/* ── Skeleton bones ────────────────────────────── */
.fsi-skel {
  border-radius: 4px;
  background: var(--fill-tsp-white-dark);
  animation: fsi-pulse 1.6s ease-in-out infinite;
}

.fsi-skel--title        { height: 14px; width: 90%; }
.fsi-skel--title-mid    { height: 14px; width: 78%; animation-delay: 0.07s; }
.fsi-skel--title-short  { height: 14px; width: 55%; animation-delay: 0.12s; }
.fsi-skel--source       { height: 11px; width: 42%; margin-top: 2px; animation-delay: 0.17s; }
.fsi-skel--thumb {
  width: 96px;
  height: 80px;
  min-width: 96px;
  border-radius: 8px;
  flex-shrink: 0;
  animation-delay: 0.05s;
}

/* ── See more / Show less ──────────────────────── */
.fsi-see-more {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 11px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background: none;
  border: none;
  border-top: 1px solid var(--border-light);
  cursor: pointer;
  transition: color 0.15s ease;
}

.fsi-see-more:hover {
  color: var(--text-primary);
}

.fsi-see-more-icon {
  color: var(--icon-secondary);
  transition: transform 0.2s ease;
  margin-left: auto;
}

.fsi-see-more-icon--open {
  transform: rotate(180deg);
}

/* ── Animations ────────────────────────────────── */
@keyframes fsi-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

@keyframes fsi-pulse {
  0%, 100% { opacity: 0.4; }
  50%       { opacity: 0.8; }
}
</style>
