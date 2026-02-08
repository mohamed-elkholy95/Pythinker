<template>
  <div v-if="suggestions.length > 0" class="suggestions-container">
    <!-- Top divider -->
    <div class="suggestions-divider"></div>

    <!-- Header -->
    <div class="suggestions-header">
      <span>Suggested follow-ups</span>
    </div>

    <!-- Suggestion Items -->
    <div
      v-for="(suggestion, index) in suggestions"
      :key="index"
      class="suggestion-item"
      @click="$emit('select', suggestion)"
    >
      <component
        :is="getSuggestionIcon(index)"
        class="suggestion-icon"
      />
      <span class="suggestion-text">{{ suggestion }}</span>
      <ArrowRight class="suggestion-arrow" :size="18" />
    </div>

    <!-- Bottom divider -->
    <div class="suggestions-divider"></div>
  </div>
</template>

<script setup lang="ts">
import { MessageSquare, FileText, Globe, ArrowRight } from 'lucide-vue-next';

defineProps<{
  suggestions: string[];
}>();

defineEmits<{
  (e: 'select', suggestion: string): void;
}>();

const getSuggestionIcon = (index: number) => {
  const icons = [MessageSquare, FileText, Globe];
  return icons[index % icons.length];
};
</script>

<style scoped>
.suggestions-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 0 8px;
}

.suggestions-divider {
  height: 1px;
  background: var(--border-light);
}

.suggestions-header {
  padding: 16px 8px 6px;
}

.suggestions-header span {
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 8px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-light);
  transition: opacity 0.15s ease;
}

.suggestion-item:hover {
  opacity: 0.7;
}

.suggestion-icon {
  width: 20px;
  height: 20px;
  color: var(--icon-tertiary);
  flex-shrink: 0;
}

.suggestion-text {
  flex: 1;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-primary);
  font-weight: 400;
}

.suggestion-arrow {
  flex-shrink: 0;
  color: var(--icon-tertiary);
}
</style>
