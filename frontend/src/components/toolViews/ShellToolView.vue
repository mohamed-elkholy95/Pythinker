<template>
  <!-- When live streaming is active, use xterm.js for real-time terminal output -->
  <TerminalLiveView
    v-if="live && terminalLiveEnabled"
    ref="terminalLiveRef"
    :session-id="sessionId"
    :shell-session-id="shellSessionId ?? ''"
    :command="currentCommand"
  />
  <!-- Existing static view for completed results -->
  <ContentContainer v-else :scrollable="false" padding="none" class="shell-view">
    <div class="shell-body">
      <div class="shell-surface">
        <LoadingState
          v-if="isLoading"
          label="Executing command"
          animation="terminal"
        />
        <div v-else-if="hasShellOutput" class="shell-output">
          <code v-html="shell"></code>
        </div>
        <EmptyState v-else :message="emptyMessage" icon="terminal" />
      </div>
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { onMounted, ref, computed, watch, onUnmounted } from 'vue';
import { viewShellSession } from '@/api/agent';
import { ToolContent } from '@/types/message';
import type { ConsoleRecord } from '@/types/response';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';
import TerminalLiveView from './TerminalLiveView.vue';
import { useShiki } from '@/composables/useShiki';
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
const { highlightDualTheme } = useShiki();

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
    // Green prompt (ubuntu@sandbox:~ $) for visibility on white background
    newShell += `<span class="shell-prompt">${escapeHtml(e.ps1)}</span>`;

    // Highlight command using Shiki bash
    if (e.command) {
      try {
        const highlightedCmd = await highlightDualTheme(e.command, 'bash');
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

    // Output as plain text
    if (e.output) {
      newShell += `<span class="shell-output-text">${escapeHtml(e.output)}</span>\n`;
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

// Start auto-refresh timer
const startAutoRefresh = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
  }
  
  if (props.live && shellSessionId.value) {
    refreshTimer.value = setInterval(() => {
      loadShellContent();
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
});

// Clear timer when component is unmounted
onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<style scoped>
.shell-view {
  flex: 1;
  min-height: 0;
}

.shell-body {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.shell-surface {
  flex: 1;
  width: 100%;
  height: 100%;
  background: #ffffff;
  color: #1f2937;
  font-family: 'SF Mono', Menlo, Monaco, 'Courier New', monospace;
  font-size: 13px;
  overflow: hidden;
}

.shell-output {
  height: 100%;
  padding: 12px 16px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.shell-view :deep(.empty-icon),
.shell-view :deep(.empty-message) {
  color: rgba(31, 41, 55, 0.5);
}

/* Green prompt (ubuntu@sandbox:~ $) */
.shell-output :deep(.shell-prompt) {
  color: #16a34a;
}

/* Dark mode */
:global(.dark) .shell-surface {
  background: var(--terminal-bg);
  color: var(--text-primary);
}

:global(.dark) .shell-view :deep(.empty-icon),
:global(.dark) .shell-view :deep(.empty-message) {
  color: var(--text-tertiary);
}

/* Green prompt in dark mode */
:global(.dark) .shell-output :deep(.shell-prompt) {
  color: #4ade80;
}

/* Highlighted command styling */
.shell-output :deep(.shell-command) {
  color: #1f2937;
}

:global(.dark) .shell-output :deep(.shell-command) {
  color: var(--text-primary);
}

/* Shiki dark theme support */
:global(.dark) .shell-output :deep(.shell-command span) {
  color: var(--shiki-dark) !important;
}

/* Output text styling */
.shell-output :deep(.shell-output-text) {
  color: #6b7280;
}

:global(.dark) .shell-output :deep(.shell-output-text) {
  color: var(--text-secondary);
}
</style>
