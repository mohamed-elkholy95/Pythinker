<template>
  <div class="w-full h-full relative" :class="showPlaceholder ? 'flex items-center justify-center' : ''">
    <!-- Text-only operation placeholder -->
    <div v-if="showPlaceholder" class="w-full h-full flex flex-col items-center justify-center bg-gradient-to-b from-[var(--background-gray-main)] to-[var(--fill-white)] dark:from-[#1a1a2e] dark:to-[#16213e]">
      <div class="fetching-container">
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
      <div class="mt-6 flex flex-col items-center gap-2">
        <div class="flex items-center gap-2 text-[var(--text-secondary)]">
          <span class="text-base font-medium">{{ placeholderLabel }}</span>
          <span v-if="isActive" class="flex gap-1">
            <span v-for="(_, i) in 3" :key="i" class="dot" :style="{ animationDelay: `${i * 200}ms` }"></span>
          </span>
        </div>
        <div v-if="placeholderDetail" class="max-w-[280px] text-center text-xs text-[var(--text-tertiary)] truncate px-4">
          {{ placeholderDetail }}
        </div>
      </div>
    </div>

    <!-- Live VNC -->
    <VNCViewer
      v-else-if="enabled"
      :session-id="sessionId"
      :enabled="enabled"
      :view-only="viewOnly"
      @connected="emit('connected')"
      @disconnected="emit('disconnected')"
      class="absolute inset-0"
    />

    <!-- Static screenshot -->
    <img v-else-if="screenshot" :src="screenshot" alt="Screenshot" class="w-full h-full object-contain" />

    <!-- Take over button -->
    <slot name="takeover"></slot>
  </div>
</template>

<script setup lang="ts">
import VNCViewer from '@/components/VNCViewer.vue';

const props = defineProps<{
  sessionId: string;
  enabled: boolean;
  viewOnly?: boolean;
  showPlaceholder?: boolean;
  placeholderLabel?: string;
  placeholderDetail?: string;
  isActive?: boolean;
  screenshot?: string;
}>();

const emit = defineEmits<{
  connected: [];
  disconnected: [];
}>();
</script>

<style scoped>
/* Fetching animation styles */
.fetching-container {
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
  background: linear-gradient(135deg, var(--text-brand), #60a5fa);
  filter: blur(1px);
  opacity: 0.8;
}

.orb-1 { width: 10px; height: 10px; top: 10%; left: 50%; transform: translateX(-50%); animation: pulse-orb 2s ease-in-out infinite; }
.orb-2 { width: 8px; height: 8px; bottom: 20%; left: 15%; animation: pulse-orb 2s ease-in-out infinite 0.5s; }
.orb-3 { width: 6px; height: 6px; bottom: 25%; right: 15%; animation: pulse-orb 2s ease-in-out infinite 1s; }

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
  background: radial-gradient(circle, rgba(59, 130, 246, 0.15) 0%, transparent 70%);
  animation: pulse-glow 2s ease-in-out infinite;
}

.globe-icon {
  width: 48px;
  height: 48px;
  color: var(--text-brand);
  animation: morph-globe 3s ease-in-out infinite;
}

.dot {
  display: inline-block;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: var(--text-tertiary);
  animation: bounce-dot 1.4s ease-in-out infinite;
}

@keyframes rotate-slow { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
@keyframes pulse-orb { 0%, 100% { transform: scale(1); opacity: 0.8; } 50% { transform: scale(1.3); opacity: 1; } }
@keyframes pulse-glow { 0%, 100% { transform: scale(1); opacity: 0.5; } 50% { transform: scale(1.15); opacity: 0.8; } }
@keyframes morph-globe { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
@keyframes bounce-dot { 0%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }
</style>
