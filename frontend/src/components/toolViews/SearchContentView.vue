<template>
  <ContentContainer
    :centered="!!isSearching"
    :constrained="!isSearching"
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
        class="search-result-card"
        @click="handleResultClick(result)"
      >
        <div class="result-header">
          <img
            :src="getFavicon(result.link)"
            :alt="getDomain(result.link)"
            class="result-favicon"
            @error="handleFaviconError"
          />
          <div class="result-meta">
            <span class="result-domain">{{ getDomain(result.link) }}</span>
          </div>
        </div>
        <div class="result-title">{{ result.title }}</div>
        <div class="result-snippet">{{ result.snippet }}</div>
        <div class="result-actions">
          <button
            class="browse-button"
            @click.stop="handleResultClick(result)"
          >
            <ExternalLink :size="14" />
            {{ t('Open in Browser') }}
          </button>
        </div>
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
import { ExternalLink } from 'lucide-vue-next';
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
 * Extract domain from URL for display
 */
function getDomain(link: string): string {
  if (!link) return '';
  try {
    const url = new URL(link);
    return url.hostname.replace(/^www\./, '');
  } catch {
    return link;
  }
}

/**
 * Handle favicon load error by hiding the image
 */
function handleFaviconError(event: Event) {
  const img = event.target as HTMLImageElement;
  img.style.display = 'none';
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
}

.search-results {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-2);
}

.search-result-card {
  padding: var(--space-3);
  border-radius: 8px;
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  cursor: pointer;
  transition: all 0.15s ease;
}

.search-result-card:hover {
  border-color: var(--border-dark);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  transform: translateY(-1px);
}

.result-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.result-favicon {
  width: 16px;
  height: 16px;
  border-radius: 2px;
  flex-shrink: 0;
}

.result-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.result-domain {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-title {
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  line-height: 1.4;
  margin-bottom: var(--space-1);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.search-result-card:hover .result-title {
  color: var(--text-brand);
}

.result-snippet {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.result-actions {
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--border-light);
  display: flex;
  justify-content: flex-end;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.search-result-card:hover .result-actions {
  opacity: 1;
}

.browse-button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-brand);
  background: var(--fill-tsp-gray-main);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.browse-button:hover {
  background: var(--text-brand);
  color: white;
}
</style>
