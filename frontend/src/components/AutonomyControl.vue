<script setup lang="ts">
import { ref, computed } from 'vue';
import { Sparkles, Zap, Brain } from 'lucide-vue-next';
import type { ThinkingMode } from '@/api/agent';
import { onClickOutside } from '@vueuse/core';

const props = defineProps<{
  modelValue: ThinkingMode;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: ThinkingMode): void;
}>();

const isOpen = ref(false);
const containerRef = ref<HTMLElement>();

onClickOutside(containerRef, () => {
  isOpen.value = false;
});

const modes: { value: ThinkingMode; label: string; icon: typeof Sparkles; description: string }[] = [
  { value: 'fast', label: 'Quick', icon: Zap, description: 'Speed-optimized, less digging' },
  { value: 'auto', label: 'Auto', icon: Sparkles, description: 'Smart routing (default)' },
  { value: 'deep_think', label: 'Thorough', icon: Brain, description: 'Maximum reasoning' },
];

const isAuto = computed(() => props.modelValue === 'auto');
const currentMode = computed(() => modes.find(m => m.value === props.modelValue) ?? modes[1]);

const select = (value: ThinkingMode) => {
  emit('update:modelValue', value);
  isOpen.value = false;
};
</script>

<template>
  <div ref="containerRef" class="autonomy-control">
    <button
      type="button"
      class="autonomy-trigger"
      :class="{ 'is-auto': isAuto, 'is-custom': !isAuto }"
      :title="currentMode.description"
      @click="isOpen = !isOpen"
    >
      <component :is="currentMode.icon" :size="13" class="autonomy-icon" />
      <span v-if="!isAuto" class="autonomy-label">{{ currentMode.label }}</span>
    </button>

    <Transition name="dropdown">
      <div v-if="isOpen" class="autonomy-dropdown">
        <button
          v-for="mode in modes"
          :key="mode.value"
          type="button"
          class="autonomy-option"
          :class="{ active: modelValue === mode.value }"
          @click="select(mode.value)"
        >
          <component :is="mode.icon" :size="12" class="autonomy-option-icon" />
          <span class="autonomy-option-label">{{ mode.label }}</span>
          <span class="autonomy-option-desc">{{ mode.description }}</span>
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.autonomy-control {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.autonomy-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  border-radius: 15px;
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  line-height: 1;
}

.autonomy-trigger.is-auto {
  padding: 0 7px;
  color: var(--text-tertiary);
}

.autonomy-trigger.is-auto:hover {
  background: var(--fill-tsp-white-main);
  border-color: var(--border-main);
  color: var(--text-secondary);
}

.autonomy-trigger.is-custom {
  padding: 0 10px;
  background: var(--fill-tsp-white-dark);
  border-color: var(--border-dark);
  color: var(--text-primary);
}

.autonomy-trigger.is-custom:hover {
  background: var(--fill-tsp-white-main);
}

.autonomy-icon {
  flex-shrink: 0;
}

.autonomy-label {
  line-height: 1;
}

/* Dropdown */
.autonomy-dropdown {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  background: var(--background-menu-white);
  border: 1px solid var(--border-main);
  border-radius: 12px;
  box-shadow: 0 8px 24px var(--shadow-S);
  padding: 4px;
  min-width: 200px;
  z-index: 100;
}

.autonomy-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border-radius: 8px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.1s ease;
  color: var(--text-primary);
}

.autonomy-option:hover {
  background: var(--fill-tsp-white-main);
}

.autonomy-option.active {
  background: var(--fill-tsp-white-dark);
}

.autonomy-option-icon {
  flex-shrink: 0;
  color: var(--text-secondary);
}

.autonomy-option-label {
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
  color: var(--text-primary);
}

.autonomy-option-desc {
  font-size: 11px;
  color: var(--text-tertiary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Transition */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
  transform-origin: bottom left;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: scaleY(0.85) translateY(4px);
}
</style>
