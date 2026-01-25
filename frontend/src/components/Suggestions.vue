<template>
  <div v-if="suggestions.length > 0" class="flex flex-col w-full">
    <!-- Header -->
    <div class="pb-3">
      <span class="text-base text-[var(--text-tertiary)]">Suggested follow-ups</span>
    </div>

    <!-- Suggestion Items -->
    <div class="flex flex-col">
      <div
        v-for="(suggestion, index) in suggestions"
        :key="index"
        class="flex items-start gap-4 py-4 cursor-pointer hover:bg-[var(--fill-tsp-white-light)] transition-colors group border-t border-[var(--border-light)]"
        @click="$emit('select', suggestion)"
      >
        <div class="flex-shrink-0 mt-1">
          <component :is="getSuggestionIcon(index)" class="w-6 h-6 text-[var(--icon-tertiary)]" />
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-base text-[var(--text-primary)] leading-relaxed font-medium">
            {{ suggestion }}
          </p>
        </div>
        <div class="flex-shrink-0 mt-1">
          <ArrowRight class="w-5 h-5 text-[var(--icon-tertiary)] group-hover:text-[var(--icon-primary)] transition-colors" />
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
