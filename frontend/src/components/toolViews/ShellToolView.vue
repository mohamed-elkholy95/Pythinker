<template>
  <ContentContainer :scrollable="false" padding="none" class="shell-view">
    <div class="shell-body">
      <!-- Orange left accent -->
      <div class="shell-accent"></div>
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
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';
//import { showErrorToast } from '@/utils/toast';

const props = defineProps<{
  sessionId: string;
  toolContent: ToolContent;
  live: boolean;
}>();

defineExpose({
  loadContent: () => {
    loadShellContent();
  }
});

const shell = ref('');
const refreshTimer = ref<number | null>(null);

// Get shellSessionId from toolContent
const shellSessionId = computed(() => {
  if (props.toolContent && props.toolContent.args.id) {
    return props.toolContent.args.id;
  }
  return '';
});

const hasShellOutput = computed(() => shell.value.trim().length > 0);
const isLoading = computed(() => props.live && !hasShellOutput.value);
const emptyMessage = computed(() => (props.live ? 'Waiting for output...' : 'No output yet...'));

const updateShellContent = (console: any) => {
  if (!console) return;
  let newShell = '';
  for (const e of console) {
    // Green prompt (ubuntu@sandbox:~ $) for visibility on white background
    newShell += `<span class="shell-prompt">${e.ps1}</span><span> ${e.command}</span>\n`;
    newShell += `<span>${e.output}</span>\n`;
  }
  if (newShell !== shell.value) {
    shell.value = newShell;
  }
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
  } catch (error) {
    console.error("Failed to load shell content:", error);
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

/* Orange left accent border */
.shell-accent {
  width: 2px;
  background: linear-gradient(180deg, #f97316 0%, #ea580c 100%);
  flex-shrink: 0;
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
  background: #1a1a1a;
  color: #e5e7eb;
}

:global(.dark) .shell-view :deep(.empty-icon),
:global(.dark) .shell-view :deep(.empty-message) {
  color: rgba(229, 231, 235, 0.65);
}

/* Green prompt in dark mode */
:global(.dark) .shell-output :deep(.shell-prompt) {
  color: #4ade80;
}
</style>
