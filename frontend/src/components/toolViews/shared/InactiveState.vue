<template>
  <div class="inactive-state">
    <!-- Computer monitor illustration -->
    <div class="monitor">
      <div class="monitor-screen">
        <div class="sleep-icon-container">
          <svg
            class="sleep-icon"
            width="40"
            height="40"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <!-- Moon shape -->
            <path
              d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"
              fill="currentColor"
              opacity="0.6"
            />
            <!-- Z letter for sleep -->
            <text
              x="16"
              y="10"
              font-size="7"
              font-weight="600"
              fill="currentColor"
              opacity="0.8"
            >z</text>
          </svg>
        </div>
      </div>
      <!-- Monitor stand -->
      <div class="monitor-neck"></div>
      <div class="monitor-base"></div>
    </div>

    <!-- Inactive message -->
    <div class="inactive-message">
      {{ message }}
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  message?: string;
}>(), {
  message: "Pythinker's computer is inactive"
});
</script>

<style scoped>
.inactive-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    to bottom,
    var(--background-gray-main),
    var(--fill-white)
  );
  padding: var(--space-8);
}

:global(.dark) .inactive-state {
  background: linear-gradient(to bottom, #0d1117, #161b22);
}

.monitor {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.monitor-screen {
  width: 180px;
  height: 120px;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.9) 0%,
    rgba(245, 245, 245, 0.95) 100%
  );
  border-radius: 12px;
  border: 3px solid rgba(200, 200, 200, 0.6);
  box-shadow:
    inset 0 2px 4px rgba(255, 255, 255, 0.8),
    0 4px 12px rgba(0, 0, 0, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

:global(.dark) .monitor-screen {
  background: linear-gradient(
    135deg,
    rgba(40, 40, 50, 0.9) 0%,
    rgba(30, 30, 40, 0.95) 100%
  );
  border-color: rgba(80, 80, 90, 0.6);
  box-shadow:
    inset 0 2px 4px rgba(255, 255, 255, 0.05),
    0 4px 12px rgba(0, 0, 0, 0.3);
}

/* Subtle screen texture */
.monitor-screen::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0, 0, 0, 0.01) 2px,
    rgba(0, 0, 0, 0.01) 4px
  );
  pointer-events: none;
}

.sleep-icon-container {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border: 2px dashed rgba(180, 180, 180, 0.5);
  border-radius: 50%;
  animation: pulse-border 3s ease-in-out infinite;
}

:global(.dark) .sleep-icon-container {
  border-color: rgba(100, 100, 110, 0.5);
}

@keyframes pulse-border {
  0%, 100% {
    border-color: rgba(180, 180, 180, 0.3);
  }
  50% {
    border-color: rgba(180, 180, 180, 0.6);
  }
}

:global(.dark) @keyframes pulse-border {
  0%, 100% {
    border-color: rgba(100, 100, 110, 0.3);
  }
  50% {
    border-color: rgba(100, 100, 110, 0.6);
  }
}

.sleep-icon {
  color: rgba(160, 160, 165, 0.8);
  animation: float 4s ease-in-out infinite;
}

:global(.dark) .sleep-icon {
  color: rgba(120, 120, 130, 0.8);
}

@keyframes float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-3px);
  }
}

.monitor-neck {
  width: 24px;
  height: 16px;
  background: linear-gradient(
    to bottom,
    rgba(200, 200, 200, 0.7),
    rgba(180, 180, 180, 0.7)
  );
  border-radius: 0 0 4px 4px;
}

:global(.dark) .monitor-neck {
  background: linear-gradient(
    to bottom,
    rgba(60, 60, 70, 0.7),
    rgba(50, 50, 60, 0.7)
  );
}

.monitor-base {
  width: 60px;
  height: 8px;
  background: linear-gradient(
    to bottom,
    rgba(190, 190, 190, 0.8),
    rgba(170, 170, 170, 0.8)
  );
  border-radius: 0 0 6px 6px;
  margin-top: -2px;
}

:global(.dark) .monitor-base {
  background: linear-gradient(
    to bottom,
    rgba(55, 55, 65, 0.8),
    rgba(45, 45, 55, 0.8)
  );
}

.inactive-message {
  margin-top: var(--space-6);
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  color: var(--text-tertiary);
  text-align: center;
}

/* Accessibility */
@media (prefers-reduced-motion: reduce) {
  .sleep-icon-container {
    animation: none;
  }
  .sleep-icon {
    animation: none;
  }
}
</style>
