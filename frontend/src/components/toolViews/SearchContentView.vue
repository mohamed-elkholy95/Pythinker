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

    <!-- Search Results -->
    <div v-else class="search-results">
      <div
        v-for="(result, index) in results"
        :key="result.link || index"
        class="search-result-item"
        @click="handleResultClick(result)"
      >
        <div class="result-title-row">
          <img
            :src="getFavicon(result.link)"
            alt=""
            class="result-favicon"
            @error="handleFaviconError"
          />
          <span class="result-title">{{ result.title }}</span>
        </div>
        <p class="result-snippet">{{ formatSnippet(result.snippet) }}<span class="read-more">Read more</span></p>
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
import { computed } from 'vue';
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
 * Format snippet - normalize whitespace and add ellipsis
 */
function formatSnippet(snippet: string): string {
  if (!snippet) return '...';
  const cleaned = snippet.replace(/\s+/g, ' ').trim();
  if (cleaned.length > 130) {
    return cleaned.slice(0, 130).trim() + ' ...';
  }
  return cleaned + '...';
}

/**
 * Handle favicon load error by hiding the image
 */
function handleFaviconError(event: Event) {
  const img = event.target as HTMLImageElement;
  img.style.visibility = 'hidden';
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
  background: #f5f5f4;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
}

.search-results {
  display: flex;
  flex-direction: column;
}

.search-result-item {
  padding: 20px 24px;
  border-bottom: 1px solid #e5e5e5;
  cursor: pointer;
}

.search-result-item:last-child {
  border-bottom: none;
}

.result-title-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 4px;
}

.result-favicon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  margin-top: 2px;
}

.result-title {
  color: #1a1a1a;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: -0.01em;
}

.result-snippet {
  color: #6b6b6b;
  font-size: 14px;
  line-height: 1.5;
  margin: 0;
  letter-spacing: -0.005em;
}

.read-more {
  color: #9a9a9a;
}
</style>
