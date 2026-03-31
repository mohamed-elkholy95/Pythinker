<template>
  <!-- Header with tabs -->
  <div
    class="h-[36px] flex items-center px-3 w-full bg-[var(--background-gray-main)] border-b border-[var(--border-main)] rounded-t-[12px] shadow-[inset_0px_1px_0px_0px_#FFFFFF] dark:shadow-[inset_0px_1px_0px_0px_#FFFFFF30]">
    <div class="flex-1 flex items-center justify-center gap-2">
      <div class="max-w-[200px] truncate text-[var(--text-tertiary)] text-sm font-medium text-center">
        {{ headerText }}
      </div>
    </div>
    <!-- View mode toggle -->
    <div class="flex items-center gap-1 bg-[var(--fill-tsp-gray-main)] rounded-lg p-0.5">
      <button
        @click="viewMode = 'screen'"
        class="px-2 py-1 text-xs rounded-md transition-colors"
        :class="viewMode === 'screen' ? 'bg-[var(--background-white-main)] text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'"
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

  <ContentContainer :scrollable="false" padding="none" class="tool-view-body">
    <div class="h-full flex flex-col relative">
      <!-- Live preview -->
      <div v-show="viewMode === 'screen'" class="w-full h-full flex items-center justify-center bg-[var(--fill-white)] relative">
        <!-- Text-only operation placeholder -->
        <LoadingState
          v-if="showTextPlaceholder"
          :label="actionLabel"
          :detail="currentOperationDetail"
          :is-active="isActiveOperation"
          animation="globe"
        />

        <!-- Live preview -->
        <LiveViewer
          v-else-if="showLivePreview"
          ref="livePreviewRef"
          :session-id="props.sessionId"
          :enabled="props.live && !isTakeoverOverlayActive"
          :view-only="true"
          @connected="onLivePreviewConnected"
          @disconnected="onLivePreviewDisconnected"
          class="w-full h-full"
        />

        <!-- Static screenshot -->
        <img v-else-if="imageUrl" :src="imageUrl" alt="Screenshot" class="w-full h-full object-contain" />

        <!-- Take over button -->
        <button
          v-if="!isShare && props.live"
          @click="takeOver"
          class="takeover-btn absolute right-3 bottom-3 z-10 min-w-10 h-10 flex items-center justify-center rounded-full bg-[var(--background-white-main)] text-[var(--text-primary)] border border-[var(--border-main)] shadow-lg cursor-pointer hover:bg-[var(--text-brand)] hover:px-4 hover:text-[var(--text-onblack)] group transition-all duration-300">
          <TakeOverIcon />
          <span class="text-sm max-w-0 overflow-hidden whitespace-nowrap opacity-0 transition-all duration-300 group-hover:max-w-[200px] group-hover:opacity-100 group-hover:ml-1">
            {{ t('Take Over') }}
          </span>
        </button>
      </div>

      <!-- Output View - Terminal/File content -->
      <div v-show="viewMode === 'output'" class="output-panel">
        <!-- Output type indicator -->
        <div class="output-header">
          <component :is="outputIcon" class="w-4 h-4 text-gray-400" />
          <span class="text-xs text-gray-400">{{ outputTypeLabel }}</span>
          <div v-if="isActiveOperation" class="ml-auto flex items-center gap-1.5">
            <div class="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></div>
            <span class="text-xs text-green-400">Live</span>
          </div>
        </div>

        <!-- Streaming content -->
        <div ref="outputRef" class="output-body">
          <!-- Shell output -->
          <template v-if="toolName === 'shell' || toolName === 'code_executor'">
            <div v-if="shellOutput" v-html="formatShellOutput(shellOutput)"></div>
            <EmptyState v-else :message="outputEmptyMessage" :icon="outputEmptyIcon" />
          </template>

          <!-- File content -->
          <template v-else-if="toolName === 'file'">
            <div v-if="fileContent" class="text-gray-200">{{ fileContent }}</div>
            <EmptyState v-else :message="outputEmptyMessage" :icon="outputEmptyIcon" />
          </template>

          <!-- Browser content -->
          <template v-else-if="toolName === 'browser' || toolName === 'browser_agent'">
            <div v-if="browserContent" class="text-gray-200">{{ browserContent }}</div>
            <EmptyState v-else :message="outputEmptyMessage" :icon="outputEmptyIcon" />
          </template>

          <!-- Generic output -->
          <template v-else>
            <div v-if="genericOutput" class="text-gray-200">{{ genericOutput }}</div>
            <EmptyState v-else :message="outputEmptyMessage" :icon="outputEmptyIcon" />
          </template>
        </div>
      </div>
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { Terminal, FileText, Globe, Code } from 'lucide-vue-next';
import { ToolContent } from '@/types/message';
import type { ConsoleRecord } from '@/types/response';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';
import LiveViewer from '@/components/LiveViewer.vue';
import TakeOverIcon from '@/components/icons/TakeOverIcon.vue';
import { getToolDisplay } from '@/utils/toolDisplay';
import { startTakeover } from '@/api/agent';
import { isTakeoverOverlayActive } from '@/composables/takeoverOverlayState';
import type { ToolEventData } from '@/types/event';

const props = defineProps<{
  sessionId: string;
  toolContent: ToolContent;
  live: boolean;
  isShare: boolean;
}>();

const { t } = useI18n();

// View mode state
const viewMode = ref<'screen' | 'output'>('screen');
const hasNewOutput = ref(false);
const outputRef = ref<HTMLElement>();
const imageUrl = ref('');

// Tool detection
const toolName = computed(() => props.toolContent?.name || '');
const toolFunction = computed(() => props.toolContent?.function || '');
const toolStatus = computed(() => props.toolContent?.status || '');

const toolDisplay = computed(() => getToolDisplay({
  name: props.toolContent?.name,
  function: props.toolContent?.function,
  args: props.toolContent?.args,
  display_command: props.toolContent?.display_command
}));

// Activity detection
const isActiveOperation = computed(() => {
  return toolStatus.value === 'calling' || toolStatus.value === 'running';
});

const TEXT_ONLY_FUNCTIONS = new Set(['browser_get_content', 'browser_agent_extract']);
const isTextOnlyOperation = computed(() => TEXT_ONLY_FUNCTIONS.has(toolFunction.value));

// Default view mode per tool
const defaultViewMode = computed<'screen' | 'output'>(() => {
  if (toolName.value === 'shell' || toolName.value === 'file' || toolName.value === 'code_executor') {
    return 'output';
  }
  if (isTextOnlyOperation.value) return 'output';
  return 'screen';
});

// Show states
const showTextPlaceholder = computed(() => isTextOnlyOperation.value);
const showLivePreview = computed(() => props.live && !isTextOnlyOperation.value);

// Header text
const headerText = computed(() => toolDisplay.value.displayName);

// Action label for placeholder
const actionLabel = computed(() => toolDisplay.value.actionLabel || 'Processing');

// Operation detail
const currentOperationDetail = computed(() => toolDisplay.value.resourceLabel || '');

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

const outputEmptyMessage = computed(() => {
  if (toolName.value === 'shell' || toolName.value === 'code_executor') {
    return 'Waiting for output...';
  }
  if (toolName.value === 'file') {
    return isFileWrite.value ? 'Generating content...' : 'Reading file...';
  }
  if (toolName.value === 'browser' || toolName.value === 'browser_agent') {
    return 'Browser activity...';
  }
  return 'No output yet...';
});

const outputEmptyIcon = computed(() => {
  if (toolName.value === 'shell') return 'terminal';
  if (toolName.value === 'code_executor') return 'code';
  if (toolName.value === 'file') return 'file';
  if (toolName.value === 'browser' || toolName.value === 'browser_agent') return 'browser';
  return 'inbox';
});

// File operations
const isFileWrite = computed(() => toolFunction.value === 'file_write');

// Extract content from tool
const shellOutput = computed(() => {
  const content = props.toolContent?.content;
  if (!content) return '';

  // Shell console output (array format)
  if (content.console && Array.isArray(content.console)) {
    return content.console.map((entry: ConsoleRecord) => {
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
const escapeHtml = (text: string): string => {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
};

const formatShellOutput = (output: string) => {
  // Escape HTML first to prevent XSS, then apply formatting highlights
  const escaped = escapeHtml(output);
  return escaped
    .replace(/(\$|&gt;)\s/g, '<span class="text-green-400">$1</span> ')
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
    if (viewMode.value === 'screen' && !showLivePreview.value) {
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

// Live preview handlers
const onLivePreviewConnected = () => { /* live preview connected */ };
const onLivePreviewDisconnected = () => { /* live preview disconnected */ };

const livePreviewRef = ref<InstanceType<typeof LiveViewer> | null>(null);
let _lastForwardedToolEventKey = '';

function forwardBrowserToolToLiveViewer(): void {
  if (!props.sessionId || !livePreviewRef.value?.processToolEvent) return;
  const tool = props.toolContent;
  if (!tool?.tool_call_id || !tool.function || !tool.status) return;
  const args = { ...(tool.args || {}) } as Record<string, unknown>;
  const eventKey = JSON.stringify([
    tool.tool_call_id,
    tool.status,
    tool.function,
    args.coordinate_x,
    args.coordinate_y,
    args.x,
    args.y,
    args.url,
  ]);
  if (eventKey === _lastForwardedToolEventKey) return;
  _lastForwardedToolEventKey = eventKey;
  const payload: ToolEventData = {
    event_id: String(tool.event_id ?? tool.tool_call_id),
    timestamp: typeof tool.timestamp === 'number' ? tool.timestamp : Math.floor(Date.now() / 1000),
    tool_call_id: tool.tool_call_id,
    name: String(tool.name ?? tool.function ?? 'browser'),
    status: tool.status === 'interrupted' ? 'called' : tool.status,
    function: tool.function,
    args,
  };
  livePreviewRef.value.processToolEvent(payload);
}

watch(
  () => [
    props.sessionId,
    props.toolContent?.tool_call_id,
    props.toolContent?.status,
    props.toolContent?.function,
    props.toolContent?.args?.coordinate_x,
    props.toolContent?.args?.coordinate_y,
    props.toolContent?.args?.x,
    props.toolContent?.args?.y,
    props.toolContent?.args?.url,
  ],
  () => {
    forwardBrowserToolToLiveViewer();
  },
  { immediate: true },
);

watch(
  () => props.sessionId,
  () => {
    _lastForwardedToolEventKey = '';
    forwardBrowserToolToLiveViewer();
  },
);

watch(livePreviewRef, () => {
  _lastForwardedToolEventKey = '';
  forwardBrowserToolToLiveViewer();
});

// Screenshot handling
watch(() => props.toolContent?.content?.screenshot, (screenshot) => {
  if (typeof screenshot === 'string' && screenshot) {
    imageUrl.value = screenshot;
  }
}, { immediate: true });

// Take over
const takeoverLoading = ref(false);

const takeOver = async () => {
  if (!props.sessionId || takeoverLoading.value) return;

  takeoverLoading.value = true;
  try {
    // Pause agent first via takeover API
    const status = await startTakeover(props.sessionId, 'manual');

    // Only enter takeover UI when backend confirms agent is paused
    if (status.takeover_state !== 'takeover_active') return;

    window.dispatchEvent(new CustomEvent('takeover', {
      detail: { sessionId: props.sessionId, active: true }
    }));
  } catch {
    // Takeover start failed — agent was not paused, don't enter takeover mode
  } finally {
    takeoverLoading.value = false;
  }
};
</script>

<style scoped>
.tool-view-body {
  flex: 1;
  min-height: 0;
}

.output-panel {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  color: #e5e7eb;
  font-family: Menlo, Monaco, 'Courier New', monospace;
  font-size: 13px;
  overflow: hidden;
}

.output-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #2d2d2d;
  border-bottom: 1px solid #404040;
}

.output-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.output-panel :deep(.empty-icon),
.output-panel :deep(.empty-message) {
  color: rgba(229, 231, 235, 0.65);
}
</style>
