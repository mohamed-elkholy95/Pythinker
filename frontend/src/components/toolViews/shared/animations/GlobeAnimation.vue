<template>
  <div class="globe-animation">
    <div class="orbs-container">
      <div class="orb orb-1"></div>
      <div class="orb orb-2"></div>
      <div class="orb orb-3"></div>
    </div>
    <div class="globe-wrapper">
      <svg class="globe-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.3"/>
        <ellipse cx="12" cy="12" rx="4" ry="10" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.5"/>
        <path d="M2 12h20" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.4"/>
        <path d="M12 2v20" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.4"/>
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
// Globe animation for browser/network operations
</script>

<style scoped>
.globe-animation {
  position: relative;
  width: 120px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.orbs-container {
  position: absolute;
  width: 100%;
  height: 100%;
  animation: rotate-slow 8s linear infinite;
}

.orb {
  position: absolute;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--text-brand), #b69eff);
  filter: blur(1px);
  opacity: 0.8;
}

.orb-1 {
  width: 10px;
  height: 10px;
  top: 10%;
  left: 50%;
  transform: translateX(-50%);
  animation: pulse-orb 2s ease-in-out infinite;
}

.orb-2 {
  width: 8px;
  height: 8px;
  bottom: 20%;
  left: 15%;
  animation: pulse-orb 2s ease-in-out infinite 0.5s;
}

.orb-3 {
  width: 6px;
  height: 6px;
  bottom: 25%;
  right: 15%;
  animation: pulse-orb 2s ease-in-out infinite 1s;
}

.globe-wrapper {
  position: relative;
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.globe-wrapper::before {
  content: '';
  position: absolute;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(156, 125, 255, 0.18) 0%, transparent 70%);
  animation: pulse-glow 2s ease-in-out infinite;
}

.globe-icon {
  width: 48px;
  height: 48px;
  color: var(--text-brand);
  animation: morph-globe 3s ease-in-out infinite;
}

@keyframes rotate-slow {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes pulse-orb {
  0%, 100% {
    transform: scale(1);
    opacity: 0.8;
  }
  50% {
    transform: scale(1.3);
    opacity: 1;
  }
}

@keyframes pulse-glow {
  0%, 100% {
    transform: scale(1);
    opacity: 0.5;
  }
  50% {
    transform: scale(1.15);
    opacity: 0.8;
  }
}

@keyframes morph-globe {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.05);
  }
}

/* Accessibility: Reduce motion */
@media (prefers-reduced-motion: reduce) {
  .orbs-container,
  .orb,
  .globe-wrapper::before,
  .globe-icon {
    animation: none;
  }
}
</style>
