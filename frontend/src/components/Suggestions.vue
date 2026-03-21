<template>
  <div v-if="suggestions.length > 0" class="suggestions-container" role="group" aria-label="Suggested follow-ups">
    <div class="suggestions-title">
      {{ $t('Suggested follow-ups') }}
    </div>
    <div
      v-for="(suggestion, index) in suggestions"
      :key="index"
      class="suggestion-item"
      role="button"
      tabindex="0"
      :aria-label="suggestion"
      @click="$emit('select', suggestion)"
      @keydown.enter="$emit('select', suggestion)"
      @keydown.space.prevent="$emit('select', suggestion)"
    >
      <div class="suggestion-content">
        <component
          :is="getSuggestionIcon(index)"
          class="suggestion-icon"
        />
        <span class="suggestion-text">{{ suggestion }}</span>
      </div>
      <ArrowRight class="suggestion-arrow" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Search, Compass, ArrowRight } from 'lucide-vue-next';

defineProps<{
  suggestions: string[];
}>();

defineEmits<{
  (e: 'select', suggestion: string): void;
}>();

const getSuggestionIcon = (index: number) => {
  const icons = [Search, Compass];
  return icons[index % icons.length];
};
</script>

<style scoped>
.suggestions-container {
  display: flex;
  flex-direction: column;
  gap: 0;
  width: 100%;
  padding: 4px 12px;
  animation: suggestions-fade-in 0.3s ease-out;
}

/* Fade-in animation when suggestions appear */
@keyframes suggestions-fade-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.suggestions-title {
  font-size: 13px;
  line-height: 18px;
  font-weight: 500;
  color: var(--text-tertiary);
  margin-bottom: 6px;
}

.suggestion-item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 46px;
  width: calc(100% + 24px);
  margin: 0 -12px;
  padding: 9px 12px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.16s ease;
}

.suggestion-item:hover {
  background: var(--fill-tsp-white-main);
  border-radius: 10px;
}

.suggestion-item::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 0;
  height: 1px;
  background: var(--border-main);
}

.suggestion-item:last-child::after {
  display: none;
}

.suggestion-item:hover::after {
  display: none;
}

.suggestion-content {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.suggestion-icon {
  width: 16px;
  height: 16px;
  color: var(--icon-tertiary);
  flex-shrink: 0;
}

.suggestion-text {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  line-height: 20px;
  color: var(--text-secondary);
  font-weight: 400;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.suggestion-arrow {
  width: 16px;
  height: 16px;
  color: var(--icon-tertiary);
  flex-shrink: 0;
}
</style>
