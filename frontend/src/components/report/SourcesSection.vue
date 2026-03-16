<template>
  <div v-if="sources && sources.length > 0" class="sources-section">
    <h3 class="text-sm font-semibold text-[var(--text-tertiary)] mb-3 flex items-center gap-2">
      <BookOpen class="w-4 h-4" />
      References ({{ sources.length }})
    </h3>
    <ol class="space-y-2.5">
      <li
        v-for="(source, index) in sources"
        :key="source.url"
        class="flex items-start gap-2 text-sm group"
      >
        <span class="text-[var(--text-quaternary)] text-xs font-mono min-w-[24px]">
          [{{ index + 1 }}]
        </span>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <img
              v-if="!faviconErrors[source.url]"
              :src="getFaviconUrl(source.url)"
              :alt="getDomain(source.url)"
              class="w-4 h-4 flex-shrink-0 rounded"
              @error="handleFaviconError(source.url)"
            />
            <span
              v-else
              class="w-4 h-4 flex-shrink-0 rounded bg-[var(--fill-tsp-gray-main)] text-[var(--text-tertiary)] text-[10px] font-semibold flex items-center justify-center"
            >{{ getIconLetterFromUrl(source.url, source.title) }}</span>
            <a
              :href="source.url"
              target="_blank"
              rel="noopener noreferrer"
              class="text-[#1a73e8] hover:underline truncate flex-1"
              :title="source.title"
            >
              {{ source.title }}
            </a>
          </div>
          <div class="flex items-center gap-1.5 mt-0.5">
            <span class="text-[var(--text-quaternary)] text-xs">
              {{ getDomain(source.url) }}
            </span>
            <span
              v-if="source.source_type"
              class="text-[10px] px-1.5 py-0.5 rounded bg-[var(--fill-tsp-gray-main)] text-[var(--text-tertiary)]"
            >
              {{ formatSourceType(source.source_type) }}
            </span>
          </div>
          <p
            v-if="source.snippet && showSnippets"
            class="text-xs text-[var(--text-secondary)] mt-1 line-clamp-2"
          >
            {{ source.snippet }}
          </p>
        </div>
        <ExternalLink
          class="w-3.5 h-3.5 text-[var(--icon-tertiary)] opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 mt-0.5"
        />
      </li>
    </ol>
  </div>
</template>

<script setup lang="ts">
import { BookOpen, ExternalLink } from 'lucide-vue-next';
import { getFaviconUrl as getSharedFaviconUrl, markFaviconFailed, getIconLetterFromUrl } from '@/utils/toolDisplay';
import type { SourceCitation } from '@/types/message';
import { reactive } from 'vue';

interface Props {
  sources?: SourceCitation[];
  showSnippets?: boolean;
}

withDefaults(defineProps<Props>(), {
  sources: () => [],
  showSnippets: false
});

const getFaviconUrl = (url: string): string => getSharedFaviconUrl(url) ?? '';

const getDomain = (url: string): string => {
  try {
    return new URL(url).hostname.replace('www.', '');
  } catch {
    return url;
  }
};

const formatSourceType = (type: string): string => {
  const typeMap: Record<string, string> = {
    'search': 'Search',
    'browser': 'Visited',
    'file': 'File'
  };
  return typeMap[type] || type;
};

const faviconErrors: Record<string, boolean> = reactive({});

const handleFaviconError = (url: string) => {
  faviconErrors[url] = true;
  markFaviconFailed(url);
};
</script>

<style scoped>
.sources-section {
  border-top: 1px solid var(--border-light);
  padding-top: 1rem;
  margin-top: 1rem;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
