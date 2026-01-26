<template>
  <!-- Header with tabs -->
  <div
    class="h-[36px] flex items-center px-3 w-full bg-[var(--background-gray-main)] border-b border-[var(--border-main)] rounded-t-[12px] shadow-[inset_0px_1px_0px_0px_#FFFFFF] dark:shadow-[inset_0px_1px_0px_0px_#FFFFFF30]">
    <div class="flex-1 flex items-center justify-center gap-2">
      <!-- Activity indicator -->
      <div v-if="isActiveOperation" class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
      <div class="max-w-[200px] truncate text-[var(--text-tertiary)] text-sm font-medium text-center">
        {{ headerText }}
      </div>
    </div>
    <!-- View mode toggle -->
    <div class="flex items-center gap-1 bg-[var(--fill-tsp-gray-main)] rounded-lg p-0.5">
      <button
        @click="viewMode = 'vnc'"
        class="px-2 py-1 text-xs rounded-md transition-colors"
        :class="viewMode === 'vnc' ? 'bg-[var(--background-white-main)] text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'"
      >
        Screen
      </button>
      <button
        @click="viewMode = 'output'"
        class="px-2 py-1 text-xs rounded-md transition-colors relative"
        :class="viewMode === 'output' ? 'bg-[var(--background-white-main)] text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'"
      >
        Output
        <span v-if="hasNewOutput && viewMode !== 'output'" class="absolute -top-0.5 -right-0.5 w-2 h-2 bg-blue-500 rounded-full"></span>
      </button>
    </div>
  </div>

  <div class="flex-1 min-h-0 w-full overflow-hidden">
    <div class="h-full flex flex-col relative">
      <!-- VNC View -->
      <div v-show="viewMode === 'vnc'" class="w-full h-full flex items-center justify-center bg-[var(--fill-white)] relative">
        <!-- Text-only operation placeholder -->
        <div v-if="showTextPlaceholder" class="w-full h-full flex flex-col items-center justify-center bg-gradient-to-b from-[var(--background-gray-main)] to-[var(--fill-white)] dark:from-[#1a1a2e] dark:to-[#16213e]">
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
              <span class="text-base font-medium">{{ actionLabel }}</span>
              <span v-if="isActiveOperation" class="flex gap-1">
                <span v-for="(_, i) in 3" :key="i" class="dot" :style="{ animationDelay: `${i * 200}ms` }"></span>
              </span>
            </div>
            <div v-if="currentOperationDetail" class="max-w-[280px] text-center text-xs text-[var(--text-tertiary)] truncate px-4">
              {{ currentOperationDetail }}
            </div>
          </div>
        </div>

        <!-- Live VNC -->
        <VNCViewer
          v-else-if="showLiveVnc"
          :session-id="props.sessionId"
          :enabled="props.live"
          :view-only="true"
          @connected="onVNCConnected"
          @disconnected="onVNCDisconnected"
          class="w-full h-full"
        />

        <!-- Static screenshot -->
        <img v-else-if="imageUrl" :src="imageUrl" alt="Screenshot" class="w-full h-full object-contain" />

        <!-- Take over button -->
        <button
          v-if="!isShare && props.live"
          @click="takeOver"
          class="absolute right-3 bottom-3 z-10 min-w-10 h-10 flex items-center justify-center rounded-full bg-[var(--background-white-main)] text-[var(--text-primary)] border border-[var(--border-main)] shadow-lg cursor-pointer hover:bg-[var(--text-brand)] hover:px-4 hover:text-white group transition-all duration-300">
          <TakeOverIcon />
          <span class="text-sm max-w-0 overflow-hidden whitespace-nowrap opacity-0 transition-all duration-300 group-hover:max-w-[200px] group-hover:opacity-100 group-hover:ml-1">
            {{ t('Take Over') }}
          </span>
        </button>
      </div>

      <!-- Output View - Terminal/File content -->
      <div v-show="viewMode === 'output'" class="w-full h-full flex flex-col bg-[#1e1e1e] text-gray-100 font-mono text-sm overflow-hidden">
        <!-- Output type indicator -->
        <div class="flex items-center gap-2 px-3 py-2 bg-[#2d2d2d] border-b border-[#404040]">
          <component :is="outputIcon" class="w-4 h-4 text-gray-400" />
          <span class="text-xs text-gray-400">{{ outputTypeLabel }}</span>
          <div v-if="isActiveOperation" class="ml-auto flex items-center gap-1.5">
            <div class="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></div>
            <span class="text-xs text-green-400">Live</span>
          </div>
        </div>

        <!-- Streaming content -->
        <div ref="outputRef" class="flex-1 overflow-y-auto p-3 whitespace-pre-wrap break-all">
          <!-- Shell output -->
          <template v-if="toolName === 'shell' || toolName === 'code_executor'">
            <div v-if="shellOutput" v-html="formatShellOutput(shellOutput)"></div>
            <div v-else class="text-gray-500 italic">Waiting for output...</div>
          </template>

          <!-- File content -->
          <template v-else-if="toolName === 'file'">
            <div v-if="fileContent" class="text-gray-200">{{ fileContent }}</div>
            <div v-else class="text-gray-500 italic">
              {{ isFileWrite ? 'Generating content...' : 'Reading file...' }}
            </div>
          </template>

          <!-- Browser content -->
          <template v-else-if="toolName === 'browser' || toolName === 'browser_agent'">
            <div v-if="browserContent" class="text-gray-200">{{ browserContent }}</div>
            <div v-else class="text-gray-500 italic">Browser activity...</div>
          </template>

          <!-- Generic output -->
          <template v-else>
            <div v-if="genericOutput" class="text-gray-200">{{ genericOutput }}</div>
            <div v-else class="text-gray-500 italic">No output yet...</div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { Terminal, FileText, Globe, Code } from 'lucide-vue-next';
import { ToolContent } from '@/types/message';
import VNCViewer from '@/components/VNCViewer.vue';
import TakeOverIcon from '@/components/icons/TakeOverIcon.vue';

const props = defineProps<{
  sessionId: string;
  toolContent: ToolContent;
  live: boolean;
  isShare: boolean;
}>();

const { t } = useI18n();

// View mode state
const viewMode = ref<'vnc' | 'output'>('vnc');
const hasNewOutput = ref(false);
const outputRef = ref<HTMLElement>();
const imageUrl = ref('');

// Tool detection
const toolName = computed(() => props.toolContent?.name || '');
const toolFunction = computed(() => props.toolContent?.function || '');
const toolStatus = computed(() => props.toolContent?.status || '');

// Activity detection
const isActiveOperation = computed(() => {
  return toolStatus.value === 'calling' || toolStatus.value === 'running';
});

const TEXT_ONLY_FUNCTIONS = new Set(['browser_get_content', 'browser_agent_extract']);
const isTextOnlyOperation = computed(() => TEXT_ONLY_FUNCTIONS.has(toolFunction.value));

// Default view mode per tool
const defaultViewMode = computed<'vnc' | 'output'>(() => {
  if (toolName.value === 'shell' || toolName.value === 'file' || toolName.value === 'code_executor') {
    return 'output';
  }
  if (isTextOnlyOperation.value) return 'output';
  return 'vnc';
});

// Show states
const showTextPlaceholder = computed(() => isTextOnlyOperation.value);
const showLiveVnc = computed(() => props.live && !isTextOnlyOperation.value);

// Header text
const headerText = computed(() => {
  const url = props.toolContent?.args?.url;
  if (url) return url;

  const nameMap: Record<string, string> = {
    'shell': 'Terminal',
    'file': 'File System',
    'code_executor': 'Code Execution',
    'browser': 'Browser',
    'browser_agent': 'Browser Agent',
  };
  return nameMap[toolName.value] || 'Sandbox';
});

// Action label for placeholder
const actionLabel = computed(() => {
  const funcMap: Record<string, string> = {
    'browser_get_content': 'Fetching page content',
    'browser_agent_extract': 'Extracting data',
    'shell_execute': 'Executing command',
    'file_write': 'Writing file',
    'file_read': 'Reading file',
    'code_execute': 'Running code',
  };
  return funcMap[toolFunction.value] || 'Processing';
});

// Operation detail
const currentOperationDetail = computed(() => {
  const args = props.toolContent?.args || {};
  if (args.url) {
    try {
      const u = new URL(args.url);
      return u.hostname + u.pathname.slice(0, 30);
    } catch { return args.url.slice(0, 50); }
  }
  if (args.file) return args.file.replace(/^\/home\/ubuntu\//, '');
  if (args.command) return args.command.slice(0, 50);
  if (args.code) return `${args.code.slice(0, 30)}...`;
  return '';
});

// Output icon
const outputIcon = computed(() => {
  if (toolName.value === 'shell' || toolName.value === 'code_executor') return Terminal;
  if (toolName.value === 'file') return FileText;
  if (toolName.value === 'browser' || toolName.value === 'browser_agent') return Globe;
  return Code;
});

// Output type label
const outputTypeLabel = computed(() => {
  const labels: Record<string, string> = {
    'shell': 'Terminal Output',
    'file': isFileWrite.value ? 'File Content (Writing)' : 'File Content',
    'code_executor': 'Execution Output',
    'browser': 'Browser Content',
    'browser_agent': 'Browser Agent Output',
  };
  return labels[toolName.value] || 'Output';
});

// File operations
const isFileWrite = computed(() => toolFunction.value === 'file_write');

// Extract content from tool
const shellOutput = computed(() => {
  const content = props.toolContent?.content;
  if (!content) return '';

  // Shell console output (array format)
  if (content.console && Array.isArray(content.console)) {
    return content.console.map((entry: any) => {
      let line = '';
      if (entry.ps1) line += entry.ps1 + ' ';
      if (entry.command) line += entry.command + '\n';
      if (entry.output) line += entry.output + '\n';
      return line;
    }).join('');
  }

  // String console output
  if (typeof content.console === 'string') return content.console;

  // Code executor output
  if (content.stdout) return content.stdout + (content.stderr ? '\n[stderr]\n' + content.stderr : '');

  return '';
});

const fileContent = computed(() => {
  // During writing, show the content being written from args
  if (isFileWrite.value && toolStatus.value === 'calling') {
    return props.toolContent?.args?.content || props.toolContent?.content?.content || '';
  }
  // After completion, show the content from result
  return props.toolContent?.content?.content || '';
});

const browserContent = computed(() => {
  return props.toolContent?.content?.content || '';
});

const genericOutput = computed(() => {
  const content = props.toolContent?.content;
  if (!content) return '';
  if (typeof content === 'string') return content;
  return JSON.stringify(content, null, 2);
});

// Format shell output with ANSI colors
const formatShellOutput = (output: string) => {
  // Simple formatting - highlight prompts
  return output
    .replace(/(\$|\>)\s/g, '<span class="text-green-400">$1</span> ')
    .replace(/(error|Error|ERROR)/gi, '<span class="text-red-400">$1</span>')
    .replace(/(warning|Warning|WARNING)/gi, '<span class="text-yellow-400">$1</span>')
    .replace(/(success|Success|SUCCESS|done|Done|DONE)/gi, '<span class="text-green-400">$1</span>');
};

// Auto-scroll output
watch([shellOutput, fileContent, browserContent], async () => {
  hasNewOutput.value = viewMode.value !== 'output';
  await nextTick();
  if (outputRef.value) {
    outputRef.value.scrollTop = outputRef.value.scrollHeight;
  }
});

// Switch to output view when there's new content during active operation
watch([shellOutput, fileContent], () => {
  if (isActiveOperation.value && (shellOutput.value || fileContent.value)) {
    // Auto-switch to output view when content starts streaming
    if (viewMode.value === 'vnc' && !showLiveVnc.value) {
      viewMode.value = 'output';
    }
  }
});

// Reset view mode when a new tool starts
watch(
  () => props.toolContent?.tool_call_id,
  () => {
    viewMode.value = defaultViewMode.value;
    hasNewOutput.value = false;
  },
  { immediate: true }
);

// VNC handlers
const onVNCConnected = () => console.log('VNC connected');
const onVNCDisconnected = () => console.log('VNC disconnected');

// Screenshot handling
watch(() => props.toolContent?.content?.screenshot, (screenshot) => {
  if (screenshot) imageUrl.value = screenshot;
}, { immediate: true });

// Take over
const takeOver = () => {
  window.dispatchEvent(new CustomEvent('takeover', {
    detail: { sessionId: props.sessionId, active: true }
  }));
};
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
