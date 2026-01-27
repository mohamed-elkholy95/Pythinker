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
      <div v-for="(result, index) in results" :key="result.link || index" class="search-result">
        <a
          :href="result.link"
          target="_blank"
          class="search-title"
        >
          {{ result.title }}
        </a>
        <div class="search-snippet">{{ result.snippet }}</div>
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

const { t } = useI18n();
const searchDetail = computed(() => (props.query ? `"${props.query}"` : ''));
</script>

<style scoped>
.search-view {
  height: 100%;
}

.search-results {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.search-result {
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-light);
}

.search-result:last-child {
  border-bottom: none;
}

.search-title {
  display: block;
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  text-decoration: none;
}

.search-title:hover {
  text-decoration: underline;
}

.search-snippet {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  margin-top: var(--space-1);
  line-height: 1.4;
}
</style>
