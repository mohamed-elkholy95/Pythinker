<template>
  <div v-if="suggestions.length > 0" class="suggestions-container">
    <div
      v-for="(suggestion, index) in suggestions"
      :key="index"
      class="suggestion-item suggestion-silver-shimmer"
      @click="$emit('select', suggestion)"
    >
      <div class="suggestion-icon-wrap">
        <component
          :is="getSuggestionIcon(index)"
          class="suggestion-icon"
        />
      </div>
      <span class="suggestion-text">{{ suggestion }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Search, Compass } from 'lucide-vue-next';

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
  gap: 10px;
  width: 100%;
  padding: 4px 0;
}

.suggestion-item {
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 56px;
  padding: 10px 16px;
  cursor: pointer;
  border-radius: 9999px;
  border: 1px solid #d4d9e1;
  background: linear-gradient(180deg, #f3f5f7 0%, #eceff3 100%);
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.suggestion-silver-shimmer::before {
  content: '';
  position: absolute;
  inset: 0;
  left: -120%;
  width: 120%;
  background: linear-gradient(
    110deg,
    rgba(255, 255, 255, 0) 0%,
    rgba(255, 255, 255, 0.45) 48%,
    rgba(255, 255, 255, 0) 100%
  );
  animation: suggestion-shimmer 2.7s ease-in-out infinite;
  pointer-events: none;
}

.suggestion-item:hover {
  border-color: #bfc6d1;
  transform: translateY(-1px);
}

.suggestion-icon-wrap {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  background: #f6f8fb;
  border: 1px solid #c9d0dc;
}

.suggestion-icon {
  width: 18px;
  height: 18px;
  color: #6a7381;
}

.suggestion-text {
  flex: 1;
  min-width: 0;
  font-size: 16px;
  line-height: 1.35;
  color: #4e545e;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@keyframes suggestion-shimmer {
  0% {
    left: -120%;
  }
  100% {
    left: 110%;
  }
}
</style>
