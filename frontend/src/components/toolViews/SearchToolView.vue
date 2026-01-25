<template>
  <div
    class="h-[36px] flex items-center px-3 w-full bg-[var(--background-gray-main)] border-b border-[var(--border-main)] rounded-t-[12px] shadow-[inset_0px_1px_0px_0px_#FFFFFF] dark:shadow-[inset_0px_1px_0px_0px_#FFFFFF30]">
    <div class="flex-1 flex items-center justify-center">
      <div class="max-w-[250px] truncate text-[var(--text-tertiary)] text-sm font-medium text-center">
        {{ isSearching ? (searchQuery || 'Search') : 'Search' }}
      </div>
    </div>
  </div>
  <div class="flex-1 min-h-0 w-full overflow-y-auto">
    <!-- Searching Animation -->
    <div v-if="isSearching" class="flex-1 h-full flex flex-col items-center justify-center bg-gradient-to-b from-[var(--background-gray-main)] to-[var(--fill-white)] dark:from-[#1a1a2e] dark:to-[#16213e] py-12">
      <div class="search-animation">
        <!-- Animated search rings -->
        <div class="search-rings">
          <div class="ring ring-1"></div>
          <div class="ring ring-2"></div>
          <div class="ring ring-3"></div>
        </div>
        <!-- Search icon -->
        <svg class="search-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="2"/>
          <path d="M16 16l4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </div>
      <div class="mt-6 flex flex-col items-center gap-2">
        <div class="flex items-center gap-2 text-[var(--text-secondary)]">
          <span class="text-base font-medium">{{ t('Searching') }}</span>
          <span class="flex gap-1">
            <span v-for="(_, i) in 3" :key="i" class="dot" :style="{ animationDelay: `${i * 200}ms` }"></span>
          </span>
        </div>
        <div v-if="searchQuery" class="max-w-[280px] text-center text-xs text-[var(--text-tertiary)] truncate px-4">
          "{{ searchQuery }}"
        </div>
      </div>
    </div>
    <!-- Search Results -->
    <div v-else class="flex-1 min-h-0 max-w-[640] mx-auto">
      <div class="flex flex-col overflow-auto h-full px-4 py-3">
        <div v-for="(result, index) in toolContent.content?.results" :key="result.link || index" class="py-3 pt-0 border-b border-[var(--border-light)]">
          <a :href="result.link" target="_blank"
            class="block text-[var(--text-primary)] text-sm font-medium hover:underline line-clamp-2 cursor-pointer">
            {{ result.title }}
          </a>
          <div class="text-[var(--text-tertiary)] text-xs mt-0.5 line-clamp-3">{{ result.snippet }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ToolContent } from '@/types/message';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps<{
  sessionId: string;
  toolContent: ToolContent;
  live: boolean;
}>();

const { t } = useI18n();

// Detect if search is in progress
const isSearching = computed(() => {
  return props.toolContent?.status === 'calling';
});

// Extract search query for display
const searchQuery = computed(() => {
  return props.toolContent?.args?.query || '';
});
</script>

<style scoped>
/* Search Animation Styles */
.search-animation {
  position: relative;
  width: 100px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.search-rings {
  position: absolute;
  width: 100%;
  height: 100%;
}

.ring {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  border: 2px solid var(--text-brand);
  opacity: 0;
  animation: pulse-ring 2s ease-out infinite;
}

.ring-1 {
  width: 40px;
  height: 40px;
  animation-delay: 0s;
}

.ring-2 {
  width: 60px;
  height: 60px;
  animation-delay: 0.4s;
}

.ring-3 {
  width: 80px;
  height: 80px;
  animation-delay: 0.8s;
}

.search-icon {
  width: 32px;
  height: 32px;
  color: var(--text-brand);
  animation: search-bounce 1.5s ease-in-out infinite;
}

/* Bouncing dots */
.dot {
  display: inline-block;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: var(--text-tertiary);
  animation: bounce-dot 1.4s ease-in-out infinite;
}

@keyframes pulse-ring {
  0% {
    transform: translate(-50%, -50%) scale(0.8);
    opacity: 0.6;
  }
  100% {
    transform: translate(-50%, -50%) scale(1.5);
    opacity: 0;
  }
}

@keyframes search-bounce {
  0%, 100% {
    transform: translateY(0) scale(1);
  }
  50% {
    transform: translateY(-4px) scale(1.05);
  }
}

@keyframes bounce-dot {
  0%, 80%, 100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-6px);
  }
}
</style>
