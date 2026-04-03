<template>
  <!--
    xterm.js live terminal (Agent UX v2 scaffolding).
    Currently renders the command prompt; streaming output requires backend
    ToolStreamEvent with content_type="terminal" to pipe chunks via
    terminalLiveRef.writeData(). Falls back to static polling view below.
  -->
  <TerminalLiveView
    v-if="live && terminalLiveEnabled"
    :session-id="sessionId"
    :shell-session-id="shellSessionId ?? ''"
    :command="currentCommand"
  />
  <div v-else class="shell-view">
    <LoadingState
      v-if="isLoading"
      class="shell-loading"
      label="Executing command"
      animation="terminal"
    />
    <div
      v-else-if="commandBlocks.length > 0"
      class="shell-output terminal-tool-shell-output-hover-scroll"
    >
      <div
        v-for="(block, idx) in commandBlocks"
        :key="idx"
        class="command-block"
      >
        <!-- Command header: prompt + command -->
        <div class="command-header">
          <span class="shell-prompt">{{ block.ps1 }}</span>
          <span class="shell-command" v-html="block.highlightedCommand"></span>
        </div>
        <!-- Command output -->
        <div v-if="block.output" class="command-output">{{ block.output }}</div>
      </div>
    </div>
    <EmptyState v-else class="shell-empty" :message="emptyMessage" icon="terminal" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed, watch, onUnmounted } from 'vue';
import { viewShellSession } from '@/api/agent';
import { ToolContent } from '@/types/message';
import type { ShellToolContent } from '@/types/toolContent';
import type { ConsoleRecord } from '@/types/response';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';
import TerminalLiveView from './TerminalLiveView.vue';
import { useShiki } from '@/composables/useShiki';
import { cleanPs1, cleanShellOutput } from '@/utils/shellSanitizer';

interface CommandBlock {
  ps1: string;
  highlightedCommand: string;
  output: string;
}

const props = defineProps<{
  sessionId: string;
  toolContent: ToolContent;
  live: boolean;
}>();

// Terminal live view feature flag (controlled by backend; enabled by default)
const terminalLiveEnabled = ref(true);
const terminalLiveRef = ref<InstanceType<typeof TerminalLiveView>>();
const shellPayload = computed(() => props.toolContent.content as ShellToolContent | undefined);

// Extract the command from tool args for the terminal prompt
const currentCommand = computed(() => {
  const cmd = props.toolContent?.args?.command;
  return typeof cmd === 'string' ? cmd : undefined;
});

defineExpose({
  terminalLiveRef,
  loadContent: () => {
    loadShellContent();
  }
});

const commandBlocks = ref<CommandBlock[]>([]);
const refreshTimer = ref<ReturnType<typeof setInterval> | null>(null);

// Shiki highlighting for shell output
const { highlightTerminalDualTheme } = useShiki();

// Get shellSessionId from toolContent
const shellSessionId = computed((): string => {
  if (props.toolContent && props.toolContent.args.id) {
    return String(props.toolContent.args.id);
  }
  return '';
});

const hasShellOutput = computed(() => commandBlocks.value.length > 0);
const isLoading = computed(() => props.live && !hasShellOutput.value);
const emptyMessage = computed(() => (props.live ? 'Waiting for output...' : 'No output yet...'));

function escapeHtml(text: string): string {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const updateShellContent = async (console: ConsoleRecord[] | undefined) => {
  if (!console) return;

  const blocks: CommandBlock[] = [];

  for (const e of console) {
    const ps1 = cleanPs1(e.ps1);

    // Highlight command using Shiki bash
    let highlightedCommand = '';
    if (e.command) {
      try {
        const highlighted = await highlightTerminalDualTheme(e.command, 'bash');
        const match = highlighted.match(/<code[^>]*>([\s\S]*?)<\/code>/);
        highlightedCommand = match ? match[1] : escapeHtml(e.command);
      } catch {
        highlightedCommand = escapeHtml(e.command);
      }
    }

    // Clean output
    let output = '';
    if (e.output) {
      output = cleanShellOutput(e.output, e.command);
    }

    blocks.push({ ps1, highlightedCommand, output });
  }

  commandBlocks.value = blocks;
};

// Function to load Shell session content
const loadShellContent = async () => {
  if (!props.live) {
    const console = shellPayload.value?.console;
    if (Array.isArray(console)) {
      void updateShellContent(console);
    }
    return;
  }

  if (!shellSessionId.value) return;

  try {
    const response = await viewShellSession(props.sessionId, shellSessionId.value);
    updateShellContent(response.console);
  } catch {
    // Shell content load failed - UI shows last known content
  }
};

// Pause polling when tab is not visible
const handleVisibilityChange = () => {
  if (document.hidden) {
    stopAutoRefresh();
  } else if (props.live) {
    loadShellContent();
    startAutoRefresh();
  }
};

// Start auto-refresh timer
const startAutoRefresh = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
  }

  if (props.live && shellSessionId.value && !document.hidden) {
    refreshTimer.value = setInterval(() => {
      if (!document.hidden) {
        loadShellContent();
      }
    }, 5000);
  }
};

// Stop auto-refresh timer
const stopAutoRefresh = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
    refreshTimer.value = null;
  }
};

watch(() => props.toolContent, () => {
  loadShellContent();
});

watch(() => props.toolContent.timestamp, () => {
  loadShellContent();
});

// Watch for live prop changes
watch(() => props.live, (live: boolean) => {
  if (live) {
    loadShellContent();
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
});

// Load content and set up refresh timer when component is mounted
onMounted(() => {
  loadShellContent();
  startAutoRefresh();
  document.addEventListener('visibilitychange', handleVisibilityChange);
});

// Clear timer and listeners when component is unmounted
onUnmounted(() => {
  stopAutoRefresh();
  document.removeEventListener('visibilitychange', handleVisibilityChange);
});
</script>

<style scoped>
.shell-view {
  flex: 1;
  min-height: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--terminal-tool-viewport-bg);
  color: var(--terminal-tool-text);
  border: none;
  border-radius: 0;
  box-sizing: border-box;
  overflow: hidden;
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 13px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.shell-loading,
.shell-empty {
  flex: 1;
  min-height: 0;
}

.shell-output {
  flex: 1;
  min-height: 0;
  padding: 8px 0;
  overflow-x: hidden;
  overflow-y: auto;
}

/* ── Command block: each command is its own visual unit ── */
.command-block {
  padding: 8px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.command-block:last-child {
  border-bottom: none;
}

/* ── Command header: prompt + command on one line ── */
.command-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
  word-break: break-word;
}

/* Prompt — green, non-wrapping */
.shell-prompt {
  color: var(--terminal-tool-prompt) !important;
  flex-shrink: 0;
  white-space: nowrap;
  opacity: 0.7;
  font-size: 12px;
}

/* Command text — wraps naturally at word boundaries */
.command-header :deep(.shell-command) {
  color: var(--terminal-tool-text);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  font-weight: 500;
}

:global(.dark) .command-header :deep(.shell-command span),
:global(html[data-theme='dark']) .command-header :deep(.shell-command span) {
  color: var(--shiki-dark) !important;
}

/* ── Command output ── */
.command-output {
  margin-top: 4px;
  padding: 6px 0 2px;
  color: var(--terminal-tool-text);
  opacity: 0.8;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  font-size: 12px;
  line-height: 1.5;
  max-height: 300px;
  overflow-y: auto;
}

/* Light mode adjustments */
:root:not(.dark) .command-block {
  border-bottom-color: rgba(0, 0, 0, 0.06);
}

/* ── Empty & loading states ── */
.shell-view :deep(.empty-icon),
.shell-view :deep(.empty-message) {
  color: var(--terminal-tool-text-muted);
}

.shell-view :deep(.loading-state.shell-loading) {
  flex: 1;
  min-height: 0;
  background: transparent;
  padding: var(--space-8);
}

.shell-view :deep(.loading-state.shell-loading .loading-text) {
  color: var(--terminal-tool-text);
}

.shell-view :deep(.empty-state.shell-empty) {
  flex: 1;
  min-height: 0;
  padding: var(--space-8) var(--space-4);
}
</style>
