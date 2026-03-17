<template>
  <div class="search-animation">
    <div class="search-rings">
      <div class="ring ring-1"></div>
      <div class="ring ring-2"></div>
      <div class="ring ring-3"></div>
    </div>
    <svg class="search-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="2"/>
      <path d="M16 16l4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    </svg>
  </div>
</template>

<script setup lang="ts">
// Search animation for search operations
</script>

<style scoped>
.search-animation {
  position: relative;
  width: 100px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.search-rings {
  position: absolute;
  width: 100%;
  height: 100%;
}

.ring {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  border: 2px solid var(--text-brand);
  opacity: 0;
  animation: pulse-ring 2s ease-out infinite;
}

.ring-1 {
  width: 40px;
  height: 40px;
  animation-delay: 0s;
}

.ring-2 {
  width: 60px;
  height: 60px;
  animation-delay: 0.4s;
}

.ring-3 {
  width: 80px;
  height: 80px;
  animation-delay: 0.8s;
}

.search-icon {
  width: 32px;
  height: 32px;
  color: var(--text-brand);
  animation: search-bounce 1.5s ease-in-out infinite;
}

@keyframes pulse-ring {
  0% {
    transform: translate(-50%, -50%) scale(0.8);
    opacity: 0.6;
  }
  100% {
    transform: translate(-50%, -50%) scale(1.5);
    opacity: 0;
  }
}

@keyframes search-bounce {
  0%, 100% {
    transform: translateY(0) scale(1);
  }
  50% {
    transform: translateY(-4px) scale(1.05);
  }
}

/* Dark mode: boost ring visibility */
:global(.dark) .ring {
  border-color: color-mix(in srgb, var(--text-brand) 80%, white 20%);
}

/* Accessibility: Reduce motion */
@media (prefers-reduced-motion: reduce) {
  .ring,
  .search-icon {
    animation: none;
  }
}
</style>
