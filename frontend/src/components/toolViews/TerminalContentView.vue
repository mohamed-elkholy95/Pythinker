<template>
  <ContentContainer :scrollable="false" padding="none" class="terminal-view">
    <div class="terminal-shell">
      <div ref="terminalRef" class="terminal-surface"></div>
      <EmptyState
        v-if="!content"
        :message="emptyLabel"
        :icon="emptyIcon"
        overlay
      />
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue';
import { Terminal } from 'xterm';
import { FitAddon } from '@xterm/addon-fit';
import 'xterm/css/xterm.css';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';

const props = defineProps<{
  content: string;
  contentType?: 'shell' | 'file' | 'browser' | 'code' | 'generic';
  isLive?: boolean;
  isWriting?: boolean;
  autoScroll?: boolean;
}>();

const emit = defineEmits<{
  newContent: [];
}>();

const terminalRef = ref<HTMLElement>();
const terminal = ref<Terminal | null>(null);
const fitAddon = new FitAddon();
const lastContent = ref('');
let resizeObserver: ResizeObserver | null = null;

const emptyLabel = computed(() => {
  if (props.contentType === 'shell' || props.contentType === 'code') {
    return 'Waiting for output...';
  }
  if (props.contentType === 'file') {
    return props.isWriting ? 'Generating content...' : 'Reading file...';
  }
  if (props.contentType === 'browser') {
    return 'Browser activity...';
  }
  return 'No output yet...';
});

const emptyIcon = computed(() => {
  if (props.contentType === 'shell') return 'terminal';
  if (props.contentType === 'code') return 'code';
  if (props.contentType === 'file') return 'file';
  if (props.contentType === 'browser') return 'browser';
  return 'inbox';
});

const writeContent = async (nextContent: string) => {
  if (!terminal.value) return;
  emit('newContent');

  const normalized = (nextContent || '').replace(/\r?\n/g, '\r\n');

  if (!lastContent.value) {
    terminal.value.clear();
    terminal.value.write(normalized);
    lastContent.value = nextContent;
  } else if (nextContent.startsWith(lastContent.value)) {
    const delta = nextContent.slice(lastContent.value.length);
    if (delta) {
      terminal.value.write(delta.replace(/\r?\n/g, '\r\n'));
    }
    lastContent.value = nextContent;
  } else {
    terminal.value.clear();
    terminal.value.write(normalized);
    lastContent.value = nextContent;
  }

  if (props.autoScroll !== false) {
    await nextTick();
    terminal.value.scrollToBottom();
  }
};

onMounted(() => {
  if (!terminalRef.value) return;
  terminal.value = new Terminal({
    disableStdin: true,
    convertEol: true,
    fontFamily: "Menlo, Monaco, 'Courier New', monospace",
    fontSize: 13,
    scrollback: 5000,
    theme: {
      background: '#1e1e1e',
      foreground: '#e5e7eb',
    },
  });
  terminal.value.loadAddon(fitAddon);
  terminal.value.open(terminalRef.value);
  fitAddon.fit();
  writeContent(props.content || '');

  resizeObserver = new ResizeObserver(() => {
    requestAnimationFrame(() => fitAddon.fit());
  });
  resizeObserver.observe(terminalRef.value);
});

onUnmounted(() => {
  resizeObserver?.disconnect();
  terminal.value?.dispose();
  terminal.value = null;
});

watch(
  () => props.content,
  (next) => {
    writeContent(next || '');
  },
);
</script>

<style scoped>
.terminal-view {
  position: relative;
}

.terminal-shell {
  position: relative;
  width: 100%;
  height: 100%;
  background: #1e1e1e;
  color: #e5e7eb;
  font-family: Menlo, Monaco, 'Courier New', monospace;
  font-size: 13px;
  overflow: hidden;
}

.terminal-surface {
  width: 100%;
  height: 100%;
}

.terminal-view :deep(.empty-state.overlay) {
  background: rgba(30, 30, 30, 0.85);
}

.terminal-view :deep(.empty-icon),
.terminal-view :deep(.empty-message) {
  color: rgba(229, 231, 235, 0.65);
}
</style>
