<template>
  <div class="w-full h-full flex flex-col bg-[#1e1e1e] text-gray-100 font-mono text-sm overflow-hidden relative">
    <div ref="terminalRef" class="flex-1 min-h-0 w-full"></div>
    <div
      v-if="!content"
      class="absolute inset-0 flex items-center justify-center text-gray-500 text-sm pointer-events-none"
    >
      {{ emptyLabel }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue';
import { Terminal } from 'xterm';
import { FitAddon } from '@xterm/addon-fit';
import 'xterm/css/xterm.css';

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
