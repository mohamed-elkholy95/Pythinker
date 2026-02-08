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
      <div class="suggestion-icon-wrap">
        <component
          :is="getSuggestionIcon(index)"
          class="suggestion-icon"
        />
      </div>
      <span class="suggestion-text">{{ suggestion }}</span>
      <ArrowRight class="suggestion-arrow" :size="16" />
    </div>
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
  padding: 0 4px;
}

.suggestions-divider {
  height: 1px;
  background: var(--border-light);
  margin: 0 8px;
}

.suggestions-header {
  padding: 14px 12px 6px;
}

.suggestions-header span {
  font-size: 13px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  border-radius: 10px;
  transition: background 0.15s ease;
}

.suggestion-item:hover {
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.04));
}

.suggestion-icon-wrap {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.04));
  border: 1px solid var(--border-light);
}

.suggestion-icon {
  width: 14px;
  height: 14px;
  color: var(--icon-tertiary);
}

.suggestion-text {
  flex: 1;
  font-size: 14px;
  line-height: 1.45;
  color: var(--text-primary);
  font-weight: 400;
}

.suggestion-arrow {
  flex-shrink: 0;
  color: var(--icon-tertiary);
  opacity: 0.5;
  transition: opacity 0.15s ease;
}

.suggestion-item:hover .suggestion-arrow {
  opacity: 1;
}
</style>
