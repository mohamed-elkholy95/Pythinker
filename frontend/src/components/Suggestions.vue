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
  const icons = [Globe, MessageSquare, FileText];
  return icons[index % icons.length];
};
</script>

<style scoped>
.suggestions-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 0 2px;
}

.suggestions-divider {
  height: 1px;
  background: var(--border-light);
  margin: 0 10px;
}

.suggestions-header {
  padding: 14px 12px 8px;
}

.suggestions-header span {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 12px 12px;
  cursor: pointer;
  border-radius: 12px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
  transition: all 0.15s ease;
  margin-bottom: 8px;
}

.suggestion-item:hover {
  background: #f6f7f9;
  border-color: var(--border-dark);
  transform: translateY(-1px);
}

.suggestion-icon-wrap {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  background: #eef1f5;
  border: 1px solid #dde3eb;
}

.suggestion-icon {
  width: 15px;
  height: 15px;
  color: #606a78;
}

.suggestion-text {
  flex: 1;
  font-size: 14px;
  line-height: 1.45;
  color: #2f333b;
  font-weight: 500;
}

.suggestion-arrow {
  flex-shrink: 0;
  color: #9099a8;
  opacity: 0.7;
  transition: all 0.15s ease;
}

.suggestion-item:hover .suggestion-arrow {
  opacity: 1;
  color: #697386;
  transform: translateX(1px);
}
</style>
