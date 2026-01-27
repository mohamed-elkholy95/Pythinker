<template>
  <div class="file-animation">
    <svg class="file-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="file-body"
      />
      <path
        d="M14 2v6h6"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="file-fold"
      />
      <path
        d="M12 11v6M9 14l3 3 3-3"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="file-arrow"
      />
    </svg>
  </div>
</template>

<script setup lang="ts">
// File animation for file operations
</script>

<style scoped>
.file-animation {
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.file-icon {
  width: 48px;
  height: 48px;
  color: var(--text-brand);
  animation: file-pulse 2s ease-in-out infinite;
}

.file-arrow {
  animation: arrow-bounce 1.5s ease-in-out infinite;
  transform-origin: center;
}

@keyframes file-pulse {
  0%, 100% {
    opacity: 0.7;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.05);
  }
}

@keyframes arrow-bounce {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(3px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .file-icon,
  .file-arrow {
    animation: none;
  }
}
</style>
