<template>
  <div
    class="loading-indicator flex items-center gap-2 text-[var(--text-tertiary)] text-sm"
    :class="{ 'heartbeat-active': pulse }"
    role="status"
    aria-live="polite"
  >
    <span class="loading-dots flex gap-1 relative top-[2px]" aria-hidden="true">
      <span
        v-for="(_, index) in 3"
        :key="index"
        class="w-1.5 h-1.5 rounded-full animate-bounce-dot bg-[var(--icon-tertiary)]"
        :style="{ 'animation-delay': `${index * 150}ms` }"
      ></span>
    </span>
    <span v-if="text" class="loading-text">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
interface Props {
  text?: string
  pulse?: boolean
}

withDefaults(defineProps<Props>(), {
  text: undefined,
  pulse: false,
})
</script>

<style scoped>
.loading-indicator {
  will-change: contents;
}

.loading-dots {
  will-change: transform;
}

.animate-bounce-dot {
  display: inline-block;
  animation: dot-animation 1.2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

/* Subtle glow effect when heartbeat is active — proves backend is alive */
.heartbeat-active .animate-bounce-dot {
  animation: dot-animation-heartbeat 1.2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

.loading-text {
  opacity: 0;
  animation: fade-in-text 0.4s ease-out 0.2s forwards;
}

@keyframes dot-animation {
  0%, 60%, 100% {
    transform: translateY(0) scale(1);
    opacity: 0.7;
  }
  30% {
    transform: translateY(-3px) scale(1.1);
    opacity: 1;
  }
}

@keyframes dot-animation-heartbeat {
  0%, 60%, 100% {
    transform: translateY(0) scale(1);
    opacity: 0.8;
  }
  30% {
    transform: translateY(-3px) scale(1.15);
    opacity: 1;
  }
}

@keyframes fade-in-text {
  to {
    opacity: 1;
  }
}
</style>
