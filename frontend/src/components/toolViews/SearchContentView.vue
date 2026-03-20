<template>
  <ContentContainer
    :centered="false"
    :constrained="false"
    padding="none"
    class="search-view"
  >
    <!-- Active Search: Progressive results feed -->
    <div v-if="isSearching" class="search-results">
      <!-- Progressive results as they stream in -->
      <div v-if="displayResults && displayResults.length > 0" class="search-results-list">
        <TransitionGroup name="result-slide">
          <div
            v-for="(result, index) in displayResults"
            :key="result.link || index"
            class="search-result-item"
            @click="handleResultClick(result)"
          >
            <div class="result-icon-wrapper">
              <img
                v-if="!faviconErrors[result.link]"
                :src="getFavicon(result.link)"
                alt=""
                class="result-favicon"
                @error="handleFaviconError($event, result.link)"
              />
              <span v-else class="result-icon-fallback">{{ getIconLetter(result) }}</span>
            </div>
            <div class="result-body">
              <h3 class="result-title">{{ result.title }}</h3>
              <p v-if="result.snippet" class="result-snippet">{{ formatSnippet(result.snippet) }}</p>
            </div>
          </div>
        </TransitionGroup>
      </div>

      <!-- Skeleton loading when no results yet -->
      <div v-else class="search-skeleton">
        <div v-for="i in 5" :key="i" class="skeleton-item" :style="{ animationDelay: `${i * 0.1}s` }">
          <div class="skeleton-icon"></div>
          <div class="skeleton-lines">
            <div class="skeleton-line skeleton-title"></div>
            <div class="skeleton-line skeleton-snippet"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Completed Search Results -->
    <div v-else class="search-results">
      <div class="search-results-list">
        <div
          v-for="(result, index) in displayResults"
          :key="result.link || index"
          class="search-result-item"
          @click="handleResultClick(result)"
        >
          <div class="result-icon-wrapper">
            <img
              v-if="!faviconErrors[result.link]"
              :src="getFavicon(result.link)"
              alt=""
              class="result-favicon"
              @error="handleFaviconError($event, result.link)"
            />
            <span v-else class="result-icon-fallback">{{ getIconLetter(result) }}</span>
          </div>
          <div class="result-body">
            <h3 class="result-title">{{ result.title }}</h3>
            <p v-if="result.snippet" class="result-snippet">{{ formatSnippet(result.snippet) }}</p>
          </div>
        </div>

        <div v-if="showEmptyState" class="search-empty-state">
          <Search :size="32" class="search-empty-icon" />
          <p class="search-empty-text">No results found</p>
          <p v-if="query" class="search-empty-query">for "{{ query }}"</p>
        </div>
      </div>
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { computed, reactive, toRef } from 'vue';
import { Search } from 'lucide-vue-next';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import { getFaviconUrl, markFaviconFailed } from '@/utils/toolDisplay';
import { useStaggeredResults } from '@/composables/useStaggeredResults';

export interface SearchResult {
  title: string;
  link: string;
  snippet: string;
}

const props = defineProps<{
  results?: SearchResult[];
  isSearching?: boolean;
  query?: string;
  explicitResults?: boolean;
  provider?: string | null;
  searchDepth?: string | null;
  creditsUsed?: number | null;
  intentTier?: string | null;
}>();

const emit = defineEmits<{
  (e: 'browseUrl', url: string): void;
}>();

const showEmptyState = computed(() => !!props.explicitResults && (!props.results || props.results.length === 0));

// Progressive result reveal (staggered animation effect)
// Only enabled during active search for perceived streaming UX
const { visibleResults } = useStaggeredResults(toRef(props, 'results'), {
  delayMs: 150,
  enabled: props.isSearching ?? false,
});

// Use staggered results when searching, otherwise show all results immediately
const displayResults = computed(() => {
  if (props.isSearching) {
    return visibleResults.value;
  }
  return props.results || [];
});

// Track favicon load errors
const faviconErrors = reactive<Record<string, boolean>>({});

function getFavicon(link: string): string {
  return getFaviconUrl(link) ?? '';
}

function getIconLetter(result: SearchResult): string {
  if (!result.link && !result.title) return '?';
  try {
    const url = new URL(result.link);
    const hostname = url.hostname.replace('www.', '');
    if (hostname.includes('wikipedia')) return 'W';
    if (hostname.includes('github')) return 'G';
    if (hostname.includes('stackoverflow')) return 'S';
    if (hostname.includes('reddit')) return 'R';
    if (hostname.includes('youtube')) return 'Y';
    if (hostname.includes('twitter') || hostname.includes('x.com')) return 'X';
    if (hostname.includes('linkedin')) return 'in';
    if (hostname.includes('medium')) return 'M';
    return hostname.charAt(0).toUpperCase();
  } catch {
    return result.title?.charAt(0).toUpperCase() || '?';
  }
}

function formatSnippet(snippet: string): string {
  if (!snippet) return '';
  const cleaned = snippet.replace(/\s+/g, ' ').trim();
  if (cleaned.length > 180) {
    return cleaned.slice(0, 180).trim() + ' ...';
  }
  return cleaned;
}

function handleFaviconError(_event: Event, link: string) {
  faviconErrors[link] = true;
  markFaviconFailed(link);
}

function handleResultClick(result: SearchResult) {
  if (result.link) {
    emit('browseUrl', result.link);
  }
}
</script>

<style scoped>
.search-view {
  height: 100%;
  background: var(--background-white-main);
}

.search-results {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.search-results-list {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

/* Result slide-in transition */
.result-slide-enter-active {
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.result-slide-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

/* ── Individual Result Item (Pythinker-style) ── */
.search-result-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 20px;
  cursor: pointer;
  transition: background-color 0.12s ease;
}

.search-result-item:hover {
  background-color: var(--fill-tsp-gray-main);
}

/* ── Circular Favicon ── */
.result-icon-wrapper {
  width: 24px;
  height: 24px;
  min-width: 24px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  margin-top: 1px;
  flex-shrink: 0;
}

.result-favicon {
  width: 14px;
  height: 14px;
  object-fit: contain;
}

.result-icon-fallback {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  line-height: 1;
}

/* ── Result Body (title + snippet) ── */
.result-body {
  flex: 1;
  min-width: 0;
}

.result-title {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
  line-height: 1.35;
  letter-spacing: -0.008em;
  margin: 0;
}

.result-snippet {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 400;
  line-height: 1.45;
  margin: 2px 0 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Skeleton ── */
.search-skeleton {
  padding: 4px 0;
  flex: 1;
}

.skeleton-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 20px;
  animation: skeleton-fade 1.2s ease-in-out infinite alternate;
}

.skeleton-icon {
  width: 24px;
  height: 24px;
  min-width: 24px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main);
}

.skeleton-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 2px;
}

.skeleton-line {
  height: 12px;
  border-radius: 6px;
  background: var(--fill-tsp-gray-main);
}

.skeleton-title { width: 60%; }
.skeleton-snippet { width: 85%; }

@keyframes skeleton-fade {
  0% { opacity: 0.35; }
  100% { opacity: 0.7; }
}

/* ── Empty State ── */
.search-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.search-empty-icon {
  color: var(--text-tertiary);
  opacity: 0.4;
  margin-bottom: 12px;
}

.search-empty-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  margin: 0;
}

.search-empty-query {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 4px 0 0;
}
</style>
