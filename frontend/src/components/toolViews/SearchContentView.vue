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
                v-if="!isFaviconError(result.link)"
                :src="getFavicon(result.link)"
                alt=""
                class="result-favicon"
                @error="onFaviconError(result.link)"
              />
              <span v-else class="result-icon-fallback">{{ getIconLetter(result) }}</span>
            </div>
            <div class="result-body">
              <div class="result-title">{{ result.title }}</div>
              <p v-if="result.snippet" class="result-snippet">{{ formatSnippet(result.snippet) }}</p>
            </div>
          </div>
        </TransitionGroup>
      </div>

      <!-- Skeleton loading when no results yet -->
      <div v-else class="search-skeleton">
        <div v-for="i in 5" :key="i" class="skeleton-item" :style="{ animationDelay: `${i * 0.1}s` }">
          <div class="skeleton-icon" />
          <div class="skeleton-lines">
            <div class="skeleton-line skeleton-title" />
            <div class="skeleton-line skeleton-snippet" />
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
              v-if="!isFaviconError(result.link)"
              :src="getFavicon(result.link)"
              alt=""
              class="result-favicon"
              @error="onFaviconError(result.link)"
            />
            <span v-else class="result-icon-fallback">{{ getIconLetter(result) }}</span>
          </div>
          <div class="result-body">
            <div class="result-title">{{ result.title }}</div>
            <p v-if="result.snippet" class="result-snippet">{{ formatSnippet(result.snippet) }}</p>
          </div>
        </div>

        <div v-if="showEmptyState" class="search-empty-state">
          <Search :size="28" class="search-empty-icon" />
          <p class="search-empty-text">No results found</p>
          <p v-if="query" class="search-empty-query">for "{{ query }}"</p>
        </div>
      </div>
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue';
import { Search } from 'lucide-vue-next';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import { useStaggeredResults } from '@/composables/useStaggeredResults';
import { useFavicon } from '@/composables/useFavicon';

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

const { getUrl: getFavicon, isError: isFaviconError, handleError: onFaviconError, getLetter } = useFavicon();

function getIconLetter(result: SearchResult): string {
  if (!result.link && !result.title) return '?';
  return getLetter(result.link, result.title);
}

function formatSnippet(snippet: string): string {
  if (!snippet) return '';
  // Strip markdown artifacts: headings, bold, italic, links, list markers
  let cleaned = snippet
    .replace(/^#{1,6}\s+/gm, '')        // Markdown headings
    .replace(/\*{1,2}([^*]+)\*{1,2}/g, '$1') // Bold/italic
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // Links [text](url)
    .replace(/^[\s]*[-*+]\s+/gm, '')    // List markers
    .replace(/`([^`]+)`/g, '$1')         // Inline code
    .replace(/\s+/g, ' ')
    .trim();
  if (cleaned.length > 200) {
    cleaned = cleaned.slice(0, 200).trim() + '...';
  }
  return cleaned;
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
}

/* ── Result slide-in transition ── */
.result-slide-enter-active {
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.result-slide-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

/* ── Individual Result Item ── */
.search-result-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 24px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-light);
  transition: background-color 0.15s ease;
}

.search-result-item:last-of-type {
  border-bottom: none;
}

.search-result-item:hover {
  background-color: var(--fill-tsp-gray-main);
}

/* ── Favicon Icon ── */
.result-icon-wrapper {
  width: 24px;
  height: 24px;
  min-width: 24px;
  border-radius: 50%;
  background: var(--fill-tsp-white-dark);
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
  font-size: 10px;
  font-weight: 700;
  color: var(--text-secondary);
  line-height: 1;
}

/* ── Result Body ── */
.result-body {
  flex: 1;
  min-width: 0;
}

.result-title {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: -0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-snippet {
  color: #9a9a9a;
  font-size: 13px;
  font-weight: 400;
  line-height: 1.5;
  margin: 2px 0 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Skeleton ── */
.search-skeleton {
  flex: 1;
}

.skeleton-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-light);
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
  gap: 8px;
  padding-top: 2px;
}

.skeleton-line {
  height: 12px;
  border-radius: 6px;
  background: var(--fill-tsp-gray-main);
}

.skeleton-title { width: 55%; height: 14px; }
.skeleton-snippet { width: 80%; }

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
