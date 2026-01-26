<template>
  <div
    class="h-[36px] flex items-center px-3 w-full bg-[var(--background-gray-main)] border-b border-[var(--border-main)] rounded-t-[12px] shadow-[inset_0px_1px_0px_0px_#FFFFFF] dark:shadow-[inset_0px_1px_0px_0px_#FFFFFF30]">
    <div class="flex-1 flex items-center justify-center">
      <div class="max-w-[250px] truncate text-[var(--text-tertiary)] text-sm font-medium text-center">
        {{ toolContent?.args?.url || 'Browser' }}
      </div>
    </div>
  </div>
  <div class="flex-1 min-h-0 w-full overflow-y-auto">
    <div class="px-0 py-0 flex flex-col relative h-full">
      <div class="w-full h-full object-cover flex items-center justify-center bg-[var(--fill-white)] relative">
        <!-- Working/Text-only overlay -->
        <div v-if="showPlaceholder" class="w-full h-full flex flex-col items-center justify-center bg-gradient-to-b from-[var(--background-gray-main)] to-[var(--fill-white)] dark:from-[#1a1a2e] dark:to-[#16213e]">
          <div class="fetching-container">
            <!-- Animated orbs -->
            <div class="orbs-container">
              <div class="orb orb-1"></div>
              <div class="orb orb-2"></div>
              <div class="orb orb-3"></div>
            </div>
            <!-- Globe icon with pulse -->
            <div class="globe-wrapper">
              <svg class="globe-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.3"/>
                <ellipse cx="12" cy="12" rx="4" ry="10" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.5"/>
                <path d="M2 12h20" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.4"/>
                <path d="M12 2v20" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.4"/>
                <path d="M3.5 7h17M3.5 17h17" stroke="currentColor" stroke-width="1" stroke-opacity="0.3"/>
              </svg>
            </div>
          </div>
          <!-- Status text -->
          <div class="mt-6 flex flex-col items-center gap-2">
            <div class="flex items-center gap-2 text-[var(--text-secondary)]">
              <span class="text-base font-medium">{{ actionLabel }}</span>
              <span v-if="showWorkingDots" class="flex gap-1">
                <span v-for="(_, i) in 3" :key="i" class="dot" :style="{ animationDelay: `${i * 200}ms` }"></span>
              </span>
            </div>
            <div class="max-w-[280px] text-center text-xs text-[var(--text-tertiary)] truncate px-4">
              {{ fetchingUrl }}
            </div>
          </div>
        </div>
        <!-- Normal VNC/Screenshot view -->
        <div v-else class="w-full h-full">
          <VNCViewer
            v-if="showLiveVnc"
            :session-id="props.sessionId"
            :enabled="props.live"
            :view-only="true"
            @connected="onVNCConnected"
            @disconnected="onVNCDisconnected"
            @credentials-required="onVNCCredentialsRequired"
          />
          <img v-else-if="showScreenshot" alt="Image Preview" class="cursor-pointer w-full" referrerpolicy="no-referrer" :src="imageUrl">
        </div>
        <button
          v-if="!isShare && !isWorking"
          @click="takeOver"
          class="absolute right-[10px] bottom-[10px] z-10 min-w-10 h-10 flex items-center justify-center rounded-full bg-[var(--background-white-main)] text-[var(--text-primary)] border border-[var(--border-main)] shadow-[0px_5px_16px_0px_var(--shadow-S),0px_0px_1.25px_0px_var(--shadow-S)] backdrop-blur-3xl cursor-pointer hover:bg-[var(--text-brand)] hover:px-4 hover:text-[var(--text-white)] group transition-width duration-300">
          <TakeOverIcon />
          <span
            class="text-sm max-w-0 overflow-hidden whitespace-nowrap opacity-0 transition-all duration-300 group-hover:max-w-[200px] group-hover:opacity-100 group-hover:ml-1 group-hover:text-[var(--text-white)]">{{ t('Take Over') }}</span></button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ToolContent } from '@/types/message';
import { ref, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import VNCViewer from '@/components/VNCViewer.vue';
import TakeOverIcon from '@/components/icons/TakeOverIcon.vue';

const props = defineProps<{
  sessionId: string;
  toolContent: ToolContent;
  live: boolean;
  isShare: boolean;
}>();

const { t } = useI18n();
const imageUrl = ref('');

const TEXT_ONLY_BROWSER_FUNCTIONS = new Set(['browser_get_content', 'browser_agent_extract']);

// Detect if we're actively working (any browser function is being called)
const isWorking = computed(() => {
  const func = props.toolContent?.function;
  const status = props.toolContent?.status;
  // Show working overlay when any browser function is running or calling
  return func?.startsWith('browser_') && (status === 'calling' || status === 'running');
});

const isTextOnlyOperation = computed(() => {
  const func = props.toolContent?.function;
  return !!func && TEXT_ONLY_BROWSER_FUNCTIONS.has(func);
});

const showPlaceholder = computed(() => isWorking.value || isTextOnlyOperation.value);
const showWorkingDots = computed(() => isWorking.value);
const showLiveVnc = computed(() => props.live && !isTextOnlyOperation.value);
const showScreenshot = computed(() => !props.live && !!imageUrl.value && !isTextOnlyOperation.value);

// Check if it's specifically a fetch operation (for display text)
const isFetchingContent = computed(() => {
  const func = props.toolContent?.function;
  return func === 'browser_get_content';
});

// Get action description for display
const actionDescription = computed(() => {
  const func = props.toolContent?.function;
  if (!func) return 'Working';

  const actionMap: Record<string, string> = {
    'browser_get_content': 'Fetching',
    'browser_navigate': 'Navigating',
    'browser_click': 'Clicking',
    'browser_input': 'Typing',
    'browser_view': 'Loading',
    'browser_scroll_up': 'Scrolling',
    'browser_scroll_down': 'Scrolling',
    'browser_press_key': 'Pressing key',
    'browser_select_option': 'Selecting',
    'browser_move_mouse': 'Moving cursor',
    'browser_restart': 'Restarting',
    'browser_agent_run': 'Running agent',
    'browser_agent_extract': 'Extracting',
  };

  return actionMap[func] || 'Working';
});

const actionLabel = computed(() => {
  if (isTextOnlyOperation.value && !isWorking.value) {
    return 'Text fetched';
  }
  return actionDescription.value;
});

// Extract URL for display in fetching overlay
const fetchingUrl = computed(() => {
  const url = props.toolContent?.args?.url || '';
  try {
    const parsed = new URL(url);
    return parsed.hostname + parsed.pathname.substring(0, 30) + (parsed.pathname.length > 30 ? '...' : '');
  } catch {
    return url.substring(0, 50) + (url.length > 50 ? '...' : '');
  }
});

// VNC event handlers
const onVNCConnected = () => {
  console.log('VNC connection successful');
};

const onVNCDisconnected = (reason?: any) => {
  console.log('VNC connection disconnected', reason);
};

const onVNCCredentialsRequired = () => {
  console.log('VNC credentials required');
};

watch(() => props.toolContent?.content?.screenshot, async () => {
  if (!props.toolContent?.content?.screenshot) {
    return;
  }
  imageUrl.value = props.toolContent?.content?.screenshot;
}, { immediate: true });

const takeOver = () => {
  window.dispatchEvent(new CustomEvent('takeover', {
    detail: {
      sessionId: props.sessionId,
      active: true
    }
  }));
};
</script>

<style scoped>
/* Fetching Overlay Styles */
.fetching-container {
  position: relative;
  width: 120px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Animated orbs around the globe */
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

/* Globe wrapper with glow effect */
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

/* Bouncing dots for "Fetching..." */
.dot {
  display: inline-block;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: var(--text-tertiary);
  animation: bounce-dot 1.4s ease-in-out infinite;
}

/* Animations */
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
    transform: scale(1) rotate(0deg);
  }
  25% {
    transform: scale(1.05) rotate(5deg);
  }
  50% {
    transform: scale(1) rotate(0deg);
  }
  75% {
    transform: scale(1.05) rotate(-5deg);
  }
}

@keyframes bounce-dot {
  0%, 80%, 100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-6px);
  }
}
</style>
