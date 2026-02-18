<script setup lang="ts">
import { Sparkles, Zap, Brain } from 'lucide-vue-next';
import type { ThinkingMode } from '@/api/agent';

defineProps<{
  modelValue: ThinkingMode;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: ThinkingMode): void;
}>();

const modes: { value: ThinkingMode; label: string; icon: typeof Sparkles; title: string }[] = [
  { value: 'auto', label: 'Auto', icon: Sparkles, title: 'Auto — complexity-based model routing' },
  { value: 'fast', label: 'Fast', icon: Zap, title: 'Fast — speed-optimized model' },
  { value: 'deep_think', label: 'Think', icon: Brain, title: 'DeepThink — maximum reasoning' },
];
</script>

<template>
  <div class="thinking-mode-selector" role="group" aria-label="Thinking mode">
    <button
      v-for="mode in modes"
      :key="mode.value"
      class="thinking-mode-option"
      :class="{ active: modelValue === mode.value }"
      :title="mode.title"
      type="button"
      @click="emit('update:modelValue', mode.value)"
    >
      <component :is="mode.icon" :size="11" class="thinking-mode-icon" />
      <span class="thinking-mode-label">{{ mode.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.thinking-mode-selector {
  display: inline-flex;
  align-items: center;
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  border-radius: 17px;
  padding: 2px;
  gap: 1px;
  height: 30px;
  flex-shrink: 0;
}

:global([data-theme='dark']) .thinking-mode-selector {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-main);
}

.thinking-mode-option {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  border-radius: 14px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  height: 24px;
  white-space: nowrap;
  line-height: 1;
}

.thinking-mode-option:hover:not(.active) {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.thinking-mode-option.active {
  background: #000;
  color: #fff;
}

:global([data-theme='dark']) .thinking-mode-option.active {
  background: var(--text-primary);
  color: var(--background-white-main);
}

.thinking-mode-icon {
  flex-shrink: 0;
}

.thinking-mode-label {
  line-height: 1;
}
</style>
