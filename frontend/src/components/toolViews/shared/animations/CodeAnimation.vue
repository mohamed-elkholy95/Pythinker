<template>
  <div class="code-animation">
    <svg class="code-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M16 18l6-6-6-6M8 6l-6 6 6 6"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="code-brackets"
      />
    </svg>
    <div class="code-particles">
      <div class="particle particle-1"></div>
      <div class="particle particle-2"></div>
      <div class="particle particle-3"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Code execution animation
</script>

<style scoped>
.code-animation {
  position: relative;
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.code-icon {
  width: 48px;
  height: 48px;
  color: var(--text-brand);
  animation: code-pulse 2s ease-in-out infinite;
}

.code-brackets {
  animation: brackets-expand 1.5s ease-in-out infinite;
}

.code-particles {
  position: absolute;
  width: 100%;
  height: 100%;
}

.particle {
  position: absolute;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--text-brand);
  opacity: 0;
  animation: particle-float 2s ease-in-out infinite;
}

.particle-1 {
  top: 30%;
  left: 20%;
  animation-delay: 0s;
}

.particle-2 {
  top: 50%;
  right: 20%;
  animation-delay: 0.4s;
}

.particle-3 {
  bottom: 30%;
  left: 30%;
  animation-delay: 0.8s;
}

@keyframes code-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.8;
  }
  50% {
    transform: scale(1.05);
    opacity: 1;
  }
}

@keyframes brackets-expand {
  0%, 100% {
    transform: scaleX(1);
  }
  50% {
    transform: scaleX(1.1);
  }
}

@keyframes particle-float {
  0%, 100% {
    transform: translateY(0);
    opacity: 0;
  }
  50% {
    transform: translateY(-10px);
    opacity: 1;
  }
}

/* Dark mode: boost visibility */
:global(.dark) .code-icon {
  opacity: 0.9;
}

:global(.dark) .particle {
  background: color-mix(in srgb, var(--text-brand) 80%, white 20%);
}

@media (prefers-reduced-motion: reduce) {
  .code-icon,
  .code-brackets,
  .particle {
    animation: none;
  }
}
</style>
