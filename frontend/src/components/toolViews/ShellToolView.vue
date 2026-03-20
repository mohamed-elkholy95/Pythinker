<template>
  <!--
    xterm.js live terminal (Agent UX v2 scaffolding).
    Currently renders the command prompt; streaming output requires backend
    ToolStreamEvent with content_type="terminal" to pipe chunks via
    terminalLiveRef.writeData(). Falls back to static polling view below.
  -->
  <TerminalLiveView
    v-if="live && terminalLiveEnabled"
    ref="terminalLiveRef"
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
      v-else-if="hasShellOutput"
      class="shell-output terminal-tool-shell-output-hover-scroll"
    >
      <code v-html="shell"></code>
    </div>
    <EmptyState v-else class="shell-empty" :message="emptyMessage" icon="terminal" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed, watch, onUnmounted } from 'vue';
import { viewShellSession } from '@/api/agent';
import { ToolContent } from '@/types/message';
import type { ConsoleRecord } from '@/types/response';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';
import TerminalLiveView from './TerminalLiveView.vue';
import { useShiki } from '@/composables/useShiki';
import { cleanPs1, cleanShellOutput } from '@/utils/shellSanitizer';
//import { showErrorToast } from '@/utils/toast';

const props = defineProps<{
  sessionId: string;
  toolContent: ToolContent;
  live: boolean;
}>();

// Terminal live view feature flag (controlled by backend; enabled by default)
const terminalLiveEnabled = ref(true);
const terminalLiveRef = ref<InstanceType<typeof TerminalLiveView>>();

// Extract the command from tool args for the terminal prompt
const currentCommand = computed(() => {
  const cmd = props.toolContent?.args?.command;
  return typeof cmd === 'string' ? cmd : undefined;
});

defineExpose({
  loadContent: () => {
    loadShellContent();
  }
});

const shell = ref('');
const refreshTimer = ref<number | null>(null);

// Shiki highlighting for shell output
const { highlightTerminalDualTheme } = useShiki();

// Get shellSessionId from toolContent
const shellSessionId = computed((): string => {
  if (props.toolContent && props.toolContent.args.id) {
    return String(props.toolContent.args.id);
  }
  return '';
});

const hasShellOutput = computed(() => shell.value.trim().length > 0);
const isLoading = computed(() => props.live && !hasShellOutput.value);
const emptyMessage = computed(() => (props.live ? 'Waiting for output...' : 'No output yet...'));

const updateShellContent = async (console: ConsoleRecord[] | undefined) => {
  if (!console) return;
  let newShell = '';
  for (const e of console) {
    // Clean PS1: strip markers, ensure ends with $
    const ps1 = cleanPs1(e.ps1);
    newShell += `<span class="shell-prompt">${escapeHtml(ps1)}</span>`;

    // Highlight command using Shiki bash
    if (e.command) {
      try {
        const highlightedCmd = await highlightTerminalDualTheme(e.command, 'bash');
        // Extract just the code content from the highlighted output
        const cmdMatch = highlightedCmd.match(/<code[^>]*>([\s\S]*?)<\/code>/);
        const cmdContent = cmdMatch ? cmdMatch[1] : escapeHtml(e.command);
        newShell += `<span class="shell-command"> ${cmdContent}</span>\n`;
      } catch {
        newShell += `<span class="shell-command"> ${escapeHtml(e.command)}</span>\n`;
      }
    } else {
      newShell += '\n';
    }

    // Output as plain text — strip markers and duplicated header
    if (e.output) {
      const output = cleanShellOutput(e.output, e.command);
      if (output) {
        newShell += `<span class="shell-output-text">${escapeHtml(output)}</span>\n`;
      }
    }
  }
  if (newShell !== shell.value) {
    shell.value = newShell;
  }
}

function escapeHtml(text: string): string {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Function to load Shell session content
const loadShellContent = async () => {
  if (!props.live) {
    updateShellContent(props.toolContent.content?.console);
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
  font-family:
    'JetBrains Mono',
    'Fira Code',
    'SF Mono',
    Menlo,
    Monaco,
    'Cascadia Code',
    monospace;
  font-size: 13px;
  line-height: 1.5;
}

.shell-loading,
.shell-empty {
  flex: 1;
  min-height: 0;
}

.shell-output {
  flex: 1;
  min-height: 0;
  padding: 10px 12px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

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

/* Prompt (reference green) */
.shell-output :deep(.shell-prompt) {
  color: var(--terminal-tool-prompt);
}

/* Command + Shiki: inner HTML omits <pre>; spans carry light hex + --shiki-dark custom prop */
.shell-output :deep(.shell-command) {
  color: var(--terminal-tool-text);
}

:global(.dark) .shell-output :deep(.shell-command span),
:global(html[data-theme='dark']) .shell-output :deep(.shell-command span) {
  color: var(--shiki-dark) !important;
}

/* Command output — same body text as reference */
.shell-output :deep(.shell-output-text) {
  color: var(--terminal-tool-text);
}
</style>
