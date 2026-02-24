<script setup lang="ts">
import { ref, computed } from 'vue';
import { AlignLeft, AlignJustify, GraduationCap } from 'lucide-vue-next';
import { onClickOutside } from '@vueuse/core';

export type DetailLevel = 'brief' | 'detailed' | 'expert';

const props = defineProps<{
  modelValue: DetailLevel;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: DetailLevel): void;
}>();

const isOpen = ref(false);
const containerRef = ref<HTMLElement>();

onClickOutside(containerRef, () => {
  isOpen.value = false;
});

const modes: { value: DetailLevel; label: string; icon: typeof AlignLeft; description: string }[] = [
  { value: 'brief', label: 'Brief', icon: AlignLeft as any, description: 'Short overview, less technical' },
  { value: 'detailed', label: 'Detailed', icon: AlignJustify as any, description: 'In-depth explanation (default)' },
  { value: 'expert', label: 'Expert', icon: GraduationCap as any, description: 'Highly technical & exhaustive' },
];

const isDetailed = computed(() => props.modelValue === 'detailed');
const currentMode = computed(() => modes.find(m => m.value === props.modelValue) ?? modes[1]);

const select = (value: DetailLevel) => {
  emit('update:modelValue', value);
  isOpen.value = false;
};
</script>

<template>
  <div ref="containerRef" class="expertise-control">
    <button
      type="button"
      class="expertise-trigger"
      :class="{ 'is-detailed': isDetailed, 'is-custom': !isDetailed }"
      :title="currentMode.description"
      @click="isOpen = !isOpen"
    >
      <component :is="currentMode.icon" :size="13" class="expertise-icon" />
      <span v-if="!isDetailed" class="expertise-label">{{ currentMode.label }}</span>
    </button>

    <Transition name="dropdown">
      <div v-if="isOpen" class="expertise-dropdown">
        <button
          v-for="mode in modes"
          :key="mode.value"
          type="button"
          class="expertise-option"
          :class="{ active: modelValue === mode.value }"
          @click="select(mode.value)"
        >
          <component :is="mode.icon" :size="14" class="expertise-option-icon mt-[2px]" />
          <div class="flex flex-col gap-[2px] text-left">
            <span class="expertise-option-label">{{ mode.label }}</span>
            <span class="expertise-option-desc">{{ mode.description }}</span>
          </div>
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.expertise-control {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.expertise-trigger {
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

.expertise-trigger.is-detailed {
  padding: 0 7px;
  color: var(--text-tertiary);
}

.expertise-trigger.is-detailed:hover {
  background: var(--fill-tsp-white-main);
  border-color: var(--border-main);
  color: var(--text-secondary);
}

.expertise-trigger.is-custom {
  padding: 0 10px;
  background: var(--fill-tsp-white-dark);
  border-color: var(--border-dark);
  color: var(--text-primary);
}

.expertise-trigger.is-custom:hover {
  background: var(--fill-tsp-white-main);
}

.expertise-icon {
  flex-shrink: 0;
}

.expertise-label {
  line-height: 1;
}

.expertise-dropdown {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  background: var(--background-menu-white);
  border: 1px solid var(--border-main);
  border-radius: 12px;
  box-shadow: 0 8px 24px var(--shadow-S);
  padding: 6px;
  min-width: 240px;
  z-index: 100;
}

.expertise-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.1s ease;
  color: var(--text-primary);
}

.expertise-option:hover {
  background: var(--fill-tsp-white-main);
}

.expertise-option.active {
  background: var(--fill-tsp-white-dark);
}

.expertise-option-icon {
  flex-shrink: 0;
  color: var(--text-secondary);
}

.expertise-option-label {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.2;
}

.expertise-option-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: normal;
  line-height: 1.35;
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
