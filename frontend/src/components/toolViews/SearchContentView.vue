<template>
  <ContentContainer
    :centered="false"
    :constrained="false"
    padding="none"
    class="search-view"
  >
    <!-- Active Search: Progressive results feed -->
    <div v-if="isSearching" class="search-results">
      <div class="search-bar">
        <Search class="search-bar-icon" />
        <input
          class="search-bar-input"
          :value="query || ''"
          placeholder="Search"
          readonly
        />
        <span class="searching-pill">
          <Loader2 :size="10" class="searching-pill-spinner" />
          {{ t('Searching') }}
        </span>
      </div>

      <!-- Progressive results as they stream in -->
      <div v-if="displayResults && displayResults.length > 0" class="search-results-list">
        <TransitionGroup name="result-slide">
          <div
            v-for="(result, index) in displayResults"
            :key="result.link || index"
            class="search-result-item"
            @click="handleResultClick(result)"
          >
            <div class="result-header">
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
              <h3 class="result-title">{{ result.title }}</h3>
              <Check :size="14" class="result-done-check" />
            </div>
            <p class="result-snippet">
              {{ formatSnippet(result.snippet) }}<a
                class="read-more-link"
                @click.stop="handleResultClick(result)"
              >Read more</a>
            </p>
          </div>
        </TransitionGroup>
      </div>

      <!-- Skeleton loading when no results yet -->
      <div v-else class="search-skeleton">
        <div v-for="i in 4" :key="i" class="skeleton-item">
          <div class="skeleton-icon"></div>
          <div class="skeleton-lines">
            <div class="skeleton-line skeleton-title"></div>
            <div class="skeleton-line skeleton-snippet"></div>
          </div>
        </div>
      </div>

      <!-- Activity bar at bottom -->
      <div class="search-activity-bar">
        <div class="activity-pulse"></div>
        <span class="activity-text">
          {{ displayResults?.length || 0 }} {{ t('sources found') }}
        </span>
      </div>
    </div>

    <!-- Completed Search Results -->
    <div v-else class="search-results">
      <div class="search-bar">
        <Search class="search-bar-icon" />
        <input
          class="search-bar-input"
          :value="query || ''"
          placeholder="Search"
          readonly
        />
        <span v-if="results && results.length > 0" class="results-count-pill">
          {{ results.length }} {{ t('results') }}
        </span>
        <span v-if="provider" class="search-meta-pill provider-pill">
          {{ provider }}
        </span>
        <span v-if="searchDepth" class="search-meta-pill depth-pill">
          {{ searchDepth }}
        </span>
        <span v-if="creditsUsed != null" class="search-meta-pill credits-pill">
          {{ creditsUsed }} cr
        </span>
      </div>
      <div class="search-results-list">
        <div
          v-for="(result, index) in displayResults"
          :key="result.link || index"
          class="search-result-item"
          @click="handleResultClick(result)"
        >
          <!-- Icon + Title Row -->
          <div class="result-header">
            <div class="result-icon-wrapper">
              <img
                v-if="!faviconErrors[result.link]"
                :src="getFavicon(result.link)"
                alt=""
                class="result-favicon"
                @error="handleFaviconError($event, result.link)"
              />
              <span v-else class="result-icon-fallback">
                {{ getIconLetter(result) }}
              </span>
            </div>
            <h3 class="result-title">{{ result.title }}</h3>
          </div>

          <!-- Snippet/Description -->
          <p class="result-snippet">
            {{ formatSnippet(result.snippet) }}<a
              class="read-more-link"
              @click.stop="handleResultClick(result)"
            >Read more</a>
          </p>
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
import { useI18n } from 'vue-i18n';
import { Search, Loader2, Check } from 'lucide-vue-next';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import { getFaviconUrl } from '@/utils/toolDisplay';
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

const { t } = useI18n();
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

/**
 * Get favicon URL for a given link, using shared utility
 */
function getFavicon(link: string): string {
  return getFaviconUrl(link) ?? '';
}

/**
 * Get a letter icon fallback based on the domain or title
 */
function getIconLetter(result: SearchResult): string {
  if (!result.link && !result.title) return '?';

  try {
    const url = new URL(result.link);
    const hostname = url.hostname.replace('www.', '');

    // Special cases for common domains
    if (hostname.includes('wikipedia')) return 'W';
    if (hostname.includes('github')) return 'G';
    if (hostname.includes('stackoverflow')) return 'S';
    if (hostname.includes('reddit')) return 'R';
    if (hostname.includes('youtube')) return 'Y';
    if (hostname.includes('twitter') || hostname.includes('x.com')) return 'X';
    if (hostname.includes('linkedin')) return 'in';
    if (hostname.includes('medium')) return 'M';

    // Return first letter of domain
    return hostname.charAt(0).toUpperCase();
  } catch {
    // Fallback to first letter of title
    return result.title?.charAt(0).toUpperCase() || '?';
  }
}

/**
 * Format snippet - normalize whitespace
 */
function formatSnippet(snippet: string): string {
  if (!snippet) return '';
  const cleaned = snippet.replace(/\s+/g, ' ').trim();
  if (cleaned.length > 95) {
    return cleaned.slice(0, 95).trim() + '...';
  }
  return cleaned;
}

/**
 * Handle favicon load error
 */
function handleFaviconError(_event: Event, link: string) {
  faviconErrors[link] = true;
}

/**
 * Handle click on search result - emit event to navigate browser
 */
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
  font-family: var(--font-sans);
}

/* Results Container */
.search-results {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  margin: 8px 8px 6px 8px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
  box-shadow: 0 4px 10px var(--shadow-XS);
}

.search-bar-icon {
  width: 14px;
  height: 14px;
  color: var(--icon-secondary);
}

.search-bar-input {
  border: none;
  outline: none;
  background: transparent;
  width: 100%;
  font-size: 12px;
  color: var(--text-primary);
}

.search-bar-input::placeholder {
  color: var(--text-tertiary);
}

.searching-pill {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-brand);
  background: var(--fill-blue);
  border: 1px solid rgba(59, 130, 246, 0.2);
  white-space: nowrap;
}

.searching-pill-spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.results-count-pill {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-tertiary);
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-light);
  white-space: nowrap;
}

.search-results-list {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow-y: auto;
}

/* Result slide-in transition */
.result-slide-enter-active {
  transition: all 0.3s ease-out;
}
.result-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

/* Individual Result Item */
.search-result-item {
  padding: 8px 14px;
  border-bottom: 1px solid var(--border-light);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.search-result-item:hover {
  background-color: var(--fill-tsp-gray-main);
}

.search-result-item:last-child {
  border-bottom: none;
}

/* Header: Icon + Title */
.result-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 2px;
}

/* Circular Icon Wrapper */
.result-icon-wrapper {
  width: 18px;
  height: 18px;
  min-width: 18px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  margin-top: 2px;
}

/* Favicon Image */
.result-favicon {
  width: 10px;
  height: 10px;
  object-fit: contain;
}

/* Fallback Letter Icon */
.result-icon-fallback {
  font-size: 9px;
  font-weight: 500;
  color: var(--text-tertiary);
  letter-spacing: -0.02em;
  line-height: 1;
}

/* Result Title */
.result-title {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.25;
  letter-spacing: -0.01em;
  margin: 0;
  flex: 1;
}

/* Check mark on each discovered result during search */
.result-done-check {
  flex-shrink: 0;
  color: var(--function-success);
  opacity: 0.6;
  margin-left: auto;
  margin-top: 1px;
}

/* Result Snippet/Description */
.result-snippet {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 400;
  line-height: 1.35;
  margin: 0;
  margin-left: 26px; /* 18px icon + 8px gap */
  letter-spacing: -0.005em;
}

/* Read More Link */
.read-more-link {
  color: var(--text-tertiary);
  text-decoration: none;
  font-size: 12px;
  font-weight: 400;
  cursor: pointer;
}

.read-more-link:hover {
  color: var(--text-secondary);
}

/* Skeleton loading placeholders */
.search-skeleton {
  padding: 6px 0;
  flex: 1;
}

.skeleton-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 14px;
}

.skeleton-icon {
  width: 18px;
  height: 18px;
  min-width: 18px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main);
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skeleton-line {
  height: 10px;
  border-radius: 4px;
  background: var(--fill-tsp-gray-main);
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-title { width: 65%; }
.skeleton-snippet { width: 90%; animation-delay: 0.15s; }

@keyframes skeleton-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.8; }
}

/* Activity bar at bottom during search */
.search-activity-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-top: 1px solid var(--border-light);
  background: var(--background-white-main);
  flex-shrink: 0;
}

.activity-pulse {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--text-brand);
  animation: pulse-dot 1.5s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

.activity-text {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 500;
}

/* Empty State */
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
  opacity: 0.5;
  margin-bottom: 12px;
}

.search-empty-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0;
}

.search-empty-query {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 4px 0 0;
  font-style: italic;
}

.search-meta-pill {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.provider-pill {
  background-color: var(--color-surface-2, #e8e8e8);
  color: var(--color-text-secondary, #666);
}

.depth-pill {
  background-color: var(--color-accent-muted, #e3f2fd);
  color: var(--color-accent, #1976d2);
}

.credits-pill {
  background-color: var(--color-warning-muted, #fff3e0);
  color: var(--color-warning, #e65100);
}
</style>
