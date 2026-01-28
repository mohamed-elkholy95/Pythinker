<template>
  <div class="agent-computer-container">
    <!-- Computer Window -->
    <div class="computer-window">
      <!-- Window Header -->
      <div class="window-header">
        <div class="window-title">{{ agentName }}'s Computer</div>
        <div class="window-controls">
          <button @click="toggleFullscreen" class="window-control-btn" title="Picture in Picture">
            <MonitorPlay :size="16" />
          </button>
          <button @click="toggleMaximize" class="window-control-btn" title="Maximize">
            <Maximize2 v-if="!isMaximized" :size="16" />
            <Minimize2 v-else :size="16" />
          </button>
          <button @click="emit('close')" class="window-control-btn close-btn" title="Close">
            <X :size="16" />
          </button>
        </div>
      </div>

      <!-- Status Bar -->
      <div class="status-bar">
        <div class="status-content">
          <div class="status-icon">
            <component :is="currentToolIcon" :size="16" class="tool-icon" />
          </div>
          <span class="status-text">
            <span class="agent-name">{{ agentName }}</span> is using
            <span class="tool-name">{{ currentToolName }}</span>
          </span>
          <span v-if="currentAction" class="status-separator">|</span>
          <span v-if="currentAction" class="action-text">{{ currentAction }}</span>
          <span v-if="currentUrl" class="current-url">{{ truncatedUrl }}</span>
        </div>
      </div>

      <!-- Browser Address Bar -->
      <div v-if="showAddressBar" class="address-bar">
        <div class="address-bar-inner">
          <Lock v-if="isHttps" :size="14" class="lock-icon" />
          <Globe v-else :size="14" class="globe-icon" />
          <span class="url-text">{{ displayUrl }}</span>
        </div>
      </div>

      <!-- VNC Display Area -->
      <div class="display-area" :class="{ 'is-maximized': isMaximized }">
        <VNCViewer
          v-if="props.sessionId && showVNC"
          :session-id="props.sessionId"
          :enabled="true"
          :view-only="true"
          @connected="onVNCConnected"
          @disconnected="onVNCDisconnected"
          class="vnc-display"
        />

        <!-- Loading State -->
        <div v-else-if="!isVNCConnected" class="loading-state">
          <div class="loading-spinner"></div>
          <span class="loading-text">Connecting to sandbox...</span>
        </div>

        <!-- Jump to Live Button (shown when scrolled back) -->
        <transition name="fade">
          <button v-if="showJumpToLive" @click="jumpToLive" class="jump-to-live">
            <Play :size="20" />
            <span>Jump to live</span>
          </button>
        </transition>
      </div>

      <!-- Timeline Controls -->
      <div class="timeline-controls">
        <button @click="playPause" class="control-btn" :disabled="!canPlayback">
          <Play v-if="!isPlaying" :size="18" />
          <Pause v-else :size="18" />
        </button>
        <button @click="skipBack" class="control-btn" :disabled="!canPlayback">
          <SkipBack :size="18" />
        </button>

        <!-- Timeline Slider -->
        <div class="timeline-slider">
          <input
            type="range"
            :value="currentTime"
            :max="totalTime"
            :disabled="!canPlayback"
            @input="seekTo"
            class="timeline-input"
          />
          <div class="timeline-progress" :style="{ width: progressPercent + '%' }"></div>
        </div>

        <button @click="skipForward" class="control-btn" :disabled="!canPlayback">
          <SkipForward :size="18" />
        </button>

        <!-- Live indicator -->
        <div class="live-indicator" :class="{ 'is-live': isLive }">
          <div v-if="isLive" class="live-dot"></div>
          <span>{{ isLive ? 'live' : 'paused' }}</span>
        </div>
      </div>

      <!-- Task Progress -->
      <div v-if="showTaskProgress" class="task-progress">
        <div class="task-indicator" :style="{ backgroundColor: taskColor }"></div>
        <div class="task-content">
          <div class="task-title">{{ taskTitle }}</div>
          <div class="task-meta">
            <span class="task-time">{{ taskTime }}</span>
            <span class="task-status">{{ taskStatus }}</span>
            <span v-if="taskSteps" class="task-steps">{{ taskSteps }}</span>
          </div>
        </div>
        <button @click="toggleTaskDetails" class="task-toggle">
          <ChevronUp v-if="showTaskDetails" :size="16" />
          <ChevronDown v-else :size="16" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import {
  MonitorPlay,
  Maximize2,
  Minimize2,
  X,
  Globe,
  Lock,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  ChevronUp,
  ChevronDown,
  Terminal,
  FileText,
  Code,
  MousePointer,
  Keyboard,
} from 'lucide-vue-next';
import VNCViewer from '@/components/VNCViewer.vue';
import type { ToolContent } from '@/types/message';

const props = defineProps<{
  sessionId: string;
  agentName?: string;
  currentTool?: ToolContent;
  taskTitle?: string;
  taskTime?: string;
  taskStatus?: string;
  taskSteps?: string;
  live?: boolean;
}>();

const emit = defineEmits<{
  close: [];
  fullscreen: [];
  taskDetailsToggle: [show: boolean];
}>();

// State
const isMaximized = ref(false);
const isVNCConnected = ref(false);
const showVNC = ref(true);
const showTaskDetails = ref(false);

// Playback state (for timeline)
const isPlaying = ref(true);
const isLive = ref(true);
const currentTime = ref(0);
const totalTime = ref(100);
const canPlayback = ref(false); // Enable when we implement session playback

// Agent name
const agentName = computed(() => props.agentName || 'Agent');

// Current tool information
const currentToolName = computed(() => {
  if (!props.currentTool) return 'Idle';

  const toolMap: Record<string, string> = {
    browser_navigate: 'Browser',
    browser_click: 'Browser',
    browser_input: 'Browser',
    browser_get_content: 'Browser',
    browser_view: 'Browser',
    shell_execute: 'Terminal',
    file_write: 'File Editor',
    file_read: 'File Viewer',
    code_execute: 'Code Executor',
  };

  return toolMap[props.currentTool.function] || 'Browser';
});

const currentToolIcon = computed(() => {
  if (!props.currentTool) return Globe;

  const iconMap: Record<string, any> = {
    browser_navigate: Globe,
    browser_click: MousePointer,
    browser_input: Keyboard,
    browser_get_content: Globe,
    browser_view: Globe,
    shell_execute: Terminal,
    file_write: FileText,
    file_read: FileText,
    code_execute: Code,
  };

  return iconMap[props.currentTool.function] || Globe;
});

const currentAction = computed(() => {
  if (!props.currentTool) return '';

  const actionMap: Record<string, string> = {
    browser_navigate: 'Browsing',
    browser_click: 'Clicking',
    browser_input: 'Typing',
    browser_get_content: 'Reading',
    browser_view: 'Viewing',
    shell_execute: 'Executing',
    file_write: 'Writing',
    file_read: 'Reading',
    code_execute: 'Running code',
  };

  return actionMap[props.currentTool.function] || '';
});

// URL handling
const currentUrl = computed(() => {
  if (!props.currentTool?.args?.url) return '';
  return props.currentTool.args.url;
});

const displayUrl = computed(() => {
  if (!currentUrl.value) return 'about:blank';
  try {
    const url = new URL(currentUrl.value);
    return url.hostname + url.pathname + url.search;
  } catch {
    return currentUrl.value;
  }
});

const truncatedUrl = computed(() => {
  if (!currentUrl.value) return '';
  const maxLen = 50;
  return currentUrl.value.length > maxLen
    ? currentUrl.value.substring(0, maxLen) + '...'
    : currentUrl.value;
});

const isHttps = computed(() => {
  return currentUrl.value.startsWith('https://');
});

const showAddressBar = computed(() => {
  return currentToolName.value === 'Browser' && currentUrl.value;
});

// Task progress
const showTaskProgress = computed(() => {
  return props.taskTitle && props.taskTitle.length > 0;
});

const taskColor = computed(() => {
  // Randomly assigned color per task (in real impl, could be based on task type)
  const colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];
  const hash = (props.taskTitle || '').split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return colors[hash % colors.length];
});

// Timeline
const progressPercent = computed(() => {
  if (totalTime.value === 0) return 0;
  return (currentTime.value / totalTime.value) * 100;
});

const showJumpToLive = computed(() => {
  return !isLive.value && isVNCConnected.value;
});

// Actions
const toggleMaximize = () => {
  isMaximized.value = !isMaximized.value;
};

const toggleFullscreen = () => {
  emit('fullscreen');
};

const playPause = () => {
  if (!canPlayback.value) return;
  isPlaying.value = !isPlaying.value;
  if (isPlaying.value && currentTime.value >= totalTime.value) {
    currentTime.value = 0;
  }
};

const skipBack = () => {
  if (!canPlayback.value) return;
  currentTime.value = Math.max(0, currentTime.value - 10);
  isLive.value = currentTime.value >= totalTime.value;
};

const skipForward = () => {
  if (!canPlayback.value) return;
  currentTime.value = Math.min(totalTime.value, currentTime.value + 10);
  isLive.value = currentTime.value >= totalTime.value;
};

const seekTo = (event: Event) => {
  if (!canPlayback.value) return;
  const target = event.target as HTMLInputElement;
  currentTime.value = parseFloat(target.value);
  isLive.value = currentTime.value >= totalTime.value;
};

const jumpToLive = () => {
  currentTime.value = totalTime.value;
  isLive.value = true;
  isPlaying.value = true;
};

const toggleTaskDetails = () => {
  showTaskDetails.value = !showTaskDetails.value;
  emit('taskDetailsToggle', showTaskDetails.value);
};

// VNC handlers
const onVNCConnected = () => {
  isVNCConnected.value = true;
  console.log('Agent Computer VNC connected');
};

const onVNCDisconnected = () => {
  isVNCConnected.value = false;
  console.log('Agent Computer VNC disconnected');
};

// Watch for live prop changes
watch(() => props.live, (live) => {
  if (live) {
    isLive.value = true;
    isPlaying.value = true;
    currentTime.value = totalTime.value;
  }
}, { immediate: true });
</script>

<style scoped>
.agent-computer-container {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(0, 0, 0, 0.6);
}

.computer-window {
  width: 100%;
  max-width: 960px;
  height: auto;
  max-height: 90vh;
  background: #2d2d2d;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  transition: all 0.3s ease;
}

.computer-window.is-maximized {
  max-width: 100%;
  max-height: 100vh;
  border-radius: 0;
}

/* Window Header */
.window-header {
  height: 48px;
  background: #1e1e1e;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid #404040;
}

.window-title {
  font-size: 15px;
  font-weight: 600;
  color: #e5e7eb;
}

.window-controls {
  display: flex;
  gap: 8px;
}

.window-control-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #9ca3af;
  cursor: pointer;
  transition: all 0.2s;
}

.window-control-btn:hover {
  background: #404040;
  color: #e5e7eb;
}

.window-control-btn.close-btn:hover {
  background: #ef4444;
  color: white;
}

/* Status Bar */
.status-bar {
  height: 40px;
  background: #252525;
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid #404040;
}

.status-content {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #9ca3af;
  width: 100%;
  overflow: hidden;
}

.status-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: #333;
  border-radius: 6px;
  flex-shrink: 0;
}

.tool-icon {
  color: #60a5fa;
}

.agent-name {
  color: #e5e7eb;
  font-weight: 500;
}

.tool-name {
  color: #60a5fa;
  font-weight: 500;
}

.status-separator {
  color: #4b5563;
  margin: 0 4px;
}

.action-text {
  color: #e5e7eb;
}

.current-url {
  color: #6b7280;
  font-size: 12px;
  margin-left: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 1;
}

/* Address Bar */
.address-bar {
  height: 56px;
  background: #1a1a1a;
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid #404040;
}

.address-bar-inner {
  width: 100%;
  height: 36px;
  background: #2d2d2d;
  border: 1px solid #404040;
  border-radius: 8px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  gap: 8px;
}

.lock-icon {
  color: #10b981;
  flex-shrink: 0;
}

.globe-icon {
  color: #6b7280;
  flex-shrink: 0;
}

.url-text {
  flex: 1;
  color: #e5e7eb;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Display Area */
.display-area {
  flex: 1;
  min-height: 400px;
  max-height: 600px;
  background: rgb(40, 40, 40);
  position: relative;
  overflow: hidden;
}

.display-area.is-maximized {
  max-height: calc(90vh - 250px);
}

.vnc-display {
  width: 100%;
  height: 100%;
}

/* Loading State */
.loading-state {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #404040;
  border-top-color: #60a5fa;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.loading-text {
  color: #9ca3af;
  font-size: 14px;
}

/* Jump to Live Button */
.jump-to-live {
  position: absolute;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  background: rgba(0, 0, 0, 0.85);
  border: 1px solid #404040;
  border-radius: 999px;
  color: white;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  backdrop-filter: blur(10px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  transition: all 0.2s;
  z-index: 10;
}

.jump-to-live:hover {
  background: rgba(0, 0, 0, 0.95);
  transform: translateX(-50%) scale(1.05);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Timeline Controls */
.timeline-controls {
  height: 56px;
  background: #1e1e1e;
  border-top: 1px solid #404040;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 12px;
}

.control-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #e5e7eb;
  cursor: pointer;
  transition: all 0.2s;
}

.control-btn:hover:not(:disabled) {
  background: #404040;
}

.control-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.timeline-slider {
  flex: 1;
  height: 36px;
  display: flex;
  align-items: center;
  position: relative;
}

.timeline-input {
  width: 100%;
  height: 4px;
  background: #404040;
  border-radius: 2px;
  outline: none;
  -webkit-appearance: none;
  appearance: none;
  cursor: pointer;
  position: relative;
  z-index: 2;
}

.timeline-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  background: #60a5fa;
  border-radius: 50%;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
}

.timeline-input::-moz-range-thumb {
  width: 14px;
  height: 14px;
  background: #60a5fa;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
}

.timeline-input:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.timeline-progress {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  height: 4px;
  background: #60a5fa;
  border-radius: 2px;
  pointer-events: none;
  transition: width 0.1s linear;
  z-index: 1;
}

.live-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #2d2d2d;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #9ca3af;
}

.live-indicator.is-live {
  color: #e5e7eb;
}

.live-dot {
  width: 8px;
  height: 8px;
  background: #ef4444;
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

/* Task Progress */
.task-progress {
  height: 64px;
  background: #252525;
  border-top: 1px solid #404040;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 12px;
}

.task-indicator {
  width: 4px;
  height: 40px;
  border-radius: 2px;
  flex-shrink: 0;
}

.task-content {
  flex: 1;
  min-width: 0;
}

.task-title {
  font-size: 14px;
  font-weight: 500;
  color: #e5e7eb;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
  font-size: 12px;
  color: #9ca3af;
}

.task-time,
.task-status,
.task-steps {
  display: flex;
  align-items: center;
}

.task-toggle {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #9ca3af;
  cursor: pointer;
  transition: all 0.2s;
}

.task-toggle:hover {
  background: #404040;
  color: #e5e7eb;
}
</style>
