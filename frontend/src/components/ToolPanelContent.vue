<template>
  <div class="bg-[var(--background-gray-main)] sm:bg-[var(--background-menu-white)] sm:rounded-[22px] shadow-[0px_0px_8px_0px_rgba(0,0,0,0.02)] border border-black/8 dark:border-[var(--border-light)] flex h-full w-full">
    <div class="flex-1 min-w-0 p-4 flex flex-col h-full">
      <!-- Frame Header: Pythinker's Computer + window controls -->
      <div class="flex items-center gap-2 w-full">
        <div class="text-[var(--text-primary)] text-lg font-semibold flex-1">{{ $t("Pythinker's Computer") }}</div>
        <div class="flex items-center gap-1">
          <button
            class="w-7 h-7 rounded-md inline-flex items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)]"
            @click="takeOver"
            aria-label="Open takeover"
          >
            <MonitorUp class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
          <button
            class="w-7 h-7 rounded-md inline-flex items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)]"
            @click="hide"
            aria-label="Minimize"
          >
            <Minimize2 class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
          <button
            class="w-7 h-7 rounded-md inline-flex items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)]"
            @click="hide"
            aria-label="Close"
          >
            <X class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
        </div>
      </div>

      <!-- Activity Bar: Icon + "Pythinker is using X" | Action -->
      <div v-if="toolInfo" class="flex items-center gap-2 mt-2 text-[13px] text-[var(--text-tertiary)]">
        <component :is="toolInfo.icon" :size="18" class="flex-shrink-0 text-[var(--icon-secondary)]" />
        <span>{{ $t('Pythinker is using') }} <span class="text-[var(--text-secondary)] font-medium">{{ toolInfo.name }}</span></span>
        <span v-if="toolSubtitle" class="text-[var(--text-quaternary)]">|</span>
        <span v-if="toolSubtitle" class="truncate">{{ toolSubtitle }}</span>
      </div>

      <!-- Confirmation banner removed -->

      <!-- Content Container with rounded frame -->
      <div
        class="relative flex flex-col rounded-[12px] overflow-hidden bg-[var(--background-gray-main)] border border-[var(--border-dark)] dark:border-black/30 shadow-[0px_4px_32px_0px_rgba(0,0,0,0.04)] flex-1 min-h-0 mt-[16px]">

        <!-- Content Header: Resource indicator + View mode tabs -->
        <div
          v-if="contentConfig"
          class="h-[36px] flex items-center px-3 w-full bg-[var(--background-gray-main)] border-b border-[var(--border-main)] rounded-t-[12px] shadow-[inset_0px_1px_0px_0px_#FFFFFF] dark:shadow-[inset_0px_1px_0px_0px_#FFFFFF30]">

          <!-- Left: Activity indicator + resource name -->
          <div class="flex-1 min-w-0 flex items-center gap-2">
            <div v-if="isActiveOperation" class="w-2 h-2 bg-green-500 rounded-full animate-pulse flex-shrink-0"></div>
            <div class="max-w-[200px] truncate text-[var(--text-tertiary)] text-sm font-medium">
              {{ resourceDisplay }}
            </div>
            <!-- Writing indicator for file operations -->
            <div v-if="isFileWriting" class="flex items-center gap-1.5 ml-2">
              <div class="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></div>
              <span class="text-xs text-blue-500 font-medium">Writing</span>
            </div>
          </div>

          <!-- Right: View mode tabs (hidden for text-only operations) -->
          <div v-if="contentConfig.showTabs && !shouldUseTextOnly" class="flex items-center gap-1 bg-[var(--fill-tsp-gray-main)] rounded-lg p-0.5">
            <button
              v-for="(label, idx) in contentConfig.tabLabels"
              :key="idx"
              @click="setViewModeByIndex(idx)"
              class="px-2 py-1 text-xs rounded-md transition-colors relative"
              :class="viewModeIndex === idx ? 'bg-[var(--background-white-main)] text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'"
            >
              {{ label }}
              <span v-if="hasNewOutput && idx === 1 && viewModeIndex !== 1" class="absolute -top-0.5 -right-0.5 w-2 h-2 bg-blue-500 rounded-full"></span>
            </button>
          </div>
        </div>

        <!-- Content Area: Dynamic content rendering -->
        <div class="flex-1 min-h-0 w-full overflow-hidden relative">
          <!-- Text-only operation: Show placeholder while active, terminal when complete -->
          <VNCContentView
            v-if="shouldUseTextOnly && isActiveOperation"
            :session-id="sessionId || ''"
            :enabled="false"
            :view-only="true"
            :show-placeholder="true"
            :placeholder-label="placeholderLabel"
            :placeholder-detail="placeholderDetail"
            :is-active="true"
          />

          <!-- Text-only operation complete: Show terminal output -->
          <TerminalContentView
            v-else-if="shouldUseTextOnly && !isActiveOperation"
            :content="terminalContent"
            :content-type="terminalContentType"
            :is-live="false"
            :auto-scroll="true"
          />

          <!-- VNC View (for non-text-only operations) -->
          <VNCContentView
            ref="vncContentRef"
            v-else-if="currentViewType === 'vnc'"
            :key="'vnc-main-' + (sessionId || 'none')"
            :session-id="sessionId || ''"
            :enabled="vncEnabled"
            :view-only="true"
            :show-placeholder="showVncPlaceholder"
            :placeholder-label="vncPlaceholderLabel"
            :placeholder-detail="vncPlaceholderDetail"
            :is-active="isActiveOperation"
            :screenshot="screenshot"
            @connected="onVNCConnected"
            @disconnected="onVNCDisconnected"
          >
            <template #takeover>
              <button
                v-if="!isShare && live"
                @click="takeOver"
                class="absolute right-3 bottom-3 z-10 min-w-10 h-10 flex items-center justify-center rounded-full bg-[var(--background-white-main)] text-[var(--text-primary)] border border-[var(--border-main)] shadow-lg cursor-pointer hover:bg-[var(--text-brand)] hover:px-4 hover:text-white group transition-all duration-300">
                <TakeOverIcon />
                <span class="text-sm max-w-0 overflow-hidden whitespace-nowrap opacity-0 transition-all duration-300 group-hover:max-w-[200px] group-hover:opacity-100 group-hover:ml-1">
                  {{ $t('Take Over') }}
                </span>
              </button>
            </template>
          </VNCContentView>

          <!-- Terminal View -->
          <TerminalContentView
            v-else-if="currentViewType === 'terminal'"
            :content="terminalContent"
            :content-type="terminalContentType"
            :is-live="isActiveOperation"
            :is-writing="isFileWriting"
            :auto-scroll="true"
            @new-content="onNewTerminalContent"
          />

          <!-- Editor View -->
          <EditorContentView
            v-else-if="currentViewType === 'editor'"
            :content="editorContent"
            :filename="fileName"
            :is-writing="isFileWriting"
            :is-loading="isEditorLoading"
          />

          <!-- Search View -->
          <SearchContentView
            v-else-if="currentViewType === 'search'"
            :results="searchResults"
            :is-searching="isSearching"
            :query="searchQuery"
          />

          <!-- Generic/MCP View -->
          <GenericContentView
            v-else-if="currentViewType === 'generic'"
            :function-name="toolContent?.function"
            :args="toolContent?.args"
            :result="toolContent?.content?.result"
            :content="toolContent?.content"
            :is-executing="isActiveOperation"
          />

          <!-- Fallback -->
          <div v-else class="w-full h-full flex items-center justify-center text-[var(--text-tertiary)]">
            No content available
          </div>
        </div>

        <!-- Timeline Controls -->
        <div class="mt-auto">
          <TimelineControls
            :progress="showTimeline ? (timelineProgress ?? 0) : 0"
            :current-timestamp="showTimeline ? timelineTimestamp : undefined"
            :is-live="realTime"
            :can-step-forward="showTimeline ? !!timelineCanStepForward : false"
            :can-step-backward="showTimeline ? !!timelineCanStepBackward : false"
            :show-timestamp-on-interact="true"
            @jump-to-live="jumpToRealTime"
            @step-forward="handleStepForward"
            @step-backward="handleStepBackward"
            @seek-by-progress="handleSeekByProgress"
          />
        </div>
      </div>

      <!-- Task Progress Bar - outside content container, at bottom -->
      <div
        v-if="plan && plan.steps.length > 0"
        class="relative z-10 mt-3"
      >
        <TaskProgressBar
          :plan="plan"
          :isLoading="isLoading"
          :isThinking="isThinking"
          :showThumbnail="false"
          :defaultExpanded="false"
          :compact="true"
          :thumbnailUrl="thumbnailUrl"
          :currentTool="currentToolForProgress"
          :toolContent="toolContent"
          :hideExpandedHeader="true"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef, computed, watch, ref, onMounted, onUnmounted } from 'vue';
import { Minimize2, MonitorUp, X } from 'lucide-vue-next';
import type { ToolContent } from '@/types/message';
import type { PlanEventData } from '@/types/event';
import { useToolInfo } from '@/composables/useTool';
import { useContentConfig } from '@/composables/useContentConfig';
import { viewFile, viewShellSession } from '@/api/agent';
import TimelineControls from '@/components/timeline/TimelineControls.vue';
import TakeOverIcon from '@/components/icons/TakeOverIcon.vue';
import TaskProgressBar from '@/components/TaskProgressBar.vue';

// Content views
import VNCContentView from '@/components/toolViews/VNCContentView.vue';
import TerminalContentView from '@/components/toolViews/TerminalContentView.vue';
import EditorContentView from '@/components/toolViews/EditorContentView.vue';
import SearchContentView from '@/components/toolViews/SearchContentView.vue';
import GenericContentView from '@/components/toolViews/GenericContentView.vue';

const props = defineProps<{
  sessionId?: string;
  realTime: boolean;
  toolContent: ToolContent;
  live: boolean;
  isShare: boolean;
  showTimeline?: boolean;
  timelineProgress?: number;
  timelineTimestamp?: number;
  timelineCanStepForward?: boolean;
  timelineCanStepBackward?: boolean;
  plan?: PlanEventData;
  isLoading?: boolean;
  isThinking?: boolean;
  thumbnailUrl?: string;
}>();

// Computed for TaskProgressBar current tool
const currentToolForProgress = computed(() => {
  if (!props.toolContent) return null;
  return {
    name: props.toolContent.name || '',
    function: props.toolContent.function || '',
    functionArg: props.toolContent.args ? Object.values(props.toolContent.args)[0]?.toString() : undefined,
    status: props.toolContent.status
  };
});

// Get tool info (icon, name, etc.)
const { toolInfo } = useToolInfo(toRef(props, 'toolContent'));

// Get content config for unified tabs
const {
  contentConfig,
  viewModeIndex,
  currentViewType,
  isTextOnlyOperation,
  hasNewOutput,
  setViewModeByIndex,
  markNewOutput
} = useContentConfig(toRef(props, 'toolContent'));

// Tool state
const toolName = computed(() => props.toolContent?.name || '');
const toolFunction = computed(() => props.toolContent?.function || '');
const toolStatus = computed(() => props.toolContent?.status || '');

// Activity detection
const isActiveOperation = computed(() => {
  return toolStatus.value === 'calling' || toolStatus.value === 'running';
});

// File operations
const isFileWriting = computed(() => {
  return toolFunction.value === 'file_write' && toolStatus.value === 'calling';
});

const isSearching = computed(() => {
  return (toolName.value === 'search' || toolName.value === 'info') && toolStatus.value === 'calling';
});

// Tool subtitle
const toolSubtitle = computed(() => {
  if (toolName.value === 'file' && (props.toolContent?.args?.file || props.toolContent?.file_path)) {
    const pathValue = props.toolContent?.args?.file || props.toolContent?.file_path || '';
    const path = String(pathValue).replace(/^\/home\/ubuntu\//, '');
    return `Editing file ${path}`;
  }
  if (toolName.value === 'shell' && props.toolContent?.args?.command) {
    const cmd = props.toolContent.command || props.toolContent.args.command;
    return `Running ${String(cmd).slice(0, 60)}`;
  }
  if (toolName.value === 'browser' && props.toolContent?.args?.url) {
    return `Browsing ${String(props.toolContent.args.url).replace(/^https?:\/\//, '')}`;
  }
  if (toolInfo.value?.function && toolInfo.value?.functionArg) {
    return `${toolInfo.value.function} ${toolInfo.value.functionArg}`;
  }
  if (toolInfo.value?.function) {
    return toolInfo.value.function;
  }
  return '';
});

// Resource display for content header
const resourceDisplay = computed(() => {
  const url = props.toolContent?.args?.url;
  if (url) return url;

  const file = props.toolContent?.args?.file || props.toolContent?.file_path;
  if (file) return String(file).replace(/^\/home\/ubuntu\//, '');

  const nameMap: Record<string, string> = {
    'shell': 'Terminal',
    'file': 'File System',
    'code_executor': 'Code Execution',
    'browser': 'Browser',
    'browser_agent': 'Browser Agent',
    'search': 'Web Search',
    'info': 'Information',
    'mcp': 'MCP Tool'
  };
  return nameMap[toolName.value] || 'Sandbox';
});

// Placeholder label for text-only operations
const placeholderLabel = computed(() => {
  const funcMap: Record<string, string> = {
    'browser_get_content': 'Fetching page content',
    'browser_agent_extract': 'Extracting data',
    'shell_exec': 'Executing command',
    'shell_execute': 'Executing command',
    'file_write': 'Writing file',
    'file_read': 'Reading file',
    'code_execute': 'Running code',
  };
  return funcMap[toolFunction.value] || 'Processing';
});

// Placeholder detail
const placeholderDetail = computed(() => {
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

// VNC Content ref for screenshot capture
const vncContentRef = ref<InstanceType<typeof VNCContentView> | null>(null);

// Screenshot
const screenshot = ref('');
watch(() => props.toolContent?.content?.screenshot, (newScreenshot) => {
  if (newScreenshot) screenshot.value = newScreenshot;
}, { immediate: true });

const showVncPlaceholder = computed(() => {
  if (!props.sessionId && !screenshot.value) return true;
  if (vncDisconnected.value && !screenshot.value) return true;
  return false;
});

const vncPlaceholderLabel = computed(() => {
  if (!props.sessionId) return 'No live session';
  if (vncDisconnected.value) return 'Reconnecting';
  return 'Connecting';
});

const vncPlaceholderDetail = computed(() => {
  if (!props.sessionId) return 'Open a session to view the screen.';
  if (vncDisconnected.value) return 'Waiting for the VNC stream.';
  return '';
});

const shouldUseTextOnly = computed(() => {
  if (!isTextOnlyOperation.value) return false;
  return !screenshot.value;
});

const vncEnabled = computed(() => {
  return !!props.sessionId && !showVncPlaceholder.value;
});

// ============ Terminal Content ============
const shellOutput = ref('');
const refreshTimer = ref<number | null>(null);

const terminalContentType = computed<'shell' | 'file' | 'browser' | 'code' | 'generic'>(() => {
  if (toolName.value === 'shell') return 'shell';
  if (toolName.value === 'code_executor') return 'code';
  if (toolName.value === 'file') return 'file';
  if (toolName.value === 'browser' || toolName.value === 'browser_agent') return 'browser';
  return 'generic';
});

const terminalContent = computed(() => {
  // Shell/Code executor output
  if (toolName.value === 'shell' || toolName.value === 'code_executor') {
    if (shellOutput.value) return shellOutput.value;

    const command = props.toolContent?.command || props.toolContent?.args?.command;
    const stdout = props.toolContent?.stdout;
    const stderr = props.toolContent?.stderr;
    const exitCode = props.toolContent?.exit_code;
    if (command || stdout || stderr || exitCode !== undefined) {
      let output = '';
      if (command) {
        output += `$ ${command}\n`;
      }
      if (stdout) {
        output += `${stdout}\n`;
      }
      if (stderr) {
        output += `[stderr]\n${stderr}\n`;
      }
      if (exitCode !== undefined && exitCode !== null) {
        output += `[exit code: ${exitCode}]\n`;
      }
      return output.trimEnd();
    }

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
  }

  // File content
  if (toolName.value === 'file') {
    if (isFileWriting.value) {
      return props.toolContent?.args?.content || props.toolContent?.content?.content || '';
    }
    return props.toolContent?.content?.content || '';
  }

  // Browser content
  if (toolName.value === 'browser' || toolName.value === 'browser_agent') {
    return props.toolContent?.content?.content || '';
  }

  // Generic
  const content = props.toolContent?.content;
  if (!content) return '';
  if (typeof content === 'string') return content;
  return JSON.stringify(content, null, 2);
});

// Load shell content via API
const loadShellContent = async () => {
  const shellSessionId = props.toolContent?.args?.id;
  if (!props.live || !shellSessionId || !props.sessionId) {
    // Use content from props
    const content = props.toolContent?.content;
    if (content?.console && Array.isArray(content.console)) {
      let newOutput = '';
      for (const e of content.console) {
        newOutput += `${e.ps1} ${e.command}\n`;
        newOutput += `${e.output}\n`;
      }
      shellOutput.value = newOutput;
    }
    return;
  }

  try {
    const response = await viewShellSession(props.sessionId, shellSessionId);
    if (response?.console) {
      let newOutput = '';
      for (const e of response.console) {
        newOutput += `${e.ps1} ${e.command}\n`;
        newOutput += `${e.output}\n`;
      }
      shellOutput.value = newOutput;
    }
  } catch (error) {
    console.error("Failed to load shell content:", error);
  }
};

// Start auto-refresh timer for shell
const startAutoRefresh = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
  }
  if (props.live && (toolName.value === 'shell' || toolName.value === 'code_executor')) {
    refreshTimer.value = setInterval(loadShellContent, 5000);
  }
};

const stopAutoRefresh = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
    refreshTimer.value = null;
  }
};

// Watch for tool changes
watch(() => props.toolContent, () => {
  if (toolName.value === 'shell' || toolName.value === 'code_executor') {
    loadShellContent();
  }
});

watch(() => props.live, (live) => {
  if (live) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
});

onMounted(() => {
  if (toolName.value === 'shell' || toolName.value === 'code_executor') {
    loadShellContent();
  }
  startAutoRefresh();
});

onUnmounted(() => {
  stopAutoRefresh();
});

// ============ Editor Content ============
const fileContent = ref('');
const originalContent = ref('');
const vncDisconnected = ref(false);

const getToolContentText = () => {
  const content = props.toolContent?.content;
  if (!content) return '';
  if (typeof content === 'string') return content;
  if (typeof (content as { content?: unknown }).content === 'string') {
    return (content as { content: string }).content;
  }
  return '';
};

const fileName = computed(() => {
  const file = props.toolContent?.args?.file;
  if (file) return String(file).split('/').pop() || '';
  return '';
});

const editorContent = computed(() => {
  // For file view modes
  if (toolName.value !== 'file') return '';

  // Modified view (primary)
  if (viewModeIndex.value === 0) {
    if (isFileWriting.value) {
      const argContent = typeof props.toolContent?.args?.content === 'string'
        ? props.toolContent?.args?.content
        : '';
      return argContent || getToolContentText() || fileContent.value;
    }
    return fileContent.value || getToolContentText() || '';
  }

  // Original view (secondary)
  if (viewModeIndex.value === 1) {
    return originalContent.value || fileContent.value;
  }

  // Diff view (tertiary)
  if (viewModeIndex.value === 2) {
    if (props.toolContent?.diff) {
      return props.toolContent.diff;
    }
    return buildSimpleDiff(originalContent.value, fileContent.value);
  }

  return fileContent.value;
});

const isEditorLoading = computed(() => {
  if (toolName.value !== 'file') return false;
  if (!isFileWriting.value) return false;
  return editorContent.value.trim().length === 0;
});

const buildSimpleDiff = (original: string, modified: string): string => {
  if (!original && !modified) return "";
  if (!original) return `+ ${modified}`;
  if (!modified) return `- ${original}`;

  const originalLines = original.split('\n');
  const modifiedLines = modified.split('\n');
  const maxLines = Math.max(originalLines.length, modifiedLines.length);
  const out: string[] = [];

  for (let i = 0; i < maxLines; i += 1) {
    const a = originalLines[i];
    const b = modifiedLines[i];
    if (a === b) {
      out.push(`  ${a ?? ''}`);
    } else {
      if (a !== undefined) out.push(`- ${a}`);
      if (b !== undefined) out.push(`+ ${b}`);
    }
  }

  return out.join('\n');
};

// Load file content
const loadFileContent = async () => {
  const filePath = props.toolContent?.args?.file;

  // During file_write, show streaming content
  if (isFileWriting.value) {
    const argContent = typeof props.toolContent?.args?.content === 'string'
      ? props.toolContent?.args?.content
      : '';
    const streamingContent = getToolContentText() || argContent || '';
    if (fileContent.value && fileContent.value !== streamingContent) {
      originalContent.value = fileContent.value;
    }
    fileContent.value = streamingContent;
    return;
  }

  if (!props.live) {
    const nextContent = getToolContentText() || '';
    if (fileContent.value && fileContent.value !== nextContent) {
      originalContent.value = fileContent.value;
    }
    fileContent.value = nextContent;
    return;
  }

  if (!filePath || !props.sessionId) return;

  try {
    const response = await viewFile(props.sessionId, filePath);
    const nextContent = response.content;
    if (fileContent.value && fileContent.value !== nextContent) {
      originalContent.value = fileContent.value;
    }
    fileContent.value = nextContent;
  } catch (error) {
    console.error("Failed to load file content:", error);
  }
};

// Watch file changes
watch(() => props.toolContent?.args?.file, (newFile) => {
  if (newFile && toolName.value === 'file') {
    loadFileContent();
  }
});

watch(() => props.toolContent?.status, () => {
  if (toolName.value === 'file') {
    loadFileContent();
  }
});

watch(() => props.toolContent?.args?.content, () => {
  if (toolName.value === 'file' && isFileWriting.value) {
    loadFileContent();
  }
});

// Confirmation state watcher removed

// ============ Search Content ============
const searchResults = computed(() => {
  return props.toolContent?.content?.results || [];
});

const searchQuery = computed(() => {
  return props.toolContent?.args?.query || '';
});

// ============ Event Handlers ============
const emit = defineEmits<{
  (e: 'jumpToRealTime'): void,
  (e: 'hide'): void
  (e: 'stepForward'): void
  (e: 'stepBackward'): void
  (e: 'seekByProgress', progress: number): void
}>();

const hide = () => {
  emit('hide');
};

const takeOver = () => {
  if (!props.sessionId) return;
  window.dispatchEvent(new CustomEvent('takeover', {
    detail: { sessionId: props.sessionId, active: true }
  }));
};

const jumpToRealTime = () => {
  emit('jumpToRealTime');
};

const handleStepForward = () => {
  emit('stepForward');
};

const handleStepBackward = () => {
  emit('stepBackward');
};

const handleSeekByProgress = (progress: number) => {
  emit('seekByProgress', progress);
};

const onVNCConnected = () => {
  vncDisconnected.value = false;
  console.log('VNC connected');
};
const onVNCDisconnected = () => {
  vncDisconnected.value = true;
  console.log('VNC disconnected');
};

const onNewTerminalContent = () => {
  markNewOutput();
};

// Confirmation action handler removed
</script>
