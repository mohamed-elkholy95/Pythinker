<template>
  <ContentContainer
    :centered="!!isSearching"
    :constrained="false"
    padding="none"
    class="search-view"
  >
    <LoadingState
      v-if="isSearching && (!results || results.length === 0) && !explicitResults"
      :label="t('Searching')"
      :detail="searchDetail"
      animation="search"
    />

    <!-- Search Results - EU Policy Portal Style -->
    <div v-else class="search-results">
      <div class="search-bar">
        <Search class="search-bar-icon" />
        <input
          class="search-bar-input"
          :value="query || ''"
          placeholder="Search"
          readonly
        />
        <span v-if="isSearching" class="searching-pill">{{ t('Searching') }}</span>
      </div>
      <div class="search-results-list">
        <div
          v-for="(result, index) in results"
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

        <EmptyState
          v-if="showEmptyState"
          message="No results from provider"
          icon="search"
        />
      </div>
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue';
import { useI18n } from 'vue-i18n';
import { Search } from 'lucide-vue-next';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';

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
}>();

const emit = defineEmits<{
  (e: 'browseUrl', url: string): void;
}>();

const { t } = useI18n();
const searchDetail = computed(() => (props.query ? `"${props.query}"` : ''));
const showEmptyState = computed(() => !!props.explicitResults && (!props.results || props.results.length === 0));

// Track favicon load errors
const faviconErrors = reactive<Record<string, boolean>>({});

/**
 * Get favicon URL for a given link using Google's favicon service
 */
function getFavicon(link: string): string {
  if (!link) return '';
  try {
    const url = new URL(link);
    return `https://www.google.com/s2/favicons?domain=${url.hostname}&sz=32`;
  } catch {
    return '';
  }
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
  if (cleaned.length > 120) {
    return cleaned.slice(0, 120).trim() + '...';
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

:global(.dark) .search-view {
  background: #1a1a1a;
}

/* Results Container */
.search-results {
  display: flex;
  flex-direction: column;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin: 12px 12px 8px 12px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.06);
}

.search-bar-icon {
  width: 16px;
  height: 16px;
  color: var(--icon-secondary);
}

.search-bar-input {
  border: none;
  outline: none;
  background: transparent;
  width: 100%;
  font-size: 13px;
  color: var(--text-primary);
}

.search-bar-input::placeholder {
  color: var(--text-tertiary);
}

.searching-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-light);
  white-space: nowrap;
}

.search-results-list {
  display: flex;
  flex-direction: column;
}

/* Individual Result Item */
.search-result-item {
  padding: 12px 20px;
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

:global(.dark) .search-result-item {
  border-bottom-color: #2a2a2a;
}

:global(.dark) .search-result-item:hover {
  background-color: #222222;
}

/* Header: Icon + Title */
.result-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 4px;
}

/* Circular Icon Wrapper */
.result-icon-wrapper {
  width: 22px;
  height: 22px;
  min-width: 22px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  margin-top: 1px;
}

:global(.dark) .result-icon-wrapper {
  background: #333333;
}

/* Favicon Image */
.result-favicon {
  width: 12px;
  height: 12px;
  object-fit: contain;
}

/* Fallback Letter Icon */
.result-icon-fallback {
  font-size: 10px;
  font-weight: 500;
  color: var(--text-tertiary);
  letter-spacing: -0.02em;
  line-height: 1;
}

:global(.dark) .result-icon-fallback {
  color: #999999;
}

/* Result Title */
.result-title {
  color: var(--text-primary);
  font-size: 14.5px;
  font-weight: 600;
  line-height: 1.35;
  letter-spacing: -0.01em;
  margin: 0;
  flex: 1;
}

:global(.dark) .result-title {
  color: #e5e5e5;
}

/* Result Snippet/Description */
.result-snippet {
  color: var(--text-secondary);
  font-size: 13.5px;
  font-weight: 400;
  line-height: 1.45;
  margin: 0;
  margin-left: 32px; /* 22px icon + 10px gap */
  letter-spacing: -0.005em;
}

:global(.dark) .result-snippet {
  color: #8a8a8a;
}

/* Read More Link */
.read-more-link {
  color: var(--text-tertiary);
  text-decoration: none;
  font-size: 13.5px;
  font-weight: 400;
  cursor: pointer;
}

.read-more-link:hover {
  color: var(--text-secondary);
}

:global(.dark) .read-more-link {
  color: #777777;
}

:global(.dark) .read-more-link:hover {
  color: #aaaaaa;
}

/* Empty State Adjustments */
.search-view :deep(.empty-state) {
  padding: 48px 24px;
}

.search-view :deep(.empty-icon) {
  color: #9a9a9a;
}

.search-view :deep(.empty-message) {
  color: #6a6a6a;
  font-weight: 400;
}

:global(.dark) .search-view :deep(.empty-icon) {
  color: #666666;
}

:global(.dark) .search-view :deep(.empty-message) {
  color: #888888;
}
</style>
