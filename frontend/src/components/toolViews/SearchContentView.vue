<template>
  <ContentContainer
    :centered="!!isSearching"
    :constrained="false"
    padding="none"
    class="search-view"
  >
    <LoadingState
      v-if="isSearching"
      :label="t('Searching')"
      :detail="searchDetail"
      animation="search"
    />

    <!-- Search Results - EU Policy Portal Style -->
    <div v-else class="search-results">
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
        v-if="!results || results.length === 0"
        message="No results found"
        icon="search"
      />
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue';
import { useI18n } from 'vue-i18n';
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
}>();

const emit = defineEmits<{
  (e: 'browseUrl', url: string): void;
}>();

const { t } = useI18n();
const searchDetail = computed(() => (props.query ? `"${props.query}"` : ''));

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
  background: #fafafa;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
}

:global(.dark) .search-view {
  background: #1a1a1a;
}

/* Results Container */
.search-results {
  display: flex;
  flex-direction: column;
}

/* Individual Result Item */
.search-result-item {
  padding: 12px 20px;
  border-bottom: 1px solid #e5e5e5;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.search-result-item:hover {
  background-color: #f0f0f0;
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
  background: #ebebeb;
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
  color: #666666;
  letter-spacing: -0.02em;
  line-height: 1;
}

:global(.dark) .result-icon-fallback {
  color: #999999;
}

/* Result Title */
.result-title {
  color: #1a1a1a;
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
  color: #6b6b6b;
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
  color: #9a9a9a;
  text-decoration: none;
  font-size: 13.5px;
  font-weight: 400;
  cursor: pointer;
}

.read-more-link:hover {
  color: #666666;
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
