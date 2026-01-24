<template>
  <div v-if="suggestions.length > 0" class="flex flex-col w-full max-w-[640px] rounded-[16px] border border-[var(--border-main)] bg-[var(--background-card)] overflow-hidden shadow-sm">
    <!-- Header -->
    <div class="px-4 pt-4 pb-2">
      <span class="text-sm text-[var(--text-tertiary)]">Suggested follow-ups</span>
    </div>

    <!-- Suggestion Items -->
    <div class="flex flex-col">
      <div
        v-for="(suggestion, index) in suggestions"
        :key="index"
        class="flex items-start gap-3 px-4 py-3 cursor-pointer hover:bg-[var(--fill-tsp-white-main)] transition-colors group"
        @click="$emit('select', suggestion)"
      >
        <div class="flex-shrink-0 mt-0.5">
          <Lightbulb class="w-5 h-5 text-[var(--icon-tertiary)]" />
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm text-[var(--text-secondary)] leading-relaxed">
            {{ suggestion }}
          </p>
        </div>
        <div class="flex-shrink-0">
          <ArrowRight class="w-5 h-5 text-[var(--icon-tertiary)] group-hover:text-[var(--icon-secondary)]" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Lightbulb, ArrowRight } from 'lucide-vue-next';

defineProps<{
  suggestions: string[];
}>();

defineEmits<{
  (e: 'select', suggestion: string): void;
}>();
</script>

<style scoped>
/* Additional styling if needed */
</style>
