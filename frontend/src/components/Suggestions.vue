<template>
  <div
    v-if="suggestions.length > 0"
    class="flex flex-col w-full sm:w-[600px] mx-auto rounded-[16px] border border-[var(--border-light)] bg-[var(--background-card)] overflow-hidden"
  >
    <!-- Header -->
    <div class="px-4 pt-4 pb-2">
      <span class="text-sm text-[var(--text-tertiary)]">Suggested follow-ups</span>
    </div>

    <!-- Suggestion Items -->
    <div class="flex flex-col">
      <div
        v-for="(suggestion, index) in suggestions"
        :key="index"
        class="group flex items-start gap-3 px-4 py-4 cursor-pointer border-t border-[var(--border-light)] transition-colors hover:bg-[var(--fill-tsp-white-light)]"
        @click="$emit('select', suggestion)"
      >
        <div class="flex-shrink-0 mt-0.5">
          <div
            class="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--border-light)] bg-[var(--fill-tsp-white-main)]"
          >
            <component
              :is="getSuggestionIcon(index)"
              class="h-4 w-4 text-[var(--icon-tertiary)] transition-colors group-hover:text-[var(--icon-primary)]"
            />
          </div>
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-base text-[var(--text-primary)] leading-relaxed font-medium">
            {{ suggestion }}
          </p>
        </div>
        <div class="flex-shrink-0 mt-1">
          <ArrowRight class="w-5 h-5 text-[var(--icon-tertiary)] transition-colors group-hover:text-[var(--icon-primary)]" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { MessageSquare, FileText, ArrowRight } from 'lucide-vue-next';

defineProps<{
  suggestions: string[];
}>();

defineEmits<{
  (e: 'select', suggestion: string): void;
}>();

// Alternate icons for variety
const getSuggestionIcon = (index: number) => {
  const icons = [MessageSquare, MessageSquare, FileText];
  return icons[index % icons.length];
};
</script>

<style scoped>
/* Additional styling if needed */
</style>
